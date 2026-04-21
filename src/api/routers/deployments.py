# =============================================================================
# VM Automation - Deployments Router
# =============================================================================
"""
Endpoints pour la gestion des déploiements de VMs.
"""

import asyncio
import traceback
from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, delete as sql_delete, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import CurrentUser, DbSession, Pagination, RequireAdmin
from src.common.constants import DEPLOYMENT_STEP_PROGRESS
from src.common.database import db_session
from src.common.logging import get_logger
from src.domain.deployment_service import DeploymentService
from src.api.websocket import emit_deployment_event, emit_notification, EventType
from src.domain.models import (
    AuditLog,
    Deployment,
    DeploymentLog,
    DeploymentStatus,
    VirtualMachine,
)

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

    vm_name: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$", description="Nom de la VM (alphanumérique, tirets, points, underscores)")
    hypervisor_id: UUID = Field(..., description="ID de l'hyperviseur")
    os_template_id: UUID = Field(..., description="ID du template OS")
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
    package_configs: dict[str, dict[str, Any]] | None = Field(None, description="Configurations des packages (ex: {'zabbix-agent2': {'server': '192.168.1.1'}})")
    # Windows Update
    enable_windows_update: bool = Field(default=False, description="Installer les mises à jour Windows")
    # Post-install
    post_install_commands: list[str] | None = Field(None, description="Commandes post-install personnalisées")
    auto_start: bool = Field(default=True, description="Démarrer automatiquement")
    # Méthode de déploiement (clone de template vSphere)
    deployment_method: str = Field(
        default="iso",
        pattern="^(iso|clone)$",
        description="Méthode de déploiement: 'iso' (par défaut) ou 'clone' d'une template vSphere"
    )
    vsphere_template_name: str | None = Field(
        None,
        description="Nom de la template vSphere à cloner (requis si deployment_method='clone')"
    )


class DeploymentResponse(BaseModel):
    """Schéma de réponse pour un déploiement."""

    id: UUID
    vm_name: str
    hypervisor_id: UUID
    os_template_id: UUID
    vm_id: UUID | None = None
    status: str
    progress: int = Field(default=0, ge=0, le=100, description="Progression en pourcentage")
    current_step: str | None = None
    error_message: str | None = None
    config: dict[str, Any]
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    # Approval workflow
    requested_by_username: str | None = None
    reviewed_by_username: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None

    class Config:
        from_attributes = True


# Schemas pour l'approbation
class ApproveDeploymentRequest(BaseModel):
    """Requête pour approuver un déploiement."""
    note: str | None = Field(None, alias="note", description="Commentaire de l'admin")
    review_note: str | None = Field(None, exclude=True, description="Alias pour 'note' (déprécié)")
    auto_start: bool = Field(default=True, description="Démarrer automatiquement après approbation")

    class Config:
        populate_by_name = True

    def __init__(self, **data):
        # Support both 'note' and 'review_note' for backward compat
        if "review_note" in data and "note" not in data:
            data["note"] = data.pop("review_note")
        super().__init__(**data)


class RejectDeploymentRequest(BaseModel):
    """Requête pour refuser un déploiement."""
    note: str = Field(..., min_length=1, description="Raison du refus")


class AuditLogEntry(BaseModel):
    """Entrée du journal d'audit."""
    id: UUID
    user_id: str
    username: str
    action: str
    resource_type: str
    resource_id: str | None = None
    details: dict[str, Any] | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogList(BaseModel):
    """Liste paginée de logs d'audit."""
    items: list[AuditLogEntry]
    total: int
    page: int
    page_size: int


# Mapping statut -> progression (pour les statuts terminaux)
STATUS_PROGRESS_MAP: dict[str, int] = {
    "pending_approval": 0,
    "pending": 0,
    "completed": 100,
    "completed_with_warnings": 100,
    "failed": 0,
    "cancelled": 0,
    "rejected": 0,
}

# Mapping current_step -> progression (importé depuis constants.py)
STEP_PROGRESS_MAP = DEPLOYMENT_STEP_PROGRESS


def get_progress_from_status(status: str, current_step: str | None = None, db_progress: int | None = None) -> int:
    """Calcule la progression à partir du statut et de l'étape courante.

    Utilise en priorité la progression stockée en base (calculée par le service),
    avec un fallback sur le mapping d'étapes si la valeur en base n'est pas disponible.
    """
    # Si la progression est déjà calculée en base par le service, l'utiliser directement
    if db_progress is not None and db_progress > 0:
        return db_progress

    # Statuts terminaux ont une progression fixe
    if status in STATUS_PROGRESS_MAP:
        return STATUS_PROGRESS_MAP[status]

    # Pour les statuts en cours, utiliser current_step
    if current_step:
        return STEP_PROGRESS_MAP.get(current_step, 10)

    # Fallback pour in_progress sans step
    return 10


def _build_response(d: Deployment) -> DeploymentResponse:
    """Construit un DeploymentResponse à partir d'un modèle Deployment."""
    # Masquer le mot de passe admin dans la config
    safe_config = dict(d.config) if d.config else {}
    if "admin_password" in safe_config:
        safe_config["admin_password"] = "********"
    
    return DeploymentResponse(
        id=d.id,
        vm_name=d.vm_name,
        hypervisor_id=d.hypervisor_id,
        os_template_id=d.os_template_id,
        vm_id=d.vm_id,
        status=d.status.value,
        progress=get_progress_from_status(d.status.value, d.current_step, db_progress=d.progress),
        current_step=d.current_step,
        error_message=d.error_message,
        config=safe_config,
        created_at=d.created_at,
        started_at=d.started_at,
        completed_at=d.completed_at,
        requested_by_username=d.requested_by_username,
        reviewed_by_username=d.reviewed_by_username,
        reviewed_at=d.reviewed_at,
        review_note=d.review_note,
    )


async def _audit(db: AsyncSession, user: dict, action: str, resource_type: str, resource_id: str | None = None, details: dict | None = None):
    """Enregistre une entrée dans le journal d'audit."""
    from uuid import uuid4
    log = AuditLog(
        id=uuid4(),
        user_id=user["user_id"],
        username=user["username"],
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
    )
    db.add(log)


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
    level: Literal["debug", "info", "warning", "error"]
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
    current_user: CurrentUser,
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
        items=[_build_response(d) for d in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/progress-mapping",
    summary="Mapping étape → progression",
    description="Retourne le mapping étape de déploiement → pourcentage de progression pour la synchronisation frontend.",
)
async def get_progress_mapping(current_user: CurrentUser) -> dict[str, int]:
    """Return the step->progress mapping for frontend sync."""
    from src.common.constants import DEPLOYMENT_STEP_PROGRESS
    return DEPLOYMENT_STEP_PROGRESS


# =============================================================================
# Approval Workflow Endpoints (AVANT /{deployment_id} pour le routing)
# =============================================================================


@router.get(
    "/pending-approval",
    response_model=list[DeploymentResponse],
    summary="Déploiements en attente d'approbation",
    description="Liste les déploiements en attente de validation (admin uniquement).",
)
async def list_pending_approvals(
    db: DbSession,
    admin: RequireAdmin,
) -> list[DeploymentResponse]:
    """Liste les déploiements en attente d'approbation."""
    result = await db.execute(
        select(Deployment)
        .where(Deployment.status == DeploymentStatus.PENDING_APPROVAL)
        .order_by(Deployment.created_at.desc())
    )
    deployments = result.scalars().all()
    return [_build_response(d) for d in deployments]


@router.get(
    "/audit-log",
    response_model=AuditLogList,
    summary="Journal d'audit",
    description="Retourne l'historique des actions (admin uniquement).",
)
async def get_audit_log(
    db: DbSession,
    admin: RequireAdmin,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    action: str | None = Query(default=None, description="Filtrer par type d'action"),
    username: str | None = Query(default=None, description="Filtrer par utilisateur"),
) -> AuditLogList:
    """Récupère le journal d'audit."""
    query = select(AuditLog)

    if action:
        query = query.where(AuditLog.action == action)
    if username:
        query = query.where(AuditLog.username == username)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(AuditLog.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    logs = result.scalars().all()

    return AuditLogList(
        items=[AuditLogEntry(
            id=log.id,
            user_id=log.user_id,
            username=log.username,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            details=log.details,
            created_at=log.created_at,
        ) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/{deployment_id}/approve",
    response_model=DeploymentResponse,
    summary="Approuver un déploiement",
    description="Approuve un déploiement en attente de validation (admin uniquement).",
)
async def approve_deployment(
    db: DbSession,
    deployment_id: UUID,
    admin: RequireAdmin,
    body: ApproveDeploymentRequest,
) -> DeploymentResponse:
    """Approuve un déploiement et le démarre optionnellement."""
    logger.info("approving_deployment", deployment_id=str(deployment_id))

    result = await db.execute(
        select(Deployment).where(Deployment.id == deployment_id).with_for_update()
    )
    deployment = result.scalar_one_or_none()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    if deployment.status != DeploymentStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail=f"Deployment is not pending approval (status: {deployment.status.value})",
        )

    deployment.status = DeploymentStatus.PENDING
    deployment.reviewed_by = admin.get("user_id") if isinstance(admin, dict) else admin["user_id"]
    deployment.reviewed_by_username = admin["username"]
    deployment.reviewed_at = datetime.now(timezone.utc)
    deployment.review_note = body.note

    await _audit(db, admin, "deployment_approved", "deployment",
                 resource_id=str(deployment_id),
                 details={"note": body.note, "auto_start": body.auto_start})
    await db.commit()

    # Notifier l'utilisateur
    await emit_notification(
        title="Déploiement approuvé",
        message=f"Votre déploiement « {deployment.vm_name} » a été approuvé par {admin['username']}."
        + (f" Note : {body.note}" if body.note else ""),
        notification_type="success",
        data={"deployment_id": str(deployment_id)},
    )

    # Auto-start if requested
    if body.auto_start:
        deployment.status = DeploymentStatus.IN_PROGRESS
        deployment.started_at = datetime.now(timezone.utc)
        await db.commit()

        async def run_approve_start(dep_id):
            try:
                async with db_session() as session:
                    bg_service = DeploymentService(session)
                    await bg_service.start_deployment(dep_id)
                    await session.commit()
                    logger.info("approved_deployment_started", deployment_id=str(dep_id))
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                logger.error("approved_deployment_start_failed",
                             deployment_id=str(dep_id), error=error_msg)
                try:
                    async with db_session() as error_session:
                        await error_session.execute(
                            sql_update(Deployment)
                            .where(Deployment.id == dep_id)
                            .values(
                                status=DeploymentStatus.FAILED,
                                current_step="failed",
                                progress=0,
                                error_message=error_msg[:500],
                                completed_at=datetime.now(timezone.utc),
                            )
                        )
                        await error_session.commit()
                        try:
                            await emit_deployment_event(
                                str(dep_id),
                                EventType.DEPLOYMENT_FAILED,
                                {"status": "failed", "error": error_msg[:200]},
                            )
                            await emit_notification(
                                title="Déploiement échoué",
                                message=f"Le déploiement a échoué : {error_msg[:150]}",
                                notification_type="error",
                                data={"deployment_id": str(dep_id)},
                            )
                        except Exception:
                            pass
                except Exception as db_error:
                    logger.error("failed_to_mark_deployment_failed", error=str(db_error))

        asyncio.create_task(run_approve_start(deployment.id))

    return _build_response(deployment)


@router.post(
    "/{deployment_id}/reject",
    response_model=DeploymentResponse,
    summary="Refuser un déploiement",
    description="Refuse un déploiement en attente de validation (admin uniquement).",
)
async def reject_deployment(
    db: DbSession,
    deployment_id: UUID,
    admin: RequireAdmin,
    body: RejectDeploymentRequest,
) -> DeploymentResponse:
    """Refuse un déploiement avec une raison obligatoire."""
    logger.info("rejecting_deployment", deployment_id=str(deployment_id))

    result = await db.execute(
        select(Deployment).where(Deployment.id == deployment_id).with_for_update()
    )
    deployment = result.scalar_one_or_none()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    if deployment.status != DeploymentStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail=f"Deployment is not pending approval (status: {deployment.status.value})",
        )

    deployment.status = DeploymentStatus.REJECTED
    deployment.reviewed_by = admin.get("user_id") if isinstance(admin, dict) else admin["user_id"]
    deployment.reviewed_by_username = admin["username"]
    deployment.reviewed_at = datetime.now(timezone.utc)
    deployment.review_note = body.note

    await _audit(db, admin, "deployment_rejected", "deployment",
                 resource_id=str(deployment_id),
                 details={"note": body.note})
    await db.commit()

    # Notifier l'utilisateur
    await emit_notification(
        title="Déploiement refusé",
        message=f"Votre déploiement « {deployment.vm_name} » a été refusé par {admin['username']}. Raison : {body.note}",
        notification_type="warning",
        data={"deployment_id": str(deployment_id)},
    )

    return _build_response(deployment)


# =============================================================================
# Create / CRUD Endpoints
# =============================================================================


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
    current_user: CurrentUser,
) -> DeploymentResponse:
    """Crée et lance un déploiement."""
    logger.info(
        "creating_deployment",
        vm_name=deployment.vm_name,
        hypervisor_id=str(deployment.hypervisor_id),
        template_id=str(deployment.os_template_id),
    )
    
    service = DeploymentService(db)
    
    # Vérifier unicité du nom de VM
    existing_vm = await db.execute(
        select(VirtualMachine).where(VirtualMachine.name == deployment.vm_name)
    )
    if existing_vm.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Une VM avec le nom '{deployment.vm_name}' existe déjà",
        )
    
    # Vérifier aussi les déploiements en cours avec le même nom
    existing_deploy = await db.execute(
        select(Deployment).where(
            Deployment.vm_name == deployment.vm_name,
            Deployment.status.in_([
                DeploymentStatus.PENDING,
                DeploymentStatus.PENDING_APPROVAL,
                DeploymentStatus.IN_PROGRESS,
            ])
        )
    )
    if existing_deploy.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Un déploiement pour '{deployment.vm_name}' est déjà en cours",
        )
    
    # Valider la cohérence deployment_method / vsphere_template_name
    if deployment.deployment_method == "clone" and not deployment.vsphere_template_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="vsphere_template_name est requis quand deployment_method='clone'",
        )

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
        template_id=deployment.os_template_id,
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
        package_configs=deployment.package_configs,
        enable_windows_update=deployment.enable_windows_update,
        post_install_commands=deployment.post_install_commands,
        deployment_method=deployment.deployment_method,
        vsphere_template_name=deployment.vsphere_template_name,
    )

    # Enregistrer qui a créé le déploiement
    created.created_by = current_user["user_id"]
    created.requested_by_username = current_user["username"]

    # Workflow d'approbation : les users non-admin passent en pending_approval
    user_role = current_user.get("role", "user")
    if user_role != "admin":
        created.status = DeploymentStatus.PENDING_APPROVAL
        await _audit(db, current_user, "deployment_requested", "deployment",
                     str(created.id), {"vm_name": deployment.vm_name})
        await db.commit()
        logger.info("deployment_pending_approval",
                     deployment_id=str(created.id), requested_by=current_user["username"])
        return _build_response(created)

    # Admin : audit + démarrage direct
    await _audit(db, current_user, "deployment_created", "deployment",
                 str(created.id), {"vm_name": deployment.vm_name})

    # Lancer le déploiement DISM automatiquement
    if deployment.auto_start:
        
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
                error_msg = f"{type(e).__name__}: {str(e)}"
                logger.error(
                    "background_deployment_failed", 
                    deployment_id=str(deployment_id), 
                    error=error_msg,
                    traceback=traceback.format_exc()
                )
                # Mettre à jour le statut en FAILED dans une nouvelle session
                try:
                    async with db_session() as error_session:
                        await error_session.execute(
                            sql_update(Deployment)
                            .where(Deployment.id == deployment_id)
                            .values(
                                status=DeploymentStatus.FAILED,
                                current_step="failed",
                                progress=0,
                                error_message=error_msg[:500],
                                completed_at=datetime.now(timezone.utc),
                            )
                        )
                        await error_session.commit()
                        logger.info("deployment_marked_failed", deployment_id=str(deployment_id))
                        try:
                            await emit_deployment_event(
                                str(deployment_id),
                                EventType.DEPLOYMENT_FAILED,
                                {"status": "failed", "error": error_msg[:200]},
                            )
                            await emit_notification(
                                title="Déploiement échoué",
                                message=f"Le déploiement a échoué : {error_msg[:150]}",
                                notification_type="error",
                                data={"deployment_id": str(deployment_id)},
                            )
                        except Exception:
                            pass
                except Exception as db_error:
                    logger.error("failed_to_mark_deployment_failed", error=str(db_error))

        # Lancer en arrière-plan
        asyncio.create_task(run_deployment_background(created.id))
    else:
        await db.commit()
    
    return _build_response(created)


@router.get(
    "/{deployment_id}",
    response_model=DeploymentResponse,
    summary="Obtenir un déploiement",
    description="Retourne les détails d'un déploiement.",
)
async def get_deployment(
    db: DbSession,
    deployment_id: UUID,
    current_user: CurrentUser,
) -> DeploymentResponse:
    """Récupère un déploiement par son ID."""
    logger.info("getting_deployment", deployment_id=str(deployment_id))
    
    service = DeploymentService(db)
    deployment = await service.get_deployment(deployment_id)

    return _build_response(deployment)


@router.post(
    "/{deployment_id}/start",
    response_model=DeploymentResponse,
    summary="Démarrer un déploiement",
    description="Démarre l'exécution d'un déploiement en attente.",
)
async def start_deployment(
    db: DbSession,
    deployment_id: UUID,
    current_user: RequireAdmin,
) -> DeploymentResponse:
    """Démarre ou relance un déploiement (PENDING ou FAILED)."""
    logger.info("starting_deployment", deployment_id=str(deployment_id))

    # Vérifier que le déploiement existe et est dans un état valide
    # with_for_update() acquires a row-level lock to prevent race conditions
    result = await db.execute(
        select(Deployment).where(Deployment.id == deployment_id).with_for_update()
    )
    deployment = result.scalar_one_or_none()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    if deployment.status not in (DeploymentStatus.PENDING, DeploymentStatus.FAILED, DeploymentStatus.PENDING_APPROVAL):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start deployment in status {deployment.status.value}",
        )

    # Marquer IN_PROGRESS immédiatement pour éviter le double traitement
    deployment.status = DeploymentStatus.IN_PROGRESS
    deployment.error_message = None
    deployment.started_at = deployment.started_at or datetime.now(timezone.utc)
    await db.commit()

    # Lancer en arrière-plan (le déploiement peut prendre 30+ min)
    async def run_start_background(dep_id):
        try:
            async with db_session() as session:
                bg_service = DeploymentService(session)
                await bg_service.start_deployment(dep_id)
                await session.commit()
                logger.info("start_deployment_completed", deployment_id=str(dep_id))
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(
                "start_deployment_failed",
                deployment_id=str(dep_id),
                error=error_msg,
                traceback=traceback.format_exc(),
            )
            try:
                async with db_session() as error_session:
                    await error_session.execute(
                        sql_update(Deployment)
                        .where(Deployment.id == dep_id)
                        .values(
                            status=DeploymentStatus.FAILED,
                            current_step="failed",
                            progress=0,
                            error_message=error_msg[:500],
                            completed_at=datetime.now(timezone.utc),
                        )
                    )
                    await error_session.commit()
                    try:
                        await emit_deployment_event(
                            str(dep_id),
                            EventType.DEPLOYMENT_FAILED,
                            {"status": "failed", "error": error_msg[:200]},
                        )
                        await emit_notification(
                            title="Déploiement échoué",
                            message=f"Le déploiement a échoué : {error_msg[:150]}",
                            notification_type="error",
                            data={"deployment_id": str(dep_id)},
                        )
                    except Exception:
                        pass
            except Exception as db_error:
                logger.error("failed_to_mark_deployment_failed", error=str(db_error))

    asyncio.create_task(run_start_background(deployment.id))

    return _build_response(deployment)


@router.post(
    "/{deployment_id}/resume",
    response_model=DeploymentResponse,
    summary="Reprendre un déploiement",
    description="Reprend un déploiement interrompu à son étape actuelle (post-install, installation logiciels, etc.).",
)
async def resume_deployment(
    db: DbSession,
    deployment_id: UUID,
    current_user: RequireAdmin,
) -> DeploymentResponse:
    """Reprend un déploiement interrompu."""
    logger.info("resuming_deployment", deployment_id=str(deployment_id))
    
    # Récupérer le déploiement
    result = await db.execute(select(Deployment).where(Deployment.id == deployment_id))
    deployment = result.scalar_one_or_none()
    
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    # Vérifier qu'il peut être repris
    if deployment.status in (DeploymentStatus.COMPLETED, DeploymentStatus.CANCELLED):
        raise HTTPException(status_code=400, detail=f"Cannot resume deployment in status {deployment.status.value}")
    
    if not deployment.vm_id:
        raise HTTPException(status_code=400, detail="Deployment has no VM linked. Cannot resume.")
    
    # Récupérer la VM
    vm_result = await db.execute(select(VirtualMachine).where(VirtualMachine.id == deployment.vm_id))
    vm = vm_result.scalar_one_or_none()
    
    if not vm:
        raise HTTPException(status_code=400, detail="VM not found in database")
    
    async def run_resume_background(dep_id, vm_id):
        """Reprend le déploiement en arrière-plan avec installation directe."""
        from src.domain.vm_service import VMService
        from src.domain.software_install_service import SoftwareInstallService
        from src.domain.software_catalog import get_software_by_name
        
        async def update_status(session, status, step, msg=None):
            # Calculer la progression a partir du step
            progress = STEP_PROGRESS_MAP.get(step, 10)
            if status == DeploymentStatus.COMPLETED:
                progress = 100
            elif status == DeploymentStatus.FAILED:
                progress = 0

            values = {
                "status": status,
                "current_step": step,
                "error_message": msg,
                "progress": progress,
            }
            if status in (DeploymentStatus.COMPLETED, DeploymentStatus.FAILED):
                values["completed_at"] = datetime.now(timezone.utc)

            await session.execute(
                sql_update(Deployment).where(Deployment.id == dep_id).values(**values)
            )
            await session.commit()
            logger.info("resume_status_update", deployment_id=str(dep_id), status=status.value, step=step)

            # Emettre un evenement WebSocket
            try:
                from src.api.websocket import emit_deployment_event, EventType

                event_map = {
                    DeploymentStatus.IN_PROGRESS: EventType.DEPLOYMENT_PROGRESS,
                    DeploymentStatus.COMPLETED: EventType.DEPLOYMENT_COMPLETED,
                    DeploymentStatus.FAILED: EventType.DEPLOYMENT_FAILED,
                }
                await emit_deployment_event(
                    str(dep_id),
                    event_map.get(status, EventType.DEPLOYMENT_PROGRESS),
                    {
                        "deployment_id": str(dep_id),
                        "status": status.value,
                        "current_step": step,
                        "progress": progress,
                        "message": msg,
                    }
                )
            except Exception as ws_err:
                logger.warning("resume_websocket_failed", error=str(ws_err))
        
        try:
            async with db_session() as session:
                # Récupérer le déploiement et la VM
                dep_result = await session.execute(select(Deployment).where(Deployment.id == dep_id))
                dep = dep_result.scalar_one()
                vm_result = await session.execute(select(VirtualMachine).where(VirtualMachine.id == vm_id))
                vm_obj = vm_result.scalar_one()
                
                config = dep.config or {}
                admin_password = config.get("admin_password", "")
                admin_username = config.get("admin_username") or config.get("username") or "otoroot"
                credentials = (admin_username, admin_password)
                # Utiliser le nom de la VM, pas le GUID hypervisor_vm_id
                vm_name = vm_obj.name
                
                logger.info("resume_starting", deployment_id=str(dep_id), vm_name=vm_name)
                
                # Obtenir le client Hyper-V
                vm_service = VMService(session)
                client = await vm_service._get_hypervisor_client(dep.hypervisor_id)
                
                # 1. Vérifier/Installer Chocolatey
                await update_status(session, DeploymentStatus.IN_PROGRESS, "installing_software")
                logger.info("resume_installing_chocolatey", vm_name=vm_name)
                
                # D'abord vérifier si Chocolatey est déjà installé
                check_script = "if(Test-Path $env:ProgramData\\chocolatey\\bin\\choco.exe){'CHOCO_OK'}else{'CHOCO_MISSING'}"
                check_result = await client.execute_in_vm(vm_name, check_script, credentials, timeout=60)
                
                choco_installed = check_result.success and check_result.output and "CHOCO_OK" in str(check_result.output)
                logger.info("resume_choco_check", vm_name=vm_name, installed=choco_installed, output=str(check_result.output)[:100] if check_result.output else "")
                
                if not choco_installed:
                    # Installer Chocolatey
                    install_script = "Set-ExecutionPolicy Bypass -Scope Process -Force;[Net.ServicePointManager]::SecurityProtocol=[Net.ServicePointManager]::SecurityProtocol -bor 3072;iex ((New-Object Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"
                    result = await client.execute_in_vm(vm_name, install_script, credentials, timeout=300)
                    logger.info("resume_choco_install_result", vm_name=vm_name, success=result.success, output=str(result.output)[:300] if result.output else "", error=result.error)
                    
                    # Vérifier à nouveau
                    check2 = await client.execute_in_vm(vm_name, check_script, credentials, timeout=60)
                    if not (check2.success and check2.output and "CHOCO_OK" in str(check2.output)):
                        raise Exception(f"Chocolatey install failed: {result.error or result.output or 'Unknown'}")
                
                logger.info("resume_chocolatey_ready", vm_name=vm_name)
                
                # 2. Installer les packages
                packages = config.get("packages", [])
                package_configs = config.get("package_configs", {})
                
                for pkg_name in packages:
                    logger.info("resume_installing_package", vm_name=vm_name, package=pkg_name)
                    
                    install_script = f"""$c="$env:ProgramData\\chocolatey\\bin\\choco.exe";if(!(Test-Path $c)){{throw "Choco not found"}};$r=&$c install {pkg_name} -y --no-progress 2>&1;$x=$LASTEXITCODE;if($x-ne 0){{throw "Install failed: $r"}};"{pkg_name} installed"
"""
                    result = await client.execute_in_vm(vm_name, install_script, credentials, timeout=300)
                    if result.success:
                        logger.info("resume_package_installed", vm_name=vm_name, package=pkg_name, output=str(result.output)[:100] if result.output else "")
                    else:
                        logger.warning("resume_package_failed", vm_name=vm_name, package=pkg_name, error=result.error)
                    
                    # Configurer le package si nécessaire
                    pkg_config = package_configs.get(pkg_name, {})
                    software_def = get_software_by_name(pkg_name)
                    if software_def and software_def.get("post_install_script") and pkg_config:
                        script = software_def["post_install_script"]
                        for key, value in pkg_config.items():
                            script = script.replace(f"{{{key}}}", str(value) if value else "")
                        
                        logger.info("resume_configuring_package", vm_name=vm_name, package=pkg_name)
                        cfg_result = await client.execute_in_vm(vm_name, script, credentials, timeout=120)
                        if cfg_result.success:
                            logger.info("resume_package_configured", vm_name=vm_name, package=pkg_name)
                        else:
                            logger.warning("resume_package_config_failed", vm_name=vm_name, package=pkg_name, error=cfg_result.error)
                
                # 3. Finalisation
                await update_status(session, DeploymentStatus.COMPLETED, "completed")
                logger.info("resume_deployment_completed", deployment_id=str(dep_id))
                
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error("resume_deployment_failed", deployment_id=str(dep_id), error=error_msg, traceback=traceback.format_exc())
            try:
                async with db_session() as error_session:
                    await error_session.execute(
                        sql_update(Deployment).where(Deployment.id == dep_id).values(
                            status=DeploymentStatus.FAILED,
                            current_step="failed",
                            progress=0,
                            error_message=error_msg[:500],
                            completed_at=datetime.now(timezone.utc),
                        )
                    )
                    await error_session.commit()
                    try:
                        await emit_deployment_event(
                            str(dep_id),
                            EventType.DEPLOYMENT_FAILED,
                            {"status": "failed", "error": error_msg[:200]},
                        )
                        await emit_notification(
                            title="Déploiement échoué",
                            message=f"Le déploiement a échoué : {error_msg[:150]}",
                            notification_type="error",
                            data={"deployment_id": str(dep_id)},
                        )
                    except Exception:
                        pass
            except Exception as db_error:
                logger.error("failed_to_mark_resume_failed", error=str(db_error))

    # Lancer en arrière-plan
    asyncio.create_task(run_resume_background(deployment.id, deployment.vm_id))

    return _build_response(deployment)


@router.post(
    "/{deployment_id}/cancel",
    response_model=DeploymentResponse,
    summary="Annuler un déploiement",
    description="Annule un déploiement en cours.",
)
async def cancel_deployment(
    db: DbSession,
    deployment_id: UUID,
    current_user: RequireAdmin,
) -> DeploymentResponse:
    """Annule un déploiement."""
    logger.info("cancelling_deployment", deployment_id=str(deployment_id))
    
    service = DeploymentService(db)
    deployment = await service.cancel_deployment(deployment_id)
    await db.commit()

    return _build_response(deployment)


@router.get(
    "/{deployment_id}/logs",
    response_model=list[DeploymentLogEntry],
    summary="Logs du déploiement",
    description="Retourne les logs d'un déploiement.",
)
async def get_deployment_logs(
    db: DbSession,
    deployment_id: UUID,
    current_user: CurrentUser,
) -> list[DeploymentLogEntry]:
    """Récupère les logs d'un déploiement."""
    logger.info("getting_deployment_logs", deployment_id=str(deployment_id))

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
    current_user: RequireAdmin,
) -> None:
    """Supprime un déploiement et ses logs associés."""
    logger.info("deleting_deployment", deployment_id=str(deployment_id))

    # Vérifier que le déploiement existe
    result = await db.execute(
        select(Deployment).where(Deployment.id == deployment_id)
    )
    deployment = result.scalar_one_or_none()
    
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    # Vérifier que le déploiement n'est pas en cours
    if deployment.status not in (
        DeploymentStatus.COMPLETED,
        DeploymentStatus.COMPLETED_WITH_WARNINGS,
        DeploymentStatus.FAILED,
        DeploymentStatus.CANCELLED,
        DeploymentStatus.REJECTED,
    ):
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
