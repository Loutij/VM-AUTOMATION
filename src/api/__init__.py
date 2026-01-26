# =============================================================================
# VM Automation - API Package
# =============================================================================
"""
Package contenant l'API FastAPI.
"""

from src.api.main import app, create_app

__all__ = [
    "app",
    "create_app",
]
