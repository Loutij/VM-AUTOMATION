# =============================================================================
# VM Automation - VNC Service
# =============================================================================
"""
VNC server provisioning service.

Handles installation and configuration of VNC servers (TigerVNC/x11vnc)
inside Linux VMs, and enables RDP for Windows VMs.
"""

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.exceptions import VMOperationError, VMNotFoundError
from src.domain.models import VirtualMachine, OSFamily

logger = logging.getLogger(__name__)


# VNC installation scripts per OS family
LINUX_VNC_INSTALL_SCRIPT = """#!/bin/bash
set -e

# Detect package manager
if command -v apt-get &>/dev/null; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq tigervnc-standalone-server tigervnc-common dbus-x11 xfce4 xfce4-terminal 2>/dev/null || \
    apt-get install -y -qq x11vnc xvfb 2>/dev/null
elif command -v dnf &>/dev/null; then
    dnf install -y -q tigervnc-server xorg-x11-xauth dbus-x11 xfce4-session 2>/dev/null || \
    dnf install -y -q x11vnc xorg-x11-server-Xvfb 2>/dev/null
elif command -v yum &>/dev/null; then
    yum install -y -q tigervnc-server xorg-x11-xauth dbus-x11 2>/dev/null || \
    yum install -y -q x11vnc xorg-x11-server-Xvfb 2>/dev/null
fi

echo "VNC_INSTALL_OK"
"""

LINUX_VNC_CONFIGURE_SCRIPT = """#!/bin/bash
set -e

VNC_USER="{username}"
VNC_PASS="{password}"
VNC_PORT="{port}"
VNC_DISPLAY=":{display}"

# Create VNC password file
mkdir -p /home/$VNC_USER/.vnc
echo "$VNC_PASS" | vncpasswd -f > /home/$VNC_USER/.vnc/passwd 2>/dev/null || true
chmod 600 /home/$VNC_USER/.vnc/passwd
chown -R $VNC_USER:$VNC_USER /home/$VNC_USER/.vnc

# Create xstartup
cat > /home/$VNC_USER/.vnc/xstartup << 'XEOF'
#!/bin/bash
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
exec startxfce4 &
XEOF
chmod +x /home/$VNC_USER/.vnc/xstartup

# Create systemd service
cat > /etc/systemd/system/vncserver@.service << 'SEOF'
[Unit]
Description=VNC Server for display %i
After=network.target

[Service]
Type=forking
User={username}
Group={username}
WorkingDirectory=/home/{username}
PIDFile=/home/{username}/.vnc/%H%i.pid
ExecStartPre=-/usr/bin/vncserver -kill %i
ExecStart=/usr/bin/vncserver %i -geometry 1280x720 -depth 24 -rfbport {port}
ExecStop=/usr/bin/vncserver -kill %i

[Install]
WantedBy=multi-user.target
SEOF

# Start VNC
systemctl daemon-reload
systemctl enable vncserver@{display}.service
systemctl start vncserver@{display}.service || true

# Fallback: try x11vnc if tigervnc failed
if ! systemctl is-active --quiet vncserver@{display}.service; then
    nohup x11vnc -display $VNC_DISPLAY -rfbport $VNC_PORT -passwd "$VNC_PASS" -forever -create &
fi

# Open firewall
if command -v ufw &>/dev/null; then
    ufw allow {port}/tcp 2>/dev/null || true
elif command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-port={port}/tcp 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
fi

echo "VNC_CONFIGURE_OK"
"""

WINDOWS_RDP_ENABLE_SCRIPT = """
# Enable RDP on Windows VM
Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -Name 'fDenyTSConnections' -Value 0
Enable-NetFirewallRule -DisplayGroup 'Remote Desktop' -ErrorAction SilentlyContinue
Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp' -Name 'UserAuthentication' -Value 0
Write-Output 'RDP_ENABLE_OK'
"""


class VNCService:
    """Service for VNC server provisioning inside VMs."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_vm(self, vm_id: UUID) -> VirtualMachine:
        """Get VM by ID or raise."""
        result = await self.db.execute(
            select(VirtualMachine).where(VirtualMachine.id == vm_id)
        )
        vm = result.scalar_one_or_none()
        if not vm:
            raise VMNotFoundError(str(vm_id))
        return vm

    async def install_vnc(
        self,
        vm_id: UUID,
        username: str = "otoroot",
        password: str = "tooroto",
        port: int = 5900,
        display: int = 1,
    ) -> dict:
        """
        Install and configure VNC server inside a VM.

        For Linux: installs TigerVNC/x11vnc with systemd service
        For Windows: enables RDP (built-in remote desktop)
        """
        vm = await self.get_vm(vm_id)

        if not vm.ip_address:
            raise VMOperationError(
                str(vm_id), "install_vnc", "VM has no IP address"
            )

        os_family = vm.os_template.os_family if vm.os_template else None

        if os_family == OSFamily.WINDOWS:
            return await self._enable_windows_rdp(vm)
        else:
            return await self._install_linux_vnc(
                vm, username, password, port, display
            )

    async def _install_linux_vnc(
        self,
        vm: VirtualMachine,
        username: str,
        password: str,
        port: int,
        display: int,
    ) -> dict:
        """Install VNC on Linux VM via SSH."""
        import paramiko

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            ssh.connect(
                vm.ip_address,
                username=username,
                password=password,
                timeout=30,
            )

            # Step 1: Install VNC packages
            logger.info("vnc_installing", extra={"vm_id": str(vm.id), "vm_ip": vm.ip_address})
            _, stdout, stderr = ssh.exec_command(
                LINUX_VNC_INSTALL_SCRIPT,
                timeout=300,
            )
            install_output = stdout.read().decode(errors="replace")
            install_error = stderr.read().decode(errors="replace")

            if "VNC_INSTALL_OK" not in install_output:
                return {
                    "success": False,
                    "step": "install",
                    "error": install_error or "VNC installation failed",
                }

            # Step 2: Configure VNC
            configure_script = LINUX_VNC_CONFIGURE_SCRIPT.format(
                username=username,
                password=password,
                port=port,
                display=display,
            )
            _, stdout, stderr = ssh.exec_command(
                configure_script,
                timeout=120,
            )
            config_output = stdout.read().decode(errors="replace")
            config_error = stderr.read().decode(errors="replace")

            success = "VNC_CONFIGURE_OK" in config_output

            logger.info(
                "vnc_install_complete",
                extra={"vm_id": str(vm.id), "success": success, "port": port},
            )

            return {
                "success": success,
                "step": "configure" if not success else "complete",
                "vnc_port": port,
                "vnc_display": display,
                "vm_ip": vm.ip_address,
                "error": config_error if not success else None,
            }

        except Exception as e:
            logger.error("vnc_install_error", extra={"vm_id": str(vm.id), "error": str(e)})
            return {
                "success": False,
                "step": "connection",
                "error": str(e),
            }
        finally:
            ssh.close()

    async def _enable_windows_rdp(self, vm: VirtualMachine) -> dict:
        """Enable RDP on Windows VM."""
        # For Windows, we use the existing PowerShell infrastructure
        from src.domain.vm_service import VMService

        vm_service = VMService(self.db)

        try:
            client = await vm_service._get_hypervisor_client(vm.hypervisor_id)
            result = await client.execute_in_vm(
                vm.hypervisor_vm_id or vm.name,
                WINDOWS_RDP_ENABLE_SCRIPT,
                vm_credentials=("otoroot", "tooroto"),
                timeout=60,
            )

            success = result.success and "RDP_ENABLE_OK" in (result.stdout or "")

            return {
                "success": success,
                "protocol": "rdp",
                "port": 3389,
                "vm_ip": vm.ip_address,
                "error": result.stderr if not success else None,
            }
        except Exception as e:
            return {
                "success": False,
                "protocol": "rdp",
                "error": str(e),
            }

    async def check_vnc_status(self, vm_id: UUID, port: int = 5900) -> dict:
        """Check if VNC server is reachable on the VM."""
        vm = await self.get_vm(vm_id)

        if not vm.ip_address:
            return {"reachable": False, "error": "No IP address"}

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(vm.ip_address, port),
                timeout=5.0,
            )
            # Read VNC server handshake (e.g., "RFB 003.008\n")
            data = await asyncio.wait_for(reader.read(12), timeout=5.0)
            writer.close()
            await writer.wait_closed()

            is_vnc = data.startswith(b"RFB ")
            return {
                "reachable": True,
                "is_vnc": is_vnc,
                "server_version": data.decode(errors="replace").strip() if is_vnc else None,
                "vm_ip": vm.ip_address,
                "port": port,
            }
        except (ConnectionRefusedError, asyncio.TimeoutError, OSError) as e:
            return {
                "reachable": False,
                "vm_ip": vm.ip_address,
                "port": port,
                "error": str(e),
            }
