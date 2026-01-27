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
        if not output or not output.strip():
            return None
        
        text = output.strip()
        
        # Essayer de parser directement
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Essayer d'extraire le JSON d'un bloc { ... } ou [ ... ]
        import re
        
        # Chercher un objet JSON {...}
        obj_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if obj_match:
            try:
                return json.loads(obj_match.group(0))
            except json.JSONDecodeError:
                pass
        
        # Chercher un tableau JSON [...]
        arr_match = re.search(r'\[[^\[\]]*\]', text, re.DOTALL)
        if arr_match:
            try:
                return json.loads(arr_match.group(0))
            except json.JSONDecodeError:
                pass
        
        # Dernière tentative: chercher la dernière ligne qui ressemble à du JSON
        for line in reversed(text.split('\n')):
            line = line.strip()
            if line.startswith('{') or line.startswith('['):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        
        logger.warning(
            "json_parse_error",
            output=text[:200],
            error="No valid JSON found",
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

    async def list_vms_with_network(self) -> list[dict]:
        """
        Liste toutes les VMs avec leurs informations réseau (IP, MAC, switch).
        
        Plus lent que list_vms car récupère aussi les infos réseau,
        mais évite de faire N requêtes séparées.
        
        Returns:
            Liste de dictionnaires avec toutes les infos VM + réseau
        """
        script = """
        $result = @()
        Get-VM | ForEach-Object {
            $vm = $_
            $nic = Get-VMNetworkAdapter -VM $vm -ErrorAction SilentlyContinue | Select-Object -First 1
            
            # Récupérer les IPs non-link-local
            $allIps = @()
            $primaryIp = $null
            if ($nic -and $nic.IPAddresses) {
                foreach ($ip in $nic.IPAddresses) {
                    if ($ip -and $ip -ne '' -and $ip -notlike 'fe80:*') {
                        $allIps += $ip
                    }
                }
                if ($allIps.Count -gt 0) {
                    $primaryIp = $allIps[0]
                }
            }
            
            $vmInfo = @{
                id = $vm.VMId.ToString()
                name = $vm.Name
                state = $vm.State.ToString()
                cpu_count = $vm.ProcessorCount
                ram_gb = [math]::Round($vm.MemoryAssigned/1GB, 2)
                uptime = $vm.Uptime.ToString()
                status = $vm.Status
                generation = $vm.Generation
                path = $vm.Path
                # Network info
                ip_address = $primaryIp
                ip_addresses = $allIps
                mac_address = if ($nic) { $nic.MacAddress } else { $null }
                switch_name = if ($nic) { $nic.SwitchName } else { $null }
                vlan_id = $null
            }
            
            # Récupérer VLAN si configuré
            if ($nic) {
                $vlan = Get-VMNetworkAdapterVlan -VMNetworkAdapter $nic -ErrorAction SilentlyContinue
                if ($vlan -and $vlan.AccessVlanId -gt 0) {
                    $vmInfo.vlan_id = $vlan.AccessVlanId
                }
            }
            
            $result += $vmInfo
        }
        $result | ConvertTo-Json -Depth 3
        """
        
        result = await self._execute(script, timeout=60)
        
        if not result.success:
            logger.warning(
                "list_vms_with_network_failed",
                error=result.stderr,
            )
            return []
        
        data = self._parse_json_output(result.stdout)
        
        if data is None:
            return []
        
        # Normaliser en liste
        if isinstance(data, dict):
            data = [data]
        
        logger.info("hyperv_vms_with_network_listed", count=len(data), host=self.host)
        return data

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
        
        # Construire le chemin VHDX complet
        if specs.vhdx_path:
            if specs.vhdx_path.lower().endswith(".vhdx"):
                # Chemin complet fourni
                vhdx_path = specs.vhdx_path
            else:
                # C'est un dossier, ajouter le nom du fichier
                vhdx_path = f"{specs.vhdx_path.rstrip(chr(92))}\\{specs.name}.vhdx"
        else:
            # Chemin par défaut
            vhdx_path = f"{self.vhdx_path}\\{specs.name}.vhdx"
        
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
        
        # Nettoyer les fichiers orphelins si présents
        $existingVm = Get-VM -Name '{specs.name}' -ErrorAction SilentlyContinue
        if ($existingVm) {{
            throw "Une VM avec le nom '{specs.name}' existe déjà. Supprimez-la d'abord."
        }}
        
        # Vérifier si un VHDX orphelin existe et le supprimer
        $vhdxPath = '{vhdx_path}'
        if (Test-Path $vhdxPath) {{
            Write-Warning "VHDX orphelin détecté, suppression: $vhdxPath"
            Remove-Item $vhdxPath -Force
        }}
        
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

    async def list_isos(self, path: str | None = None) -> list[dict[str, Any]]:
        """
        Liste les fichiers ISO disponibles sur l'hyperviseur.
        
        Args:
            path: Chemin du dossier à scanner (par défaut: iso_path configuré)
            
        Returns:
            Liste de dictionnaires avec les infos des ISOs
        """
        iso_folder = path or self.iso_path
        
        script = f"""
        $isoPath = '{iso_folder}'
        if (Test-Path $isoPath) {{
            Get-ChildItem -Path $isoPath -Filter '*.iso' -Recurse | 
            Select-Object @{{N='name';E={{$_.Name}}}},
                          @{{N='full_path';E={{$_.FullName}}}},
                          @{{N='size_bytes';E={{$_.Length}}}},
                          @{{N='size_gb';E={{[math]::Round($_.Length/1GB, 2)}}}},
                          @{{N='last_modified';E={{$_.LastWriteTime.ToString('yyyy-MM-ddTHH:mm:ss')}}}},
                          @{{N='directory';E={{$_.DirectoryName}}}} |
            ConvertTo-Json -Depth 2
        }} else {{
            Write-Output '[]'
        }}
        """
        
        result = await self._execute(script)
        
        if not result.success:
            logger.warning("Failed to list ISOs", error=result.stderr, path=iso_folder)
            return []
        
        data = self._parse_json_output(result.stdout)
        
        if data is None:
            return []
        
        # Normaliser en liste
        if isinstance(data, dict):
            data = [data]
        
        logger.info("hyperv_isos_listed", count=len(data), path=iso_folder)
        return data

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

    async def inject_unattend(
        self,
        vm_id: str,
        unattend_content: str,
    ) -> bool:
        """
        Injecte un fichier autounattend.xml dans une VM via un disque VHDX dédié.
        
        Cette méthode crée un petit disque VHDX, y place le fichier autounattend.xml,
        puis l'attache à la VM. Le Setup Windows détectera automatiquement ce fichier.
        
        Args:
            vm_id: ID ou nom de la VM
            unattend_content: Contenu XML du fichier autounattend.xml
            
        Returns:
            True si succès
            
        Raises:
            VMOperationError: En cas d'erreur
        """
        logger.info("hyperv_inject_unattend_start", vm_id=vm_id, content_length=len(unattend_content))
        
        # Échapper les caractères spéciaux pour PowerShell
        # Remplacer les guillemets simples par deux guillemets simples
        escaped_content = unattend_content.replace("'", "''")
        
        # Script PowerShell pour créer et attacher le disque unattend
        # Divisé en étapes pour éviter les problèmes de longueur de commande
        
        # Étape 1: Créer le dossier et le VHDX
        script_create = f"""
        $vmName = '{vm_id}'
        $unattendDir = 'C:\\HyperV\\Unattend'
        $vhdxPath = "$unattendDir\\${{vmName}}_unattend.vhdx"
        
        # Créer le dossier s'il n'existe pas
        if (-not (Test-Path $unattendDir)) {{
            New-Item -ItemType Directory -Path $unattendDir -Force | Out-Null
        }}
        
        # Arrêter la VM si nécessaire
        $vm = Get-VM -Name $vmName -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq $vmName }}
        }}
        if (-not $vm) {{
            throw "VM not found: $vmName"
        }}
        
        if ($vm.State -eq 'Running') {{
            Stop-VM -VM $vm -Force -TurnOff
            Start-Sleep -Seconds 2
        }}
        
        # Supprimer l'ancien disque unattend s'il existe
        Get-VMHardDiskDrive -VM $vm | Where-Object {{ $_.Path -like '*unattend*' }} | Remove-VMHardDiskDrive -ErrorAction SilentlyContinue
        if (Test-Path $vhdxPath) {{
            Remove-Item $vhdxPath -Force
        }}
        
        # Créer le VHDX
        New-VHD -Path $vhdxPath -SizeBytes 50MB -Dynamic | Out-Null
        $disk = Mount-VHD -Path $vhdxPath -Passthru
        $disk | Initialize-Disk -PartitionStyle MBR
        $partition = $disk | New-Partition -UseMaximumSize -AssignDriveLetter
        $partition | Format-Volume -FileSystem FAT32 -NewFileSystemLabel "UNATTEND" -Confirm:$false | Out-Null
        
        @{{
            VhdxPath = $vhdxPath
            DriveLetter = $partition.DriveLetter
        }} | ConvertTo-Json
        """
        
        result = await self._execute(script_create, timeout=60)
        
        if not result.success:
            raise VMOperationError(vm_id, "inject_unattend_create", result.stderr)
        
        # Parser le résultat pour obtenir la lettre de lecteur
        data = self._parse_json_output(result.stdout)
        if not data:
            raise VMOperationError(vm_id, "inject_unattend_create", "Failed to parse disk info")
        
        drive_letter = data.get("DriveLetter")
        vhdx_path = data.get("VhdxPath")
        
        logger.debug("hyperv_unattend_disk_created", drive_letter=drive_letter, vhdx_path=vhdx_path)
        
        # Étape 2: Écrire le fichier autounattend.xml en chunks pour éviter les limites WinRM
        import base64
        content_b64 = base64.b64encode(unattend_content.encode('utf-8')).decode('ascii')
        
        # Diviser en chunks de 2000 caractères pour rester sous la limite WinRM
        chunk_size = 2000
        chunks = [content_b64[i:i+chunk_size] for i in range(0, len(content_b64), chunk_size)]
        
        file_path = f"{drive_letter}:\\autounattend.xml"
        temp_b64_path = f"{drive_letter}:\\temp_unattend.b64"
        
        # Écrire le premier chunk (crée le fichier)
        script_first = f"""
        $chunk = '{chunks[0]}'
        [System.IO.File]::WriteAllText('{temp_b64_path}', $chunk)
        Write-Output "Chunk 1/{len(chunks)} written"
        """
        result = await self._execute(script_first, timeout=30)
        if not result.success:
            await self._execute(f"Dismount-VHD -Path '{vhdx_path}' -ErrorAction SilentlyContinue")
            raise VMOperationError(vm_id, "inject_unattend_write_chunk1", result.stderr)
        
        # Ajouter les chunks suivants
        for i, chunk in enumerate(chunks[1:], start=2):
            script_append = f"""
            $chunk = '{chunk}'
            [System.IO.File]::AppendAllText('{temp_b64_path}', $chunk)
            Write-Output "Chunk {i}/{len(chunks)} written"
            """
            result = await self._execute(script_append, timeout=30)
            if not result.success:
                await self._execute(f"Dismount-VHD -Path '{vhdx_path}' -ErrorAction SilentlyContinue")
                raise VMOperationError(vm_id, f"inject_unattend_write_chunk{i}", result.stderr)
        
        # Décoder le base64 et créer le fichier final
        script_decode = f"""
        $b64 = [System.IO.File]::ReadAllText('{temp_b64_path}')
        $bytes = [System.Convert]::FromBase64String($b64)
        $content = [System.Text.Encoding]::UTF8.GetString($bytes)
        [System.IO.File]::WriteAllText('{file_path}', $content, [System.Text.Encoding]::UTF8)
        Remove-Item '{temp_b64_path}' -Force
        if (Test-Path '{file_path}') {{
            Write-Output "File written successfully"
        }} else {{
            throw "Failed to write autounattend.xml"
        }}
        """
        
        result = await self._execute(script_decode, timeout=30)
        
        if not result.success:
            await self._execute(f"Dismount-VHD -Path '{vhdx_path}' -ErrorAction SilentlyContinue")
            raise VMOperationError(vm_id, "inject_unattend_decode", result.stderr)
        
        logger.debug("hyperv_unattend_file_written", vm_id=vm_id)
        
        # Étape 3: Démonter et attacher à la VM, configurer boot order
        script_attach = f"""
        $vmName = '{vm_id}'
        $vhdxPath = '{vhdx_path}'
        
        # Démonter le VHD
        Dismount-VHD -Path $vhdxPath
        
        # Récupérer la VM
        $vm = Get-VM -Name $vmName -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq $vmName }}
        }}
        
        # Attacher le disque unattend à la VM
        Add-VMHardDiskDrive -VM $vm -Path $vhdxPath -ControllerType SCSI -ControllerNumber 0 -ControllerLocation 2
        
        # Configurer le boot order: DVD en premier
        $dvd = Get-VMDvdDrive -VM $vm | Select-Object -First 1
        if ($dvd) {{
            Set-VMFirmware -VM $vm -FirstBootDevice $dvd
        }}
        
        Write-Output "Unattend disk attached and boot order configured"
        """
        
        result = await self._execute(script_attach, timeout=30)
        
        if not result.success:
            raise VMOperationError(vm_id, "inject_unattend_attach", result.stderr)
        
        logger.info("hyperv_inject_unattend_complete", vm_id=vm_id)
        return True

    async def create_custom_iso(
        self,
        source_iso: str,
        unattend_content: str,
        output_iso: str | None = None,
    ) -> str:
        """
        Crée une ISO personnalisée avec autounattend.xml inclus.
        
        Cette méthode copie le contenu de l'ISO source, ajoute autounattend.xml,
        et recrée une nouvelle ISO bootable UEFI.
        
        Args:
            source_iso: Chemin de l'ISO source
            unattend_content: Contenu XML du fichier autounattend.xml
            output_iso: Chemin de sortie (optionnel, généré automatiquement si non fourni)
            
        Returns:
            Chemin de l'ISO personnalisée créée
            
        Raises:
            VMOperationError: En cas d'erreur
        """
        import base64
        
        logger.info("hyperv_create_custom_iso_start", source_iso=source_iso)
        
        # Encoder le contenu en base64 pour éviter les problèmes de caractères
        content_b64 = base64.b64encode(unattend_content.encode('utf-8')).decode('ascii')
        
        # Diviser en chunks
        chunk_size = 2000
        chunks = [content_b64[i:i+chunk_size] for i in range(0, len(content_b64), chunk_size)]
        
        # Étape 1: Préparer les dossiers et copier l'ISO
        script_prepare = f"""
        $sourceIso = '{source_iso}'
        $tempDir = 'C:\\HyperV\\Temp\\ISO_Build'
        $isoContentDir = "$tempDir\\ISOContent"
        
        # Nettoyer et créer les dossiers
        if (Test-Path $tempDir) {{ Remove-Item $tempDir -Recurse -Force }}
        New-Item -ItemType Directory -Path $isoContentDir -Force | Out-Null
        
        # Monter l'ISO source
        $mountResult = Mount-DiskImage -ImagePath $sourceIso -PassThru
        $driveLetter = ($mountResult | Get-Volume).DriveLetter
        
        Write-Output "ISO montée sur ${{driveLetter}}:"
        
        # Copier le contenu
        Write-Output "Copie du contenu de l'ISO..."
        Copy-Item -Path "${{driveLetter}}:\\*" -Destination $isoContentDir -Recurse -Force
        
        # Démonter l'ISO source
        Dismount-DiskImage -ImagePath $sourceIso | Out-Null
        
        @{{
            TempDir = $tempDir
            IsoContentDir = $isoContentDir
        }} | ConvertTo-Json
        """
        
        result = await self._execute(script_prepare, timeout=300)
        if not result.success:
            raise VMOperationError("iso", "create_custom_iso_prepare", result.stderr)
        
        data = self._parse_json_output(result.stdout)
        if not data:
            raise VMOperationError("iso", "create_custom_iso_prepare", "Failed to parse result")
        
        temp_dir = data.get("TempDir")
        iso_content_dir = data.get("IsoContentDir")
        
        logger.debug("hyperv_iso_content_copied", temp_dir=temp_dir)
        
        # Étape 2: Écrire autounattend.xml en chunks
        temp_b64_path = f"{temp_dir}\\temp_unattend.b64"
        
        for i, chunk in enumerate(chunks):
            if i == 0:
                script = f"[System.IO.File]::WriteAllText('{temp_b64_path}', '{chunk}')"
            else:
                script = f"[System.IO.File]::AppendAllText('{temp_b64_path}', '{chunk}')"
            
            result = await self._execute(script, timeout=30)
            if not result.success:
                raise VMOperationError("iso", f"create_custom_iso_write_chunk{i}", result.stderr)
        
        # Décoder et créer autounattend.xml
        script_decode = f"""
        $b64 = [System.IO.File]::ReadAllText('{temp_b64_path}')
        $bytes = [System.Convert]::FromBase64String($b64)
        $content = [System.Text.Encoding]::UTF8.GetString($bytes)
        [System.IO.File]::WriteAllText('{iso_content_dir}\\autounattend.xml', $content, [System.Text.Encoding]::UTF8)
        Remove-Item '{temp_b64_path}' -Force
        Write-Output "autounattend.xml created"
        """
        
        result = await self._execute(script_decode, timeout=30)
        if not result.success:
            raise VMOperationError("iso", "create_custom_iso_decode", result.stderr)
        
        logger.debug("hyperv_autounattend_written")
        
        # Étape 3: Créer l'ISO avec oscdimg
        if not output_iso:
            import os
            base_name = source_iso.rsplit('\\', 1)[-1].rsplit('.', 1)[0]
            output_iso = f"C:\\HyperV\\ISOs\\{base_name}_AUTO.iso"
        
        script_create_iso = f"""
        $isoContentDir = '{iso_content_dir}'
        $outputIso = '{output_iso}'
        $oscdimg = "C:\\Program Files (x86)\\Windows Kits\\10\\Assessment and Deployment Kit\\Deployment Tools\\amd64\\Oscdimg\\oscdimg.exe"
        $efisys = "$isoContentDir\\efi\\microsoft\\boot\\efisys.bin"
        $etfsboot = "$isoContentDir\\boot\\etfsboot.com"
        
        # Supprimer l'ancienne ISO si elle existe
        if (Test-Path $outputIso) {{ Remove-Item $outputIso -Force }}
        
        # Créer l'ISO (UEFI + BIOS bootable)
        Write-Output "Création de l'ISO..."
        if ((Test-Path $efisys) -and (Test-Path $etfsboot)) {{
            # Dual boot UEFI + BIOS
            & $oscdimg -m -o -u2 -udfver102 -bootdata:2`#p0,e,b"$etfsboot"`#pEF,e,b"$efisys" $isoContentDir $outputIso
        }} elseif (Test-Path $efisys) {{
            # UEFI only
            & $oscdimg -m -o -u2 -udfver102 -bootdata:1`#pEF,e,b"$efisys" $isoContentDir $outputIso
        }} else {{
            throw "Boot files not found in ISO"
        }}
        
        if (Test-Path $outputIso) {{
            $size = (Get-Item $outputIso).Length / 1GB
            Write-Output "ISO créée: $outputIso ($([math]::Round($size, 2)) GB)"
            
            # Nettoyer
            Remove-Item '{temp_dir}' -Recurse -Force -ErrorAction SilentlyContinue
            
            $outputIso
        }} else {{
            throw "Failed to create ISO"
        }}
        """
        
        result = await self._execute(script_create_iso, timeout=600)
        if not result.success:
            raise VMOperationError("iso", "create_custom_iso_build", result.stderr)
        
        # Extraire le chemin de l'ISO
        output_lines = result.stdout.strip().split('\n')
        created_iso = output_lines[-1].strip()
        
        logger.info("hyperv_custom_iso_created", output_iso=created_iso)
        return created_iso

    async def remove_unattend_disk(self, vm_id: str) -> bool:
        """
        Supprime le disque unattend d'une VM après l'installation.
        
        Args:
            vm_id: ID ou nom de la VM
            
        Returns:
            True si succès
        """
        script = f"""
        $vmName = '{vm_id}'
        $vm = Get-VM -Name $vmName -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq $vmName }}
        }}
        if ($vm) {{
            $unattendDisk = Get-VMHardDiskDrive -VM $vm | Where-Object {{ $_.Path -like '*unattend*' }}
            if ($unattendDisk) {{
                $diskPath = $unattendDisk.Path
                Remove-VMHardDiskDrive -VMHardDiskDrive $unattendDisk
                if (Test-Path $diskPath) {{
                    Remove-Item $diskPath -Force
                }}
                Write-Output "Unattend disk removed"
            }} else {{
                Write-Output "No unattend disk found"
            }}
        }} else {{
            throw "VM not found"
        }}
        """
        
        result = await self._execute(script, timeout=30)
        
        if not result.success:
            logger.warning("hyperv_remove_unattend_disk_failed", vm_id=vm_id, error=result.stderr)
            return False
        
        logger.info("hyperv_unattend_disk_removed", vm_id=vm_id)
        return True

    async def deploy_with_dism(
        self,
        vm_id: str,
        iso_path: str,
        vhd_path: str,
        image_index: int = 2,
        unattend_content: str | None = None,
    ) -> bool:
        """
        Déploie Windows sur une VM via DISM (sans installation interactive).
        
        Cette méthode applique directement l'image Windows sur le disque de la VM,
        évitant ainsi le prompt "Press any key to boot from CD or DVD".
        
        Args:
            vm_id: ID ou nom de la VM
            iso_path: Chemin de l'ISO Windows sur l'hyperviseur
            vhd_path: Chemin du VHD de la VM
            image_index: Index de l'image dans le WIM (1=Core, 2=Desktop Experience)
            unattend_content: Contenu du fichier unattend.xml pour automatiser l'OOBE
            
        Returns:
            True si succès
            
        Raises:
            VMOperationError: En cas d'erreur
        """
        logger.info(
            "hyperv_deploy_dism_start",
            vm_id=vm_id,
            iso_path=iso_path,
            image_index=image_index,
        )
        
        # Étape 1: Préparer et partitionner le VHD
        script_prepare = f"""
        $ErrorActionPreference = 'Stop'
        $ProgressPreference = 'SilentlyContinue'
        
        $vhdPath = '{vhd_path}'
        $isoPath = '{iso_path}'
        
        # Démonter si déjà monté
        Dismount-VHD -Path $vhdPath -ErrorAction SilentlyContinue
        Dismount-DiskImage -ImagePath $isoPath -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        
        # Monter l'ISO et récupérer la lettre de lecteur
        Mount-DiskImage -ImagePath $isoPath -StorageType ISO | Out-Null
        Start-Sleep -Seconds 2
        $isoDrive = (Get-DiskImage -ImagePath $isoPath | Get-Volume).DriveLetter
        
        if (-not $isoDrive) {{
            throw "Failed to get ISO drive letter"
        }}
        
        # Monter et partitionner le VHD
        $disk = Mount-VHD -Path $vhdPath -Passthru | Get-Disk
        Clear-Disk -Number $disk.Number -RemoveData -Confirm:$false -ErrorAction SilentlyContinue
        Initialize-Disk -Number $disk.Number -PartitionStyle GPT
        
        # Partition EFI (100MB FAT32)
        $efi = New-Partition -DiskNumber $disk.Number -Size 100MB -GptType '{{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}}' -AssignDriveLetter
        Format-Volume -Partition $efi -FileSystem FAT32 -NewFileSystemLabel "System" -Confirm:$false | Out-Null
        
        # Partition MSR (16MB)
        New-Partition -DiskNumber $disk.Number -Size 16MB -GptType '{{e3c9e316-0b5c-4db8-817d-f92df00215ae}}' | Out-Null
        
        # Partition Windows (reste de l'espace)
        $win = New-Partition -DiskNumber $disk.Number -UseMaximumSize -AssignDriveLetter
        Format-Volume -Partition $win -FileSystem NTFS -NewFileSystemLabel "Windows" -Confirm:$false | Out-Null
        
        @{{
            IsoDrive = $isoDrive
            EfiDrive = $efi.DriveLetter
            WinDrive = $win.DriveLetter
        }} | ConvertTo-Json
        """
        
        result = await self._execute(script_prepare, timeout=120)
        if not result.success:
            raise VMOperationError(vm_id, "deploy_dism_prepare", result.stderr)
        
        data = self._parse_json_output(result.stdout)
        if not data:
            raise VMOperationError(vm_id, "deploy_dism_prepare", "Failed to parse partition info")
        
        iso_drive = data.get("IsoDrive")
        efi_drive = data.get("EfiDrive")
        win_drive = data.get("WinDrive")
        
        logger.debug(
            "hyperv_dism_partitions_created",
            iso_drive=iso_drive,
            efi_drive=efi_drive,
            win_drive=win_drive,
        )
        
        # Étape 2: Appliquer l'image Windows avec DISM
        script_dism = f"""
        Dism /Apply-Image /ImageFile:{iso_drive}:\\sources\\install.wim /Index:{image_index} /ApplyDir:{win_drive}:\\
        if ($LASTEXITCODE -eq 0) {{
            Write-Output "DISM_SUCCESS"
        }} else {{
            throw "DISM failed with exit code $LASTEXITCODE"
        }}
        """
        
        result = await self._execute(script_dism, timeout=600)
        if not result.success or "DISM_SUCCESS" not in (result.stdout or ""):
            # Nettoyer en cas d'erreur
            await self._execute(f"Dismount-DiskImage -ImagePath '{iso_path}' -ErrorAction SilentlyContinue")
            await self._execute(f"Dismount-VHD -Path '{vhd_path}' -ErrorAction SilentlyContinue")
            raise VMOperationError(vm_id, "deploy_dism_apply", result.stderr or result.stdout)
        
        logger.debug("hyperv_dism_image_applied", vm_id=vm_id)
        
        # Étape 3: Configuration complète pour automatiser l'OOBE
        # Extraction du mot de passe admin depuis le unattend_content
        admin_password = "Admin123!"  # Valeur par défaut
        if unattend_content:
            import re
            import base64
            
            # Essayer d'extraire le mot de passe du unattend.xml
            pwd_match = re.search(
                r'<AdministratorPassword>\s*<Value>([^<]+)</Value>',
                unattend_content
            )
            if pwd_match:
                admin_password = pwd_match.group(1)
            
            content_b64 = base64.b64encode(unattend_content.encode('utf-8')).decode('ascii')
            chunks = [content_b64[i:i+2000] for i in range(0, len(content_b64), 2000)]
            
            temp_b64 = f"{win_drive}:\\temp_unattend.b64"
            
            # Écrire le fichier en chunks
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await self._execute(f"[System.IO.File]::WriteAllText('{temp_b64}', '{chunk}')")
                else:
                    await self._execute(f"[System.IO.File]::AppendAllText('{temp_b64}', '{chunk}')")
            
            # Placer unattend.xml dans TOUS les emplacements possibles
            script_unattend = f"""
            $b64 = [System.IO.File]::ReadAllText('{temp_b64}')
            $bytes = [System.Convert]::FromBase64String($b64)
            $content = [System.Text.Encoding]::UTF8.GetString($bytes)
            
            # Créer tous les répertoires nécessaires
            $paths = @(
                '{win_drive}:\\Windows\\Panther',
                '{win_drive}:\\Windows\\Panther\\Unattend',
                '{win_drive}:\\Windows\\System32\\Sysprep',
                '{win_drive}:\\Windows\\Setup\\Scripts'
            )
            foreach ($p in $paths) {{
                New-Item -ItemType Directory -Path $p -Force -ErrorAction SilentlyContinue | Out-Null
            }}
            
            # Écrire le unattend.xml dans tous les emplacements possibles
            $unattendPaths = @(
                '{win_drive}:\\Windows\\Panther\\unattend.xml',
                '{win_drive}:\\Windows\\Panther\\Unattend\\unattend.xml',
                '{win_drive}:\\Windows\\System32\\Sysprep\\unattend.xml',
                '{win_drive}:\\unattend.xml'
            )
            foreach ($up in $unattendPaths) {{
                [System.IO.File]::WriteAllText($up, $content, [System.Text.Encoding]::UTF8)
            }}
            
            Remove-Item '{temp_b64}' -Force
            Write-Output "Unattend files written to all locations"
            """
            await self._execute(script_unattend, timeout=60)
            logger.debug("hyperv_dism_unattend_written", vm_id=vm_id)
        
        # Étape 3b: Configurer le registre offline pour bypass OOBE
        script_registry = f"""
        $winDrive = '{win_drive}:'
        $softwareHive = "$winDrive\\Windows\\System32\\config\\SOFTWARE"
        $systemHive = "$winDrive\\Windows\\System32\\config\\SYSTEM"
        
        # Charger les ruches du registre
        reg load "HKLM\\OFFLINE_SW" "$softwareHive" 2>$null
        reg load "HKLM\\OFFLINE_SYS" "$systemHive" 2>$null
        
        # Configuration OOBE - bypass tous les écrans
        $oobeKey = "HKLM\\OFFLINE_SW\\Microsoft\\Windows\\CurrentVersion\\Setup\\OOBE"
        reg add $oobeKey /v SetupDisplayedProductKey /t REG_DWORD /d 1 /f
        reg add $oobeKey /v SetupDisplayedEula /t REG_DWORD /d 1 /f
        reg add $oobeKey /v NetworkLocation /t REG_DWORD /d 1 /f
        reg add $oobeKey /v SkipUserOOBE /t REG_DWORD /d 1 /f
        reg add $oobeKey /v SkipMachineOOBE /t REG_DWORD /d 1 /f
        reg add $oobeKey /v ProtectYourPC /t REG_DWORD /d 3 /f
        reg add $oobeKey /v HideEULAPage /t REG_DWORD /d 1 /f
        reg add $oobeKey /v HideLocalAccountScreen /t REG_DWORD /d 1 /f
        reg add $oobeKey /v HideOnlineAccountScreens /t REG_DWORD /d 1 /f
        reg add $oobeKey /v HideWirelessSetupInOOBE /t REG_DWORD /d 1 /f
        
        # Pointer vers le fichier unattend
        $setupKey = "HKLM\\OFFLINE_SW\\Microsoft\\Windows\\CurrentVersion\\Setup"
        reg add $setupKey /v UnattendFile /t REG_SZ /d "C:\\Windows\\Panther\\unattend.xml" /f
        
        # AutoLogon configuration
        $winlogonKey = "HKLM\\OFFLINE_SW\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon"
        reg add $winlogonKey /v AutoAdminLogon /t REG_SZ /d "1" /f
        reg add $winlogonKey /v DefaultUserName /t REG_SZ /d "Administrator" /f
        reg add $winlogonKey /v DefaultPassword /t REG_SZ /d "{admin_password}" /f
        reg add $winlogonKey /v AutoLogonCount /t REG_DWORD /d 5 /f
        
        # Décharger les ruches
        [gc]::Collect()
        Start-Sleep -Seconds 2
        reg unload "HKLM\\OFFLINE_SW"
        reg unload "HKLM\\OFFLINE_SYS"
        
        Write-Output "REGISTRY_CONFIGURED"
        """
        
        result = await self._execute(script_registry, timeout=120)
        if result.success:
            logger.debug("hyperv_dism_registry_configured", vm_id=vm_id)
        else:
            logger.warning(
                "hyperv_dism_registry_config_warning",
                vm_id=vm_id,
                error=result.stderr,
            )
        
        # Étape 3c: Créer SetupComplete.cmd pour finaliser la configuration au premier boot
        setup_complete_content = f"""@echo off
REM ============================================
REM SetupComplete.cmd - Post-OOBE Configuration
REM ============================================
echo [%date% %time%] SetupComplete starting >> C:\\Windows\\Setup\\Scripts\\setup.log

REM Activer le compte Administrator et définir le mot de passe
net user Administrator "{admin_password}" /active:yes >> C:\\Windows\\Setup\\Scripts\\setup.log 2>&1

REM Configurer le profil réseau sur Privé (pour activer la découverte)
powershell -Command "Get-NetConnectionProfile | Set-NetConnectionProfile -NetworkCategory Private" >> C:\\Windows\\Setup\\Scripts\\setup.log 2>&1

REM Activer la découverte réseau et le partage
netsh advfirewall firewall set rule group="Network Discovery" new enable=Yes >> C:\\Windows\\Setup\\Scripts\\setup.log 2>&1
netsh advfirewall firewall set rule group="File and Printer Sharing" new enable=Yes >> C:\\Windows\\Setup\\Scripts\\setup.log 2>&1

REM Configurer WinRM
powershell -Command "Enable-PSRemoting -Force -SkipNetworkProfileCheck" >> C:\\Windows\\Setup\\Scripts\\setup.log 2>&1
powershell -Command "Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value '*' -Force" >> C:\\Windows\\Setup\\Scripts\\setup.log 2>&1
powershell -Command "winrm quickconfig -quiet" >> C:\\Windows\\Setup\\Scripts\\setup.log 2>&1
powershell -Command "Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False" >> C:\\Windows\\Setup\\Scripts\\setup.log 2>&1

REM Activer RDP
reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 0 /f >> C:\\Windows\\Setup\\Scripts\\setup.log 2>&1
netsh advfirewall firewall set rule group="remote desktop" new enable=Yes >> C:\\Windows\\Setup\\Scripts\\setup.log 2>&1

REM Marquer la configuration comme terminée
echo SETUP_COMPLETE > C:\\Windows\\Setup\\Scripts\\setup_done.flag

echo [%date% %time%] SetupComplete finished >> C:\\Windows\\Setup\\Scripts\\setup.log
"""
        
        # Encoder et écrire SetupComplete.cmd
        import base64
        setup_b64 = base64.b64encode(setup_complete_content.encode('utf-8')).decode('ascii')
        
        script_setup_complete = f"""
        $setupDir = '{win_drive}:\\Windows\\Setup\\Scripts'
        New-Item -ItemType Directory -Path $setupDir -Force -ErrorAction SilentlyContinue | Out-Null
        
        $content = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{setup_b64}'))
        [System.IO.File]::WriteAllText("$setupDir\\SetupComplete.cmd", $content)
        
        Write-Output "SetupComplete.cmd created"
        """
        
        await self._execute(script_setup_complete, timeout=30)
        logger.debug("hyperv_dism_setup_complete_created", vm_id=vm_id)
        
        # Étape 4: Configurer le bootloader
        script_boot = f"""
        bcdboot {win_drive}:\\Windows /s {efi_drive}: /f UEFI
        if ($LASTEXITCODE -eq 0) {{
            Write-Output "BOOT_SUCCESS"
        }} else {{
            throw "BCDBoot failed with exit code $LASTEXITCODE"
        }}
        """
        
        result = await self._execute(script_boot, timeout=60)
        if not result.success or "BOOT_SUCCESS" not in (result.stdout or ""):
            raise VMOperationError(vm_id, "deploy_dism_boot", result.stderr or result.stdout)
        
        logger.debug("hyperv_dism_bootloader_configured", vm_id=vm_id)
        
        # Étape 5: Nettoyer et configurer la VM
        script_finalize = f"""
        # Démonter ISO et VHD
        Dismount-DiskImage -ImagePath '{iso_path}'
        Dismount-VHD -Path '{vhd_path}'
        
        # Configurer la VM pour booter sur le disque dur
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        
        if ($vm) {{
            # Éjecter le DVD s'il est monté
            Get-VMDvdDrive -VM $vm | Remove-VMDvdDrive -ErrorAction SilentlyContinue
            
            # Configurer le boot sur le disque dur
            $hdd = Get-VMHardDiskDrive -VM $vm | Where-Object {{ $_.ControllerLocation -eq 0 }}
            if ($hdd) {{
                Set-VMFirmware -VM $vm -FirstBootDevice $hdd
            }}
            
            # Corriger les permissions sur le VHDX pour Hyper-V
            $vmId = $vm.VMId.ToString()
            $vhdPath = '{vhd_path}'
            $acl = Get-Acl $vhdPath
            
            # Ajouter permissions pour "NT VIRTUAL MACHINE\\Virtual Machines"
            try {{
                $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
                    "NT VIRTUAL MACHINE\\Virtual Machines",
                    "FullControl",
                    "Allow"
                )
                $acl.AddAccessRule($rule)
            }} catch {{ }}
            
            # Ajouter permissions pour le compte VM spécifique
            try {{
                $rule2 = New-Object System.Security.AccessControl.FileSystemAccessRule(
                    "NT VIRTUAL MACHINE\\$vmId",
                    "FullControl",
                    "Allow"
                )
                $acl.AddAccessRule($rule2)
            }} catch {{ }}
            
            Set-Acl $vhdPath $acl -ErrorAction SilentlyContinue
            
            Write-Output "FINALIZE_SUCCESS"
        }} else {{
            throw "VM not found"
        }}
        """
        
        result = await self._execute(script_finalize, timeout=60)
        if not result.success:
            raise VMOperationError(vm_id, "deploy_dism_finalize", result.stderr)
        
        logger.info("hyperv_deploy_dism_complete", vm_id=vm_id)
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

    # =========================================================================
    # Détails complets VM
    # =========================================================================

    async def get_vm_full_details(self, vm_id: str) -> dict[str, Any]:
        """
        Récupère les détails complets d'une VM.
        
        Args:
            vm_id: ID ou nom de la VM
            
        Returns:
            Dictionnaire avec tous les détails
        """
        # Script compact pour éviter la limite de longueur WinRM
        script = f"""
$v=Get-VM -Name '{vm_id}' -EA 0;if(!$v){{$v=Get-VM|?{{$_.VMId.ToString()-eq'{vm_id}'}}}}
if(!$v){{throw "VM not found"}}
$r=@{{general=@{{id=$v.VMId.ToString();name=$v.Name;state=$v.State.ToString();status=$v.Status;generation=$v.Generation;version=$v.Version;path=$v.Path;uptime=if($v.Uptime){{$v.Uptime.ToString()}}else{{$null}}}};configuration=@{{cpu_count=$v.ProcessorCount;ram_startup_gb=[math]::Round($v.MemoryStartupBytes/1GB,2);ram_minimum_gb=if($v.DynamicMemoryEnabled){{[math]::Round($v.MemoryMinimum/1GB,2)}}else{{$null}};ram_maximum_gb=if($v.DynamicMemoryEnabled){{[math]::Round($v.MemoryMaximum/1GB,2)}}else{{$null}};dynamic_memory=$v.DynamicMemoryEnabled;secure_boot=$null;tpm_enabled=$null}};resources=@{{cpu_usage_percent=$v.CPUUsage;ram_assigned_gb=[math]::Round($v.MemoryAssigned/1GB,2);ram_demand_gb=[math]::Round($v.MemoryDemand/1GB,2)}};disks=@();network_adapters=@();integration_services=@();checkpoints=@()}}
if($v.Generation-eq 2){{$fw=Get-VMFirmware -VM $v -EA 0;if($fw){{$r.configuration.secure_boot=$fw.SecureBoot-eq'On'}};$tpm=Get-VMTpm -VM $v -EA 0;if($tpm){{$r.configuration.tpm_enabled=$true}}}}
Get-VMHardDiskDrive -VM $v|%{{$vhd=Get-VHD -Path $_.Path -EA 0;$d=@{{path=$_.Path;controller_type=$_.ControllerType.ToString();controller_number=$_.ControllerNumber;controller_location=$_.ControllerLocation}};if($vhd){{$d.size_gb=[math]::Round($vhd.Size/1GB,2);$d.size_used_gb=[math]::Round($vhd.FileSize/1GB,2);$d.format=$vhd.VhdFormat.ToString();$d.type=$vhd.VhdType.ToString()}};$r.disks+=$d}}
Get-VMNetworkAdapter -VM $v|%{{$vl=Get-VMNetworkAdapterVlan -VMNetworkAdapter $_ -EA 0;$r.network_adapters+=@{{name=$_.Name;switch_name=$_.SwitchName;mac_address=$_.MacAddress;vlan_id=if($vl-and$vl.AccessVlanId-gt 0){{$vl.AccessVlanId}}else{{$null}};ip_addresses=@($_.IPAddresses);status=$_.Status.ToString()}}}}
Get-VMIntegrationService -VM $v|%{{$r.integration_services+=@{{name=$_.Name;enabled=$_.Enabled;status=$_.PrimaryOperationalStatus.ToString()}}}}
Get-VMCheckpoint -VM $v -EA 0|%{{$r.checkpoints+=@{{id=$_.Id.ToString();name=$_.Name;creation_time=$_.CreationTime.ToString('o')}}}}
$r|ConvertTo-Json -Depth 4
"""
        
        result = await self._execute(script, timeout=60)
        
        if not result.success:
            raise HypervisorError(
                f"Failed to get VM details: {result.stderr}",
                {"vm_id": vm_id},
            )
        
        data = self._parse_json_output(result.stdout)
        
        if data is None:
            raise HypervisorError(
                f"Failed to parse VM details: empty response",
                {"vm_id": vm_id},
            )
        
        logger.info("hyperv_vm_details_retrieved", vm_id=vm_id)
        return data

    async def get_vm_screenshot(
        self,
        vm_id: str,
        width: int = 640,
        height: int = 480,
    ) -> str | None:
        """
        Capture un screenshot de l'écran de la VM.
        
        Utilise WMI pour obtenir une image thumbnail de la VM.
        L'image est convertie de RGB16 brut vers PNG.
        
        Args:
            vm_id: ID ou nom de la VM
            width: Largeur de l'image (défaut 640)
            height: Hauteur de l'image (défaut 480)
            
        Returns:
            Image en base64 (format PNG) ou None si échec
        """
        script = f"""
        $ErrorActionPreference = 'Stop'
        
        # Trouver la VM
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        if (-not $vm) {{
            throw "VM not found: {vm_id}"
        }}
        
        # Vérifier que la VM est en cours d'exécution
        if ($vm.State -ne 'Running') {{
            throw "VM must be running to capture screenshot"
        }}
        
        # Obtenir le service de management via WMI
        $vmName = $vm.Name
        $ns = "root\\virtualization\\v2"
        
        # Récupérer les settings de la VM
        $vmWmi = Get-WmiObject -Namespace $ns -Query "SELECT * FROM Msvm_ComputerSystem WHERE ElementName='$vmName'" | Select-Object -First 1
        
        if (-not $vmWmi) {{
            throw "Cannot find VM in WMI"
        }}
        
        # Récupérer les settings data
        $vmSettingsQuery = "ASSOCIATORS OF {{$($vmWmi.__PATH)}} WHERE AssocClass=Msvm_SettingsDefineState ResultClass=Msvm_VirtualSystemSettingData"
        $vmSettings = Get-WmiObject -Namespace $ns -Query $vmSettingsQuery | Select-Object -First 1
        
        if (-not $vmSettings) {{
            throw "Cannot find VM settings"
        }}
        
        # Obtenir le service de management
        $vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
        
        # Capturer le thumbnail
        $result = $vsms.GetVirtualSystemThumbnailImage($vmSettings.__PATH, {width}, {height})
        
        if ($result.ReturnValue -ne 0) {{
            throw "Failed to capture screenshot. Return code: $($result.ReturnValue)"
        }}
        
        # Retourner les infos: width, height et données en base64
        @{{
            Width = {width}
            Height = {height}
            Data = [Convert]::ToBase64String($result.ImageData)
        }} | ConvertTo-Json -Compress
        """
        
        result = await self._execute(script, timeout=30)
        
        if not result.success:
            logger.warning(
                "hyperv_screenshot_failed",
                vm_id=vm_id,
                error=result.stderr,
            )
            return None
        
        # Parser le JSON
        data = self._parse_json_output(result.stdout)
        
        if not data or not data.get("Data"):
            logger.warning("hyperv_screenshot_empty", vm_id=vm_id)
            return None
        
        # Convertir RGB16 brut en PNG
        try:
            import base64
            from io import BytesIO
            from PIL import Image
            
            # Décoder les données base64
            raw_data = base64.b64decode(data["Data"])
            img_width = data.get("Width", width)
            img_height = data.get("Height", height)
            
            # Les données Hyper-V ont un header de 4 bytes
            # Format: 2 bytes width + 2 bytes height (ou autre metadata)
            header_size = 4
            if len(raw_data) > img_width * img_height * 2:
                raw_data = raw_data[header_size:]
            
            # Calculer le nombre de pixels attendu
            expected_pixels = img_width * img_height
            actual_pixels = len(raw_data) // 2
            
            # Ajuster les dimensions si nécessaire
            if actual_pixels != expected_pixels:
                logger.warning(
                    "hyperv_screenshot_size_mismatch",
                    expected=expected_pixels,
                    actual=actual_pixels,
                )
            
            # Les données sont en RGB565 (16 bits par pixel)
            # Convertir en RGB888
            pixels = []
            for i in range(0, min(len(raw_data), expected_pixels * 2), 2):
                if i + 1 < len(raw_data):
                    # Little endian
                    pixel = raw_data[i] | (raw_data[i + 1] << 8)
                    # RGB565: RRRRRGGGGGGBBBBB
                    r = ((pixel >> 11) & 0x1F) << 3
                    g = ((pixel >> 5) & 0x3F) << 2
                    b = (pixel & 0x1F) << 3
                    pixels.append((r, g, b))
            
            # Compléter si manquant
            while len(pixels) < expected_pixels:
                pixels.append((0, 0, 0))
            
            # Créer l'image
            img = Image.new("RGB", (img_width, img_height))
            img.putdata(pixels[:expected_pixels])
            
            # Sauvegarder en PNG dans un buffer
            buffer = BytesIO()
            img.save(buffer, format="PNG", optimize=True)
            buffer.seek(0)
            
            # Encoder en base64
            png_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
            
            logger.info("hyperv_screenshot_captured", vm_id=vm_id, size=len(png_b64))
            return png_b64
            
        except Exception as e:
            logger.error("hyperv_screenshot_conversion_failed", vm_id=vm_id, error=str(e))
            return None
