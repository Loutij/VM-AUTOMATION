# =============================================================================
# VM Automation - Exception Tests
# =============================================================================
"""
Tests for src/common/exceptions.py:
  - Exception hierarchy / isinstance checks
  - to_dict() serialization
  - Error code mapping
"""

import pytest

from src.common.exceptions import (
    AlreadyExistsError,
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    DatabaseError,
    DeploymentError,
    DeploymentStepError,
    DeploymentTimeoutError,
    HypervisorConnectionError,
    HypervisorError,
    InvalidTokenError,
    NotFoundError,
    PowerShellError,
    PowerShellTimeoutError,
    ResourceBusyError,
    TokenExpiredError,
    ValidationError,
    VMAutomationError,
    VMCreationError,
    VMNotFoundError,
    VMOperationError,
)


# =============================================================================
# Base exception
# =============================================================================


class TestVMAutomationError:
    def test_default_code(self):
        exc = VMAutomationError("something broke")
        assert exc.code == "VMAUTOMATION_ERROR"
        assert exc.message == "something broke"
        assert exc.details == {}

    def test_custom_code_and_details(self):
        exc = VMAutomationError("msg", code="CUSTOM", details={"key": "val"})
        assert exc.code == "CUSTOM"
        assert exc.details == {"key": "val"}

    def test_to_dict(self):
        exc = VMAutomationError("test", code="CODE", details={"x": 1})
        d = exc.to_dict()
        assert d == {"error": "CODE", "message": "test", "details": {"x": 1}}

    def test_is_exception(self):
        exc = VMAutomationError("x")
        assert isinstance(exc, Exception)
        assert str(exc) == "x"


# =============================================================================
# Hierarchy checks
# =============================================================================


class TestExceptionHierarchy:
    def test_auth_error_is_base(self):
        assert issubclass(AuthenticationError, VMAutomationError)

    def test_token_expired_is_auth(self):
        assert issubclass(TokenExpiredError, AuthenticationError)

    def test_invalid_token_is_auth(self):
        assert issubclass(InvalidTokenError, AuthenticationError)

    def test_authorization_is_base(self):
        assert issubclass(AuthorizationError, VMAutomationError)

    def test_hypervisor_error_is_base(self):
        assert issubclass(HypervisorError, VMAutomationError)

    def test_vm_creation_is_hypervisor(self):
        assert issubclass(VMCreationError, HypervisorError)

    def test_vm_not_found_is_hypervisor(self):
        assert issubclass(VMNotFoundError, HypervisorError)

    def test_vm_operation_is_hypervisor(self):
        assert issubclass(VMOperationError, HypervisorError)

    def test_powershell_error_is_base(self):
        assert issubclass(PowerShellError, VMAutomationError)

    def test_powershell_timeout_is_powershell(self):
        assert issubclass(PowerShellTimeoutError, PowerShellError)

    def test_deployment_error_is_base(self):
        assert issubclass(DeploymentError, VMAutomationError)

    def test_deployment_step_is_deployment(self):
        assert issubclass(DeploymentStepError, DeploymentError)

    def test_deployment_timeout_is_deployment(self):
        assert issubclass(DeploymentTimeoutError, DeploymentError)

    def test_config_error_is_base(self):
        assert issubclass(ConfigurationError, VMAutomationError)

    def test_database_error_is_base(self):
        assert issubclass(DatabaseError, VMAutomationError)

    def test_not_found_is_base(self):
        assert issubclass(NotFoundError, VMAutomationError)

    def test_already_exists_is_base(self):
        assert issubclass(AlreadyExistsError, VMAutomationError)

    def test_validation_is_base(self):
        assert issubclass(ValidationError, VMAutomationError)

    def test_resource_busy_is_base(self):
        assert issubclass(ResourceBusyError, VMAutomationError)


# =============================================================================
# Error codes
# =============================================================================


class TestErrorCodes:
    def test_config_error_code(self):
        assert ConfigurationError("x").code == "CONFIG_ERROR"

    def test_auth_error_code(self):
        assert AuthenticationError().code == "AUTH_ERROR"

    def test_authz_error_code(self):
        assert AuthorizationError().code == "AUTHZ_ERROR"

    def test_token_expired_code(self):
        assert TokenExpiredError().code == "TOKEN_EXPIRED"

    def test_invalid_token_code(self):
        assert InvalidTokenError().code == "INVALID_TOKEN"

    def test_db_error_code(self):
        assert DatabaseError("x").code == "DB_ERROR"

    def test_not_found_code(self):
        assert NotFoundError("VM").code == "NOT_FOUND"

    def test_already_exists_code(self):
        assert AlreadyExistsError("VM", "test-vm").code == "ALREADY_EXISTS"

    def test_hypervisor_error_code(self):
        assert HypervisorError("x").code == "HYPERVISOR_ERROR"

    def test_hypervisor_connection_error_code(self):
        assert HypervisorConnectionError("host1").code == "HYPERVISOR_CONNECTION_ERROR"

    def test_vm_creation_error_code(self):
        assert VMCreationError("vm1", "disk full").code == "VM_CREATION_ERROR"

    def test_vm_not_found_code(self):
        assert VMNotFoundError("vm1").code == "VM_NOT_FOUND"

    def test_vm_operation_error_code(self):
        assert VMOperationError("vm1", "start", "timeout").code == "VM_OPERATION_ERROR"

    def test_powershell_error_code(self):
        assert PowerShellError("x").code == "POWERSHELL_ERROR"

    def test_powershell_timeout_code(self):
        assert PowerShellTimeoutError(30).code == "POWERSHELL_TIMEOUT"

    def test_deployment_error_code(self):
        assert DeploymentError("x").code == "DEPLOYMENT_ERROR"

    def test_deployment_step_error_code(self):
        assert DeploymentStepError("d1", "install", "fail").code == "DEPLOYMENT_STEP_ERROR"

    def test_deployment_timeout_code(self):
        assert DeploymentTimeoutError("d1", "install", 300).code == "DEPLOYMENT_TIMEOUT"

    def test_validation_error_code(self):
        assert ValidationError("x").code == "VALIDATION_ERROR"

    def test_resource_busy_code(self):
        assert ResourceBusyError("VM", "vm1").code == "RESOURCE_BUSY"


# =============================================================================
# to_dict() serialization
# =============================================================================


class TestToDict:
    def test_not_found_to_dict(self):
        exc = NotFoundError("VM", "abc-123")
        d = exc.to_dict()
        assert d["error"] == "NOT_FOUND"
        assert "abc-123" in d["message"]
        assert d["details"]["resource_type"] == "VM"

    def test_already_exists_to_dict(self):
        exc = AlreadyExistsError("Template", "ubuntu-22")
        d = exc.to_dict()
        assert d["error"] == "ALREADY_EXISTS"
        assert d["details"]["identifier"] == "ubuntu-22"

    def test_powershell_error_to_dict_truncates(self):
        long_cmd = "x" * 1000
        long_stderr = "e" * 2000
        exc = PowerShellError("fail", command=long_cmd, exit_code=1, stderr=long_stderr)
        d = exc.to_dict()
        assert len(d["details"]["command"]) <= 500
        assert len(d["details"]["stderr"]) <= 1000
        assert d["details"]["exit_code"] == 1

    def test_hypervisor_connection_to_dict(self):
        exc = HypervisorConnectionError("10.0.0.1", reason="timeout")
        d = exc.to_dict()
        assert d["details"]["host"] == "10.0.0.1"

    def test_vm_operation_to_dict(self):
        exc = VMOperationError("my-vm", "stop", "already stopped")
        d = exc.to_dict()
        assert d["details"]["vm_name"] == "my-vm"
        assert d["details"]["operation"] == "stop"

    def test_resource_busy_to_dict(self):
        exc = ResourceBusyError("Hypervisor", "hv-1")
        d = exc.to_dict()
        assert d["details"]["resource_type"] == "Hypervisor"
        assert d["details"]["resource_id"] == "hv-1"

    def test_validation_error_with_fields(self):
        exc = ValidationError("bad input", fields={"name": "required"})
        d = exc.to_dict()
        assert d["details"]["fields"]["name"] == "required"

    def test_deployment_step_to_dict(self):
        exc = DeploymentStepError("dep-1", "create_vm", "disk full")
        d = exc.to_dict()
        assert d["details"]["deployment_id"] == "dep-1"
        assert d["details"]["step"] == "create_vm"
