# =============================================================================
# VM Automation - Realtime Routes (WebSocket & SSE)
# =============================================================================
"""
Routes pour les communications temps réel.
- WebSocket pour les mises à jour bidirectionnelles
- SSE (Server-Sent Events) comme fallback
- Stats dashboard en temps réel
"""

import asyncio
import json
from datetime import datetime
from typing import Any, AsyncGenerator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.websocket import (
    EventType,
    WebSocketEvent,
    ws_manager,
    emit_system_notification,
)
from src.api.dependencies import get_db_session as get_db
from src.common.logging import get_logger
from src.domain.models import (
    Deployment,
    DeploymentStatus,
    Hypervisor,
    VirtualMachine,
    VMStatus,
    OSTemplate,
)

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# WebSocket Endpoint
# =============================================================================

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: str | None = Query(None),
):
    """
    Point d'entrée WebSocket principal.
    
    Protocole de messages:
    - {"action": "subscribe", "events": ["deployment.*", "vm.*"]}
    - {"action": "unsubscribe", "events": ["deployment.*"]}
    - {"action": "join_room", "room": "deployment:123"}
    - {"action": "leave_room", "room": "deployment:123"}
    - {"action": "ping"} -> {"action": "pong"}
    """
    client = await ws_manager.connect(websocket, client_id)
    
    try:
        while True:
            # Recevoir les messages du client
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                action = message.get("action")
                
                if action == "ping":
                    await client.send(WebSocketEvent(
                        event_type=EventType.SYSTEM_NOTIFICATION,
                        data={"action": "pong", "timestamp": datetime.utcnow().isoformat()},
                    ))
                
                elif action == "subscribe":
                    events = message.get("events", [])
                    ws_manager.subscribe(client.client_id, events)
                    await client.send(WebSocketEvent(
                        event_type=EventType.SYSTEM_NOTIFICATION,
                        data={"action": "subscribed", "events": events},
                    ))
                
                elif action == "unsubscribe":
                    events = message.get("events", [])
                    ws_manager.unsubscribe(client.client_id, events)
                    await client.send(WebSocketEvent(
                        event_type=EventType.SYSTEM_NOTIFICATION,
                        data={"action": "unsubscribed", "events": events},
                    ))
                
                elif action == "join_room":
                    room = message.get("room")
                    if room:
                        ws_manager.join_room(client.client_id, room)
                        await client.send(WebSocketEvent(
                            event_type=EventType.SYSTEM_NOTIFICATION,
                            data={"action": "joined_room", "room": room},
                        ))
                
                elif action == "leave_room":
                    room = message.get("room")
                    if room:
                        ws_manager.leave_room(client.client_id, room)
                        await client.send(WebSocketEvent(
                            event_type=EventType.SYSTEM_NOTIFICATION,
                            data={"action": "left_room", "room": room},
                        ))
                
                else:
                    await client.send(WebSocketEvent(
                        event_type=EventType.SYSTEM_ERROR,
                        data={"error": f"Unknown action: {action}"},
                    ))
                    
            except json.JSONDecodeError:
                await client.send(WebSocketEvent(
                    event_type=EventType.SYSTEM_ERROR,
                    data={"error": "Invalid JSON message"},
                ))
                
    except WebSocketDisconnect:
        await ws_manager.disconnect(client.client_id)
    except Exception as e:
        logger.error(
            "websocket_error",
            client_id=client.client_id,
            error=str(e),
            exc_info=True,
        )
        await ws_manager.disconnect(client.client_id)


# =============================================================================
# Server-Sent Events (SSE) Fallback
# =============================================================================

async def event_generator(
    event_types: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Générateur d'événements SSE.
    
    Args:
        event_types: Types d'événements à écouter (tous si None)
    """
    # Créer une queue pour recevoir les événements
    queue: asyncio.Queue[WebSocketEvent] = asyncio.Queue()
    client_id = f"sse-{datetime.utcnow().timestamp()}"
    
    # Handler pour ajouter les événements à la queue
    async def event_handler(event: WebSocketEvent) -> None:
        if event_types is None or event.event_type.value in event_types:
            await queue.put(event)
    
    # S'enregistrer pour recevoir les événements (via polling)
    try:
        # Envoyer un événement de connexion
        yield f"event: connected\ndata: {json.dumps({'client_id': client_id})}\n\n"
        
        # Boucle principale avec heartbeat
        heartbeat_interval = 30  # secondes
        last_heartbeat = datetime.utcnow()
        
        while True:
            try:
                # Attendre un événement avec timeout pour le heartbeat
                event = await asyncio.wait_for(
                    queue.get(),
                    timeout=heartbeat_interval,
                )
                
                # Formater l'événement SSE
                yield f"event: {event.event_type.value}\ndata: {event.to_json()}\n\n"
                
            except asyncio.TimeoutError:
                # Envoyer un heartbeat
                now = datetime.utcnow()
                yield f"event: heartbeat\ndata: {json.dumps({'timestamp': now.isoformat()})}\n\n"
                last_heartbeat = now
                
    except asyncio.CancelledError:
        logger.debug("sse_connection_closed", client_id=client_id)
        raise


@router.get("/sse")
async def sse_endpoint(
    events: str | None = Query(None, description="Comma-separated event types to subscribe"),
):
    """
    Endpoint Server-Sent Events pour les clients ne supportant pas WebSocket.
    
    Query params:
    - events: Types d'événements séparés par des virgules (ex: "deployment.*,vm.*")
    """
    event_types = events.split(",") if events else None
    
    return StreamingResponse(
        event_generator(event_types),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Désactive le buffering nginx
        },
    )


# =============================================================================
# Dashboard Stats
# =============================================================================

@router.get("/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Récupère les statistiques du dashboard en temps réel.
    
    Returns:
        Statistiques agrégées pour le dashboard
    """
    try:
        # Compter les hyperviseurs
        hypervisor_result = await db.execute(
            select(func.count()).select_from(Hypervisor)
        )
        total_hypervisors = hypervisor_result.scalar() or 0
        
        # Compter les VMs par statut
        vm_counts = {}
        for status in VMStatus:
            result = await db.execute(
                select(func.count())
                .select_from(VirtualMachine)
                .where(VirtualMachine.status == status)
            )
            vm_counts[status.value] = result.scalar() or 0
        
        total_vms = sum(vm_counts.values())
        
        # Compter les templates
        template_result = await db.execute(
            select(func.count()).select_from(OSTemplate)
        )
        total_templates = template_result.scalar() or 0
        
        # Compter les déploiements par statut
        deployment_counts = {}
        for status in DeploymentStatus:
            result = await db.execute(
                select(func.count())
                .select_from(Deployment)
                .where(Deployment.status == status)
            )
            deployment_counts[status.value] = result.scalar() or 0
        
        total_deployments = sum(deployment_counts.values())
        
        # Déploiements récents (dernières 24h)
        from datetime import timedelta
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        recent_result = await db.execute(
            select(func.count())
            .select_from(Deployment)
            .where(Deployment.created_at >= yesterday)
        )
        recent_deployments = recent_result.scalar() or 0
        
        # Taux de succès des déploiements
        completed = deployment_counts.get("completed", 0)
        failed = deployment_counts.get("failed", 0)
        total_finished = completed + failed
        success_rate = (completed / total_finished * 100) if total_finished > 0 else 0
        
        # Stats WebSocket
        ws_stats = ws_manager.get_stats()
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "hypervisors": {
                "total": total_hypervisors,
            },
            "virtual_machines": {
                "total": total_vms,
                "by_status": vm_counts,
                "running": vm_counts.get("running", 0),
            },
            "templates": {
                "total": total_templates,
            },
            "deployments": {
                "total": total_deployments,
                "by_status": deployment_counts,
                "recent_24h": recent_deployments,
                "in_progress": deployment_counts.get("in_progress", 0),
                "success_rate": round(success_rate, 1),
            },
            "websocket": ws_stats,
        }
        
    except Exception as e:
        logger.error("dashboard_stats_error", error=str(e), exc_info=True)
        # Retourner des stats vides en cas d'erreur
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "error": "Unable to fetch stats",
            "hypervisors": {"total": 0},
            "virtual_machines": {"total": 0, "by_status": {}, "running": 0},
            "templates": {"total": 0},
            "deployments": {"total": 0, "by_status": {}, "recent_24h": 0, "in_progress": 0, "success_rate": 0},
            "websocket": {"total_clients": 0, "total_rooms": 0, "rooms": {}},
        }


@router.get("/stats/websocket")
async def get_websocket_stats() -> dict[str, Any]:
    """Récupère les statistiques WebSocket."""
    return ws_manager.get_stats()


# =============================================================================
# Test/Debug Endpoints (dev only)
# =============================================================================

@router.post("/test/broadcast")
async def test_broadcast(
    event_type: str = Query(..., description="Event type"),
    message: str = Query("Test message", description="Message content"),
) -> dict[str, Any]:
    """
    Endpoint de test pour broadcaster un événement.
    (À désactiver en production)
    """
    try:
        event_enum = EventType(event_type)
    except ValueError:
        event_enum = EventType.SYSTEM_NOTIFICATION
    
    event = WebSocketEvent(
        event_type=event_enum,
        data={"message": message, "test": True},
    )
    
    sent_count = await ws_manager.broadcast(event)
    
    return {
        "success": True,
        "event_type": event_type,
        "message": message,
        "sent_to_clients": sent_count,
    }
