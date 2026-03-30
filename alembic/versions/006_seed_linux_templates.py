"""seed default Linux OS templates

Revision ID: 006_seed_linux_templates
Revises: 005_add_template_locale
Create Date: 2026-03-04

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '006_seed_linux_templates'
down_revision: Union[str, None] = '005_add_template_locale'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fixed UUIDs for reproducibility and easy rollback
TEMPLATE_IDS = {
    "ubuntu_2404": "a1b2c3d4-0001-4000-8000-000000000001",
    "ubuntu_2204": "a1b2c3d4-0002-4000-8000-000000000002",
    "debian_12":   "a1b2c3d4-0003-4000-8000-000000000003",
    "rocky_9":     "a1b2c3d4-0004-4000-8000-000000000004",
    "rhel_9":      "a1b2c3d4-0005-4000-8000-000000000005",
}


def upgrade() -> None:
    # --------------------------------------------------------------------------
    # Ubuntu 24.04 LTS (Noble Numbat)
    # --------------------------------------------------------------------------
    op.execute(f"""
        INSERT INTO os_templates (id, name, os_family, os_type, architecture, iso_path,
            unattend_template, min_cpu, min_ram_gb, min_disk_gb, install_locale,
            is_active, created_at, updated_at)
        VALUES (
            '{TEMPLATE_IDS["ubuntu_2404"]}',
            'Ubuntu 24.04 LTS',
            'linux',
            'ubuntu_2404',
            'x64',
            '/isos/ubuntu-24.04-live-server-amd64.iso',
            'ubuntu_autoinstall.yaml',
            2, 2, 20, 'en-US',
            TRUE, NOW(), NOW()
        )
    """)

    # --------------------------------------------------------------------------
    # Ubuntu 22.04 LTS (Jammy Jellyfish)
    # --------------------------------------------------------------------------
    op.execute(f"""
        INSERT INTO os_templates (id, name, os_family, os_type, architecture, iso_path,
            unattend_template, min_cpu, min_ram_gb, min_disk_gb, install_locale,
            is_active, created_at, updated_at)
        VALUES (
            '{TEMPLATE_IDS["ubuntu_2204"]}',
            'Ubuntu 22.04 LTS',
            'linux',
            'ubuntu_2204',
            'x64',
            '/isos/ubuntu-22.04-live-server-amd64.iso',
            'ubuntu_autoinstall.yaml',
            2, 2, 20, 'en-US',
            TRUE, NOW(), NOW()
        )
    """)

    # --------------------------------------------------------------------------
    # Debian 12 (Bookworm)
    # --------------------------------------------------------------------------
    op.execute(f"""
        INSERT INTO os_templates (id, name, os_family, os_type, architecture, iso_path,
            unattend_template, min_cpu, min_ram_gb, min_disk_gb, install_locale,
            is_active, created_at, updated_at)
        VALUES (
            '{TEMPLATE_IDS["debian_12"]}',
            'Debian 12 (Bookworm)',
            'linux',
            'debian_12',
            'x64',
            '/isos/debian-12-amd64-netinst.iso',
            'debian_12.cfg',
            1, 1, 15, 'en-US',
            TRUE, NOW(), NOW()
        )
    """)

    # --------------------------------------------------------------------------
    # Rocky Linux 9
    # --------------------------------------------------------------------------
    op.execute(f"""
        INSERT INTO os_templates (id, name, os_family, os_type, architecture, iso_path,
            unattend_template, min_cpu, min_ram_gb, min_disk_gb, install_locale,
            is_active, created_at, updated_at)
        VALUES (
            '{TEMPLATE_IDS["rocky_9"]}',
            'Rocky Linux 9',
            'linux',
            'rocky_9',
            'x64',
            '/isos/Rocky-9-latest-x86_64-dvd.iso',
            'rocky_9.cfg',
            2, 2, 20, 'en-US',
            TRUE, NOW(), NOW()
        )
    """)

    # --------------------------------------------------------------------------
    # Red Hat Enterprise Linux 9
    # --------------------------------------------------------------------------
    op.execute(f"""
        INSERT INTO os_templates (id, name, os_family, os_type, architecture, iso_path,
            unattend_template, min_cpu, min_ram_gb, min_disk_gb, install_locale,
            is_active, created_at, updated_at)
        VALUES (
            '{TEMPLATE_IDS["rhel_9"]}',
            'RHEL 9',
            'linux',
            'rhel_9',
            'x64',
            '/isos/rhel-9-x86_64-dvd.iso',
            'rhel_9.cfg',
            2, 2, 20, 'en-US',
            TRUE, NOW(), NOW()
        )
    """)


def downgrade() -> None:
    ids = ", ".join(f"'{uid}'" for uid in TEMPLATE_IDS.values())
    op.execute(f"DELETE FROM os_templates WHERE id IN ({ids})")
