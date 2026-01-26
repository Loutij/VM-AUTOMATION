# =============================================================================
# VM Automation - VM Service
# =============================================================================
"""
Service métier pour la gestion des machines virtuelles.
Orchestre les opérations entre l'API, la base de données et l'hyperviseur.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.config import settings
from src.common.exceptions import (
    AlreadyExistsError,
    NotFoundError,
    ValidationError,
    VMCreationError,
    VMOperationError,
)
from src.common.logging import get_logger
from src.domain.models import (
    Deployment,
    DeploymentLog,
    DeploymentStatus,
    Hypervisor,
    HypervisorType,
    OSTemplate,
    VirtualMachine,
    VMState,
)
from src.domain.template_engine import get_template_engine
from src.integrations.hypervisors import HyperVClient, VMSpecs

logger = get_logger(__name__)


class VMService:
    """
    Service pour la gestion des VMs.
    
    Responsabilités:
    - CRUD des VMs en base de données
    - Synchronisation avec l'hyperviseur
    - Orchestration des déploiements
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialise le service.
        
        Args:
            db: Session de base de données
        """
        self.db = db
        self._hypervisor_clients: dict[UUID, HyperVClient] = {}

    async def _get_hypervisor_client(self, hypervisor_id: UUID) -> HyperVClient:
        """Récupère ou crée un client pour l'hyperviseur."""
        if hypervisor_id not in self._hypervisor_clients:
            # Récupérer l'hyperviseur de la DB
            result = await self.db.execute(
                select(Hypervisor).where(Hypervisor.id == hypervisor_id)
            )
            hypervisor = result.scalar_one_or_none()
            
            if not hypervisor:
                raise NotFoundError("Hypervisor", str(hypervisor_id))
            
            if hypervisor.type != HypervisorType.HYPERV:
                raise ValidationError(
                    f"Unsupported hypervisor type: {hypervisor.type}"
                )
            
            self._hypervisor_clients[hypervisor_id] = HyperVClient(
                host=hypervisor.host,
                username=hypervisor.username,
                password=hypervisor.password,
                use_ssl=hypervisor.use_ssl,
            )
        
        return self._hypervisor_clients[hypervisor_id]

    # =========================================================================
    # Hypervisor Operations
    # =========================================================================

    async def list_hypervisors(self) -> list[Hypervisor]:
        """Liste tous les hyperviseurs."""
        result = await self.db.execute(select(Hypervisor))
        return list(result.scalars().all())

    async def get_hypervisor(self, hypervisor_id: UUID) -> Hypervisor:
        """Récupère un hyperviseur par son ID."""
        result = await self.db.execute(
            select(Hypervisor).where(Hypervisor.id == hypervisor_id)
        )
        hypervisor = result.scalar_one_or_none()
        if not hypervisor:
            raise NotFoundError("Hypervisor", str(hypervisor_id))
        return hypervisor

    async def create_hypervisor(
        self,
        name: str,
        host: str,
        hypervisor_type: HypervisorType,
        username: str,
        password: str,
        use_ssl: bool = True,
        **kwargs: Any,
    ) -> Hypervisor:
        """Crée un nouvel hyperviseur."""
        # Vérifier l'unicité du nom
        existing = await self.db.execute(
            select(Hypervisor).where(Hypervisor.name == name)
        )
        if existing.scalar_one_or_none():
            raise AlreadyExistsError("Hypervisor", name)
        
        hypervisor = Hypervisor(
            id=uuid4(),
            name=name,
            host=host,
            type=hypervisor_type,
            username=username,
            password_encrypted=password,  # TODO: encrypt password
            use_ssl=use_ssl,
            **kwargs,
        )
        
        self.db.add(hypervisor)
        await self.db.flush()
        
        logger.info("hypervisor_created", name=name, host=host)
        return hypervisor

    async def test_hypervisor_connection(self, hypervisor_id: UUID) -> bool:
        """Teste la connexion à un hyperviseur."""
        client = await self._get_hypervisor_client(hypervisor_id)
        return await client.test_connection()

    # =========================================================================
    # VM Operations
    # =========================================================================

    async def list_vms(
        self,
        hypervisor_id: UUID | None = None,
        state: VMState | None = None,
    ) -> list[VirtualMachine]:
        """Liste les VMs avec filtres optionnels."""
        query = select(VirtualMachine)
        
        if hypervisor_id:
            query = query.where(VirtualMachine.hypervisor_id == hypervisor_id)
        if state:
            query = query.where(VirtualMachine.state == state)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_vm(self, vm_id: UUID) -> VirtualMachine:
        """Récupère une VM par son ID."""
        result = await self.db.execute(
            select(VirtualMachine).where(VirtualMachine.id == vm_id)
        )
        vm = result.scalar_one_or_none()
        if not vm:
            raise NotFoundError("VirtualMachine", str(vm_id))
        return vm

    async def get_vm_by_name(self, name: str) -> VirtualMachine | None:
        """Récupère une VM par son nom."""
        result = await self.db.execute(
            select(VirtualMachine).where(VirtualMachine.name == name)
        )
        return result.scalar_one_or_none()

    async def create_vm(
        self,
        name: str,
        hypervisor_id: UUID,
        cpu_count: int = 2,
        ram_gb: int = 4,
        disk_gb: int = 60,
        network_switch: str | None = None,
        vhdx_path: str | None = None,
        template_id: UUID | None = None,
        **kwargs: Any,
    ) -> VirtualMachine:
        """
        Crée une nouvelle VM sur l'hyperviseur.
        
        Args:
            name: Nom de la VM
            hypervisor_id: ID de l'hyperviseur cible
            cpu_count: Nombre de CPUs
            ram_gb: RAM en GB
            disk_gb: Disque en GB
            network_switch: Switch réseau (optionnel)
            vhdx_path: Chemin du dossier pour le disque VHDX (optionnel)
            template_id: ID du template OS (optionnel)
            
        Returns:
            VM créée
        """
        # Vérifier que la VM n'existe pas déjà
        existing = await self.get_vm_by_name(name)
        if existing:
            raise AlreadyExistsError("VirtualMachine", name)
        
        # Récupérer le client hyperviseur
        client = await self._get_hypervisor_client(hypervisor_id)
        hypervisor = await self.get_hypervisor(hypervisor_id)
        
        # Préparer les specs
        specs = VMSpecs(
            name=name,
            cpu_count=cpu_count,
            ram_gb=ram_gb,
            disk_gb=disk_gb,
            network_switch=network_switch or settings.hyperv_default_switch,
            vhdx_path=vhdx_path,  # Emplacement personnalisé du disque virtuel
        )
        
        # Si template spécifié, récupérer les infos ISO
        if template_id:
            template_result = await self.db.execute(
                select(OSTemplate).where(OSTemplate.id == template_id)
            )
            template = template_result.scalar_one_or_none()
            if template:
                specs.iso_path = template.iso_path
        
        logger.info(
            "creating_vm",
            name=name,
            hypervisor=hypervisor.name,
            specs=specs.__dict__,
        )
        
        # Créer la VM sur l'hyperviseur
        try:
            vm_info = await client.create_vm(specs)
        except Exception as e:
            logger.error("vm_creation_failed", name=name, error=str(e))
            raise VMCreationError(name, str(e))
        
        # Enregistrer en base
        vm = VirtualMachine(
            id=uuid4(),
            name=name,
            hypervisor_id=hypervisor_id,
            hypervisor_vm_id=vm_info.id,
            cpu_count=cpu_count,
            ram_gb=ram_gb,
            disk_gb=disk_gb,
            state=VMState.STOPPED,
            os_template_id=template_id,
            **kwargs,
        )
        
        self.db.add(vm)
        await self.db.flush()
        
        logger.info("vm_created", vm_id=str(vm.id), name=name)
        return vm

    async def delete_vm(
        self,
        vm_id: UUID,
        delete_disks: bool = False,
    ) -> bool:
        """Supprime une VM."""
        vm = await self.get_vm(vm_id)
        
        # Supprimer sur l'hyperviseur
        if vm.hypervisor_vm_id:
            client = await self._get_hypervisor_client(vm.hypervisor_id)
            await client.delete_vm(vm.hypervisor_vm_id, delete_disks=delete_disks)
        
        # Supprimer en base
        await self.db.delete(vm)
        await self.db.flush()
        
        logger.info("vm_deleted", vm_id=str(vm_id), name=vm.name)
        return True

    async def start_vm(self, vm_id: UUID) -> VirtualMachine:
        """Démarre une VM."""
        vm = await self.get_vm(vm_id)
        
        if vm.state == VMState.RUNNING:
            return vm
        
        client = await self._get_hypervisor_client(vm.hypervisor_id)
        await client.start_vm(vm.hypervisor_vm_id or vm.name)
        
        vm.state = VMState.RUNNING
        await self.db.flush()
        
        logger.info("vm_started", vm_id=str(vm_id))
        return vm

    async def stop_vm(self, vm_id: UUID, force: bool = False) -> VirtualMachine:
        """Arrête une VM."""
        vm = await self.get_vm(vm_id)
        
        if vm.state == VMState.STOPPED:
            return vm
        
        client = await self._get_hypervisor_client(vm.hypervisor_id)
        await client.stop_vm(vm.hypervisor_vm_id or vm.name, force=force)
        
        vm.state = VMState.STOPPED
        await self.db.flush()
        
        logger.info("vm_stopped", vm_id=str(vm_id), force=force)
        return vm

    async def restart_vm(self, vm_id: UUID, force: bool = False) -> VirtualMachine:
        """Redémarre une VM."""
        vm = await self.get_vm(vm_id)
        
        client = await self._get_hypervisor_client(vm.hypervisor_id)
        await client.restart_vm(vm.hypervisor_vm_id or vm.name, force=force)
        
        vm.state = VMState.RUNNING
        await self.db.flush()
        
        logger.info("vm_restarted", vm_id=str(vm_id))
        return vm

    async def sync_vm_state(self, vm_id: UUID) -> VirtualMachine:
        """Synchronise l'état de la VM avec l'hyperviseur."""
        vm = await self.get_vm(vm_id)
        
        client = await self._get_hypervisor_client(vm.hypervisor_id)
        state = await client.get_vm_state(vm.hypervisor_vm_id or vm.name)
        
        if state:
            state_mapping = {
                "Running": VMState.RUNNING,
                "Off": VMState.STOPPED,
                "Paused": VMState.PAUSED,
                "Saved": VMState.SUSPENDED,
            }
            vm.state = state_mapping.get(state, VMState.UNKNOWN)
            await self.db.flush()
        
        return vm

    # =========================================================================
    # Template Operations
    # =========================================================================

    async def list_templates(
        self,
        os_family: str | None = None,
        is_active: bool | None = None,
    ) -> list[OSTemplate]:
        """Liste les templates OS."""
        query = select(OSTemplate)
        
        if os_family:
            query = query.where(OSTemplate.os_family == os_family)
        if is_active is not None:
            query = query.where(OSTemplate.is_active == is_active)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_template(self, template_id: UUID) -> OSTemplate:
        """Récupère un template par son ID."""
        result = await self.db.execute(
            select(OSTemplate).where(OSTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        if not template:
            raise NotFoundError("OSTemplate", str(template_id))
        return template

    async def create_template(
        self,
        name: str,
        os_family: str,
        os_type: str,
        iso_path: str,
        **kwargs: Any,
    ) -> OSTemplate:
        """Crée un nouveau template OS."""
        template = OSTemplate(
            id=uuid4(),
            name=name,
            os_family=os_family,
            os_type=os_type,
            iso_path=iso_path,
            **kwargs,
        )
        
        self.db.add(template)
        await self.db.flush()
        
        logger.info("template_created", name=name, os_family=os_family)
        return template
