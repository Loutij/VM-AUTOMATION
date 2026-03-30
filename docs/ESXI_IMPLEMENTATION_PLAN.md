# ESXi/vSphere Client Implementation Plan

## Overview
Add VMware ESXi/vSphere support as a second hypervisor backend alongside Hyper-V.
Uses `pyvmomi` (VMware vSphere API Python bindings) to communicate with ESXi/vCenter.

---

## Agent 1: Base Class & Data Models Adaptation
**Files:** `src/integrations/hypervisors/base.py`, `src/domain/models.py`

- Add VMware-specific fields to `VMSpecs`: `datastore`, `resource_pool`, `folder`, `disk_format` (thin/thick/eagerzeroedthick)
- Add `VMSpecs.generation` → make optional (Hyper-V specific, not relevant for ESXi)
- Add `DiskInfo.format` support for VMDK alongside VHDX
- Add `VirtualSwitch` → support for vSwitch/dvSwitch/PortGroup concepts
- Add `VMInfo` fields: `guest_os_id`, `tools_status`, `tools_version`
- Ensure `HypervisorType.VMWARE` enum is already present (confirmed)
- Add ESXi-specific fields to `Hypervisor` model: `datacenter`, `cluster`, `default_datastore`, `default_resource_pool`

## Agent 2: Configuration & Settings
**Files:** `src/common/config.py`, `config/env.example`

- Add ESXi settings to `Settings` class:
  - `esxi_host`, `esxi_port` (default 443)
  - `esxi_user`, `esxi_password` (SecretStr)
  - `esxi_use_ssl` (default True), `esxi_verify_ssl` (default False for self-signed)
  - `esxi_datacenter`, `esxi_cluster`
  - `esxi_default_datastore`, `esxi_default_resource_pool`
  - `esxi_vm_folder`
  - `esxi_iso_datastore`, `esxi_iso_path`
- Update `config/env.example` with ESXi variables (commented out)

## Agent 3: ESXi Client Core — Connection & VM Listing
**File:** `src/integrations/hypervisors/esxi_client.py` (NEW — Part 1)

- Create `ESXiClient(BaseHypervisor)` class
- Implement connection management:
  - `__init__()` with SmartConnect/SmartConnectNoSSL
  - `test_connection()` → ServiceInstance.content check
  - `cleanup()` → Disconnect()
  - Connection pooling / reconnect logic
- Implement read operations:
  - `list_vms()` → ContainerView + vim.VirtualMachine traversal
  - `get_vm(vm_id)` → find by MoRef ID or name
  - `get_vm_state(vm_id)` → runtime.powerState mapping
  - `list_switches()` → HostNetworkSystem portgroups + dvSwitches
  - `get_vm_ip_addresses()` → guest.net info
  - `get_vm_health()` → guestHeartbeatStatus, toolsStatus
  - `get_vm_heartbeat()` → guestHeartbeatStatus
  - `get_vm_integration_services()` → VMware Tools status as equivalent

## Agent 4: ESXi Client — VM Lifecycle Operations
**File:** `src/integrations/hypervisors/esxi_client.py` (Part 2)

- Implement write operations:
  - `create_vm(specs)` → vim.vm.ConfigSpec + CloneVM or CreateVM_Task
  - `delete_vm(vm_id, delete_disks)` → Destroy_Task
  - `start_vm(vm_id)` → PowerOnVM_Task
  - `stop_vm(vm_id, force)` → ShutdownGuest (graceful) / PowerOffVM_Task (force)
  - `restart_vm(vm_id, force)` → RebootGuest / ResetVM_Task
- Implement storage operations:
  - `mount_iso(vm_id, iso_path)` → VirtualCdrom reconfigure
  - `unmount_iso(vm_id)` → disconnect CD-ROM
  - `set_boot_order(vm_id, boot_order)` → BootOptions
  - `set_first_boot_device(vm_id, device_type)`
- Implement guest operations:
  - `execute_in_vm()` → GuestOperationsManager (requires VMware Tools)
  - `enable_guest_services()` → check/install VMware Tools
  - `cleanup_post_install()` → unmount ISO + set boot order
  - `wait_for_vm_ready()` → poll guestHeartbeatStatus + toolsRunningStatus

## Agent 5: VM Service Factory & Routing
**Files:** `src/domain/vm_service.py`, `src/integrations/hypervisors/__init__.py`

- Refactor `_get_hypervisor_client()` to factory pattern:
  - `HypervisorType.HYPERV` → `HyperVClient`
  - `HypervisorType.VMWARE` → `ESXiClient`
- Update `__init__.py` to export `ESXiClient`
- Update type hints: `dict[UUID, HyperVClient]` → `dict[UUID, BaseHypervisor]`
- Handle ESXi-specific password decryption
- Add VMware-specific deployment logic in deployment flow if needed

## Agent 6: API Router & Schemas Adaptation
**Files:** `src/api/routers/hypervisors.py`

- Update `HypervisorCreate` schema:
  - Add optional VMware fields: `datacenter`, `cluster`, `default_datastore`
  - Update port default: 5986 for Hyper-V, 443 for VMware
- Update `HypervisorResponse` to include VMware-specific fields
- Adapt `list_storage_locations` endpoint:
  - For VMware: query datastores instead of PSDrive
- Adapt `list_hypervisor_isos`:
  - For VMware: browse datastore for ISOs
- Handle `orphan-vhdx` → generalize to `orphan-disks` (VHDX + VMDK)
- Add ESXi-specific endpoints if needed:
  - `GET /{id}/datastores` — list datastores
  - `GET /{id}/resource-pools` — list resource pools
  - `GET /{id}/clusters` — list clusters

## Agent 7: Frontend Types & UI Updates
**Files:** `frontend/src/types/index.ts`, `frontend/src/pages/Hypervisors.tsx`, `frontend/src/services/api.ts`

- Update TypeScript types:
  - Add VMware fields to `Hypervisor` type
  - Add `datastore`, `resourcePool` to VM types
- Update Hypervisors page:
  - Show VMware-specific fields in create/edit forms
  - Dynamic port default (5986 vs 443 based on type)
  - Show VMware Tools status instead of Integration Services
- Update API service:
  - Add datastore/resource-pool API calls
- Update VM detail views:
  - Show VMDK info instead of VHDX
  - Show VMware Tools status

## Agent 8: Requirements, Tests & Migration
**Files:** `requirements.txt`, `pyproject.toml`, `tests/`, `alembic/versions/`

- Uncomment `pyvmomi>=8.0.0` in requirements.txt
- Add pyvmomi to pyproject.toml dependencies
- Create Alembic migration for new Hypervisor columns:
  - `datacenter`, `cluster`, `default_datastore`, `default_resource_pool`
- Create unit tests:
  - `tests/unit/test_esxi_client.py` — mock pyvmomi, test all methods
  - Update `tests/unit/test_models.py` — test new fields
- Create integration test skeleton:
  - `tests/integration/test_esxi_connection.py`

---

## Architecture Notes
- pyvmomi uses synchronous blocking calls → wrap with `asyncio.to_thread()`
- ESXi MoRef IDs (e.g., `vm-123`) used as vm_id
- VMware Tools = equivalent of Hyper-V Integration Services
- Datastores = equivalent of drive letters/paths
- Resource Pools = no Hyper-V equivalent (use default)
- vCenter optional — can connect directly to ESXi host
