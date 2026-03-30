# =============================================================================
# VM Automation - Virtual Machines Router
# =============================================================================
"""
Endpoints CRUD pour la gestion des machines virtuelles.
"""

import json
from datetime import datetime, timezone
from typing import Annotated, Any
import asyncio
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.api.dependencies import CurrentUser, DbSession, Pagination, RequireAdmin
from src.common.config import settings
from src.common.logging import get_logger
from src.domain.models import OSFamily, VMState
from src.domain.vm_service import VMService
from src.domain.vnc_service import VNCService
from src.integrations.hypervisors import HyperVClient

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================


class VMBase(BaseModel):
    """Schéma de base pour une VM."""

    name: str = Field(..., min_length=1, max_length=100, description="Nom de la VM")
    cpu_count: int = Field(default=2, ge=1, le=64, description="Nombre de CPUs")
    ram_gb: int = Field(default=4, ge=1, le=512, description="RAM en GB")
    disk_gb: int = Field(default=60, ge=10, le=2048, description="Disque en GB")


class VMCreate(VMBase):
    """Schéma pour créer une VM."""

    hypervisor_id: UUID = Field(..., description="ID de l'hyperviseur cible")
    template_id: UUID | None = Field(None, description="ID du template OS")
    network_switch: str | None = Field(None, description="Switch réseau")


class VMUpdate(BaseModel):
    """Schéma pour mettre à jour une VM."""

    name: str | None = Field(None, min_length=1, max_length=100)
    cpu_count: int | None = Field(None, ge=1, le=64)
    ram_gb: int | None = Field(None, ge=1, le=512)
    notes: str | None = None


class VMResponse(VMBase):
    """Schéma de réponse pour une VM."""

    id: UUID
    hypervisor_id: UUID
    hypervisor_vm_id: str | None = None
    state: str
    ip_address: str | None = None
    network_switch: str | None = None
    vlan_id: int | None = None
    os_template_id: UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class VMList(BaseModel):
    """Schéma pour la liste paginée de VMs."""

    items: list[VMResponse]
    total: int
    page: int
    page_size: int


class VMAction(BaseModel):
    """Résultat d'une action sur une VM."""

    success: bool
    message: str
    vm_id: UUID
    state: str


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=VMList,
    summary="Lister les VMs",
    description="Retourne la liste paginée des machines virtuelles.",
)
async def list_vms(
    db: DbSession,
    pagination: Pagination,
    current_user: RequireAdmin,
    hypervisor_id: Annotated[UUID | None, Query(description="Filtrer par hyperviseur")] = None,
    state: Annotated[str | None, Query(description="Filtrer par état")] = None,
) -> VMList:
    """Liste toutes les VMs avec filtres optionnels."""
    logger.info(
        "listing_vms",
        page=pagination.page,
        page_size=pagination.page_size,
        hypervisor_id=str(hypervisor_id) if hypervisor_id else None,
        state=state,
    )
    
    service = VMService(db)
    
    # Mapper l'état si fourni
    vm_state = None
    if state:
        try:
            vm_state = VMState(state)
        except ValueError:
            pass
    
    vms = await service.list_vms(hypervisor_id=hypervisor_id, state=vm_state)
    
    # Pagination simple
    total = len(vms)
    start = (pagination.page - 1) * pagination.page_size
    end = start + pagination.page_size
    items = vms[start:end]
    
    return VMList(
        items=[VMResponse(
            id=vm.id,
            name=vm.name,
            hypervisor_id=vm.hypervisor_id,
            hypervisor_vm_id=vm.hypervisor_vm_id,
            cpu_count=vm.cpu_count,
            ram_gb=vm.ram_gb,
            disk_gb=vm.disk_gb,
            state=vm.state.value,
            ip_address=vm.ip_address,
            network_switch=vm.network_switch,
            vlan_id=vm.vlan_id,
            os_template_id=vm.os_template_id,
            created_at=vm.created_at,
            updated_at=vm.updated_at,
        ) for vm in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post(
    "",
    response_model=VMResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer une VM",
    description="Crée une nouvelle machine virtuelle sur l'hyperviseur.",
)
async def create_vm(
    db: DbSession,
    vm_data: VMCreate,
    current_user: RequireAdmin,
) -> VMResponse:
    """Crée une nouvelle VM."""
    logger.info(
        "creating_vm",
        name=vm_data.name,
        hypervisor_id=str(vm_data.hypervisor_id),
    )
    
    service = VMService(db)
    
    vm = await service.create_vm(
        name=vm_data.name,
        hypervisor_id=vm_data.hypervisor_id,
        cpu_count=vm_data.cpu_count,
        ram_gb=vm_data.ram_gb,
        disk_gb=vm_data.disk_gb,
        network_switch=vm_data.network_switch,
        template_id=vm_data.template_id,
    )
    
    await db.commit()
    
    return VMResponse(
        id=vm.id,
        name=vm.name,
        hypervisor_id=vm.hypervisor_id,
        hypervisor_vm_id=vm.hypervisor_vm_id,
        cpu_count=vm.cpu_count,
        ram_gb=vm.ram_gb,
        disk_gb=vm.disk_gb,
        state=vm.state.value,
        ip_address=vm.ip_address,
        network_switch=vm.network_switch,
        vlan_id=vm.vlan_id,
        os_template_id=vm.os_template_id,
        created_at=vm.created_at,
        updated_at=vm.updated_at,
    )


@router.get(
    "/{vm_id}",
    response_model=VMResponse,
    summary="Obtenir une VM",
    description="Retourne les détails d'une VM spécifique.",
)
async def get_vm(
    db: DbSession,
    vm_id: UUID,
    current_user: RequireAdmin,
) -> VMResponse:
    """Récupère une VM par son ID."""
    logger.info("getting_vm", vm_id=str(vm_id))
    
    service = VMService(db)
    vm = await service.get_vm(vm_id)
    
    return VMResponse(
        id=vm.id,
        name=vm.name,
        hypervisor_id=vm.hypervisor_id,
        hypervisor_vm_id=vm.hypervisor_vm_id,
        cpu_count=vm.cpu_count,
        ram_gb=vm.ram_gb,
        disk_gb=vm.disk_gb,
        state=vm.state.value,
        ip_address=vm.ip_address,
        network_switch=vm.network_switch,
        vlan_id=vm.vlan_id,
        os_template_id=vm.os_template_id,
        created_at=vm.created_at,
        updated_at=vm.updated_at,
    )


@router.patch(
    "/{vm_id}",
    response_model=VMResponse,
    summary="Mettre à jour une VM",
    description="Met à jour les informations d'une VM.",
)
async def update_vm(
    db: DbSession,
    vm_id: UUID,
    vm_data: VMUpdate,
    current_user: RequireAdmin,
) -> VMResponse:
    """Met à jour une VM existante."""
    logger.info(
        "updating_vm",
        vm_id=str(vm_id),
        fields=vm_data.model_dump(exclude_unset=True),
    )
    
    service = VMService(db)
    vm = await service.get_vm(vm_id)
    
    # Appliquer les mises à jour
    update_data = vm_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(vm, field, value)
    
    await db.commit()
    await db.refresh(vm)
    
    return VMResponse(
        id=vm.id,
        name=vm.name,
        hypervisor_id=vm.hypervisor_id,
        hypervisor_vm_id=vm.hypervisor_vm_id,
        cpu_count=vm.cpu_count,
        ram_gb=vm.ram_gb,
        disk_gb=vm.disk_gb,
        state=vm.state.value,
        ip_address=vm.ip_address,
        network_switch=vm.network_switch,
        vlan_id=vm.vlan_id,
        os_template_id=vm.os_template_id,
        created_at=vm.created_at,
        updated_at=vm.updated_at,
    )


@router.delete(
    "/{vm_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer une VM",
    description="Supprime une VM.",
)
async def delete_vm(
    db: DbSession,
    vm_id: UUID,
    current_user: RequireAdmin,
    delete_disks: Annotated[bool, Query(description="Supprimer aussi les disques")] = False,
    force: Annotated[bool, Query(description="Forcer la suppression même si l'hyperviseur échoue")] = False,
) -> None:
    """
    Supprime une VM.
    
    Si la VM est en état 'unknown' ou si force=True, la suppression en base
    sera effectuée même si la suppression sur l'hyperviseur échoue.
    """
    logger.info("deleting_vm", vm_id=str(vm_id), delete_disks=delete_disks, force=force)
    
    service = VMService(db)
    await service.delete_vm(vm_id, delete_disks=delete_disks, force=force)
    await db.commit()


# =============================================================================
# Actions
# =============================================================================


@router.post(
    "/{vm_id}/start",
    response_model=VMAction,
    summary="Démarrer une VM",
    description="Démarre une VM arrêtée.",
)
async def start_vm(
    db: DbSession,
    vm_id: UUID,
    current_user: RequireAdmin,
) -> VMAction:
    """Démarre une VM."""
    logger.info("starting_vm", vm_id=str(vm_id))
    
    service = VMService(db)
    vm = await service.start_vm(vm_id)
    await db.commit()
    
    return VMAction(
        success=True,
        message="VM started successfully",
        vm_id=vm.id,
        state=vm.state.value,
    )


@router.post(
    "/{vm_id}/stop",
    response_model=VMAction,
    summary="Arrêter une VM",
    description="Arrête une VM en cours d'exécution.",
)
async def stop_vm(
    db: DbSession,
    vm_id: UUID,
    current_user: RequireAdmin,
    force: Annotated[bool, Query(description="Forcer l'arrêt")] = False,
) -> VMAction:
    """Arrête une VM."""
    logger.info("stopping_vm", vm_id=str(vm_id), force=force)
    
    service = VMService(db)
    vm = await service.stop_vm(vm_id, force=force)
    await db.commit()
    
    return VMAction(
        success=True,
        message="VM stopped successfully",
        vm_id=vm.id,
        state=vm.state.value,
    )


@router.post(
    "/{vm_id}/restart",
    response_model=VMAction,
    summary="Redémarrer une VM",
    description="Redémarre une VM.",
)
async def restart_vm(
    db: DbSession,
    vm_id: UUID,
    current_user: RequireAdmin,
    force: Annotated[bool, Query(description="Forcer le redémarrage")] = False,
) -> VMAction:
    """Redémarre une VM (asynchrone - retourne immédiatement)."""
    logger.info("restarting_vm", vm_id=str(vm_id), force=force)
    
    # Vérifier que la VM existe avant de lancer le restart en background
    service = VMService(db)
    vm = await service.get_vm(vm_id)
    if not vm:
        raise HTTPException(status_code=404, detail="VM non trouvée")
    
    async def _do_restart(vid, do_force):
        from src.common.database import db_session
        try:
            async with db_session() as session:
                bg_service = VMService(session)
                await bg_service.restart_vm(vid, force=do_force)
                await session.commit()
                logger.info("vm_restart_completed", vm_id=str(vid))
        except Exception as e:
            logger.error("vm_restart_failed", vm_id=str(vid), error=str(e))
    
    asyncio.create_task(_do_restart(vm_id, force))
    
    return VMAction(
        success=True,
        message="VM restart initiated",
        vm_id=vm.id,
        state=vm.state.value,
    )


@router.post(
    "/{vm_id}/sync",
    response_model=VMResponse,
    summary="Synchroniser l'état",
    description="Synchronise l'état de la VM avec l'hyperviseur.",
)
async def sync_vm_state(
    db: DbSession,
    vm_id: UUID,
    current_user: RequireAdmin,
) -> VMResponse:
    """Synchronise l'état de la VM depuis l'hyperviseur."""
    logger.info("syncing_vm_state", vm_id=str(vm_id))
    
    service = VMService(db)
    vm = await service.sync_vm_state(vm_id)
    await db.commit()
    
    return VMResponse(
        id=vm.id,
        name=vm.name,
        hypervisor_id=vm.hypervisor_id,
        hypervisor_vm_id=vm.hypervisor_vm_id,
        cpu_count=vm.cpu_count,
        ram_gb=vm.ram_gb,
        disk_gb=vm.disk_gb,
        state=vm.state.value,
        ip_address=vm.ip_address,
        network_switch=vm.network_switch,
        vlan_id=vm.vlan_id,
        os_template_id=vm.os_template_id,
        created_at=vm.created_at,
        updated_at=vm.updated_at,
    )


@router.get(
    "/{vm_id}/rdp",
    summary="Télécharger fichier RDP",
    description="Génère et télécharge un fichier .rdp pour se connecter à la VM.",
    responses={
        200: {
            "content": {"application/x-rdp": {}},
            "description": "Fichier RDP téléchargeable",
        }
    },
)
async def download_rdp(
    db: DbSession,
    vm_id: UUID,
    current_user: RequireAdmin,
    username: Annotated[str | None, Query(description="Nom d'utilisateur par défaut")] = None,
) -> Response:
    """Génère un fichier RDP pour la VM."""
    logger.info("generating_rdp", vm_id=str(vm_id))
    
    service = VMService(db)
    vm = await service.get_vm(vm_id)
    
    # Utiliser l'IP si disponible, sinon le nom de la VM
    address = vm.ip_address or vm.name
    
    # Username par défaut si non fourni
    default_username = username or ".\\Administrateur"
    
    # Contenu du fichier RDP avec credentials pré-remplis
    rdp_content = f"""full address:s:{address}
username:s:{default_username}
prompt for credentials:i:1
administrative session:i:1
screen mode id:i:2
use multimon:i:0
desktopwidth:i:1920
desktopheight:i:1080
session bpp:i:32
compression:i:1
keyboardhook:i:2
audiocapturemode:i:0
videoplaybackmode:i:1
connection type:i:7
networkautodetect:i:1
bandwidthautodetect:i:1
displayconnectionbar:i:1
enableworkspacereconnect:i:0
disable wallpaper:i:0
allow font smoothing:i:1
allow desktop composition:i:1
disable full window drag:i:0
disable menu anims:i:0
disable themes:i:0
disable cursor setting:i:0
bitmapcachepersistenable:i:1
autoreconnection enabled:i:1
authentication level:i:2
"""
    
    return Response(
        content=rdp_content,
        media_type="application/x-rdp",
        headers={
            "Content-Disposition": f'attachment; filename="{vm.name}.rdp"',
        },
    )


@router.get(
    "/{vm_id}/details",
    summary="Détails complets de la VM",
    description="Récupère les détails complets d'une VM incluant ressources, disques, réseau, services d'intégration.",
)
async def get_vm_details(
    db: DbSession,
    vm_id: UUID,
    current_user: RequireAdmin,
) -> dict[str, Any]:
    """Récupère les détails complets d'une VM depuis Hyper-V."""
    logger.info("getting_vm_details", vm_id=str(vm_id))
    
    service = VMService(db)
    vm = await service.get_vm(vm_id)
    
    # Récupérer l'hyperviseur
    hypervisor = await service.get_hypervisor(vm.hypervisor_id)
    
    # Créer le client Hyper-V
    client = HyperVClient(
        host=hypervisor.host,
        username=hypervisor.username,
        password=hypervisor.password,
        use_ssl=hypervisor.use_ssl,
    )
    
    try:
        # Récupérer les détails via le nom ou l'ID Hyper-V
        vm_identifier = vm.hypervisor_vm_id or vm.name
        details = await client.get_vm_full_details(vm_identifier)
        
        # Ajouter l'ID de notre base de données
        details["db_id"] = str(vm.id)
        
        return details
    except Exception as e:
        logger.error("vm_details_failed", vm_id=str(vm_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Impossible de récupérer les détails de la VM: {str(e)}"
        )
    finally:
        client.close()


class PostInstallRequest(BaseModel):
    """Configuration pour le post-install manuel."""
    
    admin_username: str = Field(default="otoroot", description="Nom d'utilisateur admin")
    admin_password: str = Field(default="tooroto", description="Mot de passe administrateur de la VM")
    # Services
    enable_rdp: bool = Field(default=True, description="Activer Remote Desktop")
    enable_winrm: bool = Field(default=True, description="Configurer WinRM")
    enable_ssh: bool = Field(default=False, description="Installer OpenSSH Server")
    # Logiciels
    software_profile: str | None = Field(None, description="Profil logiciel (minimal, tools, development, webserver, database, monitoring)")
    packages: list[str] | None = Field(None, description="Packages Chocolatey à installer")
    package_configs: dict[str, dict[str, Any]] | None = Field(None, description="Configurations des packages (ex: {'zabbix-agent2': {'server': '172.16.0.126', 'hostname': 'SRV-01'}})")
    # Windows Update
    install_updates: bool = Field(default=False, description="Installer les mises à jour Windows")


class PostInstallResponse(BaseModel):
    """Résultat du post-install."""
    
    success: bool
    vm_id: str
    steps_completed: list[str]
    errors: list[str]
    software_installed: list[str]
    reboot_required: bool


@router.post(
    "/{vm_id}/post-install",
    response_model=PostInstallResponse,
    summary="Exécuter le post-install",
    description="Exécute les configurations post-installation sur une VM existante (services, logiciels, mises à jour).",
)
async def execute_post_install(
    db: DbSession,
    vm_id: UUID,
    config: PostInstallRequest,
    current_user: RequireAdmin,
) -> PostInstallResponse:
    """
    Exécute le post-install sur une VM existante.
    
    Permet de :
    - Configurer les services (RDP, WinRM, SSH)
    - Installer des logiciels via Chocolatey
    - Installer les mises à jour Windows
    """
    logger.info(
        "executing_post_install",
        vm_id=str(vm_id),
        services={"rdp": config.enable_rdp, "winrm": config.enable_winrm, "ssh": config.enable_ssh},
        software_profile=config.software_profile,
    )
    
    service = VMService(db)
    vm = await service.get_vm(vm_id)
    
    # Vérifier que la VM est running
    if vm.state.value != "running":
        raise HTTPException(
            status_code=400,
            detail="La VM doit être en cours d'exécution pour exécuter le post-install"
        )
    
    # Récupérer l'hyperviseur
    hypervisor = await service.get_hypervisor(vm.hypervisor_id)
    
    # Créer le client Hyper-V
    client = HyperVClient(
        host=hypervisor.host,
        username=hypervisor.username,
        password=hypervisor.password,
        use_ssl=hypervisor.use_ssl,
    )
    
    steps_completed: list[str] = []
    errors: list[str] = []
    software_installed: list[str] = []
    reboot_required = False
    
    # Utiliser .\ pour spécifier un compte local (pas domaine)
    local_username = f".\\{config.admin_username}" if not config.admin_username.startswith(".\\") else config.admin_username
    credentials = (local_username, config.admin_password)
    # IMPORTANT: -VMName utilise le NOM de la VM, pas son ID Hyper-V
    vm_name = vm.name
    
    try:
        # Vérifier que la VM est accessible via PowerShell Direct
        logger.info("post_install_checking_vm_ready", vm_name=vm_name)
        is_ready = await client.wait_for_vm_ready(vm_name, credentials, timeout=60, check_interval=10)
        
        if not is_ready:
            raise HTTPException(
                status_code=400,
                detail="La VM n'est pas accessible via PowerShell Direct. Vérifiez le mot de passe."
            )
        
        steps_completed.append("VM accessible")
        
        # Importer les services
        from src.domain.post_install_service import PostInstallService
        from src.domain.software_install_service import (
            SoftwareInstallService,
            SoftwarePackage,
            PackageManager,
            SOFTWARE_PROFILES,
        )
        
        post_install_service = PostInstallService(client)
        software_service = SoftwareInstallService(client)
        
        # 1. Configurer SSH si demandé
        if config.enable_ssh:
            try:
                result = await post_install_service.install_ssh_server(vm_name, credentials)
                if result.success:
                    steps_completed.append("SSH Server installed")
                else:
                    errors.append(f"SSH: {result.error}")
            except Exception as e:
                errors.append(f"SSH: {str(e)}")
        
        # 2. Configurer WinRM si demandé
        if config.enable_winrm:
            try:
                result = await post_install_service.configure_service(
                    vm_name, credentials, "WinRM", "Automatic", True
                )
                if result.success:
                    steps_completed.append("WinRM configured")
                else:
                    errors.append(f"WinRM: {result.error}")
            except Exception as e:
                errors.append(f"WinRM: {str(e)}")
        
        # 3. Configurer RDP si demandé
        if config.enable_rdp:
            try:
                rdp_script = """
                Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -Name "fDenyTSConnections" -Value 0 -ErrorAction SilentlyContinue
                Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp' -Name "UserAuthentication" -Value 0 -ErrorAction SilentlyContinue
                Enable-NetFirewallRule -DisplayGroup "Remote Desktop" -ErrorAction SilentlyContinue
                Enable-NetFirewallRule -DisplayGroup "Bureau à distance" -ErrorAction SilentlyContinue
                """
                await client.execute_in_vm(vm_name, rdp_script, credentials)
                steps_completed.append("RDP enabled")
            except Exception as e:
                errors.append(f"RDP: {str(e)}")
        
        # 4. Installer les logiciels
        packages_to_install: list[SoftwarePackage] = []
        
        # Packages du profil
        if config.software_profile and config.software_profile in SOFTWARE_PROFILES:
            packages_to_install.extend(SOFTWARE_PROFILES[config.software_profile])
        
        # Packages personnalisés
        if config.packages:
            for pkg_name in config.packages:
                if not any(p.name == pkg_name for p in packages_to_install):
                    packages_to_install.append(
                        SoftwarePackage(name=pkg_name, package_manager=PackageManager.CHOCOLATEY)
                    )
        
        if packages_to_install:
            try:
                result = await software_service.install_packages(
                    vm_name, credentials, packages_to_install, continue_on_error=True
                )
                
                for pkg_result in result.results:
                    if pkg_result.status.value == "installed":
                        software_installed.append(f"{pkg_result.package_name} v{pkg_result.version_installed or 'latest'}")
                    elif pkg_result.status.value == "skipped":
                        software_installed.append(f"{pkg_result.package_name} (already installed)")
                    elif pkg_result.status.value == "failed":
                        errors.append(f"{pkg_result.package_name}: {pkg_result.error}")
                
                if result.installed > 0:
                    steps_completed.append(f"Installed {result.installed} packages")
                
                reboot_required = result.reboot_required
                
            except Exception as e:
                errors.append(f"Software installation: {str(e)}")
        
        # 4b. Configurer les packages avec leurs paramètres
        if config.package_configs:
            from src.domain.software_catalog import get_software_by_name
            
            for pkg_name, pkg_config in config.package_configs.items():
                software_def = get_software_by_name(pkg_name)
                if software_def and software_def.get("post_install_script"):
                    script = software_def["post_install_script"]
                    # Remplacer les placeholders par les valeurs configurées
                    for key, value in pkg_config.items():
                        script = script.replace(f"{{{key}}}", str(value) if value else "")
                    
                    try:
                        logger.info("post_install_configuring_package", vm_name=vm_name, package=pkg_name)
                        result_script = await client.execute_in_vm(vm_name, script, credentials, timeout=120)
                        if result_script.success:
                            steps_completed.append(f"Configured {pkg_name}")
                        else:
                            errors.append(f"{pkg_name} config: {result_script.error}")
                    except Exception as cfg_e:
                        errors.append(f"{pkg_name} config: {str(cfg_e)}")
        
        # 5. Windows Update
        if config.install_updates:
            try:
                result = await post_install_service.install_windows_updates(
                    vm_name, credentials, auto_reboot=False
                )
                if result.success:
                    steps_completed.append(f"Windows Update: {result.updates_installed} installed")
                    if result.reboot_required:
                        reboot_required = True
                else:
                    errors.append(f"Windows Update: {result.error}")
            except Exception as e:
                errors.append(f"Windows Update: {str(e)}")
        
        return PostInstallResponse(
            success=len(errors) == 0,
            vm_id=str(vm.id),
            steps_completed=steps_completed,
            errors=errors,
            software_installed=software_installed,
            reboot_required=reboot_required,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("post_install_failed", vm_id=str(vm_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors du post-install: {str(e)}"
        )
    finally:
        client.close()


class ExecuteScriptRequest(BaseModel):
    """Requête pour exécuter un script sur une VM."""
    admin_username: str = Field(default="otoroot", description="Nom utilisateur admin")
    admin_password: str = Field(..., description="Mot de passe admin")
    script: str = Field(..., description="Script PowerShell à exécuter")
    timeout: int = Field(default=120, ge=10, le=3600, description="Timeout en secondes")


class ExecuteScriptResponse(BaseModel):
    """Réponse d'exécution de script."""
    success: bool
    output: str | None = None
    error: str | None = None


@router.post(
    "/{vm_id}/execute",
    response_model=ExecuteScriptResponse,
    summary="Exécuter un script sur la VM",
    description="Exécute un script PowerShell sur la VM via PowerShell Direct.",
)
async def execute_script_on_vm(
    db: DbSession,
    vm_id: UUID,
    request: ExecuteScriptRequest,
    current_user: RequireAdmin,
) -> ExecuteScriptResponse:
    """Exécute un script PowerShell sur une VM."""
    logger.info("execute_script_on_vm", vm_id=str(vm_id), script_length=len(request.script))
    
    service = VMService(db)
    vm = await service.get_vm(vm_id)
    
    if not vm:
        raise HTTPException(status_code=404, detail="VM non trouvée")
    
    if not vm.hypervisor_id:
        raise HTTPException(status_code=400, detail="VM sans hyperviseur associé")
    
    hypervisor = await service.get_hypervisor(vm.hypervisor_id)
    if not hypervisor:
        raise HTTPException(status_code=404, detail="Hyperviseur non trouvé")
    
    client = HyperVClient(
        host=hypervisor.host,
        username=hypervisor.username,
        password=hypervisor.password,
        use_ssl=hypervisor.use_ssl,
    )
    
    try:
        local_username = f".\\{request.admin_username}" if not request.admin_username.startswith(".\\") else request.admin_username
        credentials = (local_username, request.admin_password)
        vm_name = vm.name
        
        result = await client.execute_in_vm(vm_name, request.script, credentials, timeout=request.timeout)
        
        output_str = None
        if result.output:
            raw = result.output
            # Parse PowerShell object lists to plain text
            if isinstance(raw, list):
                lines = []
                for item in raw:
                    if isinstance(item, dict) and "value" in item:
                        lines.append(str(item["value"]))
                    elif isinstance(item, dict):
                        lines.append(str(item))
                    else:
                        lines.append(str(item))
                output_str = "\n".join(lines)
            elif isinstance(raw, dict) and "value" in raw:
                output_str = str(raw["value"])
            else:
                output_str = str(raw)
        
        return ExecuteScriptResponse(
            success=result.success,
            output=output_str,
            error=result.error,
        )
    except Exception as e:
        logger.error("execute_script_failed", vm_id=str(vm_id), error=str(e))
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")
    finally:
        client.close()


@router.get(
    "/{vm_id}/screenshot",
    summary="Capture d'écran de la VM",
    description="Capture et retourne un screenshot de l'écran actuel de la VM.",
)
async def get_vm_screenshot(
    db: DbSession,
    vm_id: UUID,
    current_user: RequireAdmin,
    width: Annotated[int, Query(ge=320, le=1920, description="Largeur de l'image")] = 800,
    height: Annotated[int, Query(ge=240, le=1080, description="Hauteur de l'image")] = 600,
) -> dict[str, Any]:
    """Capture un screenshot de la VM depuis Hyper-V."""
    logger.info("capturing_vm_screenshot", vm_id=str(vm_id), width=width, height=height)
    
    service = VMService(db)
    vm = await service.get_vm(vm_id)
    
    # Vérifier que la VM est running
    if vm.state.value != "running":
        raise HTTPException(
            status_code=400,
            detail="La VM doit être en cours d'exécution pour capturer un screenshot"
        )
    
    # Récupérer l'hyperviseur
    hypervisor = await service.get_hypervisor(vm.hypervisor_id)
    
    # Créer le client Hyper-V
    client = HyperVClient(
        host=hypervisor.host,
        username=hypervisor.username,
        password=hypervisor.password,
        use_ssl=hypervisor.use_ssl,
    )
    
    try:
        vm_identifier = vm.hypervisor_vm_id or vm.name
        screenshot_b64 = await client.get_vm_screenshot(vm_identifier, width, height)
        
        if not screenshot_b64:
            logger.error("vm_screenshot_empty", vm_id=str(vm_id), vm_identifier=vm_identifier)
            raise HTTPException(
                status_code=500,
                detail="Impossible de capturer le screenshot"
            )
        
        return {
            "vm_id": str(vm.id),
            "vm_name": vm.name,
            "width": width,
            "height": height,
            "image": f"data:image/png;base64,{screenshot_b64}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("vm_screenshot_failed", vm_id=str(vm_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la capture: {str(e)}"
        )
    finally:
        client.close()


# =============================================================================
# Software Inventory
# =============================================================================


@router.get(
    "/{vm_id}/software-inventory",
    summary="Inventaire logiciel de la VM",
    description="Récupère la liste des logiciels installés sur la VM via PowerShell Direct.",
)
async def get_software_inventory(
    db: DbSession,
    vm_id: UUID,
    current_user: CurrentUser,
    username: str | None = Query(None, description="Username VM (optionnel, sinon auto-détecté)"),
    password: str | None = Query(None, description="Password VM (optionnel, sinon auto-détecté)"),
) -> dict[str, Any]:
    """
    Récupère l'inventaire des logiciels installés sur une VM.

    - Windows : packages Chocolatey + programmes installés (registre)
    - Linux : packages dpkg ou rpm
    """
    logger.info("getting_software_inventory", vm_id=str(vm_id))

    service = VMService(db)
    vm = await service.get_vm(vm_id)

    # La VM doit être running
    if vm.state.value != "running":
        raise HTTPException(
            status_code=400,
            detail="La VM doit être en cours d'exécution pour récupérer l'inventaire logiciel",
        )

    # Récupérer l'hyperviseur et créer le client
    hypervisor = await service.get_hypervisor(vm.hypervisor_id)
    client = HyperVClient(
        host=hypervisor.host,
        username=hypervisor.username,
        password=hypervisor.password,
        use_ssl=hypervisor.use_ssl,
    )

    # Déterminer le type d'OS
    os_type = "windows"  # default
    if vm.os_template_id:
        try:
            template = await service.get_template(vm.os_template_id)
            if template.os_family == OSFamily.LINUX:
                os_type = "linux"
        except Exception:
            pass
    # Heuristique par nom si pas de template
    if not vm.os_template_id:
        name_lower = vm.name.lower()
        if any(kw in name_lower for kw in ("ubuntu", "debian", "rocky", "rhel", "centos", "linux", "fedora", "alma")):
            os_type = "linux"

    # Construire la liste de credentials à essayer
    creds_to_try: list[tuple[str, str]] = []

    # 1. Credentials fournis explicitement
    if username and password:
        u = f".\\{username}" if not username.startswith(".\\") else username
        creds_to_try.append((u, password))

    # 2. Credentials du dernier déploiement
    if vm.deployments:
        latest_deploy = sorted(vm.deployments, key=lambda d: d.created_at, reverse=True)[0]
        deploy_config = latest_deploy.config or {}
        dep_user = deploy_config.get("admin_username", "otoroot")
        dep_pass = deploy_config.get("admin_password", "tooroto")
        dep_u = f".\\{dep_user}" if not dep_user.startswith(".\\") else dep_user
        creds_to_try.append((dep_u, dep_pass))

    # 3. Fallbacks classiques
    default_pass = settings.default_admin_password.get_secret_value()
    for u in ["otoroot", "Administrateur", "Administrator", "admin"]:
        creds_to_try.append((f".\\{u}", default_pass))

    # Dédupliquer en gardant l'ordre
    seen: set[tuple[str, str]] = set()
    unique_creds: list[tuple[str, str]] = []
    for c in creds_to_try:
        if c not in seen:
            seen.add(c)
            unique_creds.append(c)

    vm_name = vm.name

    # Tester les credentials avec un script simple
    test_script = "$env:COMPUTERNAME"
    working_creds: tuple[str, str] | None = None

    for cred in unique_creds:
        try:
            test_result = await client.execute_in_vm(vm_name, test_script, cred, timeout=15)
            if test_result.success:
                working_creds = cred
                logger.info("inventory_credentials_ok", vm=vm_name, user=cred[0])
                break
        except Exception:
            continue

    if not working_creds:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Impossible de se connecter à la VM '{vm_name}'. "
                f"Comptes testés : {', '.join(c[0] for c in unique_creds)}. "
                "Spécifiez username et password en paramètres."
            ),
        )

    credentials = working_creds

    try:
        if os_type == "windows":
            # Fonction helper pour parser la sortie de execute_in_vm
            def _parse_vm_output(result_obj) -> Any:
                """Extrait les données de la réponse PowerShell Direct."""
                if not result_obj.success:
                    logger.warning("inventory_script_failed", error=result_obj.error)
                    return None
                raw = result_obj.output
                if raw is None:
                    return None
                # execute_in_vm retourne un dict avec {value: "JSON string", PSComputerName, ...}
                # ou directement une string JSON, ou une liste
                if isinstance(raw, dict) and "value" in raw:
                    raw = raw["value"]
                if isinstance(raw, str):
                    try:
                        return json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        return raw
                if isinstance(raw, list):
                    # Liste d'objets avec "value" imbriqués
                    parsed = []
                    for item in raw:
                        if isinstance(item, dict) and "value" in item:
                            v = item["value"]
                            if isinstance(v, str):
                                try:
                                    parsed.append(json.loads(v))
                                except Exception:
                                    parsed.append(v)
                            else:
                                parsed.append(v)
                        else:
                            parsed.append(item)
                    return parsed
                return raw

            def _ensure_list(v: Any) -> list:
                if v is None:
                    return []
                if isinstance(v, dict):
                    return [v]
                if isinstance(v, list):
                    return v
                return []

            # Scripts courts — chaque <800 chars pour rester sous la limite WinRM
            # Script 1: System + Programs
            s1 = (
                "$o=Get-CimInstance Win32_OperatingSystem -EA SilentlyContinue;"
                "$s=@{h=$env:COMPUTERNAME;n=if($o){$o.Caption}else{'?'};"
                "v=if($o){$o.Version}else{''};b=if($o){$o.BuildNumber}else{''};"
                "u=if($o){[math]::Round(((Get-Date)-$o.LastBootUpTime).TotalHours,1)}else{0}};"
                "$p=@(Get-ItemProperty 'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
                "'HKLM:\\Software\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'"
                " -EA SilentlyContinue|?{$_.DisplayName}|Select DisplayName,DisplayVersion,Publisher);"
                "@{system=$s;programs=$p}|ConvertTo-Json -Depth 3 -Compress"
            )
            r1 = await client.execute_in_vm(vm_name, s1, credentials, timeout=30)
            d1 = _parse_vm_output(r1) or {}
            if isinstance(d1, str):
                try:
                    d1 = json.loads(d1)
                except Exception:
                    d1 = {}

            # Script 2: Choco + Services + Updates + Features
            s2 = (
                "$c=@();$cp=\"$env:ProgramData\\chocolatey\\bin\\choco.exe\";"
                "if(Test-Path $cp){$c=@(& $cp list --limit-output 2>$null|%{"
                "$x=$_ -split '\\|';if($x.Count -ge 2){@{Name=$x[0];Version=$x[1]}}}|?{$_})};"
                "$sv=@(Get-Service|?{$_.Status -eq 'Running'}|Select Name,DisplayName|Select -First 30);"
                "try{$u=@(Get-HotFix -EA Stop|Select -First 15 HotFixID,Description)}catch{$u=@()};"
                "try{$f=@(Get-WindowsFeature -EA Stop|? Installed|Select Name,DisplayName)}catch{"
                "try{$f=@(Get-WindowsOptionalFeature -Online -EA Stop|?{$_.State -eq 'Enabled'}|"
                "Select FeatureName)}catch{$f=@()}};"
                "@{chocolatey=$c;services=$sv;updates=$u;features=$f}|ConvertTo-Json -Depth 3 -Compress"
            )
            r2 = await client.execute_in_vm(vm_name, s2, credentials, timeout=90)
            d2 = _parse_vm_output(r2) or {}
            if isinstance(d2, str):
                try:
                    d2 = json.loads(d2)
                except Exception:
                    d2 = {}

            # Assembler les résultats
            raw_sys = d1.get("system", {})
            system_info = {
                "hostname": raw_sys.get("h", ""),
                "os_name": raw_sys.get("n", ""),
                "os_version": raw_sys.get("v", ""),
                "os_build": raw_sys.get("b", ""),
                "uptime_hours": raw_sys.get("u", 0),
            }
            installed_programs = _ensure_list(d1.get("programs"))
            choco_packages = _ensure_list(d2.get("chocolatey"))
            services = _ensure_list(d2.get("services"))
            updates = _ensure_list(d2.get("updates"))
            features = _ensure_list(d2.get("features"))

            total = len(choco_packages) + len(installed_programs)

            return {
                "vm_id": str(vm.id),
                "vm_name": vm.name,
                "os_type": os_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "system_info": system_info,
                "chocolatey_packages": choco_packages,
                "installed_programs": installed_programs,
                "windows_features": features,
                "running_services": services,
                "recent_updates": updates,
                "total_packages": total,
            }

        else:
            # Linux — script complet via PowerShell Direct (exécute bash dans la VM)
            linux_script = r"""
$result = @{}

# 1. Packages système (dpkg ou rpm)
$pkgOutput = Invoke-Expression 'bash -c "dpkg-query -W -f ''${Package}\t${Version}\tinstalled\n'' 2>/dev/null || rpm -qa --queryformat ''%{NAME}\t%{VERSION}-%{RELEASE}\tinstalled\n'' 2>/dev/null"' 2>$null
$result.packages = @($pkgOutput | ForEach-Object {
    $p = $_ -split "`t"
    if ($p.Count -ge 2) { @{name=$p[0];version=$p[1];status='installed'} }
})

# 2. Snap packages
$snapOutput = Invoke-Expression 'bash -c "snap list 2>/dev/null | tail -n +2"' 2>$null
$result.snap = @($snapOutput | ForEach-Object {
    $p = $_ -split '\s+'
    if ($p.Count -ge 2) { @{name=$p[0];version=$p[1];source='snap'} }
})

# 3. Flatpak packages
$flatpakOutput = Invoke-Expression 'bash -c "flatpak list --columns=application,version 2>/dev/null | tail -n +1"' 2>$null
$result.flatpak = @($flatpakOutput | ForEach-Object {
    $p = $_ -split '\s+'
    if ($p.Count -ge 1) { @{name=$p[0];version=if($p.Count -ge 2){$p[1]}else{''};source='flatpak'} }
})

# 4. Services actifs
$svcOutput = Invoke-Expression 'bash -c "systemctl list-units --type=service --state=running --no-pager --no-legend 2>/dev/null | head -50"' 2>$null
$result.services = @($svcOutput | ForEach-Object {
    $p = $_ -split '\s+'
    if ($p.Count -ge 1) { @{name=$p[0] -replace '\.service$','';status='running'} }
})

# 5. Infos système
$hostname = Invoke-Expression 'bash -c "hostname"' 2>$null
$osRelease = Invoke-Expression 'bash -c "cat /etc/os-release 2>/dev/null | grep -E \"^(PRETTY_NAME|VERSION_ID)=\" | head -2"' 2>$null
$uptime = Invoke-Expression 'bash -c "uptime -p 2>/dev/null || uptime"' 2>$null
$kernel = Invoke-Expression 'bash -c "uname -r"' 2>$null
$result.system = @{
    hostname = ($hostname | Out-String).Trim()
    os_info = ($osRelease | Out-String).Trim()
    kernel = ($kernel | Out-String).Trim()
    uptime = ($uptime | Out-String).Trim()
}

$result | ConvertTo-Json -Depth 4 -Compress
"""

            result = await client.execute_in_vm(vm_name, linux_script, credentials, timeout=120)

            inventory: dict[str, Any] = {}
            if result.success and result.output:
                raw = result.output
                if isinstance(raw, dict) and "value" in raw:
                    raw = raw["value"]
                if isinstance(raw, str):
                    try:
                        inventory = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        pass
                elif isinstance(raw, dict):
                    inventory = raw

            packages = inventory.get("packages", [])
            snap_packages = inventory.get("snap", [])
            flatpak_packages = inventory.get("flatpak", [])
            services = inventory.get("services", [])
            system_info = inventory.get("system", {})

            # Normaliser
            if isinstance(packages, dict):
                packages = [packages]
            if isinstance(snap_packages, dict):
                snap_packages = [snap_packages]
            if isinstance(flatpak_packages, dict):
                flatpak_packages = [flatpak_packages]
            if isinstance(services, dict):
                services = [services]

            total = len(packages) + len(snap_packages) + len(flatpak_packages)

            return {
                "vm_id": str(vm.id),
                "vm_name": vm.name,
                "os_type": os_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "system_info": system_info,
                "packages": packages,
                "snap_packages": snap_packages,
                "flatpak_packages": flatpak_packages,
                "running_services": services,
                "total_packages": total,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("software_inventory_failed", vm_id=str(vm_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la récupération de l'inventaire logiciel: {str(e)}",
        )
    finally:
        client.close()


# =============================================================================
# VNC
# =============================================================================


class VNCInstallRequest(BaseModel):
    """Configuration pour l'installation du serveur VNC."""

    username: str = Field(default="otoroot", description="Utilisateur SSH/VNC")
    password: str = Field(default="tooroto", description="Mot de passe SSH/VNC")
    port: int = Field(default=5900, ge=5900, le=5999, description="Port VNC")
    display: int = Field(default=1, ge=1, le=99, description="Numéro de display VNC")


class VNCInstallResponse(BaseModel):
    """Résultat de l'installation VNC."""

    success: bool
    step: str | None = None
    vnc_port: int | None = None
    vnc_display: int | None = None
    protocol: str | None = None
    vm_ip: str | None = None
    port: int | None = None
    error: str | None = None


class VNCStatusResponse(BaseModel):
    """Statut du serveur VNC sur une VM."""

    reachable: bool
    is_vnc: bool | None = None
    server_version: str | None = None
    vm_ip: str | None = None
    port: int | None = None
    error: str | None = None


@router.post(
    "/{vm_id}/vnc/install",
    response_model=VNCInstallResponse,
    summary="Installer le serveur VNC",
    description="Installe et configure un serveur VNC (TigerVNC/x11vnc) sur une VM Linux, ou active RDP sur Windows.",
)
async def install_vnc(
    db: DbSession,
    vm_id: UUID,
    config: VNCInstallRequest,
    current_user: RequireAdmin,
) -> VNCInstallResponse:
    """
    Installe un serveur VNC dans la VM.

    - Linux : installe TigerVNC ou x11vnc avec service systemd
    - Windows : active le bureau a distance (RDP)
    """
    logger.info(
        "installing_vnc",
        vm_id=str(vm_id),
        port=config.port,
        display=config.display,
    )

    service = VNCService(db)

    try:
        result = await service.install_vnc(
            vm_id=vm_id,
            username=config.username,
            password=config.password,
            port=config.port,
            display=config.display,
        )
        return VNCInstallResponse(**result)
    except Exception as e:
        logger.error("vnc_install_failed", vm_id=str(vm_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de l'installation VNC: {str(e)}",
        )


@router.get(
    "/{vm_id}/vnc/status",
    response_model=VNCStatusResponse,
    summary="Statut du serveur VNC",
    description="Verifie si le serveur VNC est joignable sur la VM.",
)
async def get_vnc_status(
    db: DbSession,
    vm_id: UUID,
    current_user: RequireAdmin,
    port: Annotated[int, Query(ge=5900, le=5999, description="Port VNC")] = 5900,
) -> VNCStatusResponse:
    """Verifie la connectivite VNC sur la VM."""
    logger.info("checking_vnc_status", vm_id=str(vm_id), port=port)

    service = VNCService(db)

    try:
        result = await service.check_vnc_status(vm_id=vm_id, port=port)
        return VNCStatusResponse(**result)
    except Exception as e:
        logger.error("vnc_status_check_failed", vm_id=str(vm_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la verification VNC: {str(e)}",
        )
