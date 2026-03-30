"""add user role column

Revision ID: 010_add_user_roles
Revises: 009_add_indexes
Create Date: 2026-03-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '010_add_user_roles'
down_revision: Union[str, None] = '009_add_indexes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Créer le type enum PostgreSQL
    userrole_enum = sa.Enum('admin', 'user', name='userrole')
    userrole_enum.create(op.get_bind(), checkfirst=True)

    # Ajouter la colonne role avec valeur par défaut 'user'
    op.add_column(
        'users',
        sa.Column(
            'role',
            userrole_enum,
            server_default='user',
            nullable=False,
            comment='Rôle de l\'utilisateur (admin ou user)',
        ),
    )

    # Tous les utilisateurs existants deviennent admin
    op.execute("UPDATE users SET role = 'admin'")


def downgrade() -> None:
    op.drop_column('users', 'role')

    # Supprimer le type enum
    sa.Enum(name='userrole').drop(op.get_bind(), checkfirst=True)
