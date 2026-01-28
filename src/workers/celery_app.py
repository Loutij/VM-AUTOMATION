# =============================================================================
# VM Automation - Celery Application
# =============================================================================
"""
Configuration de l'application Celery pour les tâches asynchrones.
"""

from celery import Celery

from src.common.config import settings

# Créer l'application Celery
celery_app = Celery(
    "vm_automation",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.workers.tasks"],
)

# Configuration Celery
celery_app.conf.update(
    # Sérialisation
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # Timezone
    timezone="UTC",
    enable_utc=True,
    
    # Résultats
    result_expires=3600,  # 1 heure
    
    # Tâches
    task_track_started=True,
    task_time_limit=3600,  # 1 heure max par tâche
    task_soft_time_limit=3300,  # Soft limit à 55 min
    
    # Retry
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Concurrence
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
    
    # Beat schedule pour les tâches périodiques
    beat_schedule={
        "process-pending-deployments": {
            "task": "src.workers.tasks.process_pending_deployments",
            "schedule": 10.0,  # Toutes les 10 secondes
        },
        "monitor-active-deployments": {
            "task": "src.workers.tasks.monitor_active_deployments",
            "schedule": 30.0,  # Toutes les 30 secondes
        },
        "cleanup-old-logs": {
            "task": "src.workers.tasks.cleanup_old_logs",
            "schedule": 3600.0,  # Toutes les heures
        },
        "sync-all-hypervisors": {
            "task": "src.workers.tasks.sync_all_hypervisors",
            "schedule": 300.0,  # Toutes les 5 minutes
        },
    },
)
