# =============================================================================
# VM Automation - Logging Configuration
# =============================================================================
"""
Configuration du logging structuré avec structlog.
Produit des logs JSON en production et lisibles en développement.
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor

from src.common.config import settings


def setup_logging() -> None:
    """Configure le logging pour l'application."""
    
    # Niveau de log depuis la configuration
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    
    # Processors communs
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]
    
    # En développement : logs colorés et lisibles
    # En production : logs JSON
    if settings.app_env == "development":
        processors: list[Processor] = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        processors = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    
    # Configuration structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configuration du logging standard Python
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    
    # Réduire le bruit des loggers tiers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Retourne un logger structuré.
    
    Args:
        name: Nom du logger (généralement __name__)
        
    Returns:
        Logger structuré configuré
    """
    return structlog.get_logger(name)


class LogContext:
    """
    Context manager pour ajouter du contexte aux logs.
    
    Usage:
        with LogContext(request_id="abc123", user_id="user1"):
            logger.info("Processing request")
    """
    
    def __init__(self, **kwargs: Any) -> None:
        self.context = kwargs
        self._token: Any = None
    
    def __enter__(self) -> "LogContext":
        self._token = structlog.contextvars.bind_contextvars(**self.context)
        return self
    
    def __exit__(self, *args: Any) -> None:
        if self._token is not None:
            structlog.contextvars.unbind_contextvars(*self.context.keys())


def log_operation(
    logger: structlog.stdlib.BoundLogger,
    operation: str,
    **context: Any,
) -> None:
    """
    Log une opération avec contexte standardisé.
    
    Args:
        logger: Logger à utiliser
        operation: Nom de l'opération
        **context: Contexte additionnel
    """
    logger.info(
        "operation_started",
        operation=operation,
        **context,
    )


def log_operation_success(
    logger: structlog.stdlib.BoundLogger,
    operation: str,
    duration_ms: float | None = None,
    **context: Any,
) -> None:
    """Log la réussite d'une opération."""
    log_data: dict[str, Any] = {"operation": operation, "status": "success", **context}
    if duration_ms is not None:
        log_data["duration_ms"] = round(duration_ms, 2)
    logger.info("operation_completed", **log_data)


def log_operation_failure(
    logger: structlog.stdlib.BoundLogger,
    operation: str,
    error: Exception,
    duration_ms: float | None = None,
    **context: Any,
) -> None:
    """Log l'échec d'une opération."""
    log_data: dict[str, Any] = {
        "operation": operation,
        "status": "failure",
        "error_type": type(error).__name__,
        "error_message": str(error),
        **context,
    }
    if duration_ms is not None:
        log_data["duration_ms"] = round(duration_ms, 2)
    logger.error("operation_failed", **log_data, exc_info=True)
