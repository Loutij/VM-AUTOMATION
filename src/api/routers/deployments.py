# =============================================================================
# VM Automation - Deployments Router
# =============================================================================
"""
Endpoints pour la gestion des déploiements de VMs.
"""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Query, status
from pydantic import BaseModel, Field

from src.api.dependencies import DbSession, Pagination
from src.common.logging import get_logger
from src.domain.deployment_service import DeploymentService
from src.domain.models import DeploymentStatus

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================


class IPConfig(BaseModel):
    """Configuration IP."""

    static_ip: bool = Field(default=False, description="Utiliser une IP statique")
    ip_address: str | None = Field(None, description="Adresse IP")
    subnet_prefix: int = Field(default=24, ge=1, le=32, description="Préfixe réseau")
    gateway: str | None = Field(None, description="Passerelle")
    dns_server_1: str = Field(default="8.8.8.8", description="DNS primaire")
    dns_server_2: str | None = Field(None, description="DNS secondaire")


class DomainJoinConfig(BaseModel):
    """Configuration de jonction AD."""

    domain: str = Field(..., description="Nom du domaine")
    user: str = Field(..., description="Utilisateur pour joindre le domaine")
    password: str = Field(..., description="Mot de passe")
    ou: str | None = Field(None, description="OU cible")


class ServicesConfig(BaseModel):
    """Configuration des services à activer."""

    enable_rdp: bool = Field(default=True, description="Activer Remote Desktop")
    enable_winrm: bool = Field(default=True, description="Activer WinRM")
    enable_ssh: bool = Field(default=False, description="Installer OpenSSH Server")


class SecurityConfig(BaseModel):
    """Configuration de sécurité."""

    configure_password_policy: bool = Field(default=False, description="Configurer les politiques de mot de passe")
    password_min_length: int = Field(default=8, ge=4, le=20, description="Longueur minimale du mot de passe")
    password_complexity: bool = Field(default=True, description="Exiger la complexité")
    password_max_age: int = Field(default=90, ge=0, le=365, description="Âge maximum (jours, 0=jamais)")


class DeploymentCreate(BaseModel):
    """Schéma pour créer un déploiement."""

    vm_name: str = Field(..., min_length=1, max_length=50, description="Nom de la VM")
    hypervisor_id: UUID = Field(..., description="ID de l'hyperviseur")
    template_id: UUID = Field(..., description="ID du template OS")
    cpu_count: int = Field(default=2, ge=1, le=64, description="CPUs")
    ram_gb: int = Field(default=4, ge=1, le=512, description="RAM en GB")
    disk_gb: int = Field(default=60, ge=20, le=2048, description="Disque en GB")
    vhdx_path: str | None = Field(None, description="Emplacement du disque virtuel (dossier)")
    network_switch: str | None = Field(None, description="Switch réseau")
    hostname: str | None = Field(None, description="Nom d'hôte (défaut: vm_name)")
    admin_password: str | None = Field(None, description="Mot de passe admin")
    ip_config: IPConfig | None = Field(None, description="Configuration IP")
    domain_join: DomainJoinConfig | None = Field(None, description="Jonction AD")
    # Services
    services: ServicesConfig | None = Field(None, description="Services à activer (RDP, WinRM, SSH)")
    # Sécurité
    security: SecurityConfig | None = Field(None, description="Configuration de sécurité")
    # Logiciels
    software_profile: str | None = Field(None, description="Profil logiciel (minimal, tools, development, webserver, database, monitoring)")
    packages: list[str] | None = Field(None, description="Packages Chocolatey supplémentaires")
    # Windows Update
    enable_windows_update: bool = Field(default=False, description="Installer les mises à jour Windows")
    # Post-install
    post_install_commands: list[str] | None = Field(None, description="Commandes post-install personnalisées")
    auto_start: bool = Field(default=True, description="Démarrer automatiquement")


class DeploymentResponse(BaseModel):
    """Schéma de réponse pour un déploiement."""

    id: UUID
    vm_name: str
    hypervisor_id: UUID
    os_template_id: UUID
    vm_id: UUID | None = None
    status: str
    current_step: str | None = None
    error_message: str | None = None
    config: dict[str, Any]
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    class Config:
        from_attributes = True


class DeploymentList(BaseModel):
    """Liste paginée de déploiements."""

    items: list[DeploymentResponse]
    total: int
    page: int
    page_size: int


class DeploymentLogEntry(BaseModel):
    """Entrée de log de déploiement."""

    id: UUID
    step: str
    message: str
    level: str
    details: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=DeploymentList,
    summary="Lister les déploiements",
    description="Retourne la liste des déploiements.",
)
async def list_deployments(
    db: DbSession,
    pagination: Pagination,
    deployment_status: Annotated[str | None, Query(alias="status", description="Filtrer par statut")] = None,
) -> DeploymentList:
    """Liste les déploiements avec filtres optionnels."""
    logger.info(
        "listing_deployments",
        page=pagination.page,
        status=deployment_status,
    )
    
    service = DeploymentService(db)
    
    # Mapper le statut
    status_filter = None
    if deployment_status:
        try:
            status_filter = DeploymentStatus(deployment_status)
        except ValueError:
            pass
    
    deployments = await service.list_deployments(status=status_filter)
    
    # Pagination
    total = len(deployments)
    start = (pagination.page - 1) * pagination.page_size
    end = start + pagination.page_size
    items = deployments[start:end]
    
    return DeploymentList(
        items=[DeploymentResponse(
            id=d.id,
            vm_name=d.vm_name,
            hypervisor_id=d.hypervisor_id,
            os_template_id=d.os_template_id,
            vm_id=d.vm_id,
            status=d.status.value,
            current_step=d.current_step,
            error_message=d.error_message,
            config=d.config,
            created_at=d.created_at,
            started_at=d.started_at,
            completed_at=d.completed_at,
        ) for d in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post(
    "",
    response_model=DeploymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un déploiement",
    description="Crée un nouveau déploiement de VM.",
)
async def create_deployment(
    db: DbSession,
    deployment: DeploymentCreate,
    background_tasks: BackgroundTasks,
) -> DeploymentResponse:
    """Crée et lance un déploiement."""
    logger.info(
        "creating_deployment",
        vm_name=deployment.vm_name,
        hypervisor_id=str(deployment.hypervisor_id),
        template_id=str(deployment.template_id),
    )
    
    service = DeploymentService(db)
    
    # Préparer la config IP
    ip_config = None
    if deployment.ip_config:
        ip_config = deployment.ip_config.model_dump()
    
    # Préparer la config domain join
    domain_join = None
    if deployment.domain_join:
        domain_join = deployment.domain_join.model_dump()
    
    # Préparer la config services
    services = None
    if deployment.services:
        services = deployment.services.model_dump()
    
    # Préparer la config sécurité
    security = None
    if deployment.security:
        security = deployment.security.model_dump()
    
    # Créer le déploiement
    created = await service.create_deployment(
        vm_name=deployment.vm_name,
        hypervisor_id=deployment.hypervisor_id,
        template_id=deployment.template_id,
        cpu_count=deployment.cpu_count,
        ram_gb=deployment.ram_gb,
        disk_gb=deployment.disk_gb,
        vhdx_path=deployment.vhdx_path,
        network_switch=deployment.network_switch,
        hostname=deployment.hostname,
        admin_password=deployment.admin_password,
        ip_config=ip_config,
        domain_join=domain_join,
        services=services,
        security=security,
        software_profile=deployment.software_profile,
        packages=deployment.packages,
        enable_windows_update=deployment.enable_windows_update,
        post_install_commands=deployment.post_install_commands,
    )
    
    # Lancer le déploiement DISM automatiquement
    if deployment.auto_start:
        import asyncio
        from src.common.database import db_session
        from src.domain.models import DeploymentStatus
        from datetime import datetime, timezone
        
        # Marquer comme IN_PROGRESS immédiatement pour éviter double traitement par Celery
        created.status = DeploymentStatus.IN_PROGRESS
        created.started_at = datetime.now(timezone.utc)
        
        await db.commit()
        
        async def run_deployment_background(deployment_id):
            """Exécute le déploiement DISM en arrière-plan."""
            try:
                async with db_session() as session:
                    bg_service = DeploymentService(session)
                    await bg_service.start_deployment(deployment_id)
                    await session.commit()
                    logger.info("background_deployment_completed", deployment_id=str(deployment_id))
            except Exception as e:
                logger.error("background_deployment_failed", deployment_id=str(deployment_id), error=str(e))
        
        # Lancer en arrière-plan
        asyncio.create_task(run_deployment_background(created.id))
    else:
        await db.commit()
    
    return DeploymentResponse(
        id=created.id,
        vm_name=created.vm_name,
        hypervisor_id=created.hypervisor_id,
        os_template_id=created.os_template_id,
        vm_id=created.vm_id,
        status=created.status.value,
        current_step=created.current_step,
        error_message=created.error_message,
        config=created.config,
        created_at=created.created_at,
        started_at=created.started_at,
        completed_at=created.completed_at,
    )


@router.get(
    "/{deployment_id}",
    response_model=DeploymentResponse,
    summary="Obtenir un déploiement",
    description="Retourne les détails d'un déploiement.",
)
async def get_deployment(
    db: DbSession,
    deployment_id: UUID,
) -> DeploymentResponse:
    """Récupère un déploiement par son ID."""
    logger.info("getting_deployment", deployment_id=str(deployment_id))
    
    service = DeploymentService(db)
    deployment = await service.get_deployment(deployment_id)
    
    return DeploymentResponse(
        id=deployment.id,
        vm_name=deployment.vm_name,
        hypervisor_id=deployment.hypervisor_id,
        os_template_id=deployment.os_template_id,
        vm_id=deployment.vm_id,
        status=deployment.status.value,
        current_step=deployment.current_step,
        error_message=deployment.error_message,
        config=deployment.config,
        created_at=deployment.created_at,
        started_at=deployment.started_at,
        completed_at=deployment.completed_at,
    )


@router.post(
    "/{deployment_id}/start",
    response_model=DeploymentResponse,
    summary="Démarrer un déploiement",
    description="Démarre l'exécution d'un déploiement en attente.",
)
async def start_deployment(
    db: DbSession,
    deployment_id: UUID,
) -> DeploymentResponse:
    """Démarre un déploiement."""
    logger.info("starting_deployment", deployment_id=str(deployment_id))
    
    service = DeploymentService(db)
    deployment = await service.start_deployment(deployment_id)
    await db.commit()
    
    return DeploymentResponse(
        id=deployment.id,
        vm_name=deployment.vm_name,
        hypervisor_id=deployment.hypervisor_id,
        os_template_id=deployment.os_template_id,
        vm_id=deployment.vm_id,
        status=deployment.status.value,
        current_step=deployment.current_step,
        error_message=deployment.error_message,
        config=deployment.config,
        created_at=deployment.created_at,
        started_at=deployment.started_at,
        completed_at=deployment.completed_at,
    )


@router.post(
    "/{deployment_id}/cancel",
    response_model=DeploymentResponse,
    summary="Annuler un déploiement",
    description="Annule un déploiement en cours.",
)
async def cancel_deployment(
    db: DbSession,
    deployment_id: UUID,
) -> DeploymentResponse:
    """Annule un déploiement."""
    logger.info("cancelling_deployment", deployment_id=str(deployment_id))
    
    service = DeploymentService(db)
    deployment = await service.cancel_deployment(deployment_id)
    await db.commit()
    
    return DeploymentResponse(
        id=deployment.id,
        vm_name=deployment.vm_name,
        hypervisor_id=deployment.hypervisor_id,
        os_template_id=deployment.os_template_id,
        vm_id=deployment.vm_id,
        status=deployment.status.value,
        current_step=deployment.current_step,
        error_message=deployment.error_message,
        config=deployment.config,
        created_at=deployment.created_at,
        started_at=deployment.started_at,
        completed_at=deployment.completed_at,
    )


@router.get(
    "/{deployment_id}/logs",
    response_model=list[DeploymentLogEntry],
    summary="Logs du déploiement",
    description="Retourne les logs d'un déploiement.",
)
async def get_deployment_logs(
    db: DbSession,
    deployment_id: UUID,
) -> list[DeploymentLogEntry]:
    """Récupère les logs d'un déploiement."""
    logger.info("getting_deployment_logs", deployment_id=str(deployment_id))
    
    from sqlalchemy import select
    from src.domain.models import DeploymentLog
    
    result = await db.execute(
        select(DeploymentLog)
        .where(DeploymentLog.deployment_id == deployment_id)
        .order_by(DeploymentLog.created_at)
    )
    logs = result.scalars().all()
    
    return [DeploymentLogEntry(
        id=log.id,
        step=log.step,
        message=log.message,
        level=log.level,
        details=log.details,
        created_at=log.created_at,
    ) for log in logs]


@router.delete(
    "/{deployment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un déploiement",
    description="Supprime un déploiement terminé, échoué ou annulé.",
)
async def delete_deployment(
    db: DbSession,
    deployment_id: UUID,
) -> None:
    """Supprime un déploiement et ses logs associés."""
    logger.info("deleting_deployment", deployment_id=str(deployment_id))
    
    from sqlalchemy import select, delete as sql_delete
    from src.domain.models import Deployment, DeploymentLog
    
    # Vérifier que le déploiement existe
    result = await db.execute(
        select(Deployment).where(Deployment.id == deployment_id)
    )
    deployment = result.scalar_one_or_none()
    
    if not deployment:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    # Vérifier que le déploiement n'est pas en cours
    if deployment.status not in (
        DeploymentStatus.COMPLETED,
        DeploymentStatus.FAILED,
        DeploymentStatus.CANCELLED,
    ):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail="Cannot delete an active deployment. Cancel it first."
        )
    
    # Supprimer les logs associés
    await db.execute(
        sql_delete(DeploymentLog).where(DeploymentLog.deployment_id == deployment_id)
    )
    
    # Supprimer le déploiement
    await db.delete(deployment)
    await db.commit()
    
    logger.info("deployment_deleted", deployment_id=str(deployment_id))
