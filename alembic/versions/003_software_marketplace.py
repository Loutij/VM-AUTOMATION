"""Software marketplace - extend software_packages table

Revision ID: 003_software_marketplace
Revises: 002_update_deployment_model
Create Date: 2026-01-27 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003_software_marketplace'
down_revision: Union[str, None] = '002_update_deployment_model'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Créer l'enum pour les catégories
    software_category = postgresql.ENUM(
        'utilities', 'development', 'database', 'webserver', 
        'monitoring', 'security', 'networking', 'office', 
        'media', 'runtime', 'other',
        name='softwarecategory'
    )
    software_category.create(op.get_bind(), checkfirst=True)
    
    # Ajouter les nouvelles colonnes à software_packages
    op.add_column('software_packages', sa.Column('display_name', sa.String(150), nullable=True))
    op.add_column('software_packages', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('software_packages', sa.Column('short_description', sa.String(255), nullable=True))
    op.add_column('software_packages', sa.Column('tags', postgresql.JSONB(), server_default='[]', nullable=False))
    op.add_column('software_packages', sa.Column('package_manager', sa.String(20), server_default='chocolatey', nullable=False))
    op.add_column('software_packages', sa.Column('package_id', sa.String(100), nullable=True))
    op.add_column('software_packages', sa.Column('default_config', postgresql.JSONB(), server_default='{}', nullable=False))
    op.add_column('software_packages', sa.Column('config_schema', postgresql.JSONB(), nullable=True))
    op.add_column('software_packages', sa.Column('icon', sa.String(255), nullable=True))
    op.add_column('software_packages', sa.Column('website', sa.String(255), nullable=True))
    op.add_column('software_packages', sa.Column('documentation_url', sa.String(255), nullable=True))
    op.add_column('software_packages', sa.Column('dependencies', postgresql.JSONB(), server_default='[]', nullable=False))
    op.add_column('software_packages', sa.Column('conflicts', postgresql.JSONB(), server_default='[]', nullable=False))
    op.add_column('software_packages', sa.Column('is_featured', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('software_packages', sa.Column('install_time_minutes', sa.Integer(), server_default='5', nullable=False))
    op.add_column('software_packages', sa.Column('install_count', sa.Integer(), server_default='0', nullable=False))
    
    # Mettre à jour les données existantes
    op.execute("UPDATE software_packages SET display_name = name WHERE display_name IS NULL")
    op.execute("UPDATE software_packages SET package_id = name WHERE package_id IS NULL")
    
    # Rendre les colonnes non-nullables après la mise à jour
    op.alter_column('software_packages', 'display_name', nullable=False)
    op.alter_column('software_packages', 'package_id', nullable=False)
    
    # Mettre à jour le type de la colonne category
    # D'abord créer une nouvelle colonne temporaire
    op.add_column('software_packages', sa.Column('category_new', software_category, nullable=True))
    
    # Migrer les données (mapper les anciennes catégories vers les nouvelles)
    op.execute("""
        UPDATE software_packages SET category_new = 
        CASE 
            WHEN category IN ('utilities', 'development', 'database', 'webserver', 
                            'monitoring', 'security', 'networking', 'office', 
                            'media', 'runtime') THEN category::softwarecategory
            ELSE 'other'::softwarecategory
        END
    """)
    
    # Supprimer l'ancienne colonne et renommer la nouvelle
    op.drop_column('software_packages', 'category')
    op.alter_column('software_packages', 'category_new', new_column_name='category', nullable=False)
    
    # Ajouter une contrainte d'unicité sur le nom
    op.create_unique_constraint('uq_software_packages_name', 'software_packages', ['name'])


def downgrade() -> None:
    # Supprimer la contrainte d'unicité
    op.drop_constraint('uq_software_packages_name', 'software_packages', type_='unique')
    
    # Restaurer la colonne category en string
    op.add_column('software_packages', sa.Column('category_old', sa.String(50), nullable=True))
    op.execute("UPDATE software_packages SET category_old = category::text")
    op.drop_column('software_packages', 'category')
    op.alter_column('software_packages', 'category_old', new_column_name='category', nullable=False, server_default='other')
    
    # Supprimer les nouvelles colonnes
    op.drop_column('software_packages', 'install_count')
    op.drop_column('software_packages', 'install_time_minutes')
    op.drop_column('software_packages', 'is_featured')
    op.drop_column('software_packages', 'conflicts')
    op.drop_column('software_packages', 'dependencies')
    op.drop_column('software_packages', 'documentation_url')
    op.drop_column('software_packages', 'website')
    op.drop_column('software_packages', 'icon')
    op.drop_column('software_packages', 'config_schema')
    op.drop_column('software_packages', 'default_config')
    op.drop_column('software_packages', 'package_id')
    op.drop_column('software_packages', 'package_manager')
    op.drop_column('software_packages', 'tags')
    op.drop_column('software_packages', 'short_description')
    op.drop_column('software_packages', 'description')
    op.drop_column('software_packages', 'display_name')
    
    # Supprimer l'enum
    op.execute("DROP TYPE IF EXISTS softwarecategory")
