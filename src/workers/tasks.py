# =============================================================================
# VM Automation - Celery Tasks
# =============================================================================
"""
Tâches asynchrones pour le traitement des déploiements.

Note: Utilise des connexions sync pour éviter les conflits avec le pool Celery.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.common.config import settings
from src.common.exceptions import (
    AlreadyExistsError,
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    HypervisorConnectionError,
    HypervisorError,
    NotFoundError,
    PowerShellError,
    PowerShellTimeoutError,
    ResourceBusyError,
    ValidationError,
    VMNotFoundError,
)
from src.domain.models import Deployment, DeploymentLog, DeploymentStatus, Hypervisor, HypervisorType, VirtualMachine, VMStatus

logger = get_task_logger(__name__)


def _send_deployment_email(db: Session, deployment: Deployment, status: DeploymentStatus) -> None:
    """
    Envoie un email de notification pour un déploiement terminé ou échoué.
    Ne lève jamais d'exception — les erreurs sont loguées silencieusement.
    """
    try:
        from src.common.email import email_service

        # Récupérer l'email de l'utilisateur
        user_email = None
        if deployment.created_by:
            row = db.execute(
                text("SELECT email FROM users WHERE id = :uid"),
                {"uid": str(deployment.created_by)},
            ).fetchone()
            if row:
                user_email = row[0]

        if not user_email:
            logger.debug(f"No user email for deployment {deployment.id}, skipping email notification")
            return

        config = deployment.config or {}

        # Calculer la durée
        duration_str = "N/A"
        if deployment.started_at and deployment.completed_at:
            delta = deployment.completed_at - deployment.started_at
            minutes, seconds = divmod(int(delta.total_seconds()), 60)
            hours, minutes = divmod(minutes, 60)
            duration_str = f"{hours}h {minutes}m {seconds}s" if hours > 0 else f"{minutes}m {seconds}s"

        # Construire les détails
        details = {
            "deployment_id": str(deployment.id)[:8],
            "ip_address": None,
            "hypervisor_name": "N/A",
            "duration": duration_str,
            "admin_username": config.get("admin_username", "otoroot"),
            "admin_password": config.get("admin_password", "tooroto"),
            "cpu_count": config.get("cpu_count", "N/A"),
            "ram_gb": config.get("ram_gb", "N/A"),
            "disk_gb": config.get("disk_gb", "N/A"),
            "os_type": config.get("template", {}).get("name", "N/A"),
            "os_family": config.get("template", {}).get("os_family", "N/A"),
            "network_switch": config.get("network_switch", "N/A"),
            "started_at": deployment.started_at.strftime("%Y-%m-%d %H:%M:%S") if deployment.started_at else "N/A",
            "completed_at": deployment.completed_at.strftime("%Y-%m-%d %H:%M:%S") if deployment.completed_at else "N/A",
            "failed_at": deployment.completed_at.strftime("%Y-%m-%d %H:%M:%S") if deployment.completed_at else "N/A",
            "current_step": deployment.current_step or "N/A",
        }

        # Récupérer l'IP de la VM
        if deployment.vm_id:
            try:
                vm_row = db.execute(
                    text("SELECT ip_address FROM virtual_machines WHERE id = :vid"),
                    {"vid": str(deployment.vm_id)},
                ).fetchone()
                if vm_row and vm_row[0]:
                    details["ip_address"] = vm_row[0]
            except Exception:
                pass

        # Récupérer le nom de l'hyperviseur
        if deployment.hypervisor_id:
            try:
                hyp_row = db.execute(
                    text("SELECT name FROM hypervisors WHERE id = :hid"),
                    {"hid": str(deployment.hypervisor_id)},
                ).fetchone()
                if hyp_row and hyp_row[0]:
                    details["hypervisor_name"] = hyp_row[0]
            except Exception:
                pass

        # Envoyer l'email
        if status == DeploymentStatus.COMPLETED:
            email_service.send_deployment_completed(user_email, deployment.vm_name, details)
        elif status == DeploymentStatus.FAILED:
            email_service.send_deployment_failed(
                user_email, deployment.vm_name, deployment.error_message or "Unknown error", details,
            )

        logger.info(f"Email notification sent for deployment {deployment.id} ({status.value}) to {user_email}")

    except Exception as e:
        logger.warning(f"Failed to send email notification for deployment {deployment.id}: {e}")

# Engine sync singleton — créé une seule fois au démarrage du worker
_sync_engine = None
_SyncSessionLocal = None


def _get_sync_engine():
    """Retourne l'engine sync SQLAlchemy (singleton)."""
    global _sync_engine
    if _sync_engine is None:
        sync_url = settings.database_url.replace("+asyncpg", "").replace(
            "postgresql://", "postgresql+psycopg2://"
        )
        _sync_engine = create_engine(
            sync_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            pool_recycle=3600,
        )
        logger.info("Sync database engine created for Celery workers")
    return _sync_engine


def get_sync_session() -> Session:
    """Retourne une session sync pour les workers (engine singleton)."""
    global _SyncSessionLocal
    if _SyncSessionLocal is None:
        _SyncSessionLocal = sessionmaker(
            bind=_get_sync_engine(), autocommit=False, autoflush=False
        )
    return _SyncSessionLocal()


_worker_async_engine = None


def _get_worker_async_engine():
    """Retourne l'engine async SQLAlchemy pour les workers (singleton)."""
    global _worker_async_engine
    if _worker_async_engine is None:
        _worker_async_engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            pool_recycle=300,
        )
        logger.info("Async database engine created for Celery workers")
    return _worker_async_engine


@asynccontextmanager
async def get_fresh_async_session():
    """Crée une session async avec un engine partagé (singleton)."""
    engine = _get_worker_async_engine()
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def run_async(coro):
    """Exécute une coroutine dans un worker Celery de façon sûre."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_deployment(self, deployment_id: str) -> dict:
    """
    Traite un déploiement spécifique.
    
    Args:
        deployment_id: ID du déploiement à traiter
        
    Returns:
        Statut du traitement
    """
    logger.info(f"Processing deployment: {deployment_id}")
    
    async def _process():
        async with get_fresh_async_session() as db:
            # Déterminer le type d'hyperviseur pour choisir le bon service
            from sqlalchemy import select as sa_select
            dep_result = await db.execute(
                sa_select(Deployment).where(Deployment.id == UUID(deployment_id))
            )
            dep = dep_result.scalar_one_or_none()

            service = None
            if dep and dep.hypervisor_id:
                hyp_result = await db.execute(
                    sa_select(Hypervisor).where(Hypervisor.id == dep.hypervisor_id)
                )
                hypervisor = hyp_result.scalar_one_or_none()
                if hypervisor and hypervisor.type == HypervisorType.VMWARE:
                    from src.domain.esxi_deployment_service import ESXiDeploymentService
                    service = ESXiDeploymentService(db)

            if service is None:
                from src.domain.deployment_service import DeploymentService
                service = DeploymentService(db)

            try:
                deployment = await service.start_deployment(UUID(deployment_id))
                
                return {
                    "status": "success",
                    "deployment_id": deployment_id,
                    "deployment_status": deployment.status.value,
                }
                
            except Exception as e:
                logger.error(f"Deployment {deployment_id} failed: {e}", exc_info=True)
                raise
    
    try:
        return run_async(_process())
    except Exception as e:
        logger.error(f"Error processing deployment {deployment_id}: {e}")

        # Permanent errors — retrying will never help
        if isinstance(e, (
            NotFoundError,
            VMNotFoundError,
            ValidationError,
            AlreadyExistsError,
            ConfigurationError,
            AuthenticationError,
            AuthorizationError,
        )):
            logger.warning(
                f"Deployment {deployment_id} failed with permanent error "
                f"({type(e).__name__}), will not retry: {e}"
            )
            raise

        # Transient / potentially recoverable errors — retry with backoff
        # Covers: HypervisorError (incl. HypervisorConnectionError, VMCreationError,
        # VMOperationError), PowerShellError (incl. PowerShellTimeoutError),
        # ResourceBusyError, OSError, ConnectionError, TimeoutError, etc.
        logger.info(
            f"Deployment {deployment_id} failed with transient error "
            f"({type(e).__name__}), scheduling retry {self.request.retries + 1}/{self.max_retries}"
        )
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


# on_failure handler - assigned below
def deployment_on_failure(self, exc, task_id, args, kwargs, einfo):
    """Handler appelé quand la tâche échoue définitivement (après tous les retries)."""
    deployment_id = args[0] if args else "unknown"
    logger.error(
        "deployment_task_permanently_failed",
        extra={
            "deployment_id": deployment_id,
            "error": str(exc),
            "task_id": task_id,
        },
    )
    # Marquer le déploiement comme FAILED en base
    try:
        db = get_sync_session()
        try:
            deployment = db.query(Deployment).filter(
                Deployment.id == UUID(deployment_id)
            ).first()
            if deployment and deployment.status not in (
                DeploymentStatus.COMPLETED, DeploymentStatus.CANCELLED, DeploymentStatus.FAILED
            ):
                deployment.status = DeploymentStatus.FAILED
                deployment.error_message = f"Task permanently failed: {exc}"
                deployment.completed_at = datetime.now(timezone.utc)
                log = DeploymentLog(
                    id=uuid4(),
                    deployment_id=deployment.id,
                    step="task_failed",
                    message=f"Celery task permanently failed after retries: {exc}",
                    level="error",
                    details={"task_id": task_id},
                )
                db.add(log)
                db.commit()
        finally:
            db.close()
    except Exception as db_err:
        logger.error(f"Failed to mark deployment {deployment_id} as failed in DB: {db_err}")

process_deployment.on_failure = deployment_on_failure


@shared_task
def process_pending_deployments() -> dict:
    """
    Recherche et démarre les déploiements en attente.
    Exécutée périodiquement par Celery Beat.
    
    Returns:
        Nombre de déploiements traités
    """
    logger.info("Checking for pending deployments...")
    
    # Utiliser session sync pour éviter les problèmes d'event loop
    db = get_sync_session()
    try:
        # SELECT FOR UPDATE : verrou atomique pour éviter le double-start
        # si deux workers Celery Beat tournent simultanément.
        pending = (
            db.query(Deployment)
            .filter(Deployment.status == DeploymentStatus.PENDING)
            .order_by(Deployment.created_at)
            .limit(5)
            .with_for_update(skip_locked=True)
            .all()
        )

        processed = 0
        for deployment in pending:
            logger.info(f"Queuing deployment: {deployment.id} ({deployment.vm_name})")

            # Marquer comme IN_PROGRESS et committer immédiatement
            # pour libérer le verrou et rendre le changement visible
            # avant de lancer la tâche Celery.
            deployment.status = DeploymentStatus.IN_PROGRESS
            deployment.started_at = datetime.now(timezone.utc)
            db.commit()

            # Lancer la tâche de traitement après le commit
            process_deployment.delay(str(deployment.id))
            processed += 1

        logger.info(f"Queued {processed} pending deployments")
        return {"processed": processed}

    except Exception as e:
        db.rollback()
        logger.error(f"Error processing pending deployments: {e}")
        raise
    finally:
        db.close()


@shared_task
def monitor_active_deployments() -> dict:
    """
    Surveille les déploiements actifs (installation en cours).
    Vérifie si l'installation est terminée via heartbeat/PowerShell Direct.
    
    Returns:
        Statut du monitoring
    """
    logger.info("Monitoring active deployments...")
    
    # Timeout configurable (en minutes) au-delà duquel un déploiement INSTALLING est considéré en échec
    timeout_minutes = int(settings.deployment_timeout_minutes) if hasattr(settings, "deployment_timeout_minutes") else 60

    db = get_sync_session()
    try:
        # Trouver les déploiements en cours d'installation
        installing = db.query(Deployment).filter(
            Deployment.status == DeploymentStatus.INSTALLING
        ).order_by(Deployment.started_at).all()

        monitored = 0
        timed_out = 0
        now = datetime.now(timezone.utc)

        for deployment in installing:
            logger.info(
                f"Monitoring deployment: {deployment.id} ({deployment.vm_name}) "
                f"- started_at={deployment.started_at}, current_step={deployment.current_step}"
            )

            # Vérifier si le déploiement dépasse le timeout
            if deployment.started_at:
                elapsed = now - deployment.started_at
                if elapsed > timedelta(minutes=timeout_minutes):
                    logger.warning(
                        f"Deployment {deployment.id} ({deployment.vm_name}) timed out "
                        f"after {elapsed.total_seconds() / 60:.0f} minutes (limit: {timeout_minutes}min)"
                    )
                    deployment.status = DeploymentStatus.FAILED
                    deployment.error_message = (
                        f"Installation timed out after {elapsed.total_seconds() / 60:.0f} minutes "
                        f"(limit: {timeout_minutes} minutes)"
                    )
                    deployment.completed_at = now

                    # Ajouter log de timeout
                    log = DeploymentLog(
                        id=uuid4(),
                        deployment_id=deployment.id,
                        step="timeout",
                        message=deployment.error_message,
                        level="error",
                        details={"elapsed_minutes": elapsed.total_seconds() / 60},
                    )
                    db.add(log)

                    # Update associated VM status to ERROR
                    if deployment.vm_id:
                        vm = db.query(VirtualMachine).filter(
                            VirtualMachine.id == deployment.vm_id
                        ).first()
                        if vm:
                            vm.status = VMStatus.ERROR
                            logger.info(
                                f"VM {vm.id} ({vm.name}) status set to ERROR "
                                f"due to deployment timeout"
                            )

                    # Envoyer notification email d'échec (timeout)
                    _send_deployment_email(db, deployment, DeploymentStatus.FAILED)

                    timed_out += 1
                    continue

            # Vérifier si le déploiement a atteint l'étape post-install (prêt à compléter)
            if deployment.current_step in ("post_install_complete", "post_install"):
                logger.info(
                    f"Deployment {deployment.id} ({deployment.vm_name}) reached "
                    f"step '{deployment.current_step}' — queuing completion"
                )
                complete_deployment.delay(str(deployment.id))

            monitored += 1

        db.commit()
        logger.info(f"Monitored {monitored} active deployments, {timed_out} timed out")
        return {"monitored": monitored, "timed_out": timed_out}

    except Exception as e:
        db.rollback()
        logger.error(f"Error monitoring deployments: {e}")
        raise
    finally:
        db.close()


@shared_task
def complete_deployment(deployment_id: str) -> dict:
    """
    Finalise un déploiement après l'installation.
    Exécute les étapes de post-configuration.
    
    Args:
        deployment_id: ID du déploiement
        
    Returns:
        Statut de la finalisation
    """
    logger.info(f"Completing deployment: {deployment_id}")
    
    db = get_sync_session()
    try:
        deployment = db.query(Deployment).filter(
            Deployment.id == UUID(deployment_id)
        ).first()
        
        if not deployment:
            return {"status": "error", "message": "Deployment not found"}
        
        try:
            # Vérifier que le déploiement est dans un état compatible avec la complétion
            if deployment.status not in (
                DeploymentStatus.INSTALLING,
                DeploymentStatus.POST_INSTALL,
                DeploymentStatus.INSTALLING_SOFTWARE,
            ):
                msg = (
                    f"Cannot complete deployment in status '{deployment.status.value}' "
                    f"(expected: installing_os, post_install, or installing_software)"
                )
                logger.warning(f"Deployment {deployment_id}: {msg}")
                return {"status": "skipped", "deployment_id": deployment_id, "message": msg}

            now = datetime.now(timezone.utc)

            # Calculer la durée totale du déploiement
            duration_msg = ""
            if deployment.started_at:
                elapsed = now - deployment.started_at
                duration_msg = f" (duration: {elapsed.total_seconds() / 60:.1f} minutes)"

            logger.info(
                f"Completing deployment {deployment_id} ({deployment.vm_name}){duration_msg}"
            )

            # ── Verify VM state on Hyper-V before marking as completed ──
            vm_state_warning = None
            if deployment.vm_id:
                try:
                    async def _verify_vm_state():
                        async with get_fresh_async_session() as async_db:
                            from src.domain.vm_service import VMService
                            service = VMService(async_db)
                            vm = await service.sync_vm_state(deployment.vm_id)
                            return vm.state.value if vm.state else "unknown"

                    actual_state = run_async(_verify_vm_state())
                    if actual_state != "running":
                        vm_state_warning = (
                            f"VM '{deployment.vm_name}' is not running on Hyper-V "
                            f"(state: {actual_state}). Deployment marked as completed "
                            f"but the VM may need manual attention."
                        )
                        logger.warning(
                            f"Deployment {deployment_id}: {vm_state_warning}"
                        )

                        # Update VM status in sync DB to reflect actual state
                        db.execute(
                            text(
                                "UPDATE virtual_machines SET state = :state WHERE id = :vid"
                            ),
                            {"state": actual_state, "vid": str(deployment.vm_id)},
                        )
                except Exception as sync_err:
                    vm_state_warning = (
                        f"Could not verify VM state on Hyper-V: {sync_err}"
                    )
                    logger.warning(
                        f"Deployment {deployment_id}: {vm_state_warning}"
                    )

            # Marquer comme terminé
            deployment.status = DeploymentStatus.COMPLETED
            deployment.completed_at = now
            deployment.current_step = "completed"
            deployment.progress = 100

            # Ajouter log de complétion
            completion_details = {
                "completed_at": now.isoformat(),
                "previous_step": deployment.current_step,
            }
            if vm_state_warning:
                completion_details["vm_state_warning"] = vm_state_warning

            log = DeploymentLog(
                id=uuid4(),
                deployment_id=deployment.id,
                step="completed",
                message=(
                    f"Deployment completed successfully{duration_msg}"
                    if not vm_state_warning
                    else f"Deployment completed with warning{duration_msg}: {vm_state_warning}"
                ),
                level="info" if not vm_state_warning else "warning",
                details=completion_details,
            )
            db.add(log)
            db.commit()

            logger.info(f"Deployment {deployment_id} ({deployment.vm_name}) marked as COMPLETED")

            # Envoyer notification email
            _send_deployment_email(db, deployment, DeploymentStatus.COMPLETED)

            return {
                "status": "success",
                "deployment_id": deployment_id,
            }

        except Exception as e:
            logger.error(f"Failed to complete deployment {deployment_id}: {e}")
            deployment.status = DeploymentStatus.FAILED
            deployment.error_message = str(e)

            # Update associated VM status to ERROR
            if deployment.vm_id:
                vm = db.query(VirtualMachine).filter(
                    VirtualMachine.id == deployment.vm_id
                ).first()
                if vm:
                    vm.status = VMStatus.ERROR
                    logger.info(
                        f"VM {vm.id} ({vm.name}) status set to ERROR "
                        f"due to deployment completion failure"
                    )

            db.commit()

            # Envoyer notification email d'échec
            _send_deployment_email(db, deployment, DeploymentStatus.FAILED)

            raise
    finally:
        db.close()


@shared_task
def cleanup_old_logs() -> dict:
    """
    Nettoie les logs de déploiement anciens.
    Garde les logs des 30 derniers jours.
    
    Returns:
        Nombre de logs supprimés
    """
    logger.info("Cleaning up old deployment logs...")
    
    db = get_sync_session()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        
        # Supprimer les vieux logs
        count = db.query(DeploymentLog).filter(
            DeploymentLog.created_at < cutoff
        ).delete()
        
        db.commit()
        logger.info(f"Deleted {count} old logs")
        
        return {"deleted": count}
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error cleaning up logs: {e}")
        raise
    finally:
        db.close()


@shared_task
def cancel_deployment_task(deployment_id: str) -> dict:
    """
    Annule un déploiement en cours.
    
    Args:
        deployment_id: ID du déploiement
        
    Returns:
        Statut de l'annulation
    """
    logger.info(f"Cancelling deployment: {deployment_id}")
    
    db = get_sync_session()
    try:
        deployment = db.query(Deployment).filter(
            Deployment.id == UUID(deployment_id)
        ).first()
        
        if not deployment:
            return {"status": "error", "message": "Deployment not found"}
        
        if deployment.status in (DeploymentStatus.COMPLETED, DeploymentStatus.CANCELLED):
            return {"status": "error", "message": f"Cannot cancel deployment in status {deployment.status}"}
        
        deployment.status = DeploymentStatus.CANCELLED
        deployment.error_message = "Cancelled by user"
        deployment.completed_at = datetime.now(timezone.utc)
        
        # Ajouter log
        log = DeploymentLog(
            id=uuid4(),
            deployment_id=deployment.id,
            step="cancelled",
            message="Deployment cancelled by user",
            level="warning",
            details={},
        )
        db.add(log)
        db.commit()
        
        return {
            "status": "cancelled",
            "deployment_id": deployment_id,
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error cancelling deployment: {e}")
        raise
    finally:
        db.close()


@shared_task
def cleanup_vnc_sessions() -> dict:
    """
    Nettoie les sessions VNC expirées.
    Ferme les sessions dépassant le timeout configuré.
    Exécutée périodiquement par Celery Beat (toutes les 5 minutes).

    Returns:
        Nombre de sessions nettoyées
    """
    logger.info("Checking for expired VNC sessions...")

    try:
        from src.api.routers.console import _active_consoles as active_vnc_sessions
    except ImportError:
        logger.debug("VNC console router not available, skipping cleanup")
        return {"cleaned": 0, "active": 0}

    timeout = settings.vnc_session_timeout
    now = datetime.now(timezone.utc)
    cleaned = 0
    to_remove: list[str] = []

    for session_id, session in list(active_vnc_sessions.items()):
        created_at = session.get("created_at")
        if not created_at:
            continue

        # Support both datetime objects and ISO strings
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

        # Ensure timezone-aware comparison
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        elapsed = (now - created_at).total_seconds()
        if elapsed > timeout:
            to_remove.append(session_id)
            logger.info(
                f"VNC session {session_id} expired after {elapsed:.0f}s "
                f"(timeout: {timeout}s)"
            )

    for session_id in to_remove:
        try:
            del active_vnc_sessions[session_id]
            cleaned += 1
        except KeyError:
            pass

    active = len(active_vnc_sessions)
    if cleaned > 0:
        logger.info(f"Cleaned {cleaned} expired VNC sessions, {active} still active")
    else:
        logger.debug(f"No expired VNC sessions, {active} active")

    return {"cleaned": cleaned, "active": active}


@shared_task
def sync_all_hypervisors() -> dict:
    """
    Synchronise toutes les VMs de tous les hyperviseurs actifs.
    Exécutée périodiquement par Celery Beat (toutes les 5 minutes).
    
    Returns:
        Résumé de la synchronisation
    """
    logger.info("Starting automatic synchronization of all hypervisors...")
    
    async def _sync():
        async with get_fresh_async_session() as db:
            from src.domain.vm_service import VMService
            from src.api.websocket import emit_notification
            
            service = VMService(db)
            
            # Récupérer tous les hyperviseurs actifs
            hypervisors = await service.list_hypervisors()
            active_hypervisors = [h for h in hypervisors if h.is_active]
            
            total_imported = 0
            total_updated = 0
            total_missing = 0
            errors = []
            
            for hypervisor in active_hypervisors:
                try:
                    logger.info(f"Syncing hypervisor: {hypervisor.name} ({hypervisor.id})")
                    
                    result = await service.sync_all_vms(
                        hypervisor_id=hypervisor.id,
                        import_new=True,
                        update_existing=True,
                        mark_missing=True,
                    )
                    
                    total_imported += result["imported"]
                    total_updated += result["updated"]
                    total_missing += result["marked_missing"]
                    
                    if result["errors"]:
                        errors.extend(result["errors"])
                    
                    # Si des changements ont été détectés, émettre une notification
                    changes = result["imported"] + result["updated"] + result["marked_missing"]
                    if changes > 0:
                        logger.info(
                            f"Hypervisor {hypervisor.name}: "
                            f"{result['imported']} imported, "
                            f"{result['updated']} updated, "
                            f"{result['marked_missing']} missing"
                        )
                        
                        # Émettre notification WebSocket
                        try:
                            await emit_notification(
                                title="Synchronisation Hyper-V",
                                message=f"{hypervisor.name}: {changes} changement(s) détecté(s)",
                                notification_type="info" if not result["errors"] else "warning",
                            )
                        except Exception as ws_err:
                            logger.warning(f"Failed to emit WebSocket notification: {ws_err}")
                    
                except Exception as e:
                    error_msg = f"Error syncing {hypervisor.name}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            
            return {
                "hypervisors_synced": len(active_hypervisors),
                "total_imported": total_imported,
                "total_updated": total_updated,
                "total_missing": total_missing,
                "errors": errors,
            }
    
    try:
        result = run_async(_sync())
        logger.info(
            f"Sync completed: {result['hypervisors_synced']} hypervisors, "
            f"{result['total_imported']} imported, "
            f"{result['total_updated']} updated, "
            f"{result['total_missing']} missing"
        )
        return result
    except Exception as e:
        logger.error(f"Error in sync_all_hypervisors: {e}")
        return {
            "hypervisors_synced": 0,
            "total_imported": 0,
            "total_updated": 0,
            "total_missing": 0,
            "errors": [str(e)],
        }
