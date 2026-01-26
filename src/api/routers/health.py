# =============================================================================
# VM Automation - Health Check Router
# =============================================================================
"""
Endpoints de health check pour monitoring et load balancers.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel

from src.common.config import settings
from src.common.database import check_db_connection
from src.common.logging import get_logger

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
    
    # Check Redis (TODO: implémenter)
    checks["redis"] = {
        "status": "unknown",
        "message": "Not implemented yet",
    }
    
    # Check Celery (TODO: implémenter)
    checks["celery"] = {
        "status": "unknown",
        "message": "Not implemented yet",
    }
    
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
