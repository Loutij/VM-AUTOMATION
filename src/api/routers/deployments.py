# =============================================================================
# VM Automation - Deployments Router
# =============================================================================
"""
Endpoints pour la gestion des déploiements de VMs.
"""

from datetime import datetime
from typing import Annotated, Any, Literal
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

    class Config:
        from_attributes = True


# Mapping statut -> progression (pour les statuts terminaux)
STATUS_PROGRESS_MAP: dict[str, int] = {
    "pending": 0,
    "completed": 100,
    "failed": 0,
    "cancelled": 0,
}

# Mapping current_step -> progression (pour les étapes intermédiaires)
STEP_PROGRESS_MAP: dict[str, int] = {
    "validating": 5,
    "creating_vm": 15,
    "mounting_iso": 25,
    "deploying_dism": 35,
    "configuring_network": 45,
    "starting_installation": 55,
    "waiting_vm_ready": 65,
    "post_configuration": 75,
    "installing_software": 85,
    "finalizing": 95,
    "completed": 100,
    "failed": 0,
}


def get_progress_from_status(status: str, current_step: str | None = None) -> int:
    """Calcule la progression à partir du statut et de l'étape courante."""
    # Statuts terminaux ont une progression fixe
    if status in STATUS_PROGRESS_MAP:
        return STATUS_PROGRESS_MAP[status]
    
    # Pour les statuts en cours, utiliser current_step
    if current_step:
        return STEP_PROGRESS_MAP.get(current_step, 10)
    
    # Fallback pour in_progress sans step
    return 10


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
            progress=get_progress_from_status(d.status.value, d.current_step),
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
        template_id=str(deployment.os_template_id),
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
            import traceback
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
                        from sqlalchemy import select, update
                        from src.domain.models import Deployment
                        await error_session.execute(
                            update(Deployment)
                            .where(Deployment.id == deployment_id)
                            .values(
                                status=DeploymentStatus.FAILED,
                                current_step="failed",
                                error_message=error_msg[:500]
                            )
                        )
                        await error_session.commit()
                        logger.info("deployment_marked_failed", deployment_id=str(deployment_id))
                except Exception as db_error:
                    logger.error("failed_to_mark_deployment_failed", error=str(db_error))
        
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
        progress=get_progress_from_status(created.status.value, created.current_step),
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
        progress=get_progress_from_status(deployment.status.value, deployment.current_step),
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
        progress=get_progress_from_status(deployment.status.value, deployment.current_step),
        current_step=deployment.current_step,
        error_message=deployment.error_message,
        config=deployment.config,
        created_at=deployment.created_at,
        started_at=deployment.started_at,
        completed_at=deployment.completed_at,
    )


@router.post(
    "/{deployment_id}/resume",
    response_model=DeploymentResponse,
    summary="Reprendre un déploiement",
    description="Reprend un déploiement interrompu à son étape actuelle (post-install, installation logiciels, etc.).",
)
async def resume_deployment(
    db: DbSession,
    deployment_id: UUID,
) -> DeploymentResponse:
    """Reprend un déploiement interrompu."""
    import traceback
    from sqlalchemy import select
    from src.domain.models import Deployment, VirtualMachine
    
    logger.info("resuming_deployment", deployment_id=str(deployment_id))
    
    # Récupérer le déploiement
    result = await db.execute(select(Deployment).where(Deployment.id == deployment_id))
    deployment = result.scalar_one_or_none()
    
    if not deployment:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    # Vérifier qu'il peut être repris
    if deployment.status in (DeploymentStatus.COMPLETED, DeploymentStatus.CANCELLED):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Cannot resume deployment in status {deployment.status.value}")
    
    if not deployment.vm_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Deployment has no VM linked. Cannot resume.")
    
    # Récupérer la VM
    vm_result = await db.execute(select(VirtualMachine).where(VirtualMachine.id == deployment.vm_id))
    vm = vm_result.scalar_one_or_none()
    
    if not vm:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="VM not found in database")
    
    async def run_resume_background(dep_id, vm_id):
        """Reprend le déploiement en arrière-plan avec installation directe."""
        from src.common.database import db_session
        from src.domain.vm_service import VMService
        from src.domain.software_install_service import SoftwareInstallService
        from src.domain.software_catalog import get_software_by_name
        from sqlalchemy import update as sql_update
        
        async def update_status(session, status, step, msg=None):
            await session.execute(
                sql_update(Deployment).where(Deployment.id == dep_id).values(
                    status=status, current_step=step, error_message=msg
                )
            )
            await session.commit()
            logger.info("resume_status_update", deployment_id=str(dep_id), status=status.value, step=step)
        
        try:
            async with db_session() as session:
                # Récupérer le déploiement et la VM
                dep_result = await session.execute(select(Deployment).where(Deployment.id == dep_id))
                dep = dep_result.scalar_one()
                vm_result = await session.execute(select(VirtualMachine).where(VirtualMachine.id == vm_id))
                vm_obj = vm_result.scalar_one()
                
                config = dep.config or {}
                admin_password = config.get("admin_password", "")
                credentials = ("Administrator", admin_password)
                vm_name = vm_obj.hypervisor_vm_id or vm_obj.name
                
                logger.info("resume_starting", deployment_id=str(dep_id), vm_name=vm_name)
                
                # Obtenir le client Hyper-V
                vm_service = VMService(session)
                client = await vm_service._get_hypervisor_client(dep.hypervisor_id)
                
                # 1. Installer Chocolatey
                await update_status(session, DeploymentStatus.IN_PROGRESS, "installing_software")
                logger.info("resume_installing_chocolatey", vm_name=vm_name)
                
                choco_script = """$ErrorActionPreference='Stop';if(!(Get-Command choco -EA 0)){Set-ExecutionPolicy Bypass -Scope Process -Force;[System.Net.ServicePointManager]::SecurityProtocol=[System.Net.ServicePointManager]::SecurityProtocol -bor 3072;iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))};"Chocolatey OK"
"""
                result = await client.execute_in_vm(vm_name, choco_script, credentials, timeout=300)
                if result.success:
                    logger.info("resume_chocolatey_installed", vm_name=vm_name, output=result.output[:200] if result.output else "")
                else:
                    logger.error("resume_chocolatey_failed", vm_name=vm_name, error=result.error)
                    raise Exception(f"Chocolatey install failed: {result.error}")
                
                # 2. Installer les packages
                packages = config.get("packages", [])
                package_configs = config.get("package_configs", {})
                
                for pkg_name in packages:
                    logger.info("resume_installing_package", vm_name=vm_name, package=pkg_name)
                    
                    install_script = f"""$c="$env:ProgramData\\chocolatey\\bin\\choco.exe";if(!(Test-Path $c)){{throw "Choco not found"}};$r=&$c install {pkg_name} -y --no-progress 2>&1;$x=$LASTEXITCODE;if($x-ne 0){{throw "Install failed: $r"}};"{pkg_name} installed"
"""
                    result = await client.execute_in_vm(vm_name, install_script, credentials, timeout=300)
                    if result.success:
                        logger.info("resume_package_installed", vm_name=vm_name, package=pkg_name, output=result.output[:100] if result.output else "")
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
                            error_message=error_msg[:500]
                        )
                    )
                    await error_session.commit()
            except Exception as db_error:
                logger.error("failed_to_mark_resume_failed", error=str(db_error))
    
    # Lancer en arrière-plan
    import asyncio
    asyncio.create_task(run_resume_background(deployment.id, deployment.vm_id))
    
    return DeploymentResponse(
        id=deployment.id,
        vm_name=deployment.vm_name,
        hypervisor_id=deployment.hypervisor_id,
        os_template_id=deployment.os_template_id,
        vm_id=deployment.vm_id,
        status=deployment.status.value,
        progress=get_progress_from_status(deployment.status.value, deployment.current_step),
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
        progress=get_progress_from_status(deployment.status.value, deployment.current_step),
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
