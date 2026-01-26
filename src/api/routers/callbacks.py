# =============================================================================
# VM Automation - Callback Router
# =============================================================================
"""
Routes pour recevoir les callbacks des VMs après installation.
Permet aux VMs de signaler la fin de leur installation.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel

from src.common.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/callbacks", tags=["Callbacks"])


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
    
    # Si un deployment_id est fourni, mettre à jour le déploiement
    if callback_data.deployment_id:
        # TODO: Implémenter la mise à jour du déploiement en DB
        logger.info(
            "callback_for_deployment",
            deployment_id=callback_data.deployment_id,
            status=callback_data.status,
        )


# =============================================================================
# Routes
# =============================================================================


@router.post("/vm", response_model=CallbackResponse)
async def receive_vm_callback(
    callback: VMCallbackRequest,
    background_tasks: BackgroundTasks,
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
async def get_vm_callbacks(hostname: str) -> dict[str, Any]:
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
async def delete_vm_callbacks(hostname: str) -> dict[str, Any]:
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
async def list_pending_callbacks() -> dict[str, Any]:
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
