# =============================================================================
# VM Automation - Health Check Router
# =============================================================================
"""
Endpoints de health check pour monitoring et load balancers.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import CurrentUser
from src.common.config import settings
from src.common.database import check_db_connection, get_db_session
from src.common.logging import get_logger
from src.domain.models import Deployment, DeploymentStatus, VirtualMachine

logger = get_logger(__name__)

router = APIRouter()


class HealthStatus(BaseModel):
    """Schéma de réponse pour le health check."""

    status: str
    timestamp: str
    version: str
    environment: str
    checks: dict[str, Any]


@router.get(
    "/health",
    response_model=HealthStatus,
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description="Vérifie l'état de santé de l'application et de ses dépendances.",
)
async def health_check() -> HealthStatus:
    """
    Endpoint de health check.
    
    Vérifie:
    - Connexion à la base de données
    - Connexion à Redis (TODO)
    
    Returns:
        Status de santé avec détails des composants
    """
    checks: dict[str, Any] = {}
    overall_status = "healthy"
    
    # Check Database
    try:
        db_ok = await check_db_connection()
        checks["database"] = {
            "status": "healthy" if db_ok else "unhealthy",
            "host": settings.db_host,
        }
        if not db_ok:
            overall_status = "degraded"
    except Exception as e:
        checks["database"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        overall_status = "unhealthy"
    
    # Check Redis
    try:
        import redis
        r = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password.get_secret_value() or None,
            db=settings.redis_db,
            socket_timeout=3,
        )
        if r.ping():
            checks["redis"] = {
                "status": "healthy",
                "host": settings.redis_host,
                "port": settings.redis_port,
            }
        else:
            checks["redis"] = {"status": "unhealthy", "message": "PING failed"}
            overall_status = "degraded"
        r.close()
    except Exception as e:
        checks["redis"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        overall_status = "degraded"

    # Check Celery (via Redis broker accessibility)
    try:
        import redis as redis_lib
        broker_conn = redis_lib.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password.get_secret_value() or None,
            db=settings.redis_db,
            socket_timeout=3,
        )
        broker_ok = broker_conn.ping()
        broker_conn.close()
        if broker_ok:
            checks["celery"] = {
                "status": "healthy",
                "broker": settings.redis_url,
            }
        else:
            checks["celery"] = {"status": "unhealthy", "message": "Broker unreachable"}
            overall_status = "degraded"
    except Exception as e:
        checks["celery"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        overall_status = "degraded"
    
    return HealthStatus(
        status=overall_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="0.1.0",
        environment=settings.app_env,
        checks=checks,
    )


@router.get(
    "/ready",
    status_code=status.HTTP_200_OK,
    summary="Readiness Check",
    description="Vérifie si l'application est prête à recevoir du trafic.",
)
async def readiness_check() -> dict[str, str]:
    """
    Endpoint de readiness pour Kubernetes.
    
    Retourne 200 si l'application est prête, 503 sinon.
    """
    # Vérifier la DB
    db_ok = await check_db_connection()
    
    if not db_ok:
        return {"status": "not ready", "reason": "database unavailable"}
    
    return {"status": "ready"}


@router.get(
    "/live",
    status_code=status.HTTP_200_OK,
    summary="Liveness Check",
    description="Vérifie si l'application est vivante.",
)
async def liveness_check() -> dict[str, str]:
    """
    Endpoint de liveness pour Kubernetes.
    
    Retourne toujours 200 si l'application répond.
    """
    return {"status": "alive"}


@router.get(
    "/metrics",
    status_code=status.HTTP_200_OK,
    summary="Basic application metrics",
    description="Return basic application metrics for monitoring.",
)
async def get_metrics(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Return basic application metrics for monitoring."""
    from src.api.websocket import get_ws_manager

    ws_manager = get_ws_manager()

    vm_count = await db.execute(select(func.count()).select_from(VirtualMachine))
    deployment_count = await db.execute(select(func.count()).select_from(Deployment))
    active_deployments = await db.execute(
        select(func.count())
        .select_from(Deployment)
        .where(
            Deployment.status.in_(
                [DeploymentStatus.PENDING, DeploymentStatus.IN_PROGRESS]
            )
        )
    )

    return {
        "vms_total": vm_count.scalar() or 0,
        "deployments_total": deployment_count.scalar() or 0,
        "deployments_active": active_deployments.scalar() or 0,
        "websocket_clients": len(ws_manager._clients) if ws_manager else 0,
        "websocket_rooms": len(ws_manager._rooms) if ws_manager else 0,
    }
