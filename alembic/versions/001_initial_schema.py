"""Initial database schema

Revision ID: 001
Revises: 
Create Date: 2026-01-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Hypervisors table
    op.create_table(
        'hypervisors',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('type', sa.Enum('hyperv', 'vmware', name='hypervisortype'), nullable=False),
        sa.Column('host', sa.String(255), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False, server_default='5986'),
        sa.Column('use_ssl', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('username', sa.String(100), nullable=False),
        sa.Column('password_encrypted', sa.String(500), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_hypervisors_name', 'hypervisors', ['name'])
    op.create_index('ix_hypervisors_host', 'hypervisors', ['host'])

    # OS Templates table
    op.create_table(
        'os_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('os_family', sa.Enum('windows', 'linux', name='osfamily'), nullable=False),
        sa.Column('os_type', sa.String(50), nullable=False),
        sa.Column('architecture', sa.Enum('x64', 'x86', 'arm64', name='architecture'), nullable=False, server_default='x64'),
        sa.Column('iso_path', sa.String(500), nullable=False),
        sa.Column('unattend_template', sa.Text(), nullable=True),
        sa.Column('min_cpu', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('min_ram_gb', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('min_disk_gb', sa.Integer(), nullable=False, server_default='20'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_os_templates_name', 'os_templates', ['name'])
    op.create_index('ix_os_templates_os_family', 'os_templates', ['os_family'])

    # Virtual Machines table
    op.create_table(
        'virtual_machines',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('hypervisor_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('os_template_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('generation', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('cpu_count', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('ram_gb', sa.Integer(), nullable=False, server_default='4'),
        sa.Column('disk_gb', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('disk_path', sa.String(500), nullable=True),
        sa.Column('network_switch', sa.String(100), nullable=False),
        sa.Column('vlan_id', sa.Integer(), nullable=True),
        sa.Column('mac_address', sa.String(17), nullable=True),
        sa.Column('ip_config', postgresql.JSONB(), nullable=True),
        sa.Column('domain_config', postgresql.JSONB(), nullable=True),
        sa.Column('status', sa.Enum('creating', 'created', 'starting', 'running', 'stopping', 'stopped', 'error', 'deleting', 'deleted', name='vmstatus'), nullable=False, server_default='creating'),
        sa.Column('hyperv_id', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['hypervisor_id'], ['hypervisors.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['os_template_id'], ['os_templates.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_virtual_machines_name', 'virtual_machines', ['name'])
    op.create_index('ix_virtual_machines_status', 'virtual_machines', ['status'])
    op.create_index('ix_virtual_machines_hypervisor_id', 'virtual_machines', ['hypervisor_id'])

    # Deployments table
    op.create_table(
        'deployments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('vm_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('status', sa.Enum('pending', 'vm_creating', 'os_installing', 'post_configuring', 'software_installing', 'completed', 'failed', 'cancelled', name='deploymentstatus'), nullable=False, server_default='pending'),
        sa.Column('current_step', sa.String(50), nullable=True),
        sa.Column('progress', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['vm_id'], ['virtual_machines.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_deployments_status', 'deployments', ['status'])
    op.create_index('ix_deployments_vm_id', 'deployments', ['vm_id'])

    # Deployment Logs table
    op.create_table(
        'deployment_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('deployment_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('level', sa.Enum('debug', 'info', 'warning', 'error', name='loglevel'), nullable=False, server_default='info'),
        sa.Column('step', sa.String(50), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['deployment_id'], ['deployments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_deployment_logs_deployment_id', 'deployment_logs', ['deployment_id'])
    op.create_index('ix_deployment_logs_created_at', 'deployment_logs', ['created_at'])

    # Software Packages table
    op.create_table(
        'software_packages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('version', sa.String(50), nullable=False, server_default='latest'),
        sa.Column('os_family', sa.Enum('windows', 'linux', name='osfamily'), nullable=True),
        sa.Column('install_command_windows', sa.Text(), nullable=True),
        sa.Column('install_command_linux', sa.Text(), nullable=True),
        sa.Column('category', sa.String(50), nullable=False, server_default='other'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_software_packages_name', 'software_packages', ['name'])
    op.create_index('ix_software_packages_category', 'software_packages', ['category'])

    # VM Software (association table)
    op.create_table(
        'vm_software',
        sa.Column('vm_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('software_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.Enum('pending', 'installing', 'installed', 'failed', name='softwareinstallstatus'), nullable=False, server_default='pending'),
        sa.Column('installed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['software_id'], ['software_packages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['vm_id'], ['virtual_machines.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('vm_id', 'software_id')
    )

    # Users table for JWT auth
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('username', sa.String(50), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
        sa.UniqueConstraint('email')
    )
    op.create_index('ix_users_username', 'users', ['username'])
    op.create_index('ix_users_email', 'users', ['email'])


def downgrade() -> None:
    op.drop_table('users')
    op.drop_table('vm_software')
    op.drop_table('software_packages')
    op.drop_table('deployment_logs')
    op.drop_table('deployments')
    op.drop_table('virtual_machines')
    op.drop_table('os_templates')
    op.drop_table('hypervisors')
    
    # Drop enums
    op.execute('DROP TYPE IF EXISTS softwareinstallstatus')
    op.execute('DROP TYPE IF EXISTS loglevel')
    op.execute('DROP TYPE IF EXISTS deploymentstatus')
    op.execute('DROP TYPE IF EXISTS vmstatus')
    op.execute('DROP TYPE IF EXISTS architecture')
    op.execute('DROP TYPE IF EXISTS osfamily')
    op.execute('DROP TYPE IF EXISTS hypervisortype')
