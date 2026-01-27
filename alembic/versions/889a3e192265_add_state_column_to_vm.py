"""add_state_column_to_vm

Revision ID: 889a3e192265
Revises: 001
Create Date: 2026-01-26 17:13:13.683702

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '889a3e192265'
down_revision: Union[str, Sequence[str], None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add state, hypervisor_vm_id, ip_address to virtual_machines."""
    # Create vmstate enum with lowercase values matching Python model
    vmstate_enum = sa.Enum('running', 'stopped', 'paused', 'saved', 'unknown', name='vmstate')
    vmstate_enum.create(op.get_bind(), checkfirst=True)
    
    # Add new columns
    op.add_column('virtual_machines', sa.Column('state', vmstate_enum, nullable=True, comment='État Hyper-V (running, stopped, paused, etc.)'))
    op.add_column('virtual_machines', sa.Column('hypervisor_vm_id', sa.String(length=100), nullable=True, comment='GUID Hyper-V de la VM'))
    op.add_column('virtual_machines', sa.Column('ip_address', sa.String(length=45), nullable=True, comment='Adresse IP de la VM'))
    
    # Set default value for state on existing rows
    op.execute("UPDATE virtual_machines SET state = 'unknown' WHERE state IS NULL")
    
    # Make state NOT NULL after setting defaults
    op.alter_column('virtual_machines', 'state', nullable=False)
    
    # Note: hypervisor_vm_id is now created in migration 001
    # This block is kept for backwards compatibility with databases
    # that have the old 'hyperv_id' column
    try:
        op.execute("ALTER TABLE virtual_machines RENAME COLUMN hyperv_id TO hypervisor_vm_id_old")
        op.execute("UPDATE virtual_machines SET hypervisor_vm_id = hypervisor_vm_id_old WHERE hypervisor_vm_id IS NULL")
        op.drop_column('virtual_machines', 'hypervisor_vm_id_old')
    except Exception:
        # Column might not exist or already renamed
        pass


def downgrade() -> None:
    """Downgrade schema - remove state, hypervisor_vm_id, ip_address from virtual_machines."""
    op.drop_column('virtual_machines', 'ip_address')
    op.drop_column('virtual_machines', 'hypervisor_vm_id')
    op.drop_column('virtual_machines', 'state')
    
    # Drop vmstate enum
    vmstate_enum = sa.Enum('running', 'stopped', 'paused', 'saved', 'unknown', name='vmstate')
    vmstate_enum.drop(op.get_bind(), checkfirst=True)
