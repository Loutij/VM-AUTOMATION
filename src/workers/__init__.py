# =============================================================================
# VM Automation - Workers Module
# =============================================================================
"""
Module Celery pour le traitement asynchrone des déploiements.

Usage:
    # Lancer le worker
    celery -A src.workers.celery_app worker --loglevel=info
    
    # Lancer le scheduler (beat)
    celery -A src.workers.celery_app beat --loglevel=info
    
    # Ou les deux ensemble (dev uniquement)
    celery -A src.workers.celery_app worker --beat --loglevel=info
"""

from src.workers.celery_app import celery_app
from src.workers.tasks import (
    process_deployment,
    process_pending_deployments,
    monitor_active_deployments,
    complete_deployment,
    cancel_deployment_task,
)

__all__ = [
    "celery_app",
    "process_deployment",
    "process_pending_deployments",
    "monitor_active_deployments",
    "complete_deployment",
    "cancel_deployment_task",
]
