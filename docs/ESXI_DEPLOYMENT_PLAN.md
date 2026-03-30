# ESXi Deployment System - Implementation Plan

## Architecture
Create a **parallel deployment service** for ESXi (`esxi_deployment_service.py`) that mirrors
the Hyper-V `deployment_service.py` but uses ESXi-native approaches:

- **No PowerShell/WinRM** → VMware GuestOperationsManager + SSH (paramiko)
- **No VHDX** → VMDK (thin provisioned on datastore)
- **No DISM** → ISO-based install (mount ISO + unattend floppy/CDROM)
- **No ISO remastering on Windows host** → Upload files to datastore via pyvmomi
- **No Hyper-V cmdlets** → pyvmomi ReconfigVM_Task / GuestOperationsManager

## Workflow Differences

### Windows on ESXi
1. Create VM (VMDK + vNIC + CD-ROM)
2. Upload unattend.xml to datastore as floppy image
3. Mount Windows ISO + floppy
4. Start VM → Windows installs from ISO + unattend
5. Wait for VMware Tools + heartbeat green
6. Post-config via GuestOperationsManager (cmd.exe/powershell)
7. Finalize (unmount ISO, set boot order)

### Linux on ESXi
1. Create VM (VMDK + vNIC + CD-ROM)
2. Generate seed config (preseed/kickstart/autoinstall/cloud-init)
3. Create seed ISO locally, upload to datastore
4. Mount install ISO + seed ISO
5. Start VM → Linux installs automatically
6. Wait for VMware Tools + SSH ready
7. Post-config via SSH (paramiko)
8. Finalize (unmount ISOs, cleanup datastore temp files)

---

## Agent 1: ESXi Deployment Service — Core & Dispatcher
**File:** `src/domain/esxi_deployment_service.py` (NEW — lines 1-300)

- Create `ESXiDeploymentService` class mirroring `DeploymentService`
- Constructor: `__init__(self, db, vm_service)`
- `deploy(deployment_id)` — main entry, loads deployment, dispatches
- `_execute_deployment(deployment)` — detect OS family, dispatch to Windows/Linux workflow
- `_validate_deployment(deployment)` — same validation logic
- `_update_deployment_status()` — reuse from base
- `_log_step()` — reuse from base
- Import `ESXiClient` instead of `HyperVClient`
- Use `BaseHypervisor` type hints throughout

## Agent 2: ESXi VM Creation & Disk Management
**File:** `src/domain/esxi_deployment_service.py` (lines ~300-500)

- `_create_vm_for_esxi(deployment)` — create VM via ESXiClient.create_vm()
  - Map config to VMSpecs (datastore, resource_pool, guest_os_id, disk_format)
  - Handle retry mode (delete existing + recreate)
  - Set guest_os_id from template (e.g., "windows9_64Guest", "ubuntu64Guest")
- `_get_guest_os_id(template_config)` — map OS templates to VMware guestId
- Disk space check via datastore free space (not PSDrive)

## Agent 3: ESXi Datastore File Operations (NEW helper)
**File:** `src/integrations/hypervisors/esxi_client.py` (ADD methods)

Add datastore file management methods to ESXiClient:
- `list_datastores()` → returns list[dict] with name, capacity_gb, free_gb, type
- `list_resource_pools()` → returns list[dict] with name, cpu, memory
- `upload_file_to_datastore(local_path, datastore, remote_path)` → HTTP PUT to /folder/
- `upload_content_to_datastore(content, datastore, remote_path)` → write string content
- `delete_datastore_file(datastore, remote_path)` → HTTP DELETE
- `mkdir_on_datastore(datastore, path)` → FileManager.MakeDirectory
- `check_disk_space(required_gb)` → check datastore free space
- `ensure_paths_exist()` → create ISO/temp folders on datastore
- `create_floppy_image(content, datastore, path)` → create VFD with unattend.xml
- `get_vm_network_summary(vm_id)` → return IP/MAC/hostname from guest info

## Agent 4: ESXi Windows Deployment Workflow
**File:** `src/domain/esxi_deployment_service.py` (lines ~500-900)

- `_execute_windows_deployment(deployment)` — full Windows workflow:
  1. Create VM with CD-ROM + floppy
  2. Generate unattend.xml (reuse template_engine)
  3. Upload unattend as floppy image to datastore
  4. Mount Windows ISO on CD-ROM
  5. Attach floppy with unattend
  6. Set boot order: CD-ROM first
  7. Start VM
  8. Wait for installation (VMware Tools heartbeat)
  9. Post-configuration via GuestOps
  10. Install software via GuestOps
  11. Finalize (unmount, cleanup)
- `_create_unattend_floppy(deployment, vm)` — generate + upload floppy img
- `_wait_for_windows_ready(deployment, vm)` — poll heartbeat + test GuestOps

## Agent 5: ESXi Linux Deployment Workflow
**File:** `src/domain/esxi_deployment_service.py` (lines ~900-1300)

- `_execute_linux_deployment(deployment)` — full Linux workflow:
  1. Create VM
  2. Detect config type (preseed/kickstart/autoinstall/cloud-init)
  3. Generate seed config (reuse `_generate_linux_seed_config`)
  4. Create seed ISO locally (genisoimage/mkisofs)
  5. Upload seed ISO to datastore
  6. Mount install ISO + seed ISO on VM
  7. Configure VM for Linux (disable Secure Boot via EFI settings)
  8. Set boot order: CD-ROM first
  9. Start VM
  10. Wait for installation (VMware Tools + SSH)
  11. Post-install via SSH
  12. Finalize
- `_create_seed_iso_locally(seed_content, config_type)` — build ISO on local filesystem
- `_configure_vm_for_linux(client, vm_id)` — EFI boot, no Secure Boot

## Agent 6: ESXi Guest Operations & Post-Config
**File:** `src/domain/esxi_deployment_service.py` (lines ~1300-1700)

- `_execute_in_guest(client, vm_id, script, credentials, os_family)` — wrapper:
  - Windows: GuestOperationsManager → cmd.exe or powershell.exe
  - Linux: GuestOperationsManager → /bin/bash
- `_execute_via_ssh(ip, script, credentials, timeout)` — paramiko SSH execution
- `_wait_for_ssh_ready(ip, credentials, timeout)` — poll SSH port + test connection
- `_execute_post_configuration_esxi(deployment, vm)` — post-install services:
  - Windows: RDP, SSH, firewall rules (via GuestOps powershell)
  - Linux: packages, SSH config, users (via SSH)
- `_install_software_esxi(deployment, vm)` — install packages:
  - Windows: winget/choco via GuestOps
  - Linux: apt/dnf via SSH
- `_configure_service_esxi(client, vm_id, service, credentials)` — enable/configure services

## Agent 7: ESXi Finalization & Cleanup
**File:** `src/domain/esxi_deployment_service.py` (lines ~1700-2000)

- `_finalize_esxi_deployment(deployment, vm, os_family)` — common finalization:
  1. Get final network info (IP, MAC) from VMware Tools guest info
  2. Unmount all ISOs / floppy
  3. Set boot order: HardDrive first
  4. Delete temp files from datastore (seed ISO, floppy image, etc.)
  5. Update VM record in DB (ip_address, state)
  6. Generate deployment summary
- `_cleanup_datastore_temp_files(client, vm_name)` — remove temp ISOs/floppies
- `_get_final_network_info(client, vm_id)` — extract IP from guest.net

## Agent 8: Deployment Router & Workers Integration
**Files:** `src/api/routers/deployments.py`, `src/workers/tasks.py`

- Modify deployment router to detect hypervisor type and use correct service:
  - `HypervisorType.HYPERV` → existing `DeploymentService`
  - `HypervisorType.VMWARE` → new `ESXiDeploymentService`
- Update Celery task `deploy_vm` to dispatch to correct service
- Add ESXi-specific deployment config validation
- Ensure deployment logs work the same way for both

## Agent 9: Seed ISO Builder (Local)
**File:** `src/domain/esxi_seed_iso.py` (NEW)

Create local seed ISO builder (no Windows host needed):
- `create_seed_iso(content, config_type, output_path)` — main function
- For preseed: create ISO with `preseed.cfg` at root
- For kickstart: create ISO with `ks.cfg` at root
- For autoinstall: create ISO with `meta-data` + `user-data` (cloud-init NoCloud)
- For cloud-init: create ISO with `meta-data` + `user-data` + `network-config`
- Use `subprocess` to call `genisoimage` or `mkisofs` or `xorriso`
- Fallback: pure Python ISO creation with `pycdlib` if no system tools
- `create_floppy_image(unattend_content, output_path)` — create 1.44MB VFD image
  - Pure Python: write FAT12 floppy image with unattend.xml
  - Used for Windows unattended install on ESXi

## Agent 10: Frontend Deployment Form — ESXi Adaptations
**Files:** `frontend/src/pages/NewDeployment.tsx`, `frontend/src/types/index.ts`

- Update NewDeployment form to adapt based on hypervisor type:
  - When hypervisor is VMware:
    - Show "Datastore" selector instead of "Storage Location/VHDX path"
    - Show "Resource Pool" selector (optional)
    - Show "VM Folder" input (optional)
    - Show "Disk Format" selector: Thin / Thick / Eager Zeroed Thick
    - Show "Guest OS" selector with VMware guest IDs
    - Hide Hyper-V-specific options (Generation, VHDX path)
  - When hypervisor is Hyper-V: keep existing form as-is
- Add API calls to fetch datastores/resource-pools for VMware hypervisors
- Update deployment config payload to include VMware-specific fields
- Update types to include ESXi deployment config fields

---

## Dependencies
- `genisoimage` or `xorriso` on the Linux host (for seed ISO creation)
- `pycdlib` as Python fallback for ISO creation
- `paramiko` for SSH (already in requirements)
- `pyvmomi` (already installed)
