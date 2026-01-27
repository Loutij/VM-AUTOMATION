# =============================================================================
# VM Automation - Software Installation Service
# =============================================================================
"""
Service pour l'installation automatique de logiciels sur les VMs.
Utilise Chocolatey pour Windows et apt/yum pour Linux.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.common.logging import get_logger
from src.integrations.hypervisors.hyperv_client import HyperVClient

logger = get_logger(__name__)


class PackageManager(str, Enum):
    """Gestionnaires de paquets supportés."""
    CHOCOLATEY = "chocolatey"
    WINGET = "winget"
    APT = "apt"
    YUM = "yum"
    DNF = "dnf"


class InstallationStatus(str, Enum):
    """Statuts d'installation."""
    PENDING = "pending"
    INSTALLING = "installing"
    INSTALLED = "installed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SoftwarePackage:
    """Définition d'un package logiciel."""
    name: str
    version: str | None = None
    package_manager: PackageManager = PackageManager.CHOCOLATEY
    install_args: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "package_manager": self.package_manager.value,
            "install_args": self.install_args,
        }


@dataclass
class InstallationResult:
    """Résultat d'une installation de package."""
    package_name: str
    status: InstallationStatus
    version_installed: str | None = None
    error: str | None = None
    duration_seconds: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "package_name": self.package_name,
            "status": self.status.value,
            "version_installed": self.version_installed,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class BatchInstallResult:
    """Résultat d'une installation de plusieurs packages."""
    total: int
    installed: int
    failed: int
    skipped: int
    results: list[InstallationResult] = field(default_factory=list)
    reboot_required: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "installed": self.installed,
            "failed": self.failed,
            "skipped": self.skipped,
            "results": [r.to_dict() for r in self.results],
            "reboot_required": self.reboot_required,
        }


# Profils de logiciels prédéfinis - Windows
SOFTWARE_PROFILES = {
    "webserver": [
        SoftwarePackage("iis-webserver", package_manager=PackageManager.CHOCOLATEY),
        SoftwarePackage("urlrewrite", package_manager=PackageManager.CHOCOLATEY),
    ],
    "development": [
        SoftwarePackage("git", package_manager=PackageManager.CHOCOLATEY),
        SoftwarePackage("vscode", package_manager=PackageManager.CHOCOLATEY),
        SoftwarePackage("nodejs-lts", package_manager=PackageManager.CHOCOLATEY),
        SoftwarePackage("python", package_manager=PackageManager.CHOCOLATEY),
    ],
    "tools": [
        SoftwarePackage("7zip", package_manager=PackageManager.CHOCOLATEY),
        SoftwarePackage("notepadplusplus", package_manager=PackageManager.CHOCOLATEY),
        SoftwarePackage("sysinternals", package_manager=PackageManager.CHOCOLATEY),
    ],
    "monitoring": [
        SoftwarePackage("zabbix-agent", package_manager=PackageManager.CHOCOLATEY),
    ],
    "database": [
        SoftwarePackage("sql-server-express", package_manager=PackageManager.CHOCOLATEY),
        SoftwarePackage("sql-server-management-studio", package_manager=PackageManager.CHOCOLATEY),
    ],
    "minimal": [
        SoftwarePackage("7zip", package_manager=PackageManager.CHOCOLATEY),
        SoftwarePackage("notepadplusplus", package_manager=PackageManager.CHOCOLATEY),
    ],
}

# Profils de logiciels Linux - APT (Debian/Ubuntu)
LINUX_APT_PROFILES = {
    "webserver": [
        SoftwarePackage("nginx", package_manager=PackageManager.APT),
        SoftwarePackage("apache2", package_manager=PackageManager.APT),
        SoftwarePackage("php-fpm", package_manager=PackageManager.APT),
        SoftwarePackage("certbot", package_manager=PackageManager.APT),
    ],
    "development": [
        SoftwarePackage("git", package_manager=PackageManager.APT),
        SoftwarePackage("build-essential", package_manager=PackageManager.APT),
        SoftwarePackage("python3-pip", package_manager=PackageManager.APT),
        SoftwarePackage("nodejs", package_manager=PackageManager.APT),
        SoftwarePackage("npm", package_manager=PackageManager.APT),
    ],
    "tools": [
        SoftwarePackage("vim", package_manager=PackageManager.APT),
        SoftwarePackage("htop", package_manager=PackageManager.APT),
        SoftwarePackage("tmux", package_manager=PackageManager.APT),
        SoftwarePackage("curl", package_manager=PackageManager.APT),
        SoftwarePackage("wget", package_manager=PackageManager.APT),
        SoftwarePackage("net-tools", package_manager=PackageManager.APT),
    ],
    "monitoring": [
        SoftwarePackage("zabbix-agent", package_manager=PackageManager.APT),
        SoftwarePackage("prometheus-node-exporter", package_manager=PackageManager.APT),
    ],
    "database": [
        SoftwarePackage("postgresql", package_manager=PackageManager.APT),
        SoftwarePackage("postgresql-contrib", package_manager=PackageManager.APT),
        SoftwarePackage("mariadb-server", package_manager=PackageManager.APT),
    ],
    "docker": [
        SoftwarePackage("docker.io", package_manager=PackageManager.APT),
        SoftwarePackage("docker-compose", package_manager=PackageManager.APT),
    ],
    "minimal": [
        SoftwarePackage("vim", package_manager=PackageManager.APT),
        SoftwarePackage("curl", package_manager=PackageManager.APT),
        SoftwarePackage("wget", package_manager=PackageManager.APT),
    ],
}

# Profils de logiciels Linux - DNF (RHEL/Rocky/Fedora)
LINUX_DNF_PROFILES = {
    "webserver": [
        SoftwarePackage("nginx", package_manager=PackageManager.DNF),
        SoftwarePackage("httpd", package_manager=PackageManager.DNF),
        SoftwarePackage("php-fpm", package_manager=PackageManager.DNF),
        SoftwarePackage("certbot", package_manager=PackageManager.DNF),
    ],
    "development": [
        SoftwarePackage("git", package_manager=PackageManager.DNF),
        SoftwarePackage("gcc", package_manager=PackageManager.DNF),
        SoftwarePackage("make", package_manager=PackageManager.DNF),
        SoftwarePackage("python3-pip", package_manager=PackageManager.DNF),
        SoftwarePackage("nodejs", package_manager=PackageManager.DNF),
    ],
    "tools": [
        SoftwarePackage("vim-enhanced", package_manager=PackageManager.DNF),
        SoftwarePackage("htop", package_manager=PackageManager.DNF),
        SoftwarePackage("tmux", package_manager=PackageManager.DNF),
        SoftwarePackage("curl", package_manager=PackageManager.DNF),
        SoftwarePackage("wget", package_manager=PackageManager.DNF),
        SoftwarePackage("net-tools", package_manager=PackageManager.DNF),
    ],
    "monitoring": [
        SoftwarePackage("zabbix-agent", package_manager=PackageManager.DNF),
    ],
    "database": [
        SoftwarePackage("postgresql-server", package_manager=PackageManager.DNF),
        SoftwarePackage("mariadb-server", package_manager=PackageManager.DNF),
    ],
    "docker": [
        SoftwarePackage("docker-ce", package_manager=PackageManager.DNF),
        SoftwarePackage("docker-compose-plugin", package_manager=PackageManager.DNF),
    ],
    "minimal": [
        SoftwarePackage("vim-enhanced", package_manager=PackageManager.DNF),
        SoftwarePackage("curl", package_manager=PackageManager.DNF),
        SoftwarePackage("wget", package_manager=PackageManager.DNF),
    ],
}


class SoftwareInstallService:
    """
    Service d'installation de logiciels sur les VMs.
    
    Supporte :
    - Chocolatey pour Windows
    - Winget pour Windows 10/11
    - apt pour Debian/Ubuntu
    - yum/dnf pour RHEL/CentOS
    """

    def __init__(self, hyperv_client: HyperVClient) -> None:
        """
        Initialise le service d'installation.
        
        Args:
            hyperv_client: Client Hyper-V pour l'exécution des commandes
        """
        self.client = hyperv_client

    async def ensure_chocolatey_installed(
        self,
        vm_name: str,
        credentials: tuple[str, str],
    ) -> bool:
        """
        S'assure que Chocolatey est installé sur la VM Windows.
        
        Args:
            vm_name: Nom de la VM
            credentials: (username, password) pour la VM
            
        Returns:
            True si Chocolatey est prêt
        """
        # Script simplifié - vérifier d'abord si Chocolatey est installé
        check_script = """$p="$env:ProgramData\\chocolatey\\bin\\choco.exe";if(Test-Path $p){&$p --version}else{"NOT_INSTALLED"}"""
        
        logger.info("software_ensure_chocolatey", vm_name=vm_name)
        
        result = await self.client.execute_in_vm(
            vm_name, check_script, credentials, timeout=60
        )
        
        logger.info(
            "software_chocolatey_check",
            vm_name=vm_name,
            success=result.success,
            output=str(result.output)[:200] if result.output else None,
            error=result.error,
        )
        
        if result.success and result.output:
            output = str(result.output).strip()
            if output != "NOT_INSTALLED" and output:
                logger.info("software_chocolatey_ready", vm_name=vm_name, version=output)
                return True
        
        # Chocolatey non installé - l'installer
        logger.info("software_installing_chocolatey", vm_name=vm_name)
        install_script = """Set-ExecutionPolicy Bypass -Scope Process -Force;[Net.ServicePointManager]::SecurityProtocol=3072;iex((New-Object Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'));$env:Path=[Environment]::GetEnvironmentVariable('Path','Machine')"""
        
        install_result = await self.client.execute_in_vm(
            vm_name, install_script, credentials, timeout=300
        )
        
        logger.info(
            "software_chocolatey_install_result",
            vm_name=vm_name,
            success=install_result.success,
            error=install_result.error,
        )
        
        # Vérifier à nouveau
        result2 = await self.client.execute_in_vm(
            vm_name, check_script, credentials, timeout=60
        )
        
        if result2.success and result2.output:
            output = str(result2.output).strip()
            if output != "NOT_INSTALLED" and output:
                logger.info("software_chocolatey_ready", vm_name=vm_name, version=output)
                return True
        
        logger.error("software_chocolatey_failed", vm_name=vm_name, error=install_result.error)
        return False

    async def install_package_chocolatey(
        self,
        vm_name: str,
        credentials: tuple[str, str],
        package: SoftwarePackage,
    ) -> InstallationResult:
        """
        Installe un package via Chocolatey.
        
        Args:
            vm_name: Nom de la VM
            credentials: (username, password)
            package: Package à installer
            
        Returns:
            Résultat de l'installation
        """
        version_param = f"--version={package.version}" if package.version else ""
        extra_args = package.install_args or ""
        
        # Script minifié pour éviter la limite de ligne de commande
        script = f"""$n='{package.name}';$i=choco list --exact $n --limit-output;if($i){{@{{Status='skipped';VersionInstalled=($i-split'\\|')[1];Error=$null;Duration=0}}|ConvertTo-Json;return}};$r=choco install $n -y --no-progress {version_param} {extra_args} 2>&1;$c=$LASTEXITCODE;if($c-eq0){{$v=(choco list --exact $n --limit-output)-split'\\|';@{{Status='installed';VersionInstalled=$v[1];Error=$null;Duration=0}}|ConvertTo-Json}}else{{@{{Status='failed';VersionInstalled=$null;Error="Exit:$c"}}|ConvertTo-Json}}"""
        
        logger.info(
            "software_installing_package",
            vm_name=vm_name,
            package=package.name,
        )
        
        result = await self.client.execute_in_vm(
            vm_name, script, credentials, timeout=600
        )
        
        logger.info(
            "software_package_install_result",
            vm_name=vm_name,
            package=package.name,
            success=result.success,
            output_type=type(result.output).__name__,
            output=str(result.output)[:300] if result.output else None,
            error=result.error,
        )
        
        if not result.success:
            return InstallationResult(
                package_name=package.name,
                status=InstallationStatus.FAILED,
                error=result.error,
            )
        
        # Extraire les données du résultat
        data = {}
        if isinstance(result.output, dict):
            # Si c'est un dict avec "value", extraire la valeur
            if "value" in result.output:
                inner = result.output.get("value")
                if isinstance(inner, dict):
                    data = inner
                elif isinstance(inner, str):
                    # Essayer de parser comme JSON
                    try:
                        import json
                        data = json.loads(inner)
                    except Exception:
                        data = {"Status": "installed"} if "installed" in inner.lower() else {}
            else:
                data = result.output
        elif isinstance(result.output, str):
            try:
                import json
                data = json.loads(result.output)
            except Exception:
                data = {}
        
        status_str = data.get("Status", "failed")
        status = InstallationStatus(status_str) if status_str in [s.value for s in InstallationStatus] else InstallationStatus.FAILED
        
        return InstallationResult(
            package_name=package.name,
            status=status,
            version_installed=data.get("VersionInstalled"),
            error=data.get("Error"),
            duration_seconds=data.get("Duration", 0),
        )

    async def install_packages(
        self,
        vm_name: str,
        credentials: tuple[str, str],
        packages: list[SoftwarePackage],
        continue_on_error: bool = True,
    ) -> BatchInstallResult:
        """
        Installe plusieurs packages.
        
        Args:
            vm_name: Nom de la VM
            credentials: (username, password)
            packages: Liste des packages à installer
            continue_on_error: Continuer même si un package échoue
            
        Returns:
            Résultat de l'installation batch
        """
        logger.info(
            "software_batch_install_start",
            vm_name=vm_name,
            package_count=len(packages),
        )
        
        # S'assurer que Chocolatey est installé
        choco_ready = await self.ensure_chocolatey_installed(vm_name, credentials)
        if not choco_ready:
            return BatchInstallResult(
                total=len(packages),
                installed=0,
                failed=len(packages),
                skipped=0,
                results=[
                    InstallationResult(
                        package_name=p.name,
                        status=InstallationStatus.FAILED,
                        error="Chocolatey not available",
                    )
                    for p in packages
                ],
            )
        
        results: list[InstallationResult] = []
        installed = 0
        failed = 0
        skipped = 0
        
        for package in packages:
            if package.package_manager == PackageManager.CHOCOLATEY:
                result = await self.install_package_chocolatey(
                    vm_name, credentials, package
                )
            else:
                result = InstallationResult(
                    package_name=package.name,
                    status=InstallationStatus.FAILED,
                    error=f"Package manager {package.package_manager.value} not supported yet",
                )
            
            results.append(result)
            
            if result.status == InstallationStatus.INSTALLED:
                installed += 1
            elif result.status == InstallationStatus.FAILED:
                failed += 1
                if not continue_on_error:
                    break
            elif result.status == InstallationStatus.SKIPPED:
                skipped += 1
        
        # Vérifier si un reboot est nécessaire
        reboot_script = """
        Test-Path "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Component Based Servicing\\RebootPending" -or
        Test-Path "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired"
        """
        reboot_result = await self.client.execute_in_vm(
            vm_name, reboot_script, credentials, timeout=30
        )
        reboot_required = reboot_result.success and str(reboot_result.output).strip().lower() == "true"
        
        batch_result = BatchInstallResult(
            total=len(packages),
            installed=installed,
            failed=failed,
            skipped=skipped,
            results=results,
            reboot_required=reboot_required,
        )
        
        logger.info(
            "software_batch_install_complete",
            vm_name=vm_name,
            installed=installed,
            failed=failed,
            skipped=skipped,
            reboot_required=reboot_required,
        )
        
        return batch_result

    async def install_profile(
        self,
        vm_name: str,
        credentials: tuple[str, str],
        profile_name: str,
    ) -> BatchInstallResult:
        """
        Installe un profil de logiciels prédéfini.
        
        Args:
            vm_name: Nom de la VM
            credentials: (username, password)
            profile_name: Nom du profil (webserver, development, tools, etc.)
            
        Returns:
            Résultat de l'installation
        """
        if profile_name not in SOFTWARE_PROFILES:
            raise ValueError(f"Unknown profile: {profile_name}. Available: {list(SOFTWARE_PROFILES.keys())}")
        
        packages = SOFTWARE_PROFILES[profile_name]
        
        logger.info(
            "software_install_profile",
            vm_name=vm_name,
            profile=profile_name,
            package_count=len(packages),
        )
        
        return await self.install_packages(vm_name, credentials, packages)

    async def list_installed_packages(
        self,
        vm_name: str,
        credentials: tuple[str, str],
    ) -> list[dict[str, str]]:
        """
        Liste les packages installés via Chocolatey.
        
        Args:
            vm_name: Nom de la VM
            credentials: (username, password)
            
        Returns:
            Liste des packages installés avec leurs versions
        """
        script = """
        $packages = choco list --limit-output 2>$null
        
        $result = @()
        foreach ($line in $packages) {
            if ($line -match '^(.+)\\|(.+)$') {
                $result += @{
                    Name = $matches[1]
                    Version = $matches[2]
                }
            }
        }
        
        $result | ConvertTo-Json -Depth 2
        """
        
        result = await self.client.execute_in_vm(vm_name, script, credentials)
        
        if not result.success:
            logger.warning(
                "software_list_packages_failed",
                vm_name=vm_name,
                error=result.error,
            )
            return []
        
        if isinstance(result.output, list):
            return result.output
        elif isinstance(result.output, dict):
            return [result.output]
        
        return []

    async def uninstall_package(
        self,
        vm_name: str,
        credentials: tuple[str, str],
        package_name: str,
    ) -> InstallationResult:
        """
        Désinstalle un package.
        
        Args:
            vm_name: Nom de la VM
            credentials: (username, password)
            package_name: Nom du package à désinstaller
            
        Returns:
            Résultat de la désinstallation
        """
        script = f"""
        $ErrorActionPreference = 'Stop'
        $startTime = Get-Date
        
        try {{
            # Vérifier si installé
            $installed = choco list --local-only --exact {package_name} --limit-output
            if (-not $installed) {{
                @{{
                    Status = 'skipped'
                    Error = 'Package not installed'
                    Duration = 0
                }} | ConvertTo-Json
                return
            }}
            
            # Désinstaller
            $result = choco uninstall {package_name} -y --no-progress 2>&1
            $exitCode = $LASTEXITCODE
            
            $duration = ((Get-Date) - $startTime).TotalSeconds
            
            if ($exitCode -eq 0) {{
                @{{
                    Status = 'installed'
                    Error = $null
                    Duration = $duration
                }} | ConvertTo-Json
            }} else {{
                @{{
                    Status = 'failed'
                    Error = "Exit code: $exitCode"
                    Duration = $duration
                }} | ConvertTo-Json
            }}
        }} catch {{
            $duration = ((Get-Date) - $startTime).TotalSeconds
            @{{
                Status = 'failed'
                Error = $_.Exception.Message
                Duration = $duration
            }} | ConvertTo-Json
        }}
        """
        
        logger.info(
            "software_uninstalling_package",
            vm_name=vm_name,
            package=package_name,
        )
        
        result = await self.client.execute_in_vm(
            vm_name, script, credentials, timeout=300
        )
        
        if not result.success:
            return InstallationResult(
                package_name=package_name,
                status=InstallationStatus.FAILED,
                error=result.error,
            )
        
        data = result.output if isinstance(result.output, dict) else {}
        status_str = data.get("Status", "failed")
        
        # Pour uninstall, "installed" signifie "successfully uninstalled"
        if status_str == "installed":
            status = InstallationStatus.INSTALLED
        elif status_str == "skipped":
            status = InstallationStatus.SKIPPED
        else:
            status = InstallationStatus.FAILED
        
        return InstallationResult(
            package_name=package_name,
            status=status,
            error=data.get("Error"),
            duration_seconds=data.get("Duration", 0),
        )

    async def upgrade_all_packages(
        self,
        vm_name: str,
        credentials: tuple[str, str],
    ) -> dict[str, Any]:
        """
        Met à jour tous les packages Chocolatey.
        
        Args:
            vm_name: Nom de la VM
            credentials: (username, password)
            
        Returns:
            Résultat de la mise à jour
        """
        script = """
        $ErrorActionPreference = 'Stop'
        $startTime = Get-Date
        
        try {
            $result = choco upgrade all -y --no-progress 2>&1
            $exitCode = $LASTEXITCODE
            
            $duration = ((Get-Date) - $startTime).TotalSeconds
            
            # Parser le résultat
            $upgraded = 0
            $failed = 0
            
            if ($result -match '(\\d+) packages? upgraded') {
                $upgraded = [int]$matches[1]
            }
            if ($result -match '(\\d+) packages? failed') {
                $failed = [int]$matches[1]
            }
            
            @{
                Success = ($exitCode -eq 0)
                UpgradedCount = $upgraded
                FailedCount = $failed
                Duration = $duration
                RebootRequired = (Test-Path "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired")
            } | ConvertTo-Json
            
        } catch {
            @{
                Success = $false
                Error = $_.Exception.Message
                Duration = ((Get-Date) - $startTime).TotalSeconds
            } | ConvertTo-Json
        }
        """
        
        logger.info("software_upgrade_all", vm_name=vm_name)
        
        result = await self.client.execute_in_vm(
            vm_name, script, credentials, timeout=1800  # 30 min max
        )
        
        if not result.success:
            return {
                "success": False,
                "error": result.error,
            }
        
        return {
            "success": True,
            "data": result.output,
        }

    @staticmethod
    def get_available_profiles() -> dict[str, list[str]]:
        """Retourne les profils disponibles avec leurs packages."""
        return {
            profile: [p.name for p in packages]
            for profile, packages in SOFTWARE_PROFILES.items()
        }

    @staticmethod
    def get_linux_apt_profiles() -> dict[str, list[str]]:
        """Retourne les profils Linux APT disponibles."""
        return {
            profile: [p.name for p in packages]
            for profile, packages in LINUX_APT_PROFILES.items()
        }

    @staticmethod
    def get_linux_dnf_profiles() -> dict[str, list[str]]:
        """Retourne les profils Linux DNF disponibles."""
        return {
            profile: [p.name for p in packages]
            for profile, packages in LINUX_DNF_PROFILES.items()
        }

    @staticmethod
    def generate_apt_install_script(
        profile_name: str | None = None,
        packages: list[str] | None = None,
        update_first: bool = True,
        upgrade_system: bool = False,
    ) -> str:
        """
        Génère un script bash pour installer des packages via apt.
        
        Peut être utilisé dans cloud-init ou preseed.
        
        Args:
            profile_name: Nom du profil à installer
            packages: Liste de packages supplémentaires
            update_first: Exécuter apt update avant
            upgrade_system: Exécuter apt upgrade après update
            
        Returns:
            Script bash prêt à l'exécution
        """
        script_lines = ["#!/bin/bash", "set -e", ""]
        
        if update_first:
            script_lines.append("# Mise à jour des sources")
            script_lines.append("apt-get update -y")
            script_lines.append("")
        
        if upgrade_system:
            script_lines.append("# Mise à jour du système")
            script_lines.append("DEBIAN_FRONTEND=noninteractive apt-get upgrade -y")
            script_lines.append("")
        
        # Packages du profil
        profile_packages: list[str] = []
        if profile_name and profile_name in LINUX_APT_PROFILES:
            profile_packages = [p.name for p in LINUX_APT_PROFILES[profile_name]]
        
        # Packages supplémentaires
        all_packages = profile_packages + (packages or [])
        
        if all_packages:
            script_lines.append("# Installation des packages")
            packages_str = " ".join(all_packages)
            script_lines.append(
                f"DEBIAN_FRONTEND=noninteractive apt-get install -y {packages_str}"
            )
            script_lines.append("")
        
        script_lines.append("# Nettoyage")
        script_lines.append("apt-get autoremove -y")
        script_lines.append("apt-get clean")
        script_lines.append("")
        script_lines.append("echo 'Installation terminée'")
        
        return "\n".join(script_lines)

    @staticmethod
    def generate_dnf_install_script(
        profile_name: str | None = None,
        packages: list[str] | None = None,
        update_first: bool = True,
        enable_epel: bool = True,
    ) -> str:
        """
        Génère un script bash pour installer des packages via dnf.
        
        Peut être utilisé dans kickstart ou cloud-init.
        
        Args:
            profile_name: Nom du profil à installer
            packages: Liste de packages supplémentaires
            update_first: Exécuter dnf update avant
            enable_epel: Activer le repository EPEL
            
        Returns:
            Script bash prêt à l'exécution
        """
        script_lines = ["#!/bin/bash", "set -e", ""]
        
        if enable_epel:
            script_lines.append("# Activer EPEL")
            script_lines.append("dnf install -y epel-release || true")
            script_lines.append("")
        
        if update_first:
            script_lines.append("# Mise à jour du système")
            script_lines.append("dnf update -y")
            script_lines.append("")
        
        # Packages du profil
        profile_packages: list[str] = []
        if profile_name and profile_name in LINUX_DNF_PROFILES:
            profile_packages = [p.name for p in LINUX_DNF_PROFILES[profile_name]]
        
        # Packages supplémentaires
        all_packages = profile_packages + (packages or [])
        
        if all_packages:
            script_lines.append("# Installation des packages")
            packages_str = " ".join(all_packages)
            script_lines.append(f"dnf install -y {packages_str}")
            script_lines.append("")
        
        script_lines.append("# Nettoyage")
        script_lines.append("dnf clean all")
        script_lines.append("")
        script_lines.append("echo 'Installation terminée'")
        
        return "\n".join(script_lines)

    @staticmethod
    def generate_cloud_init_packages(
        profile_name: str | None = None,
        packages: list[str] | None = None,
        package_manager: PackageManager = PackageManager.APT,
    ) -> dict[str, Any]:
        """
        Génère la section packages pour cloud-init.
        
        Args:
            profile_name: Nom du profil
            packages: Packages supplémentaires
            package_manager: apt ou dnf
            
        Returns:
            Dict pour inclusion dans cloud-config YAML
        """
        all_packages: list[str] = []
        
        if package_manager == PackageManager.APT:
            if profile_name and profile_name in LINUX_APT_PROFILES:
                all_packages.extend(p.name for p in LINUX_APT_PROFILES[profile_name])
        elif package_manager in (PackageManager.DNF, PackageManager.YUM):
            if profile_name and profile_name in LINUX_DNF_PROFILES:
                all_packages.extend(p.name for p in LINUX_DNF_PROFILES[profile_name])
        
        if packages:
            all_packages.extend(packages)
        
        return {
            "package_update": True,
            "package_upgrade": True,
            "packages": all_packages,
        }
