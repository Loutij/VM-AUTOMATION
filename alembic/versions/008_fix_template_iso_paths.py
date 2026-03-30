"""fix template iso_path to G drive with real filenames

Revision ID: 008_fix_iso_paths
Revises: 007_seed_deb13_win_tpl
Create Date: 2026-03-05

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '008_fix_iso_paths'
down_revision: Union[str, None] = '007_seed_deb13_win_tpl'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Map: template os_type -> correct iso_path on G: drive
ISO_PATH_UPDATES = {
    # Linux (migration 006)
    "ubuntu_2404": r"G:\HyperV\ISOs\ubuntu-24.04.4-live-server-amd64.iso",
    "ubuntu_2204": r"G:\HyperV\ISOs\ubuntu-22.04-live-server-amd64.iso",
    "debian_12":   r"G:\HyperV\ISOs\debian-12-amd64-netinst.iso",
    "rocky_9":     r"G:\HyperV\ISOs\Rocky-9-latest-x86_64-dvd.iso",
    "rhel_9":      r"G:\HyperV\ISOs\rhel-9-x86_64-dvd.iso",
    # Debian 13 + Windows (migration 007)
    "debian_13":          r"G:\HyperV\ISOs\debian-13.3.0-amd64-netinst.iso",
    "windows_server_2019": r"G:\HyperV\ISOs\WinSrv2019_FR.iso",
    "windows_server_2022": r"G:\HyperV\ISOs\WinSrv2022_FR.iso",
    "windows_server_2025": r"G:\HyperV\ISOs\WinSrv2025_FR.iso",
    "windows_10":          r"G:\HyperV\ISOs\Win10_FR.iso",
    "windows_11":          r"G:\HyperV\ISOs\Win11_25H2_FR.iso",
}


def upgrade() -> None:
    for os_type, iso_path in ISO_PATH_UPDATES.items():
        # Escape backslashes for SQL
        escaped = iso_path.replace("\\", "\\\\")
        op.execute(
            f"UPDATE os_templates SET iso_path = '{escaped}' "
            f"WHERE os_type = '{os_type}'"
        )


def downgrade() -> None:
    # Revert to original paths (mix of /isos/ and C:\)
    OLD_PATHS = {
        "ubuntu_2404": "/isos/ubuntu-24.04-live-server-amd64.iso",
        "ubuntu_2204": "/isos/ubuntu-22.04-live-server-amd64.iso",
        "debian_12":   "/isos/debian-12-amd64-netinst.iso",
        "rocky_9":     "/isos/Rocky-9-latest-x86_64-dvd.iso",
        "rhel_9":      "/isos/rhel-9-x86_64-dvd.iso",
        "debian_13":          "C:\\\\HyperV\\\\ISOs\\\\debian-13.3.0-amd64-netinst.iso",
        "windows_server_2019": "C:\\\\HyperV\\\\ISOs\\\\WinSrv2019_FR.iso",
        "windows_server_2022": "C:\\\\HyperV\\\\ISOs\\\\WinSrv2022_FR.iso",
        "windows_server_2025": "C:\\\\HyperV\\\\ISOs\\\\WinSrv2025_FR.iso",
        "windows_10":          "C:\\\\HyperV\\\\ISOs\\\\Win10_FR.iso",
        "windows_11":          "C:\\\\HyperV\\\\ISOs\\\\Win11_FR.iso",
    }
    for os_type, iso_path in OLD_PATHS.items():
        op.execute(
            f"UPDATE os_templates SET iso_path = '{iso_path}' "
            f"WHERE os_type = '{os_type}'"
        )
