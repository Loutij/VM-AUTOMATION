# =============================================================================
# VM Automation - Test Configuration & Fixtures
# =============================================================================
"""
Shared fixtures for the test suite.
Uses SQLite async for unit tests, mocks for external services.
"""

import os
from collections.abc import AsyncGenerator
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON, String, StaticPool, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ---------------------------------------------------------------------------
# Environment overrides  (MUST happen before any src import)
# ---------------------------------------------------------------------------
os.environ.setdefault("API_SECRET_KEY", "test-secret-key-for-jwt-signing-only")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("HYPERV_HOST", "localhost")
os.environ.setdefault("HYPERV_USER", "test")
os.environ.setdefault("HYPERV_PASSWORD", "test")

from src.common.auth import create_access_token, hash_password  # noqa: E402
from src.common.database import Base, get_db_session  # noqa: E402

# ---------------------------------------------------------------------------
# SQLite compatibility: map PostgreSQL-only types to SQLite equivalents
# ---------------------------------------------------------------------------
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID  # noqa: E402

# When compiling for SQLite, render JSONB as plain JSON and PG UUID as VARCHAR(36)
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler  # noqa: E402

_orig_jsonb = getattr(SQLiteTypeCompiler, "visit_JSONB", None)
if _orig_jsonb is None:
    SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "JSON"

_orig_uuid = getattr(SQLiteTypeCompiler, "visit_UUID", None)
if _orig_uuid is None:
    SQLiteTypeCompiler.visit_UUID = lambda self, type_, **kw: "VARCHAR(36)"


# =============================================================================
# Database fixtures
# =============================================================================

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture()
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create an in-memory SQLite engine for tests."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture()
async def db_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional database session for each test."""
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


# =============================================================================
# FastAPI / HTTP client fixtures
# =============================================================================


@pytest.fixture()
async def app(async_engine: AsyncEngine):
    """Create a FastAPI app wired to the test database."""
    from src.api.main import create_app

    test_app = create_app()

    # Override the DB dependency to use our test session factory
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async def _override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    test_app.dependency_overrides[get_db_session] = _override_get_db
    return test_app


@pytest.fixture()
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for testing API endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# =============================================================================
# Auth fixtures
# =============================================================================

TEST_USER_ID = str(uuid4())
TEST_USERNAME = "testuser"
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "S3cure!Pass"
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)


@pytest.fixture()
def auth_token() -> str:
    """Return a valid JWT access token for the test user."""
    return create_access_token(TEST_USER_ID)


@pytest.fixture()
def expired_token() -> str:
    """Return an expired JWT access token."""
    return create_access_token(TEST_USER_ID, expires_delta=timedelta(seconds=-1))


@pytest.fixture()
def auth_headers(auth_token: str) -> dict[str, str]:
    """Return Authorization headers with a valid bearer token."""
    return {"Authorization": f"Bearer {auth_token}"}


# =============================================================================
# Hyper-V mock fixtures
# =============================================================================


@pytest.fixture()
def mock_hyperv_client() -> MagicMock:
    """Return a mocked Hyper-V client with common methods stubbed."""
    mock = MagicMock()
    mock.test_connection = AsyncMock(return_value=True)
    mock.create_vm = AsyncMock(return_value={"id": str(uuid4()), "name": "test-vm"})
    mock.start_vm = AsyncMock(return_value=True)
    mock.stop_vm = AsyncMock(return_value=True)
    mock.delete_vm = AsyncMock(return_value=True)
    mock.get_vm_status = AsyncMock(return_value="running")
    mock.list_vms = AsyncMock(return_value=[])
    return mock
