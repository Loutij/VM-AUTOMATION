# =============================================================================
# VM Automation - Software Catalog Router
# =============================================================================
"""
Endpoints pour la marketplace de logiciels.
Permet de gérer le catalogue de logiciels installables sur les VMs.
"""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from src.api.dependencies import DbSession, Pagination
from src.common.logging import get_logger
from src.domain.models import SoftwareCategory, SoftwarePackage, OSFamily

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================


class ConfigField(BaseModel):
    """Champ de configuration pour un logiciel."""
    
    name: str = Field(..., description="Nom du champ")
    type: str = Field(default="string", description="Type: string, number, boolean, select")
    label: str = Field(..., description="Label affiché")
    description: str | None = Field(None, description="Description du champ")
    required: bool = Field(default=False)
    default: Any = Field(None, description="Valeur par défaut")
    options: list[dict[str, str]] | None = Field(None, description="Options pour type select")


class SoftwareCreate(BaseModel):
    """Schéma pour créer un logiciel."""
    
    name: str = Field(..., min_length=1, max_length=100, description="Identifiant unique (ex: 7zip)")
    display_name: str = Field(..., min_length=1, max_length=150, description="Nom affiché")
    version: str = Field(default="latest", description="Version à installer")
    description: str | None = Field(None, description="Description complète")
    short_description: str | None = Field(None, max_length=255, description="Description courte")
    category: str = Field(default="other", description="Catégorie")
    tags: list[str] = Field(default_factory=list, description="Tags de recherche")
    os_family: str | None = Field(None, description="windows, linux ou null pour tous")
    package_manager: str = Field(default="chocolatey", description="Gestionnaire de paquets")
    package_id: str = Field(..., description="ID du package dans le gestionnaire")
    install_command_windows: str | None = Field(None, description="Commande d'installation Windows")
    install_command_linux: str | None = Field(None, description="Commande d'installation Linux")
    default_config: dict[str, Any] = Field(default_factory=dict, description="Configuration par défaut")
    config_schema: dict[str, Any] | None = Field(None, description="Schéma de configuration")
    icon: str | None = Field(None, description="URL ou nom d'icône")
    website: str | None = Field(None, description="Site web officiel")
    documentation_url: str | None = Field(None, description="URL documentation")
    dependencies: list[str] = Field(default_factory=list, description="Dépendances (package names)")
    conflicts: list[str] = Field(default_factory=list, description="Conflits (package names)")
    is_featured: bool = Field(default=False, description="Mettre en vedette")
    install_time_minutes: int = Field(default=5, ge=1, description="Temps d'installation estimé")


class SoftwareUpdate(BaseModel):
    """Schéma pour mettre à jour un logiciel."""
    
    display_name: str | None = Field(None, min_length=1, max_length=150)
    version: str | None = None
    description: str | None = None
    short_description: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    package_id: str | None = None
    install_command_windows: str | None = None
    install_command_linux: str | None = None
    default_config: dict[str, Any] | None = None
    config_schema: dict[str, Any] | None = None
    icon: str | None = None
    website: str | None = None
    documentation_url: str | None = None
    dependencies: list[str] | None = None
    conflicts: list[str] | None = None
    is_active: bool | None = None
    is_featured: bool | None = None
    install_time_minutes: int | None = None


class SoftwareResponse(BaseModel):
    """Schéma de réponse pour un logiciel."""
    
    id: UUID
    name: str
    display_name: str
    version: str
    description: str | None
    short_description: str | None
    category: str
    tags: list[str]
    os_family: str | None
    package_manager: str
    package_id: str
    install_command_windows: str | None
    install_command_linux: str | None
    default_config: dict[str, Any]
    config_schema: dict[str, Any] | None
    icon: str | None
    website: str | None
    documentation_url: str | None
    dependencies: list[str]
    conflicts: list[str]
    is_active: bool
    is_featured: bool
    install_time_minutes: int
    install_count: int
    created_at: datetime
    updated_at: datetime | None

    class Config:
        from_attributes = True


class SoftwareList(BaseModel):
    """Liste paginée de logiciels."""
    
    items: list[SoftwareResponse]
    total: int
    page: int
    page_size: int
    categories: dict[str, int]  # Nombre de logiciels par catégorie


class CategoryInfo(BaseModel):
    """Informations sur une catégorie."""
    
    id: str
    name: str
    description: str
    icon: str
    count: int


# =============================================================================
# Import des données du catalogue
# =============================================================================
from src.domain.software_catalog import (
    CATEGORY_INFO,
    SOFTWARE_PROFILES,
    DEFAULT_SOFTWARE_CATALOG,
    get_software_by_name,
    get_profile_packages,
)


# =============================================================================
# Schemas supplémentaires pour les profils
# =============================================================================


class ProfileInfo(BaseModel):
    """Informations sur un profil de logiciels."""
    
    name: str
    display_name: str
    description: str
    icon: str
    packages: list[str]
    package_count: int


class ProfileList(BaseModel):
    """Liste des profils disponibles."""
    
    profiles: list[ProfileInfo]


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=SoftwareList,
    summary="Lister les logiciels",
    description="Retourne la liste paginée des logiciels disponibles dans le catalogue.",
)
async def list_software(
    db: DbSession,
    pagination: Pagination,
    category: Annotated[str | None, Query(description="Filtrer par catégorie")] = None,
    os_family: Annotated[str | None, Query(description="Filtrer par OS (windows, linux)")] = None,
    search: Annotated[str | None, Query(description="Recherche par nom ou description")] = None,
    featured_only: Annotated[bool, Query(description="Uniquement les logiciels en vedette")] = False,
    active_only: Annotated[bool, Query(description="Uniquement les logiciels actifs")] = True,
) -> SoftwareList:
    """Liste les logiciels du catalogue avec filtres."""
    logger.info(
        "listing_software",
        page=pagination.page,
        category=category,
        search=search,
    )
    
    # Construire la requête
    query = select(SoftwarePackage)
    
    if active_only:
        query = query.where(SoftwarePackage.is_active == True)
    
    if featured_only:
        query = query.where(SoftwarePackage.is_featured == True)
    
    if category and category != "all":
        try:
            cat_enum = SoftwareCategory(category)
            query = query.where(SoftwarePackage.category == cat_enum)
        except ValueError:
            pass
    
    if os_family:
        try:
            os_enum = OSFamily(os_family)
            query = query.where(
                (SoftwarePackage.os_family == os_enum) | 
                (SoftwarePackage.os_family == None)
            )
        except ValueError:
            pass
    
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            (SoftwarePackage.name.ilike(search_pattern)) |
            (SoftwarePackage.display_name.ilike(search_pattern)) |
            (SoftwarePackage.description.ilike(search_pattern)) |
            (SoftwarePackage.short_description.ilike(search_pattern))
        )
    
    # Ordonner par featured puis par nom
    query = query.order_by(
        SoftwarePackage.is_featured.desc(),
        SoftwarePackage.install_count.desc(),
        SoftwarePackage.display_name,
    )
    
    # Exécuter la requête
    result = await db.execute(query)
    all_software = list(result.scalars().all())
    
    # Pagination
    total = len(all_software)
    start = (pagination.page - 1) * pagination.page_size
    end = start + pagination.page_size
    items = all_software[start:end]
    
    # Compter par catégorie
    cat_query = select(
        SoftwarePackage.category,
        func.count(SoftwarePackage.id).label('count')
    ).where(SoftwarePackage.is_active == True).group_by(SoftwarePackage.category)
    
    cat_result = await db.execute(cat_query)
    categories = {str(row.category.value): row.count for row in cat_result}
    
    return SoftwareList(
        items=[SoftwareResponse(
            id=s.id,
            name=s.name,
            display_name=s.display_name,
            version=s.version,
            description=s.description,
            short_description=s.short_description,
            category=s.category.value,
            tags=s.tags or [],
            os_family=s.os_family.value if s.os_family else None,
            package_manager=s.package_manager,
            package_id=s.package_id,
            install_command_windows=s.install_command_windows,
            install_command_linux=s.install_command_linux,
            default_config=s.default_config or {},
            config_schema=s.config_schema,
            icon=s.icon,
            website=s.website,
            documentation_url=s.documentation_url,
            dependencies=s.dependencies or [],
            conflicts=s.conflicts or [],
            is_active=s.is_active,
            is_featured=s.is_featured,
            install_time_minutes=s.install_time_minutes,
            install_count=s.install_count,
            created_at=s.created_at,
            updated_at=s.updated_at,
        ) for s in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        categories=categories,
    )


@router.get(
    "/categories",
    response_model=list[CategoryInfo],
    summary="Lister les catégories",
    description="Retourne la liste des catégories avec le nombre de logiciels.",
)
async def list_categories(db: DbSession) -> list[CategoryInfo]:
    """Liste toutes les catégories de logiciels."""
    # Compter les logiciels par catégorie
    query = select(
        SoftwarePackage.category,
        func.count(SoftwarePackage.id).label('count')
    ).where(SoftwarePackage.is_active == True).group_by(SoftwarePackage.category)
    
    result = await db.execute(query)
    counts = {str(row.category.value): row.count for row in result}
    
    categories = []
    for cat_id, info in CATEGORY_INFO.items():
        categories.append(CategoryInfo(
            id=cat_id,
            name=info["name"],
            description=info["description"],
            icon=info["icon"],
            count=counts.get(cat_id, 0),
        ))
    
    # Trier par nombre de logiciels décroissant
    categories.sort(key=lambda x: x.count, reverse=True)
    
    return categories


@router.get(
    "/profiles",
    response_model=ProfileList,
    summary="Lister les profils",
    description="Retourne la liste des profils pré-configurés de logiciels.",
)
async def list_profiles() -> ProfileList:
    """Liste tous les profils de logiciels disponibles."""
    profiles = []
    for profile_id, profile_data in SOFTWARE_PROFILES.items():
        profiles.append(ProfileInfo(
            name=profile_data["name"],
            display_name=profile_data["display_name"],
            description=profile_data["description"],
            icon=profile_data.get("icon", "Package"),
            packages=profile_data["packages"],
            package_count=len(profile_data["packages"]),
        ))
    
    return ProfileList(profiles=profiles)


@router.get(
    "/profiles/{profile_name}",
    response_model=ProfileInfo,
    summary="Obtenir un profil",
    description="Retourne les détails d'un profil avec ses packages.",
)
async def get_profile(profile_name: str) -> ProfileInfo:
    """Récupère un profil par son nom."""
    profile_data = SOFTWARE_PROFILES.get(profile_name)
    
    if not profile_data:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found")
    
    return ProfileInfo(
        name=profile_data["name"],
        display_name=profile_data["display_name"],
        description=profile_data["description"],
        icon=profile_data.get("icon", "Package"),
        packages=profile_data["packages"],
        package_count=len(profile_data["packages"]),
    )


@router.get(
    "/by-name/{name}",
    response_model=SoftwareResponse,
    summary="Obtenir par nom",
    description="Retourne un logiciel par son nom unique.",
)
async def get_software_by_name_endpoint(
    db: DbSession,
    name: str,
) -> SoftwareResponse:
    """Récupère un logiciel par son nom."""
    result = await db.execute(
        select(SoftwarePackage).where(SoftwarePackage.name == name)
    )
    software = result.scalar_one_or_none()
    
    if not software:
        raise HTTPException(status_code=404, detail=f"Software '{name}' not found")
    
    return SoftwareResponse(
        id=software.id,
        name=software.name,
        display_name=software.display_name,
        version=software.version,
        description=software.description,
        short_description=software.short_description,
        category=software.category.value,
        tags=software.tags or [],
        os_family=software.os_family.value if software.os_family else None,
        package_manager=software.package_manager,
        package_id=software.package_id,
        install_command_windows=software.install_command_windows,
        install_command_linux=software.install_command_linux,
        default_config=software.default_config or {},
        config_schema=software.config_schema,
        icon=software.icon,
        website=software.website,
        documentation_url=software.documentation_url,
        dependencies=software.dependencies or [],
        conflicts=software.conflicts or [],
        is_active=software.is_active,
        is_featured=software.is_featured,
        install_time_minutes=software.install_time_minutes,
        install_count=software.install_count,
        created_at=software.created_at,
        updated_at=software.updated_at,
    )


@router.get(
    "/featured",
    response_model=list[SoftwareResponse],
    summary="Logiciels en vedette",
    description="Retourne les logiciels mis en vedette.",
)
async def list_featured(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[SoftwareResponse]:
    """Liste les logiciels en vedette."""
    query = (
        select(SoftwarePackage)
        .where(SoftwarePackage.is_active == True)
        .where(SoftwarePackage.is_featured == True)
        .order_by(SoftwarePackage.install_count.desc())
        .limit(limit)
    )
    
    result = await db.execute(query)
    software_list = list(result.scalars().all())
    
    return [SoftwareResponse(
        id=s.id,
        name=s.name,
        display_name=s.display_name,
        version=s.version,
        description=s.description,
        short_description=s.short_description,
        category=s.category.value,
        tags=s.tags or [],
        os_family=s.os_family.value if s.os_family else None,
        package_manager=s.package_manager,
        package_id=s.package_id,
        install_command_windows=s.install_command_windows,
        install_command_linux=s.install_command_linux,
        default_config=s.default_config or {},
        config_schema=s.config_schema,
        icon=s.icon,
        website=s.website,
        documentation_url=s.documentation_url,
        dependencies=s.dependencies or [],
        conflicts=s.conflicts or [],
        is_active=s.is_active,
        is_featured=s.is_featured,
        install_time_minutes=s.install_time_minutes,
        install_count=s.install_count,
        created_at=s.created_at,
        updated_at=s.updated_at,
    ) for s in software_list]


@router.get(
    "/{software_id}",
    response_model=SoftwareResponse,
    summary="Obtenir un logiciel",
    description="Retourne les détails d'un logiciel.",
)
async def get_software(
    db: DbSession,
    software_id: UUID,
) -> SoftwareResponse:
    """Récupère un logiciel par son ID."""
    result = await db.execute(
        select(SoftwarePackage).where(SoftwarePackage.id == software_id)
    )
    software = result.scalar_one_or_none()
    
    if not software:
        raise HTTPException(status_code=404, detail="Software not found")
    
    return SoftwareResponse(
        id=software.id,
        name=software.name,
        display_name=software.display_name,
        version=software.version,
        description=software.description,
        short_description=software.short_description,
        category=software.category.value,
        tags=software.tags or [],
        os_family=software.os_family.value if software.os_family else None,
        package_manager=software.package_manager,
        package_id=software.package_id,
        install_command_windows=software.install_command_windows,
        install_command_linux=software.install_command_linux,
        default_config=software.default_config or {},
        config_schema=software.config_schema,
        icon=software.icon,
        website=software.website,
        documentation_url=software.documentation_url,
        dependencies=software.dependencies or [],
        conflicts=software.conflicts or [],
        is_active=software.is_active,
        is_featured=software.is_featured,
        install_time_minutes=software.install_time_minutes,
        install_count=software.install_count,
        created_at=software.created_at,
        updated_at=software.updated_at,
    )


@router.post(
    "",
    response_model=SoftwareResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un logiciel",
    description="Ajoute un nouveau logiciel au catalogue.",
)
async def create_software(
    db: DbSession,
    data: SoftwareCreate,
) -> SoftwareResponse:
    """Crée un nouveau logiciel dans le catalogue."""
    logger.info("creating_software", name=data.name)
    
    # Vérifier l'unicité du nom
    existing = await db.execute(
        select(SoftwarePackage).where(SoftwarePackage.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Software with name '{data.name}' already exists"
        )
    
    # Mapper les enums
    category = SoftwareCategory.OTHER
    if data.category:
        try:
            category = SoftwareCategory(data.category)
        except ValueError:
            pass
    
    os_family = None
    if data.os_family:
        try:
            os_family = OSFamily(data.os_family)
        except ValueError:
            pass
    
    software = SoftwarePackage(
        name=data.name,
        display_name=data.display_name,
        version=data.version,
        description=data.description,
        short_description=data.short_description,
        category=category,
        tags=data.tags,
        os_family=os_family,
        package_manager=data.package_manager,
        package_id=data.package_id,
        install_command_windows=data.install_command_windows,
        install_command_linux=data.install_command_linux,
        default_config=data.default_config,
        config_schema=data.config_schema,
        icon=data.icon,
        website=data.website,
        documentation_url=data.documentation_url,
        dependencies=data.dependencies,
        conflicts=data.conflicts,
        is_featured=data.is_featured,
        install_time_minutes=data.install_time_minutes,
    )
    
    db.add(software)
    await db.commit()
    await db.refresh(software)
    
    return SoftwareResponse(
        id=software.id,
        name=software.name,
        display_name=software.display_name,
        version=software.version,
        description=software.description,
        short_description=software.short_description,
        category=software.category.value,
        tags=software.tags or [],
        os_family=software.os_family.value if software.os_family else None,
        package_manager=software.package_manager,
        package_id=software.package_id,
        install_command_windows=software.install_command_windows,
        install_command_linux=software.install_command_linux,
        default_config=software.default_config or {},
        config_schema=software.config_schema,
        icon=software.icon,
        website=software.website,
        documentation_url=software.documentation_url,
        dependencies=software.dependencies or [],
        conflicts=software.conflicts or [],
        is_active=software.is_active,
        is_featured=software.is_featured,
        install_time_minutes=software.install_time_minutes,
        install_count=software.install_count,
        created_at=software.created_at,
        updated_at=software.updated_at,
    )


@router.patch(
    "/{software_id}",
    response_model=SoftwareResponse,
    summary="Mettre à jour un logiciel",
    description="Met à jour un logiciel du catalogue.",
)
async def update_software(
    db: DbSession,
    software_id: UUID,
    data: SoftwareUpdate,
) -> SoftwareResponse:
    """Met à jour un logiciel existant."""
    result = await db.execute(
        select(SoftwarePackage).where(SoftwarePackage.id == software_id)
    )
    software = result.scalar_one_or_none()
    
    if not software:
        raise HTTPException(status_code=404, detail="Software not found")
    
    # Appliquer les mises à jour
    update_data = data.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        if field == "category" and value:
            try:
                value = SoftwareCategory(value)
            except ValueError:
                continue
        setattr(software, field, value)
    
    await db.commit()
    await db.refresh(software)
    
    return SoftwareResponse(
        id=software.id,
        name=software.name,
        display_name=software.display_name,
        version=software.version,
        description=software.description,
        short_description=software.short_description,
        category=software.category.value,
        tags=software.tags or [],
        os_family=software.os_family.value if software.os_family else None,
        package_manager=software.package_manager,
        package_id=software.package_id,
        install_command_windows=software.install_command_windows,
        install_command_linux=software.install_command_linux,
        default_config=software.default_config or {},
        config_schema=software.config_schema,
        icon=software.icon,
        website=software.website,
        documentation_url=software.documentation_url,
        dependencies=software.dependencies or [],
        conflicts=software.conflicts or [],
        is_active=software.is_active,
        is_featured=software.is_featured,
        install_time_minutes=software.install_time_minutes,
        install_count=software.install_count,
        created_at=software.created_at,
        updated_at=software.updated_at,
    )


@router.delete(
    "/{software_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un logiciel",
    description="Supprime un logiciel du catalogue.",
)
async def delete_software(
    db: DbSession,
    software_id: UUID,
) -> None:
    """Supprime un logiciel du catalogue."""
    result = await db.execute(
        select(SoftwarePackage).where(SoftwarePackage.id == software_id)
    )
    software = result.scalar_one_or_none()
    
    if not software:
        raise HTTPException(status_code=404, detail="Software not found")
    
    await db.delete(software)
    await db.commit()


@router.post(
    "/seed",
    response_model=dict[str, int],
    summary="Initialiser le catalogue",
    description="Ajoute les logiciels par défaut au catalogue.",
)
async def seed_catalog(db: DbSession) -> dict[str, int]:
    """Initialise le catalogue avec les logiciels par défaut."""
    from src.domain.software_catalog import DEFAULT_SOFTWARE_CATALOG
    
    created = 0
    skipped = 0
    
    for software_data in DEFAULT_SOFTWARE_CATALOG:
        # Vérifier si existe déjà
        existing = await db.execute(
            select(SoftwarePackage).where(SoftwarePackage.name == software_data["name"])
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue
        
        # Mapper les enums
        category = SoftwareCategory.OTHER
        if software_data.get("category"):
            try:
                category = SoftwareCategory(software_data["category"])
            except ValueError:
                pass
        
        os_family = None
        if software_data.get("os_family"):
            try:
                os_family = OSFamily(software_data["os_family"])
            except ValueError:
                pass
        
        software = SoftwarePackage(
            name=software_data["name"],
            display_name=software_data["display_name"],
            version=software_data.get("version", "latest"),
            description=software_data.get("description"),
            short_description=software_data.get("short_description"),
            category=category,
            tags=software_data.get("tags", []),
            os_family=os_family,
            package_manager=software_data.get("package_manager", "chocolatey"),
            package_id=software_data.get("package_id", software_data["name"]),
            default_config=software_data.get("default_config", {}),
            config_schema=software_data.get("config_schema"),
            icon=software_data.get("icon"),
            website=software_data.get("website"),
            documentation_url=software_data.get("documentation_url"),
            dependencies=software_data.get("dependencies", []),
            conflicts=software_data.get("conflicts", []),
            is_featured=software_data.get("is_featured", False),
            install_time_minutes=software_data.get("install_time_minutes", 5),
        )
        
        db.add(software)
        created += 1
    
    await db.commit()
    
    logger.info("software_catalog_seeded", created=created, skipped=skipped)
    
    return {"created": created, "skipped": skipped}
