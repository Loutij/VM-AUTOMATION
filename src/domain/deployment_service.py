# =============================================================================
# VM Automation - Deployment Service
# =============================================================================
"""
Service pour orchestrer le déploiement complet de VMs.
Gère le workflow: création VM -> installation OS -> post-configuration.
"""

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.config import settings
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
)
from src.domain.template_engine import get_template_engine
from src.domain.vm_service import VMService
from src.integrations.hypervisors import HyperVClient

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
    POST_CONFIGURATION = "post_configuration"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"


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

    async def _update_deployment_status(
        self,
        deployment: Deployment,
        status: DeploymentStatus,
        current_step: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Met à jour le statut du déploiement."""
        deployment.status = status
        if current_step:
            deployment.current_step = current_step
        if error_message:
            deployment.error_message = error_message
        if status in (DeploymentStatus.COMPLETED, DeploymentStatus.FAILED):
            deployment.completed_at = datetime.now(timezone.utc)
        
        await self.db.flush()

    async def create_deployment(
        self,
        vm_name: str,
        hypervisor_id: UUID,
        template_id: UUID,
        cpu_count: int = 2,
        ram_gb: int = 4,
        disk_gb: int = 60,
        network_switch: str | None = None,
        ip_config: dict[str, Any] | None = None,
        admin_password: str | None = None,
        hostname: str | None = None,
        domain_join: dict[str, Any] | None = None,
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
            post_install_commands: Commandes post-installation
            
        Returns:
            Déploiement créé
        """
        # Vérifier que l'hyperviseur existe
        hypervisor = await self.vm_service.get_hypervisor(hypervisor_id)
        
        # Vérifier que le template existe
        template = await self.vm_service.get_template(template_id)
        
        # Préparer la configuration
        config = {
            "vm_name": vm_name,
            "hostname": hostname or vm_name,
            "cpu_count": cpu_count,
            "ram_gb": ram_gb,
            "disk_gb": disk_gb,
            "network_switch": network_switch or settings.hyperv_default_switch,
            "admin_password": admin_password or settings.default_admin_password.get_secret_value(),
            "ip_config": ip_config or {},
            "domain_join": domain_join,
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
        
        # Marquer comme en cours (si pas déjà)
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
        Exécute le workflow complet de déploiement via DISM.
        
        Cette méthode utilise DISM pour appliquer directement l'image Windows
        sur le disque, évitant l'installation interactive et le prompt
        "Press any key to boot from CD or DVD".
        
        Temps de déploiement: ~2-3 minutes au lieu de 15-30 minutes.
        """
        config = deployment.config
        
        # 1. Validation
        await self._log_step(deployment, DeploymentStep.VALIDATING, "Validating configuration")
        await self._validate_deployment(deployment)
        
        # 2. Création de la VM (VHDX vide, sans ISO)
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.CREATING_VM
        )
        await self._log_step(deployment, DeploymentStep.CREATING_VM, f"Creating VM: {config['vm_name']}")
        vm = await self._create_vm_for_dism(deployment)
        deployment.vm_id = vm.id
        
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
        
        # 6. Marquer comme terminé (DISM = installation déjà faite)
        await self._update_deployment_status(
            deployment,
            DeploymentStatus.COMPLETED,
            DeploymentStep.COMPLETED,
        )
        await self._log_step(
            deployment,
            DeploymentStep.COMPLETED,
            "Deployment completed. VM is booting to Windows desktop.",
        )
        
        logger.info(
            "deployment_completed_dism",
            deployment_id=str(deployment.id),
            vm_id=str(vm.id),
        )

    async def _validate_deployment(self, deployment: Deployment) -> None:
        """Valide la configuration du déploiement."""
        config = deployment.config
        
        # Vérifier les paramètres obligatoires
        required = ["vm_name", "hostname", "admin_password"]
        for field in required:
            if not config.get(field):
                raise ValidationError(f"Missing required field: {field}")
        
        # Vérifier que la VM n'existe pas déjà
        existing = await self.vm_service.get_vm_by_name(config["vm_name"])
        if existing:
            raise ValidationError(f"VM '{config['vm_name']}' already exists")

    async def _create_vm_for_dism(self, deployment: Deployment) -> VirtualMachine:
        """
        Crée la VM pour le déploiement DISM (sans ISO, VHDX vide).
        
        La VM est créée avec un disque vide qui sera ensuite rempli
        par DISM avec l'image Windows.
        """
        config = deployment.config
        
        # Créer la VM sans ISO et sans template (pour éviter l'ISO)
        # DISM appliquera l'image directement sur le VHDX
        # Note: Frontend envoie memory_mb, on convertit en GB
        memory_mb = config.get("memory_mb", 4096)
        ram_gb = memory_mb // 1024 if memory_mb >= 1024 else config.get("ram_gb", 4)
        
        vm = await self.vm_service.create_vm(
            name=config["vm_name"],
            hypervisor_id=deployment.hypervisor_id,
            cpu_count=config.get("cpu_count", 2),
            ram_gb=ram_gb,
            disk_gb=config.get("disk_size_gb", config.get("disk_gb", 60)),
            network_switch=config.get("network_switch"),
            vhdx_path=config.get("vhdx_path"),
            template_id=None,  # Pas de template = pas d'ISO
        )
        
        # Associer le template à la VM en base de données
        if deployment.os_template_id:
            vm.os_template_id = deployment.os_template_id
            await self.db.flush()
        
        return vm

    async def _deploy_with_dism(self, deployment: Deployment, vm: VirtualMachine) -> None:
        """
        Déploie Windows via DISM sur le VHDX de la VM.
        
        Cette méthode:
        1. Récupère le chemin ISO depuis le template
        2. Génère le fichier unattend.xml
        3. Appelle deploy_with_dism du client Hyper-V
        """
        config = deployment.config
        template_config = config.get("template") or {}
        
        # Récupérer le chemin ISO depuis le template
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
        
        # Générer le contenu unattend.xml
        ip_config = config.get("ip_config") or {}
        domain_join = config.get("domain_join") or {}
        
        unattend_content = self.template_engine.render_windows_unattend(
            hostname=config["hostname"],
            admin_password=config["admin_password"],
            static_ip=ip_config.get("static_ip", False),
            ip_address=ip_config.get("ip_address"),
            gateway=ip_config.get("gateway"),
            dns_server_1=ip_config.get("dns_server_1", "8.8.8.8"),
            dns_server_2=ip_config.get("dns_server_2"),
            join_domain=bool(domain_join),
            domain_name=domain_join.get("domain"),
            domain_user=domain_join.get("user"),
            domain_password=domain_join.get("password"),
            post_install_commands=[
                {"command": cmd, "description": f"Custom command {i+1}"}
                for i, cmd in enumerate(config.get("post_install_commands") or [])
            ],
        )
        
        # Appeler deploy_with_dism
        vm_identifier = vm.hypervisor_vm_id or vm.name
        success = await client.deploy_with_dism(
            vm_id=vm_identifier,
            iso_path=iso_path,
            vhd_path=vhdx_path,
            image_index=2,  # Desktop Experience (pas Core)
            unattend_content=unattend_content,
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
                unattend_content = self.template_engine.render_windows_unattend(
                    hostname=config["hostname"],
                    admin_password=config["admin_password"],
                    static_ip=ip_config.get("static_ip", False),
                    ip_address=ip_config.get("ip_address"),
                    gateway=ip_config.get("gateway"),
                    dns_server_1=ip_config.get("dns_server_1", "8.8.8.8"),
                    dns_server_2=ip_config.get("dns_server_2"),
                    join_domain=bool(domain_join),
                    domain_name=domain_join.get("domain"),
                    domain_user=domain_join.get("user"),
                    domain_password=domain_join.get("password"),
                    post_install_commands=[
                        {"command": cmd, "description": f"Custom command {i+1}"}
                        for i, cmd in enumerate(config.get("post_install_commands") or [])
                    ],
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
                        username=config.get("username", "admin"),
                        static_ip=ip_config.get("static_ip", False),
                        ip_address=ip_config.get("ip_address"),
                        gateway=ip_config.get("gateway"),
                        dns_server_1=ip_config.get("dns_server_1", "8.8.8.8"),
                        post_install_commands=config.get("post_install_commands", []),
                    )
                else:
                    content = self.template_engine.render_debian_preseed(
                        hostname=config["hostname"],
                        username=config.get("username", "admin"),
                        user_password=config["admin_password"],
                        static_ip=ip_config.get("static_ip", False),
                        ip_address=ip_config.get("ip_address"),
                        gateway=ip_config.get("gateway"),
                        post_install_commands=config.get("post_install_commands", []),
                    )
                
                logger.info(
                    "preseed_generated",
                    deployment_id=str(deployment.id),
                    length=len(content),
                )
        finally:
            client.close()

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
        """Liste les déploiements."""
        query = select(Deployment).order_by(Deployment.created_at.desc()).limit(limit)
        
        if status:
            query = query.where(Deployment.status == status)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())

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
