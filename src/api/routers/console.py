# =============================================================================
# VM Automation - VM Console WebSocket Router
# =============================================================================
"""
Router WebSocket pour la console VM interactive.
Screenshots WMI + clavier via Msvm_Keyboard.
"""

import asyncio
import hashlib
import json
import time
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState

from src.common.auth import verify_ws_token
from src.common.database import db_session
from src.common.logging import get_logger
from src.domain.vm_service import VMService
from src.integrations.hypervisors import HyperVClient

logger = get_logger(__name__)

router = APIRouter()

# Track active console sessions (1 per VM)
_active_consoles: dict[str, str] = {}  # vm_id -> client_id


def _is_ws_open(ws: WebSocket) -> bool:
    """Check if WebSocket is still open."""
    try:
        return ws.client_state == WebSocketState.CONNECTED
    except Exception:
        return False


@router.websocket("/ws/{vm_id}")
async def vm_console_ws(
    websocket: WebSocket,
    vm_id: str,
    token: str | None = Query(None),
):
    """
    WebSocket endpoint for VM console.
    Sends binary PNG frames, receives JSON keyboard input.

    Query params:
    - token: JWT access token for authentication
    """
    # Verify authentication before accepting connection
    user = await verify_ws_token(token)
    if not user:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    await websocket.accept()

    # If a console is already active for this VM, evict it (new session wins)
    if vm_id in _active_consoles:
        logger.info("console_evicting_previous", vm_id=vm_id)
        _active_consoles.pop(vm_id, None)

    client_id = str(id(websocket))
    _active_consoles[vm_id] = client_id

    # Resolve the VM and its hypervisor, then build the HyperVClient
    client: HyperVClient | None = None
    try:
        # Convert string vm_id to UUID
        try:
            vm_uuid = UUID(vm_id)
        except ValueError:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": f"Invalid VM ID format: {vm_id}",
            }))
            await websocket.close()
            _active_consoles.pop(vm_id, None)
            return

        async with db_session() as db:
            service = VMService(db)
            vm = await service.get_vm(vm_uuid)

            if not vm.hypervisor_id:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "VM has no associated hypervisor",
                }))
                await websocket.close()
                _active_consoles.pop(vm_id, None)
                return

            hypervisor = await service.get_hypervisor(vm.hypervisor_id)

        client = HyperVClient(
            host=hypervisor.host,
            username=hypervisor.username,
            password=hypervisor.password,
            use_ssl=hypervisor.use_ssl,
        )
        # Use the Hyper-V identifier (GUID) when available, otherwise the VM name
        vm_identifier = vm.hypervisor_vm_id or vm.name
    except Exception as e:
        logger.error("console_init_failed", vm_id=vm_id, error=str(e))
        try:
            if _is_ws_open(websocket):
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Failed to initialise console: {e}",
                }))
                await websocket.close()
        except Exception:
            pass
        _active_consoles.pop(vm_id, None)
        return

    try:
        await websocket.send_text(json.dumps({
            "type": "connected",
            "vm_id": vm_id,
            "message": "Console connected",
        }))

        # Two concurrent tasks: frame producer + input consumer
        last_hash: bytes | None = None
        last_input_time = time.time()
        running = True

        async def frame_producer():
            nonlocal last_hash, running

            while running:
                try:
                    if not _is_ws_open(websocket):
                        running = False
                        break

                    # Adaptive FPS: 5 FPS if recent input, 1 FPS if idle >5s
                    idle_time = time.time() - last_input_time
                    fps = 5 if idle_time < 5 else 1
                    interval = 1.0 / fps

                    # get_vm_screenshot_bytes returns raw PNG bytes
                    t_start = time.monotonic()
                    png_bytes = await client.get_vm_screenshot_bytes(
                        vm_identifier, 800, 600,
                    )
                    elapsed = time.monotonic() - t_start

                    if png_bytes and _is_ws_open(websocket):
                        # Delta detection -- skip if frame is identical
                        frame_hash = hashlib.md5(png_bytes).digest()
                        if frame_hash != last_hash:
                            last_hash = frame_hash
                            await websocket.send_bytes(png_bytes)

                    # Sleep only the remaining time to hit target FPS
                    remaining = interval - elapsed
                    if remaining > 0:
                        await asyncio.sleep(remaining)
                except (WebSocketDisconnect, RuntimeError):
                    running = False
                    break
                except Exception as e:
                    logger.warning(
                        "console_frame_error", vm_id=vm_id, error=str(e),
                    )
                    await asyncio.sleep(1)

        async def input_consumer():
            nonlocal last_input_time, running

            # Throttle mouse moves: skip if a move is already in progress
            mouse_move_in_progress = False

            while running:
                try:
                    data = await websocket.receive_text()
                    msg = json.loads(data)
                    last_input_time = time.time()

                    if msg.get("type") == "key":
                        scancode = msg.get("scancode")
                        action = msg.get("action", "type")
                        if scancode is not None:
                            if action == "press":
                                await client.press_key(vm_identifier, scancode)
                            elif action == "release":
                                await client.release_key(vm_identifier, scancode)
                            else:
                                await client.send_key(vm_identifier, scancode)

                    elif msg.get("type") == "text":
                        text = msg.get("value", "")
                        if text:
                            await client.type_text(vm_identifier, text)

                    elif msg.get("type") == "mouse_click":
                        x = float(msg.get("x", 0))
                        y = float(msg.get("y", 0))
                        button = int(msg.get("button", 1))
                        await client.click_mouse(
                            vm_identifier, x, y, button,
                        )

                    elif msg.get("type") == "mouse_move":
                        x = msg.get("x")
                        y = msg.get("y")
                        if x is not None and y is not None and not mouse_move_in_progress:
                            mouse_move_in_progress = True
                            try:
                                await client.move_mouse(
                                    vm_identifier, float(x), float(y),
                                )
                            finally:
                                mouse_move_in_progress = False

                except (WebSocketDisconnect, RuntimeError):
                    running = False
                    break
                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    logger.warning(
                        "console_input_error", vm_id=vm_id, error=str(e),
                    )

        # Run both tasks concurrently
        await asyncio.gather(
            frame_producer(),
            input_consumer(),
            return_exceptions=True,
        )

    finally:
        _active_consoles.pop(vm_id, None)
        if client:
            client.close()
        logger.info("console_disconnected", vm_id=vm_id)
