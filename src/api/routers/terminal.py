# =============================================================================
# VM Automation - Terminal WebSocket Router
# =============================================================================
"""
WebSocket endpoint for interactive terminal sessions.
Provides PowerShell remoting for Windows VMs and SSH for Linux VMs,
both executed through the hypervisor host via WinRM.
"""

import json
import re
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState

from src.common.auth import verify_ws_token
from src.common.config import settings
from src.common.database import db_session
from src.common.logging import get_logger
from src.domain.vm_service import VMService
from src.integrations.hypervisors import HyperVClient

logger = get_logger(__name__)
router = APIRouter()

# Track active terminal sessions (vm_id -> client_id)
_active_terminals: dict[str, str] = {}

# Regex to strip CLIXML noise from PowerShell stderr
_CLIXML_RE = re.compile(r"#< CLIXML\s*\n?|</?Objs[^>]*>|</?Obj[^>]*>|</?TN[^>]*>|</?T>[^<]*</T>|</?MS>|</?I64[^>]*>[^<]*</I64>|</?PR[^>]*>|</?AV>[^<]*</AV>|</?AI>[^<]*</AI>|<Nil\s*/>|</?PI>[^<]*</PI>|</?PC>[^<]*</PC>|</?SR>[^<]*</SR>|</?SD>[^<]*</SD>|<TNRef[^/]*/?>", re.DOTALL)
_CLIXML_S_RE = re.compile(r'<S S="Error">([^<]*)</S>')
_CLIXML_PROGRESS_RE = re.compile(r'<Obj S="progress"[^>]*>.*?</Obj>', re.DOTALL)


def _clean_clixml(text: str) -> str:
    """Extract readable error text from CLIXML-encoded PowerShell output."""
    if "#< CLIXML" not in text and "<Objs" not in text:
        return text
    # Remove progress objects entirely
    text = _CLIXML_PROGRESS_RE.sub("", text)
    # Extract error strings
    errors = _CLIXML_S_RE.findall(text)
    if errors:
        # Join error fragments and clean up XML escapes
        result = "".join(errors)
        result = result.replace("_x000D__x000A_", "")
        result = result.replace("_x000D_", "").replace("_x000A_", "")
        return result.strip()
    # Fallback: strip all XML tags
    cleaned = re.sub(r"<[^>]+>", "", text)
    cleaned = cleaned.replace("#< CLIXML", "").replace("_x000D__x000A_", "\n")
    return cleaned.strip()


def _is_ws_open(ws: WebSocket) -> bool:
    """Check if a WebSocket connection is still open."""
    try:
        return ws.client_state == WebSocketState.CONNECTED
    except Exception:
        return False


async def _send(ws: WebSocket, data: str) -> None:
    """Send output message to WebSocket."""
    if _is_ws_open(ws):
        await ws.send_text(json.dumps({"type": "output", "data": data}))


@router.websocket("/ws/{vm_id}")
async def vm_terminal_ws(
    websocket: WebSocket,
    vm_id: str,
    token: str | None = Query(None),
):
    """
    WebSocket for interactive terminal (PowerShell/SSH).

    Query params:
    - token: JWT access token for authentication
    """
    # Verify authentication before accepting connection
    user = await verify_ws_token(token)
    if not user:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    await websocket.accept()

    # Evict any stale session for this VM
    _active_terminals.pop(vm_id, None)
    client_id = str(id(websocket))
    _active_terminals[vm_id] = client_id

    client: HyperVClient | None = None
    try:
        # ---- Validate VM ID ----
        try:
            vm_uuid = UUID(vm_id)
        except ValueError:
            await websocket.send_text(
                json.dumps({"type": "error", "message": f"Invalid VM ID: {vm_id}"})
            )
            await websocket.close()
            _active_terminals.pop(vm_id, None)
            return

        # ---- Fetch VM and hypervisor info ----
        async with db_session() as db:
            service = VMService(db)
            vm = await service.get_vm(vm_uuid)
            if not vm.hypervisor_id:
                await websocket.send_text(
                    json.dumps({"type": "error", "message": "VM has no hypervisor"})
                )
                await websocket.close()
                _active_terminals.pop(vm_id, None)
                return
            hypervisor = await service.get_hypervisor(vm.hypervisor_id)

        # ---- Create HyperV client ----
        client = HyperVClient(
            host=hypervisor.host,
            username=hypervisor.username,
            password=hypervisor.password,
            use_ssl=hypervisor.use_ssl,
        )

        vm_ip = vm.ip_address

        # ---- Determine OS family + fetch VM credentials from deployment ----
        os_family = "windows"  # default
        # Default admin user depends on OS locale; fr-FR -> Administrateur
        _locale = settings.default_locale
        vm_admin_user = ".\\otoroot"
        _default_pw = settings.default_admin_password
        vm_admin_password: str = (
            _default_pw.get_secret_value()
            if hasattr(_default_pw, "get_secret_value")
            else str(_default_pw)
        )

        async with db_session() as db2:
            from sqlalchemy import text as sql_text

            # Get OS family from template
            if vm.os_template_id:
                result = await db2.execute(
                    sql_text("SELECT os_family FROM os_templates WHERE id = :id"),
                    {"id": str(vm.os_template_id)},
                )
                row = result.fetchone()
                if row and row[0]:
                    os_family = row[0]

            # Get VM credentials from last completed deployment
            dep_result = await db2.execute(
                sql_text(
                    "SELECT config FROM deployments "
                    "WHERE vm_id = :vm_id AND status = 'completed' "
                    "ORDER BY completed_at DESC LIMIT 1"
                ),
                {"vm_id": vm_id},
            )
            dep_row = dep_result.fetchone()
            if dep_row and dep_row[0]:
                dep_config = dep_row[0]
                if dep_config.get("admin_password"):
                    vm_admin_password = dep_config["admin_password"]
                # Use admin_username from config, or detect locale-based name
                if dep_config.get("admin_username"):
                    vm_admin_user = dep_config["admin_username"]
                elif not dep_config.get("admin_username"):
                    vm_admin_user = ".\\otoroot"

        shell_type = "powershell" if os_family == "windows" else "ssh"

        # ---- Send connected message ----
        await websocket.send_text(
            json.dumps(
                {
                    "type": "connected",
                    "vm_id": vm_id,
                    "shell": shell_type,
                    "message": f"Terminal connected ({shell_type})",
                }
            )
        )

        # ---- For Windows VMs: determine connection method ----
        # Prefer PowerShell Direct (-VMName) which bypasses network/WinRM issues.
        # Fall back to network WinRM (-ComputerName) only if Direct fails.
        use_ps_direct = False
        if shell_type == "powershell":
            await _send(websocket, f"Connecting to {vm.name}...\r\n")
            # Test PowerShell Direct first (more reliable, no network config needed)
            try:
                escaped_pw = vm_admin_password.replace("'", "''")
                escaped_user = vm_admin_user.replace("'", "''")
                test_script = (
                    f"$secPw = ConvertTo-SecureString '{escaped_pw}' -AsPlainText -Force; "
                    f"$cred = New-Object System.Management.Automation.PSCredential('{escaped_user}', $secPw); "
                    f"Invoke-Command -VMName '{vm.name}' -Credential $cred "
                    f"-ScriptBlock {{ Write-Output 'OK' }} -ErrorAction Stop"
                )
                test_result = await client._execute(test_script, timeout=20)
                if test_result.stdout and "OK" in test_result.stdout:
                    use_ps_direct = True
                    logger.info("terminal_ps_direct_ok", vm_id=vm_id, vm_name=vm.name)
            except Exception as e:
                logger.warning("terminal_ps_direct_failed", vm_id=vm_id, error=str(e))

            # If PowerShell Direct failed and we have an IP, try network WinRM
            if not use_ps_direct and vm_ip:
                try:
                    await client._execute(
                        f"$current = (Get-Item WSMan:\\localhost\\Client\\TrustedHosts -ErrorAction SilentlyContinue).Value; "
                        f"if ($current -ne '*' -and $current -notlike '*{vm_ip}*') {{ "
                        f"  $new = if ($current) {{ \"$current,{vm_ip}\" }} else {{ '{vm_ip}' }}; "
                        f"  Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value $new -Force "
                        f"}}",
                        timeout=15,
                    )
                except Exception as e:
                    logger.warning("trustedhosts_setup_failed", vm_id=vm_id, error=str(e))

        # ---- Send welcome banner ----
        if shell_type == "powershell":
            method = "PowerShell Direct" if use_ps_direct else "WinRM"
            banner = f"Windows PowerShell ({method})\r\nConnected to {vm.name}"
            if vm_ip:
                banner += f" ({vm_ip})"
            banner += "\r\n\r\n"
        else:
            banner = f"SSH Terminal\r\nConnected to {vm.name}"
            if vm_ip:
                banner += f" ({vm_ip})"
            banner += "\r\n\r\n"

        await _send(websocket, banner)

        # ---- Send initial prompt ----
        cwd = "C:\\" if shell_type == "powershell" else "~"
        prompt = f"PS {cwd}> " if shell_type == "powershell" else f"{vm.name}:~$ "
        await _send(websocket, prompt)

        # ---- Command loop ----
        input_buffer = ""
        current_dir = cwd

        while True:
            try:
                data = await websocket.receive_text()
                msg = json.loads(data)

                if msg.get("type") == "input":
                    raw = msg.get("data", "")

                    for char in raw:
                        if char in ("\r", "\n"):
                            # Execute the buffered command
                            command = input_buffer.strip()
                            input_buffer = ""

                            # Echo newline
                            await _send(websocket, "\r\n")

                            if not command:
                                await _send(websocket, prompt)
                                continue

                            # Handle exit/quit
                            if command.lower() in ("exit", "quit"):
                                await _send(websocket, "Session terminated.\r\n")
                                await websocket.close()
                                return

                            # Execute via hypervisor
                            try:
                                if shell_type == "powershell":
                                    escaped_pw = vm_admin_password.replace("'", "''")
                                    escaped_user = vm_admin_user.replace("'", "''")
                                    if use_ps_direct:
                                        # PowerShell Direct via Hyper-V host (-VMName)
                                        ps_script = (
                                            f"$ErrorActionPreference = 'Continue'; "
                                            f"$secPw = ConvertTo-SecureString '{escaped_pw}' "
                                            f"-AsPlainText -Force; "
                                            f"$cred = New-Object System.Management.Automation.PSCredential("
                                            f"'{escaped_user}', $secPw); "
                                            f"Invoke-Command -VMName '{vm.name}' -Credential $cred "
                                            f"-ScriptBlock {{ "
                                            f"  Set-Location '{current_dir}' -ErrorAction SilentlyContinue; "
                                            f"  {command}; "
                                            f'  Write-Output "::CWD::$(Get-Location)" '
                                            f"}}"
                                        )
                                    elif vm_ip:
                                        # Network WinRM fallback (-ComputerName)
                                        ps_script = (
                                            f"$ErrorActionPreference = 'Continue'; "
                                            f"$secPw = ConvertTo-SecureString '{escaped_pw}' "
                                            f"-AsPlainText -Force; "
                                            f"$cred = New-Object System.Management.Automation.PSCredential("
                                            f"'{escaped_user}', $secPw); "
                                            f"Invoke-Command -ComputerName {vm_ip} -Credential $cred "
                                            f"-ScriptBlock {{ "
                                            f"  Set-Location '{current_dir}' -ErrorAction SilentlyContinue; "
                                            f"  {command}; "
                                            f'  Write-Output "::CWD::$(Get-Location)" '
                                            f"}}"
                                        )
                                    else:
                                        # No IP and no PS Direct: execute directly on hypervisor
                                        ps_script = (
                                            f"Set-Location '{current_dir}' -ErrorAction SilentlyContinue; "
                                            f"{command}; "
                                            f'Write-Output "::CWD::$(Get-Location)"'
                                        )

                                    result = await client._execute(
                                        ps_script, timeout=30
                                    )
                                else:
                                    # SSH via hypervisor
                                    if vm_ip:
                                        ssh_cmd = (
                                            f"ssh -o StrictHostKeyChecking=no "
                                            f"-o ConnectTimeout=5 root@{vm_ip} "
                                            f"'cd {current_dir} 2>/dev/null; {command}; echo ::CWD::$(pwd)'"
                                        )
                                        result = await client._execute(
                                            ssh_cmd, timeout=30
                                        )
                                    else:
                                        # Fake result for no-IP case
                                        class _R:
                                            stdout = "Error: No IP address for SSH\n"
                                            stderr = ""
                                            status_code = 1
                                        result = _R()

                                output = result.stdout or ""
                                stderr = result.stderr or ""

                                # Clean CLIXML from stderr
                                if stderr:
                                    stderr = _clean_clixml(stderr)
                                    # Suppress if only whitespace/hash remains after cleaning
                                    if not stderr.strip().strip("#"):
                                        stderr = ""

                                # Clean CLIXML from stdout too (Invoke-Command can mix it)
                                if output and "#< CLIXML" in output:
                                    output = _clean_clixml(output)

                                # Extract CWD marker if present
                                lines = output.split("\n")
                                filtered_lines = []
                                for line in lines:
                                    stripped = line.strip()
                                    if stripped.startswith("::CWD::"):
                                        new_cwd = stripped[7:]  # len("::CWD::")
                                        if new_cwd:
                                            current_dir = new_cwd
                                    else:
                                        filtered_lines.append(line)

                                output = "\n".join(filtered_lines).rstrip("\n")

                                if output:
                                    terminal_output = output.replace(
                                        "\r\n", "\n"
                                    ).replace("\n", "\r\n")
                                    await _send(websocket, terminal_output + "\r\n")

                                if stderr:
                                    terminal_stderr = stderr.replace(
                                        "\r\n", "\n"
                                    ).replace("\n", "\r\n")
                                    await _send(
                                        websocket,
                                        f"\x1b[31m{terminal_stderr}\x1b[0m\r\n",
                                    )

                            except Exception as e:
                                error_msg = str(e)
                                await _send(
                                    websocket,
                                    f"\x1b[31mError: {error_msg}\x1b[0m\r\n",
                                )

                            # Update prompt with current directory
                            if shell_type == "powershell":
                                prompt = f"PS {current_dir}> "
                            else:
                                prompt = f"{vm.name}:{current_dir}$ "

                            await _send(websocket, prompt)

                        elif char in ("\x7f", "\b"):
                            # Backspace
                            if input_buffer:
                                input_buffer = input_buffer[:-1]
                                await _send(websocket, "\b \b")

                        elif char == "\x03":
                            # Ctrl+C
                            input_buffer = ""
                            await _send(websocket, "^C\r\n" + prompt)

                        elif char == "\x0c":
                            # Ctrl+L (clear screen)
                            input_buffer = ""
                            await _send(websocket, "\x1b[2J\x1b[H" + prompt)

                        else:
                            # Regular character - echo and buffer
                            input_buffer += char
                            await _send(websocket, char)

                elif msg.get("type") == "resize":
                    # Terminal resize event - ignored for command-by-command mode
                    pass

            except (WebSocketDisconnect, RuntimeError):
                break
            except json.JSONDecodeError:
                pass
            except Exception as e:
                logger.warning("terminal_input_error", vm_id=vm_id, error=str(e))

    except Exception as e:
        logger.error("terminal_init_failed", vm_id=vm_id, error=str(e))
        try:
            if _is_ws_open(websocket):
                await websocket.send_text(
                    json.dumps(
                        {"type": "error", "message": f"Terminal init failed: {e}"}
                    )
                )
                await websocket.close()
        except Exception:
            pass
    finally:
        _active_terminals.pop(vm_id, None)
        if client:
            client.close()
        logger.info("terminal_disconnected", vm_id=vm_id)
