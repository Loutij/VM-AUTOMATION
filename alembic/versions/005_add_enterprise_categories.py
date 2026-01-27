"""Add enterprise services and messaging categories

Revision ID: 005_add_enterprise_categories
Revises: 004_extend_categories
Create Date: 2026-01-27 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '005_add_enterprise_categories'
down_revision: Union[str, None] = '004_extend_categories'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Nouvelles catégories à ajouter
NEW_CATEGORIES = [
    'enterprise_services',
    'messaging',
]


def upgrade() -> None:
    """Ajoute les nouvelles catégories de logiciels."""
    for category in NEW_CATEGORIES:
        op.execute(f"ALTER TYPE softwarecategory ADD VALUE IF NOT EXISTS '{category}'")


def downgrade() -> None:
    """PostgreSQL ne permet pas de supprimer des valeurs d'un enum facilement.
    Les valeurs sont laissées en place mais ne seront pas utilisées.
    """
    pass
