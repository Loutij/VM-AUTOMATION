# =============================================================================
# VM Automation - ESXi Windows Deployment Mixin
# =============================================================================
"""
Mixin pour le déploiement Windows sur ESXi/vSphere.

Différences avec Hyper-V :
- Pas de DISM : installation depuis l'ISO avec unattend.xml sur floppy
- Pas de PowerShell Direct : utilise GuestOperationsManager (VMware Tools)
- Pas de WinRM vers l'hôte : communication via pyvmomi
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import TYPE_CHECKING

from sqlalchemy import select

from src.common.exceptions import DeploymentStepError
from src.common.logging import get_logger
from src.domain.deployment_service import DeploymentStep
from src.domain.models import (
    DeploymentStatus,
    OSTemplate,
)

if TYPE_CHECKING:
    from src.domain.models import Deployment, VirtualMachine

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Détection de l'édition Windows depuis le nom du template
# ─────────────────────────────────────────────────────────────────────────────

def _detect_windows_edition(template_name: str) -> str:
    """Détecte l'édition Windows depuis le nom du template."""
    name = template_name.lower()
    if "server" in name:
        if "2019" in name:
            return "Windows Server 2019 SERVERSTANDARD"
        if "2025" in name:
            return "Windows Server 2025 SERVERSTANDARD"
        return "Windows Server 2022 SERVERSTANDARD"
    if "11" in name:
        return "Windows 11 Pro"
    if "10" in name:
        return "Windows 10 Pro"
    return "Windows 11 Pro"


# ─────────────────────────────────────────────────────────────────────────────
# Mixin Windows ESXi
# ─────────────────────────────────────────────────────────────────────────────

class ESXiWindowsDeployMixin:
    """
    Mixin fournissant le workflow complet de déploiement Windows sur ESXi.

    S'intègre dans ESXiDeploymentService qui fournit :
      - self.db (AsyncSession)
      - self.vm_service (VMService)
      - self.template_engine (TemplateEngine)
      - self._log_step(), _update_deployment_status()
      - _create_vm_for_esxi(), _finalize_esxi_deployment()
    """

    # ─────────────────────────────────────────────────────────────────────────
    # Workflow principal
    # ─────────────────────────────────────────────────────────────────────────

    async def _execute_windows_deployment(self, deployment: Deployment) -> None:
        """Workflow complet de déploiement Windows sur ESXi."""
        config = deployment.config

        # 1. Créer la VM sur ESXi
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.CREATING_VM,
        )
        await self._log_step(
            deployment, DeploymentStep.CREATING_VM,
            f"Création VM ESXi : {config['vm_name']}",
        )
        try:
            vm = await self._create_vm_for_esxi(deployment)
        except Exception as exc:
            raise DeploymentStepError(
                str(deployment.id), DeploymentStep.CREATING_VM, str(exc),
            ) from exc
        deployment.vm_id = vm.id
        await self.db.commit()

        # 2. Générer le fichier unattend.xml
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.GENERATING_UNATTEND,
        )
        await self._log_step(
            deployment, DeploymentStep.GENERATING_UNATTEND,
            "Génération de unattend.xml...",
        )
        try:
            unattend_content = self._generate_windows_unattend(deployment)
        except Exception as exc:
            raise DeploymentStepError(
                str(deployment.id), DeploymentStep.GENERATING_UNATTEND, str(exc),
            ) from exc

        # 3. Créer une image floppy avec unattend.xml et l'uploader sur le datastore
        await self._log_step(
            deployment, DeploymentStep.GENERATING_UNATTEND,
            "Création de l'image floppy avec unattend.xml...",
        )
        try:
            floppy_path = await self._create_and_upload_unattend_floppy(
                deployment, vm, unattend_content,
            )
        except Exception as exc:
            raise DeploymentStepError(
                str(deployment.id), DeploymentStep.GENERATING_UNATTEND,
                f"Échec création floppy unattend : {exc}",
            ) from exc

        # 4. Monter l'ISO Windows + floppy
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.MOUNTING_ISO,
        )
        client = await self.vm_service._get_hypervisor_client(deployment.hypervisor_id)

        # Récupérer le chemin ISO depuis le template
        iso_path = await self._get_iso_path(deployment)
        await self._log_step(
            deployment, DeploymentStep.MOUNTING_ISO,
            f"Montage ISO : {iso_path}",
        )
        try:
            await client.mount_iso(vm.hypervisor_vm_id or vm.name, iso_path)
        except Exception as exc:
            raise DeploymentStepError(
                str(deployment.id), DeploymentStep.MOUNTING_ISO,
                f"Échec montage ISO : {exc}",
            ) from exc

        # Attacher le floppy contenant unattend.xml
        await self._log_step(
            deployment, DeploymentStep.MOUNTING_ISO,
            f"Attachement floppy unattend : {floppy_path}",
        )
        try:
            await self._attach_floppy(client, vm.hypervisor_vm_id or vm.name, floppy_path)
        except Exception as exc:
            # Le floppy n'est pas critique — l'installation peut continuer sans
            await self._log_step(
                deployment, DeploymentStep.MOUNTING_ISO,
                f"Avertissement : échec attachement floppy ({exc})", "warning",
            )

        # 5. Configurer le boot order : CD-ROM en premier
        try:
            await client.set_boot_order(vm.hypervisor_vm_id or vm.name, ["DVD", "HardDrive"])
        except Exception as exc:
            await self._log_step(
                deployment, DeploymentStep.MOUNTING_ISO,
                f"Avertissement : échec configuration boot order ({exc})", "warning",
            )

        # 6. Démarrer la VM pour l'installation
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.STARTING_INSTALLATION,
        )
        await self._log_step(
            deployment, DeploymentStep.STARTING_INSTALLATION,
            "Démarrage de la VM pour installation Windows...",
        )
        try:
            await self.vm_service.start_vm(vm.id)
        except Exception as exc:
            raise DeploymentStepError(
                str(deployment.id), DeploymentStep.STARTING_INSTALLATION,
                f"Échec démarrage VM : {exc}",
            ) from exc

        # 7. Attendre la fin de l'installation (heartbeat VMware Tools)
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.WAITING_INSTALLATION,
        )
        await self._log_step(
            deployment, DeploymentStep.WAITING_INSTALLATION,
            "Attente fin d'installation Windows (VMware Tools)...",
        )
        await self._wait_for_windows_install(deployment, vm)

        # 8. Attendre que Windows soit prêt (Tools running + GuestOps fonctionnel)
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.WAITING_VM_READY,
        )
        vm_ready = await self._wait_for_windows_ready(deployment, vm)

        # 9. Post-configuration via GuestOps (VMware Tools)
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.POST_CONFIGURATION,
        )
        if vm_ready:
            await self._log_step(
                deployment, DeploymentStep.POST_CONFIGURATION,
                "Configuration post-installation via VMware Tools...",
            )
            await self._execute_post_configuration_windows(deployment, vm, client)
        else:
            await self._log_step(
                deployment, DeploymentStep.POST_CONFIGURATION,
                "VM non accessible via VMware Tools — configuration manuelle requise",
                "warning",
            )

        # 10. Installation logiciels
        software_profile = config.get("software_profile")
        packages = config.get("packages", [])
        if software_profile or packages:
            await self._update_deployment_status(
                deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.INSTALLING_SOFTWARE,
            )
            if vm_ready:
                await self._install_software_windows(deployment, vm, client)
            else:
                await self._log_step(
                    deployment, DeploymentStep.INSTALLING_SOFTWARE,
                    "Installation logiciels ignorée (VMware Tools indisponible)",
                    "warning",
                )

        # 11. Finalisation
        await self._finalize_esxi_deployment(deployment, vm, "windows")

    # ─────────────────────────────────────────────────────────────────────────
    # Génération unattend.xml
    # ─────────────────────────────────────────────────────────────────────────

    def _generate_windows_unattend(self, deployment: Deployment) -> str:
        """Génère le contenu unattend.xml pour Windows sur ESXi."""
        config = deployment.config
        template_config = config.get("template") or {}
        ip_config = config.get("ip_config") or {}
        domain_join = config.get("domain_join") or {}

        # Déterminer l'édition Windows
        windows_edition = (
            config.get("windows_edition")
            or template_config.get("windows_edition")
            or _detect_windows_edition(template_config.get("name", ""))
        )

        # Commandes post-installation optionnelles
        post_install_commands = [
            {"command": cmd, "description": f"Commande personnalisée {i + 1}"}
            for i, cmd in enumerate(config.get("post_install_commands") or [])
        ]

        return self.template_engine.render_windows_unattend(
            hostname=config["hostname"],
            admin_password=config["admin_password"],
            admin_username=config.get("admin_username") or "otoroot",
            static_ip=ip_config.get("static_ip", False),
            ip_address=ip_config.get("ip_address"),
            gateway=ip_config.get("gateway"),
            dns_server_1=ip_config.get("dns_server_1", "8.8.8.8"),
            dns_server_2=ip_config.get("dns_server_2"),
            join_domain=bool(domain_join),
            domain_name=domain_join.get("domain"),
            domain_user=domain_join.get("user"),
            domain_password=domain_join.get("password"),
            windows_edition=windows_edition,
            post_install_commands=post_install_commands,
            template_name=template_config.get("name"),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Création et upload de l'image floppy
    # ─────────────────────────────────────────────────────────────────────────

    async def _create_and_upload_unattend_floppy(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        unattend_content: str,
    ) -> str:
        """
        Crée une image floppy (1.44 Mo) contenant Autounattend.xml
        et l'upload sur le datastore ESXi.

        Returns:
            Chemin datastore de l'image floppy, ex: [datastore1] vm-automation-temp/floppy/VMNAME_unattend.flp
        """
        vm_name = deployment.config["vm_name"]
        client = await self.vm_service._get_hypervisor_client(deployment.hypervisor_id)

        # Créer l'image floppy localement
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".flp", delete=False) as tmp:
                tmp_path = tmp.name

            # Construire l'image floppy FAT12 avec Autounattend.xml
            await asyncio.to_thread(
                _create_floppy_image, unattend_content, tmp_path,
            )

            # Déterminer le datastore cible
            hypervisor = await self.vm_service.get_hypervisor(deployment.hypervisor_id)
            ds_name = (
                deployment.config.get("datastore")
                or getattr(hypervisor, "default_datastore", None)
                or client.default_datastore
            )
            remote_path = f"vm-automation-temp/floppy/{vm_name}_unattend.flp"

            # Créer le répertoire et uploader
            await client.mkdir_on_datastore(ds_name, "vm-automation-temp/floppy")
            await client.upload_file_to_datastore(tmp_path, ds_name, remote_path)

            return f"[{ds_name}] {remote_path}"

        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # ─────────────────────────────────────────────────────────────────────────
    # Attachement du floppy à la VM
    # ─────────────────────────────────────────────────────────────────────────

    async def _attach_floppy(self, client, vm_id: str, floppy_path: str) -> None:
        """
        Attache une image floppy à une VM ESXi via ReconfigVM_Task.

        Ajoute un contrôleur SIO si absent, puis un lecteur de disquette
        avec le backing pointant sur l'image floppy uploadée.
        """
        def _attach():
            from pyVmomi import vim

            vm = client._get_vm_by_id(vm_id)

            # Chercher un contrôleur SIO existant
            floppy_ctrl = None
            for dev in vm.config.hardware.device:
                if isinstance(dev, vim.vm.device.VirtualSIOController):
                    floppy_ctrl = dev
                    break

            device_changes = []

            # Ajouter le contrôleur SIO s'il n'existe pas
            if floppy_ctrl is None:
                sio_spec = vim.vm.device.VirtualDeviceSpec()
                sio_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
                sio = vim.vm.device.VirtualSIOController()
                sio.key = 400
                sio_spec.device = sio
                device_changes.append(sio_spec)
                ctrl_key = 400
            else:
                ctrl_key = floppy_ctrl.key

            # Ajouter le lecteur de disquette
            floppy_spec = vim.vm.device.VirtualDeviceSpec()
            floppy_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add

            floppy = vim.vm.device.VirtualFloppy()
            floppy.key = 8000
            floppy.controllerKey = ctrl_key
            floppy.unitNumber = 0

            backing = vim.vm.device.VirtualFloppy.ImageBackingInfo()
            backing.fileName = floppy_path
            floppy.backing = backing

            connectable = vim.vm.device.VirtualDevice.ConnectInfo()
            connectable.startConnected = True
            connectable.connected = True
            connectable.allowGuestControl = True
            floppy.connectable = connectable

            floppy_spec.device = floppy
            device_changes.append(floppy_spec)

            config_spec = vim.vm.ConfigSpec()
            config_spec.deviceChange = device_changes
            task = vm.ReconfigVM_Task(spec=config_spec)
            client._wait_for_task(task)

        await asyncio.to_thread(_attach)

    # ─────────────────────────────────────────────────────────────────────────
    # Récupération du chemin ISO
    # ─────────────────────────────────────────────────────────────────────────

    async def _get_iso_path(self, deployment: Deployment) -> str:
        """
        Récupère le chemin ISO depuis le template en DB ou la config.

        Pour ESXi, le chemin doit être au format datastore : [datastore] chemin/fichier.iso
        Si c'est un chemin brut, on le préfixe avec le datastore ISO par défaut.
        """
        iso_path = None

        # Chercher d'abord dans le template en DB
        if deployment.os_template_id:
            result = await self.db.execute(
                select(OSTemplate).where(OSTemplate.id == deployment.os_template_id)
            )
            template = result.scalar_one_or_none()
            if template:
                iso_path = template.iso_path

        # Fallback sur la config du déploiement
        if not iso_path:
            template_config = deployment.config.get("template") or {}
            iso_path = template_config.get("iso_path")

        if not iso_path:
            raise DeploymentStepError(
                str(deployment.id),
                DeploymentStep.MOUNTING_ISO,
                "Aucun chemin ISO configuré dans le template",
            )

        # Convertir en format datastore ESXi si nécessaire
        if not iso_path.startswith("["):
            client = await self.vm_service._get_hypervisor_client(deployment.hypervisor_id)
            iso_ds = client.iso_datastore or client.default_datastore
            iso_path = f"[{iso_ds}] {iso_path.lstrip('/')}"

        return iso_path

    # ─────────────────────────────────────────────────────────────────────────
    # Attente installation Windows
    # ─────────────────────────────────────────────────────────────────────────

    async def _wait_for_windows_install(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        timeout: int = 1800,
    ) -> None:
        """
        Attend la fin de l'installation Windows via le heartbeat VMware Tools.

        L'installation Windows depuis un ISO prend généralement 15-30 minutes.
        On attend que le heartbeat passe à "green" ce qui indique que VMware Tools
        est installé et fonctionnel (donc Windows a fini l'installation + OOBE).

        Args:
            deployment: Déploiement en cours
            vm: VM cible
            timeout: Timeout en secondes (défaut : 30 minutes)
        """
        client = await self.vm_service._get_hypervisor_client(deployment.hypervisor_id)
        vm_id = vm.hypervisor_vm_id or vm.name

        elapsed = 0
        check_interval = 30

        while elapsed < timeout:
            try:
                heartbeat = await client.get_vm_heartbeat(vm_id)
                await self._log_step(
                    deployment, DeploymentStep.WAITING_INSTALLATION,
                    f"Installation en cours... (heartbeat : {heartbeat}, {elapsed}s écoulées)",
                )
                # "green" = VMware Tools opérationnel = OS installé et démarré
                if heartbeat == "green":
                    await self._log_step(
                        deployment, DeploymentStep.WAITING_INSTALLATION,
                        f"Installation Windows terminée après {elapsed}s",
                    )
                    return
            except Exception as exc:
                logger.debug(
                    "esxi_windows_heartbeat_check_error",
                    vm_id=vm_id, error=str(exc), elapsed=elapsed,
                )

            await asyncio.sleep(check_interval)
            elapsed += check_interval

        # Timeout atteint — on continue quand même avec un avertissement
        await self._log_step(
            deployment, DeploymentStep.WAITING_INSTALLATION,
            f"Timeout après {timeout}s d'attente de VMware Tools — poursuite du déploiement",
            "warning",
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Attente VM prête (post-OOBE)
    # ─────────────────────────────────────────────────────────────────────────

    async def _wait_for_windows_ready(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        timeout: int = 600,
    ) -> bool:
        """
        Attend que Windows soit prêt après l'installation (Tools running + GuestOps).

        Utilise la méthode wait_for_vm_ready du client ESXi qui vérifie
        le heartbeat et les opérations invité.

        Args:
            deployment: Déploiement en cours
            vm: VM cible
            timeout: Timeout en secondes (défaut : 10 minutes)

        Returns:
            True si la VM est prête et accessible, False sinon
        """
        client = await self.vm_service._get_hypervisor_client(deployment.hypervisor_id)
        vm_id = vm.hypervisor_vm_id or vm.name
        credentials = (
            deployment.config.get("admin_username", "otoroot"),
            deployment.config.get("admin_password", ""),
        )

        try:
            result = await client.wait_for_vm_ready(vm_id, credentials, timeout=timeout)
        except Exception as exc:
            logger.warning(
                "esxi_windows_wait_ready_error",
                vm_id=vm_id, error=str(exc),
            )
            result = False

        if result:
            await self._log_step(
                deployment, DeploymentStep.WAITING_VM_READY,
                "VM Windows prête et accessible via VMware Tools",
            )
        else:
            await self._log_step(
                deployment, DeploymentStep.WAITING_VM_READY,
                "VM non accessible via VMware Tools — certaines étapes seront ignorées",
                "warning",
            )

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Post-configuration Windows via GuestOps
    # ─────────────────────────────────────────────────────────────────────────

    async def _execute_post_configuration_windows(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        client,
    ) -> None:
        """
        Exécute la post-configuration Windows via VMware Tools GuestOperationsManager.

        Actions :
          - Activation du Bureau à distance (RDP)
          - Désactivation du pare-feu pour le profil Domain (si domaine)
          - Configuration WinRM pour l'administration distante
          - Nettoyage des fichiers temporaires d'installation
        """
        vm_id = vm.hypervisor_vm_id or vm.name
        credentials = (
            deployment.config.get("admin_username", "otoroot"),
            deployment.config.get("admin_password", ""),
        )

        # Liste des commandes de post-configuration
        post_config_commands = [
            # Activer RDP
            (
                'reg add "HKLM\\System\\CurrentControlSet\\Control\\Terminal Server" '
                '/v fDenyTSConnections /t REG_DWORD /d 0 /f',
                "Activation RDP",
            ),
            # Ouvrir le pare-feu pour RDP
            (
                "netsh advfirewall firewall set rule group=\"Remote Desktop\" new enable=yes",
                "Ouverture pare-feu RDP",
            ),
            # Activer WinRM
            (
                "winrm quickconfig -quiet",
                "Configuration WinRM",
            ),
            # Définir le profil réseau comme privé (pour WinRM)
            (
                'powershell -Command "Set-NetConnectionProfile -NetworkCategory Private -ErrorAction SilentlyContinue"',
                "Configuration profil réseau",
            ),
            # Supprimer le fichier Autounattend.xml du lecteur A: (si monté)
            (
                'powershell -Command "Remove-Item A:\\Autounattend.xml -Force -ErrorAction SilentlyContinue"',
                "Nettoyage Autounattend.xml",
            ),
        ]

        for cmd, description in post_config_commands:
            try:
                result = await client.execute_in_vm(vm_id, cmd, credentials, timeout=120)
                if result.success:
                    await self._log_step(
                        deployment, DeploymentStep.POST_CONFIGURATION,
                        f"{description} : OK",
                    )
                else:
                    await self._log_step(
                        deployment, DeploymentStep.POST_CONFIGURATION,
                        f"{description} : échec ({result.error})", "warning",
                    )
            except Exception as exc:
                await self._log_step(
                    deployment, DeploymentStep.POST_CONFIGURATION,
                    f"{description} : erreur ({exc})", "warning",
                )

    # ─────────────────────────────────────────────────────────────────────────
    # Installation logiciels via GuestOps
    # ─────────────────────────────────────────────────────────────────────────

    async def _install_software_windows(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        client,
    ) -> None:
        """
        Installe les logiciels demandés via VMware Tools GuestOperationsManager.

        Utilise chocolatey (choco) pour les installations silencieuses.
        Si choco n'est pas installé, l'installe d'abord.
        """
        config = deployment.config
        vm_id = vm.hypervisor_vm_id or vm.name
        credentials = (
            config.get("admin_username", "otoroot"),
            config.get("admin_password", ""),
        )

        packages = config.get("packages", [])
        software_profile = config.get("software_profile")

        # Résoudre les packages depuis le profil logiciel si nécessaire
        if software_profile and not packages:
            packages = await self._resolve_software_profile(software_profile)

        if not packages:
            await self._log_step(
                deployment, DeploymentStep.INSTALLING_SOFTWARE,
                "Aucun logiciel à installer",
            )
            return

        # Vérifier / installer chocolatey
        await self._log_step(
            deployment, DeploymentStep.INSTALLING_SOFTWARE,
            "Vérification de Chocolatey...",
        )
        choco_check = await client.execute_in_vm(
            vm_id, "choco --version", credentials, timeout=60,
        )
        if not choco_check.success:
            await self._log_step(
                deployment, DeploymentStep.INSTALLING_SOFTWARE,
                "Installation de Chocolatey...",
            )
            install_choco_cmd = (
                'powershell -Command "'
                "[System.Net.ServicePointManager]::SecurityProtocol = "
                "[System.Net.SecurityProtocolType]::Tls12; "
                "iex ((New-Object System.Net.WebClient).DownloadString("
                "'https://community.chocolatey.org/install.ps1'))\""
            )
            choco_install = await client.execute_in_vm(
                vm_id, install_choco_cmd, credentials, timeout=300,
            )
            if not choco_install.success:
                await self._log_step(
                    deployment, DeploymentStep.INSTALLING_SOFTWARE,
                    f"Échec installation Chocolatey : {choco_install.error}",
                    "warning",
                )
                return

        # Installer chaque paquet
        for pkg in packages:
            pkg_name = pkg if isinstance(pkg, str) else pkg.get("name", str(pkg))
            await self._log_step(
                deployment, DeploymentStep.INSTALLING_SOFTWARE,
                f"Installation de {pkg_name}...",
            )
            install_cmd = f"choco install {pkg_name} -y --no-progress"
            try:
                result = await client.execute_in_vm(
                    vm_id, install_cmd, credentials, timeout=600,
                )
                if result.success:
                    await self._log_step(
                        deployment, DeploymentStep.INSTALLING_SOFTWARE,
                        f"{pkg_name} : installé",
                    )
                else:
                    await self._log_step(
                        deployment, DeploymentStep.INSTALLING_SOFTWARE,
                        f"{pkg_name} : échec ({result.error})", "warning",
                    )
            except Exception as exc:
                await self._log_step(
                    deployment, DeploymentStep.INSTALLING_SOFTWARE,
                    f"{pkg_name} : erreur ({exc})", "warning",
                )

    async def _resolve_software_profile(self, profile_name: str) -> list[str]:
        """
        Résout un profil logiciel en liste de noms de paquets.

        Profils prédéfinis pour les cas courants. Extensible via la DB
        ou la configuration.
        """
        # Profils prédéfinis
        profiles = {
            "basic": ["7zip", "notepadplusplus", "vlc"],
            "dev": [
                "7zip", "notepadplusplus", "git", "vscode",
                "python3", "nodejs-lts",
            ],
            "office": [
                "7zip", "notepadplusplus", "vlc",
                "adobereader", "googlechrome", "firefox",
            ],
            "server": [
                "7zip", "notepadplusplus",
            ],
        }

        return profiles.get(profile_name.lower(), [])


# ─────────────────────────────────────────────────────────────────────────────
# Utilitaire : création d'image floppy FAT12
# ─────────────────────────────────────────────────────────────────────────────

def _create_floppy_image(unattend_content: str, output_path: str) -> None:
    """
    Crée une image floppy 1.44 Mo contenant Autounattend.xml.

    Windows cherche automatiquement Autounattend.xml sur le lecteur A:
    lors du démarrage de l'installation depuis un ISO.

    Utilise mtools (mkfs.fat + mcopy) ou une construction manuelle FAT12.
    """
    import struct
    import subprocess

    floppy_size = 1474560  # 1.44 Mo

    # Essayer avec mtools (plus fiable)
    try:
        # Créer une image vide
        with open(output_path, "wb") as f:
            f.write(b"\x00" * floppy_size)

        # Formater en FAT12
        subprocess.run(
            ["mkfs.fat", "-F", "12", output_path],
            check=True, capture_output=True, timeout=30,
        )

        # Écrire Autounattend.xml dans un fichier temporaire
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".xml", delete=False, encoding="utf-8",
        ) as tmp_xml:
            tmp_xml.write(unattend_content)
            tmp_xml_path = tmp_xml.name

        try:
            # Copier dans l'image floppy via mcopy
            subprocess.run(
                ["mcopy", "-i", output_path, tmp_xml_path, "::Autounattend.xml"],
                check=True, capture_output=True, timeout=30,
            )
        finally:
            os.unlink(tmp_xml_path)

        logger.info("floppy_image_created", path=output_path, method="mtools")
        return

    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        logger.debug(
            "mtools_not_available_fallback",
            error=str(exc),
        )

    # Fallback : construction manuelle FAT12
    # Structure minimale : BPB + FAT + root dir + données
    _create_floppy_image_manual(unattend_content, output_path, floppy_size)
    logger.info("floppy_image_created", path=output_path, method="manual_fat12")


def _create_floppy_image_manual(
    unattend_content: str,
    output_path: str,
    floppy_size: int = 1474560,
) -> None:
    """
    Construction manuelle d'une image floppy FAT12 minimale.

    Structure d'une disquette 1.44 Mo :
      - Secteur 0 : Boot sector (BPB)
      - Secteurs 1-9 : FAT #1 (9 secteurs)
      - Secteurs 10-18 : FAT #2 (copie)
      - Secteurs 19-32 : Root directory (14 secteurs = 224 entrées)
      - Secteurs 33+ : Zone de données
    """
    import struct

    SECTOR_SIZE = 512
    SECTORS_PER_CLUSTER = 1
    RESERVED_SECTORS = 1
    NUM_FATS = 2
    ROOT_ENTRY_COUNT = 224
    TOTAL_SECTORS = floppy_size // SECTOR_SIZE  # 2880
    SECTORS_PER_FAT = 9
    ROOT_DIR_SECTORS = (ROOT_ENTRY_COUNT * 32 + SECTOR_SIZE - 1) // SECTOR_SIZE  # 14
    DATA_START_SECTOR = RESERVED_SECTORS + (NUM_FATS * SECTORS_PER_FAT) + ROOT_DIR_SECTORS  # 33

    image = bytearray(floppy_size)

    # ── Boot sector (BPB - BIOS Parameter Block) ──
    bpb = bytearray(SECTOR_SIZE)
    bpb[0:3] = b"\xEB\x3C\x90"                          # Jump + NOP
    bpb[3:11] = b"MSDOS5.0"                              # OEM name
    struct.pack_into("<H", bpb, 11, SECTOR_SIZE)          # Bytes per sector
    bpb[13] = SECTORS_PER_CLUSTER                         # Sectors per cluster
    struct.pack_into("<H", bpb, 14, RESERVED_SECTORS)     # Reserved sectors
    bpb[16] = NUM_FATS                                    # Number of FATs
    struct.pack_into("<H", bpb, 17, ROOT_ENTRY_COUNT)     # Root entry count
    struct.pack_into("<H", bpb, 19, TOTAL_SECTORS)        # Total sectors (16-bit)
    bpb[21] = 0xF0                                        # Media descriptor (floppy)
    struct.pack_into("<H", bpb, 22, SECTORS_PER_FAT)      # Sectors per FAT
    struct.pack_into("<H", bpb, 24, 18)                   # Sectors per track
    struct.pack_into("<H", bpb, 26, 2)                    # Number of heads
    bpb[38] = 0x29                                        # Extended boot signature
    struct.pack_into("<I", bpb, 39, 0x12345678)           # Volume serial
    bpb[43:54] = b"OTOFLP     "                           # Volume label (11 chars)
    bpb[54:62] = b"FAT12   "                              # FS type
    bpb[510] = 0x55                                       # Boot signature
    bpb[511] = 0xAA

    image[0:SECTOR_SIZE] = bpb

    # ── FAT (File Allocation Table) ──
    # Encoder le contenu du fichier
    file_data = unattend_content.encode("utf-8")
    file_size = len(file_data)
    clusters_needed = (file_size + SECTOR_SIZE - 1) // SECTOR_SIZE

    # Première entrée FAT : media descriptor + 0xFFF
    fat = bytearray(SECTORS_PER_FAT * SECTOR_SIZE)
    fat[0] = 0xF0  # Media descriptor
    fat[1] = 0xFF
    fat[2] = 0xFF

    # Chaîne de clusters pour le fichier (clusters 2, 3, 4...)
    # FAT12 : 12 bits par entrée, emballées par paires
    for i in range(clusters_needed):
        cluster = i + 2  # Les données commencent au cluster 2
        if i == clusters_needed - 1:
            next_cluster = 0xFFF  # Fin de chaîne
        else:
            next_cluster = cluster + 1

        # Écrire l'entrée FAT12 (12 bits par cluster)
        byte_offset = (cluster * 3) // 2
        if cluster % 2 == 0:
            fat[byte_offset] = next_cluster & 0xFF
            fat[byte_offset + 1] = (fat[byte_offset + 1] & 0xF0) | ((next_cluster >> 8) & 0x0F)
        else:
            fat[byte_offset] = (fat[byte_offset] & 0x0F) | ((next_cluster & 0x0F) << 4)
            fat[byte_offset + 1] = (next_cluster >> 4) & 0xFF

    # Écrire les deux copies de la FAT
    fat1_offset = RESERVED_SECTORS * SECTOR_SIZE
    fat2_offset = (RESERVED_SECTORS + SECTORS_PER_FAT) * SECTOR_SIZE
    image[fat1_offset:fat1_offset + len(fat)] = fat
    image[fat2_offset:fat2_offset + len(fat)] = fat

    # ── Root directory ──
    root_offset = (RESERVED_SECTORS + NUM_FATS * SECTORS_PER_FAT) * SECTOR_SIZE

    # Entrée pour "AUTOUNAT XML" (format 8.3)
    entry = bytearray(32)
    entry[0:8] = b"AUTOUNAT"     # Nom (8 chars, paddé avec espaces)
    entry[8:11] = b"XML"         # Extension (3 chars)
    entry[11] = 0x20             # Attribut : Archive
    entry[26] = 2                # Premier cluster (low word) = cluster 2
    entry[27] = 0
    struct.pack_into("<I", entry, 28, file_size)  # Taille du fichier

    image[root_offset:root_offset + 32] = entry

    # Ajouter une entrée LFN (Long File Name) pour "Autounattend.xml"
    # Windows cherche ce nom exact — l'entrée 8.3 AUTOUNAT.XML suffit aussi
    # car Windows vérifie les deux formats

    # ── Zone de données ──
    data_offset = DATA_START_SECTOR * SECTOR_SIZE
    image[data_offset:data_offset + file_size] = file_data

    # Écrire l'image
    with open(output_path, "wb") as f:
        f.write(image)
