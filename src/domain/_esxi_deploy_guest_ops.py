"""
Mixin pour les opérations invité et post-configuration sur ESXi.

Sur ESXi, les opérations invité utilisent VMware GuestOperationsManager
(via pyvmomi) pour Windows et Linux. Pour Linux, SSH via paramiko est
préféré car plus fiable que GuestOps.

Ce fichier temporaire sera fusionné dans deployment_service.py.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from src.domain.deployment_service import DeploymentStep

if TYPE_CHECKING:
    from src.domain.models import Deployment, VirtualMachine

logger = logging.getLogger(__name__)

# Vérifier la disponibilité de paramiko pour les connexions SSH (Linux VMs)
try:
    import paramiko

    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False


class ESXiGuestOpsMixin:
    """
    Mixin fournissant les opérations invité (guest ops) et la
    post-configuration pour les déploiements ESXi.

    Méthodes attendues sur self (fournies par DeploymentService) :
        - _log_step(deployment, step, message, level="info")
        - vm_service._get_hypervisor_client(hypervisor_id)
        - db  (session SQLAlchemy async)
    """

    # ------------------------------------------------------------------
    # Exécution générique dans la VM via GuestOperationsManager
    # ------------------------------------------------------------------

    async def _execute_in_guest_esxi(
        self,
        client: Any,
        vm_id: str,
        script: str,
        credentials: tuple[str, str],
        os_family: str = "windows",
        timeout: int = 120,
    ) -> dict:
        """
        Exécute un script dans la VM via GuestOperationsManager (pyvmomi).

        Args:
            client: Client ESXi (ESXiClient)
            vm_id: Identifiant de la VM sur l'hyperviseur
            script: Contenu du script à exécuter
            credentials: Tuple (username, password) pour l'invité
            os_family: "windows" ou "linux"
            timeout: Timeout en secondes

        Returns:
            Dict avec clés success, output, error
        """
        try:
            result = await client.execute_in_vm(
                vm_id, script, credentials, timeout=timeout
            )
            return {
                "success": result.success,
                "output": result.output or "",
                "error": result.error or "",
            }
        except Exception as e:
            logger.warning(
                "esxi_guest_ops_execute_error",
                vm_id=vm_id,
                error=str(e),
            )
            return {
                "success": False,
                "output": "",
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # Exécution SSH pour Linux (plus fiable que GuestOps)
    # ------------------------------------------------------------------

    async def _ssh_execute_esxi(
        self,
        ip: str,
        username: str,
        password: str,
        command: str,
        timeout: int = 30,
    ) -> str:
        """
        Exécute une commande via SSH (paramiko) sur une VM Linux ESXi.

        Raises:
            RuntimeError: Si paramiko n'est pas disponible ou connexion échoue
        """
        if not PARAMIKO_AVAILABLE:
            raise RuntimeError(
                "paramiko n'est pas installé — impossible d'utiliser SSH"
            )

        def _exec() -> str:
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                ssh_client.connect(
                    hostname=ip,
                    username=username,
                    password=password,
                    timeout=10,
                    allow_agent=False,
                    look_for_keys=False,
                )
                _stdin, stdout, stderr = ssh_client.exec_command(
                    command, timeout=timeout
                )
                output = stdout.read().decode("utf-8", errors="replace").strip()
                err = stderr.read().decode("utf-8", errors="replace").strip()
                exit_code = stdout.channel.recv_exit_status()
                if exit_code != 0 and err:
                    logger.debug(
                        "esxi_ssh_command_stderr",
                        ip=ip,
                        command=command[:80],
                        stderr=err[:200],
                        exit_code=exit_code,
                    )
                return output
            finally:
                ssh_client.close()

        try:
            loop = asyncio.get_event_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, _exec),
                timeout=timeout + 15,
            )
        except asyncio.TimeoutError:
            raise RuntimeError(f"SSH timeout après {timeout}s vers {ip}")
        except paramiko.AuthenticationException:
            raise RuntimeError(f"Échec authentification SSH vers {ip}")
        except Exception as e:
            raise RuntimeError(f"Erreur SSH vers {ip}: {e}")

    # ------------------------------------------------------------------
    # Point d'entrée post-configuration ESXi
    # ------------------------------------------------------------------

    async def _execute_post_configuration_esxi(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
    ) -> None:
        """
        Post-configuration sur ESXi via GuestOps (Windows) ou SSH (Linux).

        Détecte l'OS famille et dispatch vers la méthode appropriée.
        """
        config = deployment.config or {}
        template_config = config.get("template") or {}
        os_family = str(template_config.get("os_family", "windows")).lower()

        client = await self.vm_service._get_hypervisor_client(
            deployment.hypervisor_id
        )
        vm_id = vm.hypervisor_vm_id or vm.name
        credentials = (
            config.get("admin_username", "otoroot"),
            config.get("admin_password", ""),
        )
        services_config = config.get("services", {})

        await self._log_step(
            deployment,
            DeploymentStep.POST_CONFIGURATION,
            f"Début post-configuration ESXi (OS: {os_family})",
        )

        if os_family == "windows":
            await self._post_config_windows_esxi(
                deployment, client, vm_id, credentials, services_config
            )
        else:
            await self._post_config_linux_esxi(
                deployment, vm, client, credentials, services_config
            )

        await self._log_step(
            deployment,
            DeploymentStep.POST_CONFIGURATION,
            "Post-configuration ESXi terminée",
        )

    # ------------------------------------------------------------------
    # Post-configuration Windows via VMware GuestOperationsManager
    # ------------------------------------------------------------------

    async def _post_config_windows_esxi(
        self,
        deployment: Deployment,
        client: Any,
        vm_id: str,
        credentials: tuple[str, str],
        services_config: dict,
    ) -> None:
        """Post-configuration Windows via VMware GuestOperationsManager."""

        # 1. Activer RDP
        if services_config.get("enable_rdp", True):
            await self._log_step(
                deployment,
                DeploymentStep.POST_CONFIGURATION,
                "Activation RDP...",
            )
            rdp_script = (
                'Set-ItemProperty -Path '
                '"HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server" '
                '-Name "fDenyTSConnections" -Value 0 -ErrorAction SilentlyContinue; '
                'Set-ItemProperty -Path '
                '"HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server'
                '\\WinStations\\RDP-Tcp" '
                '-Name "UserAuthentication" -Value 0 -ErrorAction SilentlyContinue; '
                'Enable-NetFirewallRule -DisplayGroup "Remote Desktop" '
                '-ErrorAction SilentlyContinue; '
                'Enable-NetFirewallRule -DisplayGroup "Bureau à distance" '
                '-ErrorAction SilentlyContinue'
            )
            result = await self._execute_in_guest_esxi(
                client, vm_id, rdp_script, credentials
            )
            status = "OK" if result["success"] else f"Erreur: {result['error']}"
            await self._log_step(
                deployment,
                DeploymentStep.POST_CONFIGURATION,
                f"RDP: {status}",
            )

        # 2. Configurer WinRM
        if services_config.get("enable_winrm", True):
            await self._log_step(
                deployment,
                DeploymentStep.POST_CONFIGURATION,
                "Configuration WinRM...",
            )
            winrm_script = (
                'Enable-PSRemoting -Force -SkipNetworkProfileCheck '
                '-ErrorAction SilentlyContinue; '
                'Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value "*" '
                '-Force -ErrorAction SilentlyContinue; '
                'Set-Service -Name WinRM -StartupType Automatic '
                '-ErrorAction SilentlyContinue'
            )
            result = await self._execute_in_guest_esxi(
                client, vm_id, winrm_script, credentials
            )
            status = "OK" if result["success"] else f"Erreur: {result['error']}"
            await self._log_step(
                deployment,
                DeploymentStep.POST_CONFIGURATION,
                f"WinRM: {status}",
            )

        # 3. Installer OpenSSH Server si demandé
        if services_config.get("enable_ssh", False):
            await self._log_step(
                deployment,
                DeploymentStep.POST_CONFIGURATION,
                "Installation OpenSSH Server...",
            )
            ssh_script = (
                'Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 '
                '-ErrorAction SilentlyContinue; '
                'Start-Service sshd -ErrorAction SilentlyContinue; '
                'Set-Service -Name sshd -StartupType Automatic '
                '-ErrorAction SilentlyContinue; '
                'New-NetFirewallRule -Name "OpenSSH-Server" -DisplayName "OpenSSH Server" '
                '-Direction Inbound -Protocol TCP -LocalPort 22 -Action Allow '
                '-ErrorAction SilentlyContinue'
            )
            result = await self._execute_in_guest_esxi(
                client, vm_id, ssh_script, credentials, timeout=180
            )
            status = "OK" if result["success"] else f"Erreur: {result['error']}"
            await self._log_step(
                deployment,
                DeploymentStep.POST_CONFIGURATION,
                f"SSH: {status}",
            )

        # 4. Profil réseau Private (requis pour WinRM/RDP)
        network_script = (
            'Get-NetConnectionProfile | Set-NetConnectionProfile '
            '-NetworkCategory Private -ErrorAction SilentlyContinue'
        )
        await self._execute_in_guest_esxi(
            client, vm_id, network_script, credentials
        )
        await self._log_step(
            deployment,
            DeploymentStep.POST_CONFIGURATION,
            "Profil réseau configuré (Private)",
        )

        # 5. Désactiver le pare-feu sur le profil Domain si nécessaire
        if services_config.get("disable_domain_firewall", False):
            fw_script = (
                'Set-NetFirewallProfile -Profile Domain '
                '-Enabled False -ErrorAction SilentlyContinue'
            )
            await self._execute_in_guest_esxi(
                client, vm_id, fw_script, credentials
            )
            await self._log_step(
                deployment,
                DeploymentStep.POST_CONFIGURATION,
                "Pare-feu profil Domain désactivé",
            )

    # ------------------------------------------------------------------
    # Post-configuration Linux via SSH (préféré) ou GuestOps (fallback)
    # ------------------------------------------------------------------

    async def _post_config_linux_esxi(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        client: Any,
        credentials: tuple[str, str],
        services_config: dict,
    ) -> None:
        """
        Post-configuration Linux via SSH ou GuestOps.

        SSH est préféré car plus fiable et supporte mieux les commandes
        longues. GuestOps est utilisé en fallback si SSH n'est pas disponible.
        """
        username, password = credentials
        vm_id = vm.hypervisor_vm_id or vm.name

        # Récupérer l'IP de la VM si pas encore connue
        ip = vm.ip_address
        if not ip:
            try:
                ips = await client.get_vm_ip_addresses(vm_id)
                if ips:
                    ip = ips[0]
                    vm.ip_address = ip
                    await self.db.flush()
                    logger.info(
                        "esxi_linux_vm_ip_resolved",
                        vm_id=vm_id,
                        ip=ip,
                    )
            except Exception as e:
                logger.warning(
                    "esxi_linux_vm_ip_resolve_failed",
                    vm_id=vm_id,
                    error=str(e),
                )

        # Choisir la méthode : SSH si IP + paramiko disponibles
        use_ssh = bool(ip and PARAMIKO_AVAILABLE)

        if use_ssh:
            await self._post_config_linux_via_ssh(
                deployment, ip, username, password, services_config, vm_id
            )
        else:
            await self._post_config_linux_via_guestops(
                deployment, client, vm_id, credentials, services_config
            )

    async def _post_config_linux_via_ssh(
        self,
        deployment: Deployment,
        ip: str,
        username: str,
        password: str,
        services_config: dict,
        vm_id: str,
    ) -> None:
        """Post-configuration Linux via SSH (méthode préférée)."""
        await self._log_step(
            deployment,
            DeploymentStep.POST_CONFIGURATION,
            f"Post-configuration Linux via SSH ({ip})",
        )

        # 1. Activer et démarrer SSH (sshd)
        if services_config.get("enable_ssh", True):
            await self._log_step(
                deployment,
                DeploymentStep.POST_CONFIGURATION,
                "Configuration SSH...",
            )
            try:
                await self._ssh_execute_esxi(
                    ip,
                    username,
                    password,
                    "sudo systemctl enable --now ssh 2>/dev/null || "
                    "sudo systemctl enable --now sshd 2>/dev/null; "
                    "echo SSH_CONFIGURED",
                )
                await self._log_step(
                    deployment,
                    DeploymentStep.POST_CONFIGURATION,
                    "SSH configuré et activé",
                )
            except Exception as e:
                await self._log_step(
                    deployment,
                    DeploymentStep.POST_CONFIGURATION,
                    f"Configuration SSH: {e}",
                    "warning",
                )

        # 2. Configurer le hostname si spécifié
        hostname = (deployment.config or {}).get("hostname")
        if hostname:
            try:
                await self._ssh_execute_esxi(
                    ip,
                    username,
                    password,
                    f"sudo hostnamectl set-hostname {hostname}",
                )
                await self._log_step(
                    deployment,
                    DeploymentStep.POST_CONFIGURATION,
                    f"Hostname configuré: {hostname}",
                )
            except Exception as e:
                await self._log_step(
                    deployment,
                    DeploymentStep.POST_CONFIGURATION,
                    f"Configuration hostname: {e}",
                    "warning",
                )

        # 3. Configurer le timezone si spécifié
        timezone = (deployment.config or {}).get("timezone")
        if timezone:
            try:
                await self._ssh_execute_esxi(
                    ip,
                    username,
                    password,
                    f"sudo timedatectl set-timezone {timezone}",
                )
            except Exception:
                pass  # Non critique

        # 4. Mettre à jour les paquets si demandé
        if services_config.get("auto_update", False):
            await self._log_step(
                deployment,
                DeploymentStep.POST_CONFIGURATION,
                "Mise à jour des paquets...",
            )
            try:
                # Détecter le gestionnaire de paquets
                await self._ssh_execute_esxi(
                    ip,
                    username,
                    password,
                    "sudo apt-get update -qq && sudo apt-get upgrade -y -qq 2>/dev/null || "
                    "sudo dnf update -y -q 2>/dev/null || "
                    "sudo yum update -y -q 2>/dev/null",
                    timeout=300,
                )
                await self._log_step(
                    deployment,
                    DeploymentStep.POST_CONFIGURATION,
                    "Paquets mis à jour",
                )
            except Exception as e:
                await self._log_step(
                    deployment,
                    DeploymentStep.POST_CONFIGURATION,
                    f"Mise à jour paquets: {e}",
                    "warning",
                )

        # 5. Configurer le pare-feu si demandé
        if services_config.get("configure_firewall", False):
            try:
                # UFW (Debian/Ubuntu) ou firewalld (RHEL/Rocky)
                await self._ssh_execute_esxi(
                    ip,
                    username,
                    password,
                    "sudo ufw allow ssh 2>/dev/null && sudo ufw --force enable 2>/dev/null || "
                    "sudo firewall-cmd --permanent --add-service=ssh 2>/dev/null && "
                    "sudo firewall-cmd --reload 2>/dev/null",
                )
                await self._log_step(
                    deployment,
                    DeploymentStep.POST_CONFIGURATION,
                    "Pare-feu configuré (SSH autorisé)",
                )
            except Exception:
                pass  # Non critique

    async def _post_config_linux_via_guestops(
        self,
        deployment: Deployment,
        client: Any,
        vm_id: str,
        credentials: tuple[str, str],
        services_config: dict,
    ) -> None:
        """
        Post-configuration Linux via GuestOperationsManager (fallback).

        Utilisé quand SSH n'est pas disponible (pas d'IP ou pas de paramiko).
        Fonctionnalités réduites par rapport à SSH.
        """
        await self._log_step(
            deployment,
            DeploymentStep.POST_CONFIGURATION,
            "Post-configuration Linux via GuestOps (fallback — SSH non disponible)",
            "warning",
        )

        # Activer SSH
        if services_config.get("enable_ssh", True):
            result = await self._execute_in_guest_esxi(
                client,
                vm_id,
                "systemctl enable --now ssh 2>/dev/null || systemctl enable --now sshd 2>/dev/null",
                credentials,
                os_family="linux",
            )
            status = "OK" if result["success"] else f"Erreur: {result['error']}"
            await self._log_step(
                deployment,
                DeploymentStep.POST_CONFIGURATION,
                f"SSH (GuestOps): {status}",
            )

        # Configurer le hostname
        hostname = (deployment.config or {}).get("hostname")
        if hostname:
            await self._execute_in_guest_esxi(
                client,
                vm_id,
                f"hostnamectl set-hostname {hostname}",
                credentials,
                os_family="linux",
            )

        await self._log_step(
            deployment,
            DeploymentStep.POST_CONFIGURATION,
            "Post-configuration GuestOps terminée (fonctionnalités limitées)",
        )

    # ------------------------------------------------------------------
    # Installation de logiciels sur ESXi
    # ------------------------------------------------------------------

    async def _install_software_esxi(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
    ) -> None:
        """
        Installe les logiciels demandés via GuestOps ou SSH.

        Pour Windows : winget puis choco en fallback.
        Pour Linux : apt/dnf/yum via SSH (délégué au mixin Linux si dispo).
        """
        config = deployment.config or {}
        template_config = config.get("template") or {}
        os_family = str(template_config.get("os_family", "windows")).lower()
        packages = config.get("packages", [])

        if not packages:
            return

        client = await self.vm_service._get_hypervisor_client(
            deployment.hypervisor_id
        )
        vm_id = vm.hypervisor_vm_id or vm.name
        credentials = (
            config.get("admin_username", "otoroot"),
            config.get("admin_password", ""),
        )

        await self._log_step(
            deployment,
            DeploymentStep.INSTALLING_SOFTWARE,
            f"Installation logiciels ({len(packages)} paquets, OS: {os_family})",
        )

        if os_family == "windows":
            await self._install_windows_software_esxi(
                deployment, client, vm_id, credentials, packages
            )
        else:
            await self._install_linux_software_esxi(
                deployment, vm, client, credentials, packages
            )

    async def _install_windows_software_esxi(
        self,
        deployment: Deployment,
        client: Any,
        vm_id: str,
        credentials: tuple[str, str],
        packages: list[str],
    ) -> None:
        """Installe des logiciels Windows via GuestOps (winget/choco)."""
        pkg_list = ", ".join(packages)
        await self._log_step(
            deployment,
            DeploymentStep.INSTALLING_SOFTWARE,
            f"Installation Windows: {pkg_list}",
        )

        # Construire la liste PowerShell des paquets
        ps_array = ", ".join(f'"{p}"' for p in packages)

        # Essayer winget puis chocolatey en fallback
        install_script = f"""
$ErrorActionPreference = 'Continue'
$installed = @()
$failed = @()
foreach ($pkg in @({ps_array})) {{
    $done = $false
    # Essayer winget
    try {{
        $out = winget install --id $pkg --accept-package-agreements --accept-source-agreements -h 2>&1
        if ($LASTEXITCODE -eq 0) {{
            $installed += $pkg
            $done = $true
        }}
    }} catch {{}}
    # Fallback chocolatey
    if (-not $done) {{
        try {{
            $out = choco install $pkg -y --no-progress 2>&1
            if ($LASTEXITCODE -eq 0) {{
                $installed += $pkg
                $done = $true
            }}
        }} catch {{}}
    }}
    if (-not $done) {{ $failed += $pkg }}
}}
"INSTALLED: $($installed -join ', ')"
if ($failed.Count -gt 0) {{ "FAILED: $($failed -join ', ')" }}
"""
        result = await self._execute_in_guest_esxi(
            client, vm_id, install_script, credentials, timeout=600
        )
        if result["success"]:
            await self._log_step(
                deployment,
                DeploymentStep.INSTALLING_SOFTWARE,
                f"Résultat: {result['output'][:500]}",
            )
        else:
            await self._log_step(
                deployment,
                DeploymentStep.INSTALLING_SOFTWARE,
                f"Erreur installation: {result['error'][:300]}",
                "warning",
            )

    async def _install_linux_software_esxi(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        client: Any,
        credentials: tuple[str, str],
        packages: list[str],
    ) -> None:
        """Installe des paquets Linux via SSH ou GuestOps."""
        username, password = credentials
        vm_id = vm.hypervisor_vm_id or vm.name
        ip = vm.ip_address
        pkg_list = " ".join(packages)

        await self._log_step(
            deployment,
            DeploymentStep.INSTALLING_SOFTWARE,
            f"Installation Linux: {pkg_list}",
        )

        # Commande d'installation multi-distro
        install_cmd = (
            f"sudo apt-get update -qq && sudo apt-get install -y -qq {pkg_list} 2>/dev/null || "
            f"sudo dnf install -y -q {pkg_list} 2>/dev/null || "
            f"sudo yum install -y -q {pkg_list} 2>/dev/null"
        )

        if ip and PARAMIKO_AVAILABLE:
            # Via SSH (préféré)
            try:
                output = await self._ssh_execute_esxi(
                    ip, username, password, install_cmd, timeout=300
                )
                await self._log_step(
                    deployment,
                    DeploymentStep.INSTALLING_SOFTWARE,
                    f"Paquets installés via SSH: {pkg_list}",
                )
            except Exception as e:
                await self._log_step(
                    deployment,
                    DeploymentStep.INSTALLING_SOFTWARE,
                    f"Erreur installation via SSH: {e}",
                    "warning",
                )
        else:
            # Via GuestOps (fallback)
            result = await self._execute_in_guest_esxi(
                client,
                vm_id,
                install_cmd,
                credentials,
                os_family="linux",
                timeout=300,
            )
            if result["success"]:
                await self._log_step(
                    deployment,
                    DeploymentStep.INSTALLING_SOFTWARE,
                    f"Paquets installés via GuestOps: {pkg_list}",
                )
            else:
                await self._log_step(
                    deployment,
                    DeploymentStep.INSTALLING_SOFTWARE,
                    f"Erreur installation via GuestOps: {result['error'][:300]}",
                    "warning",
                )

    # ------------------------------------------------------------------
    # Attente que VMware Tools soit prêt dans la VM
    # ------------------------------------------------------------------

    async def _wait_vmware_tools_ready(
        self,
        client: Any,
        vm_id: str,
        timeout: int = 300,
        poll_interval: int = 10,
    ) -> bool:
        """
        Attend que VMware Tools soit opérationnel dans la VM.

        Nécessaire avant de pouvoir utiliser GuestOperationsManager.

        Returns:
            True si VMware Tools est prêt, False si timeout
        """
        import time

        start = time.monotonic()
        while time.monotonic() - start < timeout:
            try:
                tools_status = await client.get_vmware_tools_status(vm_id)
                if tools_status in ("toolsOk", "toolsOld"):
                    logger.info(
                        "esxi_vmware_tools_ready",
                        vm_id=vm_id,
                        status=tools_status,
                        elapsed=int(time.monotonic() - start),
                    )
                    return True
            except Exception:
                pass  # VM peut ne pas encore être accessible

            await asyncio.sleep(poll_interval)

        logger.warning(
            "esxi_vmware_tools_timeout",
            vm_id=vm_id,
            timeout=timeout,
        )
        return False

    # ------------------------------------------------------------------
    # Attente de l'IP de la VM via VMware Tools
    # ------------------------------------------------------------------

    async def _wait_vm_ip_esxi(
        self,
        client: Any,
        vm_id: str,
        timeout: int = 300,
        poll_interval: int = 10,
    ) -> str | None:
        """
        Attend que la VM obtienne une adresse IP (via VMware Tools).

        Returns:
            Adresse IP ou None si timeout
        """
        import time

        start = time.monotonic()
        while time.monotonic() - start < timeout:
            try:
                ips = await client.get_vm_ip_addresses(vm_id)
                if ips:
                    # Filtrer les adresses link-local (169.254.x.x, fe80::)
                    valid_ips = [
                        ip
                        for ip in ips
                        if not ip.startswith("169.254.")
                        and not ip.startswith("fe80:")
                    ]
                    if valid_ips:
                        logger.info(
                            "esxi_vm_ip_obtained",
                            vm_id=vm_id,
                            ip=valid_ips[0],
                            elapsed=int(time.monotonic() - start),
                        )
                        return valid_ips[0]
            except Exception:
                pass

            await asyncio.sleep(poll_interval)

        logger.warning(
            "esxi_vm_ip_timeout",
            vm_id=vm_id,
            timeout=timeout,
        )
        return None
