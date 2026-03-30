# =============================================================================
# Migration 012 - Add missing foreign key indexes
# =============================================================================
"""
Ajoute des index sur les colonnes FK qui n'en ont pas encore.

Les index composites de la migration 009 couvrent certaines colonnes FK en
première position, mais pas toutes. Cette migration comble les manques pour
éviter les sequential scans sur les JOINs et les filtres courants.
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "012_add_foreign_key_indexes"
down_revision: Union[str, None] = "011_deployment_approval_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # deployments — vm_id et created_by ne sont couverts par aucun index existant
    op.create_index("ix_deployments_vm_id", "deployments", ["vm_id"], if_not_exists=True)
    op.create_index("ix_deployments_created_by", "deployments", ["created_by"], if_not_exists=True)

    # virtual_machines — os_template_id n'est pas couvert (hypervisor_id l'est via ix_..._hypervisor_status)
    op.create_index("ix_virtual_machines_os_template_id", "virtual_machines", ["os_template_id"], if_not_exists=True)

    # audit_logs — aucun index existant
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"], if_not_exists=True)
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_index("ix_virtual_machines_os_template_id", table_name="virtual_machines")
    op.drop_index("ix_deployments_created_by", table_name="deployments")
    op.drop_index("ix_deployments_vm_id", table_name="deployments")
