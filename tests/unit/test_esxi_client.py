# =============================================================================
# VM Automation - ESXi/vSphere Client Tests
# =============================================================================
"""
Tests unitaires pour le client ESXi/vSphere.

Tous les appels pyvmomi sont mockés — aucune connexion ESXi réelle requise.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Import tests
# =============================================================================


class TestESXiImport:
    """Vérifie que le module s'importe correctement."""

    def test_import_esxi_available_flag(self):
        """Le flag ESXI_AVAILABLE doit être exporté."""
        from src.integrations.hypervisors import ESXI_AVAILABLE

        assert isinstance(ESXI_AVAILABLE, bool)

    def test_import_esxi_client_class(self):
        """ESXiClient doit être exporté (classe ou None si pyvmomi absent)."""
        from src.integrations.hypervisors import ESXiClient

        # ESXiClient est soit la classe, soit None
        assert ESXiClient is None or callable(ESXiClient)


# =============================================================================
# Mock helpers
# =============================================================================


def _build_pyvmomi_mocks():
    """Construit les mocks nécessaires pour pyvmomi dans sys.modules."""
    mock_vim = MagicMock()

    # Power states
    mock_vim.VirtualMachinePowerState.poweredOn = "poweredOn"
    mock_vim.VirtualMachinePowerState.poweredOff = "poweredOff"
    mock_vim.VirtualMachinePowerState.suspended = "suspended"

    # Types
    mock_vim.VirtualMachine = MagicMock
    mock_vim.HostSystem = MagicMock
    mock_vim.DistributedVirtualSwitch = MagicMock

    return {
        "pyVim": MagicMock(),
        "pyVim.connect": MagicMock(),
        "pyVmomi": MagicMock(),
        "pyVmomi.vim": mock_vim,
        "pyVmomi.vmodl": MagicMock(),
    }


@pytest.fixture()
def mock_pyvmomi():
    """Injecte des mocks pyvmomi dans sys.modules pour la durée du test."""
    mocks = _build_pyvmomi_mocks()
    with patch.dict(sys.modules, mocks):
        yield mocks


@pytest.fixture()
def esxi_client(mock_pyvmomi):
    """Crée un client ESXi avec connexion mockée."""
    # Force reimport with mocked pyvmomi
    from src.integrations.hypervisors.esxi_client import ESXiClient

    client = ESXiClient(
        host="10.0.0.1",
        username="root",
        password="testpass",
        port=443,
        use_ssl=True,
        verify_ssl=False,
        datacenter="DC1",
        cluster="Cluster1",
        default_datastore="datastore1",
    )

    # Mock internal connection objects
    client._si = MagicMock()
    client._content = MagicMock()
    client._content.about.fullName = "VMware ESXi 8.0.0 build-12345"

    return client


# =============================================================================
# Connection tests
# =============================================================================


class TestESXiConnection:
    """Tests de gestion de connexion."""

    @pytest.mark.asyncio
    async def test_test_connection_success(self, esxi_client):
        """test_connection retourne True quand le serveur répond."""
        result = await esxi_client.test_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_cleanup_disconnects(self, esxi_client):
        """cleanup() appelle Disconnect et remet _si à None."""
        await esxi_client.cleanup()
        assert esxi_client._si is None
        assert esxi_client._content is None

    @pytest.mark.asyncio
    async def test_cleanup_idempotent(self, esxi_client):
        """cleanup() peut être appelé plusieurs fois sans erreur."""
        esxi_client._si = None
        esxi_client._content = None
        # Should not raise
        await esxi_client.cleanup()

    def test_client_attributes(self, esxi_client):
        """Les attributs du client sont correctement initialisés."""
        assert esxi_client.host == "10.0.0.1"
        assert esxi_client.username == "root"
        assert esxi_client.port == 443
        assert esxi_client.datacenter == "DC1"
        assert esxi_client.cluster == "Cluster1"
        assert esxi_client.default_datastore == "datastore1"


# =============================================================================
# VM listing tests
# =============================================================================


class TestESXiListVMs:
    """Tests du listing des VMs."""

    @pytest.mark.asyncio
    async def test_list_vms_empty(self, esxi_client):
        """list_vms retourne une liste vide quand il n'y a aucune VM."""
        container_mock = MagicMock()
        container_mock.view = []
        container_mock.Destroy = MagicMock()
        esxi_client._content.viewManager.CreateContainerView.return_value = container_mock

        result = await esxi_client.list_vms()

        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_list_vms_skips_templates(self, esxi_client):
        """list_vms ignore les VMs qui sont des templates."""
        template_vm = MagicMock()
        template_vm.config.template = True

        container_mock = MagicMock()
        container_mock.view = [template_vm]
        container_mock.Destroy = MagicMock()
        esxi_client._content.viewManager.CreateContainerView.return_value = container_mock

        result = await esxi_client.list_vms()
        assert len(result) == 0


# =============================================================================
# VM lookup tests
# =============================================================================


class TestESXiGetVM:
    """Tests de récupération d'une VM."""

    @pytest.mark.asyncio
    async def test_get_vm_not_found(self, esxi_client):
        """get_vm retourne None quand la VM n'existe pas."""
        container_mock = MagicMock()
        container_mock.view = []
        container_mock.Destroy = MagicMock()
        esxi_client._content.viewManager.CreateContainerView.return_value = container_mock

        result = await esxi_client.get_vm("nonexistent-vm")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_vm_state_not_found(self, esxi_client):
        """get_vm_state retourne None quand la VM n'existe pas."""
        container_mock = MagicMock()
        container_mock.view = []
        container_mock.Destroy = MagicMock()
        esxi_client._content.viewManager.CreateContainerView.return_value = container_mock

        result = await esxi_client.get_vm_state("nonexistent-vm")
        assert result is None


# =============================================================================
# Stub operation tests
# =============================================================================


class TestESXiStubOperations:
    """Vérifie que les opérations Part 2 lèvent NotImplementedError."""

    @pytest.mark.asyncio
    async def test_create_vm_not_implemented(self, esxi_client):
        from src.integrations.hypervisors.base import VMSpecs

        specs = VMSpecs(name="test-vm", cpu_count=2, ram_gb=4, disk_gb=40)
        with pytest.raises(NotImplementedError):
            await esxi_client.create_vm(specs)

    @pytest.mark.asyncio
    async def test_delete_vm_not_implemented(self, esxi_client):
        with pytest.raises(NotImplementedError):
            await esxi_client.delete_vm("vm-123")

    @pytest.mark.asyncio
    async def test_start_vm_not_implemented(self, esxi_client):
        with pytest.raises(NotImplementedError):
            await esxi_client.start_vm("vm-123")

    @pytest.mark.asyncio
    async def test_stop_vm_not_implemented(self, esxi_client):
        with pytest.raises(NotImplementedError):
            await esxi_client.stop_vm("vm-123")

    @pytest.mark.asyncio
    async def test_restart_vm_not_implemented(self, esxi_client):
        with pytest.raises(NotImplementedError):
            await esxi_client.restart_vm("vm-123")

    @pytest.mark.asyncio
    async def test_mount_iso_not_implemented(self, esxi_client):
        with pytest.raises(NotImplementedError):
            await esxi_client.mount_iso("vm-123", "[datastore1] ISOs/test.iso")

    @pytest.mark.asyncio
    async def test_unmount_iso_not_implemented(self, esxi_client):
        with pytest.raises(NotImplementedError):
            await esxi_client.unmount_iso("vm-123")


# =============================================================================
# Guest services (no-op on ESXi)
# =============================================================================


class TestESXiGuestServices:
    """Vérifie le comportement des guest services (VMware Tools)."""

    @pytest.mark.asyncio
    async def test_enable_guest_services_noop(self, esxi_client):
        """enable_guest_services retourne True (no-op sur ESXi)."""
        result = await esxi_client.enable_guest_services("vm-123")
        assert result is True

    @pytest.mark.asyncio
    async def test_get_vm_ip_addresses_no_tools(self, esxi_client):
        """get_vm_ip_addresses retourne vide quand VMware Tools absent."""
        # Mock a VM with no guest info
        vm_mock = MagicMock()
        vm_mock.guest = None
        vm_mock.name = "test-vm"

        container_mock = MagicMock()
        container_mock.view = [vm_mock]
        container_mock.Destroy = MagicMock()
        esxi_client._content.viewManager.CreateContainerView.return_value = container_mock

        result = await esxi_client.get_vm_ip_addresses("test-vm")
        assert isinstance(result, list)
