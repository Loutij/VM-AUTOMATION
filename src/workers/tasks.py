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
from sqlalchemy import select, create_engine, update
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.common.config import settings
from src.domain.models import Deployment, DeploymentLog, DeploymentStatus

logger = get_task_logger(__name__)


def get_sync_session() -> Session:
    """Crée une nouvelle session sync pour les workers."""
    # Utiliser psycopg2 sync au lieu d'asyncpg
    sync_url = settings.database_url.replace("+asyncpg", "").replace("postgresql://", "postgresql+psycopg2://")
    engine = create_engine(sync_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return SessionLocal()


@asynccontextmanager
async def get_fresh_async_session():
    """Crée une session async avec un engine frais (évite les problèmes de loop)."""
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
    )
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
    await engine.dispose()


def run_async(coro):
    """Helper pour exécuter une coroutine dans un contexte sync."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


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
        # Retry si possible
        raise self.retry(exc=e)


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
        # Trouver les déploiements PENDING
        pending = db.query(Deployment).filter(
            Deployment.status == DeploymentStatus.PENDING
        ).order_by(Deployment.created_at).limit(5).all()
        
        processed = 0
        for deployment in pending:
            logger.info(f"Queuing deployment: {deployment.id} ({deployment.vm_name})")
            
            # Marquer comme IN_PROGRESS pour éviter double traitement
            deployment.status = DeploymentStatus.IN_PROGRESS
            deployment.started_at = datetime.now(timezone.utc)
            
            # Lancer la tâche de traitement
            process_deployment.delay(str(deployment.id))
            processed += 1
        
        db.commit()
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
    
    db = get_sync_session()
    try:
        # Trouver les déploiements en cours d'installation
        installing = db.query(Deployment).filter(
            Deployment.status == DeploymentStatus.INSTALLING
        ).order_by(Deployment.started_at).all()
        
        monitored = 0
        for deployment in installing:
            logger.info(f"Monitoring deployment: {deployment.id} ({deployment.vm_name})")
            
            # TODO: Implémenter la vérification via PowerShell Direct
            # - Vérifier le heartbeat
            # - Vérifier si l'installation est terminée
            # - Si terminé, passer à post-configuration
            
            monitored += 1
        
        return {"monitored": monitored}
        
    except Exception as e:
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
            # TODO: Exécuter post-configuration
            # - Configuration réseau finale
            # - Installation logiciels
            # - Jonction domaine
            
            # Marquer comme terminé
            deployment.status = DeploymentStatus.COMPLETED
            deployment.completed_at = datetime.now(timezone.utc)
            deployment.current_step = "completed"
            
            # Ajouter log
            log = DeploymentLog(
                id=uuid4(),
                deployment_id=deployment.id,
                step="completed",
                message="Deployment completed successfully",
                level="info",
                details={},
            )
            db.add(log)
            db.commit()
            
            return {
                "status": "success",
                "deployment_id": deployment_id,
            }
            
        except Exception as e:
            logger.error(f"Failed to complete deployment {deployment_id}: {e}")
            deployment.status = DeploymentStatus.FAILED
            deployment.error_message = str(e)
            db.commit()
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
