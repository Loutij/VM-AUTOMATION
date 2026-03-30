"""add missing indexes for performance

Revision ID: 009_add_indexes
Revises: 008_fix_iso_paths
Create Date: 2026-03-10

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '009_add_indexes'
down_revision: Union[str, None] = '008_fix_iso_paths'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_virtual_machines_state', 'virtual_machines', ['state'], if_not_exists=True)
    op.create_index('ix_virtual_machines_hypervisor_status', 'virtual_machines', ['hypervisor_id', 'status'], if_not_exists=True)
    op.create_index('ix_deployments_status', 'deployments', ['status'], if_not_exists=True)
    op.create_index('ix_deployments_hypervisor_template', 'deployments', ['hypervisor_id', 'os_template_id'], if_not_exists=True)
    op.create_index('ix_deployment_logs_deployment_created', 'deployment_logs', ['deployment_id', 'created_at'], if_not_exists=True)
    op.create_index('ix_vm_software_status', 'vm_software', ['status'], if_not_exists=True)


def downgrade() -> None:
    op.drop_index('ix_vm_software_status', table_name='vm_software')
    op.drop_index('ix_deployment_logs_deployment_created', table_name='deployment_logs')
    op.drop_index('ix_deployments_hypervisor_template', table_name='deployments')
    op.drop_index('ix_deployments_status', table_name='deployments')
    op.drop_index('ix_virtual_machines_hypervisor_status', table_name='virtual_machines')
    op.drop_index('ix_virtual_machines_state', table_name='virtual_machines')
