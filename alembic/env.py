# =============================================================================
# VM Automation - Alembic Environment Configuration
# =============================================================================
"""
Configuration Alembic pour les migrations de base de données.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import des modèles pour que Alembic les découvre
from src.common.config import settings
from src.common.database import Base
from src.domain.models import (  # noqa: F401
    Deployment,
    DeploymentLog,
    Hypervisor,
    OSTemplate,
    SoftwarePackage,
    VirtualMachine,
    VMSoftware,
)

# Configuration Alembic
config = context.config

# Configuration du logging depuis alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata pour autogenerate
target_metadata = Base.metadata

# URL de la base de données depuis la configuration
config.set_main_option("sqlalchemy.url", settings.database_url_sync)


def run_migrations_offline() -> None:
    """
    Exécute les migrations en mode 'offline'.
    
    Dans ce mode, on génère le SQL sans se connecter à la base.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Exécute les migrations en mode 'online'.
    
    Dans ce mode, on se connecte à la base pour exécuter les migrations.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
