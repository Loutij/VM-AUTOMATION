# =============================================================================
# VM Automation - Timeout Management
# =============================================================================
"""
Gestion des timeouts et retry pour les opérations longues.
"""

import asyncio
import functools
import time
from typing import Any, Callable, TypeVar

from src.common.exceptions import DeploymentTimeoutError
from src.common.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


# =============================================================================
# Timeout Configuration
# =============================================================================


class TimeoutConfig:
    """Configuration des timeouts par étape de déploiement."""

    # Timeouts en secondes
    VM_CREATION = 300  # 5 minutes
    OS_INSTALLATION = 3600  # 1 heure
    POST_INSTALLATION = 1800  # 30 minutes
    SOFTWARE_INSTALLATION = 1800  # 30 minutes
    DOMAIN_JOIN = 600  # 10 minutes
    VM_READY_CHECK = 600  # 10 minutes
    POWERSHELL_COMMAND = 300  # 5 minutes
    
    # Intervals de vérification
    HEARTBEAT_CHECK_INTERVAL = 10  # 10 secondes
    INSTALLATION_CHECK_INTERVAL = 30  # 30 secondes
    
    # Retry configuration
    DEFAULT_RETRIES = 3
    DEFAULT_RETRY_DELAY = 5  # secondes
    RETRY_BACKOFF_FACTOR = 2
    MAX_RETRY_DELAY = 60  # secondes

    @classmethod
    def get_timeout(cls, step: str) -> int:
        """Récupère le timeout pour une étape donnée."""
        timeouts = {
            "vm_creation": cls.VM_CREATION,
            "os_installation": cls.OS_INSTALLATION,
            "post_installation": cls.POST_INSTALLATION,
            "software_installation": cls.SOFTWARE_INSTALLATION,
            "domain_join": cls.DOMAIN_JOIN,
            "vm_ready": cls.VM_READY_CHECK,
            "powershell": cls.POWERSHELL_COMMAND,
        }
        return timeouts.get(step, cls.POWERSHELL_COMMAND)


# =============================================================================
# Async Timeout Decorator
# =============================================================================


def with_timeout(
    timeout_seconds: int,
    deployment_id: str | None = None,
    step: str = "operation",
):
    """
    Décorateur pour ajouter un timeout à une fonction async.
    
    Args:
        timeout_seconds: Timeout en secondes
        deployment_id: ID du déploiement (pour les erreurs)
        step: Nom de l'étape (pour les erreurs)
    
    Usage:
        @with_timeout(300, step="vm_creation")
        async def create_vm(...):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "operation_timeout",
                    step=step,
                    timeout=timeout_seconds,
                    deployment_id=deployment_id,
                )
                raise DeploymentTimeoutError(
                    deployment_id or "unknown",
                    step,
                    timeout_seconds,
                ) from None
        return wrapper
    return decorator


# =============================================================================
# Retry with Backoff
# =============================================================================


async def retry_with_backoff(
    func: Callable[..., T],
    *args,
    retries: int = TimeoutConfig.DEFAULT_RETRIES,
    initial_delay: float = TimeoutConfig.DEFAULT_RETRY_DELAY,
    backoff_factor: float = TimeoutConfig.RETRY_BACKOFF_FACTOR,
    max_delay: float = TimeoutConfig.MAX_RETRY_DELAY,
    exceptions: tuple = (Exception,),
    on_retry: Callable[[int, Exception], None] | None = None,
    **kwargs,
) -> T:
    """
    Exécute une fonction avec retry et backoff exponentiel.
    
    Args:
        func: Fonction à exécuter (async ou sync)
        *args: Arguments positionnels
        retries: Nombre de tentatives
        initial_delay: Délai initial entre les tentatives
        backoff_factor: Facteur multiplicatif pour le backoff
        max_delay: Délai maximum entre les tentatives
        exceptions: Exceptions à intercepter
        on_retry: Callback appelé avant chaque retry
        **kwargs: Arguments nommés
    
    Returns:
        Résultat de la fonction
    
    Raises:
        La dernière exception si toutes les tentatives échouent
    """
    last_exception = None
    delay = initial_delay
    
    for attempt in range(retries + 1):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
                
        except exceptions as e:
            last_exception = e
            
            if attempt < retries:
                logger.warning(
                    "operation_retry",
                    attempt=attempt + 1,
                    max_attempts=retries + 1,
                    error=str(e),
                    next_delay=delay,
                )
                
                if on_retry:
                    on_retry(attempt, e)
                
                await asyncio.sleep(delay)
                delay = min(delay * backoff_factor, max_delay)
            else:
                logger.error(
                    "operation_failed_all_retries",
                    attempts=retries + 1,
                    error=str(e),
                )
    
    raise last_exception


def retry_decorator(
    retries: int = TimeoutConfig.DEFAULT_RETRIES,
    initial_delay: float = TimeoutConfig.DEFAULT_RETRY_DELAY,
    backoff_factor: float = TimeoutConfig.RETRY_BACKOFF_FACTOR,
    exceptions: tuple = (Exception,),
):
    """
    Décorateur pour ajouter retry avec backoff à une fonction.
    
    Usage:
        @retry_decorator(retries=3)
        async def flaky_operation(...):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await retry_with_backoff(
                func,
                *args,
                retries=retries,
                initial_delay=initial_delay,
                backoff_factor=backoff_factor,
                exceptions=exceptions,
                **kwargs,
            )
        return wrapper
    return decorator


# =============================================================================
# Progress Tracker
# =============================================================================


class DeploymentProgress:
    """Suit la progression d'un déploiement avec gestion des timeouts."""

    def __init__(
        self,
        deployment_id: str,
        total_steps: int = 4,
        global_timeout: int = 7200,  # 2 heures par défaut
    ) -> None:
        self.deployment_id = deployment_id
        self.total_steps = total_steps
        self.global_timeout = global_timeout
        self.current_step = 0
        self.current_step_name = "initializing"
        self.start_time = time.time()
        self.step_start_time = time.time()
        self._is_cancelled = False

    @property
    def elapsed_time(self) -> float:
        """Temps écoulé depuis le début du déploiement."""
        return time.time() - self.start_time

    @property
    def step_elapsed_time(self) -> float:
        """Temps écoulé depuis le début de l'étape actuelle."""
        return time.time() - self.step_start_time

    @property
    def progress_percent(self) -> int:
        """Pourcentage de progression global."""
        if self.total_steps == 0:
            return 0
        return int((self.current_step / self.total_steps) * 100)

    @property
    def is_timed_out(self) -> bool:
        """Vérifie si le timeout global est dépassé."""
        return self.elapsed_time > self.global_timeout

    @property
    def is_cancelled(self) -> bool:
        """Vérifie si le déploiement est annulé."""
        return self._is_cancelled

    def cancel(self) -> None:
        """Annule le déploiement."""
        self._is_cancelled = True
        logger.info(
            "deployment_cancelled",
            deployment_id=self.deployment_id,
            elapsed=self.elapsed_time,
        )

    def advance_step(self, step_name: str) -> None:
        """Passe à l'étape suivante."""
        self.current_step += 1
        self.current_step_name = step_name
        self.step_start_time = time.time()
        
        logger.info(
            "deployment_step_advanced",
            deployment_id=self.deployment_id,
            step=step_name,
            step_number=self.current_step,
            progress=self.progress_percent,
        )

    def check_timeout(self, step_timeout: int | None = None) -> None:
        """
        Vérifie les timeouts et lève une exception si dépassé.
        
        Args:
            step_timeout: Timeout spécifique à l'étape
        
        Raises:
            DeploymentTimeoutError: Si un timeout est dépassé
        """
        if self._is_cancelled:
            raise DeploymentTimeoutError(
                self.deployment_id,
                self.current_step_name,
                0,
            )
        
        if self.is_timed_out:
            raise DeploymentTimeoutError(
                self.deployment_id,
                "global",
                self.global_timeout,
            )
        
        if step_timeout and self.step_elapsed_time > step_timeout:
            raise DeploymentTimeoutError(
                self.deployment_id,
                self.current_step_name,
                step_timeout,
            )

    def get_status(self) -> dict[str, Any]:
        """Retourne le statut actuel du déploiement."""
        return {
            "deployment_id": self.deployment_id,
            "current_step": self.current_step,
            "step_name": self.current_step_name,
            "total_steps": self.total_steps,
            "progress_percent": self.progress_percent,
            "elapsed_time": round(self.elapsed_time, 2),
            "step_elapsed_time": round(self.step_elapsed_time, 2),
            "is_timed_out": self.is_timed_out,
            "is_cancelled": self.is_cancelled,
        }
