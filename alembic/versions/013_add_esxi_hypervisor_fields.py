# =============================================================================
# Migration 013 - Add ESXi/VMware fields to hypervisors
# =============================================================================
"""
Ajoute les colonnes spécifiques ESXi/vSphere à la table hypervisors:
  - datacenter: Nom du datacenter vCenter
  - cluster: Nom du cluster vCenter
  - default_datastore: Datastore par défaut pour les VMs
  - default_resource_pool: Resource pool par défaut
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "013_add_esxi_fields"
down_revision: Union[str, None] = "012_add_foreign_key_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "hypervisors",
        sa.Column("datacenter", sa.String(255), nullable=True),
    )
    op.add_column(
        "hypervisors",
        sa.Column("cluster", sa.String(255), nullable=True),
    )
    op.add_column(
        "hypervisors",
        sa.Column("default_datastore", sa.String(255), nullable=True),
    )
    op.add_column(
        "hypervisors",
        sa.Column("default_resource_pool", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("hypervisors", "default_resource_pool")
    op.drop_column("hypervisors", "default_datastore")
    op.drop_column("hypervisors", "cluster")
    op.drop_column("hypervisors", "datacenter")
