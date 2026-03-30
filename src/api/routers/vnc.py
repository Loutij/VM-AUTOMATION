# =============================================================================
# VM Automation - VNC WebSocket Proxy Router
# =============================================================================
"""
VNC WebSocket proxy router.

Proxies WebSocket connections from noVNC frontend to VNC servers
running inside Hyper-V VMs.  Acts as a websockify-style relay:
browser (noVNC) <-> WebSocket <-> TCP (VNC port 5900).
"""

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState

from src.common.auth import verify_ws_token
from src.common.database import db_session
from src.common.logging import get_logger
from src.domain.vm_service import VMService

logger = get_logger(__name__)

router = APIRouter()

# Active VNC proxy sessions (vm_id -> VNCProxySession)
_vnc_sessions: dict[str, "VNCProxySession"] = {}


def _is_ws_open(ws: WebSocket) -> bool:
    """Check if WebSocket is still open."""
    try:
        return ws.client_state == WebSocketState.CONNECTED
    except Exception:
        return False


class VNCProxySession:
    """Manages a WebSocket-to-TCP VNC proxy session."""

    def __init__(self, vm_id: str, vm_ip: str, vnc_port: int = 5900):
        self.vm_id = vm_id
        self.vm_ip = vm_ip
        self.vnc_port = vnc_port
        self.running = False
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def connect_to_vnc(self) -> bool:
        """Establish TCP connection to VNC server in VM."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.vm_ip, self.vnc_port),
                timeout=10.0,
            )
            self.running = True
            logger.info(
                "vnc_connected",
                vm_id=self.vm_id,
                vm_ip=self.vm_ip,
                port=self.vnc_port,
            )
            return True
        except (ConnectionRefusedError, asyncio.TimeoutError, OSError) as e:
            logger.warning(
                "vnc_connection_failed",
                vm_id=self.vm_id,
                vm_ip=self.vm_ip,
                error=str(e),
            )
            return False

    async def close(self):
        """Close VNC TCP connection."""
        self.running = False
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None

    async def relay_ws_to_vnc(self, websocket: WebSocket):
        """Forward WebSocket binary messages to VNC TCP socket."""
        try:
            while self.running:
                data = await websocket.receive_bytes()
                if self._writer and not self._writer.is_closing():
                    self._writer.write(data)
                    await self._writer.drain()
        except WebSocketDisconnect:
            logger.debug("vnc_ws_disconnected", vm_id=self.vm_id)
        except Exception as e:
            logger.warning("vnc_ws_to_tcp_error", vm_id=self.vm_id, error=str(e))
        finally:
            self.running = False

    async def relay_vnc_to_ws(self, websocket: WebSocket):
        """Forward VNC TCP data to WebSocket as binary messages."""
        try:
            while self.running and self._reader:
                data = await asyncio.wait_for(
                    self._reader.read(65536),
                    timeout=60.0,
                )
                if not data:
                    break
                if _is_ws_open(websocket):
                    await websocket.send_bytes(data)
        except asyncio.TimeoutError:
            pass  # Timeout is normal, VNC may be idle
        except WebSocketDisconnect:
            logger.debug("vnc_tcp_ws_disconnected", vm_id=self.vm_id)
        except Exception as e:
            logger.warning("vnc_tcp_to_ws_error", vm_id=self.vm_id, error=str(e))
        finally:
            self.running = False


@router.websocket("/ws/{vm_id}")
async def vnc_proxy_ws(
    websocket: WebSocket,
    vm_id: str,
    token: str | None = Query(None),
    vnc_port: int = Query(5900),
):
    """
    WebSocket endpoint for noVNC proxy.

    Establishes a bidirectional relay between the browser (noVNC)
    and the VNC server running inside the target VM.

    Query params:
    - token: JWT access token for authentication
    - vnc_port: VNC server port (default 5900, range 5900-5999)
    """
    # Verify authentication before accepting connection
    user = await verify_ws_token(token)
    if not user:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    # Validate VM ID format
    try:
        vm_uuid = UUID(vm_id)
    except ValueError:
        await websocket.close(code=1008, reason="Invalid VM ID")
        return

    # Fetch VM and validate it has an IP address
    try:
        async with db_session() as db:
            service = VMService(db)
            vm = await service.get_vm(vm_uuid)
            vm_ip = vm.ip_address
    except Exception as e:
        logger.warning("vnc_vm_lookup_failed", vm_id=vm_id, error=str(e))
        await websocket.close(code=1008, reason="VM not found")
        return

    if not vm_ip:
        await websocket.close(code=1008, reason="VM has no IP address")
        return

    # Validate VNC port range
    if not (5900 <= vnc_port <= 5999):
        vnc_port = 5900

    # Accept WebSocket with binary subprotocol for noVNC
    await websocket.accept(subprotocol="binary")

    # Evict any existing session for this VM
    old_session = _vnc_sessions.pop(vm_id, None)
    if old_session:
        logger.info("vnc_evicting_previous", vm_id=vm_id)
        await old_session.close()

    # Create proxy session
    session = VNCProxySession(vm_id=vm_id, vm_ip=vm_ip, vnc_port=vnc_port)
    _vnc_sessions[vm_id] = session

    try:
        # Connect to VNC server
        if not await session.connect_to_vnc():
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": f"Cannot connect to VNC server at {vm_ip}:{vnc_port}",
            }))
            await websocket.close(code=1011, reason="VNC connection failed")
            return

        # Send connection success notification
        await websocket.send_text(json.dumps({
            "type": "connected",
            "vm_id": vm_id,
            "vm_ip": vm_ip,
            "vnc_port": vnc_port,
        }))

        # Run bidirectional relay
        await asyncio.gather(
            session.relay_ws_to_vnc(websocket),
            session.relay_vnc_to_ws(websocket),
            return_exceptions=True,
        )

    except Exception as e:
        logger.error("vnc_proxy_error", vm_id=vm_id, error=str(e))
    finally:
        await session.close()
        _vnc_sessions.pop(vm_id, None)
        try:
            if _is_ws_open(websocket):
                await websocket.close()
        except Exception:
            pass
        logger.info("vnc_session_ended", vm_id=vm_id)


@router.get("/sessions")
async def list_vnc_sessions():
    """List active VNC proxy sessions (for debugging/monitoring)."""
    return {
        "sessions": [
            {
                "vm_id": s.vm_id,
                "vm_ip": s.vm_ip,
                "vnc_port": s.vnc_port,
                "running": s.running,
            }
            for s in _vnc_sessions.values()
        ]
    }
