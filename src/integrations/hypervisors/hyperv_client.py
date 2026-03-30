# =============================================================================
# VM Automation - Hyper-V Client
# =============================================================================
"""
Client pour l'interaction avec les hôtes Hyper-V via PowerShell/WinRM.
"""

import json
import re
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
    WINRM_AVAILABLE,
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


def _escape_ps(value: str) -> str:
    """Escape value for safe use in PowerShell single-quoted strings."""
    if not isinstance(value, str):
        value = str(value)
    # In single-quoted PowerShell strings, only single quotes need doubling
    # But we also sanitize for use in double-quoted contexts
    value = value.replace("'", "''")
    # Remove null bytes and control characters (except newline/tab)
    value = ''.join(c for c in value if c in ('\n', '\t', '\r') or (ord(c) >= 32))
    return value


def _validate_hostname(hostname: str) -> str:
    """Validate and return hostname, raise if invalid."""
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9\-]{0,14}$', hostname):
        raise ValueError(f"Invalid hostname: {hostname!r}")
    return hostname


def _validate_path(path: str) -> str:
    """Validate Windows file path."""
    if not re.match(r'^[A-Z]:\\[\w\\\.\-\s]+$', path, re.IGNORECASE):
        raise ValueError(f"Invalid path: {path!r}")
    return path


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
        self.temp_path = settings.hyperv_temp_path
        self.unattend_path = settings.hyperv_unattend_path

    async def _execute(
        self,
        script: str,
        timeout: int | None = None,
    ) -> PowerShellResult:
        """Exécute un script PowerShell."""
        return await self._executor.execute_async(script, timeout)

    def _parse_json_output(self, output: str) -> Any:
        """Parse la sortie JSON d'une commande PowerShell.

        Supporte les JSON imbriqués en utilisant un compteur de profondeur
        au lieu d'une regex simple qui ne gère que les objets plats.
        """
        if not output or not output.strip():
            return None

        text = output.strip()

        # Essayer de parser le texte entier directement
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Chercher un objet/tableau JSON avec gestion des imbrications
        start = text.find('{')
        arr_start = text.find('[')
        # Prendre le premier trouvé
        if start == -1 or (arr_start != -1 and arr_start < start):
            start = arr_start
        if start == -1:
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

        bracket = text[start]
        close_bracket = '}' if bracket == '{' else ']'
        depth = 0
        in_string = False
        escape_next = False
        for i, c in enumerate(text[start:], start):
            if escape_next:
                escape_next = False
                continue
            if c == '\\' and in_string:
                escape_next = True
                continue
            if c == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == bracket:
                depth += 1
            elif c == close_bracket:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break

        # Fallback: chercher la dernière ligne qui ressemble à du JSON
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
            $nic = Get-VMNetworkAdapter -VMName $vm.Name -ErrorAction SilentlyContinue | Select-Object -First 1
            
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
        safe_id = _escape_ps(vm_id)
        script = f"""
        $vm = Get-VM -Name '{safe_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{safe_id}' }}
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

    async def create_vm(self, specs: VMSpecs, force: bool = False) -> VMInfo:
        """
        Crée une nouvelle VM avec les spécifications données.
        
        Args:
            specs: Spécifications de la VM
            force: Si True, supprime la VM existante avant de créer (pour retry)
        """
        
        # Construire les chemins VM et VHDX
        # Si vhdx_path est spécifié, on utilise le même répertoire pour tout (VM + VHDX)
        if specs.vhdx_path:
            if specs.vhdx_path.lower().endswith(".vhdx"):
                # Chemin complet fourni - extraire le dossier parent
                vhdx_path = specs.vhdx_path
                base_path = specs.vhdx_path.rsplit("\\", 1)[0]
            else:
                # C'est un dossier, l'utiliser pour tout
                base_path = specs.vhdx_path.rstrip(chr(92))
                vhdx_path = f"{base_path}\\{specs.name}.vhdx"
            # Utiliser le même répertoire pour les fichiers de la VM
            vm_path = base_path
        else:
            # Chemins par défaut
            vm_path = specs.vm_path or self.vm_path
            vhdx_path = f"{self.vhdx_path}\\{specs.name}.vhdx"
        
        logger.info(
            "hyperv_creating_vm",
            name=specs.name,
            cpu=specs.cpu_count,
            ram_gb=specs.ram_gb,
            disk_gb=specs.disk_gb,
            generation=specs.generation,
            force=force,
        )
        
        # Script de création de VM
        if force:
            force_cleanup = f"""
        # Supprimer la VM existante si force=True
        $existingVm = Get-VM -Name '{specs.name}' -ErrorAction SilentlyContinue
        if ($existingVm) {{
            Write-Warning "VM existante détectée, suppression forcée: {specs.name}"
            # Arrêter la VM si elle est en cours d'exécution
            if ($existingVm.State -eq 'Running') {{
                Stop-VM -VM $existingVm -Force -ErrorAction SilentlyContinue
            }}
            # Supprimer la VM et ses disques
            Remove-VM -VM $existingVm -Force -ErrorAction Stop
            # Attendre un peu pour que la suppression soit complète
            Start-Sleep -Seconds 2
        }}
        """
        else:
            force_cleanup = f"""
        # Vérifier que la VM n'existe pas déjà (si force=False)
        $existingVm = Get-VM -Name '{specs.name}' -ErrorAction SilentlyContinue
        if ($existingVm) {{
            throw "Une VM avec le nom '{specs.name}' existe déjà. Supprimez-la d'abord."
        }}
        """
        
        script = f"""
        $ErrorActionPreference = 'Stop'
        
        {force_cleanup}
        
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
        
        # Fix VHD permissions for Hyper-V Virtual Machine service (SID S-1-5-83-0)
        $acl = Get-Acl '{vhdx_path}'
        $sid = New-Object System.Security.Principal.SecurityIdentifier("S-1-5-83-0")
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($sid, "FullControl", "Allow")
        $acl.AddAccessRule($rule)
        Set-Acl -Path '{vhdx_path}' -AclObject $acl

        # Configurer le processeur
        Set-VMProcessor -VMName $vm.Name -Count {specs.cpu_count}
        
        # Configurer le VLAN si spécifié
        {f"Set-VMNetworkAdapterVlan -VMName $vm.Name -Access -VlanId {specs.vlan_id}" if specs.vlan_id else ""}
        
        # Ajouter un lecteur DVD si ISO spécifié
        {f"Add-VMDvdDrive -VMName $vm.Name -Path '{specs.iso_path}'" if specs.iso_path else "Add-VMDvdDrive -VMName $vm.Name"}
        
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

        safe_id = _escape_ps(vm_id)
        script = f"""
        $ErrorActionPreference = 'Stop'
        $vm = Get-VM -Name '{safe_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{safe_id}' }}
        }}

        if (-not $vm) {{
            # VM n'existe pas sur l'hyperviseur - considéré comme un succès
            Write-Output "VM not found on hypervisor (already deleted or never created): {safe_id}"
            exit 0
        }}
        
        # Arrêter la VM si elle tourne ou dans un état intermédiaire
        if ($vm.State -ne 'Off') {{
            try {{
                Stop-VM -VMName $vm.Name -Force -TurnOff -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 2
            }} catch {{
                Write-Warning "Could not stop VM: $_"
            }}
        }}
        
        {"# Récupérer les chemins des disques avant suppression" if delete_disks else ""}
        {'''$disks = @()
        try {
            $disks = Get-VMHardDiskDrive -VMName $vm.Name -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Path
        } catch { }''' if delete_disks else ""}
        
        # Supprimer la VM
        try {{
            Remove-VM -VMName $vm.Name -Force
        }} catch {{
            Write-Warning "Error removing VM: $_"
            throw
        }}
        
        {"# Supprimer les disques" if delete_disks else ""}
        {'''foreach ($disk in $disks) {
            if ($disk -and (Test-Path $disk)) {
                try { Remove-Item -Path $disk -Force -ErrorAction SilentlyContinue } catch { }
            }
        }''' if delete_disks else ""}
        
        Write-Output "VM deleted successfully"
        """
        
        result = await self._execute(script)
        
        if not result.success:
            raise VMOperationError(vm_id, "delete", result.stderr)
        
        logger.info("hyperv_vm_deleted", vm_id=vm_id)
        return True

    async def start_vm(self, vm_id: str) -> bool:
        """Démarre une VM."""
        safe_id = _escape_ps(vm_id)
        script = f"""
        $vm = Get-VM -Name '{safe_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{safe_id}' }}
        }}
        if ($vm) {{
            Start-VM -VMName $vm.Name
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
        safe_id = _escape_ps(vm_id)
        script = f"""
        $vm = Get-VM -Name '{safe_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{safe_id}' }}
        }}
        if ($vm) {{
            Stop-VM -VMName $vm.Name -Force {force_param}
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
        safe_id = _escape_ps(vm_id)
        script = f"""
        $vm = Get-VM -Name '{safe_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{safe_id}' }}
        }}
        if ($vm) {{
            Restart-VM -VMName $vm.Name {force_param}
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
        safe_id = _escape_ps(vm_id)
        script = f"""
        $vm = Get-VM -Name '{safe_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{safe_id}' }}
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

    async def check_disk_space(
        self,
        path: str | None = None,
        required_gb: float = 0,
    ) -> dict[str, Any]:
        """
        Vérifie l'espace disque disponible sur l'hyperviseur.

        Args:
            path: Chemin à vérifier (par défaut: temp_path configuré).
                  La lettre de lecteur est extraite automatiquement.
            required_gb: Espace requis en Go. Si > 0, lève une erreur si insuffisant.

        Returns:
            Dict avec total_gb, free_gb, used_gb, percent_used, drive_letter.
        """
        check_path = path or self.temp_path
        # Extraire la lettre de lecteur (ex: "D" depuis "D:\\HyperV\\Temp")
        drive_letter = check_path[0] if len(check_path) >= 2 and check_path[1] == ":" else "C"

        script = f"""
        $drive = Get-PSDrive -Name '{drive_letter}' -ErrorAction Stop
        $totalGB = [math]::Round(($drive.Used + $drive.Free) / 1GB, 2)
        $freeGB = [math]::Round($drive.Free / 1GB, 2)
        $usedGB = [math]::Round($drive.Used / 1GB, 2)
        $pctUsed = if ($totalGB -gt 0) {{ [math]::Round(($usedGB / $totalGB) * 100, 1) }} else {{ 0 }}
        @{{
            drive_letter = '{drive_letter}'
            total_gb = $totalGB
            free_gb = $freeGB
            used_gb = $usedGB
            percent_used = $pctUsed
        }} | ConvertTo-Json
        """

        result = await self._execute(script, timeout=30)
        if not result.success:
            logger.warning("hyperv_disk_space_check_failed", error=result.stderr, path=check_path)
            return {"drive_letter": drive_letter, "total_gb": 0, "free_gb": 0, "used_gb": 0, "percent_used": 0}

        data = self._parse_json_output(result.stdout) or {}

        free_gb = float(data.get("free_gb", 0))
        if required_gb > 0 and free_gb < required_gb:
            raise VMOperationError(
                check_path,
                "check_disk_space",
                f"Espace disque insuffisant sur {drive_letter}: "
                f"{free_gb:.1f} Go disponible, {required_gb:.1f} Go requis",
            )

        logger.info(
            "hyperv_disk_space_checked",
            drive=drive_letter,
            free_gb=free_gb,
            required_gb=required_gb,
        )
        return data

    async def find_orphan_vhdx(
        self,
        paths: list[str] | None = None,
        delete: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Trouve les fichiers VHDX qui ne sont attachés à aucune VM.

        Args:
            paths: Dossiers à scanner (défaut: vhdx_path + vm_path).
            delete: Si True, supprime les orphelins trouvés.

        Returns:
            Liste de dicts avec path, size_gb, last_modified pour chaque orphelin.
        """
        default_paths = [self.vhdx_path, self.vm_path]
        # Toujours scanner l'ancien emplacement C:\ pour trouver les orphelins hérités
        for legacy in ["C:\\HyperV\\VirtualHardDisks", "C:\\HyperV\\VirtualMachines"]:
            if legacy not in default_paths:
                default_paths.append(legacy)
        scan_paths = paths or default_paths
        ps_paths = ", ".join(f"'{_escape_ps(p)}'" for p in scan_paths)

        script = f"""
        $ErrorActionPreference = 'Stop'
        $scanPaths = @({ps_paths})

        # 1. Récupérer tous les VHDX attachés à des VMs
        $attachedVhdx = @{{}}
        Get-VM | Get-VMHardDiskDrive | ForEach-Object {{
            if ($_.Path) {{ $attachedVhdx[$_.Path.ToLower()] = $true }}
        }}

        # 2. Scanner les dossiers
        $orphans = @()
        foreach ($dir in $scanPaths) {{
            if (-not (Test-Path $dir)) {{ continue }}
            Get-ChildItem -Path $dir -Filter '*.vhdx' -Recurse -ErrorAction SilentlyContinue | ForEach-Object {{
                if (-not $attachedVhdx.ContainsKey($_.FullName.ToLower())) {{
                    $orphans += [PSCustomObject]@{{
                        path          = $_.FullName
                        size_gb       = [math]::Round($_.Length / 1GB, 2)
                        size_bytes    = $_.Length
                        last_modified = $_.LastWriteTime.ToString('yyyy-MM-ddTHH:mm:ss')
                        parent_folder = $_.DirectoryName
                    }}
                }}
            }}
        }}

        # 3. Suppression si demandée
        $deleted = $false
        {"" if not delete else '''
        foreach ($o in $orphans) {
            Remove-Item $o.path -Force -ErrorAction SilentlyContinue
        }
        $deleted = $true
        '''}

        @{{
            orphans       = $orphans
            total_count   = $orphans.Count
            total_size_gb = [math]::Round(($orphans | Measure-Object -Property size_bytes -Sum).Sum / 1GB, 2)
            deleted       = $deleted
        }} | ConvertTo-Json -Depth 3
        """

        result = await self._execute(script, timeout=120)
        if not result.success:
            logger.warning("hyperv_orphan_vhdx_scan_failed", error=result.stderr)
            return []

        data = self._parse_json_output(result.stdout) or {}
        orphans = data.get("orphans", [])
        if isinstance(orphans, dict):
            orphans = [orphans]

        total_gb = data.get("total_size_gb", 0)
        logger.info(
            "hyperv_orphan_vhdx_found",
            count=len(orphans),
            total_size_gb=total_gb,
            deleted=delete,
        )
        return orphans

    async def ensure_paths_exist(self) -> None:
        """Crée les dossiers de stockage sur l'hyperviseur s'ils n'existent pas."""
        paths = [self.vm_path, self.vhdx_path, self.iso_path, self.temp_path, self.unattend_path]
        conditions = " ".join(
            f"if (-not (Test-Path '{_escape_ps(p)}')) {{ New-Item -ItemType Directory -Path '{_escape_ps(p)}' -Force | Out-Null }}"
            for p in paths
        )
        script = f"$ErrorActionPreference = 'Stop'\n{conditions}\nWrite-Output 'PATHS_OK'"
        result = await self._execute(script, timeout=30)
        if not result.success or "PATHS_OK" not in (result.stdout or ""):
            logger.warning("hyperv_ensure_paths_failed", error=result.stderr)

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
        safe_id = _escape_ps(vm_id)
        safe_iso = _escape_ps(iso_path)
        script = f"""
        $vm = Get-VM -Name '{safe_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{safe_id}' }}
        }}
        if ($vm) {{
            # Attacher l'ISO d'installation au slot explicite (Controller 0, Location 1)
            # Le seed ISO ira sur (0, 2) via _create_and_attach_seed_iso
            $dvd = Get-VMDvdDrive -VMName $vm.Name | Where-Object {{ $_.ControllerNumber -eq 0 -and $_.ControllerLocation -eq 1 }}
            if (-not $dvd) {{
                Add-VMDvdDrive -VMName $vm.Name -ControllerNumber 0 -ControllerLocation 1 -Path '{safe_iso}'
            }} else {{
                Set-VMDvdDrive -VMName $vm.Name -ControllerNumber 0 -ControllerLocation 1 -Path '{safe_iso}'
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

    async def remaster_iso_with_preseed(
        self,
        original_iso_path: str,
        preseed_file_path: str,
        vm_name: str = "",
    ) -> str:
        """
        Remaster a Debian netinst ISO to embed a preseed.cfg file.

        Two WinRM calls:
        1. Extract ISO, inject preseed, modify boot configs
        2. Rebuild ISO using oscdimg.exe (Windows ADK)

        Returns:
            The absolute path to the remastered ISO on the Hyper-V host.
        """
        safe_original = _escape_ps(original_iso_path)
        safe_preseed = _escape_ps(preseed_file_path)
        safe_vm = _escape_ps(vm_name or "preseed")
        work_dir = f"{self.temp_path}\\Remaster\\{safe_vm}"
        remastered_iso = f"{self.temp_path}\\Remaster\\{safe_vm}_preseed.iso"

        # ── Step 1: Extract ISO, inject preseed, modify boot configs ──
        extract_script = f"""
        $ErrorActionPreference = 'Stop'
        $origIso = '{safe_original}'
        $isoDir  = '{_escape_ps(work_dir)}\\iso_content'
        $preseed = '{safe_preseed}'

        if (Test-Path $isoDir) {{ Remove-Item $isoDir -Recurse -Force }}
        New-Item -ItemType Directory -Path $isoDir -Force | Out-Null

        $mountResult = Mount-DiskImage -ImagePath $origIso -PassThru
        $driveLetter = ($mountResult | Get-Volume).DriveLetter
        if (-not $driveLetter) {{ throw "Could not mount original ISO" }}
        try {{
            Copy-Item -Path "$($driveLetter):\\*" -Destination $isoDir -Recurse -Force
            Get-ChildItem -Path $isoDir -Recurse | ForEach-Object {{
                $_.Attributes = $_.Attributes -band (-bnot [System.IO.FileAttributes]::ReadOnly)
            }}
        }} finally {{
            Dismount-DiskImage -ImagePath $origIso | Out-Null
        }}

        Copy-Item -Path $preseed -Destination (Join-Path $isoDir 'preseed.cfg') -Force

        $txtCfg = "$isoDir\\isolinux\\txt.cfg"
        if (Test-Path $txtCfg) {{
            $c = Get-Content $txtCfg -Raw
            $c = $c -replace '(append\\s+.*?)(?=\\r?\\n)', '$1 auto=true priority=critical preseed/file=/cdrom/preseed.cfg'
            Set-Content -Path $txtCfg -Value $c -NoNewline
        }}

        $grubCfg = "$isoDir\\boot\\grub\\grub.cfg"
        if (Test-Path $grubCfg) {{
            $c = Get-Content $grubCfg -Raw
            $c = $c -replace '(linux\\s+/install[.a-z]*/vmlinuz\\s+.*?)(?=\\r?\\n)', '$1 auto=true priority=critical preseed/file=/cdrom/preseed.cfg'
            # Set timeout and default entry for automated install (entry 1 = text Install)
            $c = "set timeout=3`nset default=1`n" + $c
            Set-Content -Path $grubCfg -Value $c -NoNewline
        }}

        Write-Output "EXTRACT_OK"
        """

        result = await self._execute(extract_script, timeout=300)
        if not result.success or "EXTRACT_OK" not in (result.stdout or ""):
            raise VMOperationError(
                vm_name, "remaster_iso",
                f"Failed to extract/patch ISO: {result.stderr}",
            )

        # ── Step 2: Rebuild ISO with oscdimg.exe ──
        iso_dir_path = f"{work_dir}\\iso_content"
        rebuild_script = f"""
        $ErrorActionPreference = 'Stop'
        $isoDir    = '{_escape_ps(iso_dir_path)}'
        $outputIso = '{_escape_ps(remastered_iso)}'
        $oscdimg   = '{_escape_ps(settings.oscdimg_path)}'

        if (Test-Path $outputIso) {{ Remove-Item $outputIso -Force }}

        if (-not (Test-Path $oscdimg)) {{ throw "oscdimg.exe not found at: $oscdimg" }}

        $bootBin = "$isoDir\\isolinux\\isolinux.bin"
        $efiBoot = "$isoDir\\boot\\grub\\efi.img"

        if ((Test-Path $bootBin) -and (Test-Path $efiBoot)) {{
            # Use Joliet + ISO 9660 (-j1) instead of UDF (-u2).
            # UDF is not readable by GRUB EFI in Hyper-V Gen2.
            # -j1 provides Joliet long names (used by Linux kernel) + ISO 9660 8.3 fallback.
            # GRUB EFI reads ISO 9660 layer for search --file (short names OK for .disk/id/).
            & $oscdimg -m -o -j1 -lDebian -bootdata:"2#p0,e,b$bootBin#pEF,e,b$efiBoot" $isoDir $outputIso
        }} elseif (Test-Path $bootBin) {{
            & $oscdimg -m -o -j1 -lDebian -b"$bootBin" $isoDir $outputIso
        }} else {{
            & $oscdimg -m -o -j1 -lDebian $isoDir $outputIso
        }}

        if ($LASTEXITCODE -ne 0) {{ throw "oscdimg failed with exit code $LASTEXITCODE" }}
        if (-not (Test-Path $outputIso)) {{ throw "Remastered ISO not created" }}

        $size = (Get-Item $outputIso).Length
        Write-Output "REMASTERED:$($outputIso):$size"
        """

        result = await self._execute(rebuild_script, timeout=600)
        if not result.success or "REMASTERED:" not in (result.stdout or ""):
            raise VMOperationError(
                vm_name, "remaster_iso",
                f"Failed to rebuild ISO: {result.stderr}",
            )

        logger.info(
            "hyperv_iso_remastered",
            vm_name=vm_name,
            original_iso=original_iso_path,
            remastered_iso=remastered_iso,
            output=result.stdout.strip(),
        )

        return remastered_iso

    async def unmount_iso(self, vm_id: str, unmount_all: bool = True) -> bool:
        """
        Démonte les ISOs des lecteurs DVD.

        Args:
            vm_id: ID ou nom de la VM
            unmount_all: Si True, démonte tous les lecteurs DVD. Sinon, juste le premier.
        """
        safe_id = _escape_ps(vm_id)
        if unmount_all:
            script = f"""
            $vm = Get-VM -Name '{safe_id}' -ErrorAction SilentlyContinue
            if (-not $vm) {{
                $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{safe_id}' }}
            }}
            if ($vm) {{
                $count = 0
                Get-VMDvdDrive -VMName $vm.Name | ForEach-Object {{
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
            $vm = Get-VM -Name '{safe_id}' -ErrorAction SilentlyContinue
            if (-not $vm) {{
                $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{safe_id}' }}
            }}
            if ($vm) {{
                $dvd = Get-VMDvdDrive -VMName $vm.Name | Select-Object -First 1
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
        safe_id = _escape_ps(vm_id)
        script = f"""
        $vm = Get-VM -Name '{safe_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{safe_id}' }}
        }}
        if ($vm) {{
            # Rechercher le service Guest (nom peut varier selon la langue)
            $guestSvc = Get-VMIntegrationService -VMName $vm.Name | Where-Object {{ 
                $_.Name -like "*invit*" -or $_.Name -like "*Guest*" 
            }}
            if ($guestSvc) {{
                Enable-VMIntegrationService -VMName $vm.Name -Name $guestSvc.Name
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
        safe_id = _escape_ps(vm_id)
        script = f"""
        $vm = Get-VM -Name '{safe_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{safe_id}' }}
        }}
        if ($vm) {{
            if ($vm.Generation -eq 2) {{
                $device = $null
                switch ('{device_type}') {{
                    'HardDrive' {{ 
                        $device = Get-VMHardDiskDrive -VMName $vm.Name | Select-Object -First 1
                    }}
                    'DVD' {{ 
                        $device = Get-VMDvdDrive -VMName $vm.Name | Select-Object -First 1
                    }}
                    'Network' {{ 
                        $device = Get-VMNetworkAdapter -VMName $vm.Name | Select-Object -First 1
                    }}
                }}
                
                if ($device) {{
                    Set-VMFirmware -VMName $vm.Name -FirstBootDevice $device
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
        escaped_vm_id = _escape_ps(vm_id)

        # Mapping des noms simplifiés vers les types réels Hyper-V
        # BootType possibles : HardDiskDrive, DvdDrive, NetworkAdapter, File
        type_map = {
            "DVD": "Dvd",
            "HardDrive": "HardDisk",
            "Network": "Network",
            "File": "File",
        }
        # Construire les filtres PowerShell
        filters = []
        for device in boot_order:
            pattern = type_map.get(device, device)
            filters.append(
                f"$dev = $allBoot | Where-Object {{ $_.Device -is [Microsoft.HyperV.PowerShell.{pattern}Drive] -or $_.BootType.ToString() -match '{pattern}' }} | Select-Object -First 1\n"
                f"if ($dev) {{ $bootDevices += $dev }}"
            )
        filters_ps = "\n".join(filters)

        script = f"""
        $vm = Get-VM -Name '{escaped_vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{escaped_vm_id}' }}
        }}
        if (-not $vm) {{ throw "VM not found: {escaped_vm_id}" }}

        if ($vm.Generation -eq 2) {{
            $fw = Get-VMFirmware -VMName $vm.Name
            $allBoot = $fw.BootOrder
            $bootDevices = @()

            # Récupérer les devices DVD, HDD, Network par type réel
            {filters_ps}

            if ($bootDevices.Count -gt 0) {{
                Set-VMFirmware -VMName $vm.Name -BootOrder $bootDevices
                Write-Output "Boot order set: $($bootDevices.Count) devices"
            }} else {{
                # Fallback: mettre le DVD en premier directement
                $dvd = Get-VMDvdDrive -VMName $vm.Name | Select-Object -First 1
                $hdd = Get-VMHardDiskDrive -VMName $vm.Name | Select-Object -First 1
                $net = Get-VMNetworkAdapter -VMName $vm.Name | Select-Object -First 1
                $order = @()
                if ($dvd) {{ $order += $dvd }}
                if ($hdd) {{ $order += $hdd }}
                if ($net) {{ $order += $net }}
                if ($order.Count -gt 0) {{
                    Set-VMFirmware -VMName $vm.Name -FirstBootDevice $order[0]
                }}
                Write-Output "Boot order set via FirstBootDevice (fallback)"
            }}
        }} else {{
            Write-Output "Gen1 VM - BIOS boot order not modified"
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
        $unattendDir = '{self.unattend_path}'
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
            Stop-VM -VMName $vm.Name -Force -TurnOff
            Start-Sleep -Seconds 2
        }}
        
        # Supprimer l'ancien disque unattend s'il existe
        Get-VMHardDiskDrive -VMName $vm.Name | Where-Object {{ $_.Path -like '*unattend*' }} | Remove-VMHardDiskDrive -ErrorAction SilentlyContinue
        if (Test-Path $vhdxPath) {{
            Remove-Item $vhdxPath -Force
        }}
        
        # Créer le VHDX
        New-VHD -Path $vhdxPath -SizeBytes 50MB -Dynamic | Out-Null

        # Fix VHD permissions for Hyper-V Virtual Machine service (SID S-1-5-83-0)
        $acl = Get-Acl $vhdxPath
        $sid = New-Object System.Security.Principal.SecurityIdentifier("S-1-5-83-0")
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($sid, "FullControl", "Allow")
        $acl.AddAccessRule($rule)
        Set-Acl -Path $vhdxPath -AclObject $acl

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
            dismount_result = await self._execute(f"Dismount-VHD -Path '{vhdx_path}' -ErrorAction SilentlyContinue")
            if not dismount_result.success:
                logger.warning("vhd_dismount_failed", path=vhdx_path, error=dismount_result.stderr)
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
                dismount_result = await self._execute(f"Dismount-VHD -Path '{vhdx_path}' -ErrorAction SilentlyContinue")
                if not dismount_result.success:
                    logger.warning("vhd_dismount_failed", path=vhdx_path, error=dismount_result.stderr)
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
            dismount_result = await self._execute(f"Dismount-VHD -Path '{vhdx_path}' -ErrorAction SilentlyContinue")
            if not dismount_result.success:
                logger.warning("vhd_dismount_failed", path=vhdx_path, error=dismount_result.stderr)
            raise VMOperationError(vm_id, "inject_unattend_decode", result.stderr)
        
        logger.debug("hyperv_unattend_file_written", vm_id=vm_id)
        
        # Étape 3: Démonter et attacher à la VM, configurer boot order
        script_attach = f"""
        $vmName = '{vm_id}'
        $vhdxPath = '{vhdx_path}'
        
        # Démonter le VHD
        Dismount-VHD -Path $vhdxPath -ErrorAction Stop
        $mounted = Get-VHD -Path $vhdxPath -ErrorAction SilentlyContinue
        if ($mounted.Attached) {{ Write-Error "VHD still mounted after dismount: $vhdxPath" }}

        # Récupérer la VM
        $vm = Get-VM -Name $vmName -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq $vmName }}
        }}
        
        # Attacher le disque unattend à la VM
        Add-VMHardDiskDrive -VMName $vm.Name -Path $vhdxPath -ControllerType SCSI -ControllerNumber 0 -ControllerLocation 2
        
        # Configurer le boot order: DVD en premier
        $dvd = Get-VMDvdDrive -VMName $vm.Name | Select-Object -First 1
        if ($dvd) {{
            Set-VMFirmware -VMName $vm.Name -FirstBootDevice $dvd
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
        $tempDir = '{self.temp_path}\\ISO_Build'
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
            output_iso = f"{self.iso_path}\\{base_name}_AUTO.iso"
        
        script_create_iso = f"""
        $isoContentDir = '{iso_content_dir}'
        $outputIso = '{output_iso}'
        $oscdimg = "{settings.oscdimg_path}"
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

    async def inject_linux_config(
        self,
        vm_name: str,
        config_content: str,
        config_type: str,
        vm_path: str | None = None,
    ) -> bool:
        """
        Injecte une configuration Linux non-interactive via une ISO secondaire attachée à la VM.

        Crée une ISO temporaire contenant le fichier de configuration avec le nom
        et la structure appropriés, puis l'attache comme lecteur DVD à la VM.

        Pour preseed: /preseed.cfg sur l'ISO (label: PRESEED)
        Pour kickstart: /ks.cfg sur l'ISO (label: KSCONFIG)
        Pour autoinstall: /autoinstall/user-data + /autoinstall/meta-data sur l'ISO (label: CIDATA)
        Pour cloud-init: /user-data + /meta-data sur l'ISO (label: cidata)

        Args:
            vm_name: Nom de la VM
            config_content: Contenu du fichier de configuration
            config_type: Type de configuration ("preseed", "kickstart", "autoinstall", "cloud-init")
            vm_path: Chemin de stockage de la VM (optionnel, utilise self.vm_path par défaut)

        Returns:
            True si succès
        """
        logger.info(
            "hyperv_inject_linux_config_start",
            vm_name=vm_name,
            config_type=config_type,
            content_length=len(config_content),
        )

        # Valider le type de configuration
        valid_types = ("preseed", "kickstart", "autoinstall", "cloud-init")
        if config_type not in valid_types:
            logger.error(
                "hyperv_inject_linux_config_invalid_type",
                config_type=config_type,
                valid_types=valid_types,
            )
            return False

        # Déterminer le label ISO et la structure des fichiers selon le type
        type_config = {
            "preseed": {"label": "PRESEED", "files": [("preseed.cfg", config_content)]},
            "kickstart": {"label": "KSCONFIG", "files": [("ks.cfg", config_content)]},
            "autoinstall": {
                "label": "CIDATA",
                "files": [
                    ("autoinstall\\user-data", config_content),
                    ("autoinstall\\meta-data", ""),
                ],
            },
            "cloud-init": {
                "label": "cidata",
                "files": [
                    ("user-data", config_content),
                    ("meta-data", ""),
                ],
            },
        }

        cfg = type_config[config_type]
        label = cfg["label"]
        resolved_vm_path = vm_path or self.vm_path

        escaped_vm_name = _escape_ps(vm_name)
        escaped_label = _escape_ps(label)
        escaped_vm_path = _escape_ps(resolved_vm_path)

        # Encoder les contenus en Base64 pour éviter les limites de longueur WinRM
        import base64
        file_write_commands = ""
        for file_path, content in cfg["files"]:
            escaped_file_path = _escape_ps(file_path)
            # Créer le sous-dossier si nécessaire (ex: autoinstall/)
            if "\\" in file_path:
                subdir = file_path.rsplit("\\", 1)[0]
                escaped_subdir = _escape_ps(subdir)
                file_write_commands += f"""
New-Item -Path "$srcFolder\\{escaped_subdir}" -ItemType Directory -Force | Out-Null
"""
            if content:
                # Encoder en Base64 pour passer le contenu sans limite de taille
                b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
                file_write_commands += f"""
$bytes = [System.Convert]::FromBase64String('{b64}')
[System.IO.File]::WriteAllBytes("$srcFolder\\{escaped_file_path}", $bytes)
"""
            else:
                # Fichier vide (meta-data)
                file_write_commands += f"""
[System.IO.File]::WriteAllText("$srcFolder\\{escaped_file_path}", '', [System.Text.Encoding]::UTF8)
"""

        try:
            script = f"""
$isoPath = '{escaped_vm_path}\\{escaped_vm_name}_seed.iso'
$srcFolder = "$env:TEMP\\{escaped_vm_name}_seed"

# Nettoyer et créer le dossier temporaire
if (Test-Path $srcFolder) {{ Remove-Item $srcFolder -Recurse -Force }}
New-Item -Path $srcFolder -ItemType Directory -Force | Out-Null

# Écrire les fichiers de configuration (décodage Base64)
{file_write_commands}

# Créer l'ISO via l'objet COM IMAPI2FS
$fsi = New-Object -ComObject IMAPI2FS.MsftFileSystemImage
$fsi.FileSystemsToCreate = 3  # FsiFileSystemISO9660 | FsiFileSystemJoliet
$fsi.VolumeName = '{escaped_label}'
$item = $fsi.Root
$item.AddTree($srcFolder, $false)
$ri = $fsi.CreateResultImage()
$istream = $ri.ImageStream

# Écrire le IStream COM dans un fichier via Marshal
$isoDir = [System.IO.Path]::GetDirectoryName($isoPath)
if (-not (Test-Path $isoDir)) {{
    New-Item -Path $isoDir -ItemType Directory -Force | Out-Null
}}
if (Test-Path $isoPath) {{ Remove-Item $isoPath -Force }}

Add-Type -TypeDefinition @"
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
public class IStreamWriter {{
    public static void Save(object comStream, string path) {{
        IStream s = (IStream)comStream;
        using (FileStream fs = new FileStream(path, FileMode.Create, FileAccess.Write)) {{
            byte[] buf = new byte[65536];
            while (true) {{
                int read = 0;
                IntPtr p = Marshal.AllocHGlobal(4);
                try {{
                    s.Read(buf, buf.Length, p);
                    read = Marshal.ReadInt32(p);
                }} finally {{
                    Marshal.FreeHGlobal(p);
                }}
                if (read == 0) break;
                fs.Write(buf, 0, read);
            }}
        }}
    }}
}}
"@
[IStreamWriter]::Save($istream, $isoPath)

# Attacher l'ISO à la VM comme lecteur DVD
Add-VMDvdDrive -VMName '{escaped_vm_name}' -Path $isoPath

# Nettoyer le dossier temporaire
Remove-Item -Path $srcFolder -Recurse -Force

Write-Output "ISO seed créée et attachée: $isoPath"
"""

            result = await self._execute(script, timeout=120)

            if not result.success:
                logger.error(
                    "hyperv_inject_linux_config_failed",
                    vm_name=vm_name,
                    config_type=config_type,
                    error=result.stderr,
                )
                return False

            logger.info(
                "hyperv_inject_linux_config_complete",
                vm_name=vm_name,
                config_type=config_type,
            )
            return True

        except Exception as e:
            logger.error(
                "hyperv_inject_linux_config_error",
                vm_name=vm_name,
                config_type=config_type,
                error=str(e),
            )
            return False


    async def configure_linux_vm(self, vm_name: str) -> bool:
        """
        Configure les paramètres de la VM pour un système Linux.

        - Définit le modèle Secure Boot sur 'MicrosoftUEFICertificateAuthority' (requis pour Linux sur Gen2)
        - Active les Guest Services (services d'intégration)
        - Configure l'ordre de boot : DVD en premier, puis disque dur

        Args:
            vm_name: Nom de la VM

        Returns:
            True si succès
        """
        logger.info("hyperv_configure_linux_vm_start", vm_name=vm_name)

        escaped_vm_name = _escape_ps(vm_name)

        script = f"""
# Configurer Secure Boot pour Linux (template Microsoft UEFI CA)
Set-VMFirmware -VMName '{escaped_vm_name}' -SecureBootTemplate 'MicrosoftUEFICertificateAuthority'

# Activer les Guest Services (services d'intégration)
Enable-VMIntegrationService -VMName '{escaped_vm_name}' -Name 'Guest Service Interface'

# Configurer l'ordre de boot : DVD en premier, puis disque dur
$dvd = Get-VMDvdDrive -VMName '{escaped_vm_name}' | Select-Object -First 1
$hdd = Get-VMHardDiskDrive -VMName '{escaped_vm_name}' | Select-Object -First 1
if ($dvd -and $hdd) {{
    Set-VMFirmware -VMName '{escaped_vm_name}' -BootOrder $dvd, $hdd
}}

Write-Output "VM configurée pour Linux"
"""

        try:
            result = await self._execute(script, timeout=60)

            if not result.success:
                logger.error(
                    "hyperv_configure_linux_vm_failed",
                    vm_name=vm_name,
                    error=result.stderr,
                )
                return False

            logger.info("hyperv_configure_linux_vm_complete", vm_name=vm_name)
            return True

        except Exception as e:
            logger.error(
                "hyperv_configure_linux_vm_error",
                vm_name=vm_name,
                error=str(e),
            )
            return False

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
            $unattendDisk = Get-VMHardDiskDrive -VMName $vm.Name | Where-Object {{ $_.Path -like '*unattend*' }}
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
        admin_username: str | None = None,
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
        $vhdCheck = Get-VHD -Path $vhdPath -ErrorAction SilentlyContinue
        if ($vhdCheck.Attached) {{ Write-Warning "VHD still mounted after pre-cleanup dismount: $vhdPath" }}
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
        # Forcer l'encodage UTF-8 pour éviter les problèmes d'encodage avec DISM
        script_dism = f"""
        $ErrorActionPreference = 'Continue'
        $ProgressPreference = 'SilentlyContinue'
        
        # Forcer l'encodage de la console en UTF-8 pour capturer correctement la sortie DISM
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $OutputEncoding = [System.Text.Encoding]::UTF8
        chcp 65001 | Out-Null
        
        # Capturer la sortie de DISM en redirigeant vers stdout/stderr
        # Utiliser try/catch pour capturer les erreurs sans arrêter le script
        $dismOutput = ""
        $dismError = ""
        $exitCode = 0
        
        try {{
            # Exécuter DISM directement (plus fiable que Start-Process via WinRM)
            $dismResult = Dism /Apply-Image /ImageFile:{iso_drive}:\\sources\\install.wim /Index:{image_index} /ApplyDir:{win_drive}:\\ 2>&1
            $exitCode = $LASTEXITCODE
            
            # Capturer la sortie
            $dismOutput = $dismResult | Out-String
        }} catch {{
            $exitCode = $LASTEXITCODE
            $dismError = $_.Exception.Message
            $dismOutput = $_.Exception.Message
        }}
        
        # Vérifier le code de sortie ET la présence du message de succès dans la sortie
        # DISM retourne 0 en cas de succès, mais on vérifie aussi le message pour être sûr
        $hasSuccessMessage = ($dismOutput -match "op.*ration a r.*ussi" -or 
                             $dismOutput -match "operation completed successfully" -or
                             $dismOutput -match "100\.0%" -or
                             $dismOutput -match "100%")
        
        # Si le code de sortie est 0 OU si on a le message de succès, c'est un succès
        if ($exitCode -eq 0 -or $hasSuccessMessage) {{
            # TOUJOURS écrire DISM_SUCCESS si on détecte un succès
            Write-Output "DISM_SUCCESS"
            # Afficher la sortie pour le logging
            if ($dismOutput) {{
                Write-Output $dismOutput
            }}
        }} else {{
            $errorMsg = "DISM failed with exit code $exitCode"
            if ($dismError) {{
                $errorMsg += ": $dismError"
            }}
            if ($dismOutput) {{
                $errorMsg += " Output: $dismOutput"
            }}
            throw $errorMsg
        }}
        """
        
        result = await self._execute(script_dism, timeout=600)
        
        # Privilégier la présence de "DISM_SUCCESS" dans stdout/stderr plutôt que result.success
        # DISM peut réussir même si PowerShell retourne un code non-zéro à cause d'avertissements
        stdout_content = result.stdout or ""
        stderr_content = result.stderr or ""
        
        # Combiner stdout et stderr pour la recherche (DISM peut écrire dans l'un ou l'autre)
        combined_output = f"{stdout_content}\n{stderr_content}".lower()
        stdout_lower = stdout_content.lower()
        stderr_lower = stderr_content.lower()
        
        # Vérifier si DISM_SUCCESS est présent (insensible à la casse, dans stdout ou stderr)
        has_dism_success = (
            "dism_success" in stdout_lower or
            "dism_success" in stderr_lower
        )
        
        if has_dism_success:
            # Succès confirmé, continuer
            logger.debug("dism_success_confirmed", vm_id=vm_id)
        else:
            # DISM_SUCCESS absent - vérifier si c'est vraiment un échec
            # Chercher aussi les messages de succès dans la sortie (gestion encodage)
            # Patterns pour détecter les messages de succès mal encodés
            success_patterns = [
                "100.0%",  # Progression complète
                "100%",  # Progression complète (variante)
                "opération a réussi",  # Message français correct
                "operation completed successfully",  # Message anglais
                "l'op",  # Début du message français (pour détecter "L'opération")
                "rï¿½ussi",  # "réussi" mal encodé (UTF-8 mal interprété)
                "rÃ©ussi",  # "réussi" mal encodé (autre variante)
                "rÃ©ussi",  # "réussi" mal encodé (encodage Windows)
                "rÃ©ussi",  # "réussi" mal encodé (ISO-8859-1)
            ]
            
            # Vérifier dans stdout et stderr
            has_success_indicator = False
            for pattern in success_patterns:
                if pattern in combined_output:
                    has_success_indicator = True
                    break
            
            # Vérification supplémentaire : "L'op" suivi de "réussi" (même mal encodé)
            if not has_success_indicator:
                if "l'op" in combined_output:
                    # Chercher "réussi" ou ses variantes mal encodées
                    reussi_patterns = ["réussi", "rï¿½ussi", "rÃ©ussi", "rÃ©ussi"]
                    for reussi_pattern in reussi_patterns:
                        if reussi_pattern in combined_output:
                            has_success_indicator = True
                            break
            
            # Vérification finale : présence de "100%" ou "100.0%" dans la sortie
            if not has_success_indicator:
                has_success_indicator = (
                    "100.0%" in stdout_content or
                    "100%" in stdout_content or
                    "100.0%" in stderr_content or
                    "100%" in stderr_content
                )
            
            if has_success_indicator:
                # Message de succès détecté mais DISM_SUCCESS manquant - c'est un problème de script
                logger.warning(
                    "dism_success_marker_missing_but_success_detected",
                    vm_id=vm_id,
                    stdout_preview=stdout_content[:300] if stdout_content else None,
                    stderr_preview=stderr_content[:300] if stderr_content else None,
                )
                # Continuer quand même car on a détecté le succès
            elif not result.success:
                # Pas de succès détecté et result.success = False : vérifier une dernière fois
                # Si on a "100%" ou "100.0%" quelque part, c'est probablement un succès
                final_check = (
                    "100.0%" in combined_output or
                    "100%" in combined_output
                )
                
                if final_check:
                    # On a la progression complète, considérer comme succès malgré result.success = False
                    logger.warning(
                        "dism_success_detected_via_progress",
                        vm_id=vm_id,
                        result_success=result.success,
                    )
                else:
                    # Vraiment aucun indicateur de succès : échec réel
                    await self._execute(f"Dismount-DiskImage -ImagePath '{iso_path}' -ErrorAction SilentlyContinue")
                    dismount_result = await self._execute(f"Dismount-VHD -Path '{vhd_path}' -ErrorAction SilentlyContinue")
                    if not dismount_result.success:
                        logger.warning("vhd_dismount_failed", path=vhd_path, error=dismount_result.stderr)
                    raise VMOperationError(vm_id, "deploy_dism_apply", result.stderr or result.stdout)
            else:
                # DISM_SUCCESS absent, pas de message de succès, mais result.success = True
                # Situation ambiguë - logger et continuer avec avertissement
                logger.warning(
                    "dism_ambiguous_result",
                    vm_id=vm_id,
                    stdout_preview=stdout_content[:300] if stdout_content else None,
                    stderr_preview=stderr_content[:300] if stderr_content else None,
                    result_success=result.success,
                )
        
        logger.debug("hyperv_dism_image_applied", vm_id=vm_id)
        
        # Étape 3: Configuration complète pour automatiser l'OOBE
        # Extraction du mot de passe admin depuis le unattend_content
        admin_password = settings.default_admin_password.get_secret_value()  # Valeur par défaut
        # Déterminer le nom d'utilisateur admin (Admin pour Win10/11, Administrateur pour Server)
        effective_admin_username = admin_username or "otoroot"
        is_client_os = effective_admin_username.lower() == "admin"

        if unattend_content:
            import re
            import base64

            # Essayer d'extraire le mot de passe du unattend.xml
            # Format Server: <AdministratorPassword><Value>...</Value>
            pwd_match = re.search(
                r'<AdministratorPassword>\s*<Value>([^<]+)</Value>',
                unattend_content
            )
            if not pwd_match:
                # Format Client (Win10/11): <LocalAccounts><LocalAccount><Password><Value>...</Value>
                pwd_match = re.search(
                    r'<Password>\s*<Value>([^<]+)</Value>',
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
        
        # Étape 3b: Configurer le registre offline pour bypass OOBE + RunOnce pour setup
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
        
        # AutoLogon configuration - utiliser le bon compte selon l'OS
        $winlogonKey = "HKLM\\OFFLINE_SW\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon"
        reg add $winlogonKey /v AutoAdminLogon /t REG_SZ /d "1" /f
        reg add $winlogonKey /v DefaultUserName /t REG_SZ /d "{effective_admin_username}" /f
        reg add $winlogonKey /v DefaultPassword /t REG_SZ /d "{admin_password}" /f
        reg add $winlogonKey /v AutoLogonCount /t REG_DWORD /d 5 /f
        
        # Activer RDP directement dans le registre offline (avant le premier boot)
        # Cela garantit que RDP est actif même si setup.ps1 ou FirstLogonCommands échouent
        $termSrvKey = "HKLM\\OFFLINE_SYS\\ControlSet001\\Control\\Terminal Server"
        reg add $termSrvKey /v fDenyTSConnections /t REG_DWORD /d 0 /f
        $rdpTcpKey = "HKLM\\OFFLINE_SYS\\ControlSet001\\Control\\Terminal Server\\WinStations\\RDP-Tcp"
        reg add $rdpTcpKey /v UserAuthentication /t REG_DWORD /d 0 /f

        # RunOnce - Exécuter le script de configuration VM-Automation au premier boot
        # Cette clé s'exécute automatiquement après le logon de l'utilisateur
        $runOnceKey = "HKLM\\OFFLINE_SW\\Microsoft\\Windows\\CurrentVersion\\RunOnce"
        reg add $runOnceKey /v "VM-Automation-Setup" /t REG_SZ /d "powershell.exe -ExecutionPolicy Bypass -File C:\\VM-Automation\\setup.ps1" /f

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
        
        # Étape 3c: Créer le script VM-Automation pour configurer Windows au premier boot
        # Ce script est exécuté par RunOnce après le logon automatique
        setup_ps1_content = f"""# =============================================================================
# VM-Automation Setup Script
# Exécuté automatiquement au premier boot via RunOnce
# =============================================================================
$ErrorActionPreference = 'Continue'
$logFile = "C:\\VM-Automation\\setup.log"

# Créer le dossier de log s'il n'existe pas
if (-not (Test-Path "C:\\VM-Automation")) {{
    New-Item -ItemType Directory -Path "C:\\VM-Automation" -Force | Out-Null
}}

function Write-Log {{
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp - $Message" | Out-File -FilePath $logFile -Append -Encoding UTF8
    Write-Host $Message
}}

Write-Log "=========================================="
Write-Log "VM-Automation Setup Starting..."
Write-Log "=========================================="

try {{
    # 1. Configurer les comptes admin selon le type d'OS
    Write-Log "Configuring admin accounts (admin_username={effective_admin_username}, is_client_os={'true' if is_client_os else 'false'})..."

    # Toujours activer et configurer Administrateur (FR) et Administrator (EN)
    $result = net user Administrateur "{admin_password}" /active:yes 2>&1
    Write-Log "Administrateur account result: $result"
    $result = net user Administrator "{admin_password}" /active:yes 2>&1
    Write-Log "Administrator account result: $result"

    # Pour Windows 10/11 : créer le compte Admin s'il n'existe pas déjà
    if ("{effective_admin_username}" -ne "Administrateur" -and "{effective_admin_username}" -ne "Administrator") {{
        $userExists = net user "{effective_admin_username}" 2>&1
        if ($LASTEXITCODE -ne 0) {{
            Write-Log "Creating {effective_admin_username} account..."
            net user "{effective_admin_username}" "{admin_password}" /add /active:yes 2>&1
            net localgroup Administrators "{effective_admin_username}" /add 2>&1
            net localgroup Administrateurs "{effective_admin_username}" /add 2>&1
            Write-Log "{effective_admin_username} account created and added to Administrators"
        }} else {{
            Write-Log "{effective_admin_username} account already exists, setting password..."
            net user "{effective_admin_username}" "{admin_password}" 2>&1
        }}
    }}
    
    # 2. Configurer le profil réseau en Privé
    Write-Log "Setting network profile to Private..."
    Get-NetConnectionProfile | Set-NetConnectionProfile -NetworkCategory Private -ErrorAction SilentlyContinue
    Write-Log "Network profile configured"
    
    # 3. Configurer WinRM pour PowerShell Direct
    Write-Log "Configuring WinRM..."
    Enable-PSRemoting -Force -SkipNetworkProfileCheck -ErrorAction SilentlyContinue
    Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value '*' -Force -ErrorAction SilentlyContinue
    winrm quickconfig -quiet 2>&1 | Out-Null
    Write-Log "WinRM configured"
    
    # 4. Activer RDP + désactiver NLA + firewall FR/EN
    Write-Log "Enabling Remote Desktop..."
    Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -Name "fDenyTSConnections" -Value 0 -ErrorAction SilentlyContinue
    Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp' -Name "UserAuthentication" -Value 0 -ErrorAction SilentlyContinue
    Enable-NetFirewallRule -DisplayGroup "Remote Desktop" -ErrorAction SilentlyContinue
    Enable-NetFirewallRule -DisplayGroup "Bureau a distance" -ErrorAction SilentlyContinue
    # Fallback netsh pour les cas où Enable-NetFirewallRule échoue
    netsh advfirewall firewall set rule group="Remote Desktop" new enable=Yes 2>&1 | Out-Null
    netsh advfirewall firewall set rule group="Bureau a distance" new enable=Yes 2>&1 | Out-Null
    Write-Log "Remote Desktop enabled (NLA disabled, firewall FR+EN)"

    # 4b. Pour Windows Home/Home N : installer RDPWrap pour activer le serveur RDP
    $editionId = (Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion' -ErrorAction SilentlyContinue).EditionID
    Write-Log "Windows EditionID: $editionId"
    if ($editionId -match "Core") {{
        Write-Log "Windows Home detected - installing RDPWrap for RDP support..."
        try {{
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            $rdpWrapUrl = "https://github.com/stascorp/rdpwrap/releases/download/v1.6.2/RDPWrap-v1.6.2.zip"
            $zipPath = "C:\\RDPWrap.zip"
            $extractPath = "C:\\RDPWrap"
            Invoke-WebRequest -Uri $rdpWrapUrl -OutFile $zipPath -UseBasicParsing -ErrorAction Stop
            Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force
            $installer = Get-ChildItem $extractPath -Filter "RDPWInst.exe" -Recurse | Select-Object -First 1
            if ($installer) {{
                & $installer.FullName -i 2>&1 | Out-Null
                Write-Log "RDPWrap installed"
            }}
            # Update with community INI for latest Windows builds
            net stop TermService /y 2>&1 | Out-Null
            Start-Sleep 2
            $iniUrl = "https://raw.githubusercontent.com/sebaxakerhtc/rdpwrap.ini/master/rdpwrap.ini"
            $iniPath = "C:\\Program Files\\RDP Wrapper\\rdpwrap.ini"
            Invoke-WebRequest -Uri $iniUrl -OutFile $iniPath -UseBasicParsing -ErrorAction Stop
            Write-Log "Updated rdpwrap.ini from community"
            net start TermService 2>&1 | Out-Null
            Start-Sleep 3
            $listener = Get-NetTCPConnection -LocalPort 3389 -ErrorAction SilentlyContinue
            Write-Log "RDP listeners after RDPWrap: $($listener.Count)"
            Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
        }} catch {{
            Write-Log "RDPWrap install error: $($_.Exception.Message)"
        }}
    }}
    
    # 5. Activer la découverte réseau et le partage
    Write-Log "Enabling Network Discovery..."
    netsh advfirewall firewall set rule group="Network Discovery" new enable=Yes 2>&1 | Out-Null
    netsh advfirewall firewall set rule group="File and Printer Sharing" new enable=Yes 2>&1 | Out-Null
    # Aussi avec les noms français
    netsh advfirewall firewall set rule group="Découverte de réseau" new enable=Yes 2>&1 | Out-Null
    netsh advfirewall firewall set rule group="Partage de fichiers et d'imprimantes" new enable=Yes 2>&1 | Out-Null
    Write-Log "Network Discovery enabled"
    
    # 6. Configurer le pare-feu pour autoriser les connexions
    Write-Log "Configuring firewall..."
    # Ne pas désactiver complètement le pare-feu, juste autoriser les règles nécessaires
    New-NetFirewallRule -DisplayName "WinRM HTTP" -Direction Inbound -Protocol TCP -LocalPort 5985 -Action Allow -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName "WinRM HTTPS" -Direction Inbound -Protocol TCP -LocalPort 5986 -Action Allow -ErrorAction SilentlyContinue
    Write-Log "Firewall configured"
    
    # 7. Créer le fichier flag de succès
    Write-Log "Creating success flag..."
    "READY" | Out-File -FilePath "C:\\VM-Automation\\ready.flag" -Encoding UTF8
    Write-Log "Success flag created at C:\\VM-Automation\\ready.flag"
    
    Write-Log "=========================================="
    Write-Log "VM-Automation Setup Complete!"
    Write-Log "=========================================="
    
}} catch {{
    Write-Log "ERROR: $($_.Exception.Message)"
    Write-Log "Stack: $($_.ScriptStackTrace)"
}}

# Garder la fenêtre ouverte quelques secondes pour voir les logs
Start-Sleep -Seconds 3
"""
        
        # Encoder et écrire setup.ps1 dans C:\VM-Automation
        import base64
        setup_b64 = base64.b64encode(setup_ps1_content.encode('utf-8')).decode('ascii')
        
        # Découper en chunks pour éviter les limites de ligne de commande
        chunks = [setup_b64[i:i+2000] for i in range(0, len(setup_b64), 2000)]
        
        # Créer le dossier et écrire le script
        script_create_setup = f"""
        $vmAutomationDir = '{win_drive}:\\VM-Automation'
        New-Item -ItemType Directory -Path $vmAutomationDir -Force -ErrorAction SilentlyContinue | Out-Null
        
        # Écrire le fichier en chunks pour éviter les limites de taille
        $tempB64 = "$vmAutomationDir\\setup.b64"
        """
        
        for i, chunk in enumerate(chunks):
            if i == 0:
                script_create_setup += f"""
        [System.IO.File]::WriteAllText($tempB64, '{chunk}')
        """
            else:
                script_create_setup += f"""
        [System.IO.File]::AppendAllText($tempB64, '{chunk}')
        """
        
        script_create_setup += f"""
        # Décoder et écrire le script PowerShell
        $b64Content = [System.IO.File]::ReadAllText($tempB64)
        $bytes = [System.Convert]::FromBase64String($b64Content)
        $scriptContent = [System.Text.Encoding]::UTF8.GetString($bytes)
        [System.IO.File]::WriteAllText("$vmAutomationDir\\setup.ps1", $scriptContent)
        
        # Nettoyer le fichier temporaire
        Remove-Item $tempB64 -Force -ErrorAction SilentlyContinue
        
        Write-Output "VM-Automation setup.ps1 created"
        """
        
        result = await self._execute(script_create_setup, timeout=60)
        
        # Vérifier que le script a bien été créé
        if result.success and "setup.ps1 created" in str(result.stdout or ""):
            logger.info(
                "hyperv_dism_vm_automation_setup_created",
                vm_id=vm_id,
                file="C:\\VM-Automation\\setup.ps1",
            )
        else:
            logger.warning(
                "hyperv_dism_vm_automation_setup_warning",
                vm_id=vm_id,
                stdout=str(result.stdout)[:200] if result.stdout else None,
                stderr=str(result.stderr)[:200] if result.stderr else None,
            )
        
        # Vérifier également que RunOnce a été configuré
        logger.info(
            "hyperv_dism_runonce_configured",
            vm_id=vm_id,
            key="HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunOnce\\VM-Automation-Setup",
        )
        
        # Garder aussi SetupComplete.cmd comme backup (au cas où)
        setup_complete_content = f"""@echo off
REM ============================================
REM SetupComplete.cmd - Backup configuration
REM Exécuté uniquement si RunOnce échoue
REM ============================================
if exist "C:\\VM-Automation\\ready.flag" goto :EOF
echo [%date% %time%] SetupComplete starting (backup) >> C:\\VM-Automation\\setup.log
powershell.exe -ExecutionPolicy Bypass -File "C:\\VM-Automation\\setup.ps1"
echo [%date% %time%] SetupComplete finished >> C:\\VM-Automation\\setup.log
"""
        
        setup_cmd_b64 = base64.b64encode(setup_complete_content.encode('utf-8')).decode('ascii')
        
        script_setup_complete = f"""
        $setupDir = '{win_drive}:\\Windows\\Setup\\Scripts'
        New-Item -ItemType Directory -Path $setupDir -Force -ErrorAction SilentlyContinue | Out-Null
        
        $content = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{setup_cmd_b64}'))
        [System.IO.File]::WriteAllText("$setupDir\\SetupComplete.cmd", $content)
        
        Write-Output "SetupComplete.cmd created (backup)"
        """
        
        result = await self._execute(script_setup_complete, timeout=30)
        if result.success:
            logger.info(
                "hyperv_dism_setup_complete_created",
                vm_id=vm_id,
                file="C:\\Windows\\Setup\\Scripts\\SetupComplete.cmd",
            )
        else:
            logger.warning(
                "hyperv_dism_setup_complete_warning",
                vm_id=vm_id,
                error=str(result.stderr)[:200] if result.stderr else None,
            )
        
        # Étape 4: Configurer le bootloader
        script_boot = f"""
        $ErrorActionPreference = 'Continue'
        bcdboot {win_drive}:\\Windows /s {efi_drive}: /f UEFI
        $exitCode = $LASTEXITCODE
        if ($exitCode -eq 0) {{
            Write-Output "BOOT_SUCCESS"
        }} else {{
            throw "BCDBoot failed with exit code $exitCode"
        }}
        """
        
        result = await self._execute(script_boot, timeout=60)
        
        # Privilégier la présence de "BOOT_SUCCESS" dans stdout plutôt que result.success
        if "BOOT_SUCCESS" not in (result.stdout or ""):
            # Si BOOT_SUCCESS n'est pas présent, vérifier result.success
            if not result.success:
                raise VMOperationError(vm_id, "deploy_dism_boot", result.stderr or result.stdout)
            else:
                # BOOT_SUCCESS absent mais result.success = True : avertissement mais continuer
                logger.warning(
                    "boot_success_marker_missing",
                    vm_id=vm_id,
                    stdout=result.stdout[:200] if result.stdout else None,
                )
        
        logger.debug("hyperv_dism_bootloader_configured", vm_id=vm_id)
        
        # Étape 5: Nettoyer et configurer la VM
        script_finalize = f"""
        # Démonter ISO et VHD
        Dismount-DiskImage -ImagePath '{iso_path}'
        Dismount-VHD -Path '{vhd_path}' -ErrorAction Stop
        $vhdFinalCheck = Get-VHD -Path '{vhd_path}' -ErrorAction SilentlyContinue
        if ($vhdFinalCheck.Attached) {{ Write-Error "VHD still mounted after dismount: {vhd_path}" }}
        
        # Configurer la VM pour booter sur le disque dur
        $vm = Get-VM -Name '{vm_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_id}' }}
        }}
        
        if ($vm) {{
            # Éjecter le DVD s'il est monté
            Get-VMDvdDrive -VMName $vm.Name | Remove-VMDvdDrive -ErrorAction SilentlyContinue
            
            # Configurer le boot sur le disque dur
            $hdd = Get-VMHardDiskDrive -VMName $vm.Name | Where-Object {{ $_.ControllerLocation -eq 0 }}
            if ($hdd) {{
                Set-VMFirmware -VMName $vm.Name -FirstBootDevice $hdd
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

    async def cleanup(self) -> None:
        """Libère les ressources et ferme les connexions."""
        self.close()

    # =========================================================================
    # Méthodes de monitoring
    # =========================================================================

    async def get_vm_health(self, vm_id: str) -> VMHealthStatus | None:
        """Récupère l'état de santé complet d'une VM."""
        safe_id = _escape_ps(vm_id)
        script = f"""
        $vm = Get-VM -Name '{safe_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{safe_id}' }}
        }}
        if ($vm) {{
            $intServices = Get-VMIntegrationService -VMName $vm.Name | Select-Object Name, Enabled, 
                @{{N='Status';E={{$_.PrimaryOperationalStatus.ToString()}}}}
            
            $nic = Get-VMNetworkAdapter -VMName $vm.Name
            
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
        safe_id = _escape_ps(vm_id)
        script = f"""
        $vm = Get-VM -Name '{safe_id}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{safe_id}' }}
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
            Get-VMIntegrationService -VMName $vm.Name | Select-Object Name, Enabled, 
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
            $nic = Get-VMNetworkAdapter -VMName $vm.Name
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

    async def execute_via_winrm_direct(
        self,
        vm_ip: str,
        script: str,
        credentials: tuple[str, str],
        timeout: int = 60,
    ) -> PowerShellDirectResult:
        """
        Exécute un script PowerShell directement sur une VM via WinRM (connexion directe).
        
        Cette méthode se connecte directement à l'IP de la VM au lieu de passer
        par PowerShell Direct via l'hyperviseur. Plus rapide et plus fiable.
        
        Args:
            vm_ip: Adresse IP de la VM
            script: Script PowerShell à exécuter
            credentials: Tuple (username, password) pour la VM
            timeout: Timeout en secondes
            
        Returns:
            PowerShellDirectResult avec le résultat de l'exécution
        """
        if not WINRM_AVAILABLE:
            raise HypervisorError(
                "pywinrm is required for WinRM direct mode. Install with: pip install pywinrm"
            )
        import winrm
        
        username, password = credentials
        
        logger.info(
            "winrm_direct_executing",
            vm_ip=vm_ip,
            script_length=len(script),
            timeout=timeout,
        )
        
        try:
            # Connexion WinRM directe à la VM (HTTP port 5985)
            session = winrm.Session(
                f"http://{vm_ip}:5985/wsman",
                auth=(username, password),
                transport="ntlm",
                server_cert_validation="ignore",
            )
            
            # Exécuter le script PowerShell
            result = session.run_ps(script)
            
            success = result.status_code == 0
            stdout = result.std_out.decode("utf-8", errors="replace") if result.std_out else ""
            stderr = result.std_err.decode("utf-8", errors="replace") if result.std_err else ""
            
            if success:
                logger.info(
                    "winrm_direct_success",
                    vm_ip=vm_ip,
                    output_length=len(stdout),
                )
            else:
                logger.warning(
                    "winrm_direct_failed",
                    vm_ip=vm_ip,
                    exit_code=result.status_code,
                    stderr=stderr[:200] if stderr else None,
                )
            
            return PowerShellDirectResult(
                success=success,
                output=stdout if success else None,
                error=stderr if not success else None,
            )
            
        except Exception as e:
            logger.warning(
                "winrm_direct_error",
                vm_ip=vm_ip,
                error=str(e),
            )
            return PowerShellDirectResult(
                success=False,
                output=None,
                error=str(e),
            )

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
                
                # Accepter tout heartbeat qui n'est pas "NoContact", "None" ou vide
                # Cela permet de gérer différentes variantes de heartbeat (OkApplicationsHealthy, OkApplicationsUnknown, etc.)
                invalid_heartbeats = ("NoContact", "None", None, "")
                is_heartbeat_ok = heartbeat and heartbeat not in invalid_heartbeats
                
                if is_heartbeat_ok:
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
                $nic = Get-VMNetworkAdapter -VMName $vm.Name | Where-Object {{ $_.Name -eq '{adapter_name}' }}
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
                Set-VMNetworkAdapterVlan -VMName $vm.Name -Access -VlanId {vlan_id}
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
                $nic = Get-VMNetworkAdapter -VMName $vm.Name | Where-Object {{ $_.Name -eq '{adapter_name}' }}
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
                Set-VMNetworkAdapterVlan -VMName $vm.Name -Untagged
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
            $nics = Get-VMNetworkAdapter -VMName $vm.Name
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
            Get-VMNetworkAdapter -VMName $vm.Name | ForEach-Object {{
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
            $nic = Add-VMNetworkAdapter -VMName $vm.Name -SwitchName '{switch_name}' {name_param} {mac_param} -Passthru
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
            $nic = Get-VMNetworkAdapter -VMName $vm.Name | Where-Object {{ $_.Name -eq '{adapter_name}' }}
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
            $nic = Get-VMNetworkAdapter -VMName $vm.Name | Where-Object {{ $_.Name -eq '{adapter_name}' }}
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
            $nic = Get-VMNetworkAdapter -VMName $vm.Name | Where-Object {{ $_.Name -eq '{adapter_name}' }}
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
            Get-VMHardDiskDrive -VMName $vm.Name | ForEach-Object {{
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
                $diskCount = (Get-VMHardDiskDrive -VMName $vm.Name).Count
                $vhdxPath = Join-Path $vmPath "$($vm.Name)_disk$($diskCount + 1).vhdx"
            }}

            # Créer le disque
            $vhdParams = @{{
                Path = $vhdxPath
                SizeBytes = {size_gb}GB
                {"Dynamic = $true" if disk_type == "Dynamic" else "Fixed = $true"}
            }}
            $vhd = New-VHD @vhdParams

            # Fix VHD permissions for Hyper-V Virtual Machine service (SID S-1-5-83-0)
            $acl = Get-Acl $vhdxPath
            $sid = New-Object System.Security.Principal.SecurityIdentifier("S-1-5-83-0")
            $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($sid, "FullControl", "Allow")
            $acl.AddAccessRule($rule)
            Set-Acl -Path $vhdxPath -AclObject $acl

            # Trouver le prochain emplacement disponible
            $existingDisks = Get-VMHardDiskDrive -VMName $vm.Name
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
            Add-VMHardDiskDrive -VMName $vm.Name -Path $vhdxPath -ControllerType SCSI -ControllerNumber $controller -ControllerLocation $location

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
            $disk = Get-VMHardDiskDrive -VMName $vm.Name | Where-Object {{ {filter_clause} }}
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

            Add-VMHardDiskDrive -VMName $vm.Name -Path '{disk_path}' -ControllerType SCSI -ControllerNumber {controller_number} {location_param}
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

    # -------------------------------------------------------------------------
    # Keyboard input via WMI Msvm_Keyboard
    # -------------------------------------------------------------------------

    async def send_key(self, vm_id: str, scancode: int) -> bool:
        """
        Envoie une frappe clavier unique à la VM (appui + relâche).

        Utilise WMI Msvm_Keyboard.TypeKey pour simuler une touche complète.

        Args:
            vm_id: ID ou nom de la VM
            scancode: Code scancode de la touche (ex. 0x1C pour Enter)

        Returns:
            True si la touche a été envoyée, False sinon
        """
        script = f"""
        $ErrorActionPreference = 'Stop'
        $vm = Get-VM -Name '{_escape_ps(vm_id)}' -ErrorAction SilentlyContinue
        if (-not $vm) {{ $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{_escape_ps(vm_id)}' }} }}
        if (-not $vm) {{ throw "VM not found: {_escape_ps(vm_id)}" }}
        $vmName = $vm.Name
        $ns = "root\\virtualization\\v2"
        $vmWmi = Get-WmiObject -Namespace $ns -Query "SELECT * FROM Msvm_ComputerSystem WHERE ElementName='$vmName'" | Select-Object -First 1
        if (-not $vmWmi) {{ throw "Cannot find VM in WMI" }}
        $keyboard = (Get-WmiObject -Namespace $ns -Query "ASSOCIATORS OF {{$($vmWmi.__PATH)}} WHERE ResultClass=Msvm_Keyboard") | Select-Object -First 1
        if (-not $keyboard) {{ throw "Cannot find keyboard device" }}

        $result = $keyboard.TypeKey({scancode})
        if ($result.ReturnValue -ne 0) {{
            throw "TypeKey failed with return value: $($result.ReturnValue)"
        }}
        Write-Output "OK"
        """

        result = await self._execute(script, timeout=15)

        if not result.success:
            logger.warning(
                "hyperv_send_key_failed",
                vm_id=vm_id,
                scancode=scancode,
                error=result.stderr,
            )
            return False

        logger.info("hyperv_send_key", vm_id=vm_id, scancode=scancode)
        return True

    async def move_mouse(self, vm_id: str, x_pct: float, y_pct: float) -> bool:
        """
        Déplace le curseur de la souris à une position absolue dans la VM.

        Utilise WMI Msvm_SyntheticMouse.SetAbsolutePosition pour définir
        la position du pointeur. Les coordonnées sont fournies en pourcentage
        (0-100) et converties en range WMI (0-65535).

        Args:
            vm_id: ID ou nom de la VM
            x_pct: Position X en pourcentage (0-100)
            y_pct: Position Y en pourcentage (0-100)

        Returns:
            True si le déplacement a réussi, False sinon
        """
        # Clamp to 0-100 and convert to 0-65535 range
        abs_x = int(max(0, min(100, x_pct)) * 65535 / 100)
        abs_y = int(max(0, min(100, y_pct)) * 65535 / 100)

        script = f"""
        $ErrorActionPreference = 'Stop'
        $vm = Get-VM -Name '{_escape_ps(vm_id)}' -ErrorAction SilentlyContinue
        if (-not $vm) {{ $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{_escape_ps(vm_id)}' }} }}
        if (-not $vm) {{ throw "VM not found: {_escape_ps(vm_id)}" }}
        $vmName = $vm.Name
        $ns = "root\\virtualization\\v2"
        $vmWmi = Get-WmiObject -Namespace $ns -Query "SELECT * FROM Msvm_ComputerSystem WHERE ElementName='$vmName'" | Select-Object -First 1
        if (-not $vmWmi) {{ throw "Cannot find VM in WMI" }}
        $mouse = (Get-WmiObject -Namespace $ns -Query "ASSOCIATORS OF {{$($vmWmi.__PATH)}} WHERE ResultClass=Msvm_SyntheticMouse") | Select-Object -First 1
        if (-not $mouse) {{ throw "Cannot find mouse device" }}

        $result = $mouse.SetAbsolutePosition({abs_x}, {abs_y})
        if ($result.ReturnValue -ne 0) {{
            throw "SetAbsolutePosition failed with return value: $($result.ReturnValue)"
        }}
        Write-Output "OK"
        """

        result = await self._execute(script, timeout=15)

        if not result.success:
            logger.warning(
                "hyperv_move_mouse_failed",
                vm_id=vm_id,
                x_pct=x_pct,
                y_pct=y_pct,
                error=result.stderr,
            )
            return False

        logger.debug("hyperv_move_mouse", vm_id=vm_id, x_pct=x_pct, y_pct=y_pct)
        return True

    async def press_key(self, vm_id: str, scancode: int) -> bool:
        """
        Maintient une touche enfoncée sur la VM (sans relâcher).

        Utile pour les combinaisons de touches avec modificateurs
        (Ctrl, Alt, Shift). Appeler release_key ensuite pour relâcher.

        Args:
            vm_id: ID ou nom de la VM
            scancode: Code scancode de la touche modificateur

        Returns:
            True si la touche est maintenue, False sinon
        """
        script = f"""
        $ErrorActionPreference = 'Stop'
        $vm = Get-VM -Name '{_escape_ps(vm_id)}' -ErrorAction SilentlyContinue
        if (-not $vm) {{ $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{_escape_ps(vm_id)}' }} }}
        if (-not $vm) {{ throw "VM not found: {_escape_ps(vm_id)}" }}
        $vmName = $vm.Name
        $ns = "root\\virtualization\\v2"
        $vmWmi = Get-WmiObject -Namespace $ns -Query "SELECT * FROM Msvm_ComputerSystem WHERE ElementName='$vmName'" | Select-Object -First 1
        if (-not $vmWmi) {{ throw "Cannot find VM in WMI" }}
        $keyboard = (Get-WmiObject -Namespace $ns -Query "ASSOCIATORS OF {{$($vmWmi.__PATH)}} WHERE ResultClass=Msvm_Keyboard") | Select-Object -First 1
        if (-not $keyboard) {{ throw "Cannot find keyboard device" }}

        $result = $keyboard.PressKey({scancode})
        if ($result.ReturnValue -ne 0) {{
            throw "PressKey failed with return value: $($result.ReturnValue)"
        }}
        Write-Output "OK"
        """

        result = await self._execute(script, timeout=15)

        if not result.success:
            logger.warning(
                "hyperv_press_key_failed",
                vm_id=vm_id,
                scancode=scancode,
                error=result.stderr,
            )
            return False

        logger.info("hyperv_press_key", vm_id=vm_id, scancode=scancode)
        return True

    async def release_key(self, vm_id: str, scancode: int) -> bool:
        """
        Relâche une touche précédemment maintenue sur la VM.

        Utilisé après press_key pour terminer une combinaison
        de touches avec modificateurs.

        Args:
            vm_id: ID ou nom de la VM
            scancode: Code scancode de la touche à relâcher

        Returns:
            True si la touche a été relâchée, False sinon
        """
        script = f"""
        $ErrorActionPreference = 'Stop'
        $vm = Get-VM -Name '{_escape_ps(vm_id)}' -ErrorAction SilentlyContinue
        if (-not $vm) {{ $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{_escape_ps(vm_id)}' }} }}
        if (-not $vm) {{ throw "VM not found: {_escape_ps(vm_id)}" }}
        $vmName = $vm.Name
        $ns = "root\\virtualization\\v2"
        $vmWmi = Get-WmiObject -Namespace $ns -Query "SELECT * FROM Msvm_ComputerSystem WHERE ElementName='$vmName'" | Select-Object -First 1
        if (-not $vmWmi) {{ throw "Cannot find VM in WMI" }}
        $keyboard = (Get-WmiObject -Namespace $ns -Query "ASSOCIATORS OF {{$($vmWmi.__PATH)}} WHERE ResultClass=Msvm_Keyboard") | Select-Object -First 1
        if (-not $keyboard) {{ throw "Cannot find keyboard device" }}

        $result = $keyboard.ReleaseKey({scancode})
        if ($result.ReturnValue -ne 0) {{
            throw "ReleaseKey failed with return value: $($result.ReturnValue)"
        }}
        Write-Output "OK"
        """

        result = await self._execute(script, timeout=15)

        if not result.success:
            logger.warning(
                "hyperv_release_key_failed",
                vm_id=vm_id,
                scancode=scancode,
                error=result.stderr,
            )
            return False

        logger.info("hyperv_release_key", vm_id=vm_id, scancode=scancode)
        return True

    async def type_text(self, vm_id: str, text: str) -> bool:
        """
        Tape du texte brut dans la VM via le clavier virtuel.

        Utilise WMI Msvm_Keyboard.TypeText pour envoyer une chaîne
        complète d'un coup. Le texte est échappé pour PowerShell.

        Args:
            vm_id: ID ou nom de la VM
            text: Texte à taper dans la VM

        Returns:
            True si le texte a été envoyé, False sinon
        """
        escaped_text = _escape_ps(text)
        script = f"""
        $ErrorActionPreference = 'Stop'
        $vm = Get-VM -Name '{_escape_ps(vm_id)}' -ErrorAction SilentlyContinue
        if (-not $vm) {{ $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{_escape_ps(vm_id)}' }} }}
        if (-not $vm) {{ throw "VM not found: {_escape_ps(vm_id)}" }}
        $vmName = $vm.Name
        $ns = "root\\virtualization\\v2"
        $vmWmi = Get-WmiObject -Namespace $ns -Query "SELECT * FROM Msvm_ComputerSystem WHERE ElementName='$vmName'" | Select-Object -First 1
        if (-not $vmWmi) {{ throw "Cannot find VM in WMI" }}
        $keyboard = (Get-WmiObject -Namespace $ns -Query "ASSOCIATORS OF {{$($vmWmi.__PATH)}} WHERE ResultClass=Msvm_Keyboard") | Select-Object -First 1
        if (-not $keyboard) {{ throw "Cannot find keyboard device" }}

        $result = $keyboard.TypeText('{escaped_text}')
        if ($result.ReturnValue -ne 0) {{
            throw "TypeText failed with return value: $($result.ReturnValue)"
        }}
        Write-Output "OK"
        """

        result = await self._execute(script, timeout=15)

        if not result.success:
            logger.warning(
                "hyperv_type_text_failed",
                vm_id=vm_id,
                text_length=len(text),
                error=result.stderr,
            )
            return False

        logger.info("hyperv_type_text", vm_id=vm_id, text_length=len(text))
        return True

    # -------------------------------------------------------------------------
    # Mouse click
    # -------------------------------------------------------------------------

    async def click_mouse(
        self,
        vm_id: str,
        x: float,
        y: float,
        button: int = 1,
    ) -> bool:
        """
        Envoie un clic souris à la VM via WMI Msvm_SyntheticMouse.

        Args:
            vm_id: ID ou nom de la VM
            x: Position X en pourcentage (0-100) de l'écran
            y: Position Y en pourcentage (0-100) de l'écran
            button: Bouton de la souris (1=gauche, 2=droit)

        Returns:
            True si le clic a été envoyé, False sinon
        """
        # Clamp percentages to 0-100 and convert to absolute coords (0-65535)
        abs_x = int(max(0.0, min(100.0, x)) / 100.0 * 65535)
        abs_y = int(max(0.0, min(100.0, y)) / 100.0 * 65535)
        btn = int(button) if button in (1, 2) else 1

        script = f"""
        $ErrorActionPreference = 'Stop'
        $vm = Get-VM -Name '{_escape_ps(vm_id)}' -ErrorAction SilentlyContinue
        if (-not $vm) {{ $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{_escape_ps(vm_id)}' }} }}
        if (-not $vm) {{ throw "VM not found: {_escape_ps(vm_id)}" }}
        $vmName = $vm.Name
        $ns = "root\\virtualization\\v2"
        $vmWmi = Get-WmiObject -Namespace $ns -Query "SELECT * FROM Msvm_ComputerSystem WHERE ElementName='$vmName'" | Select-Object -First 1
        if (-not $vmWmi) {{ throw "Cannot find VM in WMI" }}
        $mouse = (Get-WmiObject -Namespace $ns -Query "ASSOCIATORS OF {{$($vmWmi.__PATH)}} WHERE ResultClass=Msvm_SyntheticMouse") | Select-Object -First 1
        if (-not $mouse) {{ throw "Cannot find mouse device" }}

        $posResult = $mouse.SetAbsolutePosition({abs_x}, {abs_y})
        if ($posResult.ReturnValue -ne 0) {{
            throw "SetAbsolutePosition failed with return value: $($posResult.ReturnValue)"
        }}
        $clickResult = $mouse.ClickButton({btn})
        if ($clickResult.ReturnValue -ne 0) {{
            throw "ClickButton failed with return value: $($clickResult.ReturnValue)"
        }}
        Write-Output "OK"
        """

        result = await self._execute(script, timeout=15)

        if not result.success:
            logger.warning(
                "hyperv_click_mouse_failed",
                vm_id=vm_id,
                x=x,
                y=y,
                button=button,
                error=result.stderr,
            )
            return False

        logger.info(
            "hyperv_click_mouse",
            vm_id=vm_id,
            x=x,
            y=y,
            button=button,
        )
        return True

    # -------------------------------------------------------------------------
    # Screenshot (raw bytes variant)
    # -------------------------------------------------------------------------

    async def get_vm_screenshot_bytes(
        self,
        vm_id: str,
        width: int = 640,
        height: int = 480,
    ) -> bytes | None:
        """
        Capture un screenshot de l'écran de la VM et retourne les octets PNG bruts.

        Identique à get_vm_screenshot mais retourne des bytes au lieu
        d'une chaîne base64, utile pour écrire directement dans un fichier
        ou streamer via une API.

        Args:
            vm_id: ID ou nom de la VM
            width: Largeur de l'image (défaut 640)
            height: Hauteur de l'image (défaut 480)

        Returns:
            Octets PNG bruts ou None si échec
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
                "hyperv_screenshot_bytes_failed",
                vm_id=vm_id,
                error=result.stderr,
            )
            return None

        # Parser le JSON
        data = self._parse_json_output(result.stdout)

        if not data or not data.get("Data"):
            logger.warning("hyperv_screenshot_bytes_empty", vm_id=vm_id)
            return None

        # Convertir RGB16 brut en PNG
        try:
            import base64
            from io import BytesIO
            import numpy as np
            from PIL import Image

            # Décoder les données base64
            raw_data = base64.b64decode(data["Data"])
            img_width = data.get("Width", width)
            img_height = data.get("Height", height)

            # Les données Hyper-V ont un header de 4 bytes
            header_size = 4
            if len(raw_data) > img_width * img_height * 2:
                raw_data = raw_data[header_size:]

            # Calculer le nombre de pixels attendu
            expected_pixels = img_width * img_height
            actual_pixels = len(raw_data) // 2

            # Ajuster les dimensions si nécessaire
            if actual_pixels != expected_pixels:
                logger.warning(
                    "hyperv_screenshot_bytes_size_mismatch",
                    expected=expected_pixels,
                    actual=actual_pixels,
                )

            # Les données sont en RGB565 (16 bits par pixel)
            # Convertir en RGB888 via numpy (vectorisé, ~100x plus rapide)
            usable_bytes = min(len(raw_data), expected_pixels * 2)
            raw_arr = np.frombuffer(raw_data[:usable_bytes], dtype=np.uint16)

            # RGB565: RRRRRGGGGGGBBBBB (little-endian, natif sur x86)
            r = ((raw_arr >> 11) & 0x1F).astype(np.uint8) << 3
            g = ((raw_arr >> 5) & 0x3F).astype(np.uint8) << 2
            b = (raw_arr & 0x1F).astype(np.uint8) << 3

            # Empiler en (N, 3) puis compléter avec des pixels noirs si nécessaire
            rgb = np.stack((r, g, b), axis=-1)
            if len(rgb) < expected_pixels:
                padding = np.zeros((expected_pixels - len(rgb), 3), dtype=np.uint8)
                rgb = np.concatenate((rgb, padding), axis=0)
            else:
                rgb = rgb[:expected_pixels]

            # Créer l'image directement depuis le tableau numpy
            img = Image.frombuffer(
                "RGB", (img_width, img_height), rgb.tobytes(), "raw", "RGB", 0, 1
            )

            # Sauvegarder en PNG dans un buffer (compress_level=1 : rapide)
            buffer = BytesIO()
            img.save(buffer, format="PNG", compress_level=1)
            buffer.seek(0)

            # Retourner les octets PNG bruts
            png_bytes = buffer.getvalue()

            logger.info("hyperv_screenshot_bytes_captured", vm_id=vm_id, size=len(png_bytes))
            return png_bytes

        except Exception as e:
            logger.error("hyperv_screenshot_bytes_conversion_failed", vm_id=vm_id, error=str(e))
            return None
