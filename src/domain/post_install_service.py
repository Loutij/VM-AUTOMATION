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

    # =========================================================================
    # Configuration des logiciels spécifiques
    # =========================================================================

    async def configure_zabbix_agent(
        self,
        vm_name: str,
        credentials: tuple[str, str],
        server_address: str,
        hostname: str | None = None,
        server_active: str | None = None,
        listen_port: int = 10050,
        enable_remote_commands: bool = False,
    ) -> dict[str, Any]:
        """
        Configure Zabbix Agent après installation.
        
        Args:
            vm_name: Nom de la VM
            credentials: (username, password)
            server_address: Adresse du serveur Zabbix (ex: 10.0.0.1)
            hostname: Hostname pour Zabbix (défaut: nom de l'ordinateur)
            server_active: Adresse pour les checks actifs (défaut: server_address)
            listen_port: Port d'écoute (défaut: 10050)
            enable_remote_commands: Autoriser les commandes distantes
        """
        remote_cmds = "1" if enable_remote_commands else "0"
        server_active_addr = server_active or server_address
        
        script = f"""
        $ErrorActionPreference = 'Stop'
        
        try {{
            # Chemins possibles pour le fichier de config
            $configPaths = @(
                "C:\\Program Files\\Zabbix Agent\\zabbix_agentd.conf",
                "C:\\Program Files\\Zabbix Agent 2\\zabbix_agent2.conf",
                "C:\\zabbix_agent\\zabbix_agentd.conf",
                "$env:ProgramData\\zabbix\\zabbix_agentd.conf"
            )
            
            $configFile = $null
            foreach ($path in $configPaths) {{
                if (Test-Path $path) {{
                    $configFile = $path
                    break
                }}
            }}
            
            if (-not $configFile) {{
                @{{
                    Success = $false
                    Error = "Zabbix agent config file not found"
                }} | ConvertTo-Json
                return
            }}
            
            # Lire le fichier de config
            $content = Get-Content $configFile -Raw
            
            # Hostname (utiliser le nom de l'ordinateur si non spécifié)
            $zabbixHostname = "{hostname or ''}"
            if (-not $zabbixHostname) {{
                $zabbixHostname = $env:COMPUTERNAME
            }}
            
            # Mettre à jour les paramètres
            $content = $content -replace '^Server=.*$', 'Server={server_address}' -split "`n" -join "`n"
            $content = $content -replace '^ServerActive=.*$', 'ServerActive={server_active_addr}' -split "`n" -join "`n"
            $content = $content -replace '^Hostname=.*$', "Hostname=$zabbixHostname" -split "`n" -join "`n"
            $content = $content -replace '^ListenPort=.*$', 'ListenPort={listen_port}' -split "`n" -join "`n"
            $content = $content -replace '^EnableRemoteCommands=.*$', 'EnableRemoteCommands={remote_cmds}' -split "`n" -join "`n"
            
            # Sauvegarder
            Set-Content -Path $configFile -Value $content -Force
            
            # Redémarrer le service
            $serviceName = if (Get-Service "Zabbix Agent 2" -ErrorAction SilentlyContinue) {{ "Zabbix Agent 2" }} else {{ "Zabbix Agent" }}
            Restart-Service -Name $serviceName -Force
            
            Start-Sleep -Seconds 2
            
            $svc = Get-Service -Name $serviceName
            
            @{{
                Success = $true
                ConfigFile = $configFile
                Hostname = $zabbixHostname
                Server = "{server_address}"
                ServiceStatus = $svc.Status.ToString()
            }} | ConvertTo-Json
            
        }} catch {{
            @{{
                Success = $false
                Error = $_.Exception.Message
            }} | ConvertTo-Json
        }}
        """
        
        logger.info(
            "post_install_configure_zabbix",
            vm_name=vm_name,
            server=server_address,
        )
        
        result = await self.client.execute_in_vm(
            vm_name, script, credentials, timeout=120
        )
        
        if not result.success:
            return {"success": False, "error": result.error}
        
        return {"success": True, "data": result.output}

    async def configure_sql_server(
        self,
        vm_name: str,
        credentials: tuple[str, str],
        sa_password: str | None = None,
        mixed_mode: bool = True,
        enable_tcp: bool = True,
        tcp_port: int = 1433,
    ) -> dict[str, Any]:
        """
        Configure SQL Server Express après installation.
        
        Args:
            vm_name: Nom de la VM
            credentials: (username, password)
            sa_password: Mot de passe SA (si mixed mode)
            mixed_mode: Activer l'authentification mixte
            enable_tcp: Activer TCP/IP
            tcp_port: Port TCP (défaut: 1433)
        """
        sa_pwd_param = f'"{sa_password}"' if sa_password else '$null'
        
        script = f"""
        $ErrorActionPreference = 'Stop'
        
        try {{
            Import-Module SqlServer -ErrorAction SilentlyContinue
            
            # Configurer le mode d'authentification
            $instanceName = "SQLEXPRESS"
            $regPath = "HKLM:\\SOFTWARE\\Microsoft\\Microsoft SQL Server\\MSSQL*.$instanceName\\MSSQLServer"
            
            # Trouver le bon chemin de registre
            $regPath = Get-ChildItem "HKLM:\\SOFTWARE\\Microsoft\\Microsoft SQL Server" | 
                Where-Object {{ $_.Name -like "*MSSQL*.$instanceName" }} |
                Select-Object -First 1 |
                ForEach-Object {{ "$($_.PSPath)\\MSSQLServer" }}
            
            if ($regPath -and {str(mixed_mode).lower()}) {{
                # Mode mixte (1 = Windows, 2 = Mixed)
                Set-ItemProperty -Path $regPath -Name "LoginMode" -Value 2
            }}
            
            # Configurer le mot de passe SA
            $saPwd = {sa_pwd_param}
            if ($saPwd) {{
                $query = "ALTER LOGIN sa ENABLE; ALTER LOGIN sa WITH PASSWORD = '$saPwd'"
                Invoke-Sqlcmd -ServerInstance "localhost\\$instanceName" -Query $query -TrustServerCertificate
            }}
            
            # Activer TCP/IP si demandé
            if ({str(enable_tcp).lower()}) {{
                $wmi = [Microsoft.SqlServer.Management.Smo.Wmi.ManagedComputer]::new()
                $tcp = $wmi.ServerInstances["$instanceName"].ServerProtocols["Tcp"]
                $tcp.IsEnabled = $true
                $tcp.Alter()
                
                # Configurer le port
                foreach ($ipAddress in $tcp.IPAddresses) {{
                    $ipAddress.IPAddressProperties["TcpPort"].Value = "{tcp_port}"
                    $ipAddress.IPAddressProperties["TcpDynamicPorts"].Value = ""
                }}
                $tcp.Alter()
            }}
            
            # Redémarrer SQL Server
            Restart-Service -Name "MSSQL`$$instanceName" -Force
            Start-Sleep -Seconds 5
            
            # Configurer le firewall
            New-NetFirewallRule -DisplayName "SQL Server" -Direction Inbound -Protocol TCP -LocalPort {tcp_port} -Action Allow -ErrorAction SilentlyContinue
            
            $svc = Get-Service -Name "MSSQL`$$instanceName"
            
            @{{
                Success = $true
                InstanceName = $instanceName
                MixedMode = {str(mixed_mode).lower()}
                TCPEnabled = {str(enable_tcp).lower()}
                TCPPort = {tcp_port}
                ServiceStatus = $svc.Status.ToString()
            }} | ConvertTo-Json
            
        }} catch {{
            @{{
                Success = $false
                Error = $_.Exception.Message
            }} | ConvertTo-Json
        }}
        """
        
        logger.info(
            "post_install_configure_sql_server",
            vm_name=vm_name,
            mixed_mode=mixed_mode,
        )
        
        result = await self.client.execute_in_vm(
            vm_name, script, credentials, timeout=180
        )
        
        if not result.success:
            return {"success": False, "error": result.error}
        
        return {"success": True, "data": result.output}

    async def configure_iis(
        self,
        vm_name: str,
        credentials: tuple[str, str],
        site_name: str = "Default Web Site",
        physical_path: str = "C:\\inetpub\\wwwroot",
        binding_port: int = 80,
        binding_hostname: str | None = None,
    ) -> dict[str, Any]:
        """
        Configure IIS après installation.
        
        Args:
            vm_name: Nom de la VM
            credentials: (username, password)
            site_name: Nom du site (défaut: Default Web Site)
            physical_path: Chemin physique du site
            binding_port: Port de binding
            binding_hostname: Hostname de binding (optionnel)
        """
        hostname_param = f'"{binding_hostname}"' if binding_hostname else '$null'
        
        script = f"""
        $ErrorActionPreference = 'Stop'
        
        try {{
            Import-Module WebAdministration
            
            # Vérifier si le site existe
            $site = Get-Website -Name "{site_name}" -ErrorAction SilentlyContinue
            
            if (-not $site) {{
                # Créer le site
                New-Website -Name "{site_name}" -PhysicalPath "{physical_path}" -Port {binding_port}
            }} else {{
                # Mettre à jour le site existant
                Set-ItemProperty "IIS:\\Sites\\{site_name}" -Name physicalPath -Value "{physical_path}"
            }}
            
            # Configurer le binding
            $bindInfo = "*:{binding_port}:"
            $hostname = {hostname_param}
            if ($hostname) {{
                $bindInfo = "*:{binding_port}:$hostname"
            }}
            
            # Supprimer les bindings existants et en créer un nouveau
            $existingBindings = Get-WebBinding -Name "{site_name}" -Port {binding_port} -Protocol http
            if (-not $existingBindings) {{
                New-WebBinding -Name "{site_name}" -Protocol http -Port {binding_port} -HostHeader $hostname
            }}
            
            # Démarrer le site
            Start-Website -Name "{site_name}"
            
            # Configurer le firewall
            New-NetFirewallRule -DisplayName "IIS HTTP" -Direction Inbound -Protocol TCP -LocalPort {binding_port} -Action Allow -ErrorAction SilentlyContinue
            
            $site = Get-Website -Name "{site_name}"
            
            @{{
                Success = $true
                SiteName = "{site_name}"
                PhysicalPath = "{physical_path}"
                Port = {binding_port}
                State = $site.State
            }} | ConvertTo-Json
            
        }} catch {{
            @{{
                Success = $false
                Error = $_.Exception.Message
            }} | ConvertTo-Json
        }}
        """
        
        logger.info(
            "post_install_configure_iis",
            vm_name=vm_name,
            site_name=site_name,
        )
        
        result = await self.client.execute_in_vm(
            vm_name, script, credentials, timeout=120
        )
        
        if not result.success:
            return {"success": False, "error": result.error}
        
        return {"success": True, "data": result.output}

    async def join_domain(
        self,
        vm_name: str,
        credentials: tuple[str, str],
        domain_name: str,
        domain_user: str,
        domain_password: str,
        ou_path: str | None = None,
        reboot: bool = True,
    ) -> dict[str, Any]:
        """
        Joint la VM à un domaine Active Directory.
        
        Args:
            vm_name: Nom de la VM
            credentials: (username, password) - compte local admin
            domain_name: Nom du domaine (ex: example.local)
            domain_user: Utilisateur pour joindre le domaine
            domain_password: Mot de passe du compte domaine
            ou_path: OU cible (optionnel)
            reboot: Redémarrer après jonction
        """
        ou_param = f'-OUPath "{ou_path}"' if ou_path else ""
        reboot_param = "-Restart" if reboot else ""
        
        script = f"""
        $ErrorActionPreference = 'Stop'
        
        try {{
            # Vérifier si déjà dans le domaine
            $cs = Get-WmiObject Win32_ComputerSystem
            if ($cs.PartOfDomain -and $cs.Domain -eq "{domain_name}") {{
                @{{
                    Success = $true
                    AlreadyJoined = $true
                    Domain = "{domain_name}"
                    Message = "Already joined to domain"
                }} | ConvertTo-Json
                return
            }}
            
            # Créer les credentials pour le domaine
            $secPwd = ConvertTo-SecureString "{domain_password}" -AsPlainText -Force
            $domainCred = New-Object System.Management.Automation.PSCredential("{domain_user}", $secPwd)
            
            # Joindre le domaine
            Add-Computer -DomainName "{domain_name}" -Credential $domainCred {ou_param} {reboot_param} -Force
            
            @{{
                Success = $true
                AlreadyJoined = $false
                Domain = "{domain_name}"
                RebootInitiated = {str(reboot).lower()}
                Message = "Domain join initiated"
            }} | ConvertTo-Json
            
        }} catch {{
            @{{
                Success = $false
                Error = $_.Exception.Message
            }} | ConvertTo-Json
        }}
        """
        
        logger.info(
            "post_install_join_domain",
            vm_name=vm_name,
            domain=domain_name,
        )
        
        result = await self.client.execute_in_vm(
            vm_name, script, credentials, timeout=120
        )
        
        if not result.success:
            return {"success": False, "error": result.error}
        
        return {"success": True, "data": result.output}
