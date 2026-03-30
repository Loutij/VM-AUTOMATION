"""add install_locale to os_templates

Revision ID: 005_add_template_locale
Revises: 004_extend_software_categories
Create Date: 2026-01-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005_add_template_locale'
down_revision: Union[str, None] = '004_extend_categories'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ajouter la colonne install_locale avec valeur par défaut 'fr-FR'
    op.add_column(
        'os_templates',
        sa.Column(
            'install_locale',
            sa.String(10),
            nullable=False,
            server_default='fr-FR',
            comment="Langue d'installation (ex: fr-FR, en-US)"
        )
    )


def downgrade() -> None:
    op.drop_column('os_templates', 'install_locale')
