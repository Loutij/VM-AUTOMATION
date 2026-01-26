# =============================================================================
# VM Automation - Hypervisors Router
# =============================================================================
"""
Endpoints CRUD pour la gestion des hyperviseurs.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from src.api.dependencies import DbSession, Pagination
from src.common.logging import get_logger
from src.domain.models import HypervisorType
from src.domain.vm_service import VMService

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================


class HypervisorBase(BaseModel):
    """Schéma de base pour un hyperviseur."""

    name: str = Field(..., min_length=1, max_length=100, description="Nom de l'hyperviseur")
    hypervisor_type: str = Field(..., pattern="^(hyperv|vmware)$", description="Type d'hyperviseur")
    host: str = Field(..., min_length=1, max_length=255, description="Adresse de l'hôte")
    port: int = Field(default=5985, ge=1, le=65535, description="Port de connexion")
    use_ssl: bool = Field(default=False, description="Utiliser SSL")
    username: str = Field(..., min_length=1, max_length=100, description="Nom d'utilisateur")


class HypervisorCreate(HypervisorBase):
    """Schéma pour créer un hyperviseur."""

    password: str = Field(..., min_length=1, description="Mot de passe")


class HypervisorUpdate(BaseModel):
    """Schéma pour mettre à jour un hyperviseur."""

    name: str | None = Field(None, min_length=1, max_length=100)
    host: str | None = Field(None, min_length=1, max_length=255)
    port: int | None = Field(None, ge=1, le=65535)
    use_ssl: bool | None = None
    username: str | None = Field(None, min_length=1, max_length=100)
    password: str | None = Field(None, min_length=1)
    is_active: bool | None = None


class HypervisorResponse(BaseModel):
    """Schéma de réponse pour un hyperviseur."""

    id: UUID
    name: str
    hypervisor_type: str
    host: str
    port: int
    use_ssl: bool
    username: str
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class HypervisorList(BaseModel):
    """Schéma pour la liste paginée d'hyperviseurs."""

    items: list[HypervisorResponse]
    total: int
    page: int
    page_size: int


class ConnectionTestResult(BaseModel):
    """Résultat du test de connexion."""

    success: bool
    message: str
    details: dict | None = None


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=HypervisorList,
    summary="Lister les hyperviseurs",
    description="Retourne la liste paginée des hyperviseurs configurés.",
)
async def list_hypervisors(
    db: DbSession,
    pagination: Pagination,
    is_active: Annotated[bool | None, Query(description="Filtrer par statut actif")] = None,
    hypervisor_type: Annotated[str | None, Query(description="Filtrer par type")] = None,
) -> HypervisorList:
    """Liste tous les hyperviseurs avec filtres optionnels."""
    logger.info(
        "listing_hypervisors",
        page=pagination.page,
        page_size=pagination.page_size,
        is_active=is_active,
        hypervisor_type=hypervisor_type,
    )
    
    service = VMService(db)
    hypervisors = await service.list_hypervisors()
    
    # Filtrage simple (à améliorer avec requêtes DB)
    if is_active is not None:
        hypervisors = [h for h in hypervisors if h.is_active == is_active]
    if hypervisor_type:
        hypervisors = [h for h in hypervisors if h.hypervisor_type.value == hypervisor_type]
    
    # Pagination simple
    total = len(hypervisors)
    start = (pagination.page - 1) * pagination.page_size
    end = start + pagination.page_size
    items = hypervisors[start:end]
    
    return HypervisorList(
        items=[HypervisorResponse.model_validate(h) for h in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post(
    "",
    response_model=HypervisorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un hyperviseur",
    description="Ajoute un nouvel hyperviseur à la configuration.",
)
async def create_hypervisor(
    db: DbSession,
    hypervisor: HypervisorCreate,
) -> HypervisorResponse:
    """Crée un nouvel hyperviseur."""
    logger.info(
        "creating_hypervisor",
        name=hypervisor.name,
        hypervisor_type=hypervisor.hypervisor_type,
        host=hypervisor.host,
    )
    
    service = VMService(db)
    
    # Mapper le type
    hv_type = HypervisorType.HYPERV if hypervisor.hypervisor_type == "hyperv" else HypervisorType.VMWARE
    
    created = await service.create_hypervisor(
        name=hypervisor.name,
        host=hypervisor.host,
        hypervisor_type=hv_type,
        username=hypervisor.username,
        password=hypervisor.password,
        use_ssl=hypervisor.use_ssl,
        port=hypervisor.port,
    )
    
    await db.commit()
    
    return HypervisorResponse.model_validate(created)


@router.get(
    "/{hypervisor_id}",
    response_model=HypervisorResponse,
    summary="Obtenir un hyperviseur",
    description="Retourne les détails d'un hyperviseur spécifique.",
)
async def get_hypervisor(
    db: DbSession,
    hypervisor_id: UUID,
) -> HypervisorResponse:
    """Récupère un hyperviseur par son ID."""
    logger.info("getting_hypervisor", hypervisor_id=str(hypervisor_id))
    
    service = VMService(db)
    hypervisor = await service.get_hypervisor(hypervisor_id)
    
    return HypervisorResponse.model_validate(hypervisor)


@router.patch(
    "/{hypervisor_id}",
    response_model=HypervisorResponse,
    summary="Mettre à jour un hyperviseur",
    description="Met à jour les informations d'un hyperviseur.",
)
async def update_hypervisor(
    db: DbSession,
    hypervisor_id: UUID,
    hypervisor: HypervisorUpdate,
) -> HypervisorResponse:
    """Met à jour un hyperviseur existant."""
    logger.info(
        "updating_hypervisor",
        hypervisor_id=str(hypervisor_id),
        fields=hypervisor.model_dump(exclude_unset=True),
    )
    
    service = VMService(db)
    existing = await service.get_hypervisor(hypervisor_id)
    
    # Appliquer les mises à jour
    update_data = hypervisor.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(existing, field, value)
    
    await db.commit()
    await db.refresh(existing)
    
    return HypervisorResponse.model_validate(existing)


@router.delete(
    "/{hypervisor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un hyperviseur",
    description="Supprime un hyperviseur de la configuration.",
)
async def delete_hypervisor(
    db: DbSession,
    hypervisor_id: UUID,
) -> None:
    """Supprime un hyperviseur."""
    logger.info("deleting_hypervisor", hypervisor_id=str(hypervisor_id))
    
    service = VMService(db)
    hypervisor = await service.get_hypervisor(hypervisor_id)
    
    await db.delete(hypervisor)
    await db.commit()


@router.post(
    "/{hypervisor_id}/test",
    response_model=ConnectionTestResult,
    summary="Tester la connexion",
    description="Teste la connexion à un hyperviseur.",
)
async def test_hypervisor_connection(
    db: DbSession,
    hypervisor_id: UUID,
) -> ConnectionTestResult:
    """Teste la connexion à un hyperviseur."""
    logger.info("testing_hypervisor_connection", hypervisor_id=str(hypervisor_id))
    
    service = VMService(db)
    
    try:
        success = await service.test_hypervisor_connection(hypervisor_id)
        
        if success:
            return ConnectionTestResult(
                success=True,
                message="Connection successful",
            )
        else:
            return ConnectionTestResult(
                success=False,
                message="Connection failed",
            )
    except Exception as e:
        return ConnectionTestResult(
            success=False,
            message=f"Connection error: {str(e)}",
            details={"error_type": type(e).__name__},
        )


@router.get(
    "/{hypervisor_id}/vms",
    summary="Lister les VMs sur l'hyperviseur",
    description="Liste les VMs directement depuis l'hyperviseur (non depuis la DB).",
)
async def list_hypervisor_vms(
    db: DbSession,
    hypervisor_id: UUID,
) -> list[dict]:
    """Liste les VMs directement depuis l'hyperviseur."""
    logger.info("listing_hypervisor_vms", hypervisor_id=str(hypervisor_id))
    
    service = VMService(db)
    client = await service._get_hypervisor_client(hypervisor_id)
    
    vms = await client.list_vms()
    
    return [vm.to_dict() for vm in vms]


@router.get(
    "/{hypervisor_id}/switches",
    summary="Lister les switches virtuels",
    description="Liste les switches virtuels disponibles sur l'hyperviseur.",
)
async def list_hypervisor_switches(
    db: DbSession,
    hypervisor_id: UUID,
) -> list[dict]:
    """Liste les switches virtuels de l'hyperviseur."""
    logger.info("listing_hypervisor_switches", hypervisor_id=str(hypervisor_id))
    
    service = VMService(db)
    client = await service._get_hypervisor_client(hypervisor_id)
    
    switches = await client.list_switches()
    
    return [sw.to_dict() for sw in switches]
