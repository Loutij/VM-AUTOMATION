# =============================================================================
# VM Automation - Post-Installation Service
# =============================================================================
"""
Service pour les opérations de post-installation sur les VMs.
Utilise PowerShell Direct pour exécuter des commandes dans les VMs Windows.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.common.logging import get_logger
from src.integrations.hypervisors.hyperv_client import HyperVClient

logger = get_logger(__name__)


class WindowsUpdateCategory(str, Enum):
    """Catégories de mises à jour Windows."""
    CRITICAL = "Critical Updates"
    SECURITY = "Security Updates"
    DEFINITION = "Definition Updates"
    FEATURE = "Feature Packs"
    SERVICE_PACK = "Service Packs"
    UPDATE_ROLLUP = "Update Rollups"
    UPDATES = "Updates"
    DRIVERS = "Drivers"


@dataclass
class WindowsUpdateResult:
    """Résultat d'une opération Windows Update."""
    success: bool
    updates_found: int
    updates_installed: int
    reboot_required: bool
    error: str | None = None
    installed_updates: list[str] | None = None


@dataclass
class ServiceConfigResult:
    """Résultat de configuration d'un service."""
    service_name: str
    success: bool
    status: str
    start_type: str
    error: str | None = None


@dataclass
class PasswordPolicyResult:
    """Résultat de configuration des politiques de mot de passe."""
    success: bool
    min_length: int
    complexity_enabled: bool
    max_age_days: int
    error: str | None = None


class PostInstallService:
    """
    Service de post-installation pour les VMs.
    
    Fournit des méthodes pour :
    - Installer les mises à jour Windows
    - Configurer les services
    - Appliquer les politiques de sécurité
    - Gérer les redémarrages
    """

    def __init__(self, hyperv_client: HyperVClient) -> None:
        """
        Initialise le service de post-installation.
        
        Args:
            hyperv_client: Client Hyper-V pour l'exécution des commandes
        """
        self.client = hyperv_client

    async def check_windows_updates(
        self,
        vm_name: str,
        credentials: tuple[str, str],
        categories: list[WindowsUpdateCategory] | None = None,
    ) -> dict[str, Any]:
        """
        Vérifie les mises à jour Windows disponibles.
        
        Args:
            vm_name: Nom de la VM
            credentials: (username, password) pour la VM
            categories: Catégories de mises à jour à vérifier (toutes par défaut)
        """
        categories_filter = ""
        if categories:
            cat_list = ", ".join([f"'{c.value}'" for c in categories])
            categories_filter = f"| Where-Object {{ $_.Categories.Name -in @({cat_list}) }}"
        
        script = f"""
        $UpdateSession = New-Object -ComObject Microsoft.Update.Session
        $UpdateSearcher = $UpdateSession.CreateUpdateSearcher()
        
        Write-Host "Recherche des mises a jour..."
        $SearchResult = $UpdateSearcher.Search("IsInstalled=0 and Type='Software'")
        
        $Updates = $SearchResult.Updates {categories_filter}
        
        @{{
            TotalFound = $Updates.Count
            Updates = $Updates | ForEach-Object {{
                @{{
                    Title = $_.Title
                    KB = ($_.KBArticleIDs -join ", ")
                    Size = [math]::Round($_.MaxDownloadSize / 1MB, 2)
                    Category = ($_.Categories | Select-Object -First 1).Name
                    Severity = $_.MsrcSeverity
                }}
            }}
        }} | ConvertTo-Json -Depth 3
        """
        
        logger.info("post_install_check_updates", vm_name=vm_name)
        
        result = await self.client.execute_in_vm(vm_name, script, credentials, timeout=300)
        
        if not result.success:
            return {
                "success": False,
                "error": result.error,
                "updates": [],
            }
        
        return {
            "success": True,
            "data": result.output,
        }

    async def install_windows_updates(
        self,
        vm_name: str,
        credentials: tuple[str, str],
        categories: list[WindowsUpdateCategory] | None = None,
        auto_reboot: bool = False,
    ) -> WindowsUpdateResult:
        """
        Installe les mises à jour Windows.
        
        Args:
            vm_name: Nom de la VM
            credentials: (username, password) pour la VM
            categories: Catégories de mises à jour à installer
            auto_reboot: Redémarrer automatiquement si nécessaire
        """
        categories_filter = ""
        if categories:
            cat_list = ", ".join([f"'{c.value}'" for c in categories])
            categories_filter = f"| Where-Object {{ $_.Categories.Name -in @({cat_list}) }}"
        
        reboot_action = "Shutdown.exe /r /t 60 /c 'Windows Update - Redemarrage automatique'" if auto_reboot else ""
        
        script = f"""
        $ErrorActionPreference = 'Stop'
        
        try {{
            $UpdateSession = New-Object -ComObject Microsoft.Update.Session
            $UpdateSearcher = $UpdateSession.CreateUpdateSearcher()
            
            Write-Host "Recherche des mises a jour..."
            $SearchResult = $UpdateSearcher.Search("IsInstalled=0 and Type='Software'")
            $Updates = $SearchResult.Updates {categories_filter}
            
            if ($Updates.Count -eq 0) {{
                @{{
                    Success = $true
                    UpdatesFound = 0
                    UpdatesInstalled = 0
                    RebootRequired = $false
                    InstalledUpdates = @()
                }} | ConvertTo-Json
                return
            }}
            
            Write-Host "Telechargement de $($Updates.Count) mises a jour..."
            $Downloader = $UpdateSession.CreateUpdateDownloader()
            $UpdatesToDownload = New-Object -ComObject Microsoft.Update.UpdateColl
            
            foreach ($Update in $Updates) {{
                if (-not $Update.IsDownloaded) {{
                    $UpdatesToDownload.Add($Update) | Out-Null
                }}
            }}
            
            if ($UpdatesToDownload.Count -gt 0) {{
                $Downloader.Updates = $UpdatesToDownload
                $DownloadResult = $Downloader.Download()
            }}
            
            Write-Host "Installation des mises a jour..."
            $Installer = $UpdateSession.CreateUpdateInstaller()
            $UpdatesToInstall = New-Object -ComObject Microsoft.Update.UpdateColl
            
            foreach ($Update in $Updates) {{
                if ($Update.IsDownloaded) {{
                    $UpdatesToInstall.Add($Update) | Out-Null
                }}
            }}
            
            $Installer.Updates = $UpdatesToInstall
            $InstallResult = $Installer.Install()
            
            $InstalledList = @()
            for ($i = 0; $i -lt $UpdatesToInstall.Count; $i++) {{
                if ($InstallResult.GetUpdateResult($i).ResultCode -eq 2) {{
                    $InstalledList += $UpdatesToInstall.Item($i).Title
                }}
            }}
            
            $RebootRequired = $InstallResult.RebootRequired
            
            {f'if ($RebootRequired) {{ {reboot_action} }}' if auto_reboot else ''}
            
            @{{
                Success = $true
                UpdatesFound = $Updates.Count
                UpdatesInstalled = $InstalledList.Count
                RebootRequired = $RebootRequired
                InstalledUpdates = $InstalledList
            }} | ConvertTo-Json -Depth 2
            
        }} catch {{
            @{{
                Success = $false
                UpdatesFound = 0
                UpdatesInstalled = 0
                RebootRequired = $false
                Error = $_.Exception.Message
            }} | ConvertTo-Json
        }}
        """
        
        logger.info(
            "post_install_installing_updates",
            vm_name=vm_name,
            auto_reboot=auto_reboot,
        )
        
        result = await self.client.execute_in_vm(
            vm_name, script, credentials, timeout=1800  # 30 min pour les updates
        )
        
        if not result.success:
            return WindowsUpdateResult(
                success=False,
                updates_found=0,
                updates_installed=0,
                reboot_required=False,
                error=result.error,
            )
        
        data = result.output if isinstance(result.output, dict) else {}
        
        return WindowsUpdateResult(
            success=data.get("Success", False),
            updates_found=data.get("UpdatesFound", 0),
            updates_installed=data.get("UpdatesInstalled", 0),
            reboot_required=data.get("RebootRequired", False),
            installed_updates=data.get("InstalledUpdates", []),
            error=data.get("Error"),
        )

    async def configure_service(
        self,
        vm_name: str,
        credentials: tuple[str, str],
        service_name: str,
        start_type: str = "Automatic",
        ensure_running: bool = True,
    ) -> ServiceConfigResult:
        """
        Configure un service Windows.
        
        Args:
            vm_name: Nom de la VM
            credentials: (username, password) pour la VM
            service_name: Nom du service
            start_type: Type de démarrage (Automatic, Manual, Disabled)
            ensure_running: Démarrer le service si non actif
        """
        start_action = "Start-Service -Name $svc.Name -ErrorAction SilentlyContinue" if ensure_running else ""
        
        script = f"""
        $svc = Get-Service -Name '{service_name}' -ErrorAction SilentlyContinue
        
        if (-not $svc) {{
            @{{
                ServiceName = '{service_name}'
                Success = $false
                Status = 'NotFound'
                StartType = 'Unknown'
                Error = 'Service not found'
            }} | ConvertTo-Json
            return
        }}
        
        try {{
            Set-Service -Name $svc.Name -StartupType '{start_type}'
            {start_action}
            
            $svc = Get-Service -Name '{service_name}'
            
            @{{
                ServiceName = $svc.Name
                Success = $true
                Status = $svc.Status.ToString()
                StartType = $svc.StartType.ToString()
                Error = $null
            }} | ConvertTo-Json
        }} catch {{
            @{{
                ServiceName = '{service_name}'
                Success = $false
                Status = $svc.Status.ToString()
                StartType = $svc.StartType.ToString()
                Error = $_.Exception.Message
            }} | ConvertTo-Json
        }}
        """
        
        logger.info(
            "post_install_configure_service",
            vm_name=vm_name,
            service=service_name,
            start_type=start_type,
        )
        
        result = await self.client.execute_in_vm(vm_name, script, credentials)
        
        if not result.success:
            return ServiceConfigResult(
                service_name=service_name,
                success=False,
                status="Unknown",
                start_type="Unknown",
                error=result.error,
            )
        
        data = result.output if isinstance(result.output, dict) else {}
        
        return ServiceConfigResult(
            service_name=data.get("ServiceName", service_name),
            success=data.get("Success", False),
            status=data.get("Status", "Unknown"),
            start_type=data.get("StartType", "Unknown"),
            error=data.get("Error"),
        )

    async def configure_password_policy(
        self,
        vm_name: str,
        credentials: tuple[str, str],
        min_length: int = 12,
        complexity_enabled: bool = True,
        max_age_days: int = 90,
        min_age_days: int = 1,
        history_count: int = 5,
    ) -> PasswordPolicyResult:
        """
        Configure les politiques de mot de passe Windows.
        
        Args:
            vm_name: Nom de la VM
            credentials: (username, password)
            min_length: Longueur minimale du mot de passe
            complexity_enabled: Exiger la complexité
            max_age_days: Âge maximum (0 = jamais expire)
            min_age_days: Âge minimum avant changement
            history_count: Nombre de mots de passe mémorisés
        """
        complexity_value = 1 if complexity_enabled else 0
        
        script = f"""
        try {{
            # Exporter la politique actuelle
            secedit /export /cfg C:\\secpol.cfg /quiet
            
            # Modifier les valeurs
            $content = Get-Content C:\\secpol.cfg
            $content = $content -replace 'MinimumPasswordLength = \\d+', 'MinimumPasswordLength = {min_length}'
            $content = $content -replace 'PasswordComplexity = \\d+', 'PasswordComplexity = {complexity_value}'
            $content = $content -replace 'MaximumPasswordAge = \\d+', 'MaximumPasswordAge = {max_age_days}'
            $content = $content -replace 'MinimumPasswordAge = \\d+', 'MinimumPasswordAge = {min_age_days}'
            $content = $content -replace 'PasswordHistorySize = \\d+', 'PasswordHistorySize = {history_count}'
            
            Set-Content C:\\secpol.cfg -Value $content
            
            # Appliquer la politique
            secedit /configure /db C:\\Windows\\security\\local.sdb /cfg C:\\secpol.cfg /quiet
            
            # Nettoyer
            Remove-Item C:\\secpol.cfg -Force
            
            # Vérifier
            $policy = net accounts
            
            @{{
                Success = $true
                MinLength = {min_length}
                ComplexityEnabled = ${str(complexity_enabled).lower()}
                MaxAgeDays = {max_age_days}
                Error = $null
            }} | ConvertTo-Json
            
        }} catch {{
            @{{
                Success = $false
                MinLength = 0
                ComplexityEnabled = $false
                MaxAgeDays = 0
                Error = $_.Exception.Message
            }} | ConvertTo-Json
        }}
        """
        
        logger.info(
            "post_install_configure_password_policy",
            vm_name=vm_name,
            min_length=min_length,
            complexity=complexity_enabled,
        )
        
        result = await self.client.execute_in_vm(vm_name, script, credentials)
        
        if not result.success:
            return PasswordPolicyResult(
                success=False,
                min_length=0,
                complexity_enabled=False,
                max_age_days=0,
                error=result.error,
            )
        
        data = result.output if isinstance(result.output, dict) else {}
        
        return PasswordPolicyResult(
            success=data.get("Success", False),
            min_length=data.get("MinLength", 0),
            complexity_enabled=data.get("ComplexityEnabled", False),
            max_age_days=data.get("MaxAgeDays", 0),
            error=data.get("Error"),
        )

    async def install_ssh_server(
        self,
        vm_name: str,
        credentials: tuple[str, str],
    ) -> ServiceConfigResult:
        """
        Installe et configure le serveur SSH sur Windows.
        
        Args:
            vm_name: Nom de la VM
            credentials: (username, password)
        """
        script = """
        try {
            # Vérifier si déjà installé
            $sshd = Get-Service sshd -ErrorAction SilentlyContinue
            
            if (-not $sshd) {
                Write-Host "Installation OpenSSH Server..."
                
                # Installer la fonctionnalité
                Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
                
                # Attendre que le service soit disponible
                Start-Sleep -Seconds 5
            }
            
            # Configurer et démarrer
            Set-Service -Name sshd -StartupType Automatic
            Start-Service sshd
            
            # Configurer le firewall
            $rule = Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue
            if (-not $rule) {
                New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -DisplayName "OpenSSH Server (sshd)" -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
            }
            
            $svc = Get-Service sshd
            
            @{
                ServiceName = "sshd"
                Success = $true
                Status = $svc.Status.ToString()
                StartType = $svc.StartType.ToString()
                Error = $null
            } | ConvertTo-Json
            
        } catch {
            @{
                ServiceName = "sshd"
                Success = $false
                Status = "Unknown"
                StartType = "Unknown"
                Error = $_.Exception.Message
            } | ConvertTo-Json
        }
        """
        
        logger.info("post_install_installing_ssh", vm_name=vm_name)
        
        result = await self.client.execute_in_vm(
            vm_name, script, credentials, timeout=300
        )
        
        if not result.success:
            return ServiceConfigResult(
                service_name="sshd",
                success=False,
                status="Unknown",
                start_type="Unknown",
                error=result.error,
            )
        
        data = result.output if isinstance(result.output, dict) else {}
        
        return ServiceConfigResult(
            service_name="sshd",
            success=data.get("Success", False),
            status=data.get("Status", "Unknown"),
            start_type=data.get("StartType", "Unknown"),
            error=data.get("Error"),
        )

    async def configure_firewall_rule(
        self,
        vm_name: str,
        credentials: tuple[str, str],
        rule_name: str,
        display_name: str,
        protocol: str = "TCP",
        local_port: int | str = "Any",
        direction: str = "Inbound",
        action: str = "Allow",
        enabled: bool = True,
    ) -> dict[str, Any]:
        """
        Configure une règle de firewall Windows.
        
        Args:
            vm_name: Nom de la VM
            credentials: (username, password)
            rule_name: Nom technique de la règle
            display_name: Nom d'affichage
            protocol: TCP ou UDP
            local_port: Port ou "Any"
            direction: Inbound ou Outbound
            action: Allow ou Block
            enabled: Activer la règle
        """
        port_param = f"-LocalPort {local_port}" if local_port != "Any" else ""
        
        script = f"""
        try {{
            # Supprimer l'ancienne règle si elle existe
            Remove-NetFirewallRule -Name '{rule_name}' -ErrorAction SilentlyContinue
            
            # Créer la nouvelle règle
            New-NetFirewallRule `
                -Name '{rule_name}' `
                -DisplayName '{display_name}' `
                -Enabled {str(enabled)} `
                -Direction {direction} `
                -Protocol {protocol} `
                -Action {action} `
                {port_param} | Out-Null
            
            $rule = Get-NetFirewallRule -Name '{rule_name}'
            
            @{{
                Success = $true
                RuleName = $rule.Name
                DisplayName = $rule.DisplayName
                Enabled = $rule.Enabled.ToString()
                Direction = $rule.Direction.ToString()
                Action = $rule.Action.ToString()
            }} | ConvertTo-Json
            
        }} catch {{
            @{{
                Success = $false
                Error = $_.Exception.Message
            }} | ConvertTo-Json
        }}
        """
        
        logger.info(
            "post_install_configure_firewall",
            vm_name=vm_name,
            rule_name=rule_name,
            port=local_port,
        )
        
        result = await self.client.execute_in_vm(vm_name, script, credentials)
        
        if not result.success:
            return {"success": False, "error": result.error}
        
        return {"success": True, "data": result.output}

    async def schedule_reboot(
        self,
        vm_name: str,
        credentials: tuple[str, str],
        delay_seconds: int = 60,
        message: str = "Redémarrage planifié par VM Automation",
    ) -> dict[str, Any]:
        """
        Planifie un redémarrage de la VM.
        
        Args:
            vm_name: Nom de la VM
            credentials: (username, password)
            delay_seconds: Délai avant redémarrage
            message: Message affiché aux utilisateurs
        """
        script = f"""
        try {{
            shutdown.exe /r /t {delay_seconds} /c "{message}"
            
            @{{
                Success = $true
                DelaySeconds = {delay_seconds}
                Message = "{message}"
            }} | ConvertTo-Json
            
        }} catch {{
            @{{
                Success = $false
                Error = $_.Exception.Message
            }} | ConvertTo-Json
        }}
        """
        
        logger.info(
            "post_install_schedule_reboot",
            vm_name=vm_name,
            delay=delay_seconds,
        )
        
        result = await self.client.execute_in_vm(vm_name, script, credentials)
        
        return {
            "success": result.success,
            "data": result.output if result.success else None,
            "error": result.error,
        }

    async def cancel_reboot(
        self,
        vm_name: str,
        credentials: tuple[str, str],
    ) -> dict[str, Any]:
        """Annule un redémarrage planifié."""
        script = """
        try {
            shutdown.exe /a
            @{ Success = $true } | ConvertTo-Json
        } catch {
            @{ Success = $false; Error = $_.Exception.Message } | ConvertTo-Json
        }
        """
        
        result = await self.client.execute_in_vm(vm_name, script, credentials)
        
        return {
            "success": result.success,
            "error": result.error,
        }

    async def get_system_info(
        self,
        vm_name: str,
        credentials: tuple[str, str],
    ) -> dict[str, Any]:
        """
        Récupère les informations système complètes de la VM.
        
        Args:
            vm_name: Nom de la VM
            credentials: (username, password)
        """
        script = """
        $os = Get-WmiObject Win32_OperatingSystem
        $cs = Get-WmiObject Win32_ComputerSystem
        $cpu = Get-WmiObject Win32_Processor
        $disk = Get-WmiObject Win32_LogicalDisk -Filter "DeviceID='C:'"
        
        @{
            Hostname = $env:COMPUTERNAME
            OS = $os.Caption
            OSVersion = $os.Version
            Architecture = $env:PROCESSOR_ARCHITECTURE
            Domain = $cs.Domain
            PartOfDomain = $cs.PartOfDomain
            TotalMemoryGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 2)
            CPU = $cpu.Name
            CPUCores = $cpu.NumberOfCores
            DiskSizeGB = [math]::Round($disk.Size / 1GB, 2)
            DiskFreeGB = [math]::Round($disk.FreeSpace / 1GB, 2)
            LastBoot = $os.LastBootUpTime
            Uptime = ((Get-Date) - $os.ConvertToDateTime($os.LastBootUpTime)).ToString()
            WindowsUpdateService = (Get-Service wuauserv).Status.ToString()
            PendingReboot = (Test-Path "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired")
        } | ConvertTo-Json
        """
        
        result = await self.client.execute_in_vm(vm_name, script, credentials)
        
        if not result.success:
            return {"success": False, "error": result.error}
        
        return {"success": True, "data": result.output}
