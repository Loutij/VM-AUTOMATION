# =============================================================================
# VM Automation - Guacamole WebSocket Proxy Router
# =============================================================================
"""
Guacamole WebSocket proxy for RDP/VNC access to VMs.

Uses guacd (Apache Guacamole protocol daemon) to proxy
RDP connections to Windows VMs and VNC to Linux VMs.
"""

import asyncio
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState

from src.common.auth import verify_ws_token
from src.common.database import db_session
from src.common.logging import get_logger
from src.domain.models import OSFamily
from src.domain.vm_service import VMService

logger = get_logger(__name__)

router = APIRouter()

GUACD_HOST = "guacd"
GUACD_PORT = 4822

# Active Guacamole proxy sessions (vm_id -> GuacamoleClient)
_guac_sessions: dict[str, "GuacamoleClient"] = {}


def _is_ws_open(ws: WebSocket) -> bool:
    """Check if WebSocket is still open."""
    try:
        return ws.client_state == WebSocketState.CONNECTED
    except Exception:
        return False


class GuacamoleClient:
    """Minimal Guacamole protocol client for guacd communication."""

    def __init__(self):
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self.running = False

    async def connect(self, host: str = GUACD_HOST, port: int = GUACD_PORT) -> bool:
        """Connect to guacd."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=10.0,
            )
            self.running = True
            return True
        except Exception as e:
            logger.error("guacd_connection_failed", error=str(e))
            return False

    def _encode_instruction(self, *args: str) -> bytes:
        """Encode a Guacamole protocol instruction."""
        parts = []
        for arg in args:
            encoded = str(arg)
            parts.append(f"{len(encoded)}.{encoded}")
        return (",".join(parts) + ";").encode("utf-8")

    def _decode_instruction(self, data: bytes) -> list[str]:
        """Decode a Guacamole protocol instruction."""
        text = data.decode("utf-8", errors="replace").rstrip(";")
        parts = []
        while text:
            dot_pos = text.find(".")
            if dot_pos < 0:
                break
            length = int(text[:dot_pos])
            value = text[dot_pos + 1:dot_pos + 1 + length]
            parts.append(value)
            text = text[dot_pos + 1 + length:]
            if text.startswith(","):
                text = text[1:]
        return parts

    async def handshake_rdp(
        self,
        hostname: str,
        port: int = 3389,
        username: str = "",
        password: str = "",
        width: int = 1280,
        height: int = 720,
        dpi: int = 96,
        security: str = "any",
        ignore_cert: bool = True,
    ) -> bool:
        """Perform Guacamole handshake for RDP connection."""
        if not self._writer or not self._reader:
            return False

        # Send select instruction
        self._writer.write(self._encode_instruction("select", "rdp"))
        await self._writer.drain()

        # Read args instruction
        data = await asyncio.wait_for(self._reader.read(4096), timeout=10)
        args = self._decode_instruction(data)

        if not args or args[0] != "args":
            return False

        # Build connect instruction with RDP parameters
        connect_args = {
            "hostname": hostname,
            "port": str(port),
            "username": username,
            "password": password,
            "width": str(width),
            "height": str(height),
            "dpi": str(dpi),
            "security": security,
            "ignore-cert": "true" if ignore_cert else "false",
            "resize-method": "reconnect",
            "enable-wallpaper": "false",
            "enable-font-smoothing": "true",
        }

        # Map args to connect params
        param_values = []
        for arg_name in args[1:]:
            param_values.append(connect_args.get(arg_name, ""))

        self._writer.write(self._encode_instruction("connect", *param_values))
        await self._writer.drain()

        # Read ready instruction
        data = await asyncio.wait_for(self._reader.read(4096), timeout=10)
        ready = self._decode_instruction(data)

        return bool(ready) and ready[0] == "ready"

    async def handshake_vnc(
        self,
        hostname: str,
        port: int = 5900,
        password: str = "",
        width: int = 1280,
        height: int = 720,
    ) -> bool:
        """Perform Guacamole handshake for VNC connection."""
        if not self._writer or not self._reader:
            return False

        self._writer.write(self._encode_instruction("select", "vnc"))
        await self._writer.drain()

        data = await asyncio.wait_for(self._reader.read(4096), timeout=10)
        args = self._decode_instruction(data)

        if not args or args[0] != "args":
            return False

        connect_args = {
            "hostname": hostname,
            "port": str(port),
            "password": password,
            "width": str(width),
            "height": str(height),
        }

        param_values = []
        for arg_name in args[1:]:
            param_values.append(connect_args.get(arg_name, ""))

        self._writer.write(self._encode_instruction("connect", *param_values))
        await self._writer.drain()

        data = await asyncio.wait_for(self._reader.read(4096), timeout=10)
        ready = self._decode_instruction(data)

        return bool(ready) and ready[0] == "ready"

    async def relay_to_ws(self, websocket: WebSocket):
        """Relay guacd data to WebSocket."""
        try:
            while self.running and self._reader:
                data = await asyncio.wait_for(
                    self._reader.read(65536),
                    timeout=60.0,
                )
                if not data:
                    break
                if _is_ws_open(websocket):
                    await websocket.send_text(data.decode("utf-8", errors="replace"))
        except asyncio.TimeoutError:
            pass  # Timeout is normal, connection may be idle
        except WebSocketDisconnect:
            logger.debug("guac_ws_disconnected")
        except Exception as e:
            logger.warning("guac_to_ws_error", error=str(e))
        finally:
            self.running = False

    async def relay_from_ws(self, websocket: WebSocket):
        """Relay WebSocket data to guacd."""
        try:
            while self.running and self._writer:
                text = await websocket.receive_text()
                if self._writer and not self._writer.is_closing():
                    self._writer.write(text.encode("utf-8"))
                    await self._writer.drain()
        except WebSocketDisconnect:
            logger.debug("guac_ws_from_disconnected")
        except Exception as e:
            logger.warning("guac_from_ws_error", error=str(e))
        finally:
            self.running = False

    async def close(self):
        """Close guacd connection."""
        self.running = False
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None


@router.websocket("/ws/{vm_id}")
async def guacamole_proxy_ws(
    websocket: WebSocket,
    vm_id: str,
    token: str | None = Query(None),
    width: int = Query(1280),
    height: int = Query(720),
):
    """
    Guacamole WebSocket proxy.

    Connects to guacd and relays the Guacamole protocol to the browser.
    Automatically selects RDP for Windows VMs or VNC for Linux VMs.

    Query params:
    - token: JWT access token for authentication
    - width: Display width in pixels (default 1280)
    - height: Display height in pixels (default 720)
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

    # Fetch VM and determine protocol based on OS family
    try:
        async with db_session() as db:
            service = VMService(db)
            vm = await service.get_vm(vm_uuid)
            vm_ip = vm.ip_address
            os_family = vm.os_template.os_family if vm.os_template else None
    except Exception as e:
        logger.warning("guac_vm_lookup_failed", vm_id=vm_id, error=str(e))
        await websocket.close(code=1008, reason="VM not found")
        return

    if not vm_ip:
        await websocket.close(code=1008, reason="VM has no IP address")
        return

    # Accept WebSocket
    await websocket.accept()

    # Evict any existing session for this VM
    old_session = _guac_sessions.pop(vm_id, None)
    if old_session:
        logger.info("guac_evicting_previous", vm_id=vm_id)
        await old_session.close()

    # Create Guacamole client
    guac = GuacamoleClient()
    _guac_sessions[vm_id] = guac

    try:
        if not await guac.connect():
            await websocket.send_text(
                "5.error,21.guacd_unavailable,3.519;"
            )
            await websocket.close(code=1011, reason="guacd unavailable")
            return

        # Select protocol based on OS
        if os_family == OSFamily.WINDOWS:
            success = await guac.handshake_rdp(
                hostname=vm_ip,
                username="otoroot",
                password="tooroto",
                width=width,
                height=height,
            )
            protocol = "rdp"
        else:
            success = await guac.handshake_vnc(
                hostname=vm_ip,
                password="tooroto",
                width=width,
                height=height,
            )
            protocol = "vnc"

        if not success:
            await websocket.send_text(
                "5.error,18.handshake_failed,3.519;"
            )
            await websocket.close(code=1011, reason="Guacamole handshake failed")
            return

        logger.info(
            "guac_session_started",
            vm_id=vm_id,
            vm_ip=vm_ip,
            protocol=protocol,
            width=width,
            height=height,
        )

        # Run bidirectional relay
        await asyncio.gather(
            guac.relay_to_ws(websocket),
            guac.relay_from_ws(websocket),
            return_exceptions=True,
        )

    except Exception as e:
        logger.error("guac_proxy_error", vm_id=vm_id, error=str(e))
    finally:
        await guac.close()
        _guac_sessions.pop(vm_id, None)
        try:
            if _is_ws_open(websocket):
                await websocket.close()
        except Exception:
            pass
        logger.info("guac_session_ended", vm_id=vm_id)


@router.get("/sessions")
async def list_guacamole_sessions():
    """List active Guacamole proxy sessions (for debugging/monitoring)."""
    return {
        "sessions": [
            {
                "vm_id": vm_id,
                "running": client.running,
            }
            for vm_id, client in _guac_sessions.items()
        ]
    }
