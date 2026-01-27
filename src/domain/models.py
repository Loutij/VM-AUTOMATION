# =============================================================================
# VM Automation - SQLAlchemy Models
# =============================================================================
"""
Modèles de base de données SQLAlchemy.
Définit le schéma de la base de données pour l'application.
"""

import enum
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.common.database import Base


# =============================================================================
# Enums
# =============================================================================


class HypervisorType(str, enum.Enum):
    """Types d'hyperviseurs supportés."""

    HYPERV = "hyperv"
    VMWARE = "vmware"


class OSFamily(str, enum.Enum):
    """Familles d'OS supportées."""

    WINDOWS = "windows"
    LINUX = "linux"
    
    def _generate_next_value_(name, start, count, last_values):
        return name.lower()


# Helper pour SQLAlchemy - utilise les valeurs (minuscules) au lieu des noms
def enum_values(enum_class):
    """Retourne une fonction pour obtenir les valeurs d'un enum."""
    return lambda x: [e.value for e in x]


class Architecture(str, enum.Enum):
    """Architectures processeur supportées."""

    X64 = "x64"
    X86 = "x86"
    ARM64 = "arm64"


class VMStatus(str, enum.Enum):
    """États internes de gestion d'une VM."""

    CREATING = "creating"
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
    DELETING = "deleting"
    DELETED = "deleted"


class VMState(str, enum.Enum):
    """États Hyper-V d'une VM (depuis l'hyperviseur)."""

    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    SUSPENDED = "saved"
    UNKNOWN = "unknown"


class DeploymentStatus(str, enum.Enum):
    """États possibles d'un déploiement."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    CREATING_VM = "creating_vm"
    INSTALLING = "installing_os"
    POST_INSTALL = "post_install"
    INSTALLING_SOFTWARE = "installing_software"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LogLevel(str, enum.Enum):
    """Niveaux de log."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class SoftwareInstallStatus(str, enum.Enum):
    """États d'installation d'un logiciel."""

    PENDING = "pending"
    INSTALLING = "installing"
    INSTALLED = "installed"
    FAILED = "failed"


# =============================================================================
# Mixins
# =============================================================================


class TimestampMixin:
    """Mixin pour ajouter les timestamps created_at et updated_at."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=True,
    )


# =============================================================================
# Models
# =============================================================================


class Hypervisor(Base, TimestampMixin):
    """Modèle pour un hyperviseur."""

    __tablename__ = "hypervisors"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[HypervisorType] = mapped_column(
        Enum(HypervisorType, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=5986, nullable=False)
    use_ssl: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    password_encrypted: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relations
    virtual_machines: Mapped[list["VirtualMachine"]] = relationship(
        back_populates="hypervisor",
        cascade="all, delete-orphan",
    )

    @property
    def password(self) -> str:
        """Retourne le mot de passe (à décrypter si nécessaire)."""
        # TODO: Implémenter le déchiffrement si password_encrypted est chiffré
        return self.password_encrypted

    def __repr__(self) -> str:
        return f"<Hypervisor(id={self.id}, name={self.name}, type={self.type})>"


class OSTemplate(Base, TimestampMixin):
    """Modèle pour un template d'OS."""

    __tablename__ = "os_templates"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    os_family: Mapped[OSFamily] = mapped_column(
        Enum(OSFamily, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    os_type: Mapped[str] = mapped_column(String(50), nullable=False)
    architecture: Mapped[Architecture] = mapped_column(
        Enum(Architecture, values_callable=lambda x: [e.value for e in x]),
        default=Architecture.X64,
        nullable=False
    )
    iso_path: Mapped[str] = mapped_column(String(500), nullable=False)
    unattend_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    min_cpu: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    min_ram_gb: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    min_disk_gb: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relations
    virtual_machines: Mapped[list["VirtualMachine"]] = relationship(
        back_populates="os_template",
    )

    def __repr__(self) -> str:
        return f"<OSTemplate(id={self.id}, name={self.name}, os_family={self.os_family})>"


class VirtualMachine(Base, TimestampMixin):
    """Modèle pour une machine virtuelle."""

    __tablename__ = "virtual_machines"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Foreign keys
    hypervisor_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hypervisors.id"),
        nullable=False,
    )
    os_template_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("os_templates.id"),
        nullable=True,
    )
    
    # Specs
    generation: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    cpu_count: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    ram_gb: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    disk_gb: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    disk_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    # Network
    network_switch: Mapped[str] = mapped_column(String(100), nullable=False)
    vlan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mac_address: Mapped[str | None] = mapped_column(String(17), nullable=True)
    ip_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    
    # Domain
    domain_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    
    # Status
    status: Mapped[VMStatus] = mapped_column(
        Enum(VMStatus, values_callable=lambda x: [e.value for e in x]),
        default=VMStatus.CREATING,
        nullable=False
    )
    state: Mapped[VMState] = mapped_column(
        Enum(VMState, values_callable=lambda x: [e.value for e in x]),
        default=VMState.STOPPED,
        nullable=False,
        comment="État Hyper-V (running, stopped, paused, etc.)"
    )
    hypervisor_vm_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="GUID Hyper-V de la VM"
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True, comment="Adresse IP de la VM"
    )
    
    # Relations
    hypervisor: Mapped["Hypervisor"] = relationship(back_populates="virtual_machines")
    os_template: Mapped["OSTemplate | None"] = relationship(
        back_populates="virtual_machines"
    )
    deployments: Mapped[list["Deployment"]] = relationship(
        back_populates="virtual_machine",
        cascade="all, delete-orphan",
    )
    software_installations: Mapped[list["VMSoftware"]] = relationship(
        back_populates="virtual_machine",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<VirtualMachine(id={self.id}, name={self.name}, status={self.status})>"


class Deployment(Base, TimestampMixin):
    """Modèle pour un déploiement de VM."""

    __tablename__ = "deployments"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    
    # VM info
    vm_name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Foreign keys
    hypervisor_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hypervisors.id"),
        nullable=False,
    )
    os_template_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("os_templates.id"),
        nullable=False,
    )
    vm_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("virtual_machines.id"),
        nullable=True,
        comment="ID de la VM créée (rempli après création)",
    )
    created_by: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="ID de l'utilisateur ayant créé le déploiement",
    )
    
    # Configuration
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # Status
    status: Mapped[DeploymentStatus] = mapped_column(
        Enum(DeploymentStatus, values_callable=lambda x: [e.value for e in x]),
        default=DeploymentStatus.PENDING,
        nullable=False
    )
    current_step: Mapped[str | None] = mapped_column(String(50), nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Timestamps
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # Relations
    hypervisor: Mapped["Hypervisor"] = relationship()
    os_template: Mapped["OSTemplate"] = relationship()
    virtual_machine: Mapped["VirtualMachine | None"] = relationship(
        back_populates="deployments"
    )
    logs: Mapped[list["DeploymentLog"]] = relationship(
        back_populates="deployment",
        cascade="all, delete-orphan",
        order_by="DeploymentLog.created_at",
    )

    def __repr__(self) -> str:
        return f"<Deployment(id={self.id}, status={self.status}, progress={self.progress}%)>"


class DeploymentLog(Base):
    """Modèle pour les logs de déploiement."""

    __tablename__ = "deployment_logs"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    deployment_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deployments.id"),
        nullable=False,
    )
    level: Mapped[LogLevel] = mapped_column(
        Enum(LogLevel, values_callable=lambda x: [e.value for e in x]),
        default=LogLevel.INFO,
        nullable=False
    )
    step: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relations
    deployment: Mapped["Deployment"] = relationship(back_populates="logs")

    def __repr__(self) -> str:
        return f"<DeploymentLog(id={self.id}, level={self.level}, step={self.step})>"


class SoftwareCategory(str, enum.Enum):
    """Catégories de logiciels pour la marketplace."""

    # Rôles Windows Server
    WINDOWS_ROLE = "windows_role"
    # Services d'entreprise (AD, PKI, Federation)
    ENTERPRISE_SERVICES = "enterprise_services"
    # Accès à distance
    REMOTE_ACCESS = "remote_access"
    # Base de données
    DATABASE = "database"
    # Serveurs web
    WEBSERVER = "webserver"
    # Développement
    DEVELOPMENT = "development"
    # Runtimes et langages
    RUNTIME = "runtime"
    # Monitoring
    MONITORING = "monitoring"
    # Sécurité
    SECURITY = "security"
    # Utilitaires
    UTILITIES = "utilities"
    # Navigateurs
    BROWSER = "browser"
    # Containers et virtualisation
    CONTAINERS = "containers"
    # Transfert de fichiers
    FILE_TRANSFER = "file_transfer"
    # Réseau
    NETWORK = "network"
    # Sauvegarde
    BACKUP = "backup"
    # Messagerie et collaboration
    MESSAGING = "messaging"
    # Autres
    OTHER = "other"


class SoftwarePackage(Base, TimestampMixin):
    """
    Modèle pour un package logiciel dans la marketplace.
    
    Représente un logiciel installable avec sa configuration par défaut.
    """

    __tablename__ = "software_packages"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    # Identifiants
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    version: Mapped[str] = mapped_column(String(50), default="latest", nullable=False)
    
    # Description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Catégorie et tags
    category: Mapped[SoftwareCategory] = mapped_column(
        Enum(SoftwareCategory, values_callable=lambda x: [e.value for e in x]),
        default=SoftwareCategory.OTHER,
        nullable=False,
    )
    tags: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    
    # Compatibilité OS
    os_family: Mapped[OSFamily | None] = mapped_column(
        Enum(OSFamily, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
        comment="NULL = compatible tous OS"
    )
    
    # Package manager et commandes
    package_manager: Mapped[str] = mapped_column(
        String(20), default="chocolatey", nullable=False,
        comment="chocolatey, winget, apt, dnf"
    )
    package_id: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="ID du package dans le gestionnaire (ex: 7zip, notepadplusplus)"
    )
    install_command_windows: Mapped[str | None] = mapped_column(Text, nullable=True)
    install_command_linux: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Configuration par défaut
    default_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False,
        comment="Configuration par défaut du logiciel après installation"
    )
    config_schema: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True,
        comment="Schéma JSON des options de configuration disponibles"
    )
    
    # Métadonnées
    icon: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="URL ou nom d'icône"
    )
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    documentation_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Dépendances et conflits
    dependencies: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False,
        comment="Liste des package_id requis"
    )
    conflicts: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False,
        comment="Liste des package_id incompatibles"
    )
    
    # Statut
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_featured: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="Afficher en vedette dans la marketplace"
    )
    install_time_minutes: Mapped[int] = mapped_column(
        Integer, default=5, nullable=False,
        comment="Temps d'installation estimé en minutes"
    )
    
    # Statistiques
    install_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relations
    vm_installations: Mapped[list["VMSoftware"]] = relationship(
        back_populates="software_package",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<SoftwarePackage(id={self.id}, name={self.name}, category={self.category})>"


class VMSoftware(Base):
    """Table d'association VM <-> Software avec statut d'installation."""

    __tablename__ = "vm_software"

    vm_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("virtual_machines.id"),
        primary_key=True,
    )
    software_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("software_packages.id"),
        primary_key=True,
    )
    status: Mapped[SoftwareInstallStatus] = mapped_column(
        Enum(SoftwareInstallStatus, values_callable=lambda x: [e.value for e in x]),
        default=SoftwareInstallStatus.PENDING,
        nullable=False,
    )
    installed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relations
    virtual_machine: Mapped["VirtualMachine"] = relationship(
        back_populates="software_installations"
    )
    software_package: Mapped["SoftwarePackage"] = relationship(
        back_populates="vm_installations"
    )

    def __repr__(self) -> str:
        return f"<VMSoftware(vm_id={self.vm_id}, software_id={self.software_id}, status={self.status})>"
