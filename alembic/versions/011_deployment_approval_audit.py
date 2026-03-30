# =============================================================================
# Migration 011 - Deployment Approval Workflow + Audit Log
# =============================================================================
"""
Ajoute le workflow d'approbation pour les déploiements et la table audit_logs.

- Nouveaux statuts: pending_approval, rejected
- Nouveaux champs sur deployments: requested_by_username, reviewed_by, reviewed_by_username, reviewed_at, review_note
- Nouvelle table: audit_logs
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "011_deployment_approval_audit"
down_revision = "010_add_user_roles"


def upgrade() -> None:
    # 1. Ajouter les nouveaux statuts à l'enum deploymentstatus
    # PostgreSQL ne supporte pas ALTER TYPE ADD VALUE dans une transaction
    # On doit le faire hors transaction
    op.execute("COMMIT")
    op.execute("ALTER TYPE deploymentstatus ADD VALUE IF NOT EXISTS 'pending_approval' BEFORE 'pending'")
    op.execute("ALTER TYPE deploymentstatus ADD VALUE IF NOT EXISTS 'rejected' AFTER 'cancelled'")
    op.execute("BEGIN")

    # 2. Ajouter les colonnes d'approbation sur deployments
    op.add_column("deployments", sa.Column("requested_by_username", sa.String(50), nullable=True))
    op.add_column("deployments", sa.Column("reviewed_by", UUID(as_uuid=True), nullable=True))
    op.add_column("deployments", sa.Column("reviewed_by_username", sa.String(50), nullable=True))
    op.add_column("deployments", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("deployments", sa.Column("review_note", sa.Text(), nullable=True))

    # 3. Créer la table audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(50), nullable=False),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(50), nullable=True),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Index pour les recherches fréquentes
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_resource_type", "audit_logs", ["resource_type"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_column("deployments", "review_note")
    op.drop_column("deployments", "reviewed_at")
    op.drop_column("deployments", "reviewed_by_username")
    op.drop_column("deployments", "reviewed_by")
    op.drop_column("deployments", "requested_by_username")
    # Note: On ne peut pas supprimer des valeurs d'un enum PostgreSQL facilement
