# =============================================================================
# VM Automation - Callback Router
# =============================================================================
"""
Routes pour recevoir les callbacks des VMs après installation.
Permet aux VMs de signaler la fin de leur installation.
"""

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from src.api.dependencies import CurrentUser
from src.common.config import settings
from src.common.database import db_session
from src.common.logging import get_logger
from src.domain.models import Deployment, DeploymentStatus
from src.api.websocket import EventType, emit_deployment_event

logger = get_logger(__name__)

router = APIRouter(prefix="/callbacks", tags=["Callbacks"])


def generate_callback_token(vm_name: str, secret: str) -> str:
    """
    Generate an HMAC-SHA256 callback token for a VM.

    This token should be embedded in VM installation scripts so the VM
    can authenticate its callbacks without knowing the raw API secret.
    """
    return hmac.new(secret.encode(), vm_name.encode(), hashlib.sha256).hexdigest()


async def verify_callback_token(
    x_callback_token: Annotated[str | None, Header()] = None,
    x_vm_name: Annotated[str | None, Header()] = None,
) -> str:
    """
    Vérifie le token HMAC pour les callbacks de VMs.
    Le token est un HMAC-SHA256 du hostname signé avec la clé API secrète.
    Accepte aussi le token brut (clé API) pour compatibilité (deprecated).
    """
    if x_callback_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Callback-Token header",
        )

    secret = settings.api_secret_key.get_secret_value()

    # Preferred: verify HMAC-SHA256 token (requires X-VM-Name header)
    if x_vm_name:
        expected = generate_callback_token(x_vm_name, secret)
        if hmac.compare_digest(x_callback_token, expected):
            return x_callback_token

    # Backward compatibility: accept raw secret (deprecated)
    if hmac.compare_digest(x_callback_token, secret):
        logger.warning(
            "callback_raw_secret_deprecated",
            message="Callback authenticated with raw API secret. "
            "Migrate to HMAC tokens using generate_callback_token(). "
            "Raw secret support will be removed in a future release.",
        )
        return x_callback_token

    # Otherwise reject
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid callback token",
    )


# =============================================================================
# Schemas
# =============================================================================


class VMCallbackRequest(BaseModel):
    """Schéma pour un callback de VM."""

    hostname: str
    status: str  # "completed", "failed", "progress"
    ip: str | None = None
    message: str | None = None
    deployment_id: str | None = None
    step: str | None = None
    progress: int | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None


class CallbackResponse(BaseModel):
    """Réponse au callback."""

    received: bool = True
    timestamp: datetime
    message: str


# =============================================================================
# Storage (en mémoire pour l'instant, à migrer vers Redis/DB)
# =============================================================================

# Stockage temporaire des callbacks reçus
_callbacks_store: dict[str, list[dict[str, Any]]] = {}


def store_callback(hostname: str, data: dict[str, Any]) -> None:
    """Stocke un callback reçu."""
    if hostname not in _callbacks_store:
        _callbacks_store[hostname] = []
    
    _callbacks_store[hostname].append({
        **data,
        "received_at": datetime.now(timezone.utc).isoformat(),
    })
    
    # Limiter à 100 callbacks par hostname
    if len(_callbacks_store[hostname]) > 100:
        _callbacks_store[hostname] = _callbacks_store[hostname][-100:]


def get_callbacks(hostname: str) -> list[dict[str, Any]]:
    """Récupère les callbacks d'un hostname."""
    return _callbacks_store.get(hostname, [])


def clear_callbacks(hostname: str) -> int:
    """Supprime les callbacks d'un hostname."""
    if hostname in _callbacks_store:
        count = len(_callbacks_store[hostname])
        del _callbacks_store[hostname]
        return count
    return 0


# =============================================================================
# Background Tasks
# =============================================================================


async def process_callback(callback_data: VMCallbackRequest) -> None:
    """
    Traite un callback de manière asynchrone.
    
    Cette fonction peut être étendue pour:
    - Mettre à jour le statut du déploiement en DB
    - Envoyer des notifications
    - Déclencher des actions post-installation
    """
    logger.info(
        "processing_vm_callback",
        hostname=callback_data.hostname,
        status=callback_data.status,
        ip=callback_data.ip,
    )
    
    # Mettre à jour le déploiement en DB si identifiable
    deployment = None
    try:
        async with db_session() as session:
            # Chercher par deployment_id si fourni, sinon par vm_name
            if callback_data.deployment_id:
                result = await session.execute(
                    select(Deployment).where(
                        Deployment.id == callback_data.deployment_id
                    )
                )
                deployment = result.scalar_one_or_none()

            if not deployment:
                # Fallback: chercher le déploiement actif le plus récent pour ce hostname
                result = await session.execute(
                    select(Deployment)
                    .where(Deployment.vm_name == callback_data.hostname)
                    .where(
                        Deployment.status.in_([
                            DeploymentStatus.IN_PROGRESS,
                            DeploymentStatus.INSTALLING,
                            DeploymentStatus.POST_INSTALL,
                            DeploymentStatus.INSTALLING_SOFTWARE,
                        ])
                    )
                    .order_by(Deployment.created_at.desc())
                    .limit(1)
                )
                deployment = result.scalar_one_or_none()

            if deployment:
                # Mapper le statut du callback vers DeploymentStatus
                status_map = {
                    "completed": DeploymentStatus.COMPLETED,
                    "failed": DeploymentStatus.FAILED,
                    "progress": DeploymentStatus.IN_PROGRESS,
                }
                new_status = status_map.get(callback_data.status)

                if new_status:
                    deployment.status = new_status

                if callback_data.step:
                    deployment.current_step = callback_data.step

                if callback_data.progress is not None:
                    deployment.progress = callback_data.progress

                if callback_data.error:
                    deployment.error_message = callback_data.error

                if callback_data.status == "completed":
                    deployment.completed_at = datetime.now(timezone.utc)

                await session.commit()

                logger.info(
                    "deployment_updated_from_callback",
                    deployment_id=str(deployment.id),
                    new_status=callback_data.status,
                )

                # Emettre un evenement WebSocket
                event_type_map = {
                    "completed": EventType.DEPLOYMENT_COMPLETED,
                    "failed": EventType.DEPLOYMENT_FAILED,
                    "progress": EventType.DEPLOYMENT_PROGRESS,
                }
                ws_event_type = event_type_map.get(
                    callback_data.status, EventType.DEPLOYMENT_PROGRESS
                )
                await emit_deployment_event(
                    deployment_id=str(deployment.id),
                    event_type=ws_event_type,
                    data={
                        "vm_name": callback_data.hostname,
                        "status": callback_data.status,
                        "step": callback_data.step,
                        "progress": callback_data.progress,
                        "message": callback_data.message,
                        "ip": callback_data.ip,
                    },
                )
            else:
                logger.warning(
                    "callback_no_matching_deployment",
                    hostname=callback_data.hostname,
                    deployment_id=callback_data.deployment_id,
                )
    except Exception as e:
        logger.error(
            "callback_processing_error",
            hostname=callback_data.hostname,
            error=str(e),
            exc_info=True,
        )


# =============================================================================
# Routes
# =============================================================================


@router.post("/vm", response_model=CallbackResponse)
async def receive_vm_callback(
    callback: VMCallbackRequest,
    background_tasks: BackgroundTasks,
    token: str = Depends(verify_callback_token),
) -> CallbackResponse:
    """
    Reçoit un callback d'une VM après installation.
    
    Cette route est appelée par les scripts d'installation automatique
    dans les templates (unattend.xml, kickstart, preseed, cloud-init).
    
    Args:
        callback: Données du callback
        background_tasks: Tâches en arrière-plan
    
    Returns:
        Confirmation de réception
    """
    logger.info(
        "vm_callback_received",
        hostname=callback.hostname,
        status=callback.status,
        ip=callback.ip,
        deployment_id=callback.deployment_id,
    )
    
    # Stocker le callback
    store_callback(callback.hostname, callback.model_dump())
    
    # Traiter le callback en arrière-plan
    background_tasks.add_task(process_callback, callback)
    
    return CallbackResponse(
        timestamp=datetime.now(timezone.utc),
        message=f"Callback received for {callback.hostname}",
    )


@router.get("/vm/{hostname}")
async def get_vm_callbacks(hostname: str, current_user: CurrentUser) -> dict[str, Any]:
    """
    Récupère tous les callbacks reçus pour un hostname.
    
    Args:
        hostname: Nom de la machine
    
    Returns:
        Liste des callbacks
    """
    callbacks = get_callbacks(hostname)
    
    return {
        "hostname": hostname,
        "callbacks": callbacks,
        "count": len(callbacks),
    }


@router.delete("/vm/{hostname}")
async def delete_vm_callbacks(hostname: str, current_user: CurrentUser) -> dict[str, Any]:
    """
    Supprime les callbacks d'un hostname.
    
    Args:
        hostname: Nom de la machine
    
    Returns:
        Nombre de callbacks supprimés
    """
    count = clear_callbacks(hostname)
    
    logger.info("vm_callbacks_cleared", hostname=hostname, count=count)
    
    return {
        "hostname": hostname,
        "deleted_count": count,
    }


@router.get("/pending")
async def list_pending_callbacks(current_user: CurrentUser) -> dict[str, Any]:
    """
    Liste tous les hostnames avec des callbacks en attente.
    
    Returns:
        Liste des hostnames et nombre de callbacks
    """
    pending = {
        hostname: len(callbacks)
        for hostname, callbacks in _callbacks_store.items()
    }
    
    return {
        "pending_hosts": pending,
        "total_hosts": len(pending),
        "total_callbacks": sum(pending.values()),
    }


@router.post("/vm/{hostname}/complete")
async def mark_installation_complete(
    hostname: str,
    current_user: CurrentUser,
    deployment_id: str | None = None,
) -> dict[str, Any]:
    """
    Marque manuellement une installation comme complète.
    
    Utile si le callback automatique a échoué.
    
    Args:
        hostname: Nom de la machine
        deployment_id: ID du déploiement (optionnel)
    
    Returns:
        Confirmation
    """
    callback = VMCallbackRequest(
        hostname=hostname,
        status="completed",
        deployment_id=deployment_id,
        message="Marked complete manually",
    )
    
    store_callback(hostname, callback.model_dump())
    
    logger.info(
        "vm_marked_complete_manually",
        hostname=hostname,
        deployment_id=deployment_id,
    )
    
    return {
        "hostname": hostname,
        "status": "completed",
        "message": "Installation marked as complete",
    }
