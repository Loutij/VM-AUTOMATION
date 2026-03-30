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

try:
    from src.integrations.hypervisors.esxi_client import ESXiClient
    ESXI_AVAILABLE = True
except ImportError:
    ESXiClient = None
    ESXI_AVAILABLE = False

__all__ = [
    "BaseHypervisor",
    "DiskInfo",
    "ESXiClient",
    "ESXI_AVAILABLE",
    "HyperVClient",
    "VirtualSwitch",
    "VMInfo",
    "VMSpecs",
]
