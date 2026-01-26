# =============================================================================
# VM Automation - Database Configuration
# =============================================================================
"""
Configuration de la connexion à la base de données PostgreSQL avec SQLAlchemy.
Support async pour les opérations API et sync pour les migrations Alembic.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.common.config import settings
from src.common.logging import get_logger

logger = get_logger(__name__)

# Convention de nommage pour les contraintes (facilite les migrations)
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Classe de base pour tous les modèles SQLAlchemy."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    def to_dict(self) -> dict[str, Any]:
        """Convertit le modèle en dictionnaire."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


# Engine async pour les opérations normales
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Retourne l'engine async SQLAlchemy (singleton)."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
        )
        logger.info(
            "database_engine_created",
            host=settings.db_host,
            database=settings.db_name,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Retourne la factory de sessions async (singleton)."""
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _async_session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency injection pour obtenir une session de base de données.
    
    Usage avec FastAPI:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db_session)):
            ...
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager pour obtenir une session de base de données.
    
    Usage:
        async with db_session() as session:
            result = await session.execute(query)
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialise la base de données.
    Crée les tables si elles n'existent pas (dev uniquement).
    En production, utiliser Alembic.
    """
    if settings.app_env == "development":
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("database_tables_created")


async def close_db() -> None:
    """Ferme les connexions à la base de données."""
    global _engine, _async_session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        logger.info("database_connections_closed")


async def check_db_connection() -> bool:
    """
    Vérifie la connexion à la base de données.
    
    Returns:
        True si la connexion est OK, False sinon
    """
    try:
        async with db_session() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("database_connection_check_failed", error=str(e))
        return False
