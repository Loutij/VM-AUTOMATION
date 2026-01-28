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
    WAITING_VM_READY = "waiting_vm_ready"
    POST_CONFIGURATION = "post_configuration"
    INSTALLING_SOFTWARE = "installing_software"
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
        """Met à jour le statut du déploiement, commit et notifie via WebSocket."""
        deployment.status = status
        if current_step:
            deployment.current_step = current_step
        if error_message:
            deployment.error_message = error_message
        if status in (DeploymentStatus.COMPLETED, DeploymentStatus.FAILED):
            deployment.completed_at = datetime.now(timezone.utc)
        
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
                    "status": status.value,
                    "step": current_step or deployment.current_step,
                    "progress": deployment.progress,
                    "error": error_message,
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
        
        # Préparer la configuration
        config = {
            "vm_name": vm_name,
            "hostname": hostname or vm_name,
            "cpu_count": cpu_count,
            "ram_gb": ram_gb,
            "disk_gb": disk_gb,
            "vhdx_path": vhdx_path,  # Emplacement personnalisé du VHDX
            "network_switch": network_switch or settings.hyperv_default_switch,
            "admin_password": admin_password or settings.default_admin_password.get_secret_value(),
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
        
        Workflow complet:
        1. Validation
        2. Création VM (VHDX vide)
        3. Déploiement DISM
        4. Configuration réseau (via unattend)
        5. Démarrage VM
        6. Attente VM prête (heartbeat + PowerShell Direct)
        7. Post-configuration (services, sécurité)
        8. Installation logiciels
        9. Finalisation
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
            error_msg = "VM not accessible via PowerShell Direct after all retries. Post-install configuration failed."
            await self._log_step(
                deployment, DeploymentStep.WAITING_VM_READY,
                error_msg,
                "error"
            )
            # Passer en FAILED au lieu de COMPLETED
            await self._update_deployment_status(
                deployment,
                DeploymentStatus.FAILED,
                DeploymentStep.WAITING_VM_READY,
                error_msg,
            )
            logger.error(
                "deployment_failed_vm_not_ready",
                deployment_id=str(deployment.id),
                vm_name=deployment.vm_name,
            )
            return
        
        await self._log_step(
            deployment, DeploymentStep.WAITING_VM_READY, 
            "VM is ready and accessible via PowerShell Direct"
        )
        
        # 7. Post-configuration (services, sécurité, etc.)
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.POST_CONFIGURATION
        )
        await self._log_step(
            deployment, DeploymentStep.POST_CONFIGURATION, 
            "Configuring services and security settings..."
        )
        await self._execute_post_configuration(deployment, vm)
        
        # 8. Installation des logiciels
        software_profile = config.get("software_profile")
        packages = config.get("packages", [])
        
        if software_profile or packages:
            await self._update_deployment_status(
                deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.INSTALLING_SOFTWARE
            )
            await self._log_step(
                deployment, DeploymentStep.INSTALLING_SOFTWARE, 
                f"Installing software (profile: {software_profile or 'custom'})..."
            )
            await self._install_software(deployment, vm)
        
        # 9. Finalisation
        await self._update_deployment_status(
            deployment, DeploymentStatus.IN_PROGRESS, DeploymentStep.FINALIZING
        )
        await self._log_step(deployment, DeploymentStep.FINALIZING, "Finalizing deployment...")
        await self._finalize_deployment(deployment, vm)
        
        # Terminé !
        await self._update_deployment_status(
            deployment,
            DeploymentStatus.COMPLETED,
            DeploymentStep.COMPLETED,
        )
        await self._log_step(
            deployment,
            DeploymentStep.COMPLETED,
            "Deployment completed successfully. VM is ready for use.",
        )
        
        logger.info(
            "deployment_completed_full",
            deployment_id=str(deployment.id),
            vm_id=str(vm.id),
            software_installed=bool(software_profile or packages),
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

    async def _wait_for_vm_ready(
        self,
        deployment: Deployment,
        vm: VirtualMachine,
        timeout: int = 600,
    ) -> bool:
        """
        Attend que la VM soit prête et accessible via PowerShell Direct.
        
        Le processus en 3 phases :
        1. Attendre le heartbeat (Windows a démarré)
        2. Attendre le fichier flag C:\\VM-Automation\\ready.flag (setup terminé)
        3. Vérifier que PowerShell Direct fonctionne avec les credentials
        
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
            
            vm_identifier = vm.hypervisor_vm_id or vm.name
            credentials = ("Administrateur", admin_password)  # Windows FR
            
            start_time = time.time()
            
            # Phase 1: Attendre le heartbeat (Windows boot) - timeout réduit
            await self._log_step(
                deployment, DeploymentStep.WAITING_VM_READY,
                "Phase 1/3: Waiting for Windows heartbeat...", "info"
            )
            
            heartbeat_timeout = min(timeout // 2, 300)  # Max 5 min pour le heartbeat
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
                "Windows heartbeat OK - VM is running", "info"
            )
            
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
                # Tenter une connexion WinRM directe
                await self._log_step(
                    deployment, DeploymentStep.WAITING_VM_READY,
                    f"Phase 3/4: Testing WinRM direct connection to {vm_ip}...", "info"
                )
                
                try:
                    result = await client.execute_via_winrm_direct(
                        vm_ip,
                        "$env:COMPUTERNAME",
                        credentials,
                        timeout=30,
                    )
                    if result.success:
                        use_winrm_direct = True
                        await self._log_step(
                            deployment, DeploymentStep.WAITING_VM_READY,
                            f"WinRM direct connection OK - using fast direct connection", "info"
                        )
                except Exception as e:
                    logger.debug("deployment_winrm_direct_failed", error=str(e))
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
            
            while (time.time() - start_time) < timeout and not flag_found:
                checks_count += 1
                
                try:
                    # Vérifier si le fichier flag existe
                    if use_winrm_direct and vm_ip:
                        result = await client.execute_via_winrm_direct(
                            vm_ip,
                            'if (Test-Path "C:\\VM-Automation\\ready.flag") { "FLAG_FOUND" } else { "FLAG_NOT_FOUND" }',
                            credentials,
                            timeout=30,
                        )
                    else:
                        result = await client.execute_in_vm(
                            vm_identifier,
                            'if (Test-Path "C:\\VM-Automation\\ready.flag") { "FLAG_FOUND" } else { "FLAG_NOT_FOUND" }',
                            credentials,
                        timeout=30,
                    )
                    
                    if result.success and "FLAG_FOUND" in str(result.output):
                        flag_found = True
                        await self._log_step(
                            deployment, DeploymentStep.WAITING_VM_READY,
                            "VM-Automation setup completed - ready.flag found", "info"
                        )
                        break
                    elif result.success and not fallback_attempted and not dir_checked:
                        # Connexion fonctionne - vérifier si le dossier VM-Automation existe
                        dir_checked = True
                        if use_winrm_direct and vm_ip:
                            dir_result = await client.execute_via_winrm_direct(
                                vm_ip,
                                'if (Test-Path "C:\\VM-Automation") { "DIR_EXISTS" } else { "DIR_MISSING" }',
                                credentials,
                                timeout=30,
                            )
                        else:
                            dir_result = await client.execute_in_vm(
                                vm_identifier,
                                'if (Test-Path "C:\\VM-Automation") { "DIR_EXISTS" } else { "DIR_MISSING" }',
                                credentials,
                                timeout=30,
                            )
                        
                        if dir_result.success and "DIR_MISSING" in str(dir_result.output):
                            # Le dossier n'existe pas - exécuter le fallback IMMÉDIATEMENT
                            fallback_attempted = True
                            method_msg = "via WinRM direct" if use_winrm_direct else "via PowerShell Direct"
                            await self._log_step(
                                deployment, DeploymentStep.WAITING_VM_READY,
                                f"VM-Automation folder missing - executing fallback setup IMMEDIATELY {method_msg}", "warning"
                            )
                            
                            fallback_result = await self._execute_fallback_setup(
                                client, vm_identifier, credentials, admin_password,
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
                    elif result.success and not fallback_attempted and checks_count >= 4:
                        # Après ~40-60s, si le flag n'existe toujours pas, tenter le fallback
                        fallback_attempted = True
                        method_msg = "via WinRM direct" if use_winrm_direct else "via PowerShell Direct"
                        await self._log_step(
                            deployment, DeploymentStep.WAITING_VM_READY,
                            f"Flag not found after waiting - attempting fallback setup {method_msg}...", "warning"
                        )
                        
                        # Tenter d'exécuter le script setup.ps1 manuellement
                        fallback_result = await self._execute_fallback_setup(
                            client, vm_identifier, credentials, admin_password,
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
                        logger.debug(
                            "deployment_waiting_for_flag",
                            deployment_id=str(deployment.id),
                            result=str(result.output)[:100] if result.output else "no output",
                            checks_count=checks_count,
                        )
                        
                except Exception as e:
                    # PowerShell Direct peut échouer si le setup n'est pas encore terminé
                    logger.debug(
                        "deployment_flag_check_error",
                        deployment_id=str(deployment.id),
                        error=str(e),
                    )
                
                await asyncio.sleep(flag_check_interval)
            
            if not flag_found:
                await self._log_step(
                    deployment, DeploymentStep.WAITING_VM_READY,
                    "Timeout waiting for VM-Automation setup - continuing anyway", "warning"
                )
                # On continue quand même car le setup peut avoir fonctionné
            
            # Phase finale: Vérifier que la connexion fonctionne
            connection_method = "WinRM direct" if use_winrm_direct else "PowerShell Direct"
            await self._log_step(
                deployment, DeploymentStep.WAITING_VM_READY,
                f"Final verification: Testing {connection_method} connection...", "info"
            )
            
            # Tester la connexion
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if use_winrm_direct and vm_ip:
                        result = await client.execute_via_winrm_direct(
                            vm_ip,
                            "$env:COMPUTERNAME",
                            credentials,
                            timeout=30,
                        )
                    else:
                        result = await client.execute_in_vm(
                            vm_identifier,
                            "$env:COMPUTERNAME",
                            credentials,
                            timeout=30,
                        )
                    
                    if result.success:
                        hostname = str(result.output).strip() if result.output else "unknown"
                        await self._log_step(
                            deployment, DeploymentStep.WAITING_VM_READY,
                            f"{connection_method} connected - hostname: {hostname}", "info"
                        )
                        return True
                    else:
                        logger.debug(
                            "deployment_connection_failed",
                            deployment_id=str(deployment.id),
                            attempt=attempt + 1,
                            method=connection_method,
                            error=result.error,
                        )
                        
                except Exception as e:
                    logger.debug(
                        "deployment_connection_error",
                        deployment_id=str(deployment.id),
                        attempt=attempt + 1,
                        method=connection_method,
                        error=str(e),
                    )
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(10)
            
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
    # 1. Configurer le mot de passe Administrateur
    net user Administrateur "{admin_password}" /active:yes 2>&1 | Out-Null
    "$(Get-Date) - Administrateur configured" | Out-File $logFile -Append
    
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
        credentials = ("Administrateur", admin_password)  # Windows FR
        
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
                # Activer RDP via registre
                rdp_script = """
                Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -Name "fDenyTSConnections" -Value 0
                Enable-NetFirewallRule -DisplayGroup "Remote Desktop"
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
        credentials = ("Administrateur", admin_password)  # Windows FR
        
        try:
            client = await self.vm_service._get_hypervisor_client(deployment.hypervisor_id)
            software_service = SoftwareInstallService(client)
            
            vm_name = vm.hypervisor_vm_id or vm.name
            
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
