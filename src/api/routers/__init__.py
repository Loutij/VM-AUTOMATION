# =============================================================================
# VM Automation - API Routers
# =============================================================================
"""
Package contenant tous les routers FastAPI.
"""

from src.api.routers import (
    auth,
    callbacks,
    deployments,
    health,
    hypervisors,
    realtime,
    settings,
    software_catalog,
    templates,
    vms,
)

__all__ = [
    "auth",
    "callbacks",
    "deployments",
    "health",
    "hypervisors",
    "realtime",
    "settings",
    "software_catalog",
    "templates",
    "vms",
]
