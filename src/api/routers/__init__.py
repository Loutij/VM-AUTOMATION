# =============================================================================
# VM Automation - API Routers
# =============================================================================
"""
Package contenant tous les routers FastAPI.
"""

from src.api.routers import (
    auth,
    callbacks,
    console,
    deployments,
    guacamole,
    health,
    hypervisors,
    realtime,
    settings,
    software_catalog,
    templates,
    terminal,
    vms,
    vnc,
)

__all__ = [
    "auth",
    "callbacks",
    "console",
    "deployments",
    "guacamole",
    "health",
    "hypervisors",
    "realtime",
    "settings",
    "software_catalog",
    "templates",
    "terminal",
    "vms",
    "vnc",
]
