# =============================================================================
# VM Automation - Pydantic Schemas
# =============================================================================
"""
Schémas Pydantic pour la validation des données API.
Séparés des modèles SQLAlchemy pour une meilleure séparation des préoccupations.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Base Schemas
# =============================================================================


class BaseSchema(BaseModel):
    """Schéma de base avec configuration commune."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class TimestampSchema(BaseSchema):
    """Schéma avec timestamps."""

    created_at: datetime
    updated_at: datetime | None = None


# =============================================================================
# Hypervisor Schemas
# =============================================================================


class HypervisorBase(BaseSchema):
    """Champs communs pour Hypervisor."""

    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., pattern="^(hyperv|vmware)$")
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(default=5986, ge=1, le=65535)
    use_ssl: bool = True
    username: str = Field(..., min_length=1, max_length=100)


class HypervisorCreate(HypervisorBase):
    """Schéma pour créer un hyperviseur."""

    password: str = Field(..., min_length=1)


class HypervisorUpdate(BaseSchema):
    """Schéma pour mettre à jour un hyperviseur."""

    name: str | None = Field(None, min_length=1, max_length=100)
    host: str | None = Field(None, min_length=1, max_length=255)
    port: int | None = Field(None, ge=1, le=65535)
    use_ssl: bool | None = None
    username: str | None = Field(None, min_length=1, max_length=100)
    password: str | None = Field(None, min_length=1)
    is_active: bool | None = None


class HypervisorResponse(HypervisorBase, TimestampSchema):
    """Schéma de réponse pour un hyperviseur."""

    id: UUID
    is_active: bool


class HypervisorList(BaseSchema):
    """Liste paginée d'hyperviseurs."""

    items: list[HypervisorResponse]
    total: int
    page: int
    page_size: int


# =============================================================================
# OS Template Schemas
# =============================================================================


class OSTemplateBase(BaseSchema):
    """Champs communs pour OSTemplate."""

    name: str = Field(..., min_length=1, max_length=100)
    os_family: str = Field(..., pattern="^(windows|linux)$")
    os_type: str = Field(..., min_length=1, max_length=50)
    architecture: str = Field(default="x64", pattern="^(x64|x86|arm64)$")
    iso_path: str = Field(..., min_length=1, max_length=500)
    min_cpu: int = Field(default=1, ge=1)
    min_ram_gb: int = Field(default=2, ge=1)
    min_disk_gb: int = Field(default=20, ge=10)


class OSTemplateCreate(OSTemplateBase):
    """Schéma pour créer un template OS."""

    unattend_template: str | None = None


class OSTemplateUpdate(BaseSchema):
    """Schéma pour mettre à jour un template OS."""

    name: str | None = Field(None, min_length=1, max_length=100)
    iso_path: str | None = Field(None, min_length=1, max_length=500)
    min_cpu: int | None = Field(None, ge=1)
    min_ram_gb: int | None = Field(None, ge=1)
    min_disk_gb: int | None = Field(None, ge=10)
    unattend_template: str | None = None
    is_active: bool | None = None


class OSTemplateResponse(OSTemplateBase, TimestampSchema):
    """Schéma de réponse pour un template OS."""

    id: UUID
    is_active: bool


class OSTemplateList(BaseSchema):
    """Liste paginée de templates OS."""

    items: list[OSTemplateResponse]
    total: int
    page: int
    page_size: int


# =============================================================================
# Virtual Machine Schemas
# =============================================================================


class NetworkConfigSchema(BaseSchema):
    """Configuration réseau d'une VM."""

    type: str = Field(default="dhcp", pattern="^(dhcp|static)$")
    ip_address: str | None = None
    subnet_mask: str | None = None
    gateway: str | None = None
    dns_servers: list[str] = Field(default_factory=list)
    vlan_id: int | None = Field(None, ge=1, le=4094)


class DomainConfigSchema(BaseSchema):
    """Configuration domaine AD d'une VM."""

    join_domain: bool = False
    domain_name: str | None = None
    ou_path: str | None = None


class VMBase(BaseSchema):
    """Champs communs pour VirtualMachine."""

    name: str = Field(..., min_length=1, max_length=100)
    generation: int = Field(default=2, ge=1, le=2)
    cpu_count: int = Field(default=2, ge=1, le=64)
    ram_gb: int = Field(default=4, ge=1, le=1024)
    disk_gb: int = Field(default=60, ge=10, le=65536)
    network_switch: str = Field(..., min_length=1, max_length=100)


class VMCreate(VMBase):
    """Schéma pour créer une VM."""

    hypervisor_id: UUID
    os_template_id: UUID
    network_config: NetworkConfigSchema = Field(default_factory=NetworkConfigSchema)
    domain_config: DomainConfigSchema = Field(default_factory=DomainConfigSchema)
    software_packages: list[UUID] = Field(default_factory=list)


class VMUpdate(BaseSchema):
    """Schéma pour mettre à jour une VM."""

    name: str | None = Field(None, min_length=1, max_length=100)
    cpu_count: int | None = Field(None, ge=1, le=64)
    ram_gb: int | None = Field(None, ge=1, le=1024)


class VMResponse(VMBase, TimestampSchema):
    """Schéma de réponse pour une VM."""

    id: UUID
    hypervisor_id: UUID
    os_template_id: UUID | None
    status: str
    hyperv_id: str | None
    disk_path: str | None
    mac_address: str | None
    ip_config: dict[str, Any] | None
    domain_config: dict[str, Any] | None


class VMList(BaseSchema):
    """Liste paginée de VMs."""

    items: list[VMResponse]
    total: int
    page: int
    page_size: int


# =============================================================================
# Deployment Schemas
# =============================================================================


class DeploymentCreate(BaseSchema):
    """Schéma pour créer un déploiement."""

    vm_name: str = Field(..., min_length=1, max_length=100)
    hypervisor_id: UUID
    os_template_id: UUID
    cpu_count: int = Field(default=2, ge=1, le=64)
    ram_gb: int = Field(default=4, ge=1, le=1024)
    disk_gb: int = Field(default=60, ge=10, le=65536)
    network_switch: str = Field(..., min_length=1, max_length=100)
    network_config: NetworkConfigSchema = Field(default_factory=NetworkConfigSchema)
    domain_config: DomainConfigSchema = Field(default_factory=DomainConfigSchema)
    software_packages: list[UUID] = Field(default_factory=list)


class DeploymentStatusSchema(BaseSchema):
    """Statut d'un déploiement."""

    status: str
    current_step: str | None
    progress: int = Field(ge=0, le=100)
    error_message: str | None = None


class DeploymentLogSchema(BaseSchema):
    """Log d'un déploiement."""

    id: UUID
    level: str
    step: str
    message: str
    details: dict[str, Any] | None
    created_at: datetime


class DeploymentResponse(BaseSchema, TimestampSchema):
    """Schéma de réponse pour un déploiement."""

    id: UUID
    vm_id: UUID
    status: str
    current_step: str | None
    progress: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_by: UUID | None


class DeploymentList(BaseSchema):
    """Liste paginée de déploiements."""

    items: list[DeploymentResponse]
    total: int
    page: int
    page_size: int


# =============================================================================
# Software Package Schemas
# =============================================================================


class SoftwarePackageBase(BaseSchema):
    """Champs communs pour SoftwarePackage."""

    name: str = Field(..., min_length=1, max_length=100)
    version: str = Field(default="latest", max_length=50)
    os_family: str | None = Field(None, pattern="^(windows|linux)$")
    category: str = Field(default="other", max_length=50)


class SoftwarePackageCreate(SoftwarePackageBase):
    """Schéma pour créer un package logiciel."""

    install_command_windows: str | None = None
    install_command_linux: str | None = None


class SoftwarePackageUpdate(BaseSchema):
    """Schéma pour mettre à jour un package logiciel."""

    name: str | None = Field(None, min_length=1, max_length=100)
    version: str | None = Field(None, max_length=50)
    install_command_windows: str | None = None
    install_command_linux: str | None = None
    category: str | None = Field(None, max_length=50)
    is_active: bool | None = None


class SoftwarePackageResponse(SoftwarePackageBase, TimestampSchema):
    """Schéma de réponse pour un package logiciel."""

    id: UUID
    install_command_windows: str | None
    install_command_linux: str | None
    is_active: bool


class SoftwarePackageList(BaseSchema):
    """Liste paginée de packages logiciels."""

    items: list[SoftwarePackageResponse]
    total: int
    page: int
    page_size: int
