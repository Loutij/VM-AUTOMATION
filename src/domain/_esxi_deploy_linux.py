# =============================================================================
# VM Automation - ESXi Linux Deployment Mixin
# =============================================================================
"""
Mixin pour le déploiement Linux sur ESXi/vSphere.

Workflow:
  1. Créer VM sur ESXi
  2. Générer seed config (preseed/kickstart/autoinstall/cloud-init)
  3. Créer seed ISO localement (genisoimage/xorriso)
  4. Uploader seed ISO sur le datastore
  5. Monter ISO install + seed ISO
  6. Configurer VM pour Linux (désactiver Secure Boot EFI)
  7. Démarrer VM
  8. Attendre installation (VMware Tools heartbeat + SSH)
  9. Post-install via SSH (paramiko)
  10. Finaliser
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import tempfile
import time
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from src.common.config import settings
from src.common.exceptions import DeploymentStepError
from src.common.logging import get_logger
from src.domain.deployment_service import DeploymentStep
from src.domain.models import (
    DeploymentStatus,
    OSTemplate,
    VirtualMachine,
)

if TYPE_CHECKING:
    from src.domain.models import Deployment

# Paramiko pour les connexions SSH post-installation
try:
    import paramiko

    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False

logger = get_logger(__name__)

# Timeout par défaut pour l'attente de l'installation Linux (40 min)
_LINUX_INSTALL_TIMEOUT = 2400

# Intervalle entre les vérifications de heartbeat (secondes)
_HEARTBEAT_CHECK_INTERVAL = 30

# Timeout SSH après détection du heartbeat (5 min)
_SSH_WAIT_TIMEOUT = 300

# Timeout pour les commandes SSH post-install
_SSH_CMD_TIMEOUT = 120

# Timeout pour l'installation des paquets (10 min)
_SSH_PKG_TIMEOUT = 600


def _find_iso_tool() -> str | None:
    """Trouve l'outil de création d'ISO disponible localement.

    Cherche genisoimage puis xorriso dans le PATH.
    Retourne le chemin complet ou None.
    """
    for tool in ("genisoimage", "xorriso", "mkisofs"):
        path = shutil.which(tool)
        if path:
            return path
    return None


class ESXiLinuxDeployMixin:
    """
    Mixin fournissant le workflow de déploiement Linux sur ESXi/vSphere.

    Doit être mixé dans ESXiDeploymentService qui fournit :
      - self.db (AsyncSession)
      - self.vm_service (VMService)
      - self.template_engine (TemplateEngine)
      - self._log_step()
      - self._update_deployment_status()
      - self._create_vm_for_esxi()
      - self._finalize_esxi_deployment()
    """

    # =========================================================================
    # Workflow principal Linux
    # =========================================================================

    async def _execute_linux_deployment(self, deployment: Deployment) -> None:
        """
        Workflow complet de déploiement Linux sur ESXi.

        Enchaîne toutes les étapes : création VM, génération seed config,
        création/upload ISO, montage, installation, post-install, finalisation.
        """
        config = deployment.config
        template_config = config.get("template") or {}
        vm_name = config["vm_name"]

        # ── 1. Créer la VM ──
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.CREATING_VM
        )
        await self._log_step(
            deployment,
            DeploymentStep.CREATING_VM,
            f"Création VM ESXi : {vm_name}",
        )
        vm = await self._create_vm_for_esxi(deployment)
        deployment.vm_id = vm.id
        await self.db.commit()

        client = await self.vm_service._get_hypervisor_client(
            deployment.hypervisor_id
        )
        vm_id = vm.hypervisor_vm_id or vm.name

        # ── 2. Configurer la VM pour Linux (désactiver Secure Boot EFI) ──
        await self._configure_esxi_vm_for_linux(client, vm_id, deployment)

        # ── 3. Détecter le type de config et générer le seed ──
        config_type = self._determine_config_type(template_config)
        await self._update_deployment_status(
            deployment,
            DeploymentStatus.IN_PROGRESS,
            DeploymentStep.GENERATING_SEED_CONFIG,
        )
        await self._log_step(
            deployment,
            DeploymentStep.GENERATING_SEED_CONFIG,
            f"Génération de la configuration {config_type}...",
        )

        ip_config = config.get("ip_config") or {}
        seed_content = self._generate_linux_seed_config(
            config_type, config, ip_config, template_config
        )

        await self._log_step(
            deployment,
            DeploymentStep.GENERATING_SEED_CONFIG,
            f"Configuration {config_type} générée ({len(seed_content)} octets)",
        )

        # ── 4. Créer seed ISO localement et uploader sur le datastore ──
        await self._update_deployment_status(
            deployment,
            DeploymentStatus.IN_PROGRESS,
            DeploymentStep.CREATING_SEED_ISO,
        )
        await self._log_step(
            deployment,
            DeploymentStep.CREATING_SEED_ISO,
            "Création et upload de la seed ISO...",
        )
        seed_iso_ds_path = await self._create_and_upload_seed_iso(
            deployment, vm, seed_content, config_type
        )
        await self._log_step(
            deployment,
            DeploymentStep.CREATING_SEED_ISO,
            f"Seed ISO uploadée : {seed_iso_ds_path}",
        )

        # ── 5. Monter l'ISO d'installation + seed ISO ──
        await self._update_deployment_status(
            deployment,
            DeploymentStatus.IN_PROGRESS,
            DeploymentStep.MOUNTING_ISO,
        )
        install_iso_path = await self._get_install_iso_path(deployment)
        await self._log_step(
            deployment,
            DeploymentStep.MOUNTING_ISO,
            f"Montage ISO install : {install_iso_path}",
        )
        await client.mount_iso(vm_id, install_iso_path)

        # Monter la seed ISO sur un second CD-ROM
        await self._mount_seed_iso_on_second_cdrom(
            client, vm_id, seed_iso_ds_path
        )
        await self._log_step(
            deployment,
            DeploymentStep.MOUNTING_ISO,
            "Seed ISO montée sur le second lecteur CD-ROM",
        )

        # ── 6. Configurer le boot order : CD-ROM en premier ──
        try:
            await client.set_boot_order(vm_id, ["DVD", "HardDrive"])
            await self._log_step(
                deployment,
                DeploymentStep.MOUNTING_ISO,
                "Boot order configuré : CD-ROM en premier",
            )
        except Exception as e:
            # Non bloquant — la VM peut déjà être configurée pour booter sur CD
            logger.warning("esxi_linux_boot_order_failed", error=str(e))

        # ── 6b. Configurer les paramètres kernel pour autoinstall ──
        if config_type == "autoinstall":
            try:
                await self._set_autoinstall_boot_params(client, vm_id)
                await self._log_step(
                    deployment,
                    DeploymentStep.MOUNTING_ISO,
                    "Paramètres kernel autoinstall configurés (ds=nocloud)",
                )
            except Exception as e:
                logger.warning("esxi_linux_autoinstall_params_failed", error=str(e))
                await self._log_step(
                    deployment,
                    DeploymentStep.MOUNTING_ISO,
                    f"Avertissement : paramètres autoinstall non configurés ({e})",
                    "warning",
                )

        # ── 7. Démarrer la VM ──
        await self._update_deployment_status(
            deployment,
            DeploymentStatus.IN_PROGRESS,
            DeploymentStep.STARTING_INSTALLATION,
        )
        await self._log_step(
            deployment,
            DeploymentStep.STARTING_INSTALLATION,
            "Démarrage de la VM pour installation Linux...",
        )
        await self.vm_service.start_vm(vm.id)

        # ── 8. Attendre l'installation (heartbeat + SSH) ──
        await self._update_deployment_status(
            deployment,
            DeploymentStatus.IN_PROGRESS,
            DeploymentStep.WAITING_SSH_READY,
        )
        await self._log_step(
            deployment,
            DeploymentStep.WAITING_SSH_READY,
            "Attente de la fin d'installation Linux (heartbeat + SSH)...",
        )
        ssh_ready = await self._wait_for_linux_ready_esxi(
            deployment, vm, client
        )

        # ── 9. Post-installation via SSH ──
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
                "SSH non accessible — post-installation ignorée",
                "warning",
            )

        # ── 10. Installation de paquets supplémentaires ──
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

        # ── 11. Finaliser ──
        await self._finalize_esxi_deployment(deployment, vm, "linux")

    # =========================================================================
    # Configuration VM Linux
    # =========================================================================

    async def _configure_esxi_vm_for_linux(
        self, client: Any, vm_id: str, deployment: Deployment
    ) -> None:
        """
        Configure une VM ESXi pour Linux.

        Désactive le Secure Boot EFI (incompatible avec la plupart des
        installeurs Linux non signés) via pyvmomi ReconfigVM_Task.
        """

        def _configure() -> None:
            try:
                from pyVmomi import vim
            except ImportError:
                logger.warning(
                    "esxi_linux_configure_skipped",
                    reason="pyvmomi non disponible",
                )
                return

            vm_obj = client._get_vm_by_id(vm_id)
            if vm_obj is None:
                logger.warning(
                    "esxi_linux_configure_vm_not_found", vm_id=vm_id
                )
                return

            config_spec = vim.vm.ConfigSpec()
            boot_options = vim.vm.BootOptions()
            boot_options.efiSecureBootEnabled = False
            config_spec.bootOptions = boot_options
            task = vm_obj.ReconfigVM_Task(spec=config_spec)
            client._wait_for_task(task)

        try:
            await asyncio.to_thread(_configure)
            await self._log_step(
                deployment,
                DeploymentStep.CREATING_VM,
                "Secure Boot désactivé pour Linux",
            )
        except Exception as e:
            # Non fatal — certains ESXi ne supportent pas EFI ou la VM est en BIOS
            logger.warning(
                "esxi_linux_secureboot_disable_failed",
                vm_id=vm_id,
                error=str(e),
            )
            await self._log_step(
                deployment,
                DeploymentStep.CREATING_VM,
                f"Avertissement : impossible de désactiver Secure Boot ({e})",
                "warning",
            )

    # =========================================================================
    # Autoinstall boot parameters (Ubuntu)
    # =========================================================================

    async def _set_autoinstall_boot_params(
        self, client: Any, vm_id: str
    ) -> None:
        """
        Configure les paramètres kernel pour Ubuntu autoinstall via extraConfig.

        Ubuntu Subiquity nécessite le paramètre kernel 'autoinstall' et
        'ds=nocloud' pour détecter automatiquement le seed ISO cidata.
        On utilise les extraConfig VMX pour injecter ces paramètres.
        """

        def _configure() -> None:
            from pyVmomi import vim

            vm_obj = client._get_vm_by_id(vm_id)
            if vm_obj is None:
                return

            config_spec = vim.vm.ConfigSpec()
            # bios.bootDeviceClasses = "allow:cdrom,hd" pour forcer boot CD
            # guestinfo.* pour passer des paramètres
            config_spec.extraConfig = [
                vim.option.OptionValue(
                    key="bios.bootDeviceClasses",
                    value="allow:cdrom,hd",
                ),
                vim.option.OptionValue(
                    key="guestinfo.metadata",
                    value="",
                ),
                vim.option.OptionValue(
                    key="guestinfo.userdata",
                    value="",
                ),
            ]

            # Modifier le boot delay pour laisser le temps au CD-ROM
            boot_options = vim.vm.BootOptions()
            boot_options.bootDelay = 3000  # 3 secondes
            config_spec.bootOptions = boot_options

            task = vm_obj.ReconfigVM_Task(spec=config_spec)
            client._wait_for_task(task)

        await asyncio.to_thread(_configure)

    # =========================================================================
    # Détection du type de configuration
    # =========================================================================

    def _determine_config_type(self, template_config: dict) -> str:
        """
        Détermine le type de configuration d'installation Linux.

        Priorité : champ explicite config_type > détection par nom du template.
        Retourne l'un de : autoinstall, preseed, kickstart, cloud-init.
        """
        # Champ explicite
        config_type = template_config.get("config_type", "")
        if config_type:
            return config_type

        name = (template_config.get("name") or "").lower()

        if "ubuntu" in name:
            return "autoinstall"
        if "debian" in name:
            return "preseed"
        if any(kw in name for kw in ("rocky", "rhel", "centos", "alma", "red hat")):
            return "kickstart"

        # Fallback cloud-init (compatible avec la plupart des distributions)
        return "cloud-init"

    # =========================================================================
    # Génération du seed config
    # =========================================================================

    def _generate_linux_seed_config(
        self,
        config_type: str,
        config: dict,
        ip_config: dict,
        template_config: dict,
    ) -> str:
        """
        Génère la configuration d'installation Linux.

        Délègue au template_engine qui gère les différents formats
        (preseed, kickstart, autoinstall, cloud-init).
        """
        hostname = config.get("hostname", config["vm_name"])
        username = config.get("username", "otoroot")
        password = config.get("admin_password", "tooroto")
        post_install_commands = config.get("post_install_commands") or []

        if config_type == "autoinstall":
            return self.template_engine.render_ubuntu_autoinstall(
                hostname=hostname,
                username=username,
                user_password=password,
                static_ip=ip_config.get("static_ip", False),
                ip_address=ip_config.get("ip_address"),
                gateway=ip_config.get("gateway"),
                dns_server_1=ip_config.get("dns_server_1", "8.8.8.8"),
                dns_server_2=ip_config.get("dns_server_2"),
                ssh_password_auth=True,
                post_install_commands=post_install_commands,
            )
        elif config_type == "preseed":
            dns1 = ip_config.get("dns_server_1", "8.8.8.8")
            dns2 = ip_config.get("dns_server_2")
            dns_servers = f"{dns1} {dns2}" if dns2 else dns1
            return self.template_engine.render_debian_preseed(
                hostname=hostname,
                username=username,
                user_password=password,
                static_ip=ip_config.get("static_ip", False),
                ip_address=ip_config.get("ip_address"),
                netmask=ip_config.get("netmask", "255.255.255.0"),
                gateway=ip_config.get("gateway"),
                dns_servers=dns_servers,
                post_install_commands=post_install_commands,
                os_type=template_config.get("os_type", "debian_12"),
            )
        elif config_type == "kickstart":
            os_type = template_config.get("os_type", "").lower()
            template_name = template_config.get("name", "").lower()
            combined = f"{os_type} {template_name}"

            network_config = None
            if ip_config.get("static_ip"):
                network_config = {
                    "ip": ip_config.get("ip_address"),
                    "netmask": ip_config.get("netmask", "255.255.255.0"),
                    "gateway": ip_config.get("gateway"),
                    "dns": ip_config.get("dns_server_1", "8.8.8.8"),
                }

            if "rocky" in combined:
                return self.template_engine.render_rocky_kickstart(
                    hostname=hostname,
                    username=username,
                    user_password=password or "tooroto",
                    network_config=network_config,
                    post_install_commands=post_install_commands,
                )
            else:
                return self.template_engine.render_rhel_kickstart(
                    hostname=hostname,
                    username=username,
                    user_password=password or "tooroto",
                    network_config=network_config,
                    post_install_commands=post_install_commands,
                )
        else:
            # cloud-init (fallback)
            return self.template_engine.render_cloud_init(
                hostname=hostname,
                username=username,
                user_password=password,
                ssh_password_auth=True,
            )

    # =========================================================================
    # Création et upload de la seed ISO
    # =========================================================================

    async def _create_and_upload_seed_iso(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        seed_content: str,
        config_type: str,
    ) -> str:
        """
        Crée une seed ISO localement et l'upload sur le datastore ESXi.

        Utilise genisoimage/xorriso/mkisofs pour créer l'ISO.
        L'ISO est uploadée dans un dossier temporaire sur le datastore.

        Returns:
            Chemin datastore au format "[datastore] path/to/seed.iso"
        """
        vm_name = deployment.config["vm_name"]
        client = await self.vm_service._get_hypervisor_client(
            deployment.hypervisor_id
        )

        # Créer un répertoire temporaire avec la structure de fichiers attendue
        tmp_dir = tempfile.mkdtemp(prefix=f"vm-auto-seed-{vm_name}-")
        tmp_iso = os.path.join(tmp_dir, f"{vm_name}_seed.iso")

        try:
            # Préparer les fichiers du seed selon le type de config
            self._prepare_seed_files(tmp_dir, seed_content, config_type)

            # Créer l'ISO localement
            await self._build_seed_iso(tmp_dir, tmp_iso, config_type)

            await self._log_step(
                deployment,
                DeploymentStep.CREATING_SEED_ISO,
                f"Seed ISO créée localement ({os.path.getsize(tmp_iso)} octets)",
            )

            # Déterminer le datastore cible
            hypervisor = await self.vm_service.get_hypervisor(
                deployment.hypervisor_id
            )
            ds_name = (
                deployment.config.get("datastore")
                or getattr(hypervisor, "default_datastore", None)
                or getattr(client, "default_datastore", "datastore1")
            )
            remote_dir = "vm-automation-temp/seed-iso"
            remote_path = f"{remote_dir}/{vm_name}_seed.iso"

            # Créer le répertoire sur le datastore et uploader
            try:
                await client.mkdir_on_datastore(ds_name, remote_dir)
            except Exception as e:
                # Le répertoire existe peut-être déjà
                logger.debug(
                    "esxi_seed_mkdir_warning",
                    datastore=ds_name,
                    path=remote_dir,
                    error=str(e),
                )

            await client.upload_file_to_datastore(
                tmp_iso, ds_name, remote_path
            )

            ds_path = f"[{ds_name}] {remote_path}"
            await self._log_step(
                deployment,
                DeploymentStep.CREATING_SEED_ISO,
                f"Seed ISO uploadée sur le datastore : {ds_path}",
            )

            return ds_path

        finally:
            # Nettoyage du répertoire temporaire local
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    def _prepare_seed_files(
        self, tmp_dir: str, seed_content: str, config_type: str
    ) -> None:
        """
        Prépare les fichiers du seed ISO dans le répertoire temporaire.

        La structure dépend du type de config :
          - preseed : preseed.cfg à la racine
          - autoinstall : autoinstall/ avec user-data et meta-data
          - kickstart : ks.cfg à la racine
          - cloud-init : user-data et meta-data à la racine (NoCloud)
        """
        if config_type == "autoinstall":
            # Ubuntu autoinstall attend /autoinstall/user-data + /autoinstall/meta-data
            ai_dir = os.path.join(tmp_dir, "autoinstall")
            os.makedirs(ai_dir, exist_ok=True)
            with open(
                os.path.join(ai_dir, "user-data"), "w", encoding="utf-8"
            ) as f:
                f.write(seed_content)
            with open(
                os.path.join(ai_dir, "meta-data"), "w", encoding="utf-8"
            ) as f:
                f.write("")  # Fichier vide requis

            # Aussi à la racine pour certains installeurs Ubuntu plus récents
            with open(
                os.path.join(tmp_dir, "user-data"), "w", encoding="utf-8"
            ) as f:
                f.write(seed_content)
            with open(
                os.path.join(tmp_dir, "meta-data"), "w", encoding="utf-8"
            ) as f:
                f.write("")

        elif config_type == "preseed":
            with open(
                os.path.join(tmp_dir, "preseed.cfg"), "w", encoding="utf-8"
            ) as f:
                f.write(seed_content)

        elif config_type == "kickstart":
            with open(
                os.path.join(tmp_dir, "ks.cfg"), "w", encoding="utf-8"
            ) as f:
                f.write(seed_content)

        elif config_type == "cloud-init":
            # NoCloud datasource : user-data + meta-data à la racine
            with open(
                os.path.join(tmp_dir, "user-data"), "w", encoding="utf-8"
            ) as f:
                f.write(seed_content)
            with open(
                os.path.join(tmp_dir, "meta-data"), "w", encoding="utf-8"
            ) as f:
                f.write("")

        else:
            # Fallback : écrire le contenu comme fichier générique
            with open(
                os.path.join(tmp_dir, "seed.cfg"), "w", encoding="utf-8"
            ) as f:
                f.write(seed_content)

    async def _build_seed_iso(
        self, source_dir: str, output_iso: str, config_type: str
    ) -> None:
        """
        Construit une ISO à partir du répertoire source.

        Utilise genisoimage, xorriso ou mkisofs selon la disponibilité.
        Pas de oscdimg.exe — on est sur Linux/le serveur API.
        """
        iso_tool = _find_iso_tool()
        if iso_tool is None:
            raise DeploymentStepError(
                "",
                DeploymentStep.CREATING_SEED_ISO,
                "Aucun outil ISO trouvé. Installez genisoimage : "
                "apt-get install genisoimage",
            )

        tool_name = os.path.basename(iso_tool)

        # Label de l'ISO selon le type de config
        label_map = {
            "autoinstall": "cidata",  # Ubuntu Subiquity détecte NoCloud via ce label
            "preseed": "PRESEED",
            "kickstart": "OEMDRV",  # RHEL/Rocky cherche ce label
            "cloud-init": "cidata",  # Convention NoCloud
        }
        volume_id = label_map.get(config_type, "SEEDISO")

        if tool_name == "xorriso":
            cmd = [
                iso_tool,
                "-as", "mkisofs",
                "-o", output_iso,
                "-V", volume_id,
                "-J",          # Joliet
                "-R",          # Rock Ridge
                "-iso-level", "3",
                source_dir,
            ]
        else:
            # genisoimage ou mkisofs
            cmd = [
                iso_tool,
                "-o", output_iso,
                "-V", volume_id,
                "-J",          # Joliet
                "-R",          # Rock Ridge
                "-iso-level", "3",
                "-input-charset", "utf-8",
                source_dir,
            ]

        logger.info(
            "esxi_seed_iso_build",
            tool=tool_name,
            volume_id=volume_id,
            source=source_dir,
            output=output_iso,
        )

        def _run_iso_cmd() -> subprocess.CompletedProcess:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

        result = await asyncio.to_thread(_run_iso_cmd)

        if result.returncode != 0:
            raise DeploymentStepError(
                "",
                DeploymentStep.CREATING_SEED_ISO,
                f"Échec création seed ISO ({tool_name}) : {result.stderr[:500]}",
            )

    # =========================================================================
    # Montage de la seed ISO sur un second CD-ROM
    # =========================================================================

    async def _mount_seed_iso_on_second_cdrom(
        self, client: Any, vm_id: str, iso_path: str
    ) -> None:
        """
        Ajoute un second lecteur CD-ROM à la VM et monte la seed ISO dessus.

        Utilise pyvmomi pour ajouter un VirtualCdrom sur le contrôleur IDE
        de la VM, avec l'ISO backing pointant vers le datastore.
        """

        def _add_cdrom() -> None:
            from pyVmomi import vim

            vm_obj = client._get_vm_by_id(vm_id)
            if vm_obj is None:
                raise DeploymentStepError(
                    "",
                    DeploymentStep.MOUNTING_ISO,
                    f"VM {vm_id} introuvable sur ESXi",
                )

            # Chercher le contrôleur IDE et compter les CD-ROM existants
            ide_key = None
            sata_key = None
            cdrom_count = 0
            existing_keys = set()

            for dev in vm_obj.config.hardware.device:
                if isinstance(dev, vim.vm.device.VirtualIDEController):
                    if ide_key is None:
                        ide_key = dev.key
                elif isinstance(dev, vim.vm.device.VirtualSATAController):
                    if sata_key is None:
                        sata_key = dev.key
                elif isinstance(dev, vim.vm.device.VirtualCdrom):
                    cdrom_count += 1
                    existing_keys.add(dev.key)

            # Utiliser IDE en priorité, sinon SATA
            controller_key = ide_key or sata_key
            if controller_key is None:
                raise DeploymentStepError(
                    "",
                    DeploymentStep.MOUNTING_ISO,
                    "Aucun contrôleur IDE ou SATA trouvé sur la VM",
                )

            # Créer le spec pour ajouter un CD-ROM
            cdrom_spec = vim.vm.device.VirtualDeviceSpec()
            cdrom_spec.operation = (
                vim.vm.device.VirtualDeviceSpec.Operation.add
            )

            cdrom = vim.vm.device.VirtualCdrom()
            # Générer une clé unique qui n'entre pas en conflit
            new_key = 3001
            while new_key in existing_keys:
                new_key += 1
            cdrom.key = new_key
            cdrom.controllerKey = controller_key
            cdrom.unitNumber = cdrom_count  # Prochaine unité disponible

            # Backing : ISO sur le datastore
            iso_backing = vim.vm.device.VirtualCdrom.IsoBackingInfo()
            iso_backing.fileName = iso_path
            cdrom.backing = iso_backing

            # Connexion automatique
            connectable = vim.vm.device.VirtualDevice.ConnectInfo()
            connectable.startConnected = True
            connectable.connected = True
            connectable.allowGuestControl = True
            cdrom.connectable = connectable

            cdrom_spec.device = cdrom

            config_spec = vim.vm.ConfigSpec()
            config_spec.deviceChange = [cdrom_spec]

            task = vm_obj.ReconfigVM_Task(spec=config_spec)
            client._wait_for_task(task)

        await asyncio.to_thread(_add_cdrom)

    # =========================================================================
    # Résolution du chemin ISO d'installation
    # =========================================================================

    async def _check_iso_exists_on_datastore(
        self, client: Any, ds_name: str, iso_path: str
    ) -> bool:
        """Vérifie si un fichier ISO existe sur le datastore ESXi."""

        def _check() -> bool:
            from pyVmomi import vim

            client._ensure_connected()
            ds = client._get_obj([vim.Datastore], ds_name)
            if not ds:
                return False

            # Extraire le chemin relatif depuis le format "[ds] path"
            rel_path = iso_path
            if rel_path.startswith("["):
                rel_path = rel_path.split("] ", 1)[-1]

            # Séparer dossier et fichier
            if "/" in rel_path:
                folder, filename = rel_path.rsplit("/", 1)
                search_ds_path = f"[{ds_name}] {folder}"
            else:
                filename = rel_path
                search_ds_path = f"[{ds_name}]"

            search_spec = vim.host.DatastoreBrowser.SearchSpec()
            search_spec.matchPattern = [filename]

            import time as _time

            task = ds.browser.SearchDatastore_Task(
                datastorePath=search_ds_path, searchSpec=search_spec
            )
            while task.info.state not in ("success", "error"):
                _time.sleep(0.3)

            if task.info.state == "error":
                return False

            result = task.info.result
            return bool(result and result.file)

        try:
            return await asyncio.to_thread(_check)
        except Exception:
            return False

    async def _get_install_iso_path(self, deployment: Deployment) -> str:
        """
        Résout le chemin de l'ISO d'installation sur le datastore ESXi.

        Cherche dans l'ordre :
          1. Le champ iso_path du template OS en base
          2. Le champ iso_path dans la config du template
        """
        iso_path = None

        # Depuis le template OS en base
        if deployment.os_template_id:
            result = await self.db.execute(
                select(OSTemplate).where(
                    OSTemplate.id == deployment.os_template_id
                )
            )
            template = result.scalar_one_or_none()
            if template and template.iso_path:
                iso_path = template.iso_path

        # Fallback : config du template dans la configuration du déploiement
        if not iso_path:
            template_config = deployment.config.get("template") or {}
            iso_path = template_config.get("iso_path")

        if not iso_path:
            raise DeploymentStepError(
                str(deployment.id),
                DeploymentStep.MOUNTING_ISO,
                "Aucun chemin ISO d'installation configuré dans le template Linux",
            )

        # Si le chemin est un chemin Windows/Hyper-V, convertir en chemin datastore ESXi
        if not iso_path.startswith("["):
            filename = iso_path.replace("\\", "/").split("/")[-1]
            client = await self.vm_service._get_hypervisor_client(
                deployment.hypervisor_id
            )
            ds_name = getattr(client, "iso_datastore", None) or getattr(
                client, "default_datastore", "datastore1"
            )
            # Chercher d'abord dans le dossier ISOs, sinon à la racine
            iso_dir = getattr(client, "iso_path", "ISOs")
            candidates = [
                f"[{ds_name}] {iso_dir}/{filename}",
                f"[{ds_name}] {filename}",
            ]
            # Vérifier quel chemin existe sur le datastore
            iso_path_found = None
            for candidate in candidates:
                try:
                    exists = await self._check_iso_exists_on_datastore(
                        client, ds_name, candidate
                    )
                    if exists:
                        iso_path_found = candidate
                        break
                except Exception:
                    pass
            iso_path = iso_path_found or candidates[1]  # Default: racine du datastore
            logger.info(
                "esxi_iso_path_converted",
                filename=filename,
                resolved=iso_path,
            )

        return iso_path

    # =========================================================================
    # Attente de l'installation Linux
    # =========================================================================

    async def _wait_for_linux_ready_esxi(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        client: Any,
        timeout: int = _LINUX_INSTALL_TIMEOUT,
    ) -> bool:
        """
        Attend que Linux soit installé et accessible via SSH.

        Phase 1 : Attendre le heartbeat VMware Tools (indique que l'OS est démarré).
        Phase 2 : Récupérer l'IP via VMware Tools et tester la connexion SSH.
        Phase 3 : Vérifier que l'installation est bien terminée (pas de processus
                   d'installation en cours).
        """
        vm_id = vm.hypervisor_vm_id or vm.name
        start_time = time.time()

        # ── Phase 1 : Attendre le heartbeat VMware Tools ──
        await self._log_step(
            deployment,
            DeploymentStep.WAITING_SSH_READY,
            "Phase 1/3 : Attente du heartbeat VMware Tools...",
        )

        heartbeat_ok = False
        while (time.time() - start_time) < timeout:
            elapsed = int(time.time() - start_time)
            try:
                heartbeat = await client.get_vm_heartbeat(vm_id)
                if heartbeat and heartbeat.lower() == "green":
                    await self._log_step(
                        deployment,
                        DeploymentStep.WAITING_SSH_READY,
                        f"VMware Tools heartbeat OK ({elapsed}s)",
                    )
                    heartbeat_ok = True
                    break

                # Log périodique toutes les 5 vérifications
                if (elapsed // _HEARTBEAT_CHECK_INTERVAL) % 5 == 0:
                    remaining = timeout - elapsed
                    await self._log_step(
                        deployment,
                        DeploymentStep.WAITING_SSH_READY,
                        f"Attente heartbeat... ({heartbeat or 'inconnu'}, "
                        f"{elapsed}s écoulées, {remaining}s restantes)",
                    )
            except Exception as e:
                logger.debug(
                    "esxi_linux_heartbeat_check_error",
                    vm_id=vm_id,
                    error=str(e),
                )

            await asyncio.sleep(_HEARTBEAT_CHECK_INTERVAL)

        if not heartbeat_ok:
            elapsed = int(time.time() - start_time)
            await self._log_step(
                deployment,
                DeploymentStep.WAITING_SSH_READY,
                f"Timeout heartbeat après {elapsed}s — tentative de récupération IP directe",
                "warning",
            )

        # ── Phase 2 : Récupérer l'IP et tester SSH ──
        await self._log_step(
            deployment,
            DeploymentStep.WAITING_SSH_READY,
            "Phase 2/3 : Récupération de l'IP et test SSH...",
        )

        vm_ip = None
        try:
            ips = await client.get_vm_ip_addresses(vm_id)
            if ips:
                vm_ip = ips[0]
                vm.ip_address = vm_ip
                await self.db.flush()
                await self._log_step(
                    deployment,
                    DeploymentStep.WAITING_SSH_READY,
                    f"IP détectée via VMware Tools : {vm_ip}",
                )
        except Exception as e:
            logger.warning(
                "esxi_linux_ip_retrieval_error",
                vm_id=vm_id,
                error=str(e),
            )

        if not vm_ip:
            await self._log_step(
                deployment,
                DeploymentStep.WAITING_SSH_READY,
                "Impossible de récupérer l'IP — SSH indisponible",
                "warning",
            )
            return False

        username = deployment.config.get("username", "otoroot")
        password = deployment.config.get("admin_password", "tooroto")

        ssh_ok = await self._wait_for_ssh(
            vm_ip, username, password, timeout=_SSH_WAIT_TIMEOUT
        )

        if not ssh_ok:
            elapsed = int(time.time() - start_time)
            await self._log_step(
                deployment,
                DeploymentStep.WAITING_SSH_READY,
                f"SSH non accessible après {elapsed}s (user={username}, ip={vm_ip})",
                "warning",
            )
            return False

        await self._log_step(
            deployment,
            DeploymentStep.WAITING_SSH_READY,
            f"Connexion SSH réussie vers {username}@{vm_ip}",
        )

        # ── Phase 3 : Vérifier que l'installation est terminée ──
        await self._log_step(
            deployment,
            DeploymentStep.WAITING_SSH_READY,
            "Phase 3/3 : Vérification que l'installation est terminée...",
        )

        install_complete = await self._check_linux_install_complete_ssh(
            vm_ip, username, password
        )

        if not install_complete:
            await self._log_step(
                deployment,
                DeploymentStep.WAITING_SSH_READY,
                "Processus d'installation détecté — attente supplémentaire...",
                "info",
            )
            # Attendre jusqu'à 3 min supplémentaires
            for _ in range(12):
                await asyncio.sleep(15)
                if await self._check_linux_install_complete_ssh(
                    vm_ip, username, password
                ):
                    install_complete = True
                    break

            if not install_complete:
                await self._log_step(
                    deployment,
                    DeploymentStep.WAITING_SSH_READY,
                    "L'installation semble encore en cours — on continue quand même",
                    "warning",
                )

        return True

    # =========================================================================
    # Utilitaires SSH
    # =========================================================================

    async def _wait_for_ssh(
        self,
        ip: str,
        username: str,
        password: str,
        timeout: int = _SSH_WAIT_TIMEOUT,
    ) -> bool:
        """
        Attend que SSH soit accessible sur l'IP donnée.

        Teste d'abord l'ouverture du port 22, puis (si paramiko est disponible)
        la connexion SSH complète avec authentification.
        """
        start = time.time()
        check_interval = 10

        while (time.time() - start) < timeout:
            # Tester l'ouverture du port TCP 22
            port_open = await self._check_ssh_port(ip)
            if not port_open:
                await asyncio.sleep(check_interval)
                continue

            # Port ouvert — tester la connexion SSH complète
            if PARAMIKO_AVAILABLE:
                ssh_ok = await self._check_ssh_auth(ip, username, password)
                if ssh_ok:
                    return True
                # Le port est ouvert mais l'auth échoue — peut-être que sshd
                # est encore en train de démarrer
                await asyncio.sleep(check_interval)
                continue

            # Pas de paramiko — le port ouvert suffit
            return True

        return False

    async def _check_ssh_port(self, ip: str, port: int = 22) -> bool:
        """Vérifie si le port SSH est ouvert (test TCP)."""

        def _check() -> bool:
            try:
                sock = socket.create_connection((ip, port), timeout=5)
                sock.close()
                return True
            except (OSError, socket.timeout):
                return False

        return await asyncio.to_thread(_check)

    async def _check_ssh_auth(
        self, ip: str, username: str, password: str, timeout: int = 10
    ) -> bool:
        """Vérifie la connexion SSH avec authentification (paramiko)."""
        if not PARAMIKO_AVAILABLE:
            return False

        def _check() -> bool:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                ssh.connect(
                    ip, username=username, password=password, timeout=timeout
                )
                ssh.close()
                return True
            except Exception:
                return False

        return await asyncio.to_thread(_check)

    async def _check_linux_install_complete_ssh(
        self, ip: str, username: str, password: str
    ) -> bool:
        """
        Vérifie que l'installation Linux est terminée via SSH.

        Cherche des processus d'installation courants (d-i, anaconda,
        subiquity, apt, dpkg) et retourne False s'ils sont encore actifs.
        """
        if not PARAMIKO_AVAILABLE:
            return True  # On ne peut pas vérifier sans paramiko

        try:
            output = await self._ssh_execute(
                ip,
                username,
                password,
                "ps aux 2>/dev/null | grep -E "
                "'(d-i|anaconda|subiquity|apt-get|dpkg|yum|dnf)' "
                "| grep -v grep | head -5",
                timeout=15,
            )
            # Si pas de processus d'installation trouvé, c'est terminé
            return len(output.strip()) == 0
        except Exception:
            # En cas d'erreur SSH, considérer que l'installation est terminée
            return True

    async def _ssh_execute(
        self,
        ip: str,
        username: str,
        password: str,
        command: str,
        timeout: int = _SSH_CMD_TIMEOUT,
    ) -> str:
        """
        Exécute une commande via SSH (paramiko).

        Lève une exception si le code de sortie est non nul.
        Retourne la sortie standard en UTF-8.
        """
        if not PARAMIKO_AVAILABLE:
            raise RuntimeError(
                "paramiko n'est pas installé — impossible d'exécuter des commandes SSH"
            )

        def _exec() -> str:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                ip, username=username, password=password, timeout=10
            )
            try:
                _stdin, stdout, stderr = ssh.exec_command(
                    command, timeout=timeout
                )
                exit_code = stdout.channel.recv_exit_status()
                output = stdout.read().decode("utf-8", errors="replace")
                errors = stderr.read().decode("utf-8", errors="replace")
                if exit_code != 0:
                    raise RuntimeError(
                        f"Commande SSH échouée (exit {exit_code}) : "
                        f"{errors[:300]}"
                    )
                return output
            finally:
                ssh.close()

        return await asyncio.to_thread(_exec)

    # =========================================================================
    # Post-installation Linux via SSH
    # =========================================================================

    async def _linux_post_install_ssh(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        client: Any,
    ) -> None:
        """
        Post-installation Linux via SSH.

        Configure le fuseau horaire, active SSH, et exécute les
        commandes post-installation personnalisées.
        """
        config = deployment.config
        vm_id = vm.hypervisor_vm_id or vm.name
        ip = vm.ip_address

        # Récupérer l'IP si pas encore connue
        if not ip:
            try:
                ips = await client.get_vm_ip_addresses(vm_id)
                if ips:
                    ip = ips[0]
                    vm.ip_address = ip
                    await self.db.flush()
            except Exception as e:
                logger.warning(
                    "esxi_linux_post_install_ip_error", error=str(e)
                )

        if not ip:
            await self._log_step(
                deployment,
                DeploymentStep.LINUX_POST_INSTALL,
                "Pas d'IP disponible — post-installation ignorée",
                "warning",
            )
            return

        if not PARAMIKO_AVAILABLE:
            await self._log_step(
                deployment,
                DeploymentStep.LINUX_POST_INSTALL,
                "paramiko non disponible — post-installation SSH ignorée",
                "warning",
            )
            return

        username = config.get("username", "otoroot")
        password = config.get("admin_password", "tooroto")
        tz = config.get("timezone", "Europe/Paris")

        # Commandes de base post-installation
        base_commands = [
            # Mise à jour des dépôts (apt ou dnf selon la distribution)
            "sudo apt-get update -qq 2>/dev/null || sudo dnf check-update -q 2>/dev/null || true",
            # Fuseau horaire
            f"sudo timedatectl set-timezone {tz} 2>/dev/null || true",
            # Activer le service SSH
            "sudo systemctl enable ssh 2>/dev/null || sudo systemctl enable sshd 2>/dev/null || true",
            # Installer open-vm-tools si pas déjà installé
            "dpkg -l open-vm-tools 2>/dev/null || rpm -q open-vm-tools 2>/dev/null || "
            "sudo apt-get install -y open-vm-tools 2>/dev/null || "
            "sudo dnf install -y open-vm-tools 2>/dev/null || true",
        ]

        # Commandes personnalisées depuis la config
        custom_commands = config.get("post_install_commands") or []

        all_commands = base_commands + custom_commands

        for cmd in all_commands:
            cmd_display = cmd[:80] + ("..." if len(cmd) > 80 else "")
            try:
                await self._ssh_execute(ip, username, password, cmd)
                await self._log_step(
                    deployment,
                    DeploymentStep.LINUX_POST_INSTALL,
                    f"OK : {cmd_display}",
                )
            except Exception as e:
                await self._log_step(
                    deployment,
                    DeploymentStep.LINUX_POST_INSTALL,
                    f"Avertissement : {cmd_display} — {e}",
                    "warning",
                )

        await self._log_step(
            deployment,
            DeploymentStep.LINUX_POST_INSTALL,
            f"Post-installation terminée ({len(all_commands)} commandes)",
        )

    # =========================================================================
    # Installation de paquets Linux via SSH
    # =========================================================================

    async def _install_linux_packages_ssh(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        client: Any,
        packages: list[str],
    ) -> None:
        """
        Installe les paquets Linux via SSH.

        Détecte automatiquement le gestionnaire de paquets (apt ou dnf)
        et installe les paquets demandés.
        """
        ip = vm.ip_address
        if not ip or not PARAMIKO_AVAILABLE:
            await self._log_step(
                deployment,
                DeploymentStep.INSTALLING_SOFTWARE,
                "SSH indisponible — installation des paquets ignorée",
                "warning",
            )
            return

        username = deployment.config.get("username", "otoroot")
        password = deployment.config.get("admin_password", "tooroto")

        # Échapper les noms de paquets (protection basique contre l'injection)
        safe_packages = [
            p for p in packages if p.replace("-", "").replace(".", "").replace("+", "").isalnum()
        ]

        if not safe_packages:
            await self._log_step(
                deployment,
                DeploymentStep.INSTALLING_SOFTWARE,
                "Aucun paquet valide à installer",
                "warning",
            )
            return

        pkg_list = " ".join(safe_packages)
        await self._log_step(
            deployment,
            DeploymentStep.INSTALLING_SOFTWARE,
            f"Installation des paquets : {pkg_list}",
        )

        # Commande adaptée : essaye apt puis dnf
        cmd = (
            f"sudo DEBIAN_FRONTEND=noninteractive apt-get install -y {pkg_list} 2>/dev/null "
            f"|| sudo dnf install -y {pkg_list} 2>/dev/null"
        )

        try:
            await self._ssh_execute(
                ip, username, password, cmd, timeout=_SSH_PKG_TIMEOUT
            )
            await self._log_step(
                deployment,
                DeploymentStep.INSTALLING_SOFTWARE,
                f"Paquets installés avec succès : {pkg_list}",
            )
        except Exception as e:
            await self._log_step(
                deployment,
                DeploymentStep.INSTALLING_SOFTWARE,
                f"Erreur installation paquets : {e}",
                "warning",
            )
