# =============================================================================
# Migration 014 - Add clone deployment fields to os_templates
# =============================================================================
"""
Ajoute les colonnes de support du workflow clone de templates vSphere
à la table os_templates:
  - deployment_method: méthode de déploiement ('iso' par défaut, ou 'clone')
  - vsphere_template_name: nom de la template vSphere à cloner

Backward compatible : deployment_method vaut 'iso' par défaut pour toutes
les lignes existantes, ce qui ne change pas le comportement actuel.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "014_add_clone_fields"
down_revision: Union[str, None] = "013_add_esxi_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Créer le type enum PostgreSQL (idempotent via checkfirst)
    deployment_method_enum = sa.Enum("iso", "clone", name="deploymentmethod")
    deployment_method_enum.create(bind, checkfirst=True)

    # Vérifier si les colonnes existent déjà (idempotence)
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("os_templates")}

    # Ajouter deployment_method avec default 'iso' (backward compatible)
    if "deployment_method" not in existing_cols:
        op.add_column(
            "os_templates",
            sa.Column(
                "deployment_method",
                sa.Enum("iso", "clone", name="deploymentmethod"),
                nullable=False,
                server_default="iso",
                comment="Méthode de déploiement: iso (par défaut) ou clone d'une template vSphere",
            ),
        )

    # Ajouter vsphere_template_name (nullable — non requis pour iso)
    if "vsphere_template_name" not in existing_cols:
        op.add_column(
            "os_templates",
            sa.Column(
                "vsphere_template_name",
                sa.String(255),
                nullable=True,
                comment="Nom de la template vSphere à cloner (requis si deployment_method=clone)",
            ),
        )


def downgrade() -> None:
    op.drop_column("os_templates", "vsphere_template_name")
    op.drop_column("os_templates", "deployment_method")

    # Supprimer le type enum PostgreSQL
    deployment_method_enum = sa.Enum("iso", "clone", name="deploymentmethod")
    deployment_method_enum.drop(op.get_bind(), checkfirst=True)
