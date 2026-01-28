# =============================================================================
# VM Automation - WebSocket Manager
# =============================================================================
"""
Gestionnaire WebSocket pour les communications temps réel.
Broadcast des événements de déploiement, statuts VM, etc.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from src.common.logging import get_logger

logger = get_logger(__name__)


class EventType(str, Enum):
    """Types d'événements WebSocket."""
    # Déploiements
    DEPLOYMENT_CREATED = "deployment.created"
    DEPLOYMENT_STARTED = "deployment.started"
    DEPLOYMENT_PROGRESS = "deployment.progress"
    DEPLOYMENT_STEP_COMPLETED = "deployment.step_completed"
    DEPLOYMENT_COMPLETED = "deployment.completed"
    DEPLOYMENT_FAILED = "deployment.failed"
    DEPLOYMENT_CANCELLED = "deployment.cancelled"
    
    # VMs
    VM_CREATED = "vm.created"
    VM_STARTED = "vm.started"
    VM_STOPPED = "vm.stopped"
    VM_DELETED = "vm.deleted"
    VM_STATE_CHANGED = "vm.state_changed"
    
    # Hyperviseurs
    HYPERVISOR_CONNECTED = "hypervisor.connected"
    HYPERVISOR_DISCONNECTED = "hypervisor.disconnected"
    HYPERVISOR_ERROR = "hypervisor.error"
    
    # Système
    SYSTEM_NOTIFICATION = "system.notification"
    SYSTEM_ERROR = "system.error"


@dataclass
class WebSocketEvent:
    """Structure d'un événement WebSocket."""
    event_type: EventType
    data: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    event_id: str = field(default_factory=lambda: str(uuid4()))
    
    def to_json(self) -> str:
        """Sérialise l'événement en JSON."""
        return json.dumps({
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "data": self.data,
            "timestamp": self.timestamp,
        })
    
    def to_dict(self) -> dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "data": self.data,
            "timestamp": self.timestamp,
        }


@dataclass
class WebSocketClient:
    """Représente un client WebSocket connecté."""
    websocket: WebSocket
    client_id: str
    connected_at: datetime = field(default_factory=datetime.utcnow)
    subscriptions: set[str] = field(default_factory=set)  # Event types to subscribe
    user_id: str | None = None
    
    async def send(self, event: WebSocketEvent) -> bool:
        """Envoie un événement au client."""
        try:
            if self.websocket.client_state == WebSocketState.CONNECTED:
                await self.websocket.send_text(event.to_json())
                return True
        except Exception as e:
            logger.warning(
                "websocket_send_failed",
                client_id=self.client_id,
                error=str(e),
            )
        return False


class WebSocketManager:
    """
    Gestionnaire central des connexions WebSocket.
    
    Gère :
    - Connexions/déconnexions clients
    - Broadcast d'événements
    - Subscriptions par type d'événement
    - Rooms pour les déploiements spécifiques
    """
    
    _instance: "WebSocketManager | None" = None
    
    def __new__(cls) -> "WebSocketManager":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        if self._initialized:
            return
        
        self._clients: dict[str, WebSocketClient] = {}
        self._rooms: dict[str, set[str]] = {}  # room_id -> set of client_ids
        self._event_handlers: dict[EventType, list[Callable]] = {}
        self._initialized = True
        
        logger.info("websocket_manager_initialized")
    
    @property
    def client_count(self) -> int:
        """Nombre de clients connectés."""
        return len(self._clients)
    
    async def connect(
        self,
        websocket: WebSocket,
        client_id: str | None = None,
        user_id: str | None = None,
    ) -> WebSocketClient:
        """
        Accepte une nouvelle connexion WebSocket.
        
        Args:
            websocket: Instance WebSocket FastAPI
            client_id: ID du client (généré si None)
            user_id: ID utilisateur optionnel
            
        Returns:
            Client WebSocket créé
        """
        await websocket.accept()
        
        client_id = client_id or str(uuid4())
        client = WebSocketClient(
            websocket=websocket,
            client_id=client_id,
            user_id=user_id,
        )
        
        self._clients[client_id] = client
        
        logger.info(
            "websocket_client_connected",
            client_id=client_id,
            user_id=user_id,
            total_clients=self.client_count,
        )
        
        # Envoyer un message de bienvenue
        welcome_event = WebSocketEvent(
            event_type=EventType.SYSTEM_NOTIFICATION,
            data={
                "message": "Connected to VM Automation WebSocket",
                "client_id": client_id,
            },
        )
        await client.send(welcome_event)
        
        return client
    
    async def disconnect(self, client_id: str) -> None:
        """
        Déconnecte un client.
        
        Args:
            client_id: ID du client à déconnecter
        """
        if client_id not in self._clients:
            return
        
        client = self._clients.pop(client_id)
        
        # Retirer de toutes les rooms
        for room_id, members in list(self._rooms.items()):
            members.discard(client_id)
            if not members:
                del self._rooms[room_id]
        
        logger.info(
            "websocket_client_disconnected",
            client_id=client_id,
            total_clients=self.client_count,
        )
    
    async def broadcast(
        self,
        event: WebSocketEvent,
        exclude: set[str] | None = None,
    ) -> int:
        """
        Envoie un événement à tous les clients connectés.
        
        Args:
            event: Événement à envoyer
            exclude: IDs de clients à exclure
            
        Returns:
            Nombre de clients ayant reçu l'événement
        """
        exclude = exclude or set()
        sent_count = 0
        failed_clients: list[str] = []
        
        for client_id, client in list(self._clients.items()):
            if client_id in exclude:
                continue
            
            # Vérifier si le client est abonné à ce type d'événement
            if client.subscriptions and event.event_type.value not in client.subscriptions:
                continue
            
            success = await client.send(event)
            if success:
                sent_count += 1
            else:
                failed_clients.append(client_id)
        
        # Nettoyer les clients déconnectés
        for client_id in failed_clients:
            await self.disconnect(client_id)
        
        logger.debug(
            "websocket_broadcast",
            event_type=event.event_type.value,
            sent_count=sent_count,
            failed_count=len(failed_clients),
        )
        
        return sent_count
    
    async def send_to_client(
        self,
        client_id: str,
        event: WebSocketEvent,
    ) -> bool:
        """
        Envoie un événement à un client spécifique.
        
        Args:
            client_id: ID du client
            event: Événement à envoyer
            
        Returns:
            True si envoyé avec succès
        """
        client = self._clients.get(client_id)
        if not client:
            return False
        
        return await client.send(event)
    
    async def send_to_room(
        self,
        room_id: str,
        event: WebSocketEvent,
    ) -> int:
        """
        Envoie un événement à tous les clients d'une room.
        
        Args:
            room_id: ID de la room
            event: Événement à envoyer
            
        Returns:
            Nombre de clients ayant reçu l'événement
        """
        if room_id not in self._rooms:
            return 0
        
        sent_count = 0
        for client_id in list(self._rooms[room_id]):
            if await self.send_to_client(client_id, event):
                sent_count += 1
        
        return sent_count
    
    def join_room(self, client_id: str, room_id: str) -> bool:
        """
        Ajoute un client à une room.
        
        Args:
            client_id: ID du client
            room_id: ID de la room
            
        Returns:
            True si ajouté avec succès
        """
        if client_id not in self._clients:
            return False
        
        if room_id not in self._rooms:
            self._rooms[room_id] = set()
        
        self._rooms[room_id].add(client_id)
        
        logger.debug(
            "websocket_joined_room",
            client_id=client_id,
            room_id=room_id,
        )
        
        return True
    
    def leave_room(self, client_id: str, room_id: str) -> bool:
        """
        Retire un client d'une room.
        
        Args:
            client_id: ID du client
            room_id: ID de la room
            
        Returns:
            True si retiré avec succès
        """
        if room_id not in self._rooms:
            return False
        
        self._rooms[room_id].discard(client_id)
        
        if not self._rooms[room_id]:
            del self._rooms[room_id]
        
        logger.debug(
            "websocket_left_room",
            client_id=client_id,
            room_id=room_id,
        )
        
        return True
    
    def subscribe(self, client_id: str, event_types: list[str]) -> bool:
        """
        Abonne un client à des types d'événements spécifiques.
        
        Args:
            client_id: ID du client
            event_types: Liste des types d'événements
            
        Returns:
            True si abonné avec succès
        """
        client = self._clients.get(client_id)
        if not client:
            return False
        
        client.subscriptions.update(event_types)
        return True
    
    def unsubscribe(self, client_id: str, event_types: list[str]) -> bool:
        """
        Désabonne un client de types d'événements.
        
        Args:
            client_id: ID du client
            event_types: Liste des types d'événements
            
        Returns:
            True si désabonné avec succès
        """
        client = self._clients.get(client_id)
        if not client:
            return False
        
        client.subscriptions.difference_update(event_types)
        return True
    
    def get_stats(self) -> dict[str, Any]:
        """Retourne les statistiques du manager."""
        return {
            "total_clients": self.client_count,
            "total_rooms": len(self._rooms),
            "rooms": {
                room_id: len(members)
                for room_id, members in self._rooms.items()
            },
        }


# Instance singleton globale
ws_manager = WebSocketManager()


# ============================================================================
# Helper functions pour émettre des événements
# ============================================================================

async def emit_deployment_event(
    deployment_id: str,
    event_type: EventType,
    data: dict[str, Any],
) -> None:
    """
    Émet un événement de déploiement.
    
    Args:
        deployment_id: ID du déploiement
        event_type: Type d'événement
        data: Données de l'événement
    """
    event = WebSocketEvent(
        event_type=event_type,
        data={
            "deployment_id": deployment_id,
            **data,
        },
    )
    
    # Broadcast à tous + room spécifique au déploiement
    await ws_manager.broadcast(event)
    await ws_manager.send_to_room(f"deployment:{deployment_id}", event)


async def emit_vm_event(
    vm_id: str,
    event_type: EventType,
    data: dict[str, Any],
) -> None:
    """
    Émet un événement VM.
    
    Args:
        vm_id: ID de la VM
        event_type: Type d'événement
        data: Données de l'événement
    """
    event = WebSocketEvent(
        event_type=event_type,
        data={
            "vm_id": vm_id,
            **data,
        },
    )
    
    await ws_manager.broadcast(event)


async def emit_system_notification(
    message: str,
    level: str = "info",
    data: dict[str, Any] | None = None,
) -> None:
    """
    Émet une notification système.
    
    Args:
        message: Message de notification
        level: Niveau (info, warning, error)
        data: Données additionnelles
    """
    event = WebSocketEvent(
        event_type=EventType.SYSTEM_NOTIFICATION,
        data={
            "message": message,
            "level": level,
            **(data or {}),
        },
    )
    
    await ws_manager.broadcast(event)


async def emit_notification(
    title: str,
    message: str,
    notification_type: str = "info",
    data: dict[str, Any] | None = None,
) -> None:
    """
    Émet une notification (alias pour emit_system_notification avec titre).
    
    Args:
        title: Titre de la notification
        message: Message de notification
        notification_type: Type (info, warning, error, success)
        data: Données additionnelles
    """
    await emit_system_notification(
        message=f"{title}: {message}" if title else message,
        level=notification_type,
        data={"title": title, **(data or {})},
    )
