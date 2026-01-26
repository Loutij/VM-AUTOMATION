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
    PowerShellDirectResult,
    VirtualSwitch,
    VMHealthStatus,
    VMInfo,
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
        username, password = vm_credentials
        
        # Échapper les caractères spéciaux dans le script
        escaped_script = script.replace("'", "''").replace('"', '`"')
        
        ps_script = f"""
        $ErrorActionPreference = 'Stop'
        $vmName = '{vm_id}'
        $cred = New-Object System.Management.Automation.PSCredential(
            '{username}',
            (ConvertTo-SecureString '{password}' -AsPlainText -Force)
        )
        
        try {{
            $result = Invoke-Command -VMName $vmName -Credential $cred -ScriptBlock {{
                {escaped_script}
            }} -ErrorAction Stop
            
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
