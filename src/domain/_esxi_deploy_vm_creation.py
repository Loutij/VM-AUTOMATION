# =============================================================================
# VM Automation - ESXi VM Creation Mixin
# =============================================================================
"""
Mixin pour la création de VMs ESXi dans le service de déploiement.

Fournit les méthodes de création de VM et de vérification d'espace datastore
pour les déploiements ESXi/vSphere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from src.common.exceptions import ValidationError
from src.common.logging import get_logger
from src.domain.models import VirtualMachine

if TYPE_CHECKING:
    from src.domain.models import Deployment

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Mapping template/OS → guestId VMware
# ─────────────────────────────────────────────────────────────────────────────
GUEST_OS_MAP: dict[str, str] = {
    # Windows
    "windows_10": "windows9_64Guest",
    "windows_11": "windows9_64Guest",
    "windows_server_2019": "windows2019srv_64Guest",
    "windows_server_2022": "windows2019srvNext_64Guest",
    "windows_server_2025": "windows2022srvNext_64Guest",
    # Linux
    "ubuntu": "ubuntu64Guest",
    "debian": "debian11_64Guest",
    "debian_12": "debian12_64Guest",
    "debian_13": "debian12_64Guest",
    "rocky": "centos9_64Guest",
    "rocky_9": "centos9_64Guest",
    "rhel": "rhel9_64Guest",
    "rhel_9": "rhel9_64Guest",
    "centos": "centos8_64Guest",
    # Fallback génériques
    "windows": "windows9_64Guest",
    "linux": "otherLinux64Guest",
}


def _get_guest_os_id(template_config: dict) -> str:
    """Détermine le guestId VMware depuis la config du template.

    Cherche d'abord dans le nom du template, puis dans l'os_family.
    """
    name = (template_config.get("name") or "").lower().replace(" ", "_")
    for key, guest_id in GUEST_OS_MAP.items():
        if key in name:
            return guest_id

    os_family = str(template_config.get("os_family", "linux")).lower()
    return GUEST_OS_MAP.get(os_family, "otherGuest64")


class ESXiVMCreationMixin:
    """Mixin fournissant la création de VM et la gestion des datastores ESXi."""

    async def _create_vm_for_esxi(self, deployment: Deployment) -> VirtualMachine:
        """
        Crée ou réutilise une VM pour le déploiement ESXi.

        En mode retry (deployment.vm_id existe), tente de supprimer la VM
        existante sur l'hyperviseur et en base, puis en recrée une.
        En première exécution, nettoie les VMs orphelines éventuelles.
        """
        config = deployment.config
        vm_name = config["vm_name"]
        template_config = config.get("template") or {}

        # ── Mode retry : supprimer la VM existante ──
        if deployment.vm_id:
            vm_result = await self.db.execute(
                select(VirtualMachine).where(VirtualMachine.id == deployment.vm_id)
            )
            db_vm = vm_result.scalar_one_or_none()

            if db_vm:
                try:
                    client = await self.vm_service._get_hypervisor_client(
                        deployment.hypervisor_id
                    )
                    vm_identifier = db_vm.hypervisor_vm_id or db_vm.name
                    esxi_vm = await client.get_vm(vm_identifier)

                    if esxi_vm:
                        logger.info(
                            "esxi_retry_deleting_existing_vm",
                            deployment_id=str(deployment.id),
                            vm_name=vm_name,
                        )
                        # Arrêter la VM si elle tourne
                        state = await client.get_vm_state(vm_identifier)
                        if state and state.lower() in ("running", "poweredon"):
                            await client.stop_vm(vm_identifier, force=True)

                        # Supprimer la VM sur l'hyperviseur
                        await client.delete_vm(vm_identifier, delete_disks=True)

                except Exception as e:
                    logger.warning(
                        "esxi_retry_cleanup_failed",
                        error=str(e),
                        vm_name=vm_name,
                    )

                # Supprimer l'enregistrement en base dans tous les cas
                await self.db.delete(db_vm)
                await self.db.flush()
            else:
                # VM en base disparue — tenter de nettoyer l'hyperviseur
                try:
                    client = await self.vm_service._get_hypervisor_client(
                        deployment.hypervisor_id
                    )
                    vm_info = await client.get_vm(vm_name)
                    if vm_info:
                        await client.delete_vm(vm_info.id, delete_disks=True)
                except Exception as e:
                    logger.warning(
                        "esxi_retry_cleanup_hypervisor_vm_failed",
                        error=str(e),
                    )
        else:
            # Première exécution : nettoyer une éventuelle VM orpheline du même nom
            await self.vm_service.cleanup_vm_if_exists(
                vm_name, deployment.hypervisor_id, force=True
            )

        # ── Créer une nouvelle VM ──
        # Utiliser ram_gb de la config, fallback sur memory_mb
        ram_gb = config.get("ram_gb", 4)
        if "memory_mb" in config:
            ram_gb = config["memory_mb"] // 1024

        guest_os_id = _get_guest_os_id(template_config)

        # Récupérer le datastore et resource pool depuis la config ou l'hyperviseur
        hypervisor = await self.vm_service.get_hypervisor(deployment.hypervisor_id)
        datastore = (
            config.get("datastore")
            or getattr(hypervisor, "default_datastore", None)
            or "datastore1"
        )
        resource_pool = (
            config.get("resource_pool")
            or getattr(hypervisor, "default_resource_pool", None)
            or ""
        )

        vm = await self.vm_service.create_vm(
            name=vm_name,
            hypervisor_id=deployment.hypervisor_id,
            cpu_count=config.get("cpu_count", 2),
            ram_gb=ram_gb,
            disk_gb=config.get("disk_gb", 60),
            network_switch=config.get("network_switch"),
            template_id=None,
            force=True,
            # Paramètres ESXi passés via **kwargs → VMSpecs
            datastore=datastore,
            resource_pool=resource_pool,
            guest_os_id=guest_os_id,
            disk_format=config.get("disk_format", "thin"),
        )

        if deployment.os_template_id:
            vm.os_template_id = deployment.os_template_id
            await self.db.flush()

        return vm

    async def _check_datastore_space(self, deployment: Deployment) -> None:
        """
        Vérifie l'espace disponible sur le datastore ESXi cible.

        Interroge le vSphere API via le client ESXi pour obtenir les infos
        du datastore. Lève une ValidationError si l'espace est insuffisant.
        Ne bloque pas si le datastore n'est pas trouvé (avertissement seul).
        """
        config = deployment.config
        disk_gb = config.get("disk_gb", 60)
        # Marge 1.5x pour le thin provisioning, les snapshots, et la swap VM
        required_gb = float(disk_gb) * 1.5

        client = await self.vm_service._get_hypervisor_client(
            deployment.hypervisor_id
        )

        hypervisor = await self.vm_service.get_hypervisor(deployment.hypervisor_id)
        target_ds = (
            config.get("datastore")
            or getattr(hypervisor, "default_datastore", None)
            or getattr(client, "default_datastore", "datastore1")
        )

        try:
            # Import conditionnel de pyvmomi (même logique que esxi_client.py)
            try:
                from pyVmomi import vim as vim_mod
            except ImportError:
                logger.warning(
                    "esxi_datastore_check_skipped",
                    reason="pyvmomi non installé",
                )
                return

            # Utiliser les méthodes du client ESXi pour interroger vSphere
            client._ensure_connected()

            datacenter = None
            if client.datacenter:
                datacenter = client._get_obj(
                    [vim_mod.Datacenter], client.datacenter
                )

            if datacenter:
                datastores = datacenter.datastore
            else:
                # ESXi direct — récupérer tous les datastores
                datastores = client._get_all_objs([vim_mod.Datastore])

            for ds in datastores:
                if ds.name == target_ds:
                    summary = ds.summary
                    free_gb = summary.freeSpace / (1024 ** 3)
                    capacity_gb = summary.capacity / (1024 ** 3)

                    logger.info(
                        "esxi_datastore_space_check",
                        datastore=target_ds,
                        free_gb=f"{free_gb:.1f}",
                        capacity_gb=f"{capacity_gb:.1f}",
                        required_gb=f"{required_gb:.0f}",
                    )

                    if free_gb < required_gb:
                        raise ValidationError(
                            f"Espace insuffisant sur {target_ds}: "
                            f"{free_gb:.1f} Go libre, {required_gb:.0f} Go requis"
                        )
                    return

            # Datastore non trouvé — avertissement sans bloquer
            logger.warning(
                "esxi_datastore_not_found",
                datastore=target_ds,
                available=[ds.name for ds in datastores],
            )

        except ValidationError:
            # Re-lever les erreurs de validation
            raise
        except Exception as e:
            # Erreur de connexion vSphere — avertissement sans bloquer
            logger.warning(
                "esxi_datastore_check_failed",
                datastore=target_ds,
                error=str(e),
            )
