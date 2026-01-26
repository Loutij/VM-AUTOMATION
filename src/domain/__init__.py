# =============================================================================
# VM Automation - Domain Layer
# =============================================================================
"""
Couche métier de l'application.
Contient les modèles, services et logique business.
"""

from src.domain.models import (
    Base,
    Deployment,
    DeploymentLog,
    DeploymentStatus,
    Hypervisor,
    HypervisorType,
    OSFamily,
    OSTemplate,
    SoftwarePackage,
    VirtualMachine,
    VMSoftware,
    VMState,
)
from src.domain.template_engine import TemplateEngine, get_template_engine
from src.domain.vm_service import VMService
from src.domain.deployment_service import DeploymentService

__all__ = [
    # Models
    "Base",
    "Deployment",
    "DeploymentLog",
    "DeploymentStatus",
    "Hypervisor",
    "HypervisorType",
    "OSFamily",
    "OSTemplate",
    "SoftwarePackage",
    "VirtualMachine",
    "VMSoftware",
    "VMState",
    # Services
    "VMService",
    "DeploymentService",
    "TemplateEngine",
    "get_template_engine",
]
