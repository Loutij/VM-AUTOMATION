# =============================================================================
# VM Automation - ESXi Clone Deployment Mixin
# =============================================================================
"""
Mixin pour le déploiement par clone de template sur ESXi/vSphere.

Workflow:
  1. Résolution de la template VMware source (vsphere_template_name)
  2. Cleanup de la VM existante si retry (deployment.vm_id déjà renseigné)
  3. Clone via pyvmomi CloneVM_Task
  4. Attente de la fin du clone (timeout configurable, défaut 10 min)
  5. Personnalisation :
       - Option A : CustomizationSpec pyvmomi (hostname, IP statique/DHCP, DNS)
       - Option B : guestinfo cloud-init (extraConfig guestinfo.userdata/metadata)
         → utilisée en priorité si cloud_init_config est fourni dans la config
  6. Power on de la VM clonée
  7. Attente SSH (Linux) ou VMware Tools (Windows)
  8. Post-configuration SSH (même logique que ESXiLinuxDeployMixin)
  9. Finalisation (démontage, boot order, résumé)

Architecture:
  - ESXiCloneDeployMixin doit être mixé dans ESXiDeploymentService
  - Fournit _execute_clone_deployment() comme point d'entrée
  - Dépend des méthodes fournies par les autres mixins et le service principal :
      self.db, self.vm_service, self._log_step(), _update_deployment_status(),
      _finalize_esxi_deployment(), _linux_post_install_ssh(),
      _wait_for_linux_ready_esxi(), _wait_for_ssh(), _ssh_execute()
"""

from __future__ import annotations

import asyncio
import base64
import json
import socket
import time
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from src.common.exceptions import DeploymentStepError, DeploymentTimeoutError
from src.common.logging import get_logger
from src.domain.deployment_service import DeploymentStep
from src.domain.models import (
    DeploymentStatus,
    OSFamily,
    VirtualMachine,
    VMState,
    VMStatus,
)

if TYPE_CHECKING:
    from src.domain.models import Deployment

# Paramiko pour les connexions SSH post-clone (Linux VMs)
try:
    import paramiko

    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False

logger = get_logger(__name__)

# Timeout clone : 10 min par défaut (vs 40 min pour ISO install)
_CLONE_TIMEOUT = 600

# Intervalle de polling du statut de la tâche clone (secondes)
_CLONE_POLL_INTERVAL = 10

# Timeout attente IP / SSH post-clone (5 min)
_CLONE_SSH_WAIT_TIMEOUT = 300

# Timeout commandes SSH post-clone (2 min)
_CLONE_SSH_CMD_TIMEOUT = 120


class ESXiCloneDeployMixin:
    """
    Mixin fournissant le workflow de déploiement par clone de template ESXi.

    Doit être mixé dans ESXiDeploymentService qui fournit :
      - self.db (AsyncSession)
      - self.vm_service (VMService)
      - self._log_step()
      - self._update_deployment_status()
      - self._finalize_esxi_deployment()
      - self._linux_post_install_ssh()          (depuis ESXiLinuxDeployMixin)
      - self._wait_for_ssh(), _check_ssh_port() (depuis ESXiLinuxDeployMixin)
      - self._ssh_execute()                     (depuis ESXiLinuxDeployMixin)
    """

    # =========================================================================
    # Point d'entrée du workflow clone
    # =========================================================================

    async def _execute_clone_deployment(self, deployment: Deployment) -> None:
        """
        Workflow complet de déploiement par clone de template ESXi.

        Enchaîne toutes les étapes : cleanup éventuel, clone, personnalisation,
        power on, attente SSH/VMware Tools, post-config et finalisation.

        Args:
            deployment: Déploiement à exécuter (deployment_method == "clone").
        """
        config = deployment.config
        template_config = config.get("template") or {}
        vm_name = config["vm_name"]

        # Détecter la famille OS pour les étapes suivantes
        os_family = template_config.get("os_family", "linux")
        if hasattr(os_family, "value"):
            os_family = os_family.value
        os_family = str(os_family).lower()

        client = await self.vm_service._get_hypervisor_client(
            deployment.hypervisor_id
        )

        # ── 1. Résoudre le nom de la template VMware source ──
        template_name = self._resolve_template_name(config, template_config)
        await self._log_step(
            deployment,
            DeploymentStep.CREATING_VM,
            f"Template source identifiée : {template_name}",
        )

        # ── 2. Cleanup si retry (vm_id déjà renseigné) ──
        if deployment.vm_id:
            await self._clone_cleanup_existing_vm(deployment, client, vm_name)

        # ── 3. Clone de la template ──
        await self._update_deployment_status(
            deployment,
            DeploymentStatus.IN_PROGRESS,
            DeploymentStep.CREATING_VM,
        )
        await self._log_step(
            deployment,
            DeploymentStep.CREATING_VM,
            f"Clonage de la template '{template_name}' → '{vm_name}'...",
        )

        timeout = config.get("clone_timeout", _CLONE_TIMEOUT)
        vm = await self._clone_template(
            deployment, client, template_name, vm_name, os_family, timeout
        )
        deployment.vm_id = vm.id
        await self.db.commit()

        await self._log_step(
            deployment,
            DeploymentStep.CREATING_VM,
            f"Clone créé : {vm_name} (id hyperviseur : {vm.hypervisor_vm_id})",
        )

        # ── 4. Personnalisation : cloud-init guestinfo OU CustomizationSpec ──
        await self._update_deployment_status(
            deployment,
            DeploymentStatus.IN_PROGRESS,
            DeploymentStep.POST_CONFIGURATION,
        )

        use_guestinfo = self._should_use_guestinfo(config)

        if use_guestinfo:
            await self._log_step(
                deployment,
                DeploymentStep.POST_CONFIGURATION,
                "Personnalisation via guestinfo cloud-init (extraConfig)...",
            )
            await self._apply_guestinfo_cloud_init(deployment, client, vm, os_family)
        else:
            await self._log_step(
                deployment,
                DeploymentStep.POST_CONFIGURATION,
                "Personnalisation via CustomizationSpec pyvmomi...",
            )
            await self._apply_customization_spec(deployment, client, vm, os_family)

        # ── 5. Power on de la VM ──
        await self._update_deployment_status(
            deployment,
            DeploymentStatus.IN_PROGRESS,
            DeploymentStep.STARTING_INSTALLATION,
        )
        await self._log_step(
            deployment,
            DeploymentStep.STARTING_INSTALLATION,
            f"Démarrage de la VM '{vm_name}'...",
        )
        await self.vm_service.start_vm(vm.id)

        # ── 6. Attente SSH (Linux) / VMware Tools (Windows) ──
        await self._update_deployment_status(
            deployment,
            DeploymentStatus.IN_PROGRESS,
            DeploymentStep.WAITING_SSH_READY,
        )

        if os_family == "linux":
            await self._log_step(
                deployment,
                DeploymentStep.WAITING_SSH_READY,
                "Attente de SSH post-clone (Linux)...",
            )
            ssh_ready = await self._wait_for_clone_ssh_ready(
                deployment, vm, client, timeout=_CLONE_SSH_WAIT_TIMEOUT
            )
        else:
            await self._log_step(
                deployment,
                DeploymentStep.WAITING_SSH_READY,
                "Attente VMware Tools (Windows)...",
            )
            ssh_ready = await self._wait_for_clone_vmtools_ready(
                deployment, vm, client, timeout=_CLONE_SSH_WAIT_TIMEOUT
            )

        # ── 7. Post-configuration SSH (Linux uniquement) ──
        if os_family == "linux":
            await self._update_deployment_status(
                deployment,
                DeploymentStatus.IN_PROGRESS,
                DeploymentStep.LINUX_POST_INSTALL,
            )
            if ssh_ready:
                await self._linux_post_install_ssh(deployment, vm, client)
            else:
                await self._log_step(
                    deployment,
                    DeploymentStep.LINUX_POST_INSTALL,
                    "SSH non accessible — post-configuration ignorée",
                    "warning",
                )

            # Paquets additionnels
            packages = config.get("packages") or []
            if packages and ssh_ready:
                await self._update_deployment_status(
                    deployment,
                    DeploymentStatus.IN_PROGRESS,
                    DeploymentStep.INSTALLING_SOFTWARE,
                )
                await self._install_linux_packages_ssh(
                    deployment, vm, client, packages
                )

        # ── 8. Finalisation ──
        await self._finalize_esxi_deployment(deployment, vm, os_family)

    # =========================================================================
    # Résolution du nom de la template
    # =========================================================================

    def _resolve_template_name(
        self, config: dict, template_config: dict
    ) -> str:
        """
        Résout le nom de la template VMware à cloner.

        Priorité :
          1. ``vsphere_template_name`` dans la config du déploiement
          2. ``vsphere_template_name`` dans le template OS (template_config)
          3. Fallback sur le nom du template OS préfixé par "tpl-"

        Args:
            config: Configuration du déploiement.
            template_config: Sous-dictionnaire ``config["template"]``.

        Returns:
            Nom de la template VMware (ex: "tpl-debian-12").

        Raises:
            DeploymentStepError: Si aucun nom de template n'est trouvable.
        """
        # 1. Priorité absolue : champ dans la config de déploiement
        name = config.get("vsphere_template_name")
        if name:
            return str(name)

        # 2. Champ dans le template OS
        name = template_config.get("vsphere_template_name")
        if name:
            return str(name)

        # 3. Fallback : préfixe "tpl-" + nom du template OS normalisé
        os_name = template_config.get("name") or template_config.get("os_type")
        if os_name:
            safe_name = (
                str(os_name)
                .lower()
                .replace(" ", "-")
                .replace("_", "-")
            )
            return f"tpl-{safe_name}"

        raise DeploymentStepError(
            "",
            DeploymentStep.CREATING_VM,
            "Impossible de déterminer le nom de la template VMware à cloner. "
            "Configurez 'vsphere_template_name' dans le template OS ou la config "
            "du déploiement.",
        )

    # =========================================================================
    # Cleanup de la VM existante (retry)
    # =========================================================================

    async def _clone_cleanup_existing_vm(
        self,
        deployment: Deployment,
        client: Any,
        vm_name: str,
    ) -> None:
        """
        Nettoie la VM existante avant un retry de clone.

        Arrête la VM si elle tourne, la supprime sur l'hyperviseur et en base.

        Args:
            deployment: Déploiement en retry.
            client: Client ESXi connecté.
            vm_name: Nom de la VM à nettoyer.
        """
        from sqlalchemy import select

        await self._log_step(
            deployment,
            DeploymentStep.CREATING_VM,
            f"Retry détecté — nettoyage de la VM existante '{vm_name}'...",
        )

        # Récupérer la VM en base
        vm_result = await self.db.execute(
            select(VirtualMachine).where(VirtualMachine.id == deployment.vm_id)
        )
        db_vm = vm_result.scalar_one_or_none()

        if db_vm:
            try:
                vm_identifier = db_vm.hypervisor_vm_id or db_vm.name
                esxi_vm = await client.get_vm(vm_identifier)

                if esxi_vm:
                    # Arrêter si en cours
                    state = await client.get_vm_state(vm_identifier)
                    if state and state.lower() in ("running", "poweredon"):
                        await client.stop_vm(vm_identifier, force=True)
                        await self._log_step(
                            deployment,
                            DeploymentStep.CREATING_VM,
                            f"VM '{vm_name}' arrêtée",
                        )

                    # Supprimer sur l'hyperviseur
                    await client.delete_vm(vm_identifier, delete_disks=True)
                    await self._log_step(
                        deployment,
                        DeploymentStep.CREATING_VM,
                        f"VM '{vm_name}' supprimée sur l'hyperviseur",
                    )

            except Exception as e:
                logger.warning(
                    "esxi_clone_retry_cleanup_failed",
                    vm_name=vm_name,
                    error=str(e),
                )
                await self._log_step(
                    deployment,
                    DeploymentStep.CREATING_VM,
                    f"Avertissement nettoyage VM : {e}",
                    "warning",
                )

            # Supprimer en base dans tous les cas
            await self.db.delete(db_vm)
            await self.db.flush()
            deployment.vm_id = None

        else:
            # VM disparue de la base — tenter un nettoyage hyperviseur
            try:
                vm_info = await client.get_vm(vm_name)
                if vm_info:
                    await client.delete_vm(vm_info.id, delete_disks=True)
                    await self._log_step(
                        deployment,
                        DeploymentStep.CREATING_VM,
                        f"VM orpheline '{vm_name}' supprimée sur l'hyperviseur",
                    )
            except Exception as e:
                logger.warning(
                    "esxi_clone_retry_orphan_cleanup_failed",
                    vm_name=vm_name,
                    error=str(e),
                )

    # =========================================================================
    # Clone pyvmomi
    # =========================================================================

    async def _clone_template(
        self,
        deployment: Deployment,
        client: Any,
        template_name: str,
        vm_name: str,
        os_family: str,
        timeout: int = _CLONE_TIMEOUT,
    ) -> VirtualMachine:
        """
        Clone une template VMware via pyvmomi CloneVM_Task.

        Configure les ressources (CPU, RAM, disque) via la RelocationSpec et
        CloneSpec. Attend la fin de la tâche de clone avec polling.

        Args:
            deployment: Déploiement en cours.
            client: Client ESXi pyvmomi connecté.
            template_name: Nom de la template VMware source.
            vm_name: Nom de la VM destination.
            os_family: Famille OS ("linux" ou "windows").
            timeout: Timeout en secondes (défaut 10 min).

        Returns:
            VirtualMachine créée en base.

        Raises:
            DeploymentStepError: Si la template n'est pas trouvée.
            DeploymentTimeoutError: Si le clone dépasse le timeout.
        """
        config = deployment.config
        template_config = config.get("template") or {}

        # Récupérer les ressources cibles
        cpu_count = config.get("cpu_count", 2)
        ram_gb = config.get("ram_gb", 4)
        disk_gb = config.get("disk_gb", 60)
        datastore = (
            config.get("datastore")
            or getattr(client, "default_datastore", "datastore1")
        )
        resource_pool = config.get("resource_pool") or ""

        def _do_clone() -> str:
            """Exécute le clone synchrone dans un thread (pyvmomi est synchrone)."""
            try:
                from pyVmomi import vim
            except ImportError:
                raise DeploymentStepError(
                    "",
                    DeploymentStep.CREATING_VM,
                    "pyvmomi non disponible — impossible de cloner la template",
                )

            client._ensure_connected()
            si = client.service_instance
            content = si.RetrieveContent()

            # ── Chercher la template source ──
            template_vm = client._get_obj([vim.VirtualMachine], template_name)
            if template_vm is None:
                raise DeploymentStepError(
                    "",
                    DeploymentStep.CREATING_VM,
                    f"Template VMware '{template_name}' introuvable sur l'hôte ESXi. "
                    f"Vérifiez que la template existe et est accessible.",
                )

            # ── Résoudre le datastore de destination ──
            target_ds = client._get_obj([vim.Datastore], datastore)
            if target_ds is None:
                # Fallback sur le datastore de la template
                target_ds = template_vm.config.files.vmPathName.split("]")[0].lstrip("[")
                target_ds = client._get_obj([vim.Datastore], target_ds)

            # ── Résoudre le resource pool ──
            if resource_pool:
                rp = client._get_obj([vim.ResourcePool], resource_pool)
            else:
                # Utiliser le resource pool par défaut de l'hôte
                host_objs = client._get_all_objs([vim.HostSystem])
                if host_objs:
                    rp = host_objs[0].parent.resourcePool
                else:
                    # Datacenter — chercher "Resources" par défaut
                    rp = client._get_obj([vim.ResourcePool], "Resources")

            # ── RelocateSpec : datastore + resource pool ──
            relocate_spec = vim.vm.RelocateSpec()
            if target_ds:
                relocate_spec.datastore = target_ds
            if rp:
                relocate_spec.pool = rp

            # ── ConfigSpec : ajuster CPU/RAM si nécessaire ──
            config_spec = vim.vm.ConfigSpec()
            config_spec.numCPUs = cpu_count
            config_spec.memoryMB = ram_gb * 1024

            # ── CloneSpec ──
            clone_spec = vim.vm.CloneSpec()
            clone_spec.location = relocate_spec
            clone_spec.config = config_spec
            clone_spec.powerOn = False  # On démarre manuellement après personnalisation
            clone_spec.template = False  # Crée une VM normale, pas une template

            # ── Résoudre le dossier de destination ──
            if client.datacenter:
                datacenter = client._get_obj([vim.Datacenter], client.datacenter)
                dest_folder = datacenter.vmFolder if datacenter else content.rootFolder
            else:
                dest_folder = content.rootFolder

            # ── Lancer la tâche de clone ──
            task = template_vm.Clone(
                folder=dest_folder,
                name=vm_name,
                spec=clone_spec,
            )

            # ── Polling de la tâche avec timeout ──
            start = time.time()
            while True:
                elapsed = int(time.time() - start)
                state = task.info.state

                if state == vim.TaskInfo.State.success:
                    cloned_vm = task.info.result
                    return cloned_vm.config.instanceUuid or cloned_vm._moId

                if state == vim.TaskInfo.State.error:
                    error = task.info.error
                    msg = str(error.msg if hasattr(error, "msg") else error)
                    raise DeploymentStepError(
                        "",
                        DeploymentStep.CREATING_VM,
                        f"Clone ESXi échoué : {msg}",
                    )

                if elapsed >= timeout:
                    raise DeploymentTimeoutError(
                        f"Clone de '{template_name}' → '{vm_name}' "
                        f"timeout après {timeout}s"
                    )

                time.sleep(_CLONE_POLL_INTERVAL)

        # Exécuter le clone dans un thread (pyvmomi est synchrone/bloquant)
        esxi_instance_uuid = await asyncio.to_thread(_do_clone)

        await self._log_step(
            deployment,
            DeploymentStep.CREATING_VM,
            f"Clone terminé — instanceUuid : {esxi_instance_uuid}",
        )

        # ── Créer l'enregistrement VirtualMachine en base ──
        from src.domain._esxi_deploy_vm_creation import _get_guest_os_id

        hypervisor = await self.vm_service.get_hypervisor(deployment.hypervisor_id)
        ds = (
            config.get("datastore")
            or getattr(hypervisor, "default_datastore", None)
            or "datastore1"
        )

        vm = await self.vm_service.create_vm(
            name=vm_name,
            hypervisor_id=deployment.hypervisor_id,
            cpu_count=cpu_count,
            ram_gb=ram_gb,
            disk_gb=disk_gb,
            network_switch=config.get("network_switch"),
            template_id=None,
            force=True,
            datastore=ds,
            resource_pool=resource_pool,
            guest_os_id=_get_guest_os_id(template_config),
            disk_format=config.get("disk_format", "thin"),
        )

        # Mettre à jour le hypervisor_vm_id avec l'UUID de la VM clonée
        vm.hypervisor_vm_id = esxi_instance_uuid
        if deployment.os_template_id:
            vm.os_template_id = deployment.os_template_id
        await self.db.flush()

        return vm

    # =========================================================================
    # Choix de la méthode de personnalisation
    # =========================================================================

    def _should_use_guestinfo(self, config: dict) -> bool:
        """
        Détermine si on utilise guestinfo cloud-init ou CustomizationSpec.

        Règle :
          - Si ``cloud_init_config`` est présent dans la config → guestinfo
          - Si ``customization_method == "guestinfo"`` → guestinfo
          - Sinon → CustomizationSpec (comportement par défaut)

        Args:
            config: Configuration complète du déploiement.

        Returns:
            True si guestinfo cloud-init doit être utilisé.
        """
        if config.get("cloud_init_config"):
            return True
        if config.get("customization_method") == "guestinfo":
            return True
        return False

    # =========================================================================
    # Option A : Personnalisation via guestinfo cloud-init
    # =========================================================================

    async def _apply_guestinfo_cloud_init(
        self,
        deployment: Deployment,
        client: Any,
        vm: VirtualMachine,
        os_family: str,
    ) -> None:
        """
        Personnalise la VM clonée via guestinfo cloud-init.

        Injecte les données cloud-init dans les extraConfig VMware :
          - ``guestinfo.userdata`` : user-data cloud-init encodé en base64
          - ``guestinfo.userdata.encoding`` : "base64"
          - ``guestinfo.metadata`` : metadata (instance-id, hostname)
          - ``guestinfo.metadata.encoding`` : "base64"

        Ces champs sont lus automatiquement par cloud-init au démarrage via
        le datasource VMware (cloud-init >= 21.3).

        Args:
            deployment: Déploiement en cours.
            client: Client ESXi connecté.
            vm: VirtualMachine base créée après clone.
            os_family: Famille OS.
        """
        config = deployment.config
        template_config = config.get("template") or {}
        vm_id = vm.hypervisor_vm_id or vm.name

        hostname = config.get("hostname", config["vm_name"])
        username = config.get("username", "otoroot")
        password = config.get("admin_password", "tooroto")
        ip_config = config.get("ip_config") or {}

        # Utiliser un cloud-init user-data personnalisé ou en générer un
        cloud_init_raw = config.get("cloud_init_config")
        if not cloud_init_raw:
            # Générer un user-data cloud-init minimal depuis la template engine
            cloud_init_raw = self.template_engine.render_cloud_init(
                hostname=hostname,
                username=username,
                user_password=password,
                ssh_password_auth=True,
            )

        # Metadata cloud-init : instance-id + hostname obligatoires
        metadata = {
            "instance-id": f"vm-auto-{vm.id}",
            "local-hostname": hostname,
        }

        # Ajouter la config réseau dans les metadata si IP statique
        if ip_config.get("static_ip"):
            network_config = self._build_cloud_init_network_config(ip_config)
            metadata["network"] = network_config

        metadata_yaml = json.dumps(metadata)  # JSON valide = YAML valide

        # Encoder en base64 (format attendu par VMware guestinfo)
        userdata_b64 = base64.b64encode(
            cloud_init_raw.encode("utf-8")
        ).decode("ascii")
        metadata_b64 = base64.b64encode(
            metadata_yaml.encode("utf-8")
        ).decode("ascii")

        def _inject_guestinfo() -> None:
            """Injecte les guestinfo dans les extraConfig de la VM."""
            try:
                from pyVmomi import vim
            except ImportError:
                raise DeploymentStepError(
                    "",
                    DeploymentStep.POST_CONFIGURATION,
                    "pyvmomi non disponible — impossible d'injecter les guestinfo",
                )

            vm_obj = client._get_vm_by_id(vm_id)
            if vm_obj is None:
                raise DeploymentStepError(
                    "",
                    DeploymentStep.POST_CONFIGURATION,
                    f"VM '{vm_id}' introuvable pour injection guestinfo",
                )

            extra_config_items = [
                vim.option.OptionValue(
                    key="guestinfo.userdata",
                    value=userdata_b64,
                ),
                vim.option.OptionValue(
                    key="guestinfo.userdata.encoding",
                    value="base64",
                ),
                vim.option.OptionValue(
                    key="guestinfo.metadata",
                    value=metadata_b64,
                ),
                vim.option.OptionValue(
                    key="guestinfo.metadata.encoding",
                    value="base64",
                ),
            ]

            config_spec = vim.vm.ConfigSpec()
            config_spec.extraConfig = extra_config_items
            task = vm_obj.ReconfigVM_Task(spec=config_spec)
            client._wait_for_task(task)

        await asyncio.to_thread(_inject_guestinfo)

        await self._log_step(
            deployment,
            DeploymentStep.POST_CONFIGURATION,
            f"guestinfo cloud-init injectés (hostname={hostname}, "
            f"ip={'statique' if ip_config.get('static_ip') else 'DHCP'})",
        )

    def _build_cloud_init_network_config(self, ip_config: dict) -> dict:
        """
        Construit la configuration réseau cloud-init depuis la ip_config.

        Retourne un dictionnaire au format cloud-init network v2.

        Args:
            ip_config: Dictionnaire de configuration IP du déploiement.

        Returns:
            Dict cloud-init network config (network v2).
        """
        addresses = []
        if ip_config.get("ip_address"):
            prefix = ip_config.get("prefix_length", 24)
            # Supporter netmask au format CIDR ou texte
            if ip_config.get("prefix_length"):
                prefix = int(ip_config["prefix_length"])
            elif ip_config.get("netmask"):
                prefix = self._netmask_to_prefix(ip_config["netmask"])
            addresses.append(f"{ip_config['ip_address']}/{prefix}")

        gateway = ip_config.get("gateway")
        dns = [
            d for d in [
                ip_config.get("dns_server_1"),
                ip_config.get("dns_server_2"),
            ] if d
        ]

        eth0_config: dict[str, Any] = {
            "dhcp4": False,
            "addresses": addresses,
        }
        if gateway:
            eth0_config["gateway4"] = gateway
        if dns:
            eth0_config["nameservers"] = {"addresses": dns}

        return {
            "version": 2,
            "ethernets": {
                "ens192": eth0_config,  # Nom typique pour VMware VMXNET3
            },
        }

    @staticmethod
    def _netmask_to_prefix(netmask: str) -> int:
        """Convertit un masque réseau en longueur de préfixe CIDR."""
        try:
            return sum(bin(int(octet)).count("1") for octet in netmask.split("."))
        except (ValueError, AttributeError):
            return 24  # Fallback /24

    # =========================================================================
    # Option B : Personnalisation via CustomizationSpec pyvmomi
    # =========================================================================

    async def _apply_customization_spec(
        self,
        deployment: Deployment,
        client: Any,
        vm: VirtualMachine,
        os_family: str,
    ) -> None:
        """
        Personnalise la VM clonée via CustomizationSpec pyvmomi.

        Configure le hostname, la configuration réseau (statique ou DHCP)
        et les DNS via l'API vSphere CustomizationSpec.

        Supporte Linux et Windows :
          - Linux : LinuxPrep (hostname + timezone)
          - Windows : Sysprep (hostname + timezone + AutoLogon + ProductKey)

        La configuration réseau (IP statique / DHCP) est commune aux deux OS.

        Args:
            deployment: Déploiement en cours.
            client: Client ESXi connecté.
            vm: VirtualMachine base créée après clone.
            os_family: Famille OS ("linux" ou "windows").
        """
        config = deployment.config
        ip_config = config.get("ip_config") or {}
        hostname = config.get("hostname", config["vm_name"])
        # Sanitize hostname pour RFC 952 (max 15 chars Windows)
        safe_hostname = self._sanitize_hostname(hostname)
        tz = config.get("timezone", "Europe/Paris")
        vm_id = vm.hypervisor_vm_id or vm.name

        def _do_customize() -> None:
            """Applique le CustomizationSpec synchrone (pyvmomi est synchrone)."""
            try:
                from pyVmomi import vim
            except ImportError:
                raise DeploymentStepError(
                    "",
                    DeploymentStep.POST_CONFIGURATION,
                    "pyvmomi non disponible — CustomizationSpec impossible",
                )

            vm_obj = client._get_vm_by_id(vm_id)
            if vm_obj is None:
                raise DeploymentStepError(
                    "",
                    DeploymentStep.POST_CONFIGURATION,
                    f"VM '{vm_id}' introuvable pour CustomizationSpec",
                )

            # ── Identity (Linux ou Windows) ──
            if os_family == "linux":
                identity = vim.vm.customization.LinuxPrep()
                identity.hostName = vim.vm.customization.FixedName(name=safe_hostname)
                identity.timeZone = tz
                identity.hwClockUTC = True
            else:
                # Windows Sysprep
                username = config.get("admin_username", "Administrator")
                password_val = config.get("admin_password", "tooroto")
                product_key = config.get("product_key", "")

                sysprep = vim.vm.customization.Sysprep()

                # GuiUnattended
                gui = vim.vm.customization.GuiUnattended()
                gui.autoLogon = True
                gui.autoLogonCount = 1
                gui.timeZone = 110  # Code timezone Windows (110 = Paris/Europe)
                win_pass = vim.vm.customization.Password()
                win_pass.value = password_val
                win_pass.plainText = True
                gui.password = win_pass
                sysprep.guiUnattended = gui

                # UserData
                user_data = vim.vm.customization.UserData()
                user_data.computerName = vim.vm.customization.FixedName(
                    name=safe_hostname
                )
                user_data.fullName = username
                user_data.orgName = "OTO Mation"
                if product_key:
                    user_data.productId = product_key
                sysprep.userData = user_data

                # Identification (workgroup ou domaine)
                domain_join = config.get("domain_join") or {}
                if domain_join.get("domain"):
                    domain_id = vim.vm.customization.JoinDomainSpec()
                    domain_id.domainAdmin = domain_join.get("username", "")
                    domain_id.domain = domain_join["domain"]
                    domain_pass = vim.vm.customization.Password()
                    domain_pass.value = domain_join.get("password", "")
                    domain_pass.plainText = True
                    domain_id.domainAdminPassword = domain_pass
                    sysprep.identification = domain_id
                else:
                    wg_id = vim.vm.customization.JoinWorkgroupSpec()
                    wg_id.workgroup = config.get("workgroup", "WORKGROUP")
                    sysprep.identification = wg_id

                identity = sysprep

            # ── Configuration réseau ──
            adapter_mapping = vim.vm.customization.AdapterMapping()
            adapter = vim.vm.customization.IPSettings()

            if ip_config.get("static_ip") and ip_config.get("ip_address"):
                fixed_ip = vim.vm.customization.FixedIp()
                fixed_ip.ipAddress = ip_config["ip_address"]
                adapter.ip = fixed_ip
                adapter.subnetMask = ip_config.get("netmask", "255.255.255.0")
                if ip_config.get("gateway"):
                    adapter.gateway = [ip_config["gateway"]]
                dns_servers = [
                    d for d in [
                        ip_config.get("dns_server_1"),
                        ip_config.get("dns_server_2"),
                    ] if d
                ]
                if dns_servers:
                    adapter.dnsServerList = dns_servers
            else:
                # DHCP
                adapter.ip = vim.vm.customization.DhcpIpGenerator()

            adapter_mapping.adapter = adapter

            # ── GlobalIPSettings ──
            global_ip = vim.vm.customization.GlobalIPSettings()
            dns_suffix = config.get("dns_suffix", "")
            if dns_suffix:
                global_ip.dnsSuffixList = [dns_suffix]
            dns1 = ip_config.get("dns_server_1")
            dns2 = ip_config.get("dns_server_2")
            dns_list = [d for d in [dns1, dns2] if d]
            if dns_list:
                global_ip.dnsServerList = dns_list

            # ── CustomizationSpec ──
            customization_spec = vim.vm.customization.Specification()
            customization_spec.identity = identity
            customization_spec.nicSettingMap = [adapter_mapping]
            customization_spec.globalIPSettings = global_ip

            # Appliquer la spec
            task = vm_obj.Customize(spec=customization_spec)
            client._wait_for_task(task)

        try:
            await asyncio.to_thread(_do_customize)
            await self._log_step(
                deployment,
                DeploymentStep.POST_CONFIGURATION,
                f"CustomizationSpec appliquée : hostname={safe_hostname}, "
                f"ip={'statique' if ip_config.get('static_ip') else 'DHCP'}, "
                f"os={os_family}",
            )
        except DeploymentStepError:
            raise
        except Exception as e:
            # CustomizationSpec peut échouer si VMware Tools n'est pas installé
            # dans la template → non fatal, on continue
            logger.warning(
                "esxi_clone_customization_spec_failed",
                vm_id=vm_id,
                error=str(e),
            )
            await self._log_step(
                deployment,
                DeploymentStep.POST_CONFIGURATION,
                f"Avertissement CustomizationSpec : {e} — "
                f"La personnalisation se fera au premier démarrage via cloud-init",
                "warning",
            )

    # =========================================================================
    # Attente SSH post-clone (Linux)
    # =========================================================================

    async def _wait_for_clone_ssh_ready(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        client: Any,
        timeout: int = _CLONE_SSH_WAIT_TIMEOUT,
    ) -> bool:
        """
        Attend que la VM Linux clonée soit accessible en SSH.

        Contrairement au workflow ISO, le délai est beaucoup plus court
        (pas d'installation OS) : on attend juste le démarrage + cloud-init.

        Phase 1 : Récupérer l'IP via VMware Tools (attente heartbeat).
        Phase 2 : Tester SSH avec authentification.

        Args:
            deployment: Déploiement en cours.
            vm: VirtualMachine clonée.
            client: Client ESXi connecté.
            timeout: Timeout total en secondes.

        Returns:
            True si SSH est accessible, False en cas de timeout.
        """
        vm_id = vm.hypervisor_vm_id or vm.name
        username = deployment.config.get("username", "otoroot")
        password = deployment.config.get("admin_password", "tooroto")
        start = time.time()
        poll_interval = 15  # Secondes entre chaque tentative

        await self._log_step(
            deployment,
            DeploymentStep.WAITING_SSH_READY,
            "Attente démarrage VM et disponibilité SSH...",
        )

        vm_ip = None
        while (time.time() - start) < timeout:
            elapsed = int(time.time() - start)

            # Tenter de récupérer l'IP via VMware Tools
            if not vm_ip:
                try:
                    ips = await client.get_vm_ip_addresses(vm_id)
                    if ips:
                        vm_ip = ips[0]
                        vm.ip_address = vm_ip
                        await self.db.flush()
                        await self._log_step(
                            deployment,
                            DeploymentStep.WAITING_SSH_READY,
                            f"IP détectée : {vm_ip} ({elapsed}s)",
                        )
                except Exception as e:
                    logger.debug(
                        "esxi_clone_ip_poll_error",
                        vm_id=vm_id,
                        elapsed=elapsed,
                        error=str(e),
                    )

            # Si on a une IP, tester SSH
            if vm_ip:
                port_open = await self._check_ssh_port(vm_ip)
                if port_open:
                    if PARAMIKO_AVAILABLE:
                        ssh_ok = await self._check_ssh_auth(vm_ip, username, password)
                        if ssh_ok:
                            await self._log_step(
                                deployment,
                                DeploymentStep.WAITING_SSH_READY,
                                f"SSH opérationnel : {username}@{vm_ip} ({elapsed}s)",
                            )
                            return True
                    else:
                        # Sans paramiko, le port ouvert suffit
                        await self._log_step(
                            deployment,
                            DeploymentStep.WAITING_SSH_READY,
                            f"Port SSH 22 ouvert sur {vm_ip} ({elapsed}s)",
                        )
                        return True

            if elapsed % 60 == 0 and elapsed > 0:
                await self._log_step(
                    deployment,
                    DeploymentStep.WAITING_SSH_READY,
                    f"Attente SSH... {elapsed}s / {timeout}s"
                    + (f" (ip={vm_ip})" if vm_ip else " (IP non encore disponible)"),
                )

            await asyncio.sleep(poll_interval)

        elapsed = int(time.time() - start)
        await self._log_step(
            deployment,
            DeploymentStep.WAITING_SSH_READY,
            f"Timeout SSH après {elapsed}s — VM peut-être pas encore démarrée",
            "warning",
        )
        return False

    # =========================================================================
    # Attente VMware Tools post-clone (Windows)
    # =========================================================================

    async def _wait_for_clone_vmtools_ready(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        client: Any,
        timeout: int = _CLONE_SSH_WAIT_TIMEOUT,
    ) -> bool:
        """
        Attend que la VM Windows clonée soit prête via le heartbeat VMware Tools.

        Récupère également l'IP dès qu'elle est disponible.

        Args:
            deployment: Déploiement en cours.
            vm: VirtualMachine clonée.
            client: Client ESXi connecté.
            timeout: Timeout total en secondes.

        Returns:
            True si VMware Tools est opérationnel, False en cas de timeout.
        """
        vm_id = vm.hypervisor_vm_id or vm.name
        start = time.time()
        poll_interval = 15

        await self._log_step(
            deployment,
            DeploymentStep.WAITING_SSH_READY,
            "Attente VMware Tools heartbeat (Windows)...",
        )

        while (time.time() - start) < timeout:
            elapsed = int(time.time() - start)
            try:
                heartbeat = await client.get_vm_heartbeat(vm_id)
                if heartbeat and heartbeat.lower() == "green":
                    # Récupérer l'IP
                    try:
                        ips = await client.get_vm_ip_addresses(vm_id)
                        if ips:
                            vm.ip_address = ips[0]
                            await self.db.flush()
                    except Exception:
                        pass

                    await self._log_step(
                        deployment,
                        DeploymentStep.WAITING_SSH_READY,
                        f"VMware Tools heartbeat OK ({elapsed}s)"
                        + (f" — IP : {vm.ip_address}" if vm.ip_address else ""),
                    )
                    return True

                if elapsed % 60 == 0 and elapsed > 0:
                    await self._log_step(
                        deployment,
                        DeploymentStep.WAITING_SSH_READY,
                        f"Attente VMware Tools... {elapsed}s / {timeout}s "
                        f"(heartbeat={heartbeat or 'inconnu'})",
                    )

            except Exception as e:
                logger.debug(
                    "esxi_clone_vmtools_poll_error",
                    vm_id=vm_id,
                    elapsed=elapsed,
                    error=str(e),
                )

            await asyncio.sleep(poll_interval)

        elapsed = int(time.time() - start)
        await self._log_step(
            deployment,
            DeploymentStep.WAITING_SSH_READY,
            f"Timeout VMware Tools après {elapsed}s",
            "warning",
        )
        return False
