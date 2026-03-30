# =============================================================================
# VM Automation - Health Endpoint Integration Tests
# =============================================================================
"""
Tests for the health/readiness/liveness endpoints.
These run against a real FastAPI instance with a test database.
"""

import pytest
from httpx import AsyncClient


class TestLivenessEndpoint:
    """GET /live should always return 200 with {"status": "alive"}."""

    async def test_liveness_returns_200(self, client: AsyncClient):
        response = await client.get("/live")
        assert response.status_code == 200

    async def test_liveness_body(self, client: AsyncClient):
        response = await client.get("/live")
        data = response.json()
        assert data["status"] == "alive"


class TestHealthEndpoint:
    """GET /health returns a structured status report."""

    async def test_health_returns_200(self, client: AsyncClient):
        response = await client.get("/health")
        assert response.status_code == 200

    async def test_health_has_required_fields(self, client: AsyncClient):
        response = await client.get("/health")
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data
        assert "environment" in data
        assert "checks" in data

    async def test_health_status_value(self, client: AsyncClient):
        response = await client.get("/health")
        data = response.json()
        # In test environment, DB/Redis may be unavailable, but endpoint should not crash
        assert data["status"] in {"healthy", "degraded", "unhealthy"}

    async def test_health_environment(self, client: AsyncClient):
        response = await client.get("/health")
        data = response.json()
        assert data["environment"] == "development"


class TestReadinessEndpoint:
    """GET /ready checks whether the app can serve traffic."""

    async def test_readiness_returns_200(self, client: AsyncClient):
        response = await client.get("/ready")
        assert response.status_code == 200

    async def test_readiness_has_status(self, client: AsyncClient):
        response = await client.get("/ready")
        data = response.json()
        assert "status" in data
        assert data["status"] in {"ready", "not ready"}
