# =============================================================================
# VM Automation - Types Package
# =============================================================================
"""
Package contenant les types et schémas Pydantic.
"""

from src.types.schemas import (
    # Base
    BaseSchema,
    TimestampSchema,
    # Hypervisor
    HypervisorBase,
    HypervisorCreate,
    HypervisorList,
    HypervisorResponse,
    HypervisorUpdate,
    # OS Template
    OSTemplateBase,
    OSTemplateCreate,
    OSTemplateList,
    OSTemplateResponse,
    OSTemplateUpdate,
    # Virtual Machine
    DomainConfigSchema,
    NetworkConfigSchema,
    VMBase,
    VMCreate,
    VMList,
    VMResponse,
    VMUpdate,
    # Deployment
    DeploymentCreate,
    DeploymentList,
    DeploymentLogSchema,
    DeploymentResponse,
    DeploymentStatusSchema,
    # Software Package
    SoftwarePackageBase,
    SoftwarePackageCreate,
    SoftwarePackageList,
    SoftwarePackageResponse,
    SoftwarePackageUpdate,
)

__all__ = [
    # Base
    "BaseSchema",
    "TimestampSchema",
    # Hypervisor
    "HypervisorBase",
    "HypervisorCreate",
    "HypervisorUpdate",
    "HypervisorResponse",
    "HypervisorList",
    # OS Template
    "OSTemplateBase",
    "OSTemplateCreate",
    "OSTemplateUpdate",
    "OSTemplateResponse",
    "OSTemplateList",
    # Virtual Machine
    "NetworkConfigSchema",
    "DomainConfigSchema",
    "VMBase",
    "VMCreate",
    "VMUpdate",
    "VMResponse",
    "VMList",
    # Deployment
    "DeploymentCreate",
    "DeploymentStatusSchema",
    "DeploymentLogSchema",
    "DeploymentResponse",
    "DeploymentList",
    # Software Package
    "SoftwarePackageBase",
    "SoftwarePackageCreate",
    "SoftwarePackageUpdate",
    "SoftwarePackageResponse",
    "SoftwarePackageList",
]
