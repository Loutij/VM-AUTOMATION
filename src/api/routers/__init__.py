# =============================================================================
# VM Automation - API Routers
# =============================================================================
"""
Package contenant tous les routers FastAPI.
"""

from src.api.routers import deployments, health, hypervisors, templates, vms

__all__ = [
    "health",
    "hypervisors",
    "vms",
    "templates",
    "deployments",
]
