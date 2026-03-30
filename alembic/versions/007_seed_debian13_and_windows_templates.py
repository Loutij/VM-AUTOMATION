"""seed Debian 13 and Windows OS templates

Revision ID: 007_seed_debian13_and_windows_templates
Revises: 006_seed_linux_templates
Create Date: 2026-03-04

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '007_seed_deb13_win_tpl'
down_revision: Union[str, None] = '006_seed_linux_templates'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fixed UUIDs for reproducibility and easy rollback
TEMPLATE_IDS = {
    "debian_13":          "a1b2c3d4-0006-4000-8000-000000000006",
    "windows_server_2019": "a1b2c3d4-0010-4000-8000-000000000010",
    "windows_server_2022": "a1b2c3d4-0011-4000-8000-000000000011",
    "windows_server_2025": "a1b2c3d4-0012-4000-8000-000000000012",
    "windows_10":          "a1b2c3d4-0013-4000-8000-000000000013",
    "windows_11":          "a1b2c3d4-0014-4000-8000-000000000014",
}


def upgrade() -> None:
    # --------------------------------------------------------------------------
    # Debian 13 (Trixie) LTS
    # --------------------------------------------------------------------------
    op.execute(f"""
        INSERT INTO os_templates (id, name, os_family, os_type, architecture, iso_path,
            unattend_template, min_cpu, min_ram_gb, min_disk_gb, install_locale,
            is_active, created_at, updated_at)
        VALUES (
            '{TEMPLATE_IDS["debian_13"]}',
            'Debian 13 (Trixie)',
            'linux',
            'debian_13',
            'x64',
            'C:\\HyperV\\ISOs\\debian-13.3.0-amd64-netinst.iso',
            'debian_13.cfg',
            1, 1, 15, 'fr-FR',
            TRUE, NOW(), NOW()
        )
    """)

    # --------------------------------------------------------------------------
    # Windows Server 2019
    # --------------------------------------------------------------------------
    op.execute(f"""
        INSERT INTO os_templates (id, name, os_family, os_type, architecture, iso_path,
            unattend_template, min_cpu, min_ram_gb, min_disk_gb, install_locale,
            is_active, created_at, updated_at)
        VALUES (
            '{TEMPLATE_IDS["windows_server_2019"]}',
            'Windows Server 2019',
            'windows',
            'windows_server_2019',
            'x64',
            'C:\\HyperV\\ISOs\\WinSrv2019_FR.iso',
            'windows_server_2019.xml',
            2, 2, 32, 'fr-FR',
            TRUE, NOW(), NOW()
        )
    """)

    # --------------------------------------------------------------------------
    # Windows Server 2022
    # --------------------------------------------------------------------------
    op.execute(f"""
        INSERT INTO os_templates (id, name, os_family, os_type, architecture, iso_path,
            unattend_template, min_cpu, min_ram_gb, min_disk_gb, install_locale,
            is_active, created_at, updated_at)
        VALUES (
            '{TEMPLATE_IDS["windows_server_2022"]}',
            'Windows Server 2022',
            'windows',
            'windows_server_2022',
            'x64',
            'C:\\HyperV\\ISOs\\WinSrv2022_FR.iso',
            'windows_server_2022.xml',
            2, 2, 32, 'fr-FR',
            TRUE, NOW(), NOW()
        )
    """)

    # --------------------------------------------------------------------------
    # Windows Server 2025
    # --------------------------------------------------------------------------
    op.execute(f"""
        INSERT INTO os_templates (id, name, os_family, os_type, architecture, iso_path,
            unattend_template, min_cpu, min_ram_gb, min_disk_gb, install_locale,
            is_active, created_at, updated_at)
        VALUES (
            '{TEMPLATE_IDS["windows_server_2025"]}',
            'Windows Server 2025',
            'windows',
            'windows_server_2025',
            'x64',
            'C:\\HyperV\\ISOs\\WinSrv2025_FR.iso',
            'windows_server_2025.xml',
            2, 4, 32, 'fr-FR',
            TRUE, NOW(), NOW()
        )
    """)

    # --------------------------------------------------------------------------
    # Windows 10 Enterprise
    # --------------------------------------------------------------------------
    op.execute(f"""
        INSERT INTO os_templates (id, name, os_family, os_type, architecture, iso_path,
            unattend_template, min_cpu, min_ram_gb, min_disk_gb, install_locale,
            is_active, created_at, updated_at)
        VALUES (
            '{TEMPLATE_IDS["windows_10"]}',
            'Windows 10 Enterprise',
            'windows',
            'windows_10',
            'x64',
            'C:\\HyperV\\ISOs\\Win10_FR.iso',
            'windows_10.xml',
            2, 2, 40, 'fr-FR',
            TRUE, NOW(), NOW()
        )
    """)

    # --------------------------------------------------------------------------
    # Windows 11 Enterprise
    # --------------------------------------------------------------------------
    op.execute(f"""
        INSERT INTO os_templates (id, name, os_family, os_type, architecture, iso_path,
            unattend_template, min_cpu, min_ram_gb, min_disk_gb, install_locale,
            is_active, created_at, updated_at)
        VALUES (
            '{TEMPLATE_IDS["windows_11"]}',
            'Windows 11 Enterprise',
            'windows',
            'windows_11',
            'x64',
            'C:\\HyperV\\ISOs\\Win11_FR.iso',
            'windows_11.xml',
            2, 4, 64, 'fr-FR',
            TRUE, NOW(), NOW()
        )
    """)


def downgrade() -> None:
    ids = ", ".join(f"'{uid}'" for uid in TEMPLATE_IDS.values())
    op.execute(f"DELETE FROM os_templates WHERE id IN ({ids})")
