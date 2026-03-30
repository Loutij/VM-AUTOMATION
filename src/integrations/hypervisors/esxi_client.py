# =============================================================================
# VM Automation - ESXi/vSphere Client
# =============================================================================
"""
Client pour l'interaction avec les hôtes ESXi/vCenter via pyvmomi (vSphere API).
"""

import asyncio
import atexit
import time
from typing import Any

from src.common.exceptions import (
    HypervisorConnectionError,
    HypervisorError,
    VMNotFoundError,
    VMOperationError,
)
from src.common.logging import get_logger
from src.integrations.hypervisors.base import (
    BaseHypervisor,
    DiskInfo,
    IntegrationService,
    PowerShellDirectResult,
    VirtualSwitch,
    VMHealthStatus,
    VMInfo,
    VMSpecs,
)

# Import conditionnel de pyvmomi pour ne pas bloquer si non installé
try:
    from pyVim.connect import Disconnect, SmartConnect
    from pyVmomi import vim, vmodl

    PYVMOMI_AVAILABLE = True
except ImportError:
    PYVMOMI_AVAILABLE = False
    vim = None  # type: ignore[assignment]
    vmodl = None  # type: ignore[assignment]

logger = get_logger(__name__)


class ESXiClient(BaseHypervisor):
    """
    Client ESXi/vSphere utilisant pyvmomi.

    Permet de gérer les VMs, réseaux, et datastores sur un hôte ESXi
    ou un vCenter Server.
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 443,
        use_ssl: bool = True,
        verify_ssl: bool = False,
        datacenter: str = "",
        cluster: str = "",
        default_datastore: str = "datastore1",
        default_resource_pool: str = "",
        vm_folder: str = "",
        iso_datastore: str = "",
        iso_path: str = "ISOs",
    ) -> None:
        """
        Initialise le client ESXi/vSphere.

        Args:
            host: Adresse de l'hôte ESXi ou vCenter
            username: Utilisateur (ex: root, administrator@vsphere.local)
            password: Mot de passe
            port: Port de l'API vSphere (443 par défaut)
            use_ssl: Utiliser SSL pour la connexion
            verify_ssl: Vérifier le certificat SSL
            datacenter: Nom du datacenter (vCenter uniquement)
            cluster: Nom du cluster (vCenter uniquement)
            default_datastore: Datastore par défaut pour les VMs
            default_resource_pool: Resource pool par défaut
            vm_folder: Dossier VM par défaut
            iso_datastore: Datastore pour les ISOs (si différent)
            iso_path: Chemin relatif des ISOs dans le datastore
        """
        if not PYVMOMI_AVAILABLE:
            raise HypervisorError(
                "pyvmomi n'est pas installé. "
                "Installez-le avec: pip install pyvmomi"
            )

        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.use_ssl = use_ssl
        self.verify_ssl = verify_ssl
        self.datacenter = datacenter
        self.cluster = cluster
        self.default_datastore = default_datastore
        self.default_resource_pool = default_resource_pool
        self.vm_folder = vm_folder
        self.iso_datastore = iso_datastore or default_datastore
        self.iso_path = iso_path

        # Connexion vSphere (initialisée paresseusement)
        self._si: Any = None  # ServiceInstance
        self._content: Any = None  # ServiceContent

        logger.info(
            "esxi_client_init",
            host=self.host,
            port=self.port,
            use_ssl=self.use_ssl,
            datacenter=self.datacenter or "(direct ESXi)",
        )

    # =========================================================================
    # Gestion de la connexion
    # =========================================================================

    def _connect(self) -> None:
        """
        Établit la connexion au serveur vSphere (synchrone).

        pyvmomi 9.x : SmartConnect gère SSL via disableSslCertValidation.
        """
        try:
            self._si = SmartConnect(
                host=self.host,
                user=self.username,
                pwd=self.password,
                port=self.port,
                disableSslCertValidation=not self.verify_ssl,
            )

            # Déconnexion automatique à la sortie du processus
            atexit.register(Disconnect, self._si)

            self._content = self._si.RetrieveContent()
            logger.info(
                "esxi_connected",
                host=self.host,
                api_version=self._content.about.fullName,
            )
        except Exception as e:
            self._si = None
            self._content = None
            raise HypervisorConnectionError(
                self.host,
                reason=str(e),
            ) from e

    def _ensure_connected(self) -> None:
        """
        Vérifie la connexion et reconnecte si nécessaire.

        Détecte les sessions expirées via currentSession.
        """
        if self._si is None:
            self._connect()
            return

        # Vérifier si la session est encore valide
        try:
            session = self._si.content.sessionManager.currentSession
            if session is None:
                logger.warning("esxi_session_expired", host=self.host)
                self._si = None
                self._content = None
                self._connect()
        except Exception:
            logger.warning("esxi_session_check_failed", host=self.host)
            self._si = None
            self._content = None
            self._connect()

    def _get_obj(self, vimtype: list, name: str) -> Any | None:
        """
        Recherche un objet managé par type et nom.

        Args:
            vimtype: Liste de types vim (ex: [vim.VirtualMachine])
            name: Nom de l'objet recherché

        Returns:
            L'objet trouvé ou None
        """
        self._ensure_connected()
        container = self._content.viewManager.CreateContainerView(
            self._content.rootFolder, vimtype, True
        )
        try:
            for obj in container.view:
                if obj.name == name:
                    return obj
        finally:
            container.Destroy()
        return None

    def _get_all_objs(self, vimtype: list, folder: Any = None) -> list[Any]:
        """
        Récupère tous les objets d'un type donné.

        Args:
            vimtype: Liste de types vim
            folder: Dossier racine (rootFolder par défaut)

        Returns:
            Liste des objets trouvés
        """
        self._ensure_connected()
        root = folder or self._content.rootFolder
        container = self._content.viewManager.CreateContainerView(
            root, vimtype, True
        )
        try:
            return list(container.view)
        finally:
            container.Destroy()

    def _get_vm_by_id(self, vm_id: str) -> Any:
        """
        Recherche une VM par MoRef ID (ex: "vm-123") ou par nom.

        Args:
            vm_id: Identifiant MoRef ou nom de la VM

        Returns:
            Objet VM pyvmomi

        Raises:
            VMNotFoundError: Si la VM n'est pas trouvée
        """
        self._ensure_connected()

        # Essayer d'abord par MoRef ID
        if vm_id.startswith("vm-"):
            try:
                vm = vim.VirtualMachine(vm_id, self._si._stub)
                # Vérifier que la VM existe en accédant à son nom
                _ = vm.name
                return vm
            except Exception:
                pass

        # Fallback: recherche par nom
        vm = self._get_obj([vim.VirtualMachine], vm_id)
        if vm is None:
            raise VMNotFoundError(vm_id, self.host)
        return vm

    # =========================================================================
    # Conversion VM pyvmomi → VMInfo
    # =========================================================================

    def _vm_to_info(self, vm: Any) -> VMInfo:
        """
        Convertit un objet VM pyvmomi en VMInfo dataclass.

        Args:
            vm: Objet vim.VirtualMachine

        Returns:
            VMInfo avec les données extraites
        """
        config = vm.config
        runtime = vm.runtime
        summary = vm.summary

        # Mapping des états de puissance vSphere → états internes
        state_map = {
            vim.VirtualMachinePowerState.poweredOn: "Running",
            vim.VirtualMachinePowerState.poweredOff: "Off",
            vim.VirtualMachinePowerState.suspended: "Paused",
        }

        # Uptime depuis le boot (si disponible et allumée)
        uptime = None
        if summary and summary.quickStats and summary.quickStats.uptimeSeconds:
            seconds = summary.quickStats.uptimeSeconds
            hours, remainder = divmod(seconds, 3600)
            minutes, secs = divmod(remainder, 60)
            uptime = f"{hours}h {minutes}m {secs}s"

        # Notes / annotation
        notes = None
        if config and config.annotation:
            notes = config.annotation

        # Chemin du vmx
        path = None
        if config and config.files and config.files.vmPathName:
            path = config.files.vmPathName

        return VMInfo(
            id=vm._moId,
            name=config.name if config else vm.name,
            state=state_map.get(runtime.powerState, "Unknown"),
            cpu_count=config.hardware.numCPU if config and config.hardware else 0,
            ram_gb=round((config.hardware.memoryMB or 0) / 1024) if config and config.hardware else 0,
            uptime=uptime,
            status=summary.overallStatus if summary else None,
            notes=notes,
            generation=2,  # ESXi VMs sont toujours "Gen2" (EFI par défaut)
            path=path,
        )

    # =========================================================================
    # Implémentation BaseHypervisor — Opérations de lecture
    # =========================================================================

    async def test_connection(self) -> bool:
        """Teste la connexion au serveur vSphere."""
        try:
            def _test() -> bool:
                self._ensure_connected()
                full_name = self._content.about.fullName
                logger.info(
                    "esxi_connection_test_ok",
                    host=self.host,
                    full_name=full_name,
                )
                return True

            return await asyncio.to_thread(_test)
        except HypervisorConnectionError:
            raise
        except Exception as e:
            logger.error("esxi_connection_test_failed", host=self.host, error=str(e))
            raise HypervisorConnectionError(self.host, reason=str(e)) from e

    async def list_vms(self) -> list[VMInfo]:
        """Liste toutes les VMs sur l'hôte ESXi/vCenter."""
        def _list() -> list[VMInfo]:
            self._ensure_connected()
            vms = self._get_all_objs([vim.VirtualMachine])
            result = []
            for vm in vms:
                try:
                    # Ignorer les templates
                    if vm.config and vm.config.template:
                        continue
                    result.append(self._vm_to_info(vm))
                except Exception as e:
                    logger.warning(
                        "esxi_vm_info_error",
                        vm_name=getattr(vm, "name", "unknown"),
                        error=str(e),
                    )
            return result

        try:
            return await asyncio.to_thread(_list)
        except HypervisorConnectionError:
            raise
        except Exception as e:
            logger.error("esxi_list_vms_error", error=str(e))
            raise HypervisorError(
                f"Erreur lors du listing des VMs: {e}"
            ) from e

    async def get_vm(self, vm_id: str) -> VMInfo | None:
        """Récupère les informations d'une VM par ID ou nom."""
        def _get() -> VMInfo | None:
            try:
                vm = self._get_vm_by_id(vm_id)
                return self._vm_to_info(vm)
            except VMNotFoundError:
                return None

        try:
            return await asyncio.to_thread(_get)
        except HypervisorConnectionError:
            raise
        except VMNotFoundError:
            return None
        except Exception as e:
            logger.error("esxi_get_vm_error", vm_id=vm_id, error=str(e))
            raise HypervisorError(
                f"Erreur lors de la récupération de la VM '{vm_id}': {e}"
            ) from e

    async def get_vm_state(self, vm_id: str) -> str | None:
        """Récupère l'état d'une VM (Running, Off, Paused)."""
        def _get_state() -> str | None:
            try:
                vm = self._get_vm_by_id(vm_id)
            except VMNotFoundError:
                return None

            state_map = {
                vim.VirtualMachinePowerState.poweredOn: "Running",
                vim.VirtualMachinePowerState.poweredOff: "Off",
                vim.VirtualMachinePowerState.suspended: "Paused",
            }
            return state_map.get(vm.runtime.powerState, "Unknown")

        try:
            return await asyncio.to_thread(_get_state)
        except HypervisorConnectionError:
            raise
        except Exception as e:
            logger.error("esxi_get_vm_state_error", vm_id=vm_id, error=str(e))
            return None

    async def list_switches(self) -> list[VirtualSwitch]:
        """Liste les portgroups réseau disponibles."""
        def _list() -> list[VirtualSwitch]:
            self._ensure_connected()
            switches: list[VirtualSwitch] = []

            # Récupérer les réseaux via les hôtes ESXi
            hosts = self._get_all_objs([vim.HostSystem])
            seen_names: set[str] = set()

            for host in hosts:
                try:
                    network_system = host.configManager.networkSystem
                    if not network_system:
                        continue

                    # Portgroups standard
                    for pg in network_system.networkInfo.portgroup:
                        if pg.spec.name in seen_names:
                            continue
                        seen_names.add(pg.spec.name)
                        switches.append(VirtualSwitch(
                            name=pg.spec.name,
                            switch_type="Standard",
                            interface_description=pg.spec.vswitchName,
                            notes=f"VLAN {pg.spec.vlanId}" if pg.spec.vlanId else None,
                        ))

                    # vSwitches
                    for vs in network_system.networkInfo.vswitch:
                        if vs.name in seen_names:
                            continue
                        seen_names.add(vs.name)
                        switches.append(VirtualSwitch(
                            name=vs.name,
                            switch_type="vSwitch",
                            interface_description=", ".join(vs.pnic) if vs.pnic else None,
                        ))
                except Exception as e:
                    logger.warning(
                        "esxi_list_switches_host_error",
                        host_name=host.name,
                        error=str(e),
                    )

            # Portgroups distribués (vCenter uniquement)
            try:
                dvs_list = self._get_all_objs([vim.DistributedVirtualSwitch])
                for dvs in dvs_list:
                    if dvs.name in seen_names:
                        continue
                    seen_names.add(dvs.name)
                    switches.append(VirtualSwitch(
                        name=dvs.name,
                        switch_type="Distributed",
                        interface_description=dvs.summary.description if dvs.summary else None,
                    ))
            except Exception:
                pass  # Pas de DVS disponible (ESXi standalone)

            return switches

        try:
            return await asyncio.to_thread(_list)
        except HypervisorConnectionError:
            raise
        except Exception as e:
            logger.error("esxi_list_switches_error", error=str(e))
            raise HypervisorError(
                f"Erreur lors du listing des switches: {e}"
            ) from e

    async def get_vm_ip_addresses(self, vm_id: str) -> list[str]:
        """Récupère les adresses IP d'une VM via VMware Tools (guest.net)."""
        def _get_ips() -> list[str]:
            vm = self._get_vm_by_id(vm_id)
            ips: list[str] = []

            if not vm.guest or not vm.guest.net:
                return ips

            for nic in vm.guest.net:
                if nic.ipAddress:
                    for ip in nic.ipAddress:
                        # Filtrer les adresses link-local IPv6
                        if not ip.startswith("fe80:"):
                            ips.append(ip)
            return ips

        try:
            return await asyncio.to_thread(_get_ips)
        except VMNotFoundError:
            raise
        except HypervisorConnectionError:
            raise
        except Exception as e:
            logger.error("esxi_get_vm_ips_error", vm_id=vm_id, error=str(e))
            return []

    async def get_vm_health(self, vm_id: str) -> VMHealthStatus | None:
        """Récupère l'état de santé complet d'une VM."""
        def _get_health() -> VMHealthStatus | None:
            try:
                vm = self._get_vm_by_id(vm_id)
            except VMNotFoundError:
                return None

            summary = vm.summary
            config = vm.config
            runtime = vm.runtime
            guest = vm.guest

            # État de puissance
            state_map = {
                vim.VirtualMachinePowerState.poweredOn: "Running",
                vim.VirtualMachinePowerState.poweredOff: "Off",
                vim.VirtualMachinePowerState.suspended: "Paused",
            }
            state = state_map.get(runtime.powerState, "Unknown")

            # Heartbeat — mapping des valeurs VMware
            heartbeat_map = {
                "green": "OkApplicationsHealthy",
                "yellow": "OkApplicationsUnknown",
                "red": "NoContact",
                "gray": "Disabled",
            }
            raw_heartbeat = str(summary.quickStats.guestHeartbeatStatus) if summary else "gray"
            heartbeat = heartbeat_map.get(raw_heartbeat, raw_heartbeat)

            # Uptime
            uptime = None
            if summary and summary.quickStats and summary.quickStats.uptimeSeconds:
                seconds = summary.quickStats.uptimeSeconds
                hours, remainder = divmod(seconds, 3600)
                minutes, secs = divmod(remainder, 60)
                uptime = f"{hours}h {minutes}m {secs}s"

            # CPU et mémoire
            cpu_usage = summary.quickStats.overallCpuUsage or 0 if summary else 0
            memory_mb = (config.hardware.memoryMB or 0) if config and config.hardware else 0

            # Adresses IP
            ips: list[str] = []
            if guest and guest.net:
                for nic in guest.net:
                    if nic.ipAddress:
                        for ip in nic.ipAddress:
                            if not ip.startswith("fe80:"):
                                ips.append(ip)

            # VMware Tools comme service d'intégration
            tools_status = guest.toolsRunningStatus if guest else "guestToolsNotRunning"
            tools_version = guest.toolsVersionStatus2 if guest else "guestToolsNotInstalled"
            integration_services = [
                IntegrationService(
                    name="VMware Tools",
                    enabled=tools_status == "guestToolsRunning",
                    status=f"{tools_status} ({tools_version})",
                ),
            ]

            return VMHealthStatus(
                vm_name=config.name if config else vm_id,
                state=state,
                heartbeat=heartbeat,
                uptime=uptime,
                cpu_usage=cpu_usage,
                memory_mb=memory_mb,
                ip_addresses=ips,
                integration_services=integration_services,
            )

        try:
            return await asyncio.to_thread(_get_health)
        except HypervisorConnectionError:
            raise
        except Exception as e:
            logger.error("esxi_get_vm_health_error", vm_id=vm_id, error=str(e))
            return None

    async def get_vm_heartbeat(self, vm_id: str) -> str | None:
        """Récupère le statut heartbeat d'une VM."""
        def _get_heartbeat() -> str | None:
            try:
                vm = self._get_vm_by_id(vm_id)
            except VMNotFoundError:
                return None

            if not vm.summary or not vm.summary.quickStats:
                return None

            # Retourner directement la valeur VMware (green/yellow/red/gray)
            return str(vm.summary.quickStats.guestHeartbeatStatus)

        try:
            return await asyncio.to_thread(_get_heartbeat)
        except HypervisorConnectionError:
            raise
        except Exception as e:
            logger.error("esxi_get_heartbeat_error", vm_id=vm_id, error=str(e))
            return None


    async def get_vmware_tools_status(self, vm_id: str) -> str | None:
        """Récupère le statut des VMware Tools (toolsOk, toolsOld, toolsNotInstalled, toolsNotRunning)."""
        def _get_status() -> str | None:
            try:
                vm = self._get_vm_by_id(vm_id)
            except VMNotFoundError:
                return None

            if not vm.guest:
                return None

            return str(vm.guest.toolsStatus) if vm.guest.toolsStatus else None

        try:
            return await asyncio.to_thread(_get_status)
        except HypervisorConnectionError:
            raise
        except Exception as e:
            logger.error("esxi_get_vmware_tools_status_error", vm_id=vm_id, error=str(e))
            return None

    async def get_vm_integration_services(
        self,
        vm_id: str,
    ) -> list[IntegrationService]:
        """Récupère les services d'intégration (VMware Tools) d'une VM."""
        def _get_services() -> list[IntegrationService]:
            vm = self._get_vm_by_id(vm_id)
            guest = vm.guest

            if not guest:
                return [
                    IntegrationService(
                        name="VMware Tools",
                        enabled=False,
                        status="Inconnu (guest info indisponible)",
                    )
                ]

            tools_running = guest.toolsRunningStatus or "guestToolsNotRunning"
            tools_version = guest.toolsVersionStatus2 if hasattr(guest, "toolsVersionStatus2") else (
                guest.toolsVersionStatus or "guestToolsNotInstalled"
            )

            services = [
                IntegrationService(
                    name="VMware Tools",
                    enabled=tools_running == "guestToolsRunning",
                    status=tools_running,
                ),
                IntegrationService(
                    name="VMware Tools Version",
                    enabled=tools_version not in ("guestToolsNotInstalled", "guestToolsNeedUpgrade"),
                    status=tools_version,
                ),
            ]

            # Infos supplémentaires sur l'OS invité
            if guest.guestFullName:
                services.append(IntegrationService(
                    name="Guest OS",
                    enabled=True,
                    status=guest.guestFullName,
                ))

            return services

        try:
            return await asyncio.to_thread(_get_services)
        except VMNotFoundError:
            raise
        except HypervisorConnectionError:
            raise
        except Exception as e:
            logger.error("esxi_get_integration_services_error", vm_id=vm_id, error=str(e))
            return []

    # =========================================================================
    # Utilitaires internes
    # =========================================================================

    def _wait_for_task(self, task: Any) -> Any:
        """Attend la fin d'une tâche vSphere (synchrone, appeler via to_thread)."""
        while task.info.state not in (
            vim.TaskInfo.State.success,
            vim.TaskInfo.State.error,
        ):
            time.sleep(1)
        if task.info.state == vim.TaskInfo.State.error:
            raise HypervisorError(
                f"Échec de la tâche vSphere : {task.info.error.msg}"
            )
        return task.info.result

    def _find_resource_pool(self, folder: Any, name: str) -> Any:
        """Recherche récursive d'une pool de ressources par nom."""
        for child in getattr(folder, "childEntity", []):
            if hasattr(child, "resourcePool"):
                pool = child.resourcePool
                if pool.name == name:
                    return pool
                found = self._search_pool(pool, name)
                if found:
                    return found
        return None

    def _search_pool(self, pool: Any, name: str) -> Any:
        """Recherche récursive dans les sous-pools."""
        for child in pool.resourcePool:
            if child.name == name:
                return child
            found = self._search_pool(child, name)
            if found:
                return found
        return None

    # =========================================================================
    # Opérations d'écriture — Cycle de vie des VMs
    # =========================================================================

    async def create_vm(self, specs: VMSpecs, **kwargs) -> VMInfo:
        """Crée une VM sur ESXi via vim.vm.ConfigSpec."""
        logger.info(
            "esxi_creating_vm",
            name=specs.name,
            cpu=specs.cpu_count,
            ram_gb=specs.ram_gb,
            disk_gb=specs.disk_gb,
        )

        def _create() -> Any:
            self._ensure_connected()
            content = self._si.RetrieveContent()

            # -- Résoudre le datacenter, dossier VM et resource pool --
            datacenter = content.rootFolder.childEntity[0]
            vm_folder = datacenter.vmFolder
            if specs.folder:
                for child in vm_folder.childEntity:
                    if hasattr(child, "name") and child.name == specs.folder:
                        vm_folder = child
                        break

            # Pool de ressources
            resource_pool = None
            if specs.resource_pool:
                resource_pool = self._find_resource_pool(
                    datacenter.hostFolder, specs.resource_pool
                )
            if resource_pool is None:
                host = datacenter.hostFolder.childEntity[0]
                resource_pool = (
                    host.resourcePool
                    if hasattr(host, "resourcePool")
                    else host.host[0].parent.resourcePool
                )

            # -- Résoudre le datastore --
            datastore_name = specs.datastore or self.default_datastore
            if not datastore_name:
                ds = datacenter.datastore[0]
                datastore_name = ds.name

            # -- OS invité --
            guest_os_id = specs.guest_os_id or "otherGuest64"

            # -- ConfigSpec --
            config_spec = vim.vm.ConfigSpec()
            config_spec.name = specs.name
            config_spec.numCPUs = specs.cpu_count
            config_spec.memoryMB = specs.ram_gb * 1024
            config_spec.guestId = guest_os_id
            config_spec.files = vim.vm.FileInfo(
                vmPathName=f"[{datastore_name}]"
            )

            # -- Contrôleur SCSI (ParaVirtual) --
            scsi_spec = vim.vm.device.VirtualDeviceSpec()
            scsi_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
            scsi_ctrl = vim.vm.device.ParaVirtualSCSIController()
            scsi_ctrl.key = 1000
            scsi_ctrl.busNumber = 0
            scsi_ctrl.sharedBus = vim.vm.device.VirtualSCSIController.Sharing.noSharing
            scsi_spec.device = scsi_ctrl

            # -- Disque virtuel --
            disk_spec = vim.vm.device.VirtualDeviceSpec()
            disk_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
            disk_spec.fileOperation = vim.vm.device.VirtualDeviceSpec.FileOperation.create
            disk = vim.vm.device.VirtualDisk()
            disk.key = 2000
            disk.controllerKey = 1000
            disk.unitNumber = 0
            disk.capacityInKB = specs.disk_gb * 1024 * 1024  # Go -> Ko

            disk_backing = vim.vm.device.VirtualDisk.FlatVer2BackingInfo()
            disk_backing.fileName = f"[{datastore_name}]"
            disk_backing.diskMode = "persistent"
            if specs.disk_format == "thin":
                disk_backing.thinProvisioned = True
                disk_backing.eagerlyScrub = False
            elif specs.disk_format == "eagerzeroedthick":
                disk_backing.thinProvisioned = False
                disk_backing.eagerlyScrub = True
            else:  # thick (lazy zeroed)
                disk_backing.thinProvisioned = False
                disk_backing.eagerlyScrub = False
            disk.backing = disk_backing
            disk_spec.device = disk

            # -- Adaptateur réseau (vmxnet3) --
            nic_spec = vim.vm.device.VirtualDeviceSpec()
            nic_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
            nic = vim.vm.device.VirtualVmxnet3()
            nic.key = 4000
            network = None
            network_name = specs.network_switch or "VM Network"
            for net in datacenter.network:
                if net.name == network_name:
                    network = net
                    break
            if network is None and datacenter.network:
                network = datacenter.network[0]
                network_name = network.name

            if network and isinstance(network, vim.dvs.DistributedVirtualPortgroup):
                dvs_backing = vim.vm.device.VirtualEthernetCard.DistributedVirtualPortBackingInfo()
                dvs_port = vim.dvs.PortConnection()
                dvs_port.portgroupKey = network.key
                dvs_port.switchUuid = network.config.distributedVirtualSwitch.uuid
                dvs_backing.port = dvs_port
                nic.backing = dvs_backing
            else:
                nic_backing = vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
                nic_backing.deviceName = network_name
                nic.backing = nic_backing
            nic.addressType = "Generated"
            nic_spec.device = nic

            # -- CD-ROM --
            ide_spec = vim.vm.device.VirtualDeviceSpec()
            ide_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
            ide_ctrl = vim.vm.device.VirtualIDEController()
            ide_ctrl.key = 200
            ide_ctrl.busNumber = 0
            ide_spec.device = ide_ctrl

            cdrom_spec = vim.vm.device.VirtualDeviceSpec()
            cdrom_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
            cdrom = vim.vm.device.VirtualCdrom()
            cdrom.key = 3000
            cdrom.controllerKey = 200
            cdrom.unitNumber = 0

            if specs.iso_path:
                iso_backing = vim.vm.device.VirtualCdrom.IsoBackingInfo()
                iso_backing.fileName = specs.iso_path
                cdrom.backing = iso_backing
                connectable = vim.vm.device.VirtualDevice.ConnectInfo()
                connectable.startConnected = True
                connectable.connected = True
                connectable.allowGuestControl = True
                cdrom.connectable = connectable
            else:
                remote_backing = vim.vm.device.VirtualCdrom.RemotePassthroughBackingInfo()
                remote_backing.deviceName = ""
                cdrom.backing = remote_backing
            cdrom_spec.device = cdrom

            config_spec.deviceChange = [scsi_spec, disk_spec, nic_spec, ide_spec, cdrom_spec]

            # -- Créer la VM --
            task = vm_folder.CreateVM_Task(config=config_spec, pool=resource_pool)
            vm = self._wait_for_task(task)
            return vm

        try:
            vm = await asyncio.to_thread(_create)
            vm_info = await asyncio.to_thread(self._vm_to_info, vm)
            logger.info("esxi_vm_created", name=specs.name, id=vm_info.id)
            return vm_info
        except HypervisorError:
            raise
        except Exception as e:
            raise VMOperationError(specs.name, "create_vm", str(e)) from e

    async def delete_vm(self, vm_id: str, delete_disks: bool = False) -> bool:
        """Supprime une VM ESXi. Arrête la VM d'abord si elle tourne."""
        logger.info("esxi_deleting_vm", vm_id=vm_id, delete_disks=delete_disks)

        def _delete() -> bool:
            try:
                vm = self._get_vm_by_id(vm_id)
            except VMNotFoundError:
                logger.warning("esxi_vm_not_found_for_delete", vm_id=vm_id)
                return True

            if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
                logger.info("esxi_powering_off_before_delete", vm_id=vm_id)
                task = vm.PowerOffVM_Task()
                self._wait_for_task(task)

            if delete_disks:
                task = vm.Destroy_Task()
                self._wait_for_task(task)
            else:
                vm.UnregisterVM()
            return True

        try:
            result = await asyncio.to_thread(_delete)
            logger.info("esxi_vm_deleted", vm_id=vm_id)
            return result
        except HypervisorError:
            raise
        except Exception as e:
            raise VMOperationError(vm_id, "delete_vm", str(e)) from e

    async def start_vm(self, vm_id: str) -> bool:
        """Démarre une VM ESXi."""
        def _start() -> bool:
            vm = self._get_vm_by_id(vm_id)
            if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
                logger.info("esxi_vm_already_running", vm_id=vm_id)
                return True
            task = vm.PowerOnVM_Task()
            self._wait_for_task(task)
            return True

        try:
            await asyncio.to_thread(_start)
            logger.info("esxi_vm_started", vm_id=vm_id)
            return True
        except (HypervisorError, VMNotFoundError):
            raise
        except Exception as e:
            raise VMOperationError(vm_id, "start_vm", str(e)) from e

    async def stop_vm(self, vm_id: str, force: bool = False) -> bool:
        """Arrête une VM ESXi (gracieux via VMware Tools ou brutal)."""
        def _stop() -> bool:
            vm = self._get_vm_by_id(vm_id)
            if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOff:
                logger.info("esxi_vm_already_off", vm_id=vm_id)
                return True

            if force:
                task = vm.PowerOffVM_Task()
                self._wait_for_task(task)
            else:
                try:
                    vm.ShutdownGuest()
                except vim.fault.ToolsUnavailable:
                    logger.warning("esxi_tools_unavailable_forcing_poweroff", vm_id=vm_id)
                    task = vm.PowerOffVM_Task()
                    self._wait_for_task(task)
            return True

        try:
            await asyncio.to_thread(_stop)
            logger.info("esxi_vm_stopped", vm_id=vm_id, force=force)
            return True
        except (HypervisorError, VMNotFoundError):
            raise
        except Exception as e:
            raise VMOperationError(vm_id, "stop_vm", str(e)) from e

    async def restart_vm(self, vm_id: str, force: bool = False) -> bool:
        """Redémarre une VM ESXi (gracieux via VMware Tools ou brutal)."""
        def _restart() -> bool:
            vm = self._get_vm_by_id(vm_id)
            if force:
                task = vm.ResetVM_Task()
                self._wait_for_task(task)
            else:
                try:
                    vm.RebootGuest()
                except vim.fault.ToolsUnavailable:
                    logger.warning("esxi_tools_unavailable_forcing_reset", vm_id=vm_id)
                    task = vm.ResetVM_Task()
                    self._wait_for_task(task)
            return True

        try:
            await asyncio.to_thread(_restart)
            logger.info("esxi_vm_restarted", vm_id=vm_id, force=force)
            return True
        except (HypervisorError, VMNotFoundError):
            raise
        except Exception as e:
            raise VMOperationError(vm_id, "restart_vm", str(e)) from e

    # =========================================================================
    # Stockage / Boot
    # =========================================================================

    async def mount_iso(self, vm_id: str, iso_path: str) -> bool:
        """Monte une ISO sur le lecteur CD-ROM d'une VM ESXi."""
        def _mount() -> bool:
            vm = self._get_vm_by_id(vm_id)
            cdrom_device = None
            for dev in vm.config.hardware.device:
                if isinstance(dev, vim.vm.device.VirtualCdrom):
                    cdrom_device = dev
                    break

            if cdrom_device is None:
                raise HypervisorError(f"Aucun lecteur CD-ROM trouvé sur la VM '{vm_id}'")

            cdrom_spec = vim.vm.device.VirtualDeviceSpec()
            cdrom_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
            cdrom_spec.device = cdrom_device

            iso_backing = vim.vm.device.VirtualCdrom.IsoBackingInfo()
            iso_backing.fileName = iso_path
            cdrom_spec.device.backing = iso_backing

            connectable = vim.vm.device.VirtualDevice.ConnectInfo()
            connectable.startConnected = True
            connectable.connected = True
            connectable.allowGuestControl = True
            cdrom_spec.device.connectable = connectable

            config_spec = vim.vm.ConfigSpec()
            config_spec.deviceChange = [cdrom_spec]
            task = vm.ReconfigVM_Task(spec=config_spec)
            self._wait_for_task(task)
            return True

        try:
            await asyncio.to_thread(_mount)
            logger.info("esxi_iso_mounted", vm_id=vm_id, iso_path=iso_path)
            return True
        except (HypervisorError, VMNotFoundError):
            raise
        except Exception as e:
            raise VMOperationError(vm_id, "mount_iso", str(e)) from e

    async def unmount_iso(self, vm_id: str, unmount_all: bool = True) -> bool:
        """Démonte les ISOs des lecteurs CD-ROM d'une VM ESXi."""
        def _unmount() -> bool:
            vm = self._get_vm_by_id(vm_id)
            device_changes: list[Any] = []

            for dev in vm.config.hardware.device:
                if isinstance(dev, vim.vm.device.VirtualCdrom):
                    cdrom_spec = vim.vm.device.VirtualDeviceSpec()
                    cdrom_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
                    cdrom_spec.device = dev

                    remote_backing = vim.vm.device.VirtualCdrom.RemotePassthroughBackingInfo()
                    remote_backing.deviceName = ""
                    cdrom_spec.device.backing = remote_backing

                    connectable = vim.vm.device.VirtualDevice.ConnectInfo()
                    connectable.startConnected = False
                    connectable.connected = False
                    connectable.allowGuestControl = True
                    cdrom_spec.device.connectable = connectable

                    device_changes.append(cdrom_spec)
                    if not unmount_all:
                        break

            if not device_changes:
                logger.info("esxi_no_cdrom_to_unmount", vm_id=vm_id)
                return True

            config_spec = vim.vm.ConfigSpec()
            config_spec.deviceChange = device_changes
            task = vm.ReconfigVM_Task(spec=config_spec)
            self._wait_for_task(task)
            return True

        try:
            await asyncio.to_thread(_unmount)
            logger.info("esxi_iso_unmounted", vm_id=vm_id)
            return True
        except (HypervisorError, VMNotFoundError):
            raise
        except Exception as e:
            raise VMOperationError(vm_id, "unmount_iso", str(e)) from e

    async def set_boot_order(self, vm_id: str, boot_order: list[str]) -> bool:
        """Configure l'ordre de boot d'une VM ESXi."""
        def _set_boot() -> bool:
            vm = self._get_vm_by_id(vm_id)
            boot_devices: list[Any] = []

            for device_type in boot_order:
                dt = device_type.lower()
                if dt in ("harddrive", "disk", "hdd"):
                    boot_devices.append(vim.vm.BootOptions.BootableDiskDevice(deviceKey=2000))
                elif dt in ("dvd", "cdrom", "cd"):
                    boot_devices.append(vim.vm.BootOptions.BootableCdromDevice())
                elif dt in ("network", "pxe", "nic"):
                    boot_devices.append(vim.vm.BootOptions.BootableEthernetDevice(deviceKey=4000))
                elif dt in ("floppy",):
                    boot_devices.append(vim.vm.BootOptions.BootableFloppyDevice())

            config_spec = vim.vm.ConfigSpec()
            config_spec.bootOptions = vim.vm.BootOptions()
            config_spec.bootOptions.bootOrder = boot_devices
            task = vm.ReconfigVM_Task(spec=config_spec)
            self._wait_for_task(task)
            return True

        try:
            await asyncio.to_thread(_set_boot)
            logger.info("esxi_boot_order_set", vm_id=vm_id, boot_order=boot_order)
            return True
        except (HypervisorError, VMNotFoundError):
            raise
        except Exception as e:
            raise VMOperationError(vm_id, "set_boot_order", str(e)) from e

    async def set_first_boot_device(self, vm_id: str, device_type: str = "HardDrive") -> bool:
        """Configure le premier périphérique de boot d'une VM ESXi."""
        return await self.set_boot_order(vm_id, [device_type])

    async def cleanup_post_install(self, vm_id: str) -> dict[str, bool]:
        """Nettoyage post-installation : démonte ISO, boot sur disque, vérifie Tools."""
        results: dict[str, bool] = {}

        try:
            results["unmount_iso"] = await self.unmount_iso(vm_id, unmount_all=True)
        except Exception as e:
            logger.error("esxi_cleanup_unmount_failed", vm_id=vm_id, error=str(e))
            results["unmount_iso"] = False

        try:
            results["set_boot_disk"] = await self.set_first_boot_device(vm_id, "HardDrive")
        except Exception as e:
            logger.error("esxi_cleanup_boot_failed", vm_id=vm_id, error=str(e))
            results["set_boot_disk"] = False

        try:
            results["guest_services"] = await self.enable_guest_services(vm_id)
        except Exception as e:
            logger.error("esxi_cleanup_guest_services_failed", vm_id=vm_id, error=str(e))
            results["guest_services"] = False

        logger.info("esxi_cleanup_post_install_done", vm_id=vm_id, results=results)
        return results

    # =========================================================================
    # Opérations invité (Guest Operations)
    # =========================================================================

    async def execute_in_vm(
        self,
        vm_id: str,
        script: str,
        vm_credentials: tuple[str, str],
        timeout: int = 300,
    ) -> PowerShellDirectResult:
        """Exécute un script dans une VM via GuestOperationsManager (nécessite VMware Tools)."""
        def _execute_guest() -> PowerShellDirectResult:
            vm = self._get_vm_by_id(vm_id)
            tools_status = vm.guest.toolsRunningStatus
            if tools_status != "guestToolsRunning":
                return PowerShellDirectResult(
                    success=False,
                    output=None,
                    error=f"VMware Tools non disponible (statut : {tools_status})",
                )

            content = self._si.RetrieveContent()
            process_mgr = content.guestOperationsManager.processManager
            username, password = vm_credentials
            guest_auth = vim.vm.guest.NamePasswordAuthentication(
                username=username, password=password, interactiveSession=False,
            )

            # Déterminer le shell selon l'OS invité
            guest_os_id = vm.config.guestId or ""
            is_windows = "win" in guest_os_id.lower()
            if is_windows:
                program_path = "cmd.exe"
                arguments = f"/c {script}"
            else:
                program_path = "/bin/bash"
                arguments = f"-c {script}"

            proc_spec = vim.vm.guest.ProcessManager.ProgramSpec(
                programPath=program_path, arguments=arguments,
            )

            try:
                pid = process_mgr.StartProgramInGuest(vm=vm, auth=guest_auth, spec=proc_spec)
            except vim.fault.InvalidGuestLogin:
                return PowerShellDirectResult(success=False, output=None, error="Identifiants VM invalides")
            except Exception as e:
                return PowerShellDirectResult(success=False, output=None, error=f"Erreur GuestOperations : {e}")

            # Attendre la fin du processus
            elapsed = 0
            while elapsed < timeout:
                try:
                    procs = process_mgr.ListProcessesInGuest(vm=vm, auth=guest_auth, pids=[pid])
                    if procs and procs[0].exitCode is not None:
                        exit_code = procs[0].exitCode
                        return PowerShellDirectResult(
                            success=(exit_code == 0),
                            output=f"PID {pid} terminé avec code {exit_code}",
                            error=None if exit_code == 0 else f"Code de sortie : {exit_code}",
                        )
                except Exception:
                    pass
                time.sleep(5)
                elapsed += 5

            return PowerShellDirectResult(success=False, output=None, error=f"Timeout après {timeout}s")

        try:
            return await asyncio.to_thread(_execute_guest)
        except (HypervisorError, VMNotFoundError):
            raise
        except Exception as e:
            return PowerShellDirectResult(success=False, output=None, error=f"Erreur inattendue : {e}")

    async def enable_guest_services(self, vm_id: str) -> bool:
        """Vérifie le statut des VMware Tools (équivalent des guest services Hyper-V)."""
        def _check_tools() -> bool:
            vm = self._get_vm_by_id(vm_id)
            return vm.guest.toolsRunningStatus == "guestToolsRunning"

        try:
            result = await asyncio.to_thread(_check_tools)
            logger.info("esxi_guest_services_check", vm_id=vm_id, tools_running=result)
            return result
        except (HypervisorError, VMNotFoundError):
            raise
        except Exception as e:
            raise VMOperationError(vm_id, "enable_guest_services", str(e)) from e

    async def wait_for_vm_ready(
        self,
        vm_id: str,
        vm_credentials: tuple[str, str] | None = None,
        timeout: int = 600,
        check_interval: int = 10,
    ) -> bool:
        """Attend qu'une VM ESXi soit prête (heartbeat green + optionnellement accès guest)."""
        def _wait() -> bool:
            elapsed = 0
            while elapsed < timeout:
                vm_ref = self._get_vm_by_id(vm_id)
                heartbeat = vm_ref.guestHeartbeatStatus
                if heartbeat == "green":
                    logger.info("esxi_vm_heartbeat_green", vm_id=vm_id, elapsed=elapsed)
                    return True
                logger.debug("esxi_waiting_for_vm", vm_id=vm_id, heartbeat=str(heartbeat), elapsed=elapsed)
                time.sleep(check_interval)
                elapsed += check_interval

            logger.warning("esxi_vm_ready_timeout", vm_id=vm_id, timeout=timeout)
            return False

        try:
            result = await asyncio.to_thread(_wait)
            if result and vm_credentials:
                try:
                    test_result = await self.execute_in_vm(vm_id, "echo ready", vm_credentials, timeout=30)
                    if not test_result.success:
                        logger.warning("esxi_vm_heartbeat_ok_but_exec_failed", vm_id=vm_id, error=test_result.error)
                        return False
                except Exception as e:
                    logger.warning("esxi_vm_exec_test_error", vm_id=vm_id, error=str(e))
                    return False
            return result
        except (HypervisorError, VMNotFoundError):
            raise
        except Exception as e:
            raise VMOperationError(vm_id, "wait_for_vm_ready", str(e)) from e

    # =========================================================================
    # Listing ISOs sur datastore
    # =========================================================================

    async def list_isos(self, path: str | None = None) -> list[dict[str, Any]]:
        """Liste les fichiers ISO disponibles sur le datastore."""
        def _list() -> list[dict[str, Any]]:
            self._ensure_connected()
            ds_name = self.iso_datastore or self.default_datastore
            search_path = path or self.iso_path or ""

            # Trouver le datastore
            ds = self._get_obj([vim.Datastore], ds_name)
            if not ds:
                logger.warning("esxi_iso_datastore_not_found", datastore=ds_name)
                return []

            # Rechercher les fichiers ISO
            search_spec = vim.host.DatastoreBrowser.SearchSpec()
            file_query = vim.host.DatastoreBrowser.IsoImageQuery()
            search_spec.query = [file_query]
            search_spec.matchPattern = ["*.iso", "*.ISO"]
            search_spec.details = vim.host.DatastoreBrowser.FileInfo.Details(
                fileType=True, fileSize=True, modification=True,
            )

            ds_path = f"[{ds_name}] {search_path}" if search_path else f"[{ds_name}]"
            try:
                task = ds.browser.SearchDatastoreSubFolders_Task(
                    datastorePath=ds_path, searchSpec=search_spec,
                )
                # Attendre la tâche
                import time as _time
                while task.info.state not in ("success", "error"):
                    _time.sleep(0.5)
                if task.info.state == "error":
                    logger.warning("esxi_iso_search_error", error=str(task.info.error))
                    return []

                results = []
                for folder_result in (task.info.result or []):
                    folder = folder_result.folderPath
                    for f in (folder_result.file or []):
                        size_bytes = f.fileSize or 0
                        results.append({
                            "name": f.path,
                            "full_path": f"{folder}{f.path}",
                            "size_bytes": size_bytes,
                            "size_gb": round(size_bytes / (1024**3), 2),
                            "last_modified": str(f.modification) if f.modification else "",
                            "directory": folder,
                        })
                return results
            except Exception as e:
                logger.warning("esxi_iso_search_error", error=str(e))
                return []

        try:
            return await asyncio.to_thread(_list)
        except Exception as e:
            logger.error("esxi_list_isos_error", error=str(e))
            return []

    # =========================================================================
    # Opérations sur les datastores
    # =========================================================================

    async def list_datastores(self) -> list[dict[str, Any]]:
        """Liste les datastores disponibles avec leurs capacités."""
        def _list() -> list[dict[str, Any]]:
            self._ensure_connected()
            datastores = self._get_all_objs([vim.Datastore])
            result = []
            for ds in datastores:
                try:
                    summary = ds.summary
                    capacity = summary.capacity or 0
                    free = summary.freeSpace or 0
                    result.append({
                        "name": summary.name,
                        "capacity_gb": round(capacity / (1024**3), 2),
                        "free_gb": round(free / (1024**3), 2),
                        "used_gb": round((capacity - free) / (1024**3), 2),
                        "percent_free": round((free / capacity * 100), 1) if capacity > 0 else 0,
                        "type": summary.type,  # VMFS, NFS, vsan
                        "accessible": summary.accessible,
                        "url": summary.url,
                    })
                except Exception as e:
                    logger.warning("esxi_datastore_info_error", ds=getattr(ds, 'name', '?'), error=str(e))
            return result

        try:
            return await asyncio.to_thread(_list)
        except Exception as e:
            logger.error("esxi_list_datastores_error", error=str(e))
            return []

    async def list_resource_pools(self) -> list[dict[str, Any]]:
        """Liste les resource pools disponibles."""
        def _list() -> list[dict[str, Any]]:
            self._ensure_connected()
            pools = self._get_all_objs([vim.ResourcePool])
            result = []
            for pool in pools:
                try:
                    config = pool.config
                    runtime = pool.runtime
                    result.append({
                        "name": pool.name,
                        "cpu_reservation_mhz": config.cpuAllocation.reservation if config else 0,
                        "memory_reservation_mb": config.memoryAllocation.reservation if config else 0,
                        "cpu_usage_mhz": runtime.cpu.overallUsage if runtime and runtime.cpu else 0,
                        "memory_usage_mb": runtime.memory.overallUsage // (1024*1024) if runtime and runtime.memory else 0,
                    })
                except Exception as e:
                    logger.warning("esxi_pool_info_error", error=str(e))
            return result

        try:
            return await asyncio.to_thread(_list)
        except Exception as e:
            logger.error("esxi_list_pools_error", error=str(e))
            return []

    async def upload_file_to_datastore(
        self, local_path: str, datastore_name: str, remote_path: str
    ) -> bool:
        """Upload un fichier local vers un datastore ESXi via HTTP PUT."""
        def _upload() -> bool:
            import requests
            import urllib.parse

            self._ensure_connected()

            # Construire l'URL pour l'upload HTTP
            # Format: https://host/folder/path?dcPath=datacenter&dsName=datastore
            dc = self._content.rootFolder.childEntity[0]
            dc_name = dc.name

            encoded_path = urllib.parse.quote(remote_path, safe='/')
            url = (
                f"https://{self.host}:{self.port}/folder/{encoded_path}"
                f"?dcPath={urllib.parse.quote(dc_name)}"
                f"&dsName={urllib.parse.quote(datastore_name)}"
            )

            # Récupérer le cookie de session
            cookie = self._si._stub.cookie
            cookie_name = cookie.split("=", 1)[0]
            cookie_value = cookie.split("=", 1)[1].split(";")[0]

            headers = {"Content-Type": "application/octet-stream"}
            cookies = {cookie_name: cookie_value}

            with open(local_path, "rb") as f:
                response = requests.put(
                    url, data=f, headers=headers, cookies=cookies,
                    verify=False, timeout=600,
                )

            if response.status_code in (200, 201):
                logger.info("esxi_file_uploaded", path=remote_path, datastore=datastore_name)
                return True
            else:
                raise HypervisorError(
                    f"Upload échoué ({response.status_code}): {response.text[:200]}"
                )

        return await asyncio.to_thread(_upload)

    async def upload_content_to_datastore(
        self, content: str | bytes, datastore_name: str, remote_path: str
    ) -> bool:
        """Upload du contenu texte/bytes vers un datastore ESXi."""
        def _upload() -> bool:
            import requests
            import urllib.parse

            self._ensure_connected()
            dc = self._content.rootFolder.childEntity[0]
            dc_name = dc.name

            encoded_path = urllib.parse.quote(remote_path, safe='/')
            url = (
                f"https://{self.host}:{self.port}/folder/{encoded_path}"
                f"?dcPath={urllib.parse.quote(dc_name)}"
                f"&dsName={urllib.parse.quote(datastore_name)}"
            )

            cookie = self._si._stub.cookie
            cookie_name = cookie.split("=", 1)[0]
            cookie_value = cookie.split("=", 1)[1].split(";")[0]

            data = content.encode("utf-8") if isinstance(content, str) else content
            headers = {"Content-Type": "application/octet-stream"}
            cookies = {cookie_name: cookie_value}

            response = requests.put(
                url, data=data, headers=headers, cookies=cookies,
                verify=False, timeout=120,
            )

            if response.status_code in (200, 201):
                return True
            raise HypervisorError(f"Upload échoué ({response.status_code})")

        return await asyncio.to_thread(_upload)

    async def delete_datastore_file(self, datastore_name: str, remote_path: str) -> bool:
        """Supprime un fichier sur un datastore."""
        def _delete() -> bool:
            self._ensure_connected()
            dc = self._content.rootFolder.childEntity[0]
            file_manager = self._content.fileManager
            full_path = f"[{datastore_name}] {remote_path}"
            task = file_manager.DeleteDatastoreFile_Task(name=full_path, datacenter=dc)
            self._wait_for_task(task)
            return True

        try:
            return await asyncio.to_thread(_delete)
        except Exception as e:
            logger.warning("esxi_delete_file_error", path=remote_path, error=str(e))
            return False

    async def mkdir_on_datastore(self, datastore_name: str, path: str) -> bool:
        """Crée un répertoire sur un datastore."""
        def _mkdir() -> bool:
            self._ensure_connected()
            dc = self._content.rootFolder.childEntity[0]
            file_manager = self._content.fileManager
            full_path = f"[{datastore_name}] {path}"
            try:
                file_manager.MakeDirectory(name=full_path, datacenter=dc, createParentDirectories=True)
            except vim.fault.FileAlreadyExists:
                pass  # OK si déjà existant
            return True

        try:
            return await asyncio.to_thread(_mkdir)
        except Exception as e:
            logger.warning("esxi_mkdir_error", path=path, error=str(e))
            return False

    async def check_disk_space(self, required_gb: float = 0, path: str | None = None) -> dict[str, Any]:
        """Vérifie l'espace disque sur le datastore par défaut."""
        datastores = await self.list_datastores()
        target = path or self.default_datastore

        for ds in datastores:
            if ds["name"] == target:
                if required_gb > 0 and ds["free_gb"] < required_gb:
                    raise HypervisorError(
                        f"Espace insuffisant sur {target}: {ds['free_gb']:.1f} Go libre, {required_gb:.0f} Go requis"
                    )
                return {
                    "drive_letter": ds["name"],
                    "free_gb": ds["free_gb"],
                    "total_gb": ds["capacity_gb"],
                    "used_gb": ds["used_gb"],
                    "percent_free": ds["percent_free"],
                }

        # Fallback: return first datastore
        if datastores:
            ds = datastores[0]
            return {"drive_letter": ds["name"], "free_gb": ds["free_gb"], "total_gb": ds["capacity_gb"], "used_gb": ds["used_gb"], "percent_free": ds["percent_free"]}
        return {"drive_letter": "unknown", "free_gb": 0, "total_gb": 0, "used_gb": 0, "percent_free": 0}

    async def ensure_paths_exist(self) -> None:
        """Crée les dossiers nécessaires sur le datastore."""
        ds = self.default_datastore
        await self.mkdir_on_datastore(ds, "vm-automation-temp")
        await self.mkdir_on_datastore(ds, "vm-automation-temp/seed-iso")
        await self.mkdir_on_datastore(ds, "vm-automation-temp/floppy")

    async def get_vm_network_summary(self, vm_id: str) -> dict[str, Any]:
        """Récupère un résumé réseau d'une VM (IP, MAC, hostname)."""
        def _get_net() -> dict[str, Any]:
            vm = self._get_vm_by_id(vm_id)
            result: dict[str, Any] = {"ip_addresses": [], "mac_addresses": [], "hostname": None}

            guest = vm.guest
            if not guest:
                return result

            result["hostname"] = guest.hostName

            if guest.net:
                for nic in guest.net:
                    if nic.macAddress:
                        result["mac_addresses"].append(nic.macAddress)
                    if nic.ipAddress:
                        for ip in nic.ipAddress:
                            if not ip.startswith("fe80:") and not ip.startswith("127."):
                                result["ip_addresses"].append(ip)
            return result

        try:
            return await asyncio.to_thread(_get_net)
        except Exception as e:
            logger.warning("esxi_get_network_summary_error", vm_id=vm_id, error=str(e))
            return {"ip_addresses": [], "mac_addresses": [], "hostname": None}

    # =========================================================================
    # Nettoyage
    # =========================================================================

    async def cleanup(self) -> None:
        """Libère la connexion vSphere."""
        def _cleanup() -> None:
            if self._si is not None:
                try:
                    Disconnect(self._si)
                    logger.info("esxi_disconnected", host=self.host)
                except Exception as e:
                    logger.warning(
                        "esxi_disconnect_error",
                        host=self.host,
                        error=str(e),
                    )
                finally:
                    self._si = None
                    self._content = None

        await asyncio.to_thread(_cleanup)
