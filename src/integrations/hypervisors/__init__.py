# =============================================================================
# VM Automation - Hypervisor Integrations
# =============================================================================
"""
Exports des clients hyperviseurs.
"""

from src.integrations.hypervisors.base import (
    BaseHypervisor,
    DiskInfo,
    VirtualSwitch,
    VMInfo,
    VMSpecs,
)
from src.integrations.hypervisors.hyperv_client import HyperVClient

__all__ = [
    "BaseHypervisor",
    "DiskInfo",
    "HyperVClient",
    "VirtualSwitch",
    "VMInfo",
    "VMSpecs",
]
