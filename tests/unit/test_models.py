# =============================================================================
# VM Automation - Domain Model Tests
# =============================================================================
"""
Tests for src/domain/models.py:
  - Enum values and membership
  - Model instantiation (plain Python, no DB round-trip needed for unit tests)
"""

import pytest

from src.domain.models import (
    Architecture,
    DeploymentStatus,
    HypervisorType,
    LogLevel,
    OSFamily,
    SoftwareCategory,
    SoftwareInstallStatus,
    VMState,
    VMStatus,
)


# =============================================================================
# Enum tests
# =============================================================================


class TestVMStatusEnum:
    def test_values(self):
        expected = {
            "creating", "created", "starting", "running",
            "stopping", "stopped", "error", "deleting", "deleted",
        }
        assert {e.value for e in VMStatus} == expected

    def test_string_access(self):
        assert VMStatus("running") is VMStatus.RUNNING

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            VMStatus("nonexistent")


class TestVMStateEnum:
    def test_values(self):
        expected = {"running", "stopped", "paused", "saved", "unknown"}
        assert {e.value for e in VMState} == expected


class TestDeploymentStatusEnum:
    def test_values(self):
        expected = {
            "pending", "in_progress", "creating_vm", "installing_os",
            "post_install", "installing_software", "completed", "failed", "cancelled",
        }
        assert {e.value for e in DeploymentStatus} == expected

    def test_is_str_subclass(self):
        assert isinstance(DeploymentStatus.PENDING, str)
        assert DeploymentStatus.PENDING == "pending"


class TestOSFamilyEnum:
    def test_values(self):
        assert OSFamily.WINDOWS.value == "windows"
        assert OSFamily.LINUX.value == "linux"

    def test_membership(self):
        assert "windows" in [e.value for e in OSFamily]


class TestArchitectureEnum:
    def test_values(self):
        assert {e.value for e in Architecture} == {"x64", "x86", "arm64"}


class TestHypervisorTypeEnum:
    def test_values(self):
        assert HypervisorType.HYPERV.value == "hyperv"
        assert HypervisorType.VMWARE.value == "vmware"


class TestLogLevelEnum:
    def test_values(self):
        assert {e.value for e in LogLevel} == {"debug", "info", "warning", "error"}


class TestSoftwareInstallStatusEnum:
    def test_values(self):
        assert {e.value for e in SoftwareInstallStatus} == {
            "pending", "installing", "installed", "failed",
        }


class TestSoftwareCategoryEnum:
    def test_has_expected_categories(self):
        names = {e.name for e in SoftwareCategory}
        assert "DATABASE" in names
        assert "WEBSERVER" in names
        assert "SECURITY" in names
        assert "CONTAINERS" in names
