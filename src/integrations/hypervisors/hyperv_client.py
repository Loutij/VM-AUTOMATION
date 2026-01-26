# =============================================================================
# VM Automation - Hyper-V Client
# =============================================================================
"""
Client pour l'interaction avec les hôtes Hyper-V via PowerShell/WinRM.
"""

import json
from typing import Any

from src.common.config import settings
from src.common.exceptions import (
    HypervisorConnectionError,
    HypervisorError,
    VMCreationError,
    VMNotFoundError,
    VMOperationError,
)
from src.common.logging import get_logger
from src.common.powershell import (
    PowerShellExecutor,
    PowerShellResult,
    create_powershell_executor,
)
from src.integrations.hypervisors.base import (
    BaseHypervisor,
    DiskInfo,
    IntegrationService,
    NetworkAdapterInfo,
    NetworkInterfaceDetails,
    PowerShellDirectResult,
    VirtualSwitch,
    VMHealthStatus,
    VMInfo,
    VMNetworkInfo,
    VMSpecs,
)

logger = get_logger(__name__)


class HyperVClient(BaseHypervisor):
    """
    Client Hyper-V utilisant PowerShell via WinRM.
    
    Permet de gérer les VMs, switches, et disques sur un hôte Hyper-V distant.
    """

    def __init__(
        self,
        host: str | None = None,
        username: str | None = None,
        password: str | None = None,
        use_ssl: bool | None = None,
        use_mock: bool = False,
    ) -> None:
        """
        Initialise le client Hyper-V.
        
        Args:
            host: Adresse de l'hôte Hyper-V
            username: Utilisateur
            password: Mot de passe
            use_ssl: Utiliser SSL
            use_mock: Utiliser le mock PowerShell
        """
        self.host = host or settings.hyperv_host
        self.username = username or settings.hyperv_user
        self.password = password or settings.hyperv_password.get_secret_value()
        self.use_ssl = use_ssl if use_ssl is not None else settings.hyperv_use_ssl
        
        self._executor = create_powershell_executor(
            host=self.host,
            username=self.username,
            password=self.password,
            use_ssl=self.use_ssl,
            use_mock=use_mock,
        )
        
        # Chemins par défaut
        self.vm_path = settings.hyperv_vm_path
        self.vhdx_path = settings.hyperv_vhdx_path
        self.iso_path = settings.hyperv_iso_path

    async def _execute(
        self,
        script: str,
        timeout: int | None = None,
    ) -> PowerShellResult:
        """Exécute un script PowerShell."""
        return await self._executor.execute_async(script, timeout)

    def _parse_json_output(self, output: str) -> Any:
        """Parse la sortie JSON d'une commande PowerShell."""
        if not output.strip():
            return None
        try:
            return json.loads(output)
        except json.JSONDecodeError as e:
            logger.warning(
                "json_parse_error",
                output=output[:200],
                error=str(e),
            )
            return None

    async def test_connection(self) -> bool:
        """Teste la connexion à l'hôte Hyper-V."""
        try:
            result = await self._execute(
                "Get-VMHost | Select-Object Name | ConvertTo-Json",
                timeout=30,
            )
            return result.success
        except Exception as e:
            logger.warning(
                "hyperv_connection_test_failed",
                host=self.host,
                error=str(e),
            )
            return False

    async def list_vms(self) -> list[VMInfo]:
        """Liste toutes les VMs sur l'hôte."""
        script = """
        Get-VM | Select-Object @{N='id';E={$_.VMId.ToString()}},
                               Name,
                               State,
                               @{N='cpu_count';E={$_.ProcessorCount}},
                               @{N='ram_gb';E={[math]::Round($_.MemoryAssigned/1GB, 2)}},
                               @{N='uptime';E={$_.Uptime.ToString()}},
                               Status,
                               Notes,
                               Generation,
                               Path | ConvertTo-Json -Depth 2
        """
        
        result = await self._execute(script)
        
        if not result.success:
            raise HypervisorError(
                f"Failed to list VMs: {result.stderr}",
                {"host": self.host},
            )
        
        data = self._parse_json_output(result.stdout)
        
        if data is None:
            return []
        
        # Normaliser en liste
        if isinstance(data, dict):
            data = [data]
        
        vms = []
        for vm_data in data:
            vms.append(VMInfo(
                id=vm_data.get("id", ""),
                name=vm_data.get("Name", ""),
                state=str(vm_data.get("State", "Unknown")),
                cpu_count=vm_data.get("cpu_count", 0),
                ram_gb=vm_data.get("ram_gb", 0),
                uptime=vm_data.get("uptime"),
                status=vm_data.get("Status"),
                notes=vm_data.get("Notes"),
                generation=vm_data.get("Generation", 2),
                path=vm_data.get("Path"),
            ))
        
        logger.info("hyperv_vms_listed", count=len(vms), host=self.host)
        return vms

    async def get_vm(self, vm_id: str) -> VMInfo | None:
        """Récupère les informations d'une VM par son nom ou ID."""
        # Essayer par nom d'abord, puis par VMID
        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            $vm | Select-Object @{{N='id';E={{$_.VMId.ToString()}}}},
                               Name,
                               State,
                               @{{N='cpu_count';E={{$_.ProcessorCount}}}},
                               @{{N='ram_gb';E={{[math]::Round($_.MemoryAssigned/1GB, 2)}}}},
                               @{{N='uptime';E={{$_.Uptime.ToString()}}}},
                               Status,
                               Notes,
                               Generation,
                               Path | ConvertTo-Json
        }}
        """
        
        result = await self._execute(script)
        
        if not result.success:
            logger.warning(
                "hyperv_get_vm_failed",
                vm_id=vm_id,
                error=result.stderr,
            )
            return None
        
        data = self._parse_json_output(result.stdout)
        
        if data is None:
            return None
        
        return VMInfo(
            id=data.get("id", ""),
            name=data.get("Name", ""),
            state=str(data.get("State", "Unknown")),
            cpu_count=data.get("cpu_count", 0),
            ram_gb=data.get("ram_gb", 0),
            uptime=data.get("uptime"),
            status=data.get("Status"),
            notes=data.get("Notes"),
            generation=data.get("Generation", 2),
            path=data.get("Path"),
        )

    async def create_vm(self, specs: VMSpecs) -> VMInfo:
        """Crée une nouvelle VM avec les spécifications données."""
        vm_path = specs.vm_path or self.vm_path
        vhdx_path = specs.vhdx_path or f"{self.vhdx_path}\\{specs.name}.vhdx"
        
        logger.info(
            "hyperv_creating_vm",
            name=specs.name,
            cpu=specs.cpu_count,
            ram_gb=specs.ram_gb,
            disk_gb=specs.disk_gb,
            generation=specs.generation,
        )
        
        # Script de création de VM
        script = f"""
        $ErrorActionPreference = 'Stop'
        
        # Créer la VM
        $vm = New-VM -Name '{specs.name}' `
            -Generation {specs.generation} `
            -MemoryStartupBytes {specs.ram_gb}GB `
            -Path '{vm_path}' `
            -NewVHDPath '{vhdx_path}' `
            -NewVHDSizeBytes {specs.disk_gb}GB `
            -SwitchName '{specs.network_switch}'
        
        # Configurer le processeur
        Set-VMProcessor -VM $vm -Count {specs.cpu_count}
        
        # Configurer le VLAN si spécifié
        {f"Set-VMNetworkAdapterVlan -VM $vm -Access -VlanId {specs.vlan_id}" if specs.vlan_id else ""}
        
        # Ajouter un lecteur DVD si ISO spécifié
        {f"Add-VMDvdDrive -VM $vm -Path '{specs.iso_path}'" if specs.iso_path else "Add-VMDvdDrive -VM $vm"}
        
        # Retourner les infos de la VM créée
        $vm | Select-Object @{{N='id';E={{$_.VMId.ToString()}}}},
                           Name,
                           State,
                           @{{N='cpu_count';E={{$_.ProcessorCount}}}},
                           @{{N='ram_gb';E={{[math]::Round($_.MemoryStartupBytes/1GB, 2)}}}},
                           Generation,
                           Path | ConvertTo-Json
        """
        
        result = await self._execute(script, timeout=settings.vm_creation_timeout)
        
        if not result.success:
            raise VMCreationError(
                specs.name,
                result.stderr or "Unknown error during VM creation",
            )
        
        data = self._parse_json_output(result.stdout)
        
        if data is None:
            raise VMCreationError(specs.name, "No VM data returned after creation")
        
        vm_info = VMInfo(
            id=data.get("id", ""),
            name=data.get("Name", specs.name),
            state=str(data.get("State", "Off")),
            cpu_count=data.get("cpu_count", specs.cpu_count),
            ram_gb=data.get("ram_gb", specs.ram_gb),
            generation=data.get("Generation", specs.generation),
            path=data.get("Path"),
        )
        
        logger.info(
            "hyperv_vm_created",
            vm_id=vm_info.id,
            name=vm_info.name,
        )
        
        return vm_info

    async def delete_vm(self, vm_id: str, delete_disks: bool = False) -> bool:
        """Supprime une VM."""
        logger.info(
            "hyperv_deleting_vm",
            vm_id=vm_id,
            delete_disks=delete_disks,
        )
        
        script = f"""
        $ErrorActionPreference = 'Stop'
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        
        if (-not $vm) {{
            throw "VM not found: {vm_id}"
        }}
        
        # Arrêter la VM si elle tourne
        if ($vm.State -eq 'Running') {{
            Stop-VM -VM $vm -Force -TurnOff
        }}
        
        {"# Récupérer les chemins des disques avant suppression" if delete_disks else ""}
        {'''$disks = Get-VMHardDiskDrive -VM $vm | Select-Object -ExpandProperty Path''' if delete_disks else ""}
        
        # Supprimer la VM
        Remove-VM -VM $vm -Force
        
        {"# Supprimer les disques" if delete_disks else ""}
        {'''foreach ($disk in $disks) { Remove-Item -Path $disk -Force -ErrorAction SilentlyContinue }''' if delete_disks else ""}
        
        Write-Output "VM deleted successfully"
        """
        
        result = await self._execute(script)
        
        if not result.success:
            raise VMOperationError(vm_id, "delete", result.stderr)
        
        logger.info("hyperv_vm_deleted", vm_id=vm_id)
        return True

    async def start_vm(self, vm_id: str) -> bool:
        """Démarre une VM."""
        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            Start-VM -VM $vm
            Write-Output "VM started"
        }} else {{
            throw "VM not found"
        }}
        """
        
        result = await self._execute(script)
        
        if not result.success:
            raise VMOperationError(vm_id, "start", result.stderr)
        
        logger.info("hyperv_vm_started", vm_id=vm_id)
        return True

    async def stop_vm(self, vm_id: str, force: bool = False) -> bool:
        """Arrête une VM."""
        force_param = "-TurnOff" if force else ""
        
        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            Stop-VM -VM $vm -Force {force_param}
            Write-Output "VM stopped"
        }} else {{
            throw "VM not found"
        }}
        """
        
        result = await self._execute(script)
        
        if not result.success:
            raise VMOperationError(vm_id, "stop", result.stderr)
        
        logger.info("hyperv_vm_stopped", vm_id=vm_id, force=force)
        return True

    async def restart_vm(self, vm_id: str, force: bool = False) -> bool:
        """Redémarre une VM."""
        force_param = "-Force" if force else ""
        
        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            Restart-VM -VM $vm {force_param}
            Write-Output "VM restarted"
        }} else {{
            throw "VM not found"
        }}
        """
        
        result = await self._execute(script)
        
        if not result.success:
            raise VMOperationError(vm_id, "restart", result.stderr)
        
        logger.info("hyperv_vm_restarted", vm_id=vm_id, force=force)
        return True

    async def get_vm_state(self, vm_id: str) -> str | None:
        """Récupère l'état d'une VM."""
        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            Write-Output $vm.State
        }}
        """
        
        result = await self._execute(script)
        
        if result.success and result.stdout:
            return result.stdout.strip()
        return None

    async def list_switches(self) -> list[VirtualSwitch]:
        """Liste les switches virtuels."""
        script = """
        Get-VMSwitch | Select-Object Name,
                                     @{N='switch_type';E={$_.SwitchType.ToString()}},
                                     @{N='interface_description';E={$_.NetAdapterInterfaceDescription}},
                                     Notes | ConvertTo-Json
        """
        
        result = await self._execute(script)
        
        if not result.success:
            raise HypervisorError(
                f"Failed to list switches: {result.stderr}",
                {"host": self.host},
            )
        
        data = self._parse_json_output(result.stdout)
        
        if data is None:
            return []
        
        if isinstance(data, dict):
            data = [data]
        
        switches = []
        for sw_data in data:
            switches.append(VirtualSwitch(
                name=sw_data.get("Name", ""),
                switch_type=sw_data.get("switch_type", "Unknown"),
                interface_description=sw_data.get("interface_description"),
                notes=sw_data.get("Notes"),
            ))
        
        logger.info("hyperv_switches_listed", count=len(switches))
        return switches

    async def list_physical_adapters(self) -> list[dict[str, Any]]:
        """Liste les adaptateurs réseau physiques disponibles pour créer des switches externes."""
        script = """
        Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and $_.Virtual -eq $false } |
        Select-Object Name, InterfaceDescription, Status, LinkSpeed, MacAddress |
        ConvertTo-Json
        """
        
        result = await self._execute(script)
        
        if not result.success:
            logger.warning("Failed to list physical adapters", error=result.stderr)
            return []
        
        data = self._parse_json_output(result.stdout)
        
        if data is None:
            return []
        
        if isinstance(data, dict):
            data = [data]
        
        adapters = []
        for adapter in data:
            adapters.append({
                "name": adapter.get("Name", ""),
                "description": adapter.get("InterfaceDescription", ""),
                "status": adapter.get("Status", ""),
                "link_speed": adapter.get("LinkSpeed", ""),
                "mac_address": adapter.get("MacAddress", ""),
            })
        
        logger.info("hyperv_physical_adapters_listed", count=len(adapters))
        return adapters

    async def create_switch(
        self,
        name: str,
        switch_type: str,
        net_adapter_name: str | None = None,
        allow_management_os: bool = True,
        notes: str | None = None,
    ) -> VirtualSwitch:
        """
        Crée un nouveau switch virtuel.
        
        Args:
            name: Nom du switch
            switch_type: Type de switch ('Internal', 'External', 'Private')
            net_adapter_name: Nom de l'adaptateur réseau (requis pour External)
            allow_management_os: Permettre à l'OS hôte d'utiliser l'adaptateur (External uniquement)
            notes: Notes/description du switch
            
        Returns:
            VirtualSwitch créé
        """
        # Valider le type
        valid_types = ["Internal", "External", "Private"]
        if switch_type not in valid_types:
            raise HypervisorError(
                f"Invalid switch type '{switch_type}'. Must be one of: {valid_types}",
                {"switch_type": switch_type},
            )
        
        # Construire la commande
        if switch_type == "External":
            if not net_adapter_name:
                raise HypervisorError(
                    "net_adapter_name is required for External switch",
                    {"switch_type": switch_type},
                )
            mgmt_param = "-AllowManagementOS $true" if allow_management_os else "-AllowManagementOS $false"
            script = f"""
            $switch = New-VMSwitch -Name '{name}' -NetAdapterName '{net_adapter_name}' {mgmt_param}
            {f"Set-VMSwitch -VMSwitch $switch -Notes '{notes}'" if notes else ""}
            Get-VMSwitch -Name '{name}' | Select-Object Name,
                @{{N='switch_type';E={{$_.SwitchType.ToString()}}}},
                @{{N='interface_description';E={{$_.NetAdapterInterfaceDescription}}}},
                Notes | ConvertTo-Json
            """
        else:
            script = f"""
            $switch = New-VMSwitch -Name '{name}' -SwitchType {switch_type}
            {f"Set-VMSwitch -VMSwitch $switch -Notes '{notes}'" if notes else ""}
            Get-VMSwitch -Name '{name}' | Select-Object Name,
                @{{N='switch_type';E={{$_.SwitchType.ToString()}}}},
                @{{N='interface_description';E={{$_.NetAdapterInterfaceDescription}}}},
                Notes | ConvertTo-Json
            """
        
        result = await self._execute(script)
        
        if not result.success:
            raise HypervisorError(
                f"Failed to create switch '{name}': {result.stderr}",
                {"name": name, "switch_type": switch_type},
            )
        
        data = self._parse_json_output(result.stdout)
        
        if not data:
            raise HypervisorError(
                f"Failed to create switch '{name}': No data returned",
                {"name": name},
            )
        
        switch = VirtualSwitch(
            name=data.get("Name", name),
            switch_type=data.get("switch_type", switch_type),
            interface_description=data.get("interface_description"),
            notes=data.get("Notes"),
        )
        
        logger.info(
            "hyperv_switch_created",
            name=name,
            switch_type=switch_type,
        )
        return switch

    async def delete_switch(self, name: str) -> bool:
        """Supprime un switch virtuel."""
        script = f"""
        $switch = Get-VMSwitch -Name '{name}' -ErrorAction SilentlyContinue
        if ($switch) {{
            Remove-VMSwitch -VMSwitch $switch -Force
            Write-Output "Switch deleted"
        }} else {{
            throw "Switch '{name}' not found"
        }}
        """
        
        result = await self._execute(script)
        
        if not result.success:
            raise HypervisorError(
                f"Failed to delete switch '{name}': {result.stderr}",
                {"name": name},
            )
        
        logger.info("hyperv_switch_deleted", name=name)
        return True

    async def mount_iso(self, vm_id: str, iso_path: str) -> bool:
        """Monte une ISO sur le lecteur DVD d'une VM."""
        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            $dvd = Get-VMDvdDrive -VM $vm
            if (-not $dvd) {{
                Add-VMDvdDrive -VM $vm -Path '{iso_path}'
            }} else {{
                Set-VMDvdDrive -VMDvdDrive $dvd[0] -Path '{iso_path}'
            }}
            Write-Output "ISO mounted"
        }} else {{
            throw "VM not found"
        }}
        """
        
        result = await self._execute(script)
        
        if not result.success:
            raise VMOperationError(vm_id, "mount_iso", result.stderr)
        
        logger.info("hyperv_iso_mounted", vm_id=vm_id, iso_path=iso_path)
        return True

    async def unmount_iso(self, vm_id: str, unmount_all: bool = True) -> bool:
        """
        Démonte les ISOs des lecteurs DVD.
        
        Args:
            vm_id: ID ou nom de la VM
            unmount_all: Si True, démonte tous les lecteurs DVD. Sinon, juste le premier.
        """
        if unmount_all:
            script = f"""
            $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
            if (-not $vm) {{
                $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
            }}
            if ($vm) {{
                $count = 0
                Get-VMDvdDrive -VM $vm | ForEach-Object {{
                    if ($_.Path) {{
                        Set-VMDvdDrive -VMName $vm.Name -ControllerNumber $_.ControllerNumber -ControllerLocation $_.ControllerLocation -Path $null
                        $count++
                    }}
                }}
                Write-Output "$count ISOs unmounted"
            }} else {{
                throw "VM not found"
            }}
            """
        else:
            script = f"""
            $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
            if (-not $vm) {{
                $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
            }}
            if ($vm) {{
                $dvd = Get-VMDvdDrive -VM $vm | Select-Object -First 1
                if ($dvd -and $dvd.Path) {{
                    Set-VMDvdDrive -VMDvdDrive $dvd -Path $null
                }}
                Write-Output "ISO unmounted"
            }} else {{
                throw "VM not found"
            }}
            """
        
        result = await self._execute(script)
        
        if not result.success:
            raise VMOperationError(vm_id, "unmount_iso", result.stderr)
        
        logger.info("hyperv_iso_unmounted", vm_id=vm_id, unmount_all=unmount_all)
        return True

    async def enable_guest_services(self, vm_id: str) -> bool:
        """
        Active le Guest Service Interface (copie de fichiers hôte -> VM).
        
        Args:
            vm_id: ID ou nom de la VM
        """
        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            # Rechercher le service Guest (nom peut varier selon la langue)
            $guestSvc = Get-VMIntegrationService -VM $vm | Where-Object {{ 
                $_.Name -like "*invit*" -or $_.Name -like "*Guest*" 
            }}
            if ($guestSvc) {{
                Enable-VMIntegrationService -VM $vm -Name $guestSvc.Name
                Write-Output "Guest Service enabled: $($guestSvc.Name)"
            }} else {{
                Write-Output "Guest Service not found"
            }}
        }} else {{
            throw "VM not found"
        }}
        """
        
        result = await self._execute(script)
        
        if not result.success:
            raise VMOperationError(vm_id, "enable_guest_services", result.stderr)
        
        logger.info("hyperv_guest_services_enabled", vm_id=vm_id)
        return True

    async def set_first_boot_device(
        self,
        vm_id: str,
        device_type: str = "HardDrive",
    ) -> bool:
        """
        Configure le premier périphérique de boot d'une VM Gen2.
        
        Args:
            vm_id: ID ou nom de la VM
            device_type: Type de périphérique (HardDrive, DVD, Network)
        """
        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            if ($vm.Generation -eq 2) {{
                $device = $null
                switch ('{device_type}') {{
                    'HardDrive' {{ 
                        $device = Get-VMHardDiskDrive -VM $vm | Select-Object -First 1
                    }}
                    'DVD' {{ 
                        $device = Get-VMDvdDrive -VM $vm | Select-Object -First 1
                    }}
                    'Network' {{ 
                        $device = Get-VMNetworkAdapter -VM $vm | Select-Object -First 1
                    }}
                }}
                
                if ($device) {{
                    Set-VMFirmware -VM $vm -FirstBootDevice $device
                    Write-Output "First boot device set to {device_type}"
                }} else {{
                    throw "Device type {device_type} not found"
                }}
            }} else {{
                Write-Output "Gen1 VM - use BIOS settings"
            }}
        }} else {{
            throw "VM not found"
        }}
        """
        
        result = await self._execute(script)
        
        if not result.success:
            raise VMOperationError(vm_id, "set_first_boot_device", result.stderr)
        
        logger.info(
            "hyperv_first_boot_device_set",
            vm_id=vm_id,
            device_type=device_type,
        )
        return True

    async def cleanup_post_install(self, vm_id: str) -> dict[str, bool]:
        """
        Effectue le nettoyage post-installation d'une VM.
        
        Actions:
        - Démonte tous les ISOs
        - Configure le boot sur le disque dur
        - Active les Guest Services
        
        Args:
            vm_id: ID ou nom de la VM
            
        Returns:
            Dictionnaire avec le résultat de chaque action
        """
        results = {
            "unmount_isos": False,
            "set_boot_device": False,
            "enable_guest_services": False,
        }
        
        logger.info("hyperv_cleanup_post_install_start", vm_id=vm_id)
        
        try:
            await self.unmount_iso(vm_id, unmount_all=True)
            results["unmount_isos"] = True
        except Exception as e:
            logger.warning(
                "hyperv_cleanup_unmount_failed",
                vm_id=vm_id,
                error=str(e),
            )
        
        try:
            await self.set_first_boot_device(vm_id, "HardDrive")
            results["set_boot_device"] = True
        except Exception as e:
            logger.warning(
                "hyperv_cleanup_boot_failed",
                vm_id=vm_id,
                error=str(e),
            )
        
        try:
            await self.enable_guest_services(vm_id)
            results["enable_guest_services"] = True
        except Exception as e:
            logger.warning(
                "hyperv_cleanup_guest_services_failed",
                vm_id=vm_id,
                error=str(e),
            )
        
        logger.info(
            "hyperv_cleanup_post_install_complete",
            vm_id=vm_id,
            results=results,
        )
        
        return results

    async def set_boot_order(
        self,
        vm_id: str,
        boot_order: list[str],
    ) -> bool:
        """Configure l'ordre de boot d'une VM Gen2."""
        # Mapping des noms de périphériques vers les objets PowerShell
        # boot_order peut contenir: "DVD", "HardDrive", "Network", "File"
        
        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            if ($vm.Generation -eq 2) {{
                $bootDevices = @()
                {"".join([f'''
                $dev = Get-VMFirmware -VM $vm | Select-Object -ExpandProperty BootOrder | Where-Object {{ $_.BootType -like '*{device}*' }} | Select-Object -First 1
                if ($dev) {{ $bootDevices += $dev }}
                ''' for device in boot_order])}
                
                if ($bootDevices.Count -gt 0) {{
                    Set-VMFirmware -VM $vm -BootOrder $bootDevices
                }}
                Write-Output "Boot order configured"
            }} else {{
                # Gen1 VMs use BIOS boot order
                Write-Output "Gen1 VM - BIOS boot order not modified"
            }}
        }} else {{
            throw "VM not found"
        }}
        """
        
        result = await self._execute(script)
        
        if not result.success:
            raise VMOperationError(vm_id, "set_boot_order", result.stderr)
        
        logger.info("hyperv_boot_order_set", vm_id=vm_id, boot_order=boot_order)
        return True

    def close(self) -> None:
        """Ferme les connexions."""
        if self._executor:
            self._executor.close()

    # =========================================================================
    # Méthodes de monitoring
    # =========================================================================

    async def get_vm_health(self, vm_id: str) -> VMHealthStatus | None:
        """Récupère l'état de santé complet d'une VM."""
        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            $intServices = Get-VMIntegrationService -VM $vm | Select-Object Name, Enabled, 
                @{{N='Status';E={{$_.PrimaryOperationalStatus.ToString()}}}}
            
            $nic = Get-VMNetworkAdapter -VM $vm
            
            @{{
                VMName = $vm.Name
                State = $vm.State.ToString()
                Heartbeat = $vm.Heartbeat.ToString()
                Uptime = $vm.Uptime.ToString()
                CPUUsage = $vm.CPUUsage
                MemoryMB = [math]::Round($vm.MemoryAssigned/1MB)
                IPAddresses = $nic.IPAddresses
                IntegrationServices = $intServices | ForEach-Object {{
                    @{{
                        Name = $_.Name
                        Enabled = $_.Enabled
                        Status = $_.Status
                    }}
                }}
            }} | ConvertTo-Json -Depth 3
        }}
        """
        
        result = await self._execute(script)
        
        if not result.success:
            logger.warning(
                "hyperv_get_vm_health_failed",
                vm_id=vm_id,
                error=result.stderr,
            )
            return None
        
        data = self._parse_json_output(result.stdout)
        
        if data is None:
            return None
        
        # Parser les services d'intégration
        int_services = []
        for svc in data.get("IntegrationServices", []):
            if svc:
                int_services.append(IntegrationService(
                    name=svc.get("Name", ""),
                    enabled=svc.get("Enabled", False),
                    status=svc.get("Status", "Unknown"),
                ))
        
        # Parser les adresses IP (peut être une string ou une liste)
        ip_addresses = data.get("IPAddresses", [])
        if isinstance(ip_addresses, str):
            ip_addresses = [ip_addresses] if ip_addresses else []
        
        return VMHealthStatus(
            vm_name=data.get("VMName", vm_id),
            state=data.get("State", "Unknown"),
            heartbeat=data.get("Heartbeat", "Unknown"),
            uptime=data.get("Uptime"),
            cpu_usage=data.get("CPUUsage", 0),
            memory_mb=data.get("MemoryMB", 0),
            ip_addresses=ip_addresses,
            integration_services=int_services,
        )

    async def get_vm_heartbeat(self, vm_id: str) -> str | None:
        """Récupère le statut heartbeat d'une VM."""
        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            Write-Output $vm.Heartbeat.ToString()
        }}
        """
        
        result = await self._execute(script)
        
        if result.success and result.stdout:
            heartbeat = result.stdout.strip()
            logger.debug("hyperv_heartbeat", vm_id=vm_id, heartbeat=heartbeat)
            return heartbeat
        return None

    async def get_vm_integration_services(
        self,
        vm_id: str,
    ) -> list[IntegrationService]:
        """Récupère la liste des services d'intégration d'une VM."""
        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            Get-VMIntegrationService -VM $vm | Select-Object Name, Enabled, 
                @{{N='Status';E={{$_.PrimaryOperationalStatus.ToString()}}}} | ConvertTo-Json
        }}
        """
        
        result = await self._execute(script)
        
        if not result.success:
            logger.warning(
                "hyperv_get_integration_services_failed",
                vm_id=vm_id,
                error=result.stderr,
            )
            return []
        
        data = self._parse_json_output(result.stdout)
        
        if data is None:
            return []
        
        if isinstance(data, dict):
            data = [data]
        
        services = []
        for svc in data:
            services.append(IntegrationService(
                name=svc.get("Name", ""),
                enabled=svc.get("Enabled", False),
                status=svc.get("Status", "Unknown"),
            ))
        
        logger.info(
            "hyperv_integration_services_listed",
            vm_id=vm_id,
            count=len(services),
        )
        return services

    async def get_vm_ip_addresses(self, vm_id: str) -> list[str]:
        """Récupère les adresses IP d'une VM."""
        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            $nic = Get-VMNetworkAdapter -VM $vm
            $nic.IPAddresses | ConvertTo-Json
        }}
        """
        
        result = await self._execute(script)
        
        if not result.success:
            return []
        
        data = self._parse_json_output(result.stdout)
        
        if data is None:
            return []
        
        if isinstance(data, str):
            return [data] if data else []
        
        return list(data) if data else []

    async def execute_in_vm(
        self,
        vm_id: str,
        script: str,
        vm_credentials: tuple[str, str],
        timeout: int = 300,
    ) -> PowerShellDirectResult:
        """
        Exécute un script PowerShell dans une VM via PowerShell Direct.
        
        Args:
            vm_id: ID ou nom de la VM
            script: Script PowerShell à exécuter
            vm_credentials: Tuple (username, password) pour la VM
            timeout: Timeout en secondes
        """
        import base64
        
        username, password = vm_credentials
        
        # Encoder le script en Base64 pour éviter les problèmes d'échappement
        script_bytes = script.encode("utf-16-le")
        script_b64 = base64.b64encode(script_bytes).decode("ascii")
        
        ps_script = f"""
        $ErrorActionPreference = 'Stop'
        $vmName = '{vm_id}'
        $cred = New-Object System.Management.Automation.PSCredential(
            '{username}',
            (ConvertTo-SecureString '{password}' -AsPlainText -Force)
        )
        
        # Décoder le script Base64
        $scriptB64 = '{script_b64}'
        $scriptBytes = [Convert]::FromBase64String($scriptB64)
        $scriptText = [System.Text.Encoding]::Unicode.GetString($scriptBytes)
        
        try {{
            $result = Invoke-Command -VMName $vmName -Credential $cred -ScriptBlock {{
                param($code)
                Invoke-Expression $code
            }} -ArgumentList $scriptText -ErrorAction Stop
            
            @{{
                Success = $true
                Output = $result
                Error = $null
            }} | ConvertTo-Json -Depth 5
        }} catch {{
            @{{
                Success = $false
                Output = $null
                Error = $_.Exception.Message
            }} | ConvertTo-Json -Depth 5
        }}
        """
        
        logger.info(
            "hyperv_execute_in_vm",
            vm_id=vm_id,
            script_length=len(script),
        )
        
        result = await self._execute(ps_script, timeout=timeout)
        
        if not result.success:
            return PowerShellDirectResult(
                success=False,
                output=None,
                error=result.stderr or "PowerShell execution failed",
            )
        
        data = self._parse_json_output(result.stdout)
        
        if data is None:
            return PowerShellDirectResult(
                success=False,
                output=None,
                error="Failed to parse PowerShell Direct result",
            )
        
        return PowerShellDirectResult(
            success=data.get("Success", False),
            output=data.get("Output"),
            error=data.get("Error"),
        )

    async def wait_for_vm_ready(
        self,
        vm_id: str,
        vm_credentials: tuple[str, str] | None = None,
        timeout: int = 600,
        check_interval: int = 10,
    ) -> bool:
        """
        Attend qu'une VM soit prête (heartbeat OK et optionnellement accessible).
        
        Args:
            vm_id: ID ou nom de la VM
            vm_credentials: Credentials pour tester l'accès PowerShell Direct
            timeout: Timeout total en secondes
            check_interval: Intervalle entre les vérifications
        """
        import asyncio
        import time
        
        start_time = time.time()
        
        logger.info(
            "hyperv_waiting_for_vm",
            vm_id=vm_id,
            timeout=timeout,
            with_credentials=vm_credentials is not None,
        )
        
        while (time.time() - start_time) < timeout:
            try:
                # Vérifier le heartbeat
                heartbeat = await self.get_vm_heartbeat(vm_id)
                
                if heartbeat in ("OkApplicationsHealthy", "OkApplicationsUnknown"):
                    logger.info(
                        "hyperv_vm_heartbeat_ok",
                        vm_id=vm_id,
                        heartbeat=heartbeat,
                    )
                    
                    # Si des credentials sont fournis, tester PowerShell Direct
                    if vm_credentials:
                        result = await self.execute_in_vm(
                            vm_id,
                            "$env:COMPUTERNAME",
                            vm_credentials,
                            timeout=30,
                        )
                        
                        if result.success:
                            logger.info(
                                "hyperv_vm_ready",
                                vm_id=vm_id,
                                hostname=result.output,
                            )
                            return True
                        else:
                            logger.debug(
                                "hyperv_ps_direct_not_ready",
                                vm_id=vm_id,
                                error=result.error,
                            )
                    else:
                        # Pas de credentials, heartbeat OK suffit
                        return True
                else:
                    logger.debug(
                        "hyperv_vm_not_ready",
                        vm_id=vm_id,
                        heartbeat=heartbeat,
                    )
                
            except Exception as e:
                logger.debug(
                    "hyperv_wait_check_failed",
                    vm_id=vm_id,
                    error=str(e),
                )
            
            await asyncio.sleep(check_interval)
        
        logger.warning(
            "hyperv_vm_ready_timeout",
            vm_id=vm_id,
            timeout=timeout,
        )
        return False

    # =========================================================================
    # Gestion VLAN (2.2.3)
    # =========================================================================

    async def set_vm_vlan(
        self,
        vm_id: str,
        vlan_id: int,
        adapter_name: str | None = None,
    ) -> bool:
        """
        Configure le VLAN sur un adaptateur réseau d'une VM.

        Args:
            vm_id: ID ou nom de la VM
            vlan_id: ID du VLAN (1-4094)
            adapter_name: Nom de l'adaptateur (si None, applique au premier)
        """
        if adapter_name:
            script = f"""
            $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
            if (-not $vm) {{
                $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
            }}
            if ($vm) {{
                $nic = Get-VMNetworkAdapter -VM $vm | Where-Object {{ $_.Name -eq '{adapter_name}' }}
                if ($nic) {{
                    Set-VMNetworkAdapterVlan -VMNetworkAdapter $nic -Access -VlanId {vlan_id}
                    Write-Output "VLAN {vlan_id} set on adapter {adapter_name}"
                }} else {{
                    throw "Adapter '{adapter_name}' not found"
                }}
            }} else {{
                throw "VM not found"
            }}
            """
        else:
            script = f"""
            $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
            if (-not $vm) {{
                $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
            }}
            if ($vm) {{
                Set-VMNetworkAdapterVlan -VM $vm -Access -VlanId {vlan_id}
                Write-Output "VLAN {vlan_id} set"
            }} else {{
                throw "VM not found"
            }}
            """

        result = await self._execute(script)

        if not result.success:
            raise VMOperationError(vm_id, "set_vlan", result.stderr)

        logger.info("hyperv_vlan_set", vm_id=vm_id, vlan_id=vlan_id, adapter=adapter_name)
        return True

    async def remove_vm_vlan(
        self,
        vm_id: str,
        adapter_name: str | None = None,
    ) -> bool:
        """
        Supprime la configuration VLAN d'un adaptateur.

        Args:
            vm_id: ID ou nom de la VM
            adapter_name: Nom de l'adaptateur (si None, applique à tous)
        """
        if adapter_name:
            script = f"""
            $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
            if (-not $vm) {{
                $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
            }}
            if ($vm) {{
                $nic = Get-VMNetworkAdapter -VM $vm | Where-Object {{ $_.Name -eq '{adapter_name}' }}
                if ($nic) {{
                    Set-VMNetworkAdapterVlan -VMNetworkAdapter $nic -Untagged
                    Write-Output "VLAN removed from adapter {adapter_name}"
                }}
            }} else {{
                throw "VM not found"
            }}
            """
        else:
            script = f"""
            $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
            if (-not $vm) {{
                $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
            }}
            if ($vm) {{
                Set-VMNetworkAdapterVlan -VM $vm -Untagged
                Write-Output "VLAN removed"
            }} else {{
                throw "VM not found"
            }}
            """

        result = await self._execute(script)

        if not result.success:
            raise VMOperationError(vm_id, "remove_vlan", result.stderr)

        logger.info("hyperv_vlan_removed", vm_id=vm_id, adapter=adapter_name)
        return True

    async def get_vm_vlan(
        self,
        vm_id: str,
        adapter_name: str | None = None,
    ) -> int | None:
        """
        Récupère l'ID VLAN configuré sur un adaptateur.

        Args:
            vm_id: ID ou nom de la VM
            adapter_name: Nom de l'adaptateur

        Returns:
            ID du VLAN ou None si non configuré
        """
        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            $nics = Get-VMNetworkAdapter -VM $vm
            {f"$nics = $nics | Where-Object {{ $_.Name -eq '{adapter_name}' }}" if adapter_name else ""}
            $nic = $nics | Select-Object -First 1
            if ($nic) {{
                $vlan = Get-VMNetworkAdapterVlan -VMNetworkAdapter $nic
                if ($vlan.AccessVlanId -gt 0) {{
                    Write-Output $vlan.AccessVlanId
                }}
            }}
        }}
        """

        result = await self._execute(script)

        if result.success and result.stdout.strip():
            try:
                return int(result.stdout.strip())
            except ValueError:
                return None
        return None

    # =========================================================================
    # Support multi-NIC (2.2.5)
    # =========================================================================

    async def list_network_adapters(self, vm_id: str) -> list[NetworkAdapterInfo]:
        """
        Liste tous les adaptateurs réseau d'une VM.

        Args:
            vm_id: ID ou nom de la VM

        Returns:
            Liste des adaptateurs réseau
        """
        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            Get-VMNetworkAdapter -VM $vm | ForEach-Object {{
                $vlan = Get-VMNetworkAdapterVlan -VMNetworkAdapter $_
                @{{
                    Name = $_.Name
                    SwitchName = $_.SwitchName
                    MacAddress = $_.MacAddress
                    VlanId = if ($vlan.AccessVlanId -gt 0) {{ $vlan.AccessVlanId }} else {{ $null }}
                    IPAddresses = $_.IPAddresses
                    IsManagementOs = $_.IsManagementOs
                }}
            }} | ConvertTo-Json -Depth 2
        }}
        """

        result = await self._execute(script)

        if not result.success:
            raise HypervisorError(
                f"Failed to list network adapters: {result.stderr}",
                {"vm_id": vm_id},
            )

        data = self._parse_json_output(result.stdout)

        if data is None:
            return []

        if isinstance(data, dict):
            data = [data]

        adapters = []
        for nic_data in data:
            ip_addresses = nic_data.get("IPAddresses", [])
            if isinstance(ip_addresses, str):
                ip_addresses = [ip_addresses] if ip_addresses else []

            adapters.append(NetworkAdapterInfo(
                name=nic_data.get("Name", ""),
                switch_name=nic_data.get("SwitchName"),
                mac_address=nic_data.get("MacAddress"),
                vlan_id=nic_data.get("VlanId"),
                ip_addresses=ip_addresses or [],
                is_management_os=nic_data.get("IsManagementOs", False),
            ))

        logger.info("hyperv_network_adapters_listed", vm_id=vm_id, count=len(adapters))
        return adapters

    async def add_network_adapter(
        self,
        vm_id: str,
        switch_name: str,
        adapter_name: str | None = None,
        vlan_id: int | None = None,
        static_mac: str | None = None,
    ) -> NetworkAdapterInfo:
        """
        Ajoute un adaptateur réseau à une VM.

        Args:
            vm_id: ID ou nom de la VM
            switch_name: Nom du switch virtuel
            adapter_name: Nom de l'adaptateur (généré automatiquement si None)
            vlan_id: ID VLAN optionnel
            static_mac: Adresse MAC statique optionnelle

        Returns:
            Informations sur l'adaptateur créé
        """
        name_param = f"-Name '{adapter_name}'" if adapter_name else ""
        mac_param = f"-StaticMacAddress '{static_mac}'" if static_mac else ""

        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            $nic = Add-VMNetworkAdapter -VM $vm -SwitchName '{switch_name}' {name_param} {mac_param} -Passthru
            {f"Set-VMNetworkAdapterVlan -VMNetworkAdapter $nic -Access -VlanId {vlan_id}" if vlan_id else ""}
            $vlan = Get-VMNetworkAdapterVlan -VMNetworkAdapter $nic
            @{{
                Name = $nic.Name
                SwitchName = $nic.SwitchName
                MacAddress = $nic.MacAddress
                VlanId = if ($vlan.AccessVlanId -gt 0) {{ $vlan.AccessVlanId }} else {{ $null }}
            }} | ConvertTo-Json
        }} else {{
            throw "VM not found"
        }}
        """

        result = await self._execute(script)

        if not result.success:
            raise VMOperationError(vm_id, "add_network_adapter", result.stderr)

        data = self._parse_json_output(result.stdout)

        if data is None:
            raise VMOperationError(vm_id, "add_network_adapter", "No adapter data returned")

        adapter = NetworkAdapterInfo(
            name=data.get("Name", ""),
            switch_name=data.get("SwitchName"),
            mac_address=data.get("MacAddress"),
            vlan_id=data.get("VlanId"),
        )

        logger.info(
            "hyperv_network_adapter_added",
            vm_id=vm_id,
            adapter_name=adapter.name,
            switch=switch_name,
        )
        return adapter

    async def remove_network_adapter(
        self,
        vm_id: str,
        adapter_name: str,
    ) -> bool:
        """
        Supprime un adaptateur réseau d'une VM.

        Args:
            vm_id: ID ou nom de la VM
            adapter_name: Nom de l'adaptateur à supprimer

        Returns:
            True si supprimé
        """
        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            $nic = Get-VMNetworkAdapter -VM $vm | Where-Object {{ $_.Name -eq '{adapter_name}' }}
            if ($nic) {{
                Remove-VMNetworkAdapter -VMNetworkAdapter $nic
                Write-Output "Adapter removed"
            }} else {{
                throw "Adapter '{adapter_name}' not found"
            }}
        }} else {{
            throw "VM not found"
        }}
        """

        result = await self._execute(script)

        if not result.success:
            raise VMOperationError(vm_id, "remove_network_adapter", result.stderr)

        logger.info("hyperv_network_adapter_removed", vm_id=vm_id, adapter_name=adapter_name)
        return True

    async def connect_network_adapter(
        self,
        vm_id: str,
        adapter_name: str,
        switch_name: str,
    ) -> bool:
        """
        Connecte un adaptateur à un switch.

        Args:
            vm_id: ID ou nom de la VM
            adapter_name: Nom de l'adaptateur
            switch_name: Nom du switch

        Returns:
            True si connecté
        """
        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            $nic = Get-VMNetworkAdapter -VM $vm | Where-Object {{ $_.Name -eq '{adapter_name}' }}
            if ($nic) {{
                Connect-VMNetworkAdapter -VMNetworkAdapter $nic -SwitchName '{switch_name}'
                Write-Output "Adapter connected"
            }} else {{
                throw "Adapter '{adapter_name}' not found"
            }}
        }} else {{
            throw "VM not found"
        }}
        """

        result = await self._execute(script)

        if not result.success:
            raise VMOperationError(vm_id, "connect_network_adapter", result.stderr)

        logger.info(
            "hyperv_network_adapter_connected",
            vm_id=vm_id,
            adapter_name=adapter_name,
            switch=switch_name,
        )
        return True

    async def disconnect_network_adapter(
        self,
        vm_id: str,
        adapter_name: str,
    ) -> bool:
        """
        Déconnecte un adaptateur de son switch.

        Args:
            vm_id: ID ou nom de la VM
            adapter_name: Nom de l'adaptateur

        Returns:
            True si déconnecté
        """
        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            $nic = Get-VMNetworkAdapter -VM $vm | Where-Object {{ $_.Name -eq '{adapter_name}' }}
            if ($nic) {{
                Disconnect-VMNetworkAdapter -VMNetworkAdapter $nic
                Write-Output "Adapter disconnected"
            }} else {{
                throw "Adapter '{adapter_name}' not found"
            }}
        }} else {{
            throw "VM not found"
        }}
        """

        result = await self._execute(script)

        if not result.success:
            raise VMOperationError(vm_id, "disconnect_network_adapter", result.stderr)

        logger.info("hyperv_network_adapter_disconnected", vm_id=vm_id, adapter_name=adapter_name)
        return True

    # =========================================================================
    # Support multi-disques (2.3.4)
    # =========================================================================

    async def list_hard_disks(self, vm_id: str) -> list[DiskInfo]:
        """
        Liste tous les disques durs attachés à une VM.

        Args:
            vm_id: ID ou nom de la VM

        Returns:
            Liste des disques
        """
        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            Get-VMHardDiskDrive -VM $vm | ForEach-Object {{
                $vhd = Get-VHD -Path $_.Path -ErrorAction SilentlyContinue
                @{{
                    Path = $_.Path
                    ControllerNumber = $_.ControllerNumber
                    ControllerLocation = $_.ControllerLocation
                    SizeGB = if ($vhd) {{ [math]::Round($vhd.Size/1GB, 2) }} else {{ 0 }}
                    Format = if ($vhd) {{ $vhd.VhdFormat.ToString() }} else {{ 'Unknown' }}
                    Type = if ($vhd) {{ $vhd.VhdType.ToString() }} else {{ 'Unknown' }}
                }}
            }} | ConvertTo-Json -Depth 2
        }}
        """

        result = await self._execute(script)

        if not result.success:
            raise HypervisorError(
                f"Failed to list hard disks: {result.stderr}",
                {"vm_id": vm_id},
            )

        data = self._parse_json_output(result.stdout)

        if data is None:
            return []

        if isinstance(data, dict):
            data = [data]

        disks = []
        for disk_data in data:
            disks.append(DiskInfo(
                path=disk_data.get("Path", ""),
                size_gb=disk_data.get("SizeGB", 0),
                format=disk_data.get("Format", "VHDX"),
                type=disk_data.get("Type", "Dynamic"),
                attached_to=vm_id,
                controller_number=disk_data.get("ControllerNumber", 0),
                controller_location=disk_data.get("ControllerLocation", 0),
            ))

        logger.info("hyperv_hard_disks_listed", vm_id=vm_id, count=len(disks))
        return disks

    async def add_hard_disk(
        self,
        vm_id: str,
        size_gb: int,
        vhdx_path: str | None = None,
        disk_type: str = "Dynamic",
    ) -> DiskInfo:
        """
        Ajoute un nouveau disque dur à une VM.

        Args:
            vm_id: ID ou nom de la VM
            size_gb: Taille du disque en GB
            vhdx_path: Chemin du fichier VHDX (généré automatiquement si None)
            disk_type: Type de disque ("Dynamic" ou "Fixed")

        Returns:
            Informations sur le disque créé
        """
        script = f"""
        $ErrorActionPreference = 'Stop'
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            # Déterminer le chemin du disque
            $vhdxPath = '{vhdx_path}'
            if (-not $vhdxPath) {{
                $vmPath = Split-Path $vm.Path
                $diskCount = (Get-VMHardDiskDrive -VM $vm).Count
                $vhdxPath = Join-Path $vmPath "$($vm.Name)_disk$($diskCount + 1).vhdx"
            }}

            # Créer le disque
            $vhdParams = @{{
                Path = $vhdxPath
                SizeBytes = {size_gb}GB
                {"Dynamic = $true" if disk_type == "Dynamic" else "Fixed = $true"}
            }}
            $vhd = New-VHD @vhdParams

            # Trouver le prochain emplacement disponible
            $existingDisks = Get-VMHardDiskDrive -VM $vm
            $controller = 0
            $location = 0

            if ($existingDisks) {{
                # Trouver le prochain emplacement libre sur SCSI controller 0
                $usedLocations = $existingDisks | Where-Object {{ $_.ControllerNumber -eq 0 }} | Select-Object -ExpandProperty ControllerLocation
                while ($usedLocations -contains $location) {{
                    $location++
                }}
            }}

            # Attacher le disque
            Add-VMHardDiskDrive -VM $vm -Path $vhdxPath -ControllerType SCSI -ControllerNumber $controller -ControllerLocation $location

            @{{
                Path = $vhdxPath
                SizeGB = {size_gb}
                Format = 'VHDX'
                Type = '{disk_type}'
                ControllerNumber = $controller
                ControllerLocation = $location
            }} | ConvertTo-Json
        }} else {{
            throw "VM not found"
        }}
        """

        result = await self._execute(script, timeout=120)

        if not result.success:
            raise VMOperationError(vm_id, "add_hard_disk", result.stderr)

        data = self._parse_json_output(result.stdout)

        if data is None:
            raise VMOperationError(vm_id, "add_hard_disk", "No disk data returned")

        disk = DiskInfo(
            path=data.get("Path", ""),
            size_gb=data.get("SizeGB", size_gb),
            format=data.get("Format", "VHDX"),
            type=data.get("Type", disk_type),
            attached_to=vm_id,
            controller_number=data.get("ControllerNumber", 0),
            controller_location=data.get("ControllerLocation", 0),
        )

        logger.info(
            "hyperv_hard_disk_added",
            vm_id=vm_id,
            path=disk.path,
            size_gb=size_gb,
        )
        return disk

    async def remove_hard_disk(
        self,
        vm_id: str,
        disk_path: str | None = None,
        controller_number: int | None = None,
        controller_location: int | None = None,
        delete_vhdx: bool = False,
    ) -> bool:
        """
        Supprime un disque dur d'une VM.

        Args:
            vm_id: ID ou nom de la VM
            disk_path: Chemin du disque (prioritaire)
            controller_number: Numéro du contrôleur
            controller_location: Emplacement sur le contrôleur
            delete_vhdx: Si True, supprime aussi le fichier VHDX

        Returns:
            True si supprimé
        """
        if disk_path:
            filter_clause = f"$_.Path -eq '{disk_path}'"
        elif controller_number is not None and controller_location is not None:
            filter_clause = f"$_.ControllerNumber -eq {controller_number} -and $_.ControllerLocation -eq {controller_location}"
        else:
            raise ValueError("Spécifiez disk_path ou controller_number+controller_location")

        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            $disk = Get-VMHardDiskDrive -VM $vm | Where-Object {{ {filter_clause} }}
            if ($disk) {{
                $diskPath = $disk.Path
                Remove-VMHardDiskDrive -VMHardDiskDrive $disk
                {"Remove-Item -Path $diskPath -Force -ErrorAction SilentlyContinue" if delete_vhdx else ""}
                Write-Output "Disk removed"
            }} else {{
                throw "Disk not found"
            }}
        }} else {{
            throw "VM not found"
        }}
        """

        result = await self._execute(script)

        if not result.success:
            raise VMOperationError(vm_id, "remove_hard_disk", result.stderr)

        logger.info(
            "hyperv_hard_disk_removed",
            vm_id=vm_id,
            disk_path=disk_path,
            delete_vhdx=delete_vhdx,
        )
        return True

    async def resize_hard_disk(
        self,
        vm_id: str,
        disk_path: str,
        new_size_gb: int,
    ) -> bool:
        """
        Redimensionne un disque dur (augmentation uniquement).

        Args:
            vm_id: ID ou nom de la VM
            disk_path: Chemin du disque
            new_size_gb: Nouvelle taille en GB

        Returns:
            True si redimensionné
        """
        script = f"""
        $ErrorActionPreference = 'Stop'
        $vhd = Get-VHD -Path '{disk_path}'
        $currentSizeGB = [math]::Round($vhd.Size/1GB)

        if ({new_size_gb} -le $currentSizeGB) {{
            throw "New size ({new_size_gb} GB) must be greater than current size ($currentSizeGB GB)"
        }}

        Resize-VHD -Path '{disk_path}' -SizeBytes {new_size_gb}GB
        Write-Output "Disk resized from $currentSizeGB GB to {new_size_gb} GB"
        """

        result = await self._execute(script, timeout=120)

        if not result.success:
            raise VMOperationError(vm_id, "resize_hard_disk", result.stderr)

        logger.info(
            "hyperv_hard_disk_resized",
            vm_id=vm_id,
            disk_path=disk_path,
            new_size_gb=new_size_gb,
        )
        return True

    async def attach_existing_disk(
        self,
        vm_id: str,
        disk_path: str,
        controller_number: int = 0,
        controller_location: int | None = None,
    ) -> bool:
        """
        Attache un disque VHDX existant à une VM.

        Args:
            vm_id: ID ou nom de la VM
            disk_path: Chemin du fichier VHDX
            controller_number: Numéro du contrôleur SCSI
            controller_location: Emplacement (auto si None)

        Returns:
            True si attaché
        """
        if controller_location is not None:
            location_param = f"-ControllerLocation {controller_location}"
        else:
            location_param = ""

        script = f"""
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if ($vm) {{
            if (-not (Test-Path '{disk_path}')) {{
                throw "Disk file not found: {disk_path}"
            }}

            Add-VMHardDiskDrive -VM $vm -Path '{disk_path}' -ControllerType SCSI -ControllerNumber {controller_number} {location_param}
            Write-Output "Disk attached"
        }} else {{
            throw "VM not found"
        }}
        """

        result = await self._execute(script)

        if not result.success:
            raise VMOperationError(vm_id, "attach_existing_disk", result.stderr)

        logger.info(
            "hyperv_disk_attached",
            vm_id=vm_id,
            disk_path=disk_path,
        )
        return True

    # =========================================================================
    # Informations réseau complètes
    # =========================================================================

    async def get_vm_network_info(
        self,
        vm_id: str,
        vm_credentials: tuple[str, str] | None = None,
    ) -> VMNetworkInfo:
        """
        Récupère les informations réseau complètes d'une VM.

        Combine les infos Hyper-V (MAC, switch, VLAN) avec les infos
        récupérées depuis l'intérieur de la VM via PowerShell Direct
        (IP, masque, gateway, DNS, DHCP status).

        Args:
            vm_id: ID ou nom de la VM
            vm_credentials: Tuple (username, password) pour récupérer les infos
                           depuis l'intérieur de la VM. Si None, seules les
                           infos Hyper-V sont retournées.

        Returns:
            VMNetworkInfo avec toutes les informations réseau
        """
        # Récupérer les infos côté Hyper-V
        adapters = await self.list_network_adapters(vm_id)

        network_info = VMNetworkInfo(
            vm_name=vm_id,
            adapters_hyperv=adapters,
        )

        # Si pas de credentials, retourner uniquement les infos Hyper-V
        if not vm_credentials:
            logger.info(
                "hyperv_network_info_partial",
                vm_id=vm_id,
                adapters_count=len(adapters),
            )
            return network_info

        # Script guest ultra-simplifié pour éviter limite ligne de commande
        guest_script = '''$r=@{H=$env:COMPUTERNAME;I=@()};Get-NetAdapter|?{$_.Status-eq"Up"}|%{$a=$_;$i=$a.InterfaceIndex;$p=Get-NetIPAddress -InterfaceIndex $i -AddressFamily IPv4 -EA 0|Select -First 1;$c=Get-NetIPConfiguration -InterfaceIndex $i -EA 0;$d=Get-DnsClientServerAddress -InterfaceIndex $i -AddressFamily IPv4 -EA 0;$g=if($c.IPv4DefaultGateway){$c.IPv4DefaultGateway.NextHop}else{$null};$r.I+=@{N=$a.Name;M=$a.MacAddress;IP=if($p){$p.IPAddress}else{$null};P=if($p){$p.PrefixLength}else{$null};G=$g;D=$d.ServerAddresses}};$r|ConvertTo-Json -Depth 3'''

        result = await self.execute_in_vm(vm_id, guest_script, vm_credentials, timeout=60)

        if not result.success:
            logger.warning(
                "hyperv_network_info_guest_failed",
                vm_id=vm_id,
                error=result.error,
            )
            return network_info

        # Parser les données guest (clés abrégées pour réduire taille script)
        # Le résultat peut être encapsulé dans {'value': 'json_string'}
        raw_output = result.output
        if isinstance(raw_output, dict) and "value" in raw_output:
            raw_output = raw_output["value"]
        if isinstance(raw_output, str):
            guest_data = self._parse_json_output(raw_output)
        else:
            guest_data = raw_output

        if guest_data:
            # Clés abrégées: H=Hostname, I=Interfaces
            network_info.hostname = guest_data.get("H")

            interfaces = guest_data.get("I", [])
            if isinstance(interfaces, dict):
                interfaces = [interfaces]

            for iface in interfaces:
                if iface:
                    # Clés abrégées: D=DNS, G=Gateway, N=Name, M=MAC, IP=IP, P=Prefix
                    dns_servers = iface.get("D", [])
                    if isinstance(dns_servers, str):
                        dns_servers = [dns_servers] if dns_servers else []

                    network_info.interfaces_guest.append(
                        NetworkInterfaceDetails(
                            interface_name=iface.get("N", ""),
                            interface_alias=iface.get("N", ""),  # Même que Name dans script simplifié
                            interface_index=0,  # Non récupéré dans script simplifié
                            mac_address=iface.get("M", ""),
                            ip_address=iface.get("IP"),
                            subnet_mask=None,  # Non récupéré dans script simplifié
                            prefix_length=iface.get("P"),
                            default_gateway=iface.get("G"),
                            dns_servers=dns_servers,
                            dhcp_enabled=False,  # Non récupéré dans script simplifié
                            dhcp_server=None,
                            connection_status="Up",  # Implicite car on filtre Status="Up"
                            link_speed_mbps=None,
                        )
                    )

        logger.info(
            "hyperv_network_info_complete",
            vm_id=vm_id,
            hostname=network_info.hostname,
            adapters_hyperv=len(network_info.adapters_hyperv),
            interfaces_guest=len(network_info.interfaces_guest),
            primary_ip=network_info.get_primary_ip(),
            primary_mac=network_info.get_primary_mac(),
        )

        return network_info

    async def get_vm_network_summary(
        self,
        vm_id: str,
        vm_credentials: tuple[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Retourne un résumé des informations réseau d'une VM.

        Format simplifié pour l'affichage/API.

        Args:
            vm_id: ID ou nom de la VM
            vm_credentials: Credentials pour les infos guest (optionnel)

        Returns:
            Dictionnaire avec les infos réseau essentielles
        """
        network_info = await self.get_vm_network_info(vm_id, vm_credentials)

        summary = {
            "vm_name": network_info.vm_name,
            "hostname": network_info.hostname,
            "primary_ip": network_info.get_primary_ip(),
            "primary_mac": network_info.get_primary_mac(),
            "adapters": [],
        }

        # Combiner les infos Hyper-V et guest
        for adapter in network_info.adapters_hyperv:
            adapter_info = {
                "name": adapter.name,
                "switch": adapter.switch_name,
                "mac": adapter.mac_address,
                "vlan": adapter.vlan_id,
                "ips_hyperv": adapter.ip_addresses,
            }

            # Chercher l'interface guest correspondante (par MAC)
            if adapter.mac_address:
                # Normaliser le format MAC pour comparaison
                adapter_mac = adapter.mac_address.replace("-", "").replace(":", "").upper()
                for guest_iface in network_info.interfaces_guest:
                    guest_mac = guest_iface.mac_address.replace("-", "").replace(":", "").upper()
                    if adapter_mac == guest_mac:
                        adapter_info["ip"] = guest_iface.ip_address
                        adapter_info["subnet_mask"] = guest_iface.subnet_mask
                        adapter_info["gateway"] = guest_iface.default_gateway
                        adapter_info["dns"] = guest_iface.dns_servers
                        adapter_info["dhcp"] = guest_iface.dhcp_enabled
                        adapter_info["status"] = guest_iface.connection_status
                        adapter_info["speed_mbps"] = guest_iface.link_speed_mbps
                        break

            summary["adapters"].append(adapter_info)

        return summary
