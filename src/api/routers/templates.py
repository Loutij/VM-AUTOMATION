# =============================================================================
# VM Automation - OS Templates Router
# =============================================================================
"""
Endpoints CRUD pour la gestion des templates OS.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from src.api.dependencies import CurrentUser, DbSession, Pagination
from src.common.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================


class OSTemplateBase(BaseModel):
    """Schéma de base pour un template OS."""

    name: str = Field(..., min_length=1, max_length=100, description="Nom du template")
    os_family: str = Field(..., pattern="^(windows|linux)$", description="Famille OS")
    os_type: str = Field(..., min_length=1, max_length=50, description="Type OS spécifique")
    architecture: str = Field(default="x64", pattern="^(x64|x86|arm64)$")
    iso_path: str = Field(..., min_length=1, max_length=500, description="Chemin vers l'ISO")
    min_cpu: int = Field(default=1, ge=1, description="CPU minimum requis")
    min_ram_gb: int = Field(default=2, ge=1, description="RAM minimum en GB")
    min_disk_gb: int = Field(default=20, ge=10, description="Disque minimum en GB")


class OSTemplateCreate(OSTemplateBase):
    """Schéma pour créer un template OS."""

    unattend_template: str | None = Field(None, description="Template Jinja2 pour unattend/preseed")


class OSTemplateUpdate(BaseModel):
    """Schéma pour mettre à jour un template OS."""

    name: str | None = Field(None, min_length=1, max_length=100)
    iso_path: str | None = Field(None, min_length=1, max_length=500)
    min_cpu: int | None = Field(None, ge=1)
    min_ram_gb: int | None = Field(None, ge=1)
    min_disk_gb: int | None = Field(None, ge=10)
    unattend_template: str | None = None
    is_active: bool | None = None


class OSTemplateResponse(OSTemplateBase):
    """Schéma de réponse pour un template OS."""

    id: UUID
    is_active: bool
    created_at: str
    updated_at: str | None

    class Config:
        from_attributes = True


class OSTemplateList(BaseModel):
    """Schéma pour la liste paginée de templates."""

    items: list[OSTemplateResponse]
    total: int
    page: int
    page_size: int


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=OSTemplateList,
    summary="Lister les templates OS",
    description="Retourne la liste paginée des templates OS disponibles.",
)
async def list_templates(
    db: DbSession,
    pagination: Pagination,
    os_family: Annotated[str | None, Query(description="Filtrer par famille OS")] = None,
    is_active: Annotated[bool | None, Query(description="Filtrer par statut actif")] = None,
) -> OSTemplateList:
    """Liste tous les templates OS avec filtres optionnels."""
    logger.info(
        "listing_templates",
        page=pagination.page,
        page_size=pagination.page_size,
        os_family=os_family,
        is_active=is_active,
    )
    
    # TODO: Implémenter la requête DB
    return OSTemplateList(
        items=[],
        total=0,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post(
    "",
    response_model=OSTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un template OS",
    description="Ajoute un nouveau template OS.",
)
async def create_template(
    db: DbSession,
    template: OSTemplateCreate,
    # user: CurrentUser,
) -> OSTemplateResponse:
    """Crée un nouveau template OS."""
    logger.info(
        "creating_template",
        name=template.name,
        os_family=template.os_family,
        os_type=template.os_type,
    )
    
    # TODO: Implémenter la création en DB
    # TODO: Valider que l'ISO existe
    raise NotImplementedError("Template creation not implemented yet")


@router.get(
    "/{template_id}",
    response_model=OSTemplateResponse,
    summary="Obtenir un template OS",
    description="Retourne les détails d'un template OS spécifique.",
)
async def get_template(
    db: DbSession,
    template_id: UUID,
) -> OSTemplateResponse:
    """Récupère un template OS par son ID."""
    logger.info("getting_template", template_id=str(template_id))
    
    # TODO: Implémenter la requête DB
    raise NotImplementedError("Template retrieval not implemented yet")


@router.patch(
    "/{template_id}",
    response_model=OSTemplateResponse,
    summary="Mettre à jour un template OS",
    description="Met à jour les informations d'un template OS.",
)
async def update_template(
    db: DbSession,
    template_id: UUID,
    template: OSTemplateUpdate,
    # user: CurrentUser,
) -> OSTemplateResponse:
    """Met à jour un template OS existant."""
    logger.info(
        "updating_template",
        template_id=str(template_id),
        fields=template.model_dump(exclude_unset=True),
    )
    
    # TODO: Implémenter la mise à jour en DB
    raise NotImplementedError("Template update not implemented yet")


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un template OS",
    description="Supprime un template OS.",
)
async def delete_template(
    db: DbSession,
    template_id: UUID,
    # user: CurrentUser,
) -> None:
    """Supprime un template OS."""
    logger.info("deleting_template", template_id=str(template_id))
    
    # TODO: Implémenter la suppression en DB
    # TODO: Vérifier qu'aucune VM n'utilise ce template
    raise NotImplementedError("Template deletion not implemented yet")


@router.post(
    "/{template_id}/validate",
    summary="Valider un template",
    description="Valide la configuration d'un template OS.",
)
async def validate_template(
    db: DbSession,
    template_id: UUID,
) -> dict:
    """Valide un template OS (vérifie l'ISO, le template Jinja2, etc.)."""
    logger.info("validating_template", template_id=str(template_id))
    
    # TODO: Implémenter la validation
    return {
        "status": "not_implemented",
        "message": "Template validation not implemented yet",
    }
