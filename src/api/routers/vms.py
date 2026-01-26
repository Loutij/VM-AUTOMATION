# =============================================================================
# VM Automation - Virtual Machines Router
# =============================================================================
"""
Endpoints CRUD pour la gestion des machines virtuelles.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from src.api.dependencies import DbSession, Pagination
from src.common.logging import get_logger
from src.domain.models import VMState
from src.domain.vm_service import VMService

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================


class VMBase(BaseModel):
    """Schéma de base pour une VM."""

    name: str = Field(..., min_length=1, max_length=100, description="Nom de la VM")
    cpu_count: int = Field(default=2, ge=1, le=64, description="Nombre de CPUs")
    ram_gb: int = Field(default=4, ge=1, le=512, description="RAM en GB")
    disk_gb: int = Field(default=60, ge=10, le=2048, description="Disque en GB")


class VMCreate(VMBase):
    """Schéma pour créer une VM."""

    hypervisor_id: UUID = Field(..., description="ID de l'hyperviseur cible")
    template_id: UUID | None = Field(None, description="ID du template OS")
    network_switch: str | None = Field(None, description="Switch réseau")


class VMUpdate(BaseModel):
    """Schéma pour mettre à jour une VM."""

    name: str | None = Field(None, min_length=1, max_length=100)
    cpu_count: int | None = Field(None, ge=1, le=64)
    ram_gb: int | None = Field(None, ge=1, le=512)
    notes: str | None = None


class VMResponse(VMBase):
    """Schéma de réponse pour une VM."""

    id: UUID
    hypervisor_id: UUID
    hypervisor_vm_id: str | None = None
    state: str
    ip_address: str | None = None
    os_template_id: UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class VMList(BaseModel):
    """Schéma pour la liste paginée de VMs."""

    items: list[VMResponse]
    total: int
    page: int
    page_size: int


class VMAction(BaseModel):
    """Résultat d'une action sur une VM."""

    success: bool
    message: str
    vm_id: UUID
    state: str


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=VMList,
    summary="Lister les VMs",
    description="Retourne la liste paginée des machines virtuelles.",
)
async def list_vms(
    db: DbSession,
    pagination: Pagination,
    hypervisor_id: Annotated[UUID | None, Query(description="Filtrer par hyperviseur")] = None,
    state: Annotated[str | None, Query(description="Filtrer par état")] = None,
) -> VMList:
    """Liste toutes les VMs avec filtres optionnels."""
    logger.info(
        "listing_vms",
        page=pagination.page,
        page_size=pagination.page_size,
        hypervisor_id=str(hypervisor_id) if hypervisor_id else None,
        state=state,
    )
    
    service = VMService(db)
    
    # Mapper l'état si fourni
    vm_state = None
    if state:
        try:
            vm_state = VMState(state)
        except ValueError:
            pass
    
    vms = await service.list_vms(hypervisor_id=hypervisor_id, state=vm_state)
    
    # Pagination simple
    total = len(vms)
    start = (pagination.page - 1) * pagination.page_size
    end = start + pagination.page_size
    items = vms[start:end]
    
    return VMList(
        items=[VMResponse(
            id=vm.id,
            name=vm.name,
            hypervisor_id=vm.hypervisor_id,
            hypervisor_vm_id=vm.hypervisor_vm_id,
            cpu_count=vm.cpu_count,
            ram_gb=vm.ram_gb,
            disk_gb=vm.disk_gb,
            state=vm.state.value,
            ip_address=vm.ip_address,
            os_template_id=vm.os_template_id,
            created_at=vm.created_at,
            updated_at=vm.updated_at,
        ) for vm in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post(
    "",
    response_model=VMResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer une VM",
    description="Crée une nouvelle machine virtuelle sur l'hyperviseur.",
)
async def create_vm(
    db: DbSession,
    vm_data: VMCreate,
) -> VMResponse:
    """Crée une nouvelle VM."""
    logger.info(
        "creating_vm",
        name=vm_data.name,
        hypervisor_id=str(vm_data.hypervisor_id),
    )
    
    service = VMService(db)
    
    vm = await service.create_vm(
        name=vm_data.name,
        hypervisor_id=vm_data.hypervisor_id,
        cpu_count=vm_data.cpu_count,
        ram_gb=vm_data.ram_gb,
        disk_gb=vm_data.disk_gb,
        network_switch=vm_data.network_switch,
        template_id=vm_data.template_id,
    )
    
    await db.commit()
    
    return VMResponse(
        id=vm.id,
        name=vm.name,
        hypervisor_id=vm.hypervisor_id,
        hypervisor_vm_id=vm.hypervisor_vm_id,
        cpu_count=vm.cpu_count,
        ram_gb=vm.ram_gb,
        disk_gb=vm.disk_gb,
        state=vm.state.value,
        ip_address=vm.ip_address,
        os_template_id=vm.os_template_id,
        created_at=vm.created_at,
        updated_at=vm.updated_at,
    )


@router.get(
    "/{vm_id}",
    response_model=VMResponse,
    summary="Obtenir une VM",
    description="Retourne les détails d'une VM spécifique.",
)
async def get_vm(
    db: DbSession,
    vm_id: UUID,
) -> VMResponse:
    """Récupère une VM par son ID."""
    logger.info("getting_vm", vm_id=str(vm_id))
    
    service = VMService(db)
    vm = await service.get_vm(vm_id)
    
    return VMResponse(
        id=vm.id,
        name=vm.name,
        hypervisor_id=vm.hypervisor_id,
        hypervisor_vm_id=vm.hypervisor_vm_id,
        cpu_count=vm.cpu_count,
        ram_gb=vm.ram_gb,
        disk_gb=vm.disk_gb,
        state=vm.state.value,
        ip_address=vm.ip_address,
        os_template_id=vm.os_template_id,
        created_at=vm.created_at,
        updated_at=vm.updated_at,
    )


@router.patch(
    "/{vm_id}",
    response_model=VMResponse,
    summary="Mettre à jour une VM",
    description="Met à jour les informations d'une VM.",
)
async def update_vm(
    db: DbSession,
    vm_id: UUID,
    vm_data: VMUpdate,
) -> VMResponse:
    """Met à jour une VM existante."""
    logger.info(
        "updating_vm",
        vm_id=str(vm_id),
        fields=vm_data.model_dump(exclude_unset=True),
    )
    
    service = VMService(db)
    vm = await service.get_vm(vm_id)
    
    # Appliquer les mises à jour
    update_data = vm_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(vm, field, value)
    
    await db.commit()
    await db.refresh(vm)
    
    return VMResponse(
        id=vm.id,
        name=vm.name,
        hypervisor_id=vm.hypervisor_id,
        hypervisor_vm_id=vm.hypervisor_vm_id,
        cpu_count=vm.cpu_count,
        ram_gb=vm.ram_gb,
        disk_gb=vm.disk_gb,
        state=vm.state.value,
        ip_address=vm.ip_address,
        os_template_id=vm.os_template_id,
        created_at=vm.created_at,
        updated_at=vm.updated_at,
    )


@router.delete(
    "/{vm_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer une VM",
    description="Supprime une VM.",
)
async def delete_vm(
    db: DbSession,
    vm_id: UUID,
    delete_disks: Annotated[bool, Query(description="Supprimer aussi les disques")] = False,
) -> None:
    """Supprime une VM."""
    logger.info("deleting_vm", vm_id=str(vm_id), delete_disks=delete_disks)
    
    service = VMService(db)
    await service.delete_vm(vm_id, delete_disks=delete_disks)
    await db.commit()


# =============================================================================
# Actions
# =============================================================================


@router.post(
    "/{vm_id}/start",
    response_model=VMAction,
    summary="Démarrer une VM",
    description="Démarre une VM arrêtée.",
)
async def start_vm(
    db: DbSession,
    vm_id: UUID,
) -> VMAction:
    """Démarre une VM."""
    logger.info("starting_vm", vm_id=str(vm_id))
    
    service = VMService(db)
    vm = await service.start_vm(vm_id)
    await db.commit()
    
    return VMAction(
        success=True,
        message="VM started successfully",
        vm_id=vm.id,
        state=vm.state.value,
    )


@router.post(
    "/{vm_id}/stop",
    response_model=VMAction,
    summary="Arrêter une VM",
    description="Arrête une VM en cours d'exécution.",
)
async def stop_vm(
    db: DbSession,
    vm_id: UUID,
    force: Annotated[bool, Query(description="Forcer l'arrêt")] = False,
) -> VMAction:
    """Arrête une VM."""
    logger.info("stopping_vm", vm_id=str(vm_id), force=force)
    
    service = VMService(db)
    vm = await service.stop_vm(vm_id, force=force)
    await db.commit()
    
    return VMAction(
        success=True,
        message="VM stopped successfully",
        vm_id=vm.id,
        state=vm.state.value,
    )


@router.post(
    "/{vm_id}/restart",
    response_model=VMAction,
    summary="Redémarrer une VM",
    description="Redémarre une VM.",
)
async def restart_vm(
    db: DbSession,
    vm_id: UUID,
    force: Annotated[bool, Query(description="Forcer le redémarrage")] = False,
) -> VMAction:
    """Redémarre une VM."""
    logger.info("restarting_vm", vm_id=str(vm_id), force=force)
    
    service = VMService(db)
    vm = await service.restart_vm(vm_id, force=force)
    await db.commit()
    
    return VMAction(
        success=True,
        message="VM restarted successfully",
        vm_id=vm.id,
        state=vm.state.value,
    )


@router.post(
    "/{vm_id}/sync",
    response_model=VMResponse,
    summary="Synchroniser l'état",
    description="Synchronise l'état de la VM avec l'hyperviseur.",
)
async def sync_vm_state(
    db: DbSession,
    vm_id: UUID,
) -> VMResponse:
    """Synchronise l'état de la VM depuis l'hyperviseur."""
    logger.info("syncing_vm_state", vm_id=str(vm_id))
    
    service = VMService(db)
    vm = await service.sync_vm_state(vm_id)
    await db.commit()
    
    return VMResponse(
        id=vm.id,
        name=vm.name,
        hypervisor_id=vm.hypervisor_id,
        hypervisor_vm_id=vm.hypervisor_vm_id,
        cpu_count=vm.cpu_count,
        ram_gb=vm.ram_gb,
        disk_gb=vm.disk_gb,
        state=vm.state.value,
        ip_address=vm.ip_address,
        os_template_id=vm.os_template_id,
        created_at=vm.created_at,
        updated_at=vm.updated_at,
    )
