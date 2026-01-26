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


# Profils de logiciels prédéfinis
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
        script = """
        # Vérifier si Chocolatey est installé
        $chocoPath = "$env:ProgramData\\chocolatey\\bin\\choco.exe"
        
        if (Test-Path $chocoPath) {
            $version = & $chocoPath --version
            Write-Output "INSTALLED:$version"
            return
        }
        
        Write-Host "Installation de Chocolatey..."
        
        # Installer Chocolatey
        Set-ExecutionPolicy Bypass -Scope Process -Force
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
        
        try {
            Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
            
            # Rafraîchir le PATH
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
            
            # Vérifier l'installation
            if (Test-Path $chocoPath) {
                $version = & $chocoPath --version
                Write-Output "INSTALLED:$version"
            } else {
                Write-Output "FAILED:Installation failed"
            }
        } catch {
            Write-Output "FAILED:$($_.Exception.Message)"
        }
        """
        
        logger.info("software_ensure_chocolatey", vm_name=vm_name)
        
        result = await self.client.execute_in_vm(
            vm_name, script, credentials, timeout=300
        )
        
        if result.success and result.output:
            output = str(result.output).strip()
            if output.startswith("INSTALLED:"):
                version = output.split(":", 1)[1]
                logger.info(
                    "software_chocolatey_ready",
                    vm_name=vm_name,
                    version=version,
                )
                return True
        
        logger.error(
            "software_chocolatey_failed",
            vm_name=vm_name,
            error=result.error or result.output,
        )
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
        
        script = f"""
        $ErrorActionPreference = 'Stop'
        $startTime = Get-Date
        
        try {{
            # Vérifier si déjà installé
            $installed = choco list --exact {package.name} --limit-output
            if ($installed) {{
                $currentVersion = ($installed -split '\\|')[1]
                @{{
                    Status = 'skipped'
                    VersionInstalled = $currentVersion
                    Error = $null
                    Duration = 0
                }} | ConvertTo-Json
                return
            }}
            
            # Installer le package
            $result = choco install {package.name} -y --no-progress {version_param} {extra_args} 2>&1
            $exitCode = $LASTEXITCODE
            
            $duration = ((Get-Date) - $startTime).TotalSeconds
            
            if ($exitCode -eq 0) {{
                # Récupérer la version installée
                $installed = choco list --exact {package.name} --limit-output
                $version = if ($installed) {{ ($installed -split '\\|')[1] }} else {{ 'unknown' }}
                
                @{{
                    Status = 'installed'
                    VersionInstalled = $version
                    Error = $null
                    Duration = $duration
                }} | ConvertTo-Json
            }} else {{
                @{{
                    Status = 'failed'
                    VersionInstalled = $null
                    Error = "Exit code: $exitCode - $result"
                    Duration = $duration
                }} | ConvertTo-Json
            }}
        }} catch {{
            $duration = ((Get-Date) - $startTime).TotalSeconds
            @{{
                Status = 'failed'
                VersionInstalled = $null
                Error = $_.Exception.Message
                Duration = $duration
            }} | ConvertTo-Json
        }}
        """
        
        logger.info(
            "software_installing_package",
            vm_name=vm_name,
            package=package.name,
        )
        
        result = await self.client.execute_in_vm(
            vm_name, script, credentials, timeout=600
        )
        
        if not result.success:
            return InstallationResult(
                package_name=package.name,
                status=InstallationStatus.FAILED,
                error=result.error,
            )
        
        data = result.output if isinstance(result.output, dict) else {}
        
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
