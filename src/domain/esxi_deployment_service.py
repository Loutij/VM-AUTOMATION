# =============================================================================
# VM Automation - ESXi/vSphere Deployment Service
# =============================================================================
"""
Service pour orchestrer le déploiement de VMs sur ESXi/vSphere.
Système parallèle au DeploymentService (Hyper-V) utilisant pyvmomi.

Architecture:
  - deploy() est le point d'entrée principal, appelé par le worker Celery
  - _execute_deployment() dispatche vers le workflow Windows ou Linux
  - Les méthodes _execute_windows_deployment() et _execute_linux_deployment()
    sont des stubs à implémenter par les agents spécialisés
"""

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

# Paramiko pour les connexions SSH post-installation (Linux VMs)
try:
    import paramiko

    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.common.config import settings
from src.common.constants import DEPLOYMENT_STEP_PROGRESS
from src.common.exceptions import (
    DeploymentError,
    DeploymentStepError,
    DeploymentTimeoutError,
    NotFoundError,
    ValidationError,
)
from src.common.logging import get_logger
from src.domain.deployment_service import DeploymentStep
from src.domain.models import (
    Deployment,
    DeploymentLog,
    DeploymentMethod,
    DeploymentStatus,
    Hypervisor,
    HypervisorType,
    OSTemplate,
    VirtualMachine,
    VMState,
    VMStatus,
)
from src.domain.template_engine import get_template_engine
from src.domain.vm_service import VMService

# Mixins contenant les implémentations des différents workflows
from src.domain._esxi_deploy_vm_creation import ESXiVMCreationMixin
from src.domain._esxi_deploy_windows import ESXiWindowsDeployMixin
from src.domain._esxi_deploy_linux import ESXiLinuxDeployMixin
from src.domain._esxi_deploy_guest_ops import ESXiGuestOpsMixin
from src.domain._esxi_deploy_finalize import ESXiFinalizeMixin
from src.domain._esxi_deploy_clone import ESXiCloneDeployMixin

logger = get_logger(__name__)


class ESXiDeploymentService(
    ESXiVMCreationMixin,
    ESXiWindowsDeployMixin,
    ESXiLinuxDeployMixin,
    ESXiGuestOpsMixin,
    ESXiFinalizeMixin,
    ESXiCloneDeployMixin,
):
    """
    Service de déploiement pour ESXi/vSphere.

    Implémente le même workflow que DeploymentService (Hyper-V) mais
    utilise le client VMware (pyvmomi) au lieu de WinRM/PowerShell.

    Workflow:
      1. Validation des paramètres et vérification de l'espace datastore
      2. Dispatch vers le workflow Windows ou Linux
      3. Création de la VM sur ESXi
      4. Configuration réseau
      5. Installation de l'OS (ISO / template clone)
      6. Post-configuration
      7. Installation logiciels
      8. Finalisation
    """

    @staticmethod
    def _sanitize_hostname(name: str) -> str:
        """Convertit un nom de VM en hostname valide (RFC 952, max 15 chars pour Windows)."""
        import re

        h = re.sub(r"[^a-zA-Z0-9]", "-", name)
        h = re.sub(r"-+", "-", h)
        h = h.strip("-")
        h = h[:15].rstrip("-")
        return h or "VM"

    def __init__(self, db: AsyncSession, vm_service: VMService | None = None) -> None:
        """
        Initialise le service de déploiement ESXi.

        Args:
            db: Session de base de données async
            vm_service: Service VM (optionnel, créé automatiquement)
        """
        self.db = db
        self.vm_service = vm_service or VMService(db)
        self.template_engine = get_template_engine()

    # =========================================================================
    # Point d'entrée principal
    # =========================================================================

    async def deploy(self, deployment_id: UUID) -> Deployment:
        """
        Point d'entrée principal du déploiement ESXi.

        Charge le déploiement depuis la base, exécute le workflow complet
        et met à jour le statut final (completed/failed).

        Args:
            deployment_id: ID du déploiement à exécuter

        Returns:
            Déploiement mis à jour
        """
        # Charger le déploiement avec ses relations
        result = await self.db.execute(
            select(Deployment)
            .where(Deployment.id == deployment_id)
            .options(
                selectinload(Deployment.hypervisor),
                selectinload(Deployment.os_template),
            )
        )
        deployment = result.scalar_one_or_none()

        if not deployment:
            raise NotFoundError("Deployment", str(deployment_id))

        # Vérifier que c'est bien un hyperviseur VMware
        if deployment.hypervisor and deployment.hypervisor.type != HypervisorType.VMWARE:
            raise ValidationError(
                f"ESXiDeploymentService ne peut déployer que sur des hyperviseurs "
                f"VMware, mais '{deployment.hypervisor.name}' est de type "
                f"'{deployment.hypervisor.type.value}'"
            )

        # Marquer comme en cours
        deployment.error_message = None
        deployment.progress = 0
        if deployment.status != DeploymentStatus.IN_PROGRESS:
            await self._update_deployment_status(
                deployment,
                DeploymentStatus.IN_PROGRESS,
                DeploymentStep.VALIDATING,
            )
        if not deployment.started_at:
            deployment.started_at = datetime.now(timezone.utc)

        try:
            await self._execute_deployment(deployment)
        except Exception as e:
            logger.error(
                "esxi_deployment_failed",
                deployment_id=str(deployment_id),
                error=str(e),
                exc_info=True,
            )
            await self._update_deployment_status(
                deployment,
                DeploymentStatus.FAILED,
                DeploymentStep.FAILED,
                str(e),
            )
            await self._log_step(
                deployment,
                DeploymentStep.FAILED,
                f"Déploiement ESXi échoué : {e}",
                "error",
            )

        return deployment

    # =========================================================================
    # Dispatcher principal
    # =========================================================================

    async def _execute_deployment(self, deployment: Deployment) -> None:
        """
        Dispatche vers le workflow Windows ou Linux selon la famille d'OS.

        Étapes communes avant le dispatch:
          1. Validation de la configuration
          2. Vérification de l'espace datastore sur l'hôte ESXi

        Args:
            deployment: Déploiement à exécuter
        """
        config = deployment.config

        # Détecter la famille d'OS pour dispatcher vers le bon workflow
        template_config = config.get("template") or {}
        os_family = template_config.get("os_family", "windows")
        # Normaliser : peut être un enum OSFamily ou une string
        if hasattr(os_family, "value"):
            os_family = os_family.value
        os_family = str(os_family).lower()

        # 1. Validation
        await self._log_step(
            deployment,
            DeploymentStep.VALIDATING,
            "Validation de la configuration ESXi",
        )
        await self._validate_deployment(deployment)

        # 1b. Vérification espace datastore sur l'hôte ESXi
        try:
            client = await self.vm_service._get_hypervisor_client(
                deployment.hypervisor_id
            )
            disk_gb = config.get("disk_gb", template_config.get("min_disk_gb", 40))
            # Exiger au moins 1.5x la taille du disque VM (VMDK + ISO temp + marge)
            required_gb = float(disk_gb) * 1.5
            disk_info = await client.check_disk_space(required_gb=required_gb)
            datastore_name = disk_info.get("datastore", disk_info.get("drive_letter", "?"))
            free_gb = disk_info.get("free_gb", 0)
            await self._log_step(
                deployment,
                DeploymentStep.VALIDATING,
                f"Espace datastore OK sur {datastore_name} — "
                f"{free_gb:.1f} Go libre (requis: {required_gb:.0f} Go)",
            )
        except Exception as e:
            error_msg = f"Vérification espace datastore échouée : {e}"
            await self._log_step(
                deployment, DeploymentStep.VALIDATING, error_msg, "error"
            )
            await self._update_deployment_status(
                deployment,
                DeploymentStatus.FAILED,
                DeploymentStep.VALIDATING,
                error_msg,
            )
            return

        # 2. Détecter la méthode de déploiement (iso ou clone)
        deployment_method = template_config.get("deployment_method", "iso")
        # Normaliser : peut être un enum DeploymentMethod ou une string
        if hasattr(deployment_method, "value"):
            deployment_method = deployment_method.value
        deployment_method = str(deployment_method).lower()

        # Vérifier aussi sur le template OS chargé en base
        if deployment_method == "iso" and deployment.os_template:
            os_template_method = deployment.os_template.deployment_method
            if hasattr(os_template_method, "value"):
                os_template_method = os_template_method.value
            if str(os_template_method).lower() == DeploymentMethod.CLONE.value:
                deployment_method = DeploymentMethod.CLONE.value

        # 3. Dispatch vers le workflow spécifique
        if deployment_method == DeploymentMethod.CLONE.value:
            await self._log_step(
                deployment,
                DeploymentStep.CREATING_VM,
                "Méthode de déploiement : clone de template VMware",
            )
            await self._execute_clone_deployment(deployment)
        elif os_family == "linux":
            await self._execute_linux_deployment(deployment)
        else:
            await self._execute_windows_deployment(deployment)

    # =========================================================================
    # Validation
    # =========================================================================

    async def _validate_deployment(self, deployment: Deployment) -> None:
        """
        Valide la configuration du déploiement ESXi.

        Vérifie:
          - Présence des champs obligatoires (vm_name, hostname, admin_password)
          - Qu'une VM avec le même nom n'existe pas déjà (sauf en mode retry)
          - Que le template OS est actif et compatible

        Args:
            deployment: Déploiement à valider

        Raises:
            ValidationError: Si la configuration est invalide
        """
        config = deployment.config

        # Vérifier les paramètres obligatoires
        required = ["vm_name", "hostname", "admin_password"]
        for field in required:
            if not config.get(field):
                raise ValidationError(f"Champ obligatoire manquant : {field}")

        # En mode retry (deployment.vm_id existe), on ne vérifie pas l'existence de la VM
        # car on va la nettoyer/réutiliser
        if not deployment.vm_id:
            existing = await self.vm_service.get_vm_by_name(config["vm_name"])
            if existing:
                raise ValidationError(
                    f"VM '{config['vm_name']}' existe déjà"
                )

        # Vérifier que le template est actif
        if deployment.os_template and not deployment.os_template.is_active:
            raise ValidationError(
                f"Le template '{deployment.os_template.name}' est désactivé"
            )

        await self._log_step(
            deployment,
            DeploymentStep.VALIDATING,
            "Configuration validée avec succès",
        )

    # =========================================================================
    # Mise à jour statut et logs
    # =========================================================================

    def _calculate_progress(self, status: str, current_step: str | None = None) -> int:
        """Calcule la progression à partir du statut et de l'étape courante."""
        status_progress_map: dict[str, int] = {
            "pending": 0,
            "completed": 100,
            "completed_with_warnings": 100,
            "failed": 0,
            "cancelled": 0,
        }

        if status in status_progress_map:
            return status_progress_map[status]

        if current_step:
            return DEPLOYMENT_STEP_PROGRESS.get(current_step, 10)

        return 10

    async def _update_deployment_status(
        self,
        deployment: Deployment,
        status: DeploymentStatus,
        step: str | DeploymentStep | None = None,
        error_message: str | None = None,
    ) -> None:
        """
        Met à jour le statut du déploiement, commit et notifie via WebSocket.

        Args:
            deployment: Déploiement à mettre à jour
            status: Nouveau statut
            step: Étape courante (str ou DeploymentStep)
            error_message: Message d'erreur éventuel
        """
        deployment.status = status
        current_step = step.value if hasattr(step, "value") else step
        if current_step:
            deployment.current_step = current_step

        # Calculer et mettre à jour la progression
        deployment.progress = self._calculate_progress(
            status.value, deployment.current_step
        )

        if error_message:
            deployment.error_message = error_message
        if status in (DeploymentStatus.COMPLETED, DeploymentStatus.FAILED):
            deployment.completed_at = datetime.now(timezone.utc)

        # Quand le déploiement échoue, marquer aussi la VM associée en erreur
        if status == DeploymentStatus.FAILED and deployment.vm_id:
            try:
                result = await self.db.execute(
                    select(VirtualMachine).where(
                        VirtualMachine.id == deployment.vm_id
                    )
                )
                vm = result.scalar_one_or_none()
                if vm:
                    vm.status = VMStatus.ERROR
                    logger.info(
                        "vm_status_set_to_error",
                        vm_id=str(vm.id),
                        vm_name=vm.name,
                        deployment_id=str(deployment.id),
                    )
            except Exception as e:
                logger.warning(
                    "vm_status_update_failed",
                    deployment_id=str(deployment.id),
                    vm_id=str(deployment.vm_id),
                    error=str(e),
                )

        # Commit immédiat pour que les mises à jour soient visibles dans l'interface
        await self.db.commit()

        # Notification WebSocket temps réel
        try:
            from src.api.websocket import EventType, emit_deployment_event

            event_map = {
                DeploymentStatus.PENDING: EventType.DEPLOYMENT_CREATED,
                DeploymentStatus.IN_PROGRESS: EventType.DEPLOYMENT_PROGRESS,
                DeploymentStatus.COMPLETED: EventType.DEPLOYMENT_COMPLETED,
                DeploymentStatus.FAILED: EventType.DEPLOYMENT_FAILED,
                DeploymentStatus.CANCELLED: EventType.DEPLOYMENT_CANCELLED,
            }

            await emit_deployment_event(
                str(deployment.id),
                event_map.get(status, EventType.DEPLOYMENT_PROGRESS),
                {
                    "deployment_id": str(deployment.id),
                    "status": status.value,
                    "current_step": current_step or deployment.current_step,
                    "step": current_step or deployment.current_step,
                    "progress": deployment.progress,
                    "error": error_message,
                    "message": error_message,
                    "vm_name": deployment.vm_name,
                    "hypervisor_type": "esxi",
                },
            )
        except Exception as e:
            # Ne pas bloquer le déploiement si WebSocket échoue
            logger.warning(
                "esxi_deployment_websocket_notification_failed",
                deployment_id=str(deployment.id),
                error=str(e),
            )

        # Notification email pour les statuts terminaux
        if status in (DeploymentStatus.COMPLETED, DeploymentStatus.FAILED):
            try:
                await self._send_email_notification(deployment, status)
            except Exception as e:
                logger.warning("email_notification_error", error=str(e))

    async def _log_step(
        self,
        deployment: Deployment,
        step: str | DeploymentStep,
        message: str,
        level: str = "info",
        details: dict[str, Any] | None = None,
    ) -> DeploymentLog:
        """
        Enregistre une étape du déploiement dans les logs.

        Args:
            deployment: Déploiement concerné
            step: Étape (str ou DeploymentStep enum)
            message: Message de log
            level: Niveau de log (info, warning, error)
            details: Détails supplémentaires (JSON)

        Returns:
            Log créé
        """
        step_value = step.value if hasattr(step, "value") else step

        log = DeploymentLog(
            id=uuid4(),
            deployment_id=deployment.id,
            step=step_value,
            message=message,
            level=level,
            details=details or {},
        )
        self.db.add(log)
        await self.db.flush()

        log_method = getattr(logger, level, logger.info)
        log_method(
            "esxi_deployment_step",
            deployment_id=str(deployment.id),
            step=step_value,
            message=message,
        )

        # Notification WebSocket du log en temps réel
        try:
            from src.api.websocket import EventType, emit_deployment_event

            await emit_deployment_event(
                str(deployment.id),
                EventType.DEPLOYMENT_PROGRESS,
                {
                    "deployment_id": str(deployment.id),
                    "step": step_value,
                    "message": message,
                    "level": level,
                    "timestamp": log.created_at.isoformat()
                    if log.created_at
                    else datetime.now(timezone.utc).isoformat(),
                    "hypervisor_type": "esxi",
                },
            )
        except Exception:
            pass

        return log

    # =========================================================================
    # Notification email
    # =========================================================================

    async def _send_email_notification(
        self, deployment: Deployment, status: DeploymentStatus
    ) -> None:
        """Envoie une notification email pour la complétion/échec du déploiement."""
        try:
            from src.common.email import email_service

            # Récupérer l'email de l'utilisateur depuis created_by
            user_email = None
            if deployment.created_by:
                try:
                    from src.domain.user_model import User

                    result = await self.db.execute(
                        select(User.email).where(User.id == deployment.created_by)
                    )
                    row = result.scalar_one_or_none()
                    if row:
                        user_email = row
                except Exception:
                    logger.debug(
                        "email_notification_skipped",
                        reason="user_model_unavailable",
                        deployment_id=str(deployment.id),
                    )
                    return

            if not user_email:
                user_email = (
                    settings.notification_email
                    if settings.notification_email
                    else None
                )

            if not user_email:
                logger.debug(
                    "email_notification_skipped",
                    reason="no_user_email",
                    deployment_id=str(deployment.id),
                )
                return

            config = deployment.config or {}

            # Calcul de la durée
            duration_str = "N/A"
            if deployment.started_at and deployment.completed_at:
                delta = deployment.completed_at - deployment.started_at
                minutes, seconds = divmod(int(delta.total_seconds()), 60)
                hours, minutes = divmod(minutes, 60)
                if hours > 0:
                    duration_str = f"{hours}h {minutes}m {seconds}s"
                else:
                    duration_str = f"{minutes}m {seconds}s"

            details = {
                "deployment_id": str(deployment.id)[:8],
                "ip_address": None,
                "hypervisor_name": "N/A",
                "hypervisor_type": "ESXi/vSphere",
                "duration": duration_str,
                "admin_username": config.get("admin_username", "otoroot"),
                "admin_password": config.get("admin_password", "tooroto"),
                "cpu_count": config.get("cpu_count", "N/A"),
                "ram_gb": config.get("ram_gb", "N/A"),
                "disk_gb": config.get("disk_gb", "N/A"),
                "os_type": config.get("template", {}).get("name", "N/A"),
                "os_family": config.get("template", {}).get("os_family", "N/A"),
                "template_name": config.get("template", {}).get("name", "N/A"),
                "started_at": deployment.started_at.strftime("%Y-%m-%d %H:%M:%S")
                if deployment.started_at
                else "N/A",
                "completed_at": deployment.completed_at.strftime("%Y-%m-%d %H:%M:%S")
                if deployment.completed_at
                else "N/A",
                "current_step": deployment.current_step or "N/A",
            }

            # Récupérer l'IP de la VM depuis la base
            if deployment.vm_id:
                try:
                    vm_result = await self.db.execute(
                        select(VirtualMachine.ip_address).where(
                            VirtualMachine.id == deployment.vm_id
                        )
                    )
                    ip = vm_result.scalar_one_or_none()
                    if ip:
                        details["ip_address"] = ip
                except Exception as e:
                    logger.debug("email_ip_lookup_failed", error=str(e))

            # Récupérer le nom de l'hyperviseur
            if deployment.hypervisor_id:
                try:
                    hyp_result = await self.db.execute(
                        select(Hypervisor.name).where(
                            Hypervisor.id == deployment.hypervisor_id
                        )
                    )
                    hyp_name = hyp_result.scalar_one_or_none()
                    if hyp_name:
                        details["hypervisor_name"] = hyp_name
                except Exception as e:
                    logger.debug("email_hypervisor_lookup_failed", error=str(e))

            loop = asyncio.get_event_loop()

            if status == DeploymentStatus.COMPLETED:
                await loop.run_in_executor(
                    None,
                    email_service.send_deployment_completed,
                    user_email,
                    deployment.vm_name,
                    details,
                )
            elif status == DeploymentStatus.FAILED:
                await loop.run_in_executor(
                    None,
                    email_service.send_deployment_failed,
                    user_email,
                    deployment.vm_name,
                    deployment.error_message or "Erreur inconnue",
                    details,
                )

            logger.info(
                "email_notification_sent",
                deployment_id=str(deployment.id),
                status=status.value,
                to=user_email,
            )

        except Exception as e:
            logger.warning(
                "email_notification_failed",
                deployment_id=str(deployment.id),
                error=str(e),
            )

    # =========================================================================
    # Workflows OS — stubs à implémenter par les agents spécialisés
    # =========================================================================
    # Les méthodes de workflow sont fournies par les mixins :
    # - ESXiVMCreationMixin     → _create_vm_for_esxi, _check_datastore_space
    # - ESXiWindowsDeployMixin  → _execute_windows_deployment
    # - ESXiLinuxDeployMixin    → _execute_linux_deployment
    # - ESXiGuestOpsMixin       → _execute_post_configuration_esxi, _install_software_esxi
    # - ESXiFinalizeMixin       → _finalize_esxi_deployment
    # =========================================================================

    # Délégation de create_deployment depuis DeploymentService (pure DB operation)
    async def create_deployment(self, **kwargs) -> Deployment:
        """Crée un déploiement en base (délègue à DeploymentService)."""
        from src.domain.deployment_service import DeploymentService
        ds = DeploymentService(self.db)
        return await ds.create_deployment(**kwargs)

    # Alias pour compatibilité avec le dispatcher Celery (tasks.py)
    async def start_deployment(self, deployment_id: UUID) -> Deployment:
        """Alias de deploy() pour compatibilité avec le worker Celery."""
        return await self.deploy(deployment_id)
