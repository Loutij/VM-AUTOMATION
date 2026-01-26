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
    generation: int = 2
    network_switch: str = "Default Switch"
    vlan_id: int | None = None
    iso_path: str | None = None
    vm_path: str | None = None
    vhdx_path: str | None = None


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
        }


@dataclass
class VirtualSwitch:
    """Informations sur un switch virtuel."""

    name: str
    switch_type: str
    interface_description: str | None = None
    notes: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            "name": self.name,
            "switch_type": self.switch_type,
            "interface_description": self.interface_description,
            "notes": self.notes,
        }


@dataclass
class DiskInfo:
    """Informations sur un disque virtuel."""

    path: str
    size_gb: float
    format: str = "VHDX"
    type: str = "Dynamic"
    attached_to: str | None = None


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
    
    @property
    def is_healthy(self) -> bool:
        """Vérifie si la VM est en bonne santé."""
        return (
            self.state == "Running"
            and self.heartbeat in ("OkApplicationsHealthy", "OkApplicationsUnknown", "Ok")
        )
    
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
        pass

    @abstractmethod
    async def list_vms(self) -> list[VMInfo]:
        """
        Liste toutes les VMs sur l'hyperviseur.
        
        Returns:
            Liste des VMs
        """
        pass

    @abstractmethod
    async def get_vm(self, vm_id: str) -> VMInfo | None:
        """
        Récupère les informations d'une VM.
        
        Args:
            vm_id: ID ou nom de la VM
            
        Returns:
            Informations de la VM ou None si non trouvée
        """
        pass

    @abstractmethod
    async def create_vm(self, specs: VMSpecs) -> VMInfo:
        """
        Crée une nouvelle VM.
        
        Args:
            specs: Spécifications de la VM
            
        Returns:
            Informations de la VM créée
        """
        pass

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
        pass

    @abstractmethod
    async def start_vm(self, vm_id: str) -> bool:
        """
        Démarre une VM.
        
        Args:
            vm_id: ID ou nom de la VM
            
        Returns:
            True si le démarrage a réussi
        """
        pass

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
        pass

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
        pass

    @abstractmethod
    async def get_vm_state(self, vm_id: str) -> str | None:
        """
        Récupère l'état d'une VM.
        
        Args:
            vm_id: ID ou nom de la VM
            
        Returns:
            État de la VM (Running, Off, Paused, etc.) ou None
        """
        pass

    @abstractmethod
    async def list_switches(self) -> list[VirtualSwitch]:
        """
        Liste les switches virtuels disponibles.
        
        Returns:
            Liste des switches
        """
        pass

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
        pass

    @abstractmethod
    async def unmount_iso(self, vm_id: str) -> bool:
        """
        Démonte l'ISO du lecteur DVD d'une VM.
        
        Args:
            vm_id: ID ou nom de la VM
            
        Returns:
            True si le démontage a réussi
        """
        pass

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
        pass

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
        pass

    @abstractmethod
    async def get_vm_heartbeat(self, vm_id: str) -> str | None:
        """
        Récupère le statut heartbeat d'une VM.
        
        Args:
            vm_id: ID ou nom de la VM
            
        Returns:
            Statut heartbeat (OkApplicationsHealthy, NoContact, etc.) ou None
        """
        pass

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
        pass

    @abstractmethod
    async def get_vm_ip_addresses(self, vm_id: str) -> list[str]:
        """
        Récupère les adresses IP d'une VM.
        
        Args:
            vm_id: ID ou nom de la VM
            
        Returns:
            Liste des adresses IP
        """
        pass

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
        pass

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
        pass
