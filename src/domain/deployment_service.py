# =============================================================================
# VM Automation - Deployment Service
# =============================================================================
"""
Service pour orchestrer le déploiement complet de VMs.
Gère le workflow: création VM -> installation OS -> post-configuration.
"""

import asyncio
import shlex
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

# Vérifier la disponibilité de paramiko pour les connexions SSH (Linux VMs)
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
from src.domain.models import (
    Deployment,
    DeploymentLog,
    DeploymentStatus,
    Hypervisor,
    OSTemplate,
    VirtualMachine,
    VMState,
    VMStatus,
)
from src.domain.template_engine import get_template_engine
from src.domain.vm_service import VMService
from src.integrations.hypervisors import HyperVClient
from src.integrations.hypervisors.hyperv_client import _escape_ps

logger = get_logger(__name__)


class DeploymentStep(str, Enum):
    """Étapes du déploiement."""

    VALIDATING = "validating"
    CREATING_VM = "creating_vm"
    CONFIGURING_NETWORK = "configuring_network"
    MOUNTING_ISO = "mounting_iso"
    GENERATING_UNATTEND = "generating_unattend"
    STARTING_INSTALLATION = "starting_installation"
    WAITING_INSTALLATION = "waiting_installation"
    WAITING_VM_READY = "waiting_vm_ready"
    POST_CONFIGURATION = "post_configuration"
    INSTALLING_SOFTWARE = "installing_software"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"

    # Étapes spécifiques Linux
    GENERATING_SEED_CONFIG = "generating_seed_config"
    CREATING_SEED_ISO = "creating_seed_iso"
    WAITING_SSH_READY = "waiting_ssh_ready"
    LINUX_POST_INSTALL = "linux_post_install"


def _detect_windows_edition(template_name: str) -> str:
    """Détecte l'édition Windows depuis le nom du template."""
    name = template_name.lower()
    if "server" in name:
        if "2019" in name:
            return "Windows Server 2019 SERVERSTANDARD"
        if "2025" in name:
            return "Windows Server 2025 SERVERSTANDARD"
        return "Windows Server 2022 SERVERSTANDARD"
    if "11" in name:
        return "Windows 11 Pro"
    if "10" in name:
        return "Windows 10 Pro"
    return "Windows 11 Pro"


# Mapping des éditions Windows vers l'index WIM dans les ISOs multi-édition.
# Les ISOs consumer (Win10/11) contiennent typiquement :
#   1=Home, 2=Home N, 3=Education, 4=Education N, 5=Pro, 6=Pro N
# Les ISOs Server n'ont généralement que 1-2 éditions (Standard, Datacenter).
_WIM_INDEX_MAP = {
    "windows 10 home": 1,
    "windows 10 home n": 2,
    "windows 10 education": 3,
    "windows 10 education n": 4,
    "windows 10 pro": 5,
    "windows 10 pro n": 6,
    "windows 11 home": 1,
    "windows 11 home n": 2,
    "windows 11 education": 3,
    "windows 11 education n": 4,
    "windows 11 pro": 5,
    "windows 11 pro n": 6,
}


def _get_wim_image_index(windows_edition: str) -> int:
    """Retourne l'index WIM pour une édition Windows donnée."""
    edition_lower = windows_edition.lower().strip()
    if edition_lower in _WIM_INDEX_MAP:
        return _WIM_INDEX_MAP[edition_lower]
    # Server editions: Standard=2 (Desktop Experience), Core=1
    if "server" in edition_lower:
        return 2
    # Fallback: Pro = index 5 pour les ISOs consumer
    return 5


def _build_admin_credentials(admin_password: str, config: dict | None = None) -> list[tuple[str, str]]:
    """Build list of admin credential pairs to try.

    If ``admin_username`` is provided in *config*, only that username is used.
    Otherwise falls back to trying both the French ("Administrateur") and
    English ("Administrator") built-in admin account names for backward
    compatibility.
    """
    admin_username = None
    if config:
        admin_username = config.get("admin_username")
    # Also allow a global setting from the app config
    if not admin_username and hasattr(settings, "admin_username"):
        admin_username = getattr(settings, "admin_username", None)

    if admin_username:
        return [
            (f".\\{admin_username}", admin_password),
        ]
    return [
        (".\\otoroot", admin_password),          # Default custom account
        (".\\Administrateur", admin_password),  # Windows FR built-in (Server)
        (".\\Administrator", admin_password),    # Windows EN built-in (Server)
    ]


class DeploymentService:
    """
    Service pour orchestrer les déploiements de VMs.

    Workflow complet:
    1. Validation des paramètres
    2. Création de la VM
    3. Configuration réseau
    4. Génération du fichier d'installation automatique
    5. Montage de l'ISO
    6. Démarrage de l'installation
    7. Attente de la fin d'installation
    8. Post-configuration
    9. Finalisation
    """

    @staticmethod
    def _sanitize_hostname(name: str) -> str:
        """Convert a VM name into a valid hostname (RFC 952, max 15 chars for Windows)."""
        import re
        # Replace underscores and non-alphanumeric chars with hyphens
        h = re.sub(r'[^a-zA-Z0-9]', '-', name)
        # Collapse multiple hyphens
        h = re.sub(r'-+', '-', h)
        # Strip leading/trailing hyphens
        h = h.strip('-')
        # Truncate to 15 chars, avoid trailing hyphen after truncation
        h = h[:15].rstrip('-')
        # Fallback if empty
        return h or "VM"

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialise le service.

        Args:
            db: Session de base de données
        """
        self.db = db
        self.vm_service = VMService(db)
        self.template_engine = get_template_engine()

    async def _log_step(
        self,
        deployment: Deployment,
        step: str,
        message: str,
        level: str = "info",
        details: dict[str, Any] | None = None,
    ) -> DeploymentLog:
        """Enregistre un log de déploiement."""
        log = DeploymentLog(
            id=uuid4(),
            deployment_id=deployment.id,
            step=step,
            message=message,
            level=level,
            details=details or {},
        )
        self.db.add(log)
        await self.db.flush()
        
        log_method = getattr(logger, level, logger.info)
        log_method(
            "deployment_step",
            deployment_id=str(deployment.id),
            step=step,
            message=message,
        )
        
        return log

    def _calculate_progress(self, status: str, current_step: str | None = None) -> int:
        """Calcule la progression à partir du statut et de l'étape courante."""
        # Mapping statut -> progression (pour les statuts terminaux)
        status_progress_map: dict[str, int] = {
            "pending": 0,
            "completed": 100,
            "failed": 0,
            "cancelled": 0,
        }
        
        # Statuts terminaux ont une progression fixe
        if status in status_progress_map:
            return status_progress_map[status]

        # Pour les statuts en cours, utiliser current_step
        if current_step:
            return DEPLOYMENT_STEP_PROGRESS.get(current_step, 10)
        
        # Fallback pour in_progress sans step
        return 10

    async def _update_deployment_status(
        self,
        deployment: Deployment,
        status: DeploymentStatus,
        current_step: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Met à jour le statut du déploiement, commit et notifie via WebSocket."""
        deployment.status = status
        if current_step:
            deployment.current_step = current_step
        
        # Calculer et mettre à jour la progression
        deployment.progress = self._calculate_progress(status.value, deployment.current_step)
        
        if error_message:
            deployment.error_message = error_message
        if status in (DeploymentStatus.COMPLETED, DeploymentStatus.FAILED):
            deployment.completed_at = datetime.now(timezone.utc)

        # When deployment fails, also update the associated VM status to ERROR
        if status == DeploymentStatus.FAILED and deployment.vm_id:
            try:
                result = await self.db.execute(
                    select(VirtualMachine).where(VirtualMachine.id == deployment.vm_id)
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
            from src.api.websocket import emit_deployment_event, EventType
            
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
                    "step": current_step or deployment.current_step,  # Compatibilité
                    "progress": deployment.progress,
                    "error": error_message,
                    "message": error_message,  # Compatibilité
                    "vm_name": deployment.vm_name,
                }
            )
        except Exception as e:
            # Ne pas bloquer le déploiement si WebSocket échoue
            logger.warning(
                "deployment_websocket_notification_failed",
                deployment_id=str(deployment.id),
                error=str(e),
            )

        # Email notification for terminal states
        if status in (DeploymentStatus.COMPLETED, DeploymentStatus.FAILED):
            try:
                await self._send_email_notification(deployment, status)
            except Exception as e:
                logger.warning("email_notification_error", error=str(e))

    async def _send_email_notification(self, deployment: Deployment, status: DeploymentStatus) -> None:
        """Send email notification for deployment completion/failure."""
        try:
            from src.common.email import email_service

            # Get user email from deployment.created_by
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
                    logger.debug("email_notification_skipped", reason="user_model_unavailable", deployment_id=str(deployment.id))
                    return

            if not user_email:
                # Fallback to notification_email from config
                user_email = settings.notification_email if settings.notification_email else None

            if not user_email:
                logger.debug("email_notification_skipped", reason="no_user_email", deployment_id=str(deployment.id))
                return

            config = deployment.config or {}

            # Calculate duration
            duration_str = "N/A"
            if deployment.started_at and deployment.completed_at:
                delta = deployment.completed_at - deployment.started_at
                minutes, seconds = divmod(int(delta.total_seconds()), 60)
                hours, minutes = divmod(minutes, 60)
                if hours > 0:
                    duration_str = f"{hours}h {minutes}m {seconds}s"
                else:
                    duration_str = f"{minutes}m {seconds}s"

            # Build details dict
            details = {
                "deployment_id": str(deployment.id)[:8],
                "ip_address": None,
                "hypervisor_name": "N/A",
                "duration": duration_str,
                "admin_username": config.get("admin_username", "otoroot"),
                "admin_password": config.get("admin_password", "tooroto"),
                "cpu_count": config.get("cpu_count", "N/A"),
                "ram_gb": config.get("ram_gb", "N/A"),
                "disk_gb": config.get("disk_gb", "N/A"),
                "os_type": config.get("template", {}).get("name", "N/A"),
                "os_family": config.get("template", {}).get("os_family", "N/A"),
                "network_switch": config.get("network_switch", "N/A"),
                "template_name": config.get("template", {}).get("name", "N/A"),
                "started_at": deployment.started_at.strftime("%Y-%m-%d %H:%M:%S") if deployment.started_at else "N/A",
                "completed_at": deployment.completed_at.strftime("%Y-%m-%d %H:%M:%S") if deployment.completed_at else "N/A",
                "current_step": deployment.current_step or "N/A",
            }

            # Try to get VM IP from DB
            if deployment.vm_id:
                try:
                    vm_result = await self.db.execute(
                        select(VirtualMachine.ip_address).where(VirtualMachine.id == deployment.vm_id)
                    )
                    ip = vm_result.scalar_one_or_none()
                    if ip:
                        details["ip_address"] = ip
                except Exception as e:
                    logger.debug("email_ip_lookup_failed", error=str(e))

            # Try to get hypervisor name from DB
            if deployment.hypervisor_id:
                try:
                    hyp_result = await self.db.execute(
                        select(Hypervisor.name).where(Hypervisor.id == deployment.hypervisor_id)
                    )
                    hyp_name = hyp_result.scalar_one_or_none()
                    if hyp_name:
                        details["hypervisor_name"] = hyp_name
                except Exception as e:
                    logger.debug("email_hypervisor_lookup_failed", error=str(e))

            # Send in background to not block deployment
            loop = asyncio.get_running_loop()

            if status == DeploymentStatus.COMPLETED:
                await loop.run_in_executor(
                    None,
                    email_service.send_deployment_completed,
                    user_email, deployment.vm_name, details,
                )
            elif status == DeploymentStatus.FAILED:
                await loop.run_in_executor(
                    None,
                    email_service.send_deployment_failed,
                    user_email, deployment.vm_name, deployment.error_message or "Unknown error", details,
                )

            logger.info("email_notification_sent", deployment_id=str(deployment.id), status=status.value, to=user_email)

        except Exception as e:
            logger.warning("email_notification_failed", deployment_id=str(deployment.id), error=str(e))

    async def create_deployment(
        self,
        vm_name: str,
        hypervisor_id: UUID,
        template_id: UUID,
        cpu_count: int = 2,
        ram_gb: int = 4,
        disk_gb: int = 60,
        vhdx_path: str | None = None,
        network_switch: str | None = None,
        ip_config: dict[str, Any] | None = None,
        admin_password: str | None = None,
        hostname: str | None = None,
        domain_join: dict[str, Any] | None = None,
        services: dict[str, Any] | None = None,
        security: dict[str, Any] | None = None,
        software_profile: str | None = None,
        packages: list[str] | None = None,
        package_configs: dict[str, dict[str, Any]] | None = None,
        enable_windows_update: bool = False,
        post_install_commands: list[str] | None = None,
        **kwargs: Any,
    ) -> Deployment:
        """
        Crée un nouveau déploiement.
        
        Args:
            vm_name: Nom de la VM
            hypervisor_id: ID de l'hyperviseur
            template_id: ID du template OS
            cpu_count: Nombre de CPUs
            ram_gb: RAM en GB
            disk_gb: Disque en GB
            network_switch: Switch réseau
            ip_config: Configuration IP (static_ip, ip_address, gateway, dns, etc.)
            admin_password: Mot de passe administrateur
            hostname: Nom d'hôte (défaut: vm_name)
            domain_join: Configuration de jonction AD
            services: Configuration des services (RDP, WinRM, SSH)
            security: Configuration de sécurité (politiques de mot de passe)
            software_profile: Profil logiciel (minimal, tools, development, etc.)
            packages: Packages Chocolatey supplémentaires
            package_configs: Configurations des packages (ex: {'zabbix-agent2': {'server': '192.168.1.1'}})
            enable_windows_update: Installer les mises à jour Windows
            post_install_commands: Commandes post-installation personnalisées
            
        Returns:
            Déploiement créé
        """
        # Vérifier que l'hyperviseur existe
        hypervisor = await self.vm_service.get_hypervisor(hypervisor_id)
        
        # Vérifier que le template existe
        template = await self.vm_service.get_template(template_id)
        
        # Configuration par défaut des services si non spécifiée
        default_services = {
            "enable_rdp": True,
            "enable_winrm": True,
            "enable_ssh": False,
        }
        
        # Username par défaut : otoroot partout
        default_admin_username = "otoroot"

        # Préparer la configuration
        resolved_username = kwargs.pop("admin_username", None) or default_admin_username
        config = {
            "vm_name": vm_name,
            "hostname": hostname or self._sanitize_hostname(vm_name),
            "cpu_count": cpu_count,
            "ram_gb": ram_gb,
            "disk_gb": disk_gb,
            "vhdx_path": vhdx_path,  # Emplacement personnalisé du VHDX
            "network_switch": network_switch or settings.hyperv_default_switch,
            "admin_password": admin_password or settings.default_admin_password.get_secret_value(),
            "admin_username": resolved_username,
            "username": resolved_username,  # Alias pour le code Linux SSH
            "ip_config": ip_config or {},
            "domain_join": domain_join,
            "services": services or default_services,
            "security": security or {},
            "software_profile": software_profile,
            "packages": packages or [],
            "package_configs": package_configs or {},
            "enable_windows_update": enable_windows_update,
            "post_install_commands": post_install_commands or [],
            "template": {
                "id": str(template.id),
                "name": template.name,
                "os_family": template.os_family,
                "iso_path": template.iso_path,
            },
            **kwargs,
        }
        
        # Créer le déploiement
        deployment = Deployment(
            id=uuid4(),
            vm_name=vm_name,
            hypervisor_id=hypervisor_id,
            os_template_id=template_id,
            status=DeploymentStatus.PENDING,
            current_step=DeploymentStep.VALIDATING,
            config=config,
        )
        
        self.db.add(deployment)
        await self.db.flush()
        
        logger.info(
            "deployment_created",
            deployment_id=str(deployment.id),
            vm_name=vm_name,
            template=template.name,
        )
        
        return deployment

    async def start_deployment(self, deployment_id: UUID) -> Deployment:
        """
        Démarre l'exécution d'un déploiement.
        
        Args:
            deployment_id: ID du déploiement
            
        Returns:
            Déploiement mis à jour
        """
        # Récupérer le déploiement
        result = await self.db.execute(
            select(Deployment).where(Deployment.id == deployment_id)
        )
        deployment = result.scalar_one_or_none()
        
        if not deployment:
            raise NotFoundError("Deployment", str(deployment_id))
        
        # Permettre le démarrage si PENDING, FAILED, ou IN_PROGRESS (reprise après queue)
        if deployment.status not in (DeploymentStatus.PENDING, DeploymentStatus.FAILED, DeploymentStatus.IN_PROGRESS):
            raise ValidationError(
                f"Cannot start deployment in status {deployment.status}"
            )
        
        # Marquer comme en cours et effacer l'erreur précédente
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
            # Exécuter le workflow
            await self._execute_deployment(deployment)
            
        except Exception as e:
            logger.error(
                "deployment_failed",
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
                f"Deployment failed: {e}",
                "error",
            )
        
        return deployment

    async def _execute_deployment(self, deployment: Deployment) -> None:
        """
        Exécute le workflow complet de déploiement.

        Dispatche vers le workflow Windows (DISM) ou Linux (ISO + seed)
        en fonction de la famille d'OS du template.

        Workflow Windows (DISM):
        1. Validation
        2. Création VM (VHDX vide)
        3. Déploiement DISM
        4. Configuration réseau (via unattend)
        5. Démarrage VM
        6. Attente VM prête (heartbeat + PowerShell Direct)
        7. Post-configuration (services, sécurité)
        8. Installation logiciels
        9. Finalisation

        Workflow Linux (ISO + seed config):
        1. Validation
        2. Création VM
        3. Génération config (preseed/kickstart/autoinstall)
        4. Montage ISO + seed
        5. Démarrage VM
        6. Attente installation (SSH)
        7. Post-installation via SSH
        8. Installation paquets
        9. Finalisation
        """
        config = deployment.config

        # Détecter la famille d'OS pour dispatcher vers le bon workflow
        template_config = config.get("template") or {}
        os_family = template_config.get("os_family", "windows")
        # Normaliser: peut être un enum OSFamily ou une string
        if hasattr(os_family, "value"):
            os_family = os_family.value
        os_family = str(os_family).lower()

        # 1. Validation
        await self._log_step(deployment, DeploymentStep.VALIDATING, "Validation de la configuration")
        await self._validate_deployment(deployment)

        # 1b. Vérification espace disque sur l'hyperviseur
        try:
            client = await self.vm_service._get_hypervisor_client(deployment.hypervisor_id)
            disk_gb = config.get("disk_gb", template_config.get("min_disk_gb", 40))
            # Exiger au moins 2x la taille du disque VM (VHDX + ISO temp + marge)
            required_gb = float(disk_gb) * 2
            disk_info = await client.check_disk_space(required_gb=required_gb)
            await self._log_step(
                deployment, DeploymentStep.VALIDATING,
                f"Espace disque OK sur {disk_info.get('drive_letter', '?')}: — "
                f"{disk_info.get('free_gb', 0):.1f} Go libre "
                f"(requis: {required_gb:.0f} Go)",
            )
            # Créer les dossiers de stockage si nécessaire
            await client.ensure_paths_exist()
        except Exception as e:
            error_msg = f"Vérification espace disque échouée : {e}"
            await self._log_step(deployment, DeploymentStep.VALIDATING, error_msg, "error")
            await self._update_deployment_status(
                deployment, DeploymentStatus.FAILED, DeploymentStep.VALIDATING, error_msg,
            )
            return

        if os_family == "linux":
            await self._execute_linux_deployment(deployment)
            return

        # === Workflow Windows (DISM) ===

        # 2. Création de la VM (VHDX vide, sans ISO)
        # Si deployment.vm_id existe (retry), _create_vm_for_dism va nettoyer la VM existante
        # et en créer une nouvelle pour garantir un état propre
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.CREATING_VM
        )
        await self._log_step(deployment, DeploymentStep.CREATING_VM, f"Creating VM: {config['vm_name']}")
        vm = await self._create_vm_for_dism(deployment)
        # Mettre à jour deployment.vm_id (peut être nouveau si retry)
        deployment.vm_id = vm.id
        # Commit immédiat pour persister le vm_id
        await self.db.commit()
        
        # 3. Déploiement DISM (applique l'image Windows directement)
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.MOUNTING_ISO
        )
        await self._log_step(
            deployment, 
            DeploymentStep.MOUNTING_ISO, 
            "Applying Windows image via DISM (fast deployment)"
        )
        await self._deploy_with_dism(deployment, vm)
        
        # 4. Configuration réseau (déjà fait par DISM via unattend)
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.CONFIGURING_NETWORK
        )
        await self._log_step(deployment, DeploymentStep.CONFIGURING_NETWORK, "Network pre-configured")
        
        # 5. Démarrage de la VM
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.STARTING_INSTALLATION
        )
        await self._log_step(deployment, DeploymentStep.STARTING_INSTALLATION, "Starting VM")
        await self.vm_service.start_vm(vm.id)
        
        # 6. Attendre que la VM soit prête (heartbeat + PowerShell Direct)
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.WAITING_VM_READY
        )
        await self._log_step(
            deployment, DeploymentStep.WAITING_VM_READY, 
            "Waiting for Windows to complete OOBE and become accessible..."
        )
        
        vm_ready = await self._wait_for_vm_ready(deployment, vm)

        if not vm_ready:
            # VM not accessible via PowerShell Direct but may still be running fine
            # Continue deployment with warning instead of failing
            logger.warning(
                "deployment_vm_not_accessible_continuing",
                deployment_id=str(deployment.id),
                vm_name=deployment.vm_name,
            )
            await self._log_step(
                deployment, DeploymentStep.WAITING_VM_READY,
                "VM not accessible via PowerShell Direct - VM is likely running but remote management unavailable. Continuing deployment with warning.",
                "warning"
            )
        else:
            await self._log_step(
                deployment, DeploymentStep.WAITING_VM_READY,
                "VM is ready and accessible via PowerShell Direct"
            )

        # 7. Post-configuration (services, sécurité, etc.)
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.POST_CONFIGURATION
        )
        if vm_ready:
            await self._log_step(
                deployment, DeploymentStep.POST_CONFIGURATION,
                "Configuring services and security settings..."
            )
            await self._execute_post_configuration(deployment, vm)
        else:
            await self._log_step(
                deployment, DeploymentStep.POST_CONFIGURATION,
                "Skipping post-configuration (PowerShell Direct unavailable) - VM is running, configure manually if needed.",
                "warning"
            )
        
        # 8. Installation des logiciels
        software_profile = config.get("software_profile")
        packages = config.get("packages", [])

        if (software_profile or packages) and vm_ready:
            await self._update_deployment_status(
                deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.INSTALLING_SOFTWARE
            )
            await self._log_step(
                deployment, DeploymentStep.INSTALLING_SOFTWARE,
                f"Installing software (profile: {software_profile or 'custom'})..."
            )
            await self._install_software(deployment, vm)
        elif (software_profile or packages) and not vm_ready:
            await self._update_deployment_status(
                deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.INSTALLING_SOFTWARE
            )
            await self._log_step(
                deployment, DeploymentStep.INSTALLING_SOFTWARE,
                "Skipping software installation (PowerShell Direct unavailable) - install manually if needed.",
                "warning"
            )

        # 9. Finalisation
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.FINALIZING
        )
        await self._log_step(deployment, DeploymentStep.FINALIZING, "Finalizing deployment...")
        await self._finalize_deployment(deployment, vm)

        # Terminé !
        if vm_ready:
            final_status = DeploymentStatus.COMPLETED
            final_message = "Deployment completed successfully. VM is ready for use."
        else:
            final_status = DeploymentStatus.COMPLETED_WITH_WARNINGS
            final_message = "Deployment completed with warnings. VM is running but PowerShell Direct was unavailable - post-configuration was skipped."

        await self._update_deployment_status(
            deployment,
            final_status,
            DeploymentStep.COMPLETED,
        )
        await self._log_step(
            deployment,
            DeploymentStep.COMPLETED,
            final_message,
        )
        
        logger.info(
            "deployment_completed_full",
            deployment_id=str(deployment.id),
            vm_id=str(vm.id),
            software_installed=bool(software_profile or packages),
        )

    # =========================================================================
    # Workflow Linux
    # =========================================================================

    def _determine_config_type(self, template_config: dict) -> str:
        """Détermine le type de configuration Linux selon le template OS.

        Returns:
            ``"preseed"``, ``"kickstart"``, ``"autoinstall"`` ou ``"cloud-init"``
        """
        os_type = template_config.get("os_type", "").lower()
        template_name = template_config.get("name", "").lower()
        # Combiner os_type et name pour une détection plus large
        combined = f"{os_type} {template_name}"

        if "ubuntu" in combined:
            return "autoinstall"
        elif "debian" in combined:
            return "preseed"
        elif any(x in combined for x in ("rhel", "rocky", "centos", "alma", "fedora")):
            return "kickstart"
        else:
            return "cloud-init"  # fallback générique

    # Ordre des étapes Linux pour la logique de reprise
    _LINUX_STEP_ORDER = [
        DeploymentStep.VALIDATING,
        DeploymentStep.CREATING_VM,
        DeploymentStep.MOUNTING_ISO,
        DeploymentStep.STARTING_INSTALLATION,
        DeploymentStep.CONFIGURING_NETWORK,
        DeploymentStep.WAITING_VM_READY,
        DeploymentStep.POST_CONFIGURATION,
        DeploymentStep.INSTALLING_SOFTWARE,
        DeploymentStep.FINALIZING,
        DeploymentStep.COMPLETED,
    ]

    def _step_already_done(self, failed_step: str | None, target_step: DeploymentStep) -> bool:
        """Vérifie si target_step a déjà été complétée avant l'échec."""
        if not failed_step:
            return False
        try:
            failed_idx = next(
                i for i, s in enumerate(self._LINUX_STEP_ORDER)
                if s.value == failed_step
            )
            target_idx = next(
                i for i, s in enumerate(self._LINUX_STEP_ORDER)
                if s == target_step
            )
            # L'étape est "done" si on a échoué APRÈS elle
            return target_idx < failed_idx
        except StopIteration:
            return False

    async def _execute_linux_deployment(self, deployment: Deployment) -> None:
        """
        Exécute le workflow de déploiement pour une VM Linux.

        Supporte la reprise intelligente : si le déploiement a déjà échoué
        à une étape avancée (ex: WAITING_VM_READY), les étapes précédentes
        (création VM, montage ISO, démarrage) sont sautées.

        Workflow:
        1. Création VM sur Hyper-V
        2. Génération de la config d'installation (preseed/kickstart/autoinstall)
        3. Montage ISO + seed
        4. Démarrage de la VM
        5. Attente fin d'installation (détection via SSH)
        6. Post-installation via SSH
        7. Installation de paquets supplémentaires
        8. Finalisation (nettoyage, démontage ISO)
        """
        config = deployment.config
        template_config = config.get("template") or {}

        # ── Déterminer le point de reprise ──
        # Si le déploiement a échoué à une étape avancée, on peut sauter
        # les étapes précédentes (la VM existe déjà et peut être en marche)
        failed_step = deployment.current_step
        is_retry = deployment.vm_id is not None and failed_step not in (
            None, DeploymentStep.VALIDATING.value, DeploymentStep.CREATING_VM.value,
        )

        if is_retry:
            await self._log_step(
                deployment, DeploymentStep.VALIDATING,
                f"Reprise du déploiement — échec précédent à l'étape '{failed_step}'",
            )

        # ------------------------------------------------------------------
        # 2. Création de la VM (sautée si déjà faite)
        # ------------------------------------------------------------------
        if is_retry and self._step_already_done(failed_step, DeploymentStep.CREATING_VM):
            # VM déjà créée — la récupérer en DB
            vm_result = await self.db.execute(
                select(VirtualMachine).where(VirtualMachine.id == deployment.vm_id)
            )
            vm = vm_result.scalar_one_or_none()
            if not vm:
                raise DeploymentStepError(
                    DeploymentStep.CREATING_VM.value,
                    f"VM {deployment.vm_id} introuvable en base — impossible de reprendre",
                )
            await self._log_step(
                deployment, DeploymentStep.CREATING_VM,
                f"VM existante réutilisée : {vm.name} (id={vm.id})",
            )
        else:
            await self._update_deployment_status(
                deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.CREATING_VM
            )
            await self._log_step(
                deployment, DeploymentStep.CREATING_VM,
                f"Création de la VM Linux : {config['vm_name']}",
            )
            vm = await self._create_vm_for_linux(deployment)
            deployment.vm_id = vm.id
            await self.db.commit()

        # Récupérer le client Hyper-V
        client = await self.vm_service._get_hypervisor_client(deployment.hypervisor_id)

        # ------------------------------------------------------------------
        # 3. Génération de la seed config + montage ISO (sautée si déjà faite)
        # ------------------------------------------------------------------
        if is_retry and self._step_already_done(failed_step, DeploymentStep.MOUNTING_ISO):
            await self._log_step(
                deployment, DeploymentStep.MOUNTING_ISO,
                "Montage ISO déjà effectué — étape sautée",
            )
        else:
            await self._update_deployment_status(
                deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.MOUNTING_ISO
            )
            config_type = self._determine_config_type(template_config)
            await self._log_step(
                deployment, DeploymentStep.MOUNTING_ISO,
                f"Génération de la configuration {config_type} et montage des ISO",
            )
            await self._deploy_linux_vm(deployment, vm, client, config, template_config)

        # ------------------------------------------------------------------
        # 4. Démarrage de la VM (sauté si déjà en marche)
        # ------------------------------------------------------------------
        if is_retry and self._step_already_done(failed_step, DeploymentStep.STARTING_INSTALLATION):
            # Vérifier si la VM tourne déjà
            vm_identifier = vm.hypervisor_vm_id or vm.name
            try:
                state_result = await client._execute(
                    f"$vm = Get-VM -Name '{vm_identifier}' -ErrorAction SilentlyContinue; "
                    f"if (-not $vm) {{ $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_identifier}' }} }}; "
                    f"if ($vm) {{ $vm.State }}",
                    timeout=15,
                )
                vm_state = state_result.stdout.strip().lower() if state_result.success else ""
                if vm_state == "running":
                    await self._log_step(
                        deployment, DeploymentStep.STARTING_INSTALLATION,
                        "VM déjà en cours d'exécution — démarrage sauté",
                    )
                else:
                    await self._log_step(
                        deployment, DeploymentStep.STARTING_INSTALLATION,
                        f"VM dans l'état '{vm_state}' — redémarrage...",
                    )
                    await self.vm_service.start_vm(vm.id)
            except Exception:
                await self.vm_service.start_vm(vm.id)
        else:
            await self._update_deployment_status(
                deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.STARTING_INSTALLATION
            )
            await self._log_step(
                deployment, DeploymentStep.STARTING_INSTALLATION,
                "Démarrage de la VM — l'installeur Linux va s'exécuter automatiquement",
            )
            await self.vm_service.start_vm(vm.id)

        # ------------------------------------------------------------------
        # 5. Configuration réseau — attente d'une IP
        # ------------------------------------------------------------------
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.CONFIGURING_NETWORK
        )
        await self._log_step(
            deployment, DeploymentStep.CONFIGURING_NETWORK,
            "Attente de l'attribution d'une adresse IP par la VM...",
        )

        # ------------------------------------------------------------------
        # 6. Attente que la VM soit prête (SSH)
        # ------------------------------------------------------------------
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.WAITING_VM_READY
        )

        if is_retry:
            await self._log_step(
                deployment, DeploymentStep.WAITING_VM_READY,
                "Reprise — vérification de l'accessibilité SSH...",
            )
        else:
            await self._log_step(
                deployment, DeploymentStep.WAITING_VM_READY,
                "Attente de la fin de l'installation Linux (vérification SSH)...",
            )

        vm_ready = await self._wait_for_linux_vm_ready(deployment, vm, config)

        if not vm_ready:
            error_msg = (
                "La VM Linux n'est pas accessible via SSH après le timeout. "
                "La configuration post-installation a échoué."
            )
            await self._log_step(
                deployment, DeploymentStep.WAITING_VM_READY,
                error_msg, "error",
            )
            await self._update_deployment_status(
                deployment,
                DeploymentStatus.FAILED,
                DeploymentStep.WAITING_VM_READY,
                error_msg,
            )
            logger.error(
                "deployment_failed_linux_vm_not_ready",
                deployment_id=str(deployment.id),
                vm_name=deployment.vm_name,
            )
            return

        await self._log_step(
            deployment, DeploymentStep.WAITING_VM_READY,
            "VM Linux prête et accessible via SSH",
        )

        # ------------------------------------------------------------------
        # 7. Post-installation via SSH
        # ------------------------------------------------------------------
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.POST_CONFIGURATION
        )
        await self._log_step(
            deployment, DeploymentStep.POST_CONFIGURATION,
            "Exécution de la configuration post-installation via SSH...",
        )

        ip_address = vm.ip_address or ""
        if ip_address:
            await self._execute_linux_post_install(deployment, vm, config, ip_address)

        # ------------------------------------------------------------------
        # 8. Installation de paquets supplémentaires
        # ------------------------------------------------------------------
        packages = config.get("packages", [])
        if packages:
            await self._update_deployment_status(
                deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.INSTALLING_SOFTWARE
            )
            await self._log_step(
                deployment, DeploymentStep.INSTALLING_SOFTWARE,
                f"Installation de {len(packages)} paquet(s) supplémentaire(s)...",
            )
            await self._install_linux_packages(deployment, vm, config, ip_address, packages)

        # ------------------------------------------------------------------
        # 9. Finalisation
        # ------------------------------------------------------------------
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.FINALIZING
        )
        await self._log_step(
            deployment, DeploymentStep.FINALIZING,
            "Finalisation du déploiement Linux...",
        )
        await self._finalize_linux_deployment(deployment, vm, client)

        # Terminé
        await self._update_deployment_status(
            deployment, DeploymentStatus.COMPLETED, DeploymentStep.COMPLETED,
        )
        await self._log_step(
            deployment, DeploymentStep.COMPLETED,
            "Déploiement Linux terminé avec succès. La VM est prête.",
        )

        logger.info(
            "deployment_linux_completed",
            deployment_id=str(deployment.id),
            vm_id=str(vm.id),
            vm_name=deployment.vm_name,
        )

    async def _create_vm_for_linux(self, deployment: Deployment) -> VirtualMachine:
        """
        Crée ou réutilise la VM pour un déploiement Linux.

        En mode retry (deployment.vm_id existe), tente de réutiliser la VM
        existante plutôt que de la supprimer et recréer. Arrête la VM si
        elle tourne, nettoie les DVD montés, et la réinitialise.
        """
        config = deployment.config
        vm_name = config["vm_name"]

        # ── Mode retry : réutiliser la VM existante ──
        if deployment.vm_id:
            vm_result = await self.db.execute(
                select(VirtualMachine).where(VirtualMachine.id == deployment.vm_id)
            )
            db_vm = vm_result.scalar_one_or_none()

            if db_vm:
                try:
                    client = await self.vm_service._get_hypervisor_client(
                        deployment.hypervisor_id
                    )
                    vm_identifier = db_vm.hypervisor_vm_id or db_vm.name
                    hyperv_vm = await client.get_vm(vm_identifier)

                    if hyperv_vm:
                        logger.info(
                            "retry_reusing_existing_linux_vm",
                            deployment_id=str(deployment.id),
                            vm_name=vm_name,
                        )
                        # Arrêter la VM si elle tourne
                        await client._execute(f"""
                        $vm = Get-VM -Name '{_escape_ps(vm_identifier)}' -ErrorAction SilentlyContinue
                        if (-not $vm) {{
                            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{_escape_ps(vm_identifier)}' }}
                        }}
                        if ($vm -and $vm.State -ne 'Off') {{
                            Stop-VM -VMName $vm.Name -Force -TurnOff
                            Start-Sleep -Seconds 2
                        }}
                        # Retirer complètement tous les DVD drives (pas juste démonter)
                        # pour éviter les entrées firmware boot stale sur Gen2
                        Get-VMDvdDrive -VMName $vm.Name | Remove-VMDvdDrive
                        # Nettoyer les ISO seed temporaires
                        $seedIso = "{settings.hyperv_temp_path}\\SeedISO\\{_escape_ps(vm_name)}_seed.iso"
                        if (Test-Path $seedIso) {{ Remove-Item $seedIso -Force }}
                        $seedDir = "{settings.hyperv_temp_path}\\SeedISO\\{_escape_ps(vm_name)}"
                        if (Test-Path $seedDir) {{ Remove-Item $seedDir -Recurse -Force }}
                        # Nettoyer les ISO remastered temporaires (Debian preseed)
                        $remasterIso = "{settings.hyperv_temp_path}\\Remaster\\{_escape_ps(vm_name)}_preseed.iso"
                        if (Test-Path $remasterIso) {{ Remove-Item $remasterIso -Force }}
                        $remasterDir = "{settings.hyperv_temp_path}\\Remaster\\{_escape_ps(vm_name)}"
                        if (Test-Path $remasterDir) {{ Remove-Item $remasterDir -Recurse -Force }}
                        # Nettoyer l'ISO patched temporaire (Ubuntu autoinstall)
                        $patchedIso = "{settings.hyperv_temp_path}\\{_escape_ps(vm_name)}_install.iso"
                        if (Test-Path $patchedIso) {{ Remove-Item $patchedIso -Force }}
                        Write-Output "VM_RESET"
                        """, timeout=60)

                        # Remettre le statut VM en DB
                        db_vm.state = VMState.STOPPED
                        await self.db.flush()
                        return db_vm

                except Exception as e:
                    logger.warning(
                        "retry_reuse_linux_vm_failed",
                        error=str(e),
                        vm_name=vm_name,
                    )
                    # Fallback : supprimer et recréer
                    try:
                        client = await self.vm_service._get_hypervisor_client(
                            deployment.hypervisor_id
                        )
                        await client.delete_vm(
                            db_vm.hypervisor_vm_id or db_vm.name, delete_disks=True
                        )
                    except Exception as e:
                        logger.warning("retry_cleanup_vm_delete_failed", vm_name=vm_name, error=str(e))
                    await self.db.delete(db_vm)
                    await self.db.flush()
        else:
            # Première exécution : nettoyer une éventuelle VM orpheline du même nom
            await self.vm_service.cleanup_vm_if_exists(
                vm_name, deployment.hypervisor_id, force=True
            )

        # ── Créer une nouvelle VM ──
        memory_mb = config.get("memory_mb", 4096)
        ram_gb = memory_mb // 1024 if memory_mb >= 1024 else config.get("ram_gb", 4)

        vm = await self.vm_service.create_vm(
            name=vm_name,
            hypervisor_id=deployment.hypervisor_id,
            cpu_count=config.get("cpu_count", 2),
            ram_gb=ram_gb,
            disk_gb=config.get("disk_gb", 60),
            network_switch=config.get("network_switch"),
            vhdx_path=config.get("vhdx_path"),
            template_id=None,
            force=True,
        )

        if deployment.os_template_id:
            vm.os_template_id = deployment.os_template_id
            await self.db.flush()

        return vm

    async def _deploy_linux_vm(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        client: HyperVClient,
        config: dict,
        template_config: dict,
    ) -> None:
        """
        Prépare et configure une VM Linux sur Hyper-V.

        Étapes :
        1. Configure la VM pour Linux (template Secure Boot, boot order)
        2. Génère la config d'installation (preseed/kickstart/autoinstall/cloud-init)
        3. Crée une seed ISO contenant la config et l'attache à la VM
        4. Monte l'ISO d'installation du système
        """
        vm_identifier = vm.hypervisor_vm_id or vm.name
        config_type = self._determine_config_type(template_config)

        # ---- 1. Configuration Hyper-V pour Linux ----
        # Pour les VMs Gen2, utiliser le template Secure Boot Linux
        await self._log_step(
            deployment, DeploymentStep.MOUNTING_ISO,
            "Configuration Hyper-V pour Linux (Secure Boot, boot order)...",
        )

        try:
            configure_script = f"""
            $vm = Get-VM -Name '{_escape_ps(vm_identifier)}' -ErrorAction SilentlyContinue
            if (-not $vm) {{
                $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{_escape_ps(vm_identifier)}' }}
            }}
            if ($vm -and $vm.Generation -eq 2) {{
                # Désactiver Secure Boot pour Linux (plus fiable que le template UEFI CA)
                Set-VMFirmware -VMName $vm.Name -EnableSecureBoot Off -ErrorAction SilentlyContinue
                # Activer les services d'intégration invité
                Enable-VMIntegrationService -VMName $vm.Name -Name 'Guest Service Interface' -ErrorAction SilentlyContinue
                Write-Output "SecureBoot disabled + Guest Services enabled"
            }} else {{
                Write-Output "Gen1 VM or VM not found"
            }}
            """
            result = await client._execute(configure_script)
            if result.success:
                await self._log_step(
                    deployment, DeploymentStep.MOUNTING_ISO,
                    f"Configuration Linux : {result.stdout.strip()}",
                )
            else:
                logger.warning(
                    "linux_secure_boot_config_failed",
                    vm_id=vm_identifier,
                    error=result.stderr,
                )
        except Exception as e:
            logger.warning(
                "linux_secure_boot_config_error",
                vm_id=vm_identifier,
                error=str(e),
            )

        # ---- 2. Générer la config d'installation ----
        await self._log_step(
            deployment, DeploymentStep.MOUNTING_ISO,
            f"Génération de la configuration {config_type}...",
        )

        ip_config = config.get("ip_config") or {}
        seed_content = self._generate_linux_seed_config(
            config_type, config, ip_config, template_config,
        )

        await self._log_step(
            deployment, DeploymentStep.MOUNTING_ISO,
            f"Configuration {config_type} générée ({len(seed_content)} octets)",
        )

        # ---- 3. Resolve the install ISO path ----
        iso_path = None
        if deployment.os_template_id:
            template_result = await self.db.execute(
                select(OSTemplate).where(OSTemplate.id == deployment.os_template_id)
            )
            template = template_result.scalar_one_or_none()
            if template:
                iso_path = template.iso_path

        if not iso_path:
            iso_path = template_config.get("iso_path")

        if not iso_path:
            raise DeploymentStepError(
                str(deployment.id),
                DeploymentStep.MOUNTING_ISO,
                "Aucun chemin ISO configuré dans le template Linux",
            )

        # ---- 4. Preseed: remaster ISO / Others: seed ISO + install ISO ----
        if config_type == "preseed":
            # -- Debian preseed: remaster the install ISO with preseed baked in --
            await self._log_step(
                deployment, DeploymentStep.MOUNTING_ISO,
                "Remastering de l'ISO Debian avec preseed intégré...",
            )

            # Transfer preseed.cfg to the Hyper-V host
            vm_name = config["vm_name"]
            remaster_dir = f"{settings.hyperv_temp_path}\\Remaster\\{vm_name}"
            preseed_remote_path = f"{remaster_dir}\\preseed.cfg"

            # Ensure the remaster directory exists
            init_script = f"""
            $ErrorActionPreference = 'Stop'
            $dir = '{_escape_ps(remaster_dir)}'
            if (Test-Path $dir) {{ Remove-Item $dir -Recurse -Force }}
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
            Write-Output "OK"
            """
            result = await client._execute(init_script, timeout=30)
            if not result.success:
                raise DeploymentStepError(
                    str(deployment.id),
                    DeploymentStep.MOUNTING_ISO,
                    f"Échec création dossier remaster : {result.stderr}",
                )

            await self._winrm_copy_file(client, seed_content, preseed_remote_path)

            # Remaster the ISO (preseed baked into the ISO itself)
            remastered_iso_path = await client.remaster_iso_with_preseed(
                original_iso_path=iso_path,
                preseed_file_path=preseed_remote_path,
                vm_name=vm_name,
            )

            await self._log_step(
                deployment, DeploymentStep.MOUNTING_ISO,
                f"ISO remastered avec succès : {remastered_iso_path}",
            )

            # Store the remastered ISO path in deployment config for cleanup
            deployment.config = {
                **deployment.config,
                "_remastered_iso_path": remastered_iso_path,
            }
            await self.db.flush()

            # Mount ONLY the remastered ISO (no seed ISO needed)
            await self._log_step(
                deployment, DeploymentStep.MOUNTING_ISO,
                f"Montage de l'ISO remastered : {remastered_iso_path}",
            )
            await client.mount_iso(vm_identifier, remastered_iso_path)

        else:
            # -- autoinstall / kickstart / cloud-init: existing seed ISO approach --
            await self._log_step(
                deployment, DeploymentStep.MOUNTING_ISO,
                "Création de l'ISO seed et attachement à la VM...",
            )

            await self._create_and_attach_seed_iso(
                client, vm_identifier, seed_content, config_type, config["vm_name"],
            )

            await self._log_step(
                deployment, DeploymentStep.MOUNTING_ISO,
                "ISO seed attachée avec succès",
            )

            # For Ubuntu autoinstall: the seed ISO (cidata) with user-data is
            # already attached above. The install ISO needs 'autoinstall ds=nocloud'
            # in its grub.cfg. Check if it's already present, otherwise remaster.
            if config_type == "autoinstall":
                check_script = f"""
                $mount = Mount-DiskImage -ImagePath '{_escape_ps(iso_path)}' -PassThru
                $d = ($mount | Get-Volume).DriveLetter
                $grub = Get-Content "$d`:\\boot\\grub\\grub.cfg" -Raw -ErrorAction SilentlyContinue
                Dismount-DiskImage -ImagePath '{_escape_ps(iso_path)}' | Out-Null
                if ($grub -match 'autoinstall') {{ Write-Output "HAS_AUTOINSTALL" }}
                else {{ Write-Output "NEEDS_PATCH" }}
                """
                check_result = await client._execute(check_script, timeout=60)
                needs_patch = "NEEDS_PATCH" in (check_result.stdout or "")

                if needs_patch:
                    await self._log_step(
                        deployment, DeploymentStep.MOUNTING_ISO,
                        "Remastering ISO Ubuntu pour ajouter autoinstall...",
                    )
                    await self._patch_ubuntu_iso_grub(
                        client, iso_path, config["vm_name"],
                    )
                    iso_path = f"{settings.hyperv_temp_path}\\{config['vm_name']}_install.iso"
                    await self._log_step(
                        deployment, DeploymentStep.MOUNTING_ISO,
                        f"ISO remastered: {iso_path}",
                    )
                else:
                    await self._log_step(
                        deployment, DeploymentStep.MOUNTING_ISO,
                        "ISO Ubuntu contient déjà autoinstall, utilisation directe.",
                    )

            # Mount the install ISO as the primary DVD
            await self._log_step(
                deployment, DeploymentStep.MOUNTING_ISO,
                f"Montage de l'ISO d'installation : {iso_path}",
            )
            await client.mount_iso(vm_identifier, iso_path)

        # ---- 5. Configurer le boot order (DVD d'installation en premier) ----
        try:
            boot_script = f"""
            $vm = Get-VM -Name '{_escape_ps(vm_identifier)}' -ErrorAction SilentlyContinue
            if (-not $vm) {{
                $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{_escape_ps(vm_identifier)}' }}
            }}
            # Trouver le DVD qui contient l'ISO d'installation (pas le seed)
            $dvds = Get-VMDvdDrive -VMName $vm.Name
            $installDvd = $dvds | Where-Object {{ $_.Path -and $_.Path -notmatch '_seed\\.iso$' }} | Select-Object -First 1
            if (-not $installDvd) {{
                $installDvd = $dvds | Where-Object {{ $_.Path }} | Select-Object -First 1
            }}
            if ($installDvd) {{
                Set-VMFirmware -VMName $vm.Name -FirstBootDevice $installDvd
                Write-Output "FirstBootDevice set to DVD: $($installDvd.Path)"
            }} else {{
                Write-Output "No DVD with media found"
            }}
            """
            result = await client._execute(boot_script, timeout=30)
            if result.success:
                await self._log_step(
                    deployment, DeploymentStep.MOUNTING_ISO,
                    f"Boot order : {result.stdout.strip()}",
                )
        except Exception as e:
            logger.warning(
                "linux_boot_order_config_failed",
                vm_id=vm_identifier,
                error=str(e),
            )

        logger.info(
            "deployment_linux_vm_prepared",
            deployment_id=str(deployment.id),
            vm_name=config["vm_name"],
            config_type=config_type,
        )

    def _generate_linux_seed_config(
        self,
        config_type: str,
        config: dict,
        ip_config: dict,
        template_config: dict,
    ) -> str:
        """Génère le contenu de la configuration d'installation Linux."""
        hostname = config["hostname"]
        username = config.get("username", "otoroot")
        password = config.get("admin_password", "")
        post_install_commands = config.get("post_install_commands") or []

        if config_type == "autoinstall":
            return self.template_engine.render_ubuntu_autoinstall(
                hostname=hostname,
                username=username,
                user_password=password or "tooroto",
                static_ip=ip_config.get("static_ip", False),
                ip_address=ip_config.get("ip_address"),
                gateway=ip_config.get("gateway"),
                dns_server_1=ip_config.get("dns_server_1", "8.8.8.8"),
                dns_server_2=ip_config.get("dns_server_2"),
                ssh_password_auth=True,
                post_install_commands=post_install_commands,
            )
        elif config_type == "preseed":
            dns1 = ip_config.get("dns_server_1", "8.8.8.8")
            dns2 = ip_config.get("dns_server_2")
            dns_servers = f"{dns1} {dns2}" if dns2 else dns1
            return self.template_engine.render_debian_preseed(
                hostname=hostname,
                username=username,
                user_password=password,
                static_ip=ip_config.get("static_ip", False),
                ip_address=ip_config.get("ip_address"),
                netmask=ip_config.get("netmask", "255.255.255.0"),
                gateway=ip_config.get("gateway"),
                dns_servers=dns_servers,
                post_install_commands=post_install_commands,
                os_type=template_config.get("os_type", "debian_12"),
            )
        elif config_type == "kickstart":
            os_type = template_config.get("os_type", "").lower()
            template_name = template_config.get("name", "").lower()
            combined = f"{os_type} {template_name}"

            network_config = None
            if ip_config.get("static_ip"):
                network_config = {
                    "ip": ip_config.get("ip_address"),
                    "netmask": ip_config.get("netmask", "255.255.255.0"),
                    "gateway": ip_config.get("gateway"),
                    "dns": ip_config.get("dns_server_1", "8.8.8.8"),
                }

            if "rocky" in combined:
                return self.template_engine.render_rocky_kickstart(
                    hostname=hostname,
                    username=username,
                    user_password=password or "tooroto",
                    network_config=network_config,
                    post_commands=post_install_commands or None,
                )
            else:
                return self.template_engine.render_rhel_kickstart(
                    hostname=hostname,
                    username=username,
                    user_password=password or "tooroto",
                    network_config=network_config,
                    post_commands=post_install_commands or None,
                )
        else:
            # cloud-init (fallback)
            return self.template_engine.render_cloud_init(
                hostname=hostname,
                username=username,
                user_password=password,
                static_ip=ip_config.get("static_ip", False),
                ip_address=ip_config.get("ip_address"),
                gateway=ip_config.get("gateway"),
                dns_server_1=ip_config.get("dns_server_1", "8.8.8.8"),
                dns_server_2=ip_config.get("dns_server_2"),
                ssh_password_auth=True,
                post_install_commands=post_install_commands,
            )

    async def _winrm_copy_file(
        self,
        client: HyperVClient,
        content: str,
        remote_path: str,
    ) -> None:
        """
        Copie un fichier texte vers l'hôte distant via WinRM.

        Utilise l'encodage base64 pour éviter les problèmes de here-strings
        PowerShell (lignes collées entre batchs, BOM UTF-8 indésirable).
        """
        import base64

        escaped_path = _escape_ps(remote_path)
        content_bytes = content.encode("utf-8")  # UTF-8 sans BOM
        b64_full = base64.b64encode(content_bytes).decode("ascii")

        # Écrire le base64 dans un fichier temp en petits chunks,
        # puis décoder en une seule opération.
        # run_ps encode le script en UTF-16LE+base64, ce qui triple la taille
        # effective → on limite les chunks b64 à 1500 chars pour rester sous
        # la limite de ligne de commande Windows (~8191 chars).
        temp_b64_path = escaped_path + ".b64.tmp"
        chunk_size = 1500
        b64_chunks = [
            b64_full[i:i + chunk_size]
            for i in range(0, len(b64_full), chunk_size)
        ]

        for idx, b64_chunk in enumerate(b64_chunks):
            if idx == 0:
                script = f"[System.IO.File]::WriteAllText('{temp_b64_path}', '{b64_chunk}')"
            else:
                script = f"[System.IO.File]::AppendAllText('{temp_b64_path}', '{b64_chunk}')"

            result = await client._execute(script, timeout=15)
            if not result.success:
                raise DeploymentStepError(
                    "", DeploymentStep.MOUNTING_ISO,
                    f"Échec écriture fichier seed (chunk {idx}): {result.stderr}",
                )

        # Décoder le fichier base64 temp vers le fichier final
        decode_script = (
            f"$b64 = [System.IO.File]::ReadAllText('{temp_b64_path}')\n"
            f"$bytes = [Convert]::FromBase64String($b64)\n"
            f"[System.IO.File]::WriteAllBytes('{escaped_path}', $bytes)\n"
            f"Remove-Item -Path '{temp_b64_path}' -Force"
        )
        result = await client._execute(decode_script, timeout=15)
        if not result.success:
            raise DeploymentStepError(
                "", DeploymentStep.MOUNTING_ISO,
                f"Échec décodage fichier seed: {result.stderr}",
            )

        logger.info(
            "winrm_file_copied",
            remote_path=remote_path,
            size=len(content_bytes),
        )

    async def _patch_ubuntu_iso_grub(
        self,
        client: "HyperVClient",
        iso_path: str,
        vm_name: str,
    ) -> None:
        """
        Remaster a Ubuntu ISO to add 'autoinstall ds=nocloud' to grub.cfg.

        Uses the same oscdimg remastering approach as Debian preseed:
        mount → copy → modify grub.cfg → rebuild with oscdimg.
        This avoids the 2GB ReadAllBytes limit and slow binary searches.
        """
        work_iso_path = f"{settings.hyperv_temp_path}\\{vm_name}_install.iso"
        work_dir = f"{settings.hyperv_temp_path}\\Remaster\\{vm_name}_ubuntu"
        safe_iso = _escape_ps(iso_path)
        safe_work = _escape_ps(work_dir)
        safe_output = _escape_ps(work_iso_path)

        # Step 1: Extract ISO and patch grub.cfg
        extract_script = f"""
        $ErrorActionPreference = 'Stop'
        $origIso = '{safe_iso}'
        $isoDir  = '{safe_work}\\iso_content'

        if (Test-Path $isoDir) {{ Remove-Item $isoDir -Recurse -Force }}
        New-Item -ItemType Directory -Path $isoDir -Force | Out-Null

        $mountResult = Mount-DiskImage -ImagePath $origIso -PassThru
        $driveLetter = ($mountResult | Get-Volume).DriveLetter
        if (-not $driveLetter) {{ throw "Could not mount original ISO" }}
        try {{
            Copy-Item -Path "$($driveLetter):\\*" -Destination $isoDir -Recurse -Force
            Get-ChildItem -Path $isoDir -Recurse | ForEach-Object {{
                $_.Attributes = $_.Attributes -band (-bnot [System.IO.FileAttributes]::ReadOnly)
            }}
        }} finally {{
            Dismount-DiskImage -ImagePath $origIso | Out-Null
        }}

        # Patch grub.cfg with autoinstall kernel parameter
        $grubCfg = "$isoDir\\boot\\grub\\grub.cfg"
        if (Test-Path $grubCfg) {{
            $patched = @"
set timeout=5

loadfont unicode

set menu_color_normal=white/black
set menu_color_highlight=black/light-gray

menuentry "Ubuntu Server Autoinstall" {{
`tset gfxpayload=keep
`tlinux`t/casper/vmlinuz autoinstall ds=nocloud ---
`tinitrd`t/casper/initrd
}}
menuentry "Ubuntu Server HWE Autoinstall" {{
`tset gfxpayload=keep
`tlinux`t/casper/hwe-vmlinuz autoinstall ds=nocloud ---
`tinitrd`t/casper/hwe-initrd
}}
"@
            Set-Content -Path $grubCfg -Value $patched -Encoding ASCII -NoNewline
            Write-Output "grub.cfg patched"
        }} else {{
            Write-Output "grub.cfg not found, skipping patch"
        }}

        Write-Output "EXTRACT_OK"
        """
        result = await client._execute(extract_script, timeout=300)
        if not result.success or "EXTRACT_OK" not in (result.stdout or ""):
            raise DeploymentStepError(
                vm_name, DeploymentStep.MOUNTING_ISO,
                f"Échec extraction/patch ISO Ubuntu: {result.stderr}",
            )

        # Step 2: Rebuild ISO with oscdimg (Joliet + ISO 9660)
        iso_dir_path = f"{work_dir}\\iso_content"
        rebuild_script = f"""
        $ErrorActionPreference = 'Stop'
        $isoDir    = '{_escape_ps(iso_dir_path)}'
        $outputIso = '{safe_output}'
        $oscdimg   = '{_escape_ps(settings.oscdimg_path)}'

        if (Test-Path $outputIso) {{ Remove-Item $outputIso -Force }}
        if (-not (Test-Path $oscdimg)) {{ throw "oscdimg.exe not found at: $oscdimg" }}

        # Detect boot files (Ubuntu uses different paths than Debian)
        $biosBootFiles = @(
            "$isoDir\\isolinux\\isolinux.bin",         # Debian
            "$isoDir\\boot\\grub\\i386-pc\\eltorito.img" # Ubuntu
        )
        $efiBootFiles = @(
            "$isoDir\\boot\\grub\\efi.img",             # Debian
            "$isoDir\\EFI\\boot\\bootx64.efi"           # Ubuntu
        )
        $bootBin = $biosBootFiles | Where-Object {{ Test-Path $_ }} | Select-Object -First 1
        $efiBoot = $efiBootFiles | Where-Object {{ Test-Path $_ }} | Select-Object -First 1

        if ($bootBin -and $efiBoot) {{
            & $oscdimg -m -o -j1 -lUbuntu -bootdata:"2#p0,e,b$bootBin#pEF,e,b$efiBoot" $isoDir $outputIso
        }} elseif ($efiBoot) {{
            & $oscdimg -m -o -j1 -lUbuntu -bootdata:"1#pEF,e,b$efiBoot" $isoDir $outputIso
        }} elseif ($bootBin) {{
            & $oscdimg -m -o -j1 -lUbuntu -b"$bootBin" $isoDir $outputIso
        }} else {{
            & $oscdimg -m -o -j1 -lUbuntu $isoDir $outputIso
        }}

        if ($LASTEXITCODE -ne 0) {{ throw "oscdimg failed with exit code $LASTEXITCODE" }}
        if (-not (Test-Path $outputIso)) {{ throw "Remastered ISO not created" }}

        Write-Output "REMASTERED:$outputIso"
        """

        result = await client._execute(rebuild_script, timeout=600)
        if not result.success or "REMASTERED:" not in (result.stdout or ""):
            raise DeploymentStepError(
                vm_name, DeploymentStep.MOUNTING_ISO,
                f"Échec rebuild ISO Ubuntu: {result.stderr}",
            )

        logger.info(
            "ubuntu_iso_remastered",
            vm_name=vm_name,
            original_iso=iso_path,
            work_iso=work_iso_path,
        )

        if "PATCHED" not in (result.stdout or ""):
            raise DeploymentStepError(
                vm_name, DeploymentStep.MOUNTING_ISO,
                f"Patching grub.cfg failed: {result.stdout}",
            )

        logger.info(
            "ubuntu_iso_grub_patched",
            vm_name=vm_name,
            iso_path=work_iso_path,
            output=result.stdout.strip(),
        )

    async def _create_and_attach_seed_iso(
        self,
        client: HyperVClient,
        vm_identifier: str,
        seed_content: str,
        config_type: str,
        vm_name: str,
    ) -> None:
        """
        Crée une ISO contenant la configuration d'installation Linux et
        l'attache comme second DVD à la VM.

        Utilise le transfert de fichier natif pywinrm (copy) pour envoyer
        le contenu sans limite de taille WinRM, puis crée l'ISO et l'attache.
        """
        # Déterminer le nom de fichier et le label selon le type
        if config_type == "autoinstall":
            file_name = "user-data"
            iso_label = "cidata"
            need_meta_data = True
        elif config_type == "preseed":
            file_name = "preseed.cfg"
            iso_label = "preseed"
            need_meta_data = False
        elif config_type == "kickstart":
            file_name = "ks.cfg"
            iso_label = "OEMDRV"
            need_meta_data = False
        else:
            file_name = "user-data"
            iso_label = "cidata"
            need_meta_data = True

        seed_dir = f"{settings.hyperv_temp_path}\\SeedISO\\{vm_name}"
        iso_path = f"{settings.hyperv_temp_path}\\SeedISO\\{vm_name}_seed.iso"

        # ── Étape 1 : Créer le dossier + écrire le fichier via pywinrm copy ──
        script_init = f"""
        $ErrorActionPreference = 'Stop'
        $seedDir = '{_escape_ps(seed_dir)}'
        if (Test-Path $seedDir) {{ Remove-Item $seedDir -Recurse -Force }}
        New-Item -ItemType Directory -Path $seedDir -Force | Out-Null
        Write-Output "OK"
        """
        result = await client._execute(script_init, timeout=30)
        if not result.success:
            raise DeploymentStepError(
                vm_identifier, DeploymentStep.MOUNTING_ISO,
                f"Échec création dossier seed : {result.stderr}",
            )

        # Transférer le fichier via pywinrm copy (pas de limite de taille)
        remote_file_path = f"{seed_dir}\\{file_name}"
        await self._winrm_copy_file(client, seed_content, remote_file_path)

        # Créer meta-data vide si nécessaire (cloud-init/autoinstall)
        if need_meta_data:
            meta_script = f"""
            Set-Content -Path '{_escape_ps(seed_dir)}\\meta-data' -Value '' -NoNewline
            Write-Output "OK"
            """
            result = await client._execute(meta_script, timeout=15)
            if not result.success:
                logger.warning("linux_meta_data_write_failed", error=result.stderr)

        # ── Étape 2 : Créer l'ISO ──
        import random
        import string
        ish_class = "ISH_" + "".join(random.choices(string.ascii_uppercase, k=8))
        script_iso = f"""
        $ErrorActionPreference = 'Stop'
        $seedDir = '{_escape_ps(seed_dir)}'
        $isoPath = '{_escape_ps(iso_path)}'
        if (Test-Path $isoPath) {{ Remove-Item $isoPath -Force }}

        $oscdimg = Get-Command oscdimg.exe -ErrorAction SilentlyContinue
        if ($oscdimg) {{
            & oscdimg.exe -l"{iso_label}" -j1 $seedDir $isoPath 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {{ throw "oscdimg exit code $LASTEXITCODE" }}
        }} else {{
            # Créer l'ISO via IMAPI2FS avec écriture correcte du stream COM
            $fsi = New-Object -ComObject IMAPI2FS.MsftFileSystemImage
            $fsi.FileSystemsToCreate = 3
            $fsi.VolumeName = '{iso_label}'
            $fsi.Root.AddTree($seedDir, $false)
            $ri = $fsi.CreateResultImage()
            $istream = $ri.ImageStream

            # Lire le IStream COM via Marshal
            Add-Type -TypeDefinition @"
            using System;
            using System.IO;
            using System.Runtime.InteropServices;
            using System.Runtime.InteropServices.ComTypes;
            public class {ish_class} {{
                public static void WriteToFile(object comStream, string path) {{
                    IStream stream = (IStream)comStream;
                    using (FileStream fs = new FileStream(path, FileMode.Create, FileAccess.Write)) {{
                        byte[] buffer = new byte[32768];
                        while (true) {{
                            int bytesRead = 0;
                            IntPtr pBytesRead = Marshal.AllocHGlobal(4);
                            try {{
                                stream.Read(buffer, buffer.Length, pBytesRead);
                                bytesRead = Marshal.ReadInt32(pBytesRead);
                            }} finally {{
                                Marshal.FreeHGlobal(pBytesRead);
                            }}
                            if (bytesRead == 0) break;
                            fs.Write(buffer, 0, bytesRead);
                        }}
                    }}
                }}
            }}
"@
            [{ish_class}]::WriteToFile($istream, $isoPath)
        }}

        if (-not (Test-Path $isoPath)) {{
            throw "Seed ISO not found: $isoPath"
        }}
        Write-Output "ISO_CREATED"
        """
        result = await client._execute(script_iso, timeout=120)
        if not result.success:
            raise DeploymentStepError(
                vm_identifier, DeploymentStep.MOUNTING_ISO,
                f"Échec création ISO seed : {result.stderr}",
            )

        # ── Étape 3 : Attacher l'ISO à la VM ──
        script_attach = f"""
        $ErrorActionPreference = 'Stop'
        $isoPath = '{_escape_ps(iso_path)}'
        $vm = Get-VM -Name '{_escape_ps(vm_identifier)}' -ErrorAction SilentlyContinue
        if (-not $vm) {{
            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{_escape_ps(vm_identifier)}' }}
        }}
        if (-not $vm) {{ throw "VM not found: {vm_identifier}" }}

        # Attacher le seed ISO au slot explicite (Controller 0, Location 2)
        # L'ISO d'installation ira sur (0, 1) via mount_iso, le seed sur (0, 2)
        $dvdDrives = Get-VMDvdDrive -VMName $vm.Name
        $seedDrive = $dvdDrives | Where-Object {{ $_.ControllerNumber -eq 0 -and $_.ControllerLocation -eq 2 }}
        if ($seedDrive) {{
            Set-VMDvdDrive -VMName $vm.Name -ControllerNumber 0 -ControllerLocation 2 -Path $isoPath
        }} else {{
            Add-VMDvdDrive -VMName $vm.Name -ControllerNumber 0 -ControllerLocation 2 -Path $isoPath
        }}
        Write-Output "ATTACHED"
        """
        result = await client._execute(script_attach, timeout=60)
        if not result.success:
            raise DeploymentStepError(
                vm_identifier, DeploymentStep.MOUNTING_ISO,
                f"Échec attachement ISO seed : {result.stderr}",
            )

        logger.info(
            "linux_seed_iso_attached",
            vm_id=vm_identifier,
            config_type=config_type,
        )

    async def _wait_for_linux_vm_ready(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        config: dict,
        timeout: int = 1800,
    ) -> bool:
        """
        Attend qu'une VM Linux soit prête en vérifiant la connectivité SSH.

        Étapes :
        1. Attendre que la VM obtienne une adresse IP (services d'intégration Hyper-V)
        2. Tester la connexion SSH de manière répétée jusqu'au succès ou timeout
           (re-vérifie l'IP périodiquement car elle peut changer après reboot)
        3. Vérifier qu'aucun processus d'installation n'est en cours

        Args:
            deployment: Déploiement en cours
            vm: VM créée
            config: Configuration du déploiement
            timeout: Timeout total en secondes (défaut : 1800s / 30 min)

        Returns:
            True si la VM est accessible via SSH, False sinon
        """
        import time

        vm_identifier = vm.hypervisor_vm_id or vm.name
        username = config.get("username") or config.get("admin_username") or "otoroot"
        password = config.get("admin_password", "")

        start_time = time.time()

        try:
            client = await self.vm_service._get_hypervisor_client(deployment.hypervisor_id)

            # ── Phase 0 : Vérifier si on a déjà une IP (retry rapide) ──
            if vm.ip_address:
                await self._log_step(
                    deployment, DeploymentStep.WAITING_VM_READY,
                    f"IP déjà connue en base : {vm.ip_address} — test SSH direct...",
                )
                ssh_quick = await self._check_ssh_connectivity(
                    vm.ip_address, username, password,
                )
                if ssh_quick:
                    await self._log_step(
                        deployment, DeploymentStep.WAITING_VM_READY,
                        f"Connexion SSH réussie vers {username}@{vm.ip_address} (reprise rapide)",
                    )
                    # Aller directement à Phase 3
                    install_ok = await self._check_linux_install_complete(
                        vm.ip_address, username, password,
                    )
                    if not install_ok:
                        await self._log_step(
                            deployment, DeploymentStep.WAITING_VM_READY,
                            "Processus d'installation détecté — attente supplémentaire...",
                            "info",
                        )
                        for _ in range(12):
                            await asyncio.sleep(15)
                            if await self._check_linux_install_complete(vm.ip_address, username, password):
                                break
                    return True

            # ── Phase 1 : Attendre une adresse IP via Hyper-V ──
            await self._log_step(
                deployment, DeploymentStep.WAITING_VM_READY,
                "Phase 1/3 : Attente de l'attribution d'une IP...",
            )

            # Construire le script PowerShell qui supporte VMName OU VMId
            def _build_ip_script(identifier: str) -> str:
                return (
                    f"$vm = Get-VM -Name '{identifier}' -ErrorAction SilentlyContinue; "
                    f"if (-not $vm) {{ $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{identifier}' }} }}; "
                    f"if ($vm) {{ (Get-VMNetworkAdapter -VMName $vm.Name).IPAddresses "
                    f"| Where-Object {{ $_ -match '^\\d+\\.\\d+\\.\\d+\\.\\d+$' }} "
                    f"| Select-Object -First 1 }}"
                )

            vm_ip = None
            ip_timeout = min(timeout // 3, 600)  # Max 10 min pour l'IP
            ip_start = time.time()

            while (time.time() - ip_start) < ip_timeout:
                try:
                    ip_script = _build_ip_script(vm_identifier)
                    result = await client._execute(ip_script, timeout=15)
                    if result.success and result.stdout.strip():
                        candidate = result.stdout.strip()
                        # Ignorer les IPs link-local
                        if not candidate.startswith("169.254."):
                            vm_ip = candidate
                            await self._log_step(
                                deployment, DeploymentStep.WAITING_VM_READY,
                                f"Adresse IP obtenue : {vm_ip}",
                            )
                            # Sauvegarder l'IP dans la VM
                            vm.ip_address = vm_ip
                            await self.db.flush()
                            break
                except Exception as e:
                    logger.debug("linux_get_ip_error", error=str(e))

                await asyncio.sleep(10)

            if not vm_ip:
                # Dernier recours : utiliser l'IP déjà en base si elle existe
                if vm.ip_address:
                    vm_ip = vm.ip_address
                    await self._log_step(
                        deployment, DeploymentStep.WAITING_VM_READY,
                        f"Hyper-V ne retourne pas d'IP — utilisation de l'IP en base : {vm_ip}",
                        "warning",
                    )
                else:
                    await self._log_step(
                        deployment, DeploymentStep.WAITING_VM_READY,
                        "Impossible d'obtenir une IP — timeout dépassé",
                        "warning",
                    )
                    return False

            # Phase 2 : Tester la connectivité SSH (re-vérifie l'IP périodiquement)
            await self._log_step(
                deployment, DeploymentStep.WAITING_VM_READY,
                f"Phase 2/3 : Test de connectivité SSH vers {vm_ip}...",
            )

            ssh_ok = False
            ssh_check_interval = 15
            consecutive_failures = 0
            ip_refresh_interval = 60  # Re-vérifier l'IP toutes les 60s
            last_ip_refresh = time.time()

            while (time.time() - start_time) < timeout:
                # Re-vérifier l'IP périodiquement (elle peut changer après reboot)
                if (time.time() - last_ip_refresh) >= ip_refresh_interval:
                    try:
                        ip_script = _build_ip_script(vm_identifier)
                        result = await client._execute(ip_script, timeout=15)
                        if result.success and result.stdout.strip():
                            new_ip = result.stdout.strip()
                            if not new_ip.startswith("169.254.") and new_ip != vm_ip:
                                await self._log_step(
                                    deployment, DeploymentStep.WAITING_VM_READY,
                                    f"IP changée après reboot : {vm_ip} → {new_ip}",
                                )
                                vm_ip = new_ip
                                vm.ip_address = vm_ip
                                await self.db.flush()
                    except Exception as e:
                        logger.debug("ip_refresh_failed", vm_name=vm_identifier, error=str(e))
                    last_ip_refresh = time.time()

                ssh_ok = await self._check_ssh_connectivity(
                    vm_ip, username, password,
                )
                if ssh_ok:
                    await self._log_step(
                        deployment, DeploymentStep.WAITING_VM_READY,
                        f"Connexion SSH réussie vers {username}@{vm_ip}",
                    )
                    break

                consecutive_failures += 1
                if consecutive_failures % 5 == 0:
                    elapsed = int(time.time() - start_time)
                    remaining = timeout - elapsed
                    await self._log_step(
                        deployment, DeploymentStep.WAITING_VM_READY,
                        f"SSH pas encore disponible ({consecutive_failures} tentatives, "
                        f"{elapsed}s écoulées, {remaining}s restantes)...",
                        "info",
                    )

                await asyncio.sleep(ssh_check_interval)

            if not ssh_ok:
                await self._log_step(
                    deployment, DeploymentStep.WAITING_VM_READY,
                    f"Connexion SSH impossible après {int(time.time() - start_time)}s "
                    f"(user={username}, ip={vm_ip})",
                    "error",
                )
                return False

            # Phase 3 : Vérifier que l'installation est terminée
            await self._log_step(
                deployment, DeploymentStep.WAITING_VM_READY,
                "Phase 3/3 : Vérification que l'installation est terminée...",
            )

            install_check_ok = await self._check_linux_install_complete(
                vm_ip, username, password,
            )
            if not install_check_ok:
                # L'installation est peut-être encore en cours, attendre un peu
                await self._log_step(
                    deployment, DeploymentStep.WAITING_VM_READY,
                    "Processus d'installation détecté — attente supplémentaire...",
                    "info",
                )
                for _ in range(12):  # Max 3 min supplémentaires
                    await asyncio.sleep(15)
                    if await self._check_linux_install_complete(vm_ip, username, password):
                        install_check_ok = True
                        break

            if not install_check_ok:
                await self._log_step(
                    deployment, DeploymentStep.WAITING_VM_READY,
                    "L'installation semble encore en cours — on continue quand même",
                    "warning",
                )

            return True

        except Exception as e:
            logger.error(
                "deployment_wait_linux_vm_ready_failed",
                deployment_id=str(deployment.id),
                error=str(e),
                exc_info=True,
            )
            return False

    async def _check_ssh_connectivity(
        self,
        ip: str,
        username: str,
        password: str,
        timeout: int = 10,
    ) -> bool:
        """
        Vérifie si une VM est accessible via SSH.

        Utilise paramiko si disponible, sinon utilise sshpass + ssh en subprocess.
        """
        if PARAMIKO_AVAILABLE:
            return await self._check_ssh_via_paramiko(ip, username, password, timeout)
        return await self._check_ssh_via_subprocess(ip, username, password, timeout)

    async def _check_ssh_via_paramiko(
        self,
        ip: str,
        username: str,
        password: str,
        timeout: int = 10,
    ) -> bool:
        """Vérifie la connectivité SSH via paramiko."""
        def _connect():
            try:
                ssh_client = paramiko.SSHClient()
                ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh_client.connect(
                    hostname=ip,
                    username=username,
                    password=password,
                    timeout=timeout,
                    allow_agent=False,
                    look_for_keys=False,
                )
                _stdin, stdout, _stderr = ssh_client.exec_command("echo ready", timeout=5)
                output = stdout.read().decode("utf-8", errors="replace").strip()
                ssh_client.close()
                return output == "ready"
            except Exception:
                return False

        try:
            loop = asyncio.get_running_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, _connect),
                timeout=timeout + 5,
            )
        except Exception:
            return False

    async def _check_ssh_via_subprocess(
        self,
        ip: str,
        username: str,
        password: str,
        timeout: int = 10,
    ) -> bool:
        """Vérifie la connectivité SSH via sshpass + ssh subprocess."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "sshpass", "-p", password,
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=5",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "LogLevel=ERROR",
                f"{username}@{ip}",
                "echo", "ready",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout,
            )
            return proc.returncode == 0 and b"ready" in stdout
        except Exception:
            return False

    async def _check_linux_install_complete(
        self,
        ip: str,
        username: str,
        password: str,
    ) -> bool:
        """
        Vérifie qu'aucun processus d'installation Linux n'est en cours.

        Recherche les processus typiques d'un installeur (d-i, anaconda,
        subiquity, unattended-upgrade au premier boot).
        """
        check_cmd = (
            "! pgrep -x '(d-i|anaconda|subiquity|unattended-upgr)' > /dev/null 2>&1 "
            "&& echo INSTALL_COMPLETE || echo INSTALL_RUNNING"
        )

        if PARAMIKO_AVAILABLE:
            result = await self._run_ssh_command(ip, username, password, check_cmd)
        else:
            result = await self._run_ssh_command_subprocess(ip, username, password, check_cmd)

        return "INSTALL_COMPLETE" in (result or "")

    async def _run_ssh_command(
        self,
        ip: str,
        username: str,
        password: str,
        command: str,
        timeout: int = 30,
    ) -> str | None:
        """Exécute une commande via SSH (paramiko) et retourne stdout."""
        if PARAMIKO_AVAILABLE:
            return await self._run_ssh_command_paramiko(ip, username, password, command, timeout)
        return await self._run_ssh_command_subprocess(ip, username, password, command, timeout)

    async def _run_ssh_command_paramiko(
        self,
        ip: str,
        username: str,
        password: str,
        command: str,
        timeout: int = 30,
    ) -> str | None:
        """Exécute une commande via paramiko."""
        def _exec():
            try:
                ssh_client = paramiko.SSHClient()
                ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh_client.connect(
                    hostname=ip,
                    username=username,
                    password=password,
                    timeout=10,
                    allow_agent=False,
                    look_for_keys=False,
                )
                _stdin, stdout, _stderr = ssh_client.exec_command(command, timeout=timeout)
                output = stdout.read().decode("utf-8", errors="replace").strip()
                ssh_client.close()
                return output
            except Exception:
                return None

        try:
            loop = asyncio.get_running_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, _exec),
                timeout=timeout + 10,
            )
        except Exception:
            return None

    async def _run_ssh_command_subprocess(
        self,
        ip: str,
        username: str,
        password: str,
        command: str,
        timeout: int = 30,
    ) -> str | None:
        """Exécute une commande via sshpass + ssh subprocess."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "sshpass", "-p", password,
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=5",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "LogLevel=ERROR",
                f"{username}@{ip}",
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout,
            )
            if proc.returncode == 0:
                return stdout.decode("utf-8", errors="replace").strip()
            return None
        except Exception:
            return None

    async def _execute_linux_post_install(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        config: dict,
        ip_address: str,
    ) -> None:
        """
        Exécute les commandes post-installation sur une VM Linux via SSH.

        - Configure une IP statique si demandé
        - Installe des paquets supplémentaires
        - Exécute les scripts post-installation personnalisés
        - Rejoint un domaine AD si demandé (via realmd/sssd)
        """
        username = config.get("username", "otoroot")
        password = config.get("admin_password", "")

        try:
            # 1. Configurer l'IP statique si demandé
            ip_config = config.get("ip_config") or {}
            if ip_config.get("static_ip") and ip_config.get("ip_address"):
                await self._log_step(
                    deployment, DeploymentStep.POST_CONFIGURATION,
                    f"Configuration de l'IP statique : {ip_config['ip_address']}...",
                )

                gateway = ip_config.get("gateway", "")
                dns1 = ip_config.get("dns_server_1", "8.8.8.8")
                dns2 = ip_config.get("dns_server_2", "")
                prefix = ip_config.get("subnet_prefix", "24")

                network_script = f"""
                sudo bash -c 'cat > /etc/netplan/01-static.yaml << NETPLAN_EOF
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: no
      addresses:
        - {ip_config["ip_address"]}/{prefix}
      routes:
        - to: default
          via: {gateway}
      nameservers:
        addresses: [{dns1}{", " + dns2 if dns2 else ""}]
NETPLAN_EOF
netplan apply 2>/dev/null || true
# Fallback pour les systèmes sans netplan (RHEL/CentOS)
if ! command -v netplan &>/dev/null; then
  nmcli con mod "$(nmcli -t -f NAME con show --active | head -1)" \\
    ipv4.addresses {ip_config["ip_address"]}/{prefix} \\
    ipv4.gateway {gateway} \\
    ipv4.dns "{dns1}{" " + dns2 if dns2 else ""}" \\
    ipv4.method manual 2>/dev/null || true
  nmcli con up "$(nmcli -t -f NAME con show --active | head -1)" 2>/dev/null || true
fi
'
"""
                result = await self._run_ssh_command(
                    ip_address, username, password, network_script, timeout=30,
                )
                if result is not None:
                    await self._log_step(
                        deployment, DeploymentStep.POST_CONFIGURATION,
                        "IP statique configurée",
                    )
                else:
                    await self._log_step(
                        deployment, DeploymentStep.POST_CONFIGURATION,
                        "Erreur lors de la configuration de l'IP statique",
                        "warning",
                    )

            # 2. Configurer SSH (s'assurer que PermitRootLogin et PasswordAuthentication)
            await self._log_step(
                deployment, DeploymentStep.POST_CONFIGURATION,
                "Vérification de la configuration SSH...",
            )
            ssh_config_script = """
            sudo bash -c '
            sed -i "s/#PasswordAuthentication.*/PasswordAuthentication yes/" /etc/ssh/sshd_config
            sed -i "s/PasswordAuthentication no/PasswordAuthentication yes/" /etc/ssh/sshd_config
            systemctl restart sshd 2>/dev/null || systemctl restart ssh 2>/dev/null
            echo "SSH_CONFIGURED"
            '
            """
            result = await self._run_ssh_command(
                ip_address, username, password, ssh_config_script, timeout=15,
            )
            if result and "SSH_CONFIGURED" in result:
                await self._log_step(
                    deployment, DeploymentStep.POST_CONFIGURATION,
                    "Configuration SSH vérifiée",
                )

            # 3. Jonction AD si demandé (via realmd/sssd)
            domain_join = config.get("domain_join") or {}
            if domain_join.get("domain"):
                domain = domain_join["domain"]
                domain_user = domain_join.get("user", "")
                domain_password = domain_join.get("password", "")

                await self._log_step(
                    deployment, DeploymentStep.POST_CONFIGURATION,
                    f"Jonction au domaine AD : {domain}...",
                )

                ad_script = f"""
                sudo bash -c '
                apt-get install -y realmd sssd sssd-tools adcli packagekit 2>/dev/null || \\
                dnf install -y realmd sssd sssd-tools adcli 2>/dev/null || \\
                yum install -y realmd sssd sssd-tools adcli 2>/dev/null

                echo "{domain_password}" | realm join -U "{domain_user}" {domain} 2>&1
                if [ $? -eq 0 ]; then
                    echo "AD_JOIN_SUCCESS"
                else
                    echo "AD_JOIN_FAILED"
                fi
                '
                """
                result = await self._run_ssh_command(
                    ip_address, username, password, ad_script, timeout=120,
                )
                if result and "AD_JOIN_SUCCESS" in result:
                    await self._log_step(
                        deployment, DeploymentStep.POST_CONFIGURATION,
                        f"Jonction au domaine {domain} réussie",
                    )
                else:
                    await self._log_step(
                        deployment, DeploymentStep.POST_CONFIGURATION,
                        f"Échec de la jonction au domaine {domain}",
                        "warning",
                    )

            # 4. Exécuter les commandes post-installation personnalisées
            post_commands = config.get("post_install_commands") or []
            if post_commands:
                await self._log_step(
                    deployment, DeploymentStep.POST_CONFIGURATION,
                    f"Exécution de {len(post_commands)} commande(s) post-installation...",
                )

                for i, cmd in enumerate(post_commands, 1):
                    await self._log_step(
                        deployment, DeploymentStep.POST_CONFIGURATION,
                        f"Commande {i}/{len(post_commands)} : {cmd[:80]}...",
                    )
                    result = await self._run_ssh_command(
                        ip_address, username, password,
                        f"sudo bash -c {shlex.quote(cmd)}",
                        timeout=120,
                    )
                    if result is not None:
                        await self._log_step(
                            deployment, DeploymentStep.POST_CONFIGURATION,
                            f"Commande {i} terminée",
                        )
                    else:
                        await self._log_step(
                            deployment, DeploymentStep.POST_CONFIGURATION,
                            f"Commande {i} échouée ou timeout",
                            "warning",
                        )

            logger.info(
                "deployment_linux_post_install_complete",
                deployment_id=str(deployment.id),
                vm_name=deployment.vm_name,
            )

        except Exception as e:
            logger.error(
                "deployment_linux_post_install_error",
                deployment_id=str(deployment.id),
                error=str(e),
                exc_info=True,
            )
            await self._log_step(
                deployment, DeploymentStep.POST_CONFIGURATION,
                f"Erreur post-installation Linux : {e}",
                "warning",
            )

    async def _install_linux_packages(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        config: dict,
        ip_address: str,
        packages: list[str],
    ) -> None:
        """
        Installe des paquets supplémentaires sur une VM Linux via SSH.

        Détecte automatiquement le gestionnaire de paquets (apt, dnf, yum).
        """
        username = config.get("username", "otoroot")
        password = config.get("admin_password", "")

        if not ip_address or not packages:
            return

        try:
            packages_str = " ".join(packages)

            install_script = f"""
            sudo bash -c '
            export DEBIAN_FRONTEND=noninteractive
            if command -v apt-get &>/dev/null; then
                apt-get update -qq && apt-get install -y -qq {packages_str} 2>&1
            elif command -v dnf &>/dev/null; then
                dnf install -y {packages_str} 2>&1
            elif command -v yum &>/dev/null; then
                yum install -y {packages_str} 2>&1
            else
                echo "PACKAGE_MANAGER_NOT_FOUND"
                exit 1
            fi
            echo "PACKAGES_INSTALLED"
            '
            """

            result = await self._run_ssh_command(
                ip_address, username, password, install_script, timeout=300,
            )
            if result and "PACKAGES_INSTALLED" in result:
                await self._log_step(
                    deployment, DeploymentStep.INSTALLING_SOFTWARE,
                    f"Paquets installés : {packages_str}",
                )
            elif result and "PACKAGE_MANAGER_NOT_FOUND" in result:
                await self._log_step(
                    deployment, DeploymentStep.INSTALLING_SOFTWARE,
                    "Aucun gestionnaire de paquets trouvé (apt/dnf/yum)",
                    "error",
                )
            else:
                await self._log_step(
                    deployment, DeploymentStep.INSTALLING_SOFTWARE,
                    "Échec de l'installation des paquets",
                    "warning",
                )

        except Exception as e:
            logger.error(
                "deployment_linux_packages_error",
                deployment_id=str(deployment.id),
                error=str(e),
            )
            await self._log_step(
                deployment, DeploymentStep.INSTALLING_SOFTWARE,
                f"Erreur installation paquets : {e}",
                "warning",
            )

    async def _finalize_linux_deployment(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        client: HyperVClient,
    ) -> None:
        """
        Finalise le déploiement Linux.

        - Récupère les infos réseau finales
        - Démonte les ISO (installation + seed)
        - Reconfigure le boot order (HardDrive en premier)
        - Nettoie les fichiers temporaires
        """
        config = deployment.config
        vm_identifier = vm.hypervisor_vm_id or vm.name

        try:
            # 1. Récupérer les infos réseau
            await self._log_step(
                deployment, DeploymentStep.FINALIZING,
                "Récupération des informations réseau...",
            )

            try:
                network_info = await client.get_vm_network_summary(vm_identifier)
                if network_info.get("ip_addresses"):
                    ip = network_info["ip_addresses"][0]
                    await self._log_step(
                        deployment, DeploymentStep.FINALIZING,
                        f"Adresse IP de la VM : {ip}",
                    )
                    vm.ip_address = ip
                    await self.db.flush()
            except Exception as e:
                logger.warning("deployment_linux_network_info_error", error=str(e))

            # 2. Démonter les ISO et nettoyer
            await self._log_step(
                deployment, DeploymentStep.FINALIZING,
                "Démontage des ISO et nettoyage...",
            )

            try:
                cleanup_script = f"""
                $vm = Get-VM -Name '{vm_identifier}' -ErrorAction SilentlyContinue
                if (-not $vm) {{
                    $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{vm_identifier}' }}
                }}
                if ($vm) {{
                    # Démonter tous les DVD
                    Get-VMDvdDrive -VMName $vm.Name | ForEach-Object {{
                        Set-VMDvdDrive -VMDvdDrive $_ -Path $null -ErrorAction SilentlyContinue
                    }}
                    Write-Output "DVD drives unmounted"

                    # Reconfigurer le boot order (HardDrive en premier)
                    if ($vm.Generation -eq 2) {{
                        $bootDevices = @()
                        $hd = Get-VMFirmware -VMName $vm.Name | Select-Object -ExpandProperty BootOrder | Where-Object {{ $_.BootType -like '*HardDrive*' }} | Select-Object -First 1
                        if ($hd) {{ $bootDevices += $hd }}
                        $dvd = Get-VMFirmware -VMName $vm.Name | Select-Object -ExpandProperty BootOrder | Where-Object {{ $_.BootType -like '*DVD*' }} | Select-Object -First 1
                        if ($dvd) {{ $bootDevices += $dvd }}
                        $net = Get-VMFirmware -VMName $vm.Name | Select-Object -ExpandProperty BootOrder | Where-Object {{ $_.BootType -like '*Network*' }} | Select-Object -First 1
                        if ($net) {{ $bootDevices += $net }}
                        if ($bootDevices.Count -gt 0) {{
                            Set-VMFirmware -VMName $vm.Name -BootOrder $bootDevices
                        }}
                        Write-Output "Boot order reset: HardDrive first"
                    }}
                }}

                # Supprimer l'ISO seed temporaire
                $seedIso = "{settings.hyperv_temp_path}\\SeedISO\\{config['vm_name']}_seed.iso"
                if (Test-Path $seedIso) {{
                    Remove-Item $seedIso -Force
                    Write-Output "Seed ISO cleaned up"
                }}
                $seedDir = "{settings.hyperv_temp_path}\\SeedISO\\{config['vm_name']}"
                if (Test-Path $seedDir) {{
                    Remove-Item $seedDir -Recurse -Force
                    Write-Output "Seed directory cleaned up"
                }}

                # Supprimer l'ISO remastered temporaire (Debian preseed)
                $remasterIso = "{settings.hyperv_temp_path}\\Remaster\\{config['vm_name']}_preseed.iso"
                if (Test-Path $remasterIso) {{
                    Remove-Item $remasterIso -Force
                    Write-Output "Remastered ISO cleaned up"
                }}
                $remasterDir = "{settings.hyperv_temp_path}\\Remaster\\{config['vm_name']}"
                if (Test-Path $remasterDir) {{
                    Remove-Item $remasterDir -Recurse -Force
                    Write-Output "Remaster directory cleaned up"
                }}

                # Supprimer l'ISO patched temporaire (Ubuntu autoinstall)
                $patchedIso = "{settings.hyperv_temp_path}\\{config['vm_name']}_install.iso"
                if (Test-Path $patchedIso) {{
                    Remove-Item $patchedIso -Force
                    Write-Output "Patched ISO cleaned up"
                }}
                """
                result = await client._execute(cleanup_script, timeout=30)
                if result.success:
                    await self._log_step(
                        deployment, DeploymentStep.FINALIZING,
                        f"Nettoyage terminé : {result.stdout.strip()}",
                    )
                else:
                    logger.warning(
                        "linux_cleanup_failed",
                        error=result.stderr,
                    )
            except Exception as e:
                logger.warning("deployment_linux_cleanup_error", error=str(e))

            # 3. Résumé du déploiement
            username = config.get("username", "otoroot")
            summary_lines = [
                f"VM : {config['vm_name']}",
                f"Hostname : {config.get('hostname', config['vm_name'])}",
                f"Utilisateur : {username}",
                f"IP : {vm.ip_address or 'DHCP'}",
            ]

            domain_join = config.get("domain_join") or {}
            if domain_join.get("domain"):
                summary_lines.append(f"Domaine AD : {domain_join['domain']}")

            packages = config.get("packages") or []
            if packages:
                summary_lines.append(f"Paquets installés : {', '.join(packages)}")

            await self._log_step(
                deployment, DeploymentStep.FINALIZING,
                "Résumé du déploiement :\n" + "\n".join(summary_lines),
            )

        except Exception as e:
            logger.warning(
                "deployment_linux_finalize_error",
                deployment_id=str(deployment.id),
                error=str(e),
            )

    async def _validate_deployment(self, deployment: Deployment) -> None:
        """Valide la configuration du déploiement."""
        config = deployment.config
        
        # Vérifier les paramètres obligatoires
        required = ["vm_name", "hostname", "admin_password"]
        for field in required:
            if not config.get(field):
                raise ValidationError(f"Missing required field: {field}")
        
        # En mode retry (deployment.vm_id existe), on ne vérifie pas l'existence de la VM
        # car on va la nettoyer/réutiliser dans _create_vm_for_dism
        if not deployment.vm_id:
            # Vérifier que la VM n'existe pas déjà (seulement pour les nouveaux déploiements)
            existing = await self.vm_service.get_vm_by_name(config["vm_name"])
            if existing:
                raise ValidationError(f"VM '{config['vm_name']}' already exists")

    async def _create_vm_for_dism(self, deployment: Deployment) -> VirtualMachine:
        """
        Crée ou réutilise la VM pour le déploiement DISM.

        En mode retry (deployment.vm_id existe), réutilise la VM existante :
        arrête, démonte les VHD/ISO, reformate le disque. Évite de supprimer/
        recréer inutilement.
        """
        config = deployment.config
        vm_name = config["vm_name"]

        # ── Mode retry : réutiliser la VM existante ──
        if deployment.vm_id:
            vm_result = await self.db.execute(
                select(VirtualMachine).where(VirtualMachine.id == deployment.vm_id)
            )
            db_vm = vm_result.scalar_one_or_none()

            if db_vm:
                try:
                    client = await self.vm_service._get_hypervisor_client(
                        deployment.hypervisor_id
                    )
                    vm_identifier = db_vm.hypervisor_vm_id or db_vm.name
                    hyperv_vm = await client.get_vm(vm_identifier)

                    if hyperv_vm:
                        logger.info(
                            "retry_reusing_existing_vm",
                            deployment_id=str(deployment.id),
                            vm_name=vm_name,
                        )
                        # Arrêter la VM et nettoyer pour DISM
                        await client._execute(f"""
                        $vm = Get-VM -Name '{_escape_ps(vm_identifier)}' -ErrorAction SilentlyContinue
                        if (-not $vm) {{
                            $vm = Get-VM | Where-Object {{ $_.VMId.ToString() -eq '{_escape_ps(vm_identifier)}' }}
                        }}
                        if ($vm -and $vm.State -ne 'Off') {{
                            Stop-VM -VMName $vm.Name -Force -TurnOff
                            Start-Sleep -Seconds 2
                        }}
                        # Retirer complètement tous les DVD drives (pas juste démonter)
                        # pour éviter les entrées firmware boot stale sur Gen2
                        Get-VMDvdDrive -VMName $vm.Name | Remove-VMDvdDrive
                        # Démonter les VHD/ISO en cours sur le host
                        $vhdPath = (Get-VMHardDiskDrive -VMName $vm.Name | Select-Object -First 1).Path
                        if ($vhdPath) {{
                            Dismount-VHD -Path $vhdPath -ErrorAction SilentlyContinue
                        }}
                        Write-Output "VM_RESET"
                        """, timeout=60)

                        db_vm.state = VMState.STOPPED
                        await self.db.flush()
                        return db_vm

                except Exception as e:
                    logger.warning(
                        "retry_reuse_vm_failed",
                        error=str(e),
                        vm_name=vm_name,
                    )
                    # Fallback : supprimer et recréer
                    try:
                        client = await self.vm_service._get_hypervisor_client(
                            deployment.hypervisor_id
                        )
                        await client.delete_vm(
                            db_vm.hypervisor_vm_id or db_vm.name, delete_disks=True
                        )
                    except Exception as e:
                        logger.warning("retry_cleanup_vm_delete_failed", vm_name=vm_name, error=str(e))
                    await self.db.delete(db_vm)
                    await self.db.flush()
            else:
                # VM en base disparue — nettoyer l'hyperviseur
                try:
                    client = await self.vm_service._get_hypervisor_client(
                        deployment.hypervisor_id
                    )
                    vm_info = await client.get_vm(vm_name)
                    if vm_info:
                        await client.delete_vm(vm_info.id, delete_disks=True)
                except Exception as e:
                    logger.warning(
                        "retry_cleanup_hypervisor_vm_failed",
                        error=str(e),
                    )
        else:
            await self.vm_service.cleanup_vm_if_exists(
                vm_name, deployment.hypervisor_id, force=True
            )

        # ── Créer une nouvelle VM ──
        memory_mb = config.get("memory_mb", 4096)
        ram_gb = memory_mb // 1024 if memory_mb >= 1024 else config.get("ram_gb", 4)

        vm = await self.vm_service.create_vm(
            name=vm_name,
            hypervisor_id=deployment.hypervisor_id,
            cpu_count=config.get("cpu_count", 2),
            ram_gb=ram_gb,
            disk_gb=config.get("disk_gb", 60),
            network_switch=config.get("network_switch"),
            vhdx_path=config.get("vhdx_path"),
            template_id=None,
            force=True,
        )

        if deployment.os_template_id:
            vm.os_template_id = deployment.os_template_id
            await self.db.flush()

        return vm

    async def _deploy_with_dism(self, deployment: Deployment, vm: VirtualMachine) -> None:
        """
        Déploie Windows via DISM sur le VHDX de la VM.
        
        Cette méthode:
        1. Récupère le chemin ISO depuis le template en DB
        2. Génère le fichier unattend.xml
        3. Appelle deploy_with_dism du client Hyper-V
        """
        config = deployment.config
        
        # Récupérer le template depuis la DB pour avoir le chemin ISO
        iso_path = None
        if deployment.os_template_id:
            from sqlalchemy import select
            template_result = await self.db.execute(
                select(OSTemplate).where(OSTemplate.id == deployment.os_template_id)
            )
            template = template_result.scalar_one_or_none()
            if template:
                iso_path = template.iso_path
        
        # Fallback sur la config si pas trouvé en DB
        if not iso_path:
            template_config = config.get("template") or {}
            iso_path = template_config.get("iso_path")
        
        if not iso_path:
            raise DeploymentStepError(
                str(deployment.id),
                DeploymentStep.MOUNTING_ISO,
                "No ISO path configured in template",
            )
        
        # Récupérer le chemin VHDX de la VM
        client = await self.vm_service._get_hypervisor_client(deployment.hypervisor_id)
        
        # Obtenir le chemin du VHDX
        vhdx_path = config.get("vhdx_path")
        if not vhdx_path:
            # Utiliser le chemin par défaut
            vhdx_path = f"{client.vhdx_path}\\{config['vm_name']}.vhdx"
        elif not vhdx_path.lower().endswith(".vhdx"):
            # C'est un dossier, construire le chemin complet
            vhdx_path = f"{vhdx_path.rstrip(chr(92))}\\{config['vm_name']}.vhdx"
        
        # Générer le contenu unattend.xml
        ip_config = config.get("ip_config") or {}
        domain_join = config.get("domain_join") or {}
        
        template_config = config.get("template") or {}

        # Déterminer l'édition Windows depuis le template ou la config
        windows_edition = config.get("windows_edition") or template_config.get("windows_edition") or _detect_windows_edition(template_config.get("name", ""))

        unattend_content = self.template_engine.render_windows_unattend(
            hostname=config["hostname"],
            admin_password=config["admin_password"],
            admin_username=config.get("admin_username") or "otoroot",
            static_ip=ip_config.get("static_ip", False),
            ip_address=ip_config.get("ip_address"),
            gateway=ip_config.get("gateway"),
            dns_server_1=ip_config.get("dns_server_1", "8.8.8.8"),
            dns_server_2=ip_config.get("dns_server_2"),
            join_domain=bool(domain_join),
            domain_name=domain_join.get("domain"),
            domain_user=domain_join.get("user"),
            domain_password=domain_join.get("password"),
            windows_edition=windows_edition,
            post_install_commands=[
                {"command": cmd, "description": f"Custom command {i+1}"}
                for i, cmd in enumerate(config.get("post_install_commands") or [])
            ],
            template_name=template_config.get("name"),
        )

        # Déterminer le bon image_index pour DISM
        image_index = _get_wim_image_index(windows_edition)

        # Appeler deploy_with_dism
        vm_identifier = vm.hypervisor_vm_id or vm.name
        success = await client.deploy_with_dism(
            vm_id=vm_identifier,
            iso_path=iso_path,
            vhd_path=vhdx_path,
            image_index=image_index,
            unattend_content=unattend_content,
            admin_username=config.get("admin_username"),
        )
        
        if not success:
            raise DeploymentStepError(
                str(deployment.id),
                DeploymentStep.MOUNTING_ISO,
                "DISM deployment failed",
            )
        
        logger.info(
            "deployment_dism_completed",
            deployment_id=str(deployment.id),
            vm_name=config["vm_name"],
        )

    async def _create_vm(self, deployment: Deployment) -> VirtualMachine:
        """Crée la VM pour le déploiement (legacy, utilisé si DISM désactivé)."""
        config = deployment.config
        
        vm = await self.vm_service.create_vm(
            name=config["vm_name"],
            hypervisor_id=deployment.hypervisor_id,
            cpu_count=config.get("cpu_count", 2),
            ram_gb=config.get("ram_gb", 4),
            disk_gb=config.get("disk_gb", 60),
            network_switch=config.get("network_switch"),
            vhdx_path=config.get("vhdx_path"),
            template_id=deployment.os_template_id,
        )
        
        return vm

    async def _mount_iso(self, deployment: Deployment, vm: VirtualMachine) -> None:
        """Monte l'ISO d'installation sur la VM."""
        template_config = deployment.config.get("template", {})
        iso_path = template_config.get("iso_path")
        
        if not iso_path:
            raise DeploymentStepError(
                str(deployment.id),
                DeploymentStep.MOUNTING_ISO,
                "No ISO path configured in template",
            )
        
        client = await self.vm_service._get_hypervisor_client(deployment.hypervisor_id)
        await client.mount_iso(vm.hypervisor_vm_id or vm.name, iso_path)

    async def _generate_unattend(self, deployment: Deployment, vm: VirtualMachine) -> None:
        """Génère et injecte le fichier d'installation automatique."""
        config = deployment.config
        template_config = config.get("template") or {}
        os_family = template_config.get("os_family", "windows")
        
        # Préparer les variables
        ip_config = config.get("ip_config") or {}
        domain_join = config.get("domain_join") or {}
        
        # Récupérer le client Hyper-V
        client = await self.vm_service._get_hypervisor_client(deployment.hypervisor_id)
        
        try:
            if os_family == "windows":
                # Déterminer l'édition Windows
                windows_edition = config.get("windows_edition") or template_config.get("windows_edition") or _detect_windows_edition(template_config.get("name", ""))

                unattend_content = self.template_engine.render_windows_unattend(
                    hostname=config["hostname"],
                    admin_password=config["admin_password"],
                    admin_username=config.get("admin_username") or "otoroot",
                    static_ip=ip_config.get("static_ip", False),
                    ip_address=ip_config.get("ip_address"),
                    gateway=ip_config.get("gateway"),
                    dns_server_1=ip_config.get("dns_server_1", "8.8.8.8"),
                    dns_server_2=ip_config.get("dns_server_2"),
                    join_domain=bool(domain_join),
                    domain_name=domain_join.get("domain"),
                    domain_user=domain_join.get("user"),
                    domain_password=domain_join.get("password"),
                    windows_edition=windows_edition,
                    post_install_commands=[
                        {"command": cmd, "description": f"Custom command {i+1}"}
                        for i, cmd in enumerate(config.get("post_install_commands") or [])
                    ],
                    template_name=template_config.get("name"),
                )
                
                # Injecter le fichier unattend dans la VM via un disque dédié
                vm_identifier = vm.hypervisor_vm_id or vm.name
                await client.inject_unattend(vm_identifier, unattend_content)
                
                logger.info(
                    "unattend_injected",
                    deployment_id=str(deployment.id),
                    vm_id=str(vm.id),
                    length=len(unattend_content),
                )
                
            elif os_family == "linux":
                if "ubuntu" in template_config.get("name", "").lower():
                    content = self.template_engine.render_ubuntu_autoinstall(
                        hostname=config["hostname"],
                        username=config.get("username", "otoroot"),
                        static_ip=ip_config.get("static_ip", False),
                        ip_address=ip_config.get("ip_address"),
                        gateway=ip_config.get("gateway"),
                        dns_server_1=ip_config.get("dns_server_1", "8.8.8.8"),
                        post_install_commands=config.get("post_install_commands", []),
                    )
                else:
                    content = self.template_engine.render_debian_preseed(
                        hostname=config["hostname"],
                        username=config.get("username", "otoroot"),
                        user_password=config["admin_password"],
                        static_ip=ip_config.get("static_ip", False),
                        ip_address=ip_config.get("ip_address"),
                        gateway=ip_config.get("gateway"),
                        post_install_commands=config.get("post_install_commands", []),
                        os_type=template_config.get("os_type", "debian_12"),
                    )
                
                logger.info(
                    "preseed_generated",
                    deployment_id=str(deployment.id),
                    length=len(content),
                )
        finally:
            client.close()

    async def _try_credentials(
        self,
        client: Any,
        vm_identifier: str,
        vm_ip: str | None,
        use_winrm_direct: bool,
        admin_password: str,
        script: str,
        timeout: int = 30,
    ) -> tuple[bool, tuple[str, str] | None, Any]:
        """
        Essaie d'exécuter un script avec différents credentials (Administrateur/Administrator).
        
        Returns:
            Tuple (success, working_credentials, result)
        """
        credentials_list = _build_admin_credentials(admin_password)
        
        for credentials in credentials_list:
            try:
                if use_winrm_direct and vm_ip:
                    result = await client.execute_via_winrm_direct(
                        vm_ip, script, credentials, timeout=timeout
                    )
                else:
                    result = await client.execute_in_vm(
                        vm_identifier, script, credentials, timeout=timeout
                    )
                
                if result.success:
                    return True, credentials, result
            except Exception:
                continue
        
        return False, None, None

    async def _wait_for_vm_ready(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        timeout: int = 1200,
    ) -> bool:
        """
        Attend que la VM soit prête et accessible via PowerShell Direct.
        
        Le processus en 4 phases :
        1. Attendre le heartbeat (Windows a démarré)
        2. Récupérer l'IP et tenter WinRM direct
        3. Attendre le fichier flag C:\\VM-Automation\\ready.flag (setup terminé)
        4. Vérifier que PowerShell Direct fonctionne avec les credentials
        
        Renforcements:
        - Teste automatiquement Administrateur et Administrator (FR/EN)
        - Timeout dédié pour la phase flag (240s)
        - Compteur d'échecs consécutifs avec fallback/screenshot après N échecs
        - Utilise screenshot comme preuve de boot si connexion échoue
        
        Args:
            deployment: Le déploiement en cours
            vm: La VM créée
            timeout: Timeout en secondes (défaut: 10 minutes)
            
        Returns:
            True si la VM est accessible, False sinon
        """
        import time
        
        config = deployment.config
        admin_password = config.get("admin_password", "")
        
        try:
            client = await self.vm_service._get_hypervisor_client(deployment.hypervisor_id)
            
            # Utiliser l'UUID pour les opérations Hyper-V (heartbeat, IP, etc.)
            # Mais utiliser le nom pour PowerShell Direct (qui ne fonctionne qu'avec le nom)
            vm_identifier = vm.hypervisor_vm_id or vm.name
            vm_name_for_powershell = vm.name  # PowerShell Direct nécessite le nom, pas l'UUID
            # Credentials seront déterminés dynamiquement via _try_credentials
            working_credentials = None
            
            start_time = time.time()
            
            # Phase 1: Attendre le heartbeat (Windows boot) - timeout réduit
            await self._log_step(
                deployment, DeploymentStep.WAITING_VM_READY,
                "Phase 1/3: Waiting for Windows heartbeat...", "info"
            )
            
            heartbeat_timeout = min(timeout // 2, 720)  # Max 12 min pour le heartbeat (Windows OOBE needs up to 15 min)
            heartbeat_ok = await client.wait_for_vm_ready(
                vm_id=vm_identifier,
                vm_credentials=None,  # Pas de test credentials, juste heartbeat
                timeout=heartbeat_timeout,
                check_interval=10,
            )
            
            if not heartbeat_ok:
                await self._log_step(
                    deployment, DeploymentStep.WAITING_VM_READY,
                    "Windows heartbeat timeout - VM may not be running properly", "warning"
                )
                return False
            
            await self._log_step(
                deployment, DeploymentStep.WAITING_VM_READY,
                "Windows heartbeat OK - VM is running. Waiting 90s for OOBE/FirstLogonCommands to complete...", "info"
            )
            # Wait for OOBE and FirstLogonCommands (including ready.flag creation) to complete
            await asyncio.sleep(90)

            # Track heartbeat state for OOBE reboot detection
            had_heartbeat = True
            reboot_count = 0
            max_reboots = 2

            # Phase 2: Récupérer l'IP de la VM et tenter WinRM direct
            await self._log_step(
                deployment, DeploymentStep.WAITING_VM_READY,
                "Phase 2/4: Getting VM IP address...", "info"
            )
            
            vm_ip = None
            use_winrm_direct = False
            
            # Attendre que la VM obtienne une IP (max 60s)
            ip_wait_start = time.time()
            while (time.time() - ip_wait_start) < 60:
                try:
                    vm_ips = await client.get_vm_ip_addresses(vm_identifier)
                    # Filtrer les IPs link-local (169.254.x.x)
                    valid_ips = [ip for ip in vm_ips if ip and not ip.startswith("169.254.") and not ip.startswith("fe80:")]
                    if valid_ips:
                        vm_ip = valid_ips[0]
                        await self._log_step(
                            deployment, DeploymentStep.WAITING_VM_READY,
                            f"VM IP obtained: {vm_ip}", "info"
                        )
                        break
                except Exception as e:
                    logger.debug("deployment_get_ip_error", error=str(e))
                
                await asyncio.sleep(5)
            
            if vm_ip:
                # Tenter une connexion WinRM directe avec dual credentials
                await self._log_step(
                    deployment, DeploymentStep.WAITING_VM_READY,
                    f"Phase 3/4: Testing WinRM direct connection to {vm_ip} (trying Administrateur/Administrator)...", "info"
                )
                
                success, creds, result = await self._try_credentials(
                    client, vm_name_for_powershell, vm_ip, True, admin_password,
                    "$env:COMPUTERNAME", timeout=30
                )
                
                if success and creds:
                    use_winrm_direct = True
                    working_credentials = creds
                    hostname = str(result.output).strip() if result.output else "unknown"
                    await self._log_step(
                        deployment, DeploymentStep.WAITING_VM_READY,
                        f"WinRM direct connection OK (user: {creds[0]}) - hostname: {hostname}", "info"
                    )
                else:
                    logger.debug("deployment_winrm_direct_failed", vm_ip=vm_ip)
                    await self._log_step(
                        deployment, DeploymentStep.WAITING_VM_READY,
                        f"WinRM direct failed, falling back to PowerShell Direct", "warning"
                    )
            else:
                await self._log_step(
                    deployment, DeploymentStep.WAITING_VM_READY,
                    "Could not get VM IP, using PowerShell Direct", "warning"
                )
            
            # Phase 3: Attendre le fichier flag ready.flag
            await self._log_step(
                deployment, DeploymentStep.WAITING_VM_READY,
                "Phase 4/4: Waiting for VM-Automation setup to complete...", "info"
            )
            
            flag_check_interval = 10 if use_winrm_direct else 15
            flag_found = False
            fallback_attempted = False
            dir_checked = False
            checks_count = 0
            consecutive_failures = 0
            last_heartbeat = "OkApplicationsUnknown"  # Track heartbeat to detect VM reboots
            max_consecutive_failures = 8  # Après 8 échecs (~2-2.5 min), déclencher fallback/screenshot (OOBE reboot ~60s + boot ~45s)
            flag_phase_timeout = 600  # Timeout dédié pour la phase flag (10 min after OOBE)
            flag_phase_start = time.time()
            
            # Utiliser working_credentials si disponible, sinon essayer les deux
            if not working_credentials:
                # Essayer de trouver les credentials qui fonctionnent
                test_success, test_creds, _ = await self._try_credentials(
                    client, vm_name_for_powershell, vm_ip, use_winrm_direct, admin_password,
                    "$env:COMPUTERNAME", timeout=30
                )
                if test_success and test_creds:
                    working_credentials = test_creds
                    await self._log_step(
                        deployment, DeploymentStep.WAITING_VM_READY,
                        f"Working credentials found: {test_creds[0]}", "info"
                    )
            
            # Utiliser working_credentials ou fallback sur Administrateur
            current_credentials = working_credentials or _build_admin_credentials(admin_password)[0]
            
            while (time.time() - start_time) < timeout and (time.time() - flag_phase_start) < flag_phase_timeout and not flag_found:
                checks_count += 1

                # --- OOBE reboot detection ---
                # Windows reboots after OOBE, heartbeat goes NoContact temporarily.
                # Detect this and wait for the VM to come back instead of burning attempts.
                if had_heartbeat and reboot_count < max_reboots:
                    try:
                        current_heartbeat = await client.get_vm_heartbeat(vm_identifier)
                        if current_heartbeat in ("NoContact", "None", None, ""):
                            reboot_count += 1
                            await self._log_step(
                                deployment, DeploymentStep.WAITING_VM_READY,
                                f"OOBE reboot detected (reboot {reboot_count}/{max_reboots}) - waiting for VM to come back...", "warning"
                            )
                            consecutive_failures = 0

                            # Poll heartbeat until it comes back (max 120s)
                            reboot_wait_start = time.time()
                            reboot_recovered = False
                            while (time.time() - reboot_wait_start) < 120:
                                await asyncio.sleep(10)
                                try:
                                    hb = await client.get_vm_heartbeat(vm_identifier)
                                    if hb and hb not in ("NoContact", "None", None, ""):
                                        reboot_recovered = True
                                        break
                                except Exception as e:
                                    logger.debug("reboot_heartbeat_check_failed", vm_name=vm_identifier, error=str(e))

                            if reboot_recovered:
                                # Reset flag phase timer after OOBE reboot - give Windows time to run FirstLogonCommands
                                flag_phase_start = time.time()
                                await self._log_step(
                                    deployment, DeploymentStep.WAITING_VM_READY,
                                    "VM back after reboot - resetting flag timer, waiting 30s for Windows to run FirstLogonCommands", "info"
                                )
                                await asyncio.sleep(30)
                            else:
                                await self._log_step(
                                    deployment, DeploymentStep.WAITING_VM_READY,
                                    "VM did not recover heartbeat after reboot within 120s - continuing checks", "warning"
                                )
                    except Exception as hb_err:
                        logger.debug("deployment_reboot_heartbeat_check_error", error=str(hb_err))
                # --- End OOBE reboot detection ---

                try:
                    # Vérifier si le fichier flag existe avec dual credentials
                    flag_script = 'if (Test-Path "C:\\VM-Automation\\ready.flag") { "FLAG_FOUND" } else { "FLAG_NOT_FOUND" }'
                    success, creds, result = await self._try_credentials(
                        client, vm_name_for_powershell, vm_ip, use_winrm_direct, admin_password,
                        flag_script, timeout=30
                    )
                    
                    if success and creds:
                        # Connexion réussie - réinitialiser le compteur d'échecs
                        consecutive_failures = 0
                        if working_credentials != creds:
                            working_credentials = creds
                            await self._log_step(
                                deployment, DeploymentStep.WAITING_VM_READY,
                                f"Connection working with user: {creds[0]}", "info"
                            )
                    
                        if result and "FLAG_FOUND" in str(result.output):
                            flag_found = True
                            await self._log_step(
                                deployment, DeploymentStep.WAITING_VM_READY,
                                "VM-Automation setup completed - ready.flag found", "info"
                            )
                            break
                        elif result and not fallback_attempted and not dir_checked:
                            # Connexion fonctionne - vérifier si le dossier VM-Automation existe
                            dir_checked = True
                            dir_script = 'if (Test-Path "C:\\VM-Automation") { "DIR_EXISTS" } else { "DIR_MISSING" }'
                            dir_success, dir_creds, dir_result = await self._try_credentials(
                                client, vm_name_for_powershell, vm_ip, use_winrm_direct, admin_password,
                                dir_script, timeout=30
                            )
                            
                            if dir_success and dir_result and "DIR_MISSING" in str(dir_result.output):
                                # Le dossier n'existe pas - exécuter le fallback IMMÉDIATEMENT
                                fallback_attempted = True
                                method_msg = "via WinRM direct" if use_winrm_direct else "via PowerShell Direct"
                                await self._log_step(
                                    deployment, DeploymentStep.WAITING_VM_READY,
                                    f"VM-Automation folder missing - executing fallback setup IMMEDIATELY {method_msg}", "warning"
                                )
                                
                                fallback_result = await self._execute_fallback_setup(
                                    client, vm_identifier, dir_creds or creds, admin_password,
                                    vm_ip=vm_ip, use_winrm_direct=use_winrm_direct
                                )
                                
                                if fallback_result:
                                    await self._log_step(
                                        deployment, DeploymentStep.WAITING_VM_READY,
                                        "Fallback setup executed successfully - flag created", "info"
                                    )
                                    flag_found = True
                                    break
                                else:
                                    await self._log_step(
                                        deployment, DeploymentStep.WAITING_VM_READY,
                                        "Fallback setup failed - will retry", "error"
                                    )
                            else:
                                # Le dossier existe mais pas le flag - le script est peut-être en cours
                                logger.debug(
                                    "deployment_dir_exists_waiting_flag",
                                    deployment_id=str(deployment.id),
                                )
                        elif result and not fallback_attempted and checks_count >= 4:
                            # Après ~40-60s, si le flag n'existe toujours pas, tenter le fallback
                            fallback_attempted = True
                            method_msg = "via WinRM direct" if use_winrm_direct else "via PowerShell Direct"
                            await self._log_step(
                                deployment, DeploymentStep.WAITING_VM_READY,
                                f"Flag not found after waiting - attempting fallback setup {method_msg}...", "warning"
                            )
                            
                                # Tenter d'exécuter le script setup.ps1 manuellement
                            fallback_result = await self._execute_fallback_setup(
                                client, vm_name_for_powershell, creds or current_credentials, admin_password,
                                vm_ip=vm_ip, use_winrm_direct=use_winrm_direct
                            )
                            
                            if fallback_result:
                                await self._log_step(
                                    deployment, DeploymentStep.WAITING_VM_READY,
                                    "Fallback setup executed successfully", "info"
                                )
                                flag_found = True
                                break
                            else:
                                await self._log_step(
                                    deployment, DeploymentStep.WAITING_VM_READY,
                                    "Fallback setup failed - continuing checks...", "warning"
                                )
                    else:
                        # Connexion échouée - incrémenter le compteur d'échecs
                        consecutive_failures += 1
                        logger.debug(
                            "deployment_connection_failed",
                            deployment_id=str(deployment.id),
                            consecutive_failures=consecutive_failures,
                            checks_count=checks_count,
                        )

                        # Check if VM rebooted (heartbeat change indicates fresh state)
                        try:
                            current_hb = await client.get_vm_heartbeat(vm_identifier)
                            if current_hb and current_hb != last_heartbeat:
                                if last_heartbeat is not None:
                                    logger.info(
                                        "deployment_heartbeat_changed",
                                        old=last_heartbeat, new=current_hb,
                                        deployment_id=str(deployment.id),
                                    )
                                    consecutive_failures = 0  # Reset on heartbeat state change
                                last_heartbeat = current_hb
                        except Exception as e:
                            logger.debug("heartbeat_monitor_failed", vm_name=vm_identifier, error=str(e))

                        # Après N échecs consécutifs, vérifier IP + heartbeat pour confirmer que Windows est démarré
                        if consecutive_failures >= max_consecutive_failures and not fallback_attempted:
                            await self._log_step(
                                deployment, DeploymentStep.WAITING_VM_READY,
                                f"Connection never succeeded after {consecutive_failures} attempts - verifying Windows boot status (IP + heartbeat)...", "warning"
                            )
                            
                            # Vérifier IP (indicateur fiable que Windows est démarré et réseau fonctionne)
                            has_valid_ip = False
                            current_vm_ip = None
                            try:
                                vm_ips = await client.get_vm_ip_addresses(vm_identifier)
                                valid_ips = [ip for ip in vm_ips if ip and not ip.startswith("169.254.") and not ip.startswith("fe80:")]
                                if valid_ips:
                                    has_valid_ip = True
                                    current_vm_ip = valid_ips[0]
                                    # Mettre à jour vm_ip si on n'en avait pas avant
                                    if not vm_ip:
                                        vm_ip = current_vm_ip
                            except Exception as e:
                                logger.debug("deployment_get_ip_check_error", error=str(e))
                            
                            # Vérifier heartbeat (indicateur que Windows est démarré)
                            heartbeat_ok = False
                            heartbeat_value = None
                            try:
                                heartbeat_value = await client.get_vm_heartbeat(vm_identifier)
                                invalid_heartbeats = ("NoContact", "None", None, "")
                                heartbeat_ok = heartbeat_value and heartbeat_value not in invalid_heartbeats
                            except Exception as e:
                                logger.debug("deployment_heartbeat_check_error", error=str(e))
                            
                            # Si IP valide OU heartbeat OK, Windows est démarré
                            if has_valid_ip or heartbeat_ok:
                                indicators = []
                                if has_valid_ip:
                                    indicators.append(f"IP: {current_vm_ip}")
                                if heartbeat_ok:
                                    indicators.append(f"heartbeat: {heartbeat_value}")
                                
                                await self._log_step(
                                    deployment, DeploymentStep.WAITING_VM_READY,
                                    f"Windows is booted ({', '.join(indicators)}) but connection failed. Continuing deployment with warning - post-config may fail if connection not available.", "warning",
                                    details={
                                        "has_valid_ip": has_valid_ip,
                                        "vm_ip": current_vm_ip,
                                        "heartbeat": heartbeat_value,
                                        "heartbeat_ok": heartbeat_ok,
                                        "consecutive_failures": consecutive_failures
                                    }
                                )
                                # Ne pas marquer flag_found = True ici - on continue mais avec warning
                                # Le flag sera considéré comme "timeout" et on continuera quand même
                            else:
                                await self._log_step(
                                    deployment, DeploymentStep.WAITING_VM_READY,
                                    f"Connection failed and no valid indicators (IP: {current_vm_ip or 'none'}, heartbeat: {heartbeat_value}) - Windows may not be fully booted yet", "warning",
                                    details={
                                        "has_valid_ip": has_valid_ip,
                                        "vm_ip": current_vm_ip,
                                        "heartbeat": heartbeat_value,
                                        "consecutive_failures": consecutive_failures
                                    }
                                )
                            
                            # Tenter quand même le fallback si on a des credentials qui ont fonctionné avant
                            if working_credentials:
                                fallback_attempted = True
                                await self._log_step(
                                    deployment, DeploymentStep.WAITING_VM_READY,
                                    "Attempting fallback setup with previously working credentials...", "warning"
                                )
                                fallback_result = await self._execute_fallback_setup(
                                    client, vm_name_for_powershell, working_credentials, admin_password,
                                    vm_ip=vm_ip, use_winrm_direct=use_winrm_direct
                                )
                                if fallback_result:
                                    flag_found = True
                                    break
                        
                except Exception as e:
                    # PowerShell Direct peut échouer si le setup n'est pas encore terminé
                    consecutive_failures += 1
                    logger.debug(
                        "deployment_flag_check_error",
                        deployment_id=str(deployment.id),
                        error=str(e),
                        consecutive_failures=consecutive_failures,
                    )
                    
                    # Après N échecs consécutifs (exceptions), vérifier IP + heartbeat
                    if consecutive_failures >= max_consecutive_failures and not flag_found:
                        await self._log_step(
                            deployment, DeploymentStep.WAITING_VM_READY,
                            f"Multiple connection failures ({consecutive_failures}) - verifying Windows boot status (IP + heartbeat)...", "warning"
                        )
                        
                        # Vérifier IP + heartbeat
                        has_valid_ip = False
                        current_vm_ip = None
                        try:
                            vm_ips = await client.get_vm_ip_addresses(vm_identifier)
                            valid_ips = [ip for ip in vm_ips if ip and not ip.startswith("169.254.") and not ip.startswith("fe80:")]
                            if valid_ips:
                                has_valid_ip = True
                                current_vm_ip = valid_ips[0]
                                if not vm_ip:
                                    vm_ip = current_vm_ip
                        except Exception as ip_error:
                            logger.debug("deployment_get_ip_exception_error", error=str(ip_error))
                        
                        heartbeat_ok = False
                        heartbeat_value = None
                        try:
                            heartbeat_value = await client.get_vm_heartbeat(vm_identifier)
                            invalid_heartbeats = ("NoContact", "None", None, "")
                            heartbeat_ok = heartbeat_value and heartbeat_value not in invalid_heartbeats
                        except Exception as hb_error:
                            logger.debug("deployment_heartbeat_exception_error", error=str(hb_error))
                        
                        if has_valid_ip or heartbeat_ok:
                            indicators = []
                            if has_valid_ip:
                                indicators.append(f"IP: {current_vm_ip}")
                            if heartbeat_ok:
                                indicators.append(f"heartbeat: {heartbeat_value}")
                            
                            await self._log_step(
                                deployment, DeploymentStep.WAITING_VM_READY,
                                f"Windows is booted ({', '.join(indicators)}) but connection failed. Continuing with warning.", "warning",
                                details={
                                    "has_valid_ip": has_valid_ip,
                                    "vm_ip": current_vm_ip,
                                    "heartbeat": heartbeat_value,
                                    "heartbeat_ok": heartbeat_ok,
                                    "consecutive_failures": consecutive_failures
                                }
                            )
                            # Ne pas marquer flag_found = True - on continue avec warning
                
                await asyncio.sleep(flag_check_interval)
            
            # Si timeout de la phase flag atteint, vérifier IP + heartbeat avant de continuer
            if not flag_found and (time.time() - flag_phase_start) >= flag_phase_timeout:
                await self._log_step(
                    deployment, DeploymentStep.WAITING_VM_READY,
                    f"Flag phase timeout ({flag_phase_timeout}s) - verifying Windows boot status (IP + heartbeat)...", "warning"
                )
                
                # Vérifier IP (indicateur fiable que Windows est démarré)
                has_valid_ip = False
                current_vm_ip = None
                try:
                    vm_ips = await client.get_vm_ip_addresses(vm_identifier)
                    valid_ips = [ip for ip in vm_ips if ip and not ip.startswith("169.254.") and not ip.startswith("fe80:")]
                    if valid_ips:
                        has_valid_ip = True
                        current_vm_ip = valid_ips[0]
                        # Mettre à jour vm_ip si on n'en avait pas avant
                        if not vm_ip:
                            vm_ip = current_vm_ip
                except Exception as e:
                    logger.debug("deployment_get_ip_timeout_error", error=str(e))
                
                # Vérifier heartbeat
                heartbeat_ok = False
                heartbeat_value = None
                try:
                    heartbeat_value = await client.get_vm_heartbeat(vm_identifier)
                    invalid_heartbeats = ("NoContact", "None", None, "")
                    heartbeat_ok = heartbeat_value and heartbeat_value not in invalid_heartbeats
                except Exception as e:
                    logger.debug("deployment_heartbeat_timeout_error", error=str(e))
                
                # Si IP valide OU heartbeat OK, Windows est démarré
                if has_valid_ip or heartbeat_ok:
                    indicators = []
                    if has_valid_ip:
                        indicators.append(f"IP: {current_vm_ip}")
                    if heartbeat_ok:
                        indicators.append(f"heartbeat: {heartbeat_value}")
                    
                    await self._log_step(
                        deployment, DeploymentStep.WAITING_VM_READY,
                        f"Windows is booted ({', '.join(indicators)}) but ready.flag timeout. Continuing deployment with warning.", "warning",
                        details={
                            "ready_via_indicators": True,
                            "has_valid_ip": has_valid_ip,
                            "vm_ip": current_vm_ip,
                            "heartbeat": heartbeat_value,
                            "heartbeat_ok": heartbeat_ok,
                            "flag_timeout": True
                        }
                    )
                    # Ne pas marquer flag_found = True - on continue avec warning
                else:
                    await self._log_step(
                        deployment, DeploymentStep.WAITING_VM_READY,
                        f"Flag timeout and no valid indicators (IP: {current_vm_ip or 'none'}, heartbeat: {heartbeat_value}) - continuing anyway", "warning",
                        details={
                            "has_valid_ip": has_valid_ip,
                            "vm_ip": current_vm_ip,
                            "heartbeat": heartbeat_value,
                            "flag_timeout": True
                        }
                    )
            
            if not flag_found:
                await self._log_step(
                    deployment, DeploymentStep.WAITING_VM_READY,
                    "Timeout waiting for VM-Automation setup - continuing anyway", "warning",
                    details={"checks_count": checks_count, "consecutive_failures": consecutive_failures}
                )
                # On continue quand même car le setup peut avoir fonctionné
            
            # Phase finale: Vérifier que la connexion fonctionne
            connection_method = "WinRM direct" if use_winrm_direct else "PowerShell Direct"
            await self._log_step(
                deployment, DeploymentStep.WAITING_VM_READY,
                f"Final verification: Testing {connection_method} connection...", "info"
            )
            
            # Utiliser working_credentials si disponible
            final_credentials = working_credentials or _build_admin_credentials(admin_password)[0]
            
            # Tester la connexion avec dual credentials
            max_retries = 5
            for attempt in range(max_retries):
                success, creds, result = await self._try_credentials(
                    client, vm_name_for_powershell, vm_ip, use_winrm_direct, admin_password,
                    "$env:COMPUTERNAME", timeout=30
                )

                if success and creds and result:
                    hostname = str(result.output).strip() if result.output else "unknown"
                    await self._log_step(
                        deployment, DeploymentStep.WAITING_VM_READY,
                        f"{connection_method} connected (user: {creds[0]}) - hostname: {hostname}", "info"
                    )
                    return True
                else:
                    logger.debug(
                        "deployment_connection_failed",
                        deployment_id=str(deployment.id),
                        attempt=attempt + 1,
                        method=connection_method,
                    )

                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
            
            # Si la connexion échoue mais qu'on a des indicateurs valides (IP + heartbeat), considérer la VM ready quand même
            # Vérifier une dernière fois IP + heartbeat
            has_valid_ip_final = False
            heartbeat_ok_final = False
            try:
                vm_ips_final = await client.get_vm_ip_addresses(vm_identifier)
                valid_ips_final = [ip for ip in vm_ips_final if ip and not ip.startswith("169.254.") and not ip.startswith("fe80:")]
                if valid_ips_final:
                    has_valid_ip_final = True
            except Exception as e:
                logger.debug("final_ip_check_failed", vm_name=vm_identifier, error=str(e))

            try:
                heartbeat_final = await client.get_vm_heartbeat(vm_identifier)
                invalid_heartbeats = ("NoContact", "None", None, "")
                heartbeat_ok_final = heartbeat_final and heartbeat_final not in invalid_heartbeats
            except Exception as e:
                logger.debug("final_heartbeat_check_failed", vm_name=vm_identifier, error=str(e))
            
            if has_valid_ip_final or heartbeat_ok_final:
                indicators_final = []
                if has_valid_ip_final:
                    indicators_final.append("IP valid")
                if heartbeat_ok_final:
                    indicators_final.append("heartbeat OK")
                
                await self._log_step(
                    deployment, DeploymentStep.WAITING_VM_READY,
                    f"{connection_method} connection failed but Windows is booted ({', '.join(indicators_final)}) - continuing deployment with warning", "warning",
                    details={
                        "has_valid_ip": has_valid_ip_final,
                        "heartbeat_ok": heartbeat_ok_final,
                        "connection_failed": True
                    }
                )
                return True
            
            await self._log_step(
                deployment, DeploymentStep.WAITING_VM_READY,
                f"{connection_method} connection failed after retries", "warning"
            )
            return False
            
        except Exception as e:
            logger.warning(
                "deployment_wait_vm_ready_failed",
                deployment_id=str(deployment.id),
                error=str(e),
            )
            return False

    async def _execute_fallback_setup(
        self,
        client: Any,
        vm_identifier: str,
        credentials: tuple[str, str],
        admin_password: str,
        vm_ip: str | None = None,
        use_winrm_direct: bool = False,
    ) -> bool:
        """
        Exécute la configuration de setup manuellement.
        
        Utilise WinRM direct si vm_ip est fourni, sinon PowerShell Direct.
        
        Args:
            client: Client Hyper-V
            vm_identifier: ID ou nom de la VM
            credentials: Credentials pour la connexion
            admin_password: Mot de passe admin à configurer
            vm_ip: IP de la VM pour WinRM direct (optionnel)
            use_winrm_direct: Utiliser WinRM direct au lieu de PowerShell Direct
            
        Returns:
            True si la configuration a réussi
        """
        method = "WinRM direct" if (use_winrm_direct and vm_ip) else "PowerShell Direct"
        logger.info(
            "deployment_fallback_setup_starting",
            vm_id=vm_identifier,
            method=method,
            vm_ip=vm_ip if use_winrm_direct else None,
        )
        
        # Determine the admin account name from credentials (first part after .\)
        admin_account = credentials[0].replace(".\\", "") if credentials[0].startswith(".\\") else credentials[0]

        # Script de configuration minimal
        fallback_script = f'''
$ErrorActionPreference = 'Continue'
$logFile = "C:\\VM-Automation\\setup.log"

# Créer le dossier si nécessaire
if (-not (Test-Path "C:\\VM-Automation")) {{
    New-Item -ItemType Directory -Path "C:\\VM-Automation" -Force | Out-Null
}}

"$(Get-Date) - Fallback setup starting..." | Out-File $logFile -Append

try {{
    # 1. Configurer le mot de passe admin
    net user {admin_account} "{admin_password}" /active:yes 2>&1 | Out-Null
    "$(Get-Date) - {admin_account} configured" | Out-File $logFile -Append
    
    # 2. Configurer WinRM
    Enable-PSRemoting -Force -SkipNetworkProfileCheck -ErrorAction SilentlyContinue
    Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value '*' -Force -ErrorAction SilentlyContinue
    "$(Get-Date) - WinRM configured" | Out-File $logFile -Append
    
    # 3. Activer RDP
    Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -Name "fDenyTSConnections" -Value 0 -ErrorAction SilentlyContinue
    Enable-NetFirewallRule -DisplayGroup "Remote Desktop" -ErrorAction SilentlyContinue
    Enable-NetFirewallRule -DisplayGroup "Bureau à distance" -ErrorAction SilentlyContinue
    "$(Get-Date) - RDP enabled" | Out-File $logFile -Append
    
    # 4. Configurer le réseau en Privé
    Get-NetConnectionProfile | Set-NetConnectionProfile -NetworkCategory Private -ErrorAction SilentlyContinue
    "$(Get-Date) - Network configured" | Out-File $logFile -Append
    
    # 5. Créer le flag de succès
    "READY" | Out-File "C:\\VM-Automation\\ready.flag"
    "$(Get-Date) - Fallback setup complete!" | Out-File $logFile -Append
    
    "FALLBACK_SUCCESS"
}} catch {{
    "$(Get-Date) - ERROR: $($_.Exception.Message)" | Out-File $logFile -Append
    "FALLBACK_FAILED"
}}
'''
        
        try:
            # Utiliser WinRM direct si disponible (plus rapide et plus fiable)
            if use_winrm_direct and vm_ip:
                result = await client.execute_via_winrm_direct(
                    vm_ip,
                    fallback_script,
                    credentials,
                    timeout=120,
                )
            else:
                result = await client.execute_in_vm(
                    vm_identifier,
                    fallback_script,
                    credentials,
                    timeout=120,
                )
            
            if result.success and "FALLBACK_SUCCESS" in str(result.output):
                logger.info(
                    "deployment_fallback_setup_success",
                    vm_id=vm_identifier,
                    method=method,
                )
                return True
            else:
                logger.warning(
                    "deployment_fallback_setup_failed",
                    vm_id=vm_identifier,
                    method=method,
                    output=str(result.output)[:200] if result.output else "no output",
                    error=result.error,
                )
                return False
                
        except Exception as e:
            logger.warning(
                "deployment_fallback_setup_error",
                vm_id=vm_identifier,
                error=str(e),
            )
            return False

    async def _execute_post_configuration(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
    ) -> None:
        """
        Exécute les configurations post-installation.
        
        - Active/configure les services (SSH, RDP, WinRM)
        - Configure les politiques de sécurité
        - Configure le firewall
        """
        from src.domain.post_install_service import PostInstallService
        
        config = deployment.config
        admin_password = config.get("admin_password", "")
        credentials = _build_admin_credentials(admin_password, config=config)[0]

        try:
            client = await self.vm_service._get_hypervisor_client(deployment.hypervisor_id)
            post_install = PostInstallService(client)
            
            vm_name = vm.hypervisor_vm_id or vm.name
            services_config = config.get("services", {})
            
            # 1. Installer SSH si demandé
            if services_config.get("enable_ssh", False):
                await self._log_step(
                    deployment, DeploymentStep.POST_CONFIGURATION,
                    "Installing OpenSSH Server...", "info"
                )
                result = await post_install.install_ssh_server(vm_name, credentials)
                if result.success:
                    await self._log_step(
                        deployment, DeploymentStep.POST_CONFIGURATION,
                        f"SSH Server installed: {result.status}", "info"
                    )
                else:
                    await self._log_step(
                        deployment, DeploymentStep.POST_CONFIGURATION,
                        f"SSH installation failed: {result.error}", "warning"
                    )
            
            # 2. Configurer WinRM si demandé
            if services_config.get("enable_winrm", True):
                await self._log_step(
                    deployment, DeploymentStep.POST_CONFIGURATION,
                    "Configuring WinRM service...", "info"
                )
                result = await post_install.configure_service(
                    vm_name, credentials, "WinRM", "Automatic", True
                )
                if result.success:
                    await self._log_step(
                        deployment, DeploymentStep.POST_CONFIGURATION,
                        "WinRM configured successfully", "info"
                    )
            
            # 3. Configurer RDP si demandé
            if services_config.get("enable_rdp", True):
                await self._log_step(
                    deployment, DeploymentStep.POST_CONFIGURATION,
                    "Configuring Remote Desktop...", "info"
                )
                # Activer RDP via registre + firewall (EN + FR)
                rdp_script = """
                Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -Name "fDenyTSConnections" -Value 0 -ErrorAction SilentlyContinue
                Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp' -Name "UserAuthentication" -Value 0 -ErrorAction SilentlyContinue
                Enable-NetFirewallRule -DisplayGroup "Remote Desktop" -ErrorAction SilentlyContinue
                Enable-NetFirewallRule -DisplayGroup "Bureau à distance" -ErrorAction SilentlyContinue
                """
                await client.execute_in_vm(vm_name, rdp_script, credentials)
                await self._log_step(
                    deployment, DeploymentStep.POST_CONFIGURATION,
                    "Remote Desktop enabled", "info"
                )
            
            # 4. Configurer les politiques de mot de passe
            security_config = config.get("security", {})
            if security_config.get("configure_password_policy", False):
                await self._log_step(
                    deployment, DeploymentStep.POST_CONFIGURATION,
                    "Configuring password policy...", "info"
                )
                result = await post_install.configure_password_policy(
                    vm_name, credentials,
                    min_length=security_config.get("password_min_length", 8),
                    complexity_enabled=security_config.get("password_complexity", True),
                    max_age_days=security_config.get("password_max_age", 90),
                )
                if result.success:
                    await self._log_step(
                        deployment, DeploymentStep.POST_CONFIGURATION,
                        "Password policy configured", "info"
                    )
            
            # 5. Installer les mises à jour Windows si demandé
            if config.get("enable_windows_update", False):
                await self._log_step(
                    deployment, DeploymentStep.POST_CONFIGURATION,
                    "Checking for Windows updates...", "info"
                )
                result = await post_install.install_windows_updates(
                    vm_name, credentials,
                    auto_reboot=False,  # Pas de reboot automatique pendant le déploiement
                )
                await self._log_step(
                    deployment, DeploymentStep.POST_CONFIGURATION,
                    f"Windows Update: {result.updates_installed} updates installed, reboot required: {result.reboot_required}",
                    "info"
                )
            
            logger.info(
                "deployment_post_config_complete",
                deployment_id=str(deployment.id),
                services_configured=list(services_config.keys()),
            )
            
        except Exception as e:
            logger.error(
                "deployment_post_config_error",
                deployment_id=str(deployment.id),
                error=str(e),
            )
            await self._log_step(
                deployment, DeploymentStep.POST_CONFIGURATION,
                f"Post-configuration error: {e}", "warning"
            )

    async def _install_software(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
    ) -> None:
        """
        Installe les logiciels demandés via Chocolatey.
        
        Supporte les profils prédéfinis et les packages personnalisés.
        """
        from src.domain.software_install_service import (
            SoftwareInstallService,
            SoftwarePackage,
            PackageManager,
            SOFTWARE_PROFILES,
        )
        
        config = deployment.config
        admin_password = config.get("admin_password", "")
        credentials = _build_admin_credentials(admin_password, config=config)[0]

        try:
            client = await self.vm_service._get_hypervisor_client(deployment.hypervisor_id)
            software_service = SoftwareInstallService(client)

            vm_name = vm.hypervisor_vm_id or vm.name

            # 0. Attendre que la VM soit en état Running (peut redémarrer après post-config)
            await self._log_step(
                deployment, DeploymentStep.INSTALLING_SOFTWARE,
                "Waiting for VM to be in Running state before software install...", "info"
            )
            vm_identifier = vm.hypervisor_vm_id or vm.name
            for attempt in range(30):  # 30 x 10s = 5 min max
                state = await client.get_vm_state(vm_identifier)
                if state and state.lower() in ("running", "2"):
                    break
                if attempt % 3 == 0:
                    await self._log_step(
                        deployment, DeploymentStep.INSTALLING_SOFTWARE,
                        f"VM not yet running (state: {state}), waiting... ({attempt * 10}s)", "info"
                    )
                await asyncio.sleep(10)
            else:
                await self._log_step(
                    deployment, DeploymentStep.INSTALLING_SOFTWARE,
                    f"VM still not running after 5 minutes (state: {state}). Skipping software install.", "warning"
                )
                return

            # Attendre que PowerShell Direct soit opérationnel après le démarrage
            await asyncio.sleep(15)

            # 1. S'assurer que Chocolatey est installé
            await self._log_step(
                deployment, DeploymentStep.INSTALLING_SOFTWARE,
                "Ensuring Chocolatey is installed...", "info"
            )
            choco_ready = await software_service.ensure_chocolatey_installed(vm_name, credentials)
            
            if not choco_ready:
                await self._log_step(
                    deployment, DeploymentStep.INSTALLING_SOFTWARE,
                    "Failed to install Chocolatey. Skipping software installation.", "error"
                )
                return
            
            await self._log_step(
                deployment, DeploymentStep.INSTALLING_SOFTWARE,
                "Chocolatey is ready", "info"
            )
            
            # 2. Construire la liste des packages à installer
            packages_to_install: list[SoftwarePackage] = []
            
            # Packages du profil
            software_profile = config.get("software_profile")
            if software_profile and software_profile in SOFTWARE_PROFILES:
                profile_packages = SOFTWARE_PROFILES[software_profile]
                packages_to_install.extend(profile_packages)
                await self._log_step(
                    deployment, DeploymentStep.INSTALLING_SOFTWARE,
                    f"Profile '{software_profile}': {len(profile_packages)} packages", "info"
                )
            
            # Packages personnalisés
            custom_packages = config.get("packages", [])
            for pkg_name in custom_packages:
                if not any(p.name == pkg_name for p in packages_to_install):
                    packages_to_install.append(
                        SoftwarePackage(name=pkg_name, package_manager=PackageManager.CHOCOLATEY)
                    )
            
            if not packages_to_install:
                await self._log_step(
                    deployment, DeploymentStep.INSTALLING_SOFTWARE,
                    "No software packages to install", "info"
                )
                return
            
            # 3. Installer les packages
            await self._log_step(
                deployment, DeploymentStep.INSTALLING_SOFTWARE,
                f"Installing {len(packages_to_install)} packages...", "info"
            )
            
            result = await software_service.install_packages(
                vm_name, credentials, packages_to_install,
                continue_on_error=True,
            )
            
            # 4. Logger les résultats
            for pkg_result in result.results:
                status_emoji = "✅" if pkg_result.status.value == "installed" else "⏭️" if pkg_result.status.value == "skipped" else "❌"
                version_info = f" v{pkg_result.version_installed}" if pkg_result.version_installed else ""
                error_info = f" - {pkg_result.error}" if pkg_result.error else ""
                await self._log_step(
                    deployment, DeploymentStep.INSTALLING_SOFTWARE,
                    f"{status_emoji} {pkg_result.package_name}{version_info}{error_info}",
                    "info" if pkg_result.status.value != "failed" else "warning"
                )
            
            summary = f"Software installation: {result.installed} installed, {result.skipped} skipped, {result.failed} failed"
            if result.reboot_required:
                summary += " (reboot required)"
            
            await self._log_step(
                deployment, DeploymentStep.INSTALLING_SOFTWARE,
                summary, "info"
            )
            
            # 5. Exécuter les scripts de configuration des packages
            package_configs = config.get("package_configs", {})
            if package_configs:
                from src.domain.software_catalog import get_software_by_name
                
                await self._log_step(
                    deployment, DeploymentStep.INSTALLING_SOFTWARE,
                    f"Configuring {len(package_configs)} package(s)...", "info"
                )
                
                for pkg_name, pkg_config in package_configs.items():
                    software_def = get_software_by_name(pkg_name)
                    if software_def and software_def.get("post_install_script"):
                        script = software_def["post_install_script"]
                        # Remplacer les placeholders par les valeurs configurées
                        for key, value in pkg_config.items():
                            script = script.replace(f"{{{key}}}", str(value) if value else "")
                        
                        try:
                            await self._log_step(
                                deployment, DeploymentStep.INSTALLING_SOFTWARE,
                                f"Configuring {pkg_name}...", "info"
                            )
                            result_script = await client.execute_in_vm(vm_name, script, credentials, timeout=120)
                            if result_script.success:
                                await self._log_step(
                                    deployment, DeploymentStep.INSTALLING_SOFTWARE,
                                    f"✅ {pkg_name} configured", "info"
                                )
                            else:
                                await self._log_step(
                                    deployment, DeploymentStep.INSTALLING_SOFTWARE,
                                    f"⚠️ {pkg_name} config failed: {result_script.error}", "warning"
                                )
                        except Exception as cfg_e:
                            await self._log_step(
                                deployment, DeploymentStep.INSTALLING_SOFTWARE,
                                f"⚠️ {pkg_name} config error: {cfg_e}", "warning"
                            )
            
            logger.info(
                "deployment_software_install_complete",
                deployment_id=str(deployment.id),
                installed=result.installed,
                failed=result.failed,
                reboot_required=result.reboot_required,
            )
            
        except Exception as e:
            logger.error(
                "deployment_software_install_error",
                deployment_id=str(deployment.id),
                error=str(e),
            )
            await self._log_step(
                deployment, DeploymentStep.INSTALLING_SOFTWARE,
                f"Software installation error: {e}", "warning"
            )

    async def _finalize_deployment(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
    ) -> None:
        """
        Finalise le déploiement.
        
        - Nettoie les fichiers temporaires
        - Met à jour les informations réseau de la VM
        - Génère un rapport final
        """
        config = deployment.config
        
        try:
            client = await self.vm_service._get_hypervisor_client(deployment.hypervisor_id)
            vm_name = vm.hypervisor_vm_id or vm.name
            
            # 1. Récupérer les infos réseau de la VM
            await self._log_step(
                deployment, DeploymentStep.FINALIZING,
                "Retrieving network information...", "info"
            )
            
            try:
                network_info = await client.get_vm_network_summary(vm_name)
                if network_info.get("ip_addresses"):
                    ip = network_info["ip_addresses"][0]
                    await self._log_step(
                        deployment, DeploymentStep.FINALIZING,
                        f"VM IP address: {ip}", "info"
                    )
                    # Mettre à jour la VM en base
                    vm.ip_address = ip
                    await self.db.flush()
            except Exception as e:
                logger.warning("deployment_network_info_error", error=str(e))
            
            # 2. Nettoyer les fichiers temporaires (ISO OEMDRV, etc.)
            await self._log_step(
                deployment, DeploymentStep.FINALIZING,
                "Cleaning up temporary files...", "info"
            )
            
            try:
                cleanup_result = await client.cleanup_post_install(vm_name)
                if cleanup_result.get("iso_unmounted"):
                    await self._log_step(
                        deployment, DeploymentStep.FINALIZING,
                        "Installation media unmounted", "info"
                    )
            except Exception as e:
                logger.warning("deployment_cleanup_error", error=str(e))
            
            # 3. Résumé du déploiement
            services = config.get("services", {})
            software_profile = config.get("software_profile", "")
            
            summary_lines = [
                f"VM Name: {config['vm_name']}",
                f"Hostname: {config.get('hostname', config['vm_name'])}",
            ]
            
            if services:
                enabled_services = [k.replace("enable_", "") for k, v in services.items() if v]
                if enabled_services:
                    summary_lines.append(f"Services: {', '.join(enabled_services)}")
            
            if software_profile:
                summary_lines.append(f"Software profile: {software_profile}")
            
            await self._log_step(
                deployment, DeploymentStep.FINALIZING,
                "Deployment summary:\n" + "\n".join(summary_lines), "info"
            )
            
        except Exception as e:
            logger.warning(
                "deployment_finalize_error",
                deployment_id=str(deployment.id),
                error=str(e),
            )

    async def get_deployment(self, deployment_id: UUID) -> Deployment:
        """Récupère un déploiement par son ID."""
        result = await self.db.execute(
            select(Deployment).where(Deployment.id == deployment_id)
        )
        deployment = result.scalar_one_or_none()
        if not deployment:
            raise NotFoundError("Deployment", str(deployment_id))
        return deployment

    async def list_deployments(
        self,
        status: DeploymentStatus | None = None,
        limit: int = 50,
    ) -> list[Deployment]:
        """Liste les déploiements avec eager loading des relations."""
        query = (
            select(Deployment)
            .options(
                selectinload(Deployment.hypervisor),
                selectinload(Deployment.os_template),
                selectinload(Deployment.virtual_machine),
                selectinload(Deployment.logs),
            )
            .order_by(Deployment.created_at.desc())
            .limit(limit)
        )

        if status:
            query = query.where(Deployment.status == status)

        result = await self.db.execute(query)
        return list(result.scalars().unique().all())

    async def cancel_deployment(self, deployment_id: UUID) -> Deployment:
        """Annule un déploiement."""
        deployment = await self.get_deployment(deployment_id)
        
        if deployment.status in (DeploymentStatus.COMPLETED, DeploymentStatus.CANCELLED):
            raise ValidationError(f"Cannot cancel deployment in status {deployment.status}")
        
        await self._update_deployment_status(
            deployment,
            DeploymentStatus.CANCELLED,
            error_message="Cancelled by user",
        )
        
        await self._log_step(
            deployment,
            "cancelled",
            "Deployment cancelled by user",
            "warning",
        )
        
        return deployment
