"""Update deployment model

Revision ID: 002_update_deployment
Revises: 889a3e192265
Create Date: 2026-01-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002_update_deployment'
down_revision: Union[str, None] = '889a3e192265'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to deployments table
    op.add_column('deployments', sa.Column('vm_name', sa.String(100), nullable=True))
    op.add_column('deployments', sa.Column('hypervisor_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('deployments', sa.Column('os_template_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('deployments', sa.Column('config', postgresql.JSONB(), server_default='{}', nullable=False))
    
    # Make vm_id nullable
    op.alter_column('deployments', 'vm_id', nullable=True)
    
    # Add foreign keys
    op.create_foreign_key(
        'fk_deployments_hypervisor_id',
        'deployments', 'hypervisors',
        ['hypervisor_id'], ['id']
    )
    op.create_foreign_key(
        'fk_deployments_os_template_id',
        'deployments', 'os_templates',
        ['os_template_id'], ['id']
    )
    
    # Note: deployment_status enum values are now defined in migration 001
    # These ADD VALUE statements are kept for backwards compatibility with existing databases
    op.execute("ALTER TYPE deploymentstatus ADD VALUE IF NOT EXISTS 'in_progress'")
    op.execute("ALTER TYPE deploymentstatus ADD VALUE IF NOT EXISTS 'creating_vm'")
    op.execute("ALTER TYPE deploymentstatus ADD VALUE IF NOT EXISTS 'installing_os'")
    op.execute("ALTER TYPE deploymentstatus ADD VALUE IF NOT EXISTS 'post_install'")
    op.execute("ALTER TYPE deploymentstatus ADD VALUE IF NOT EXISTS 'installing_software'")


def downgrade() -> None:
    # Remove foreign keys
    op.drop_constraint('fk_deployments_os_template_id', 'deployments', type_='foreignkey')
    op.drop_constraint('fk_deployments_hypervisor_id', 'deployments', type_='foreignkey')
    
    # Make vm_id not nullable (may fail if there are null values)
    op.alter_column('deployments', 'vm_id', nullable=False)
    
    # Remove new columns
    op.drop_column('deployments', 'config')
    op.drop_column('deployments', 'os_template_id')
    op.drop_column('deployments', 'hypervisor_id')
    op.drop_column('deployments', 'vm_name')
    
    # Note: Cannot easily remove enum values in PostgreSQL
