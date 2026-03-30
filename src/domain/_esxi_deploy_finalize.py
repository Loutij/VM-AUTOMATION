# =============================================================================
# VM Automation - ESXi Deployment Finalization Mixin
# =============================================================================
"""
Mixin pour la finalisation et le nettoyage des deploiements ESXi/vSphere.

Gere :
- Recuperation des informations reseau finales (IP, hostname)
- Demontage des ISOs et medias d'installation
- Retrait des peripheriques temporaires (floppy pour Windows)
- Reconfiguration du boot order (disque dur en premier)
- Nettoyage des fichiers temporaires sur le datastore
- Generation du resume de deploiement
- Marquage du deploiement comme termine
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from src.common.logging import get_logger
from src.domain.models import DeploymentStatus, VMState, VMStatus

if TYPE_CHECKING:
    from src.domain.models import Deployment, VirtualMachine

logger = get_logger(__name__)


class ESXiFinalizeMixin:
    """Mixin de finalisation pour les deploiements ESXi."""

    # ------------------------------------------------------------------
    # Point d'entree principal
    # ------------------------------------------------------------------

    async def _finalize_esxi_deployment(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        os_family: str,
    ) -> None:
        """
        Finalise un deploiement ESXi (Windows ou Linux).

        Etapes :
        1. Recuperation des informations reseau
        2. Demontage des ISOs et floppy
        3. Reconfiguration du boot order
        4. Nettoyage des fichiers temporaires sur le datastore
        5. Mise a jour de l'etat VM en base
        6. Generation du resume
        7. Marquage du deploiement comme termine

        Args:
            deployment: Deploiement en cours.
            vm: Machine virtuelle associee.
            os_family: ``"linux"`` ou ``"windows"``.
        """
        from src.domain.deployment_service import DeploymentStep

        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.FINALIZING
        )

        client = await self.vm_service._get_hypervisor_client(deployment.hypervisor_id)
        vm_id = vm.hypervisor_vm_id or vm.name
        config: dict[str, Any] = deployment.config

        try:
            # ── 1. Informations reseau ───────────────────────────────────
            await self._esxi_finalize_network(deployment, vm, client, vm_id)

            # ── 2. Demontage des medias d'installation ───────────────────
            await self._esxi_finalize_unmount(
                deployment, client, vm_id, os_family
            )

            # ── 3. Boot order : disque dur en premier ────────────────────
            await self._esxi_finalize_boot_order(deployment, client, vm_id)

            # ── 4. Nettoyage des fichiers temporaires sur le datastore ───
            await self._esxi_finalize_cleanup(deployment, client, config)

            # ── 5. Mise a jour de l'etat VM en base ──────────────────────
            vm.state = VMState.RUNNING
            vm.status = VMStatus.RUNNING
            await self.db.flush()

            # ── 6. Resume du deploiement ─────────────────────────────────
            await self._esxi_finalize_summary(deployment, vm, config, os_family, client)

            # ── 7. Deploiement termine ───────────────────────────────────
            await self._update_deployment_status(
                deployment,
                DeploymentStatus.COMPLETED,
                DeploymentStep.COMPLETED,
                "Deploiement ESXi termine avec succes",
            )
            deployment.completed_at = datetime.now(timezone.utc)
            await self.db.commit()

            await self._log_step(
                deployment, DeploymentStep.COMPLETED,
                "Deploiement termine avec succes !",
            )

            logger.info(
                "esxi_deployment_completed",
                deployment_id=str(deployment.id),
                vm_id=str(vm.id),
                vm_name=config.get("vm_name"),
                os_family=os_family,
            )

        except Exception as e:
            logger.error(
                "esxi_finalize_error",
                deployment_id=str(deployment.id),
                error=str(e),
            )
            await self._log_step(
                deployment, DeploymentStep.FINALIZING,
                f"Erreur lors de la finalisation : {e}",
                "error",
            )

    # ------------------------------------------------------------------
    # Sous-etapes de finalisation
    # ------------------------------------------------------------------

    async def _esxi_finalize_network(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        client: Any,
        vm_id: str,
    ) -> None:
        """Recupere et enregistre les informations reseau de la VM."""
        from src.domain.deployment_service import DeploymentStep

        await self._log_step(
            deployment, DeploymentStep.FINALIZING,
            "Recuperation des informations reseau...",
        )
        try:
            network_info = await client.get_vm_network_summary(vm_id)

            if network_info.get("ip_addresses"):
                ip = network_info["ip_addresses"][0]
                await self._log_step(
                    deployment, DeploymentStep.FINALIZING,
                    f"Adresse IP de la VM : {ip}",
                )
                vm.ip_address = ip
                await self.db.flush()

            if network_info.get("hostname"):
                await self._log_step(
                    deployment, DeploymentStep.FINALIZING,
                    f"Hostname : {network_info['hostname']}",
                )

        except Exception as e:
            logger.warning(
                "esxi_finalize_network_error",
                vm_id=vm_id,
                error=str(e),
            )
            await self._log_step(
                deployment, DeploymentStep.FINALIZING,
                f"Impossible de recuperer les infos reseau : {e}",
                "warning",
            )

    async def _esxi_finalize_unmount(
        self,
        deployment: Deployment,
        client: Any,
        vm_id: str,
        os_family: str,
    ) -> None:
        """Demonte les ISOs et retire le lecteur floppy si necessaire."""
        from src.domain.deployment_service import DeploymentStep

        await self._log_step(
            deployment, DeploymentStep.FINALIZING,
            "Demontage des medias d'installation...",
        )

        # Demonter toutes les ISOs montees
        try:
            await client.unmount_iso(vm_id, unmount_all=True)
            await self._log_step(
                deployment, DeploymentStep.FINALIZING,
                "ISO demontees",
            )
        except Exception as e:
            logger.warning("esxi_finalize_unmount_iso_error", error=str(e))
            await self._log_step(
                deployment, DeploymentStep.FINALIZING,
                f"Avertissement demontage ISO : {e}",
                "warning",
            )

        # Retirer le lecteur floppy (ajoute pour unattend.xml Windows)
        if os_family == "windows":
            try:
                await self._esxi_remove_floppy_drive(client, vm_id)
                await self._log_step(
                    deployment, DeploymentStep.FINALIZING,
                    "Lecteur floppy retire",
                )
            except Exception as e:
                logger.warning("esxi_finalize_floppy_error", error=str(e))
                await self._log_step(
                    deployment, DeploymentStep.FINALIZING,
                    f"Avertissement retrait floppy : {e}",
                    "warning",
                )

    async def _esxi_finalize_boot_order(
        self,
        deployment: Deployment,
        client: Any,
        vm_id: str,
    ) -> None:
        """Reconfigure le boot order : disque dur en premier."""
        from src.domain.deployment_service import DeploymentStep

        try:
            await client.set_first_boot_device(vm_id, "HardDrive")
            await self._log_step(
                deployment, DeploymentStep.FINALIZING,
                "Boot order : disque dur en premier",
            )
        except Exception as e:
            logger.warning("esxi_finalize_boot_order_error", error=str(e))
            await self._log_step(
                deployment, DeploymentStep.FINALIZING,
                f"Avertissement boot order : {e}",
                "warning",
            )

    async def _esxi_finalize_cleanup(
        self,
        deployment: Deployment,
        client: Any,
        config: dict[str, Any],
    ) -> None:
        """Nettoie les fichiers temporaires du datastore."""
        from src.domain.deployment_service import DeploymentStep

        await self._log_step(
            deployment, DeploymentStep.FINALIZING,
            "Nettoyage des fichiers temporaires...",
        )
        try:
            await self._cleanup_datastore_temp_files(client, config)
            await self._log_step(
                deployment, DeploymentStep.FINALIZING,
                "Fichiers temporaires nettoyes",
            )
        except Exception as e:
            logger.warning("esxi_finalize_cleanup_error", error=str(e))
            await self._log_step(
                deployment, DeploymentStep.FINALIZING,
                f"Avertissement nettoyage : {e}",
                "warning",
            )

    async def _esxi_finalize_summary(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        config: dict[str, Any],
        os_family: str,
        client: Any,
    ) -> None:
        """Genere et enregistre le resume du deploiement."""
        from src.domain.deployment_service import DeploymentStep

        # Nom d'utilisateur selon la famille OS
        if os_family == "linux":
            username = config.get("username", "otoroot")
        else:
            username = config.get("admin_username", "otoroot")

        host_label = getattr(client, "host", "inconnu")

        summary_lines = [
            f"VM : {config.get('vm_name', vm.name)}",
            f"Hyperviseur : ESXi ({host_label})",
            f"Hostname : {config.get('hostname', config.get('vm_name', vm.name))}",
            f"OS : {os_family.capitalize()}",
            f"Utilisateur : {username}",
            f"IP : {vm.ip_address or 'DHCP'}",
            f"CPU : {config.get('cpu_count', 2)} vCPU",
            f"RAM : {config.get('ram_gb', 4)} Go",
            f"Disque : {config.get('disk_gb', 60)} Go ({config.get('disk_format', 'thin')})",
        ]

        # Datastore utilise
        ds_name = config.get("datastore") or getattr(client, "default_datastore", None)
        if ds_name:
            summary_lines.append(f"Datastore : {ds_name}")

        # Domaine Active Directory (Windows)
        domain_join = config.get("domain_join") or {}
        if domain_join.get("domain"):
            summary_lines.append(f"Domaine AD : {domain_join['domain']}")

        # Paquets installes
        packages = config.get("packages") or []
        if packages:
            summary_lines.append(f"Paquets : {', '.join(packages)}")

        # Profil logiciel
        software_profile = config.get("software_profile")
        if software_profile:
            summary_lines.append(f"Profil logiciel : {software_profile}")

        await self._log_step(
            deployment, DeploymentStep.FINALIZING,
            "Resume du deploiement :\n" + "\n".join(summary_lines),
        )

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------

    async def _cleanup_datastore_temp_files(
        self,
        client: Any,
        config: dict[str, Any],
    ) -> None:
        """
        Supprime les fichiers temporaires crees sur le datastore pendant
        le deploiement (ISOs seed, images floppy, etc.).

        Les erreurs de suppression sont non fatales : on les log et on continue.
        """
        vm_name = config.get("vm_name", "")
        ds_name = config.get("datastore") or getattr(
            client, "default_datastore", None
        )

        if not ds_name:
            logger.warning(
                "esxi_cleanup_no_datastore",
                vm_name=vm_name,
            )
            return

        # Liste des fichiers temporaires a supprimer
        temp_paths = [
            # ISO seed cloud-init / autoinstall
            f"vm-automation-temp/seed-iso/{vm_name}_seed.iso",
            # Image floppy unattend Windows
            f"vm-automation-temp/floppy/{vm_name}_unattend.flp",
            # ISO preseed remaster Debian
            f"vm-automation-temp/remaster/{vm_name}_preseed.iso",
            # ISO patched Ubuntu autoinstall
            f"vm-automation-temp/patched/{vm_name}_install.iso",
        ]

        deleted_count = 0
        for path in temp_paths:
            try:
                await client.delete_datastore_file(ds_name, path)
                deleted_count += 1
                logger.debug("esxi_temp_file_deleted", datastore=ds_name, path=path)
            except Exception:
                # Fichier inexistant ou deja supprime — non fatal
                pass

        if deleted_count:
            logger.info(
                "esxi_temp_files_cleaned",
                vm_name=vm_name,
                datastore=ds_name,
                deleted=deleted_count,
            )

    async def _esxi_remove_floppy_drive(
        self,
        client: Any,
        vm_id: str,
    ) -> None:
        """
        Retire le lecteur floppy virtuel ajoute pendant le deploiement Windows.

        Utilise l'API pyVmomi pour reconfigurer la VM et supprimer tous les
        peripheriques VirtualFloppy.
        """

        def _remove() -> None:
            from pyVmomi import vim

            vm_obj = client._get_vm_by_id(vm_id)
            if vm_obj is None:
                logger.warning(
                    "esxi_remove_floppy_vm_not_found",
                    vm_id=vm_id,
                )
                return

            device_changes: list = []
            for dev in vm_obj.config.hardware.device:
                if isinstance(dev, vim.vm.device.VirtualFloppy):
                    spec = vim.vm.device.VirtualDeviceSpec()
                    spec.operation = (
                        vim.vm.device.VirtualDeviceSpec.Operation.remove
                    )
                    spec.device = dev
                    device_changes.append(spec)

            if not device_changes:
                logger.debug("esxi_remove_floppy_none_found", vm_id=vm_id)
                return

            config_spec = vim.vm.ConfigSpec()
            config_spec.deviceChange = device_changes
            task = vm_obj.ReconfigVM_Task(spec=config_spec)
            client._wait_for_task(task)

            logger.info(
                "esxi_floppy_removed",
                vm_id=vm_id,
                count=len(device_changes),
            )

        await asyncio.to_thread(_remove)

    # ------------------------------------------------------------------
    # Finalisation avec avertissements (VM prete mais post-config incomplete)
    # ------------------------------------------------------------------

    async def _finalize_esxi_deployment_with_warnings(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        os_family: str,
        warning_message: str,
    ) -> None:
        """
        Finalise un deploiement ESXi qui s'est termine avec des avertissements.

        Meme logique que ``_finalize_esxi_deployment`` mais marque le statut
        final comme ``COMPLETED_WITH_WARNINGS``.

        Args:
            deployment: Deploiement en cours.
            vm: Machine virtuelle associee.
            os_family: ``"linux"`` ou ``"windows"``.
            warning_message: Message d'avertissement a inclure.
        """
        from src.domain.deployment_service import DeploymentStep

        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.FINALIZING
        )

        client = await self.vm_service._get_hypervisor_client(deployment.hypervisor_id)
        vm_id = vm.hypervisor_vm_id or vm.name
        config: dict[str, Any] = deployment.config

        try:
            # Memes etapes de nettoyage
            await self._esxi_finalize_network(deployment, vm, client, vm_id)
            await self._esxi_finalize_unmount(deployment, client, vm_id, os_family)
            await self._esxi_finalize_boot_order(deployment, client, vm_id)
            await self._esxi_finalize_cleanup(deployment, client, config)

            # Etat VM
            vm.state = VMState.RUNNING
            vm.status = VMStatus.RUNNING
            await self.db.flush()

            # Resume
            await self._esxi_finalize_summary(deployment, vm, config, os_family, client)

            # Marquer comme termine avec avertissements
            await self._update_deployment_status(
                deployment,
                DeploymentStatus.COMPLETED_WITH_WARNINGS,
                DeploymentStep.COMPLETED,
                warning_message,
            )
            deployment.completed_at = datetime.now(timezone.utc)
            await self.db.commit()

            await self._log_step(
                deployment, DeploymentStep.COMPLETED,
                f"Deploiement termine avec avertissements : {warning_message}",
                "warning",
            )

            logger.info(
                "esxi_deployment_completed_with_warnings",
                deployment_id=str(deployment.id),
                vm_id=str(vm.id),
                warning=warning_message,
            )

        except Exception as e:
            logger.error(
                "esxi_finalize_warning_error",
                deployment_id=str(deployment.id),
                error=str(e),
            )
            await self._log_step(
                deployment, DeploymentStep.FINALIZING,
                f"Erreur lors de la finalisation : {e}",
                "error",
            )
