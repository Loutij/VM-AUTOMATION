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

    @classmethod
    def model_validate(cls, obj, **kwargs):
        """Convertit le modèle ORM en réponse avec mapping type -> hypervisor_type."""
        return cls(
            id=obj.id,
            name=obj.name,
            hypervisor_type=obj.type.value if hasattr(obj.type, 'value') else str(obj.type),
            host=obj.host,
            port=obj.port,
            use_ssl=obj.use_ssl,
            username=obj.username,
            is_active=obj.is_active,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


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


class SwitchCreate(BaseModel):
    """Schéma pour créer un switch virtuel."""
    
    name: str = Field(..., min_length=1, max_length=100, description="Nom du switch")
    switch_type: str = Field(
        ..., 
        pattern="^(Internal|External|Private)$",
        description="Type de switch: Internal, External, ou Private"
    )
    net_adapter_name: str | None = Field(
        None,
        description="Nom de l'adaptateur réseau (requis pour External)"
    )
    allow_management_os: bool = Field(
        True,
        description="Permettre à l'OS hôte d'utiliser l'adaptateur (External uniquement)"
    )
    notes: str | None = Field(None, max_length=500, description="Notes/description")


class SwitchResponse(BaseModel):
    """Schéma de réponse pour un switch virtuel."""
    
    name: str
    switch_type: str
    interface_description: str | None = None
    notes: str | None = None


@router.post(
    "/{hypervisor_id}/switches",
    response_model=SwitchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un switch virtuel",
    description="Crée un nouveau switch virtuel sur l'hyperviseur.",
)
async def create_hypervisor_switch(
    db: DbSession,
    hypervisor_id: UUID,
    switch_data: SwitchCreate,
) -> SwitchResponse:
    """Crée un switch virtuel sur l'hyperviseur."""
    logger.info(
        "creating_hypervisor_switch",
        hypervisor_id=str(hypervisor_id),
        name=switch_data.name,
        switch_type=switch_data.switch_type,
    )
    
    service = VMService(db)
    client = await service._get_hypervisor_client(hypervisor_id)
    
    switch = await client.create_switch(
        name=switch_data.name,
        switch_type=switch_data.switch_type,
        net_adapter_name=switch_data.net_adapter_name,
        allow_management_os=switch_data.allow_management_os,
        notes=switch_data.notes,
    )
    
    return SwitchResponse(
        name=switch.name,
        switch_type=switch.switch_type,
        interface_description=switch.interface_description,
        notes=switch.notes,
    )


@router.delete(
    "/{hypervisor_id}/switches/{switch_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un switch virtuel",
    description="Supprime un switch virtuel de l'hyperviseur.",
)
async def delete_hypervisor_switch(
    db: DbSession,
    hypervisor_id: UUID,
    switch_name: str,
) -> None:
    """Supprime un switch virtuel."""
    logger.info(
        "deleting_hypervisor_switch",
        hypervisor_id=str(hypervisor_id),
        switch_name=switch_name,
    )
    
    service = VMService(db)
    client = await service._get_hypervisor_client(hypervisor_id)
    
    await client.delete_switch(switch_name)


@router.get(
    "/{hypervisor_id}/physical-adapters",
    summary="Lister les adaptateurs réseau physiques",
    description="Liste les adaptateurs réseau physiques disponibles pour créer des switches externes.",
)
async def list_physical_adapters(
    db: DbSession,
    hypervisor_id: UUID,
) -> list[dict]:
    """Liste les adaptateurs réseau physiques de l'hyperviseur."""
    logger.info("listing_physical_adapters", hypervisor_id=str(hypervisor_id))
    
    service = VMService(db)
    client = await service._get_hypervisor_client(hypervisor_id)
    
    adapters = await client.list_physical_adapters()
    
    return adapters


class ISOInfo(BaseModel):
    """Informations sur un fichier ISO."""
    
    name: str = Field(..., description="Nom du fichier ISO")
    full_path: str = Field(..., description="Chemin complet sur l'hyperviseur")
    size_bytes: int = Field(..., description="Taille en octets")
    size_gb: float = Field(..., description="Taille en Go")
    last_modified: str = Field(..., description="Date de dernière modification")
    directory: str = Field(..., description="Dossier parent")


@router.get(
    "/{hypervisor_id}/isos",
    response_model=list[ISOInfo],
    summary="Lister les ISOs disponibles",
    description="Liste les fichiers ISO disponibles sur l'hyperviseur pour l'installation des VMs.",
)
async def list_hypervisor_isos(
    db: DbSession,
    hypervisor_id: UUID,
    path: Annotated[str | None, Query(description="Chemin personnalisé (optionnel)")] = None,
) -> list[ISOInfo]:
    """Liste les fichiers ISO disponibles sur l'hyperviseur."""
    logger.info("listing_hypervisor_isos", hypervisor_id=str(hypervisor_id), custom_path=path)
    
    service = VMService(db)
    client = await service._get_hypervisor_client(hypervisor_id)
    
    isos = await client.list_isos(path=path)
    
    return [ISOInfo(**iso) for iso in isos]


# =============================================================================
# Storage Locations
# =============================================================================


class StorageLocation(BaseModel):
    """Informations sur un emplacement de stockage."""
    
    drive_letter: str = Field(..., description="Lettre du lecteur (ex: C, D, E)")
    path: str = Field(..., description="Chemin suggéré pour les VHDx")
    total_gb: float = Field(..., description="Espace total en Go")
    free_gb: float = Field(..., description="Espace libre en Go")
    used_gb: float = Field(..., description="Espace utilisé en Go")
    percent_free: float = Field(..., description="Pourcentage d'espace libre")
    is_default: bool = Field(default=False, description="Emplacement par défaut")
    is_recommended: bool = Field(default=False, description="Recommandé (plus d'espace)")


@router.get(
    "/{hypervisor_id}/storage-locations",
    response_model=list[StorageLocation],
    summary="Lister les emplacements de stockage",
    description="Liste les disques disponibles pour stocker les VHDx des VMs.",
)
async def list_storage_locations(
    db: DbSession,
    hypervisor_id: UUID,
    min_free_gb: Annotated[int, Query(description="Espace libre minimum en Go")] = 50,
) -> list[StorageLocation]:
    """Liste les emplacements de stockage disponibles sur l'hyperviseur."""
    logger.info("listing_storage_locations", hypervisor_id=str(hypervisor_id))
    
    service = VMService(db)
    client = await service._get_hypervisor_client(hypervisor_id)
    
    # Récupérer les disques avec espace libre
    script = f'''
        $minFree = {min_free_gb}
        Get-PSDrive -PSProvider FileSystem | 
        Where-Object {{ $_.Free -ne $null -and ($_.Free / 1GB) -ge $minFree }} |
        ForEach-Object {{
            $total = $_.Used + $_.Free
            [PSCustomObject]@{{
                DriveLetter = $_.Name
                TotalGB = [math]::Round($total / 1GB, 2)
                FreeGB = [math]::Round($_.Free / 1GB, 2)
                UsedGB = [math]::Round($_.Used / 1GB, 2)
                PercentFree = if ($total -gt 0) {{ [math]::Round(($_.Free / $total) * 100, 1) }} else {{ 0 }}
            }}
        }} | Sort-Object FreeGB -Descending | ConvertTo-Json -Compress
    '''
    
    result = await client._execute(script)
    
    if not result.success or not result.output:
        return []
    
    import json
    try:
        data = json.loads(result.output)
        # Si un seul résultat, le mettre dans une liste
        if isinstance(data, dict):
            data = [data]
    except json.JSONDecodeError:
        return []
    
    locations = []
    max_free = max(d.get("FreeGB", 0) for d in data) if data else 0
    
    for disk in data:
        drive = disk.get("DriveLetter", "")
        free_gb = disk.get("FreeGB", 0)
        
        locations.append(StorageLocation(
            drive_letter=drive,
            path=f"{drive}:\\HyperV\\VirtualHardDisks",
            total_gb=disk.get("TotalGB", 0),
            free_gb=free_gb,
            used_gb=disk.get("UsedGB", 0),
            percent_free=disk.get("PercentFree", 0),
            is_default=(drive == "C"),
            is_recommended=(free_gb == max_free and free_gb >= min_free_gb),
        ))
    
    return locations


# =============================================================================
# Synchronisation
# =============================================================================


class SyncOptions(BaseModel):
    """Options de synchronisation."""
    
    import_new: bool = Field(
        default=True,
        description="Importer les VMs présentes sur Hyper-V mais pas en base"
    )
    update_existing: bool = Field(
        default=True,
        description="Mettre à jour l'état des VMs existantes"
    )
    mark_missing: bool = Field(
        default=True,
        description="Marquer les VMs en base qui n'existent plus sur Hyper-V"
    )


class SyncResult(BaseModel):
    """Résultat de synchronisation."""
    
    success: bool
    imported: int
    updated: int
    marked_missing: int
    errors: list[str]
    details: dict | None = None


@router.post(
    "/{hypervisor_id}/sync",
    response_model=SyncResult,
    summary="Synchroniser les VMs",
    description="Synchronise les VMs entre l'hyperviseur et la base de données. "
                "Importe les nouvelles VMs, met à jour les existantes, et marque celles supprimées.",
)
async def sync_hypervisor_vms(
    db: DbSession,
    hypervisor_id: UUID,
    options: SyncOptions | None = None,
) -> SyncResult:
    """Synchronise les VMs de l'hyperviseur avec la base de données."""
    logger.info(
        "syncing_hypervisor_vms",
        hypervisor_id=str(hypervisor_id),
        options=options.model_dump() if options else None,
    )
    
    if options is None:
        options = SyncOptions()
    
    service = VMService(db)
    
    try:
        result = await service.sync_all_vms(
            hypervisor_id=hypervisor_id,
            import_new=options.import_new,
            update_existing=options.update_existing,
            mark_missing=options.mark_missing,
        )
        
        await db.commit()
        
        return SyncResult(
            success=len(result["errors"]) == 0,
            imported=result["imported"],
            updated=result["updated"],
            marked_missing=result["marked_missing"],
            errors=result["errors"],
            details=result["details"],
        )
    except Exception as e:
        logger.error("sync_failed", hypervisor_id=str(hypervisor_id), error=str(e))
        return SyncResult(
            success=False,
            imported=0,
            updated=0,
            marked_missing=0,
            errors=[f"Erreur de synchronisation: {str(e)}"],
        )
