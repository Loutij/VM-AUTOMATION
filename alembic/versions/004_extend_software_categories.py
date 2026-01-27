"""Extend software categories enum

Revision ID: 004_extend_categories
Revises: 003_software_marketplace
Create Date: 2026-01-27 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '004_extend_categories'
down_revision: Union[str, None] = '003_software_marketplace'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Note: Les catégories sont maintenant définies directement dans migration 003
# Cette migration est gardée pour la compatibilité avec les bases existantes
NEW_CATEGORIES = [
    'windows_role',
    'remote_access',
    'browser',
    'containers',
    'file_transfer',
    'network',
    'backup',
]


def upgrade() -> None:
    # Ajouter les nouvelles valeurs à l'enum si elles n'existent pas
    # (pour les bases de données créées avant cette correction)
    for category in NEW_CATEGORIES:
        op.execute(f"ALTER TYPE softwarecategory ADD VALUE IF NOT EXISTS '{category}'")


def downgrade() -> None:
    # PostgreSQL ne permet pas de supprimer des valeurs d'un enum facilement
    # On doit recréer l'enum complet
    # Pour simplifier, on laisse les valeurs en place (elles ne seront juste pas utilisées)
    pass
