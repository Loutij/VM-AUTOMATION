# =============================================================================
# VM Automation - Base Hypervisor Interface
# =============================================================================
"""
Interface abstraite pour les clients hyperviseurs.
Définit le contrat que tous les clients hyperviseurs doivent respecter.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass
class VMSpecs:
    """Spécifications d'une machine virtuelle."""

    name: str
    cpu_count: int = 2
    ram_gb: int = 4
    disk_gb: int = 60
    generation: int | None = 2  # None pour VMware (pas de concept de génération)
    network_switch: str = "Default Switch"
    vlan_id: int | None = None
    iso_path: str | None = None
    vm_path: str | None = None
    vhdx_path: str | None = None
    # Champs spécifiques VMware
    datastore: str | None = None  # Nom du datastore VMware
    resource_pool: str | None = None  # Pool de ressources VMware
    folder: str | None = None  # Dossier VM VMware
    disk_format: str = "thin"  # thin/thick/eagerzeroedthick (provisionnement disque VMware)
    guest_os_id: str | None = None  # Identifiant OS invité VMware (ex: "ubuntu64Guest")


@dataclass
class VMInfo:
    """Informations sur une VM existante."""

    id: str
    name: str
    state: str
    cpu_count: int
    ram_gb: int
    uptime: str | None = None
    status: str | None = None
    notes: str | None = None
    generation: int = 2
    path: str | None = None
    # Champs spécifiques VMware
    tools_status: str | None = None  # Statut VMware Tools
    tools_version: str | None = None  # Version VMware Tools
    guest_os: str | None = None  # Nom complet de l'OS invité

    def to_dict(self) -> dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state,
            "cpu_count": self.cpu_count,
            "ram_gb": self.ram_gb,
            "uptime": self.uptime,
            "status": self.status,
            "notes": self.notes,
            "generation": self.generation,
            "path": self.path,
            "tools_status": self.tools_status,
            "tools_version": self.tools_version,
            "guest_os": self.guest_os,
        }


@dataclass
class VirtualSwitch:
    """Informations sur un switch virtuel."""

    name: str
    switch_type: str
    interface_description: str | None = None
    notes: str | None = None
    vlan_id: int | None = None  # VLAN associé au switch (VMware port group)

    def to_dict(self) -> dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            "name": self.name,
            "switch_type": self.switch_type,
            "interface_description": self.interface_description,
            "notes": self.notes,
            "vlan_id": self.vlan_id,
        }


@dataclass
class DiskInfo:
    """Informations sur un disque virtuel."""

    path: str
    size_gb: float
    format: str = "VHDX"
    type: str = "Dynamic"
    attached_to: str | None = None
    controller_number: int = 0
    controller_location: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            "path": self.path,
            "size_gb": self.size_gb,
            "format": self.format,
            "type": self.type,
            "attached_to": self.attached_to,
            "controller_number": self.controller_number,
            "controller_location": self.controller_location,
        }


@dataclass
class NetworkAdapterInfo:
    """Informations sur un adaptateur réseau virtuel."""

    name: str
    switch_name: str | None
    mac_address: str | None = None
    vlan_id: int | None = None
    ip_addresses: list[str] = field(default_factory=list)
    is_management_os: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            "name": self.name,
            "switch_name": self.switch_name,
            "mac_address": self.mac_address,
            "vlan_id": self.vlan_id,
            "ip_addresses": self.ip_addresses,
            "is_management_os": self.is_management_os,
        }


@dataclass
class NetworkInterfaceDetails:
    """Informations réseau détaillées d'une interface depuis l'intérieur de la VM."""

    interface_name: str
    interface_alias: str
    interface_index: int
    mac_address: str
    ip_address: str | None = None
    subnet_mask: str | None = None
    prefix_length: int | None = None
    default_gateway: str | None = None
    dns_servers: list[str] = field(default_factory=list)
    dhcp_enabled: bool = False
    dhcp_server: str | None = None
    connection_status: str = "Unknown"
    link_speed_mbps: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            "interface_name": self.interface_name,
            "interface_alias": self.interface_alias,
            "interface_index": self.interface_index,
            "mac_address": self.mac_address,
            "ip_address": self.ip_address,
            "subnet_mask": self.subnet_mask,
            "prefix_length": self.prefix_length,
            "default_gateway": self.default_gateway,
            "dns_servers": self.dns_servers,
            "dhcp_enabled": self.dhcp_enabled,
            "dhcp_server": self.dhcp_server,
            "connection_status": self.connection_status,
            "link_speed_mbps": self.link_speed_mbps,
        }


@dataclass
class VMNetworkInfo:
    """Informations réseau complètes d'une VM (Hyper-V + Guest OS)."""

    vm_name: str
    hostname: str | None = None
    adapters_hyperv: list[NetworkAdapterInfo] = field(default_factory=list)
    interfaces_guest: list[NetworkInterfaceDetails] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            "vm_name": self.vm_name,
            "hostname": self.hostname,
            "adapters_hyperv": [a.to_dict() for a in self.adapters_hyperv],
            "interfaces_guest": [i.to_dict() for i in self.interfaces_guest],
        }

    def get_primary_ip(self) -> str | None:
        """Retourne l'IP principale (première IPv4 non-loopback)."""
        for iface in self.interfaces_guest:
            if iface.ip_address and not iface.ip_address.startswith("127."):
                return iface.ip_address
        # Fallback sur les adresses Hyper-V
        for adapter in self.adapters_hyperv:
            for ip in adapter.ip_addresses:
                if not ip.startswith("127.") and ":" not in ip:  # Exclure IPv6
                    return ip
        return None

    def get_primary_mac(self) -> str | None:
        """Retourne l'adresse MAC principale."""
        for adapter in self.adapters_hyperv:
            if adapter.mac_address:
                return adapter.mac_address
        for iface in self.interfaces_guest:
            if iface.mac_address:
                return iface.mac_address
        return None


@dataclass
class IntegrationService:
    """Informations sur un service d'intégration Hyper-V."""

    name: str
    enabled: bool
    status: str
    
    def to_dict(self) -> dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "status": self.status,
        }


@dataclass
class VMHealthStatus:
    """État de santé d'une VM."""

    vm_name: str
    state: str
    heartbeat: str
    uptime: str | None
    cpu_usage: int
    memory_mb: int
    ip_addresses: list[str] = field(default_factory=list)
    integration_services: list[IntegrationService] = field(default_factory=list)
    # Champ spécifique VMware
    tools_running: bool | None = None  # VMware Tools en cours d'exécution

    @property
    def is_healthy(self) -> bool:
        """Vérifie si la VM est en bonne santé."""
        base_healthy = (
            self.state == "Running"
            and self.heartbeat in ("OkApplicationsHealthy", "OkApplicationsUnknown", "Ok")
        )
        # Pour VMware, vérifier aussi que les Tools tournent si l'info est disponible
        if self.tools_running is not None:
            return base_healthy and self.tools_running
        return base_healthy

    def to_dict(self) -> dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            "vm_name": self.vm_name,
            "state": self.state,
            "heartbeat": self.heartbeat,
            "uptime": self.uptime,
            "cpu_usage": self.cpu_usage,
            "memory_mb": self.memory_mb,
            "ip_addresses": self.ip_addresses,
            "integration_services": [s.to_dict() for s in self.integration_services],
            "is_healthy": self.is_healthy,
            "tools_running": self.tools_running,
        }


@dataclass
class PowerShellDirectResult:
    """Résultat d'une exécution PowerShell Direct dans une VM."""

    success: bool
    output: Any
    error: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
        }


class BaseHypervisor(ABC):
    """
    Interface abstraite pour les clients hyperviseurs.
    
    Tous les clients hyperviseurs (Hyper-V, VMware, etc.) doivent
    implémenter cette interface.
    """

    @abstractmethod
    async def test_connection(self) -> bool:
        """
        Teste la connexion à l'hyperviseur.
        
        Returns:
            True si la connexion est OK
        """
        raise NotImplementedError

    @abstractmethod
    async def list_vms(self) -> list[VMInfo]:
        """
        Liste toutes les VMs sur l'hyperviseur.

        Returns:
            Liste des VMs
        """
        raise NotImplementedError

    @abstractmethod
    async def get_vm(self, vm_id: str) -> VMInfo | None:
        """
        Récupère les informations d'une VM.

        Args:
            vm_id: ID ou nom de la VM

        Returns:
            Informations de la VM ou None si non trouvée
        """
        raise NotImplementedError

    @abstractmethod
    async def create_vm(self, specs: VMSpecs) -> VMInfo:
        """
        Crée une nouvelle VM.

        Args:
            specs: Spécifications de la VM

        Returns:
            Informations de la VM créée
        """
        raise NotImplementedError

    @abstractmethod
    async def delete_vm(self, vm_id: str, delete_disks: bool = False) -> bool:
        """
        Supprime une VM.

        Args:
            vm_id: ID ou nom de la VM
            delete_disks: Supprimer aussi les disques associés

        Returns:
            True si la suppression a réussi
        """
        raise NotImplementedError

    @abstractmethod
    async def start_vm(self, vm_id: str) -> bool:
        """
        Démarre une VM.

        Args:
            vm_id: ID ou nom de la VM

        Returns:
            True si le démarrage a réussi
        """
        raise NotImplementedError

    @abstractmethod
    async def stop_vm(self, vm_id: str, force: bool = False) -> bool:
        """
        Arrête une VM.

        Args:
            vm_id: ID ou nom de la VM
            force: Forcer l'arrêt (équivalent de débrancher)

        Returns:
            True si l'arrêt a réussi
        """
        raise NotImplementedError

    @abstractmethod
    async def restart_vm(self, vm_id: str, force: bool = False) -> bool:
        """
        Redémarre une VM.

        Args:
            vm_id: ID ou nom de la VM
            force: Forcer le redémarrage

        Returns:
            True si le redémarrage a réussi
        """
        raise NotImplementedError

    @abstractmethod
    async def get_vm_state(self, vm_id: str) -> str | None:
        """
        Récupère l'état d'une VM.

        Args:
            vm_id: ID ou nom de la VM

        Returns:
            État de la VM (Running, Off, Paused, etc.) ou None
        """
        raise NotImplementedError

    @abstractmethod
    async def list_switches(self) -> list[VirtualSwitch]:
        """
        Liste les switches virtuels disponibles.

        Returns:
            Liste des switches
        """
        raise NotImplementedError

    @abstractmethod
    async def mount_iso(self, vm_id: str, iso_path: str) -> bool:
        """
        Monte une ISO sur le lecteur DVD d'une VM.

        Args:
            vm_id: ID ou nom de la VM
            iso_path: Chemin vers l'ISO

        Returns:
            True si le montage a réussi
        """
        raise NotImplementedError

    @abstractmethod
    async def unmount_iso(self, vm_id: str, unmount_all: bool = True) -> bool:
        """
        Démonte les ISOs des lecteurs DVD d'une VM.

        Args:
            vm_id: ID ou nom de la VM
            unmount_all: Si True, démonte tous les lecteurs. Sinon, juste le premier.

        Returns:
            True si le démontage a réussi
        """
        raise NotImplementedError

    @abstractmethod
    async def enable_guest_services(self, vm_id: str) -> bool:
        """
        Active le Guest Service Interface (copie de fichiers hôte -> VM).

        Args:
            vm_id: ID ou nom de la VM

        Returns:
            True si l'activation a réussi
        """
        raise NotImplementedError

    @abstractmethod
    async def set_first_boot_device(
        self,
        vm_id: str,
        device_type: str = "HardDrive",
    ) -> bool:
        """
        Configure le premier périphérique de boot d'une VM.

        Args:
            vm_id: ID ou nom de la VM
            device_type: Type de périphérique (HardDrive, DVD, Network)

        Returns:
            True si la configuration a réussi
        """
        raise NotImplementedError

    @abstractmethod
    async def cleanup_post_install(self, vm_id: str) -> dict[str, bool]:
        """
        Effectue le nettoyage post-installation d'une VM.

        Actions typiques:
        - Démonte tous les ISOs
        - Configure le boot sur le disque dur
        - Active les Guest Services

        Args:
            vm_id: ID ou nom de la VM

        Returns:
            Dictionnaire avec le résultat de chaque action
        """
        raise NotImplementedError

    @abstractmethod
    async def set_boot_order(
        self,
        vm_id: str,
        boot_order: list[str],
    ) -> bool:
        """
        Configure l'ordre de boot d'une VM.

        Args:
            vm_id: ID ou nom de la VM
            boot_order: Liste ordonnée des périphériques de boot

        Returns:
            True si la configuration a réussi
        """
        raise NotImplementedError

    # =========================================================================
    # Méthodes de monitoring
    # =========================================================================

    @abstractmethod
    async def get_vm_health(self, vm_id: str) -> VMHealthStatus | None:
        """
        Récupère l'état de santé complet d'une VM.

        Args:
            vm_id: ID ou nom de la VM

        Returns:
            État de santé de la VM ou None si non trouvée
        """
        raise NotImplementedError

    @abstractmethod
    async def get_vm_heartbeat(self, vm_id: str) -> str | None:
        """
        Récupère le statut heartbeat d'une VM.

        Args:
            vm_id: ID ou nom de la VM

        Returns:
            Statut heartbeat (OkApplicationsHealthy, NoContact, etc.) ou None
        """
        raise NotImplementedError

    @abstractmethod
    async def get_vm_integration_services(
        self,
        vm_id: str,
    ) -> list[IntegrationService]:
        """
        Récupère la liste des services d'intégration d'une VM.

        Args:
            vm_id: ID ou nom de la VM

        Returns:
            Liste des services d'intégration
        """
        raise NotImplementedError

    @abstractmethod
    async def get_vm_ip_addresses(self, vm_id: str) -> list[str]:
        """
        Récupère les adresses IP d'une VM.

        Args:
            vm_id: ID ou nom de la VM

        Returns:
            Liste des adresses IP
        """
        raise NotImplementedError

    @abstractmethod
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

        Returns:
            Résultat de l'exécution
        """
        raise NotImplementedError

    @abstractmethod
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

        Returns:
            True si la VM est prête, False si timeout
        """
        raise NotImplementedError

    @abstractmethod
    async def cleanup(self) -> None:
        """
        Libère les ressources et ferme les connexions à l'hyperviseur.

        Doit être appelé lors de l'arrêt de l'application ou quand
        le client n'est plus nécessaire.
        """
        raise NotImplementedError
