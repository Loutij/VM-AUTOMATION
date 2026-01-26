# =============================================================================
# VM Automation - Common Package
# =============================================================================
"""
Package contenant les utilitaires communs.
"""

from src.common.config import settings
from src.common.database import get_db_session
from src.common.exceptions import (
    VMAutomationError,
    ConfigurationError,
    AuthenticationError,
    HypervisorError,
    PowerShellError,
    DeploymentError,
    ValidationError,
)
from src.common.logging import get_logger, setup_logging
from src.common.powershell import (
    PowerShellExecutor,
    PowerShellResult,
    create_powershell_executor,
)

__all__ = [
    "settings",
    "get_db_session",
    "VMAutomationError",
    "ConfigurationError",
    "AuthenticationError",
    "HypervisorError",
    "PowerShellError",
    "DeploymentError",
    "ValidationError",
    "get_logger",
    "setup_logging",
    "PowerShellExecutor",
    "PowerShellResult",
    "create_powershell_executor",
]
