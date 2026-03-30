# =============================================================================
# VM Automation - OS Templates Router
# =============================================================================
"""
Endpoints CRUD pour la gestion des templates OS.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import CurrentUser, DbSession, Pagination, RequireAdmin
from src.common.logging import get_logger
from src.domain.models import OSTemplate, OSFamily, Architecture

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
    install_locale: str = Field(
        default="fr-FR",
        max_length=10,
        pattern="^[a-z]{2}-[A-Z]{2}$",
        description="Langue d'installation (ex: fr-FR, en-US)"
    )


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
    install_locale: str | None = Field(
        None,
        max_length=10,
        pattern="^[a-z]{2}-[A-Z]{2}$",
        description="Langue d'installation"
    )
    unattend_template: str | None = None
    is_active: bool | None = None


class OSTemplateResponse(OSTemplateBase):
    """Schéma de réponse pour un template OS."""

    id: UUID
    install_locale: str
    is_active: bool
    created_at: datetime
    updated_at: datetime | None

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
    current_user: CurrentUser,
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
    
    # Construire la requête
    query = select(OSTemplate)
    count_query = select(func.count()).select_from(OSTemplate)
    
    # Appliquer les filtres
    if os_family:
        try:
            family_enum = OSFamily(os_family)
            query = query.where(OSTemplate.os_family == family_enum)
            count_query = count_query.where(OSTemplate.os_family == family_enum)
        except ValueError:
            pass  # Ignorer si la valeur n'est pas valide
    
    if is_active is not None:
        query = query.where(OSTemplate.is_active == is_active)
        count_query = count_query.where(OSTemplate.is_active == is_active)
    
    # Compter le total
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Pagination
    offset = (pagination.page - 1) * pagination.page_size
    query = query.offset(offset).limit(pagination.page_size)
    
    # Exécuter
    result = await db.execute(query)
    templates = result.scalars().all()
    
    return OSTemplateList(
        items=[_template_to_response(t) for t in templates],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


def _template_to_response(template: OSTemplate) -> OSTemplateResponse:
    """Convertit un modèle OSTemplate en réponse API."""
    return OSTemplateResponse(
        id=template.id,
        name=template.name,
        os_family=template.os_family.value,
        os_type=template.os_type,
        architecture=template.architecture.value,
        iso_path=template.iso_path,
        min_cpu=template.min_cpu,
        min_ram_gb=template.min_ram_gb,
        min_disk_gb=template.min_disk_gb,
        install_locale=template.install_locale,
        is_active=template.is_active,
        created_at=template.created_at.isoformat() if template.created_at else "",
        updated_at=template.updated_at.isoformat() if template.updated_at else None,
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
    user: RequireAdmin,
) -> OSTemplateResponse:
    """Crée un nouveau template OS."""
    logger.info(
        "creating_template",
        name=template.name,
        os_family=template.os_family,
        os_type=template.os_type,
    )
    
    # Vérifier si un template avec le même nom existe
    existing = await db.execute(
        select(OSTemplate).where(OSTemplate.name == template.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Un template avec le nom '{template.name}' existe déjà",
        )
    
    # Créer le template
    try:
        os_family_enum = OSFamily(template.os_family)
        arch_enum = Architecture(template.architecture)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Valeur invalide: {e}",
        )
    
    db_template = OSTemplate(
        name=template.name,
        os_family=os_family_enum,
        os_type=template.os_type,
        architecture=arch_enum,
        iso_path=template.iso_path,
        unattend_template=template.unattend_template,
        min_cpu=template.min_cpu,
        min_ram_gb=template.min_ram_gb,
        min_disk_gb=template.min_disk_gb,
        install_locale=template.install_locale,
    )
    
    db.add(db_template)
    await db.commit()
    await db.refresh(db_template)
    
    logger.info("template_created", template_id=str(db_template.id), name=db_template.name)
    return _template_to_response(db_template)


@router.get(
    "/{template_id}",
    response_model=OSTemplateResponse,
    summary="Obtenir un template OS",
    description="Retourne les détails d'un template OS spécifique.",
)
async def get_template(
    db: DbSession,
    template_id: UUID,
    current_user: CurrentUser,
) -> OSTemplateResponse:
    """Récupère un template OS par son ID."""
    logger.info("getting_template", template_id=str(template_id))
    
    result = await db.execute(
        select(OSTemplate).where(OSTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template avec l'ID '{template_id}' non trouvé",
        )
    
    return _template_to_response(template)


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
    user: RequireAdmin,
) -> OSTemplateResponse:
    """Met à jour un template OS existant."""
    logger.info(
        "updating_template",
        template_id=str(template_id),
        fields=template.model_dump(exclude_unset=True),
    )
    
    # Récupérer le template
    result = await db.execute(
        select(OSTemplate).where(OSTemplate.id == template_id)
    )
    db_template = result.scalar_one_or_none()
    
    if not db_template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template avec l'ID '{template_id}' non trouvé",
        )
    
    # Mettre à jour les champs fournis
    update_data = template.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(db_template, field, value)
    
    await db.commit()
    await db.refresh(db_template)
    
    logger.info("template_updated", template_id=str(template_id))
    return _template_to_response(db_template)


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un template OS",
    description="Supprime un template OS.",
)
async def delete_template(
    db: DbSession,
    template_id: UUID,
    user: RequireAdmin,
) -> None:
    """Supprime un template OS."""
    logger.info("deleting_template", template_id=str(template_id))
    
    # Récupérer le template
    result = await db.execute(
        select(OSTemplate).where(OSTemplate.id == template_id)
    )
    db_template = result.scalar_one_or_none()
    
    if not db_template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template avec l'ID '{template_id}' non trouvé",
        )
    
    # Vérifier qu'aucune VM n'utilise ce template
    from src.domain.models import VirtualMachine
    vm_result = await db.execute(
        select(func.count()).select_from(VirtualMachine).where(
            VirtualMachine.os_template_id == template_id
        )
    )
    vm_count = vm_result.scalar() or 0
    
    if vm_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Impossible de supprimer: {vm_count} VM(s) utilisent ce template",
        )
    
    await db.delete(db_template)
    await db.commit()
    
    logger.info("template_deleted", template_id=str(template_id))


@router.post(
    "/{template_id}/validate",
    summary="Valider un template",
    description="Valide la configuration d'un template OS.",
)
async def validate_template(
    db: DbSession,
    template_id: UUID,
    current_user: CurrentUser,
) -> dict:
    """Valide un template OS (vérifie l'ISO, le template Jinja2, etc.)."""
    logger.info("validating_template", template_id=str(template_id))
    
    # Récupérer le template
    result = await db.execute(
        select(OSTemplate).where(OSTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template avec l'ID '{template_id}' non trouvé",
        )
    
    validation_results = {
        "template_id": str(template_id),
        "name": template.name,
        "valid": True,
        "checks": [],
        "errors": [],
    }
    
    # Check 1: ISO path format
    if template.iso_path:
        validation_results["checks"].append({
            "name": "iso_path_format",
            "status": "ok",
            "message": f"ISO path défini: {template.iso_path}",
        })
    else:
        validation_results["valid"] = False
        validation_results["errors"].append("ISO path non défini")
    
    # Check 2: Minimum requirements
    if template.min_cpu >= 1 and template.min_ram_gb >= 1 and template.min_disk_gb >= 10:
        validation_results["checks"].append({
            "name": "min_requirements",
            "status": "ok",
            "message": f"CPU: {template.min_cpu}, RAM: {template.min_ram_gb}GB, Disk: {template.min_disk_gb}GB",
        })
    else:
        validation_results["valid"] = False
        validation_results["errors"].append("Exigences minimales invalides")
    
    # Check 3: Unattend template (if provided)
    if template.unattend_template:
        # Vérification basique Jinja2
        try:
            from jinja2 import Environment
            env = Environment()
            env.parse(template.unattend_template)
            validation_results["checks"].append({
                "name": "unattend_template",
                "status": "ok",
                "message": "Template Jinja2 syntaxiquement valide",
            })
        except Exception as e:
            validation_results["valid"] = False
            validation_results["errors"].append(f"Template Jinja2 invalide: {e}")
    
    return validation_results
