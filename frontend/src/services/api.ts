import axios from 'axios';
import type { AxiosError, AxiosInstance } from 'axios';
import type {
  Hypervisor,
  VirtualMachine,
  VMDetails,
  VMScreenshot,
  OSTemplate,
  Deployment,
  DeploymentConfig,
  DashboardStats,
  HealthCheck,
  VirtualSwitch,
  CreateSwitchRequest,
  PhysicalAdapter,
  StorageLocation,
  SoftwarePackage,
  SoftwareCategory_Info,
  SoftwareProfile,
  SoftwareList,
  ProfileList,
  AdminUser,
  CreateUserRequest,
  UpdateUserRequest,
  ResetPasswordRequest,
  AuditLogList,
  SoftwareInventory,
} from '../types';

// Configuration de base
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

// Instance Axios configurée
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 60000,
});

// Intercepteur pour les erreurs
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const errorData = error.response?.data as any;
    const message = errorData?.detail || errorData?.message || errorData?.error || error.message;
    console.error('API Error:', message);

    // Token expiré ou invalide → forcer reconnexion
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      // Redirect vers login si on n'y est pas déjà
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login';
      }
    }

    return Promise.reject(error);
  }
);

// ============================================
// Health Check
// ============================================

export const healthApi = {
  check: async (): Promise<HealthCheck> => {
    // Health est sur /health (racine, sans préfixe /api/v1)
    const response = await axios.get<HealthCheck>('/health', { timeout: 10000 });
    return response.data;
  },
};

// ============================================
// Types pour les réponses paginées
// ============================================

interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// Type pour les fichiers ISO
export interface ISOInfo {
  name: string;
  full_path: string;
  size_bytes: number;
  size_gb: number;
  last_modified: string;
  directory: string;
}

// ============================================
// Hypervisors API
// ============================================

// Type backend pour hypervisor
interface HypervisorBackend {
  id: string;
  name: string;
  type: string;
  host: string;
  port: number;
  use_ssl: boolean;
  username: string;
  is_active: boolean;
  vm_count: number;
  // VMware-specific
  datacenter?: string;
  cluster?: string;
  default_datastore?: string;
  default_resource_pool?: string;
  created_at: string;
  updated_at: string | null;
}

// Mapper backend vers frontend
function mapHypervisor(h: HypervisorBackend): Hypervisor {
  return {
    id: h.id,
    name: h.name,
    type: (h.type || 'hyperv') as 'hyperv' | 'vmware',
    host: h.host,
    port: h.port,
    username: h.username,
    is_active: h.is_active,
    vm_count: h.vm_count ?? 0,
    // VMware-specific
    datacenter: h.datacenter,
    cluster: h.cluster,
    default_datastore: h.default_datastore,
    default_resource_pool: h.default_resource_pool,
    created_at: h.created_at,
    updated_at: h.updated_at || h.created_at,
  };
}

export const hypervisorsApi = {
  list: async (): Promise<Hypervisor[]> => {
    const response = await apiClient.get<PaginatedResponse<HypervisorBackend>>('/hypervisors');
    return response.data.items.map(mapHypervisor);
  },

  get: async (id: string): Promise<Hypervisor> => {
    const response = await apiClient.get<HypervisorBackend>(`/hypervisors/${id}`);
    return mapHypervisor(response.data);
  },

  create: async (data: Partial<Hypervisor>): Promise<Hypervisor> => {
    const defaultPort = data.type === 'vmware' ? 443 : 5985;
    const payload: Record<string, unknown> = {
      name: data.name,
      type: data.type,
      host: data.host,
      port: data.port || defaultPort,
      use_ssl: data.type === 'vmware' ? true : false,
      username: data.username,
      password: (data as { password?: string }).password,
    };
    // VMware-specific fields
    if (data.type === 'vmware') {
      if (data.datacenter) payload.datacenter = data.datacenter;
      if (data.cluster) payload.cluster = data.cluster;
      if (data.default_datastore) payload.default_datastore = data.default_datastore;
      if (data.default_resource_pool) payload.default_resource_pool = data.default_resource_pool;
    }
    const response = await apiClient.post<HypervisorBackend>('/hypervisors', payload);
    return mapHypervisor(response.data);
  },

  update: async (id: string, data: Partial<Hypervisor>): Promise<Hypervisor> => {
    const payload: Record<string, unknown> = {};
    if (data.name) payload.name = data.name;
    if (data.type) payload.type = data.type;
    if (data.host) payload.host = data.host;
    if (data.port) payload.port = data.port;
    if (data.username) payload.username = data.username;
    if ((data as { password?: string }).password) payload.password = (data as { password?: string }).password;
    // VMware-specific fields
    if (data.type === 'vmware') {
      payload.datacenter = data.datacenter || undefined;
      payload.cluster = data.cluster || undefined;
      payload.default_datastore = data.default_datastore || undefined;
      payload.default_resource_pool = data.default_resource_pool || undefined;
    }

    const response = await apiClient.patch<HypervisorBackend>(`/hypervisors/${id}`, payload);
    return mapHypervisor(response.data);
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/hypervisors/${id}`);
  },

  testConnection: async (id: string): Promise<{ connected: boolean; message: string }> => {
    const response = await apiClient.post<{ success: boolean; message: string }>(`/hypervisors/${id}/test`);
    return { connected: response.data.success, message: response.data.message };
  },

  // Switches
  listSwitches: async (id: string): Promise<VirtualSwitch[]> => {
    const response = await apiClient.get<VirtualSwitch[]>(`/hypervisors/${id}/switches`);
    return response.data;
  },

  createSwitch: async (hypervisorId: string, data: CreateSwitchRequest): Promise<VirtualSwitch> => {
    const response = await apiClient.post<VirtualSwitch>(`/hypervisors/${hypervisorId}/switches`, data);
    return response.data;
  },

  deleteSwitch: async (hypervisorId: string, switchName: string): Promise<void> => {
    await apiClient.delete(`/hypervisors/${hypervisorId}/switches/${encodeURIComponent(switchName)}`);
  },

  listPhysicalAdapters: async (id: string): Promise<PhysicalAdapter[]> => {
    const response = await apiClient.get<PhysicalAdapter[]>(`/hypervisors/${id}/physical-adapters`);
    return response.data;
  },

  // Lister les fichiers ISO disponibles sur l'hyperviseur
  listIsos: async (id: string, path?: string): Promise<ISOInfo[]> => {
    const params = path ? { path } : {};
    const response = await apiClient.get<ISOInfo[]>(`/hypervisors/${id}/isos`, { params });
    return response.data;
  },

  // Synchronisation des VMs avec Hyper-V
  syncVms: async (
    id: string,
    options?: {
      import_new?: boolean;
      update_existing?: boolean;
      mark_missing?: boolean;
    }
  ): Promise<{
    success: boolean;
    imported: number;
    updated: number;
    marked_missing: number;
    errors: string[];
    details?: {
      imported_vms: { name: string; hyperv_id: string; state: string }[];
      updated_vms: { name: string; old_state: string; new_state: string }[];
      missing_vms: { name: string; db_id: string }[];
    };
  }> => {
    const response = await apiClient.post(`/hypervisors/${id}/sync`, options || {}, {
      timeout: 60000, // 60s pour la synchronisation
    });
    return response.data;
  },

  // Lister les VMs directement depuis Hyper-V (non filtrées par la DB)
  listHypervisorVms: async (id: string): Promise<{
    id: string;
    name: string;
    state: string;
    cpu_count: number;
    ram_gb: number;
    uptime?: string;
    status?: string;
    notes?: string;
    generation?: number;
    path?: string;
  }[]> => {
    const response = await apiClient.get(`/hypervisors/${id}/vms`);
    return response.data;
  },

  // Lister les emplacements de stockage disponibles
  getStorageLocations: async (id: string, minFreeGb = 50): Promise<StorageLocation[]> => {
    const response = await apiClient.get<StorageLocation[]>(`/hypervisors/${id}/storage-locations`, {
      params: { min_free_gb: minFreeGb },
    });
    return response.data;
  },

  // VMware-specific endpoints
  listDatastores: async (hypervisorId: string): Promise<{ name: string; capacity_gb: number; free_gb: number; type: string }[]> => {
    const response = await apiClient.get(`/hypervisors/${hypervisorId}/datastores`);
    return response.data;
  },

  listResourcePools: async (hypervisorId: string): Promise<{ name: string; cpu_limit?: number; memory_limit_gb?: number }[]> => {
    const response = await apiClient.get(`/hypervisors/${hypervisorId}/resource-pools`);
    return response.data;
  },
};

// ============================================
// Virtual Machines API
// ============================================

// Type backend pour VM
interface VMBackend {
  id: string;
  name: string;
  hypervisor_id: string;
  hypervisor_vm_id: string | null;
  cpu_count: number;
  ram_gb: number;
  disk_gb: number;
  state: string;
  ip_address: string | null;
  network_switch: string | null;
  vlan_id: number | null;
  os_template_id: string | null;
  os_type?: string;
  created_at: string;
  updated_at: string | null;
}

// Mapper backend vers frontend
function mapVM(vm: VMBackend): VirtualMachine {
  return {
    id: vm.id,
    name: vm.name,
    hypervisor_id: vm.hypervisor_id,
    state: vm.state as VirtualMachine['state'],
    cpu_count: vm.cpu_count,
    ram_gb: vm.ram_gb,
    disk_gb: vm.disk_gb,
    os_type: vm.os_type || undefined,
    ip_address: vm.ip_address || undefined,
    network_switch: vm.network_switch || undefined,
    vlan_id: vm.vlan_id || undefined,
    created_at: vm.created_at,
    updated_at: vm.updated_at || vm.created_at,
  };
}

// Type pour l'action VM
interface VMActionResponse {
  success: boolean;
  message: string;
  vm_id: string;
  state: string;
}

export const vmsApi = {
  list: async (hypervisorId?: string): Promise<VirtualMachine[]> => {
    const params: Record<string, string> = {};
    if (hypervisorId) params.hypervisor_id = hypervisorId;
    const response = await apiClient.get<PaginatedResponse<VMBackend>>('/vms', { params });
    return response.data.items.map(mapVM);
  },

  get: async (id: string): Promise<VirtualMachine> => {
    const response = await apiClient.get<VMBackend>(`/vms/${id}`);
    return mapVM(response.data);
  },

  start: async (id: string): Promise<VirtualMachine> => {
    const response = await apiClient.post<VMActionResponse>(`/vms/${id}/start`);
    // Refetch pour avoir l'état complet
    return vmsApi.get(response.data.vm_id);
  },

  stop: async (id: string, force = false): Promise<VirtualMachine> => {
    const response = await apiClient.post<VMActionResponse>(`/vms/${id}/stop`, null, { params: { force } });
    return vmsApi.get(response.data.vm_id);
  },

  restart: async (id: string): Promise<VirtualMachine> => {
    const response = await apiClient.post<VMActionResponse>(`/vms/${id}/restart`);
    return vmsApi.get(response.data.vm_id);
  },

  delete: async (id: string, options?: { deleteDisks?: boolean; force?: boolean }): Promise<void> => {
    await apiClient.delete(`/vms/${id}`, {
      params: {
        delete_disks: options?.deleteDisks ?? false,
        force: options?.force ?? false,
      },
    });
  },

  getDetails: async (id: string): Promise<VMDetails> => {
    const response = await apiClient.get<VMDetails>(`/vms/${id}/details`);
    return response.data;
  },

  getScreenshot: async (id: string, width = 800, height = 600): Promise<VMScreenshot> => {
    const response = await apiClient.get<VMScreenshot>(`/vms/${id}/screenshot`, {
      params: { width, height },
      timeout: 15000, // Screenshot peut prendre du temps
    });
    return response.data;
  },

  getRdpUrl: (id: string, username?: string): string => {
    const params = username ? `?username=${encodeURIComponent(username)}` : '';
    return `${API_BASE_URL}/vms/${id}/rdp${params}`;
  },

  getSoftwareInventory: async (id: string): Promise<SoftwareInventory> => {
    const response = await apiClient.get<SoftwareInventory>(`/vms/${id}/software-inventory`);
    return response.data;
  },
};

// ============================================
// Templates API
// ============================================

// Type backend pour template
interface TemplateBackend {
  id: string;
  name: string;
  os_family: string;
  os_type: string;
  architecture: string;
  iso_path: string;
  min_cpu: number;
  min_ram_gb: number;
  min_disk_gb: number;
  install_locale: string;
  is_active: boolean;
  created_at: string;
  updated_at: string | null;
}

// Mapper backend vers frontend
function mapTemplate(t: TemplateBackend): OSTemplate {
  return {
    id: t.id,
    name: t.name,
    os_family: t.os_family as 'windows' | 'linux',
    os_type: t.os_type,
    description: undefined,
    iso_path: t.iso_path,
    min_cpu: t.min_cpu,
    min_ram_gb: t.min_ram_gb,
    min_disk_gb: t.min_disk_gb,
    install_locale: t.install_locale,
    updated_at: t.updated_at || undefined,
    created_at: t.created_at,
  };
}

export const templatesApi = {
  list: async (): Promise<OSTemplate[]> => {
    const response = await apiClient.get<PaginatedResponse<TemplateBackend>>('/templates');
    return response.data.items.map(mapTemplate);
  },

  get: async (id: string): Promise<OSTemplate> => {
    const response = await apiClient.get<TemplateBackend>(`/templates/${id}`);
    return mapTemplate(response.data);
  },

  create: async (data: Partial<OSTemplate>): Promise<OSTemplate> => {
    const payload = {
      name: data.name,
      os_family: data.os_family,
      os_type: data.os_type,
      architecture: 'x64',
      iso_path: data.iso_path || '/path/to/iso',
      min_cpu: data.min_cpu || 2,
      min_ram_gb: data.min_ram_gb || 4,
      min_disk_gb: data.min_disk_gb || 60,
      install_locale: data.install_locale || 'fr-FR',
    };
    const response = await apiClient.post<TemplateBackend>('/templates', payload);
    return mapTemplate(response.data);
  },

  update: async (id: string, data: Partial<OSTemplate>): Promise<OSTemplate> => {
    const payload: Record<string, unknown> = {};
    if (data.name) payload.name = data.name;
    if (data.iso_path) payload.iso_path = data.iso_path;
    if (data.min_cpu) payload.min_cpu = data.min_cpu;
    if (data.min_ram_gb) payload.min_ram_gb = data.min_ram_gb;
    if (data.min_disk_gb) payload.min_disk_gb = data.min_disk_gb;
    if (data.install_locale) payload.install_locale = data.install_locale;
    
    const response = await apiClient.patch<TemplateBackend>(`/templates/${id}`, payload);
    return mapTemplate(response.data);
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/templates/${id}`);
  },
};

// ============================================
// Deployments API
// ============================================

// Type backend pour deployment
interface DeploymentBackend {
  id: string;
  vm_name: string;
  hypervisor_id: string;
  os_template_id: string;
  vm_id: string | null;
  status: string;
  progress: number;
  current_step: string | null;
  error_message: string | null;
  config: Record<string, unknown>;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

// Mapper backend vers frontend
function mapDeployment(d: DeploymentBackend): Deployment {
  return {
    id: d.id,
    vm_name: d.vm_name,
    name: d.vm_name,  // Alias pour l'affichage
    hypervisor_id: d.hypervisor_id,
    os_template_id: d.os_template_id,
    vm_id: d.vm_id || undefined,
    status: d.status as Deployment['status'],
    progress: d.progress ?? 0,  // Utilise la progression du backend
    current_step: d.current_step || undefined,
    error_message: d.error_message || undefined,
    config: {
      vm_name: d.vm_name,
      cpu_count: (d.config.cpu_count as number) || 2,
      ram_gb: (d.config.ram_gb as number) || 4,
      disk_gb: (d.config.disk_gb as number) || 60,
      vhdx_path: d.config.vhdx_path as string | undefined,
      network_switch: d.config.network_switch as string | undefined,
      hostname: d.config.hostname as string | undefined,
      admin_password: d.config.admin_password as string | undefined,
      domain_join: d.config.domain_join as DeploymentConfig['domain_join'],
      ip_config: d.config.ip_config as DeploymentConfig['ip_config'],
      services: d.config.services as DeploymentConfig['services'],
      security: d.config.security as DeploymentConfig['security'],
      software_profile: d.config.software_profile as string | undefined,
      packages: d.config.packages as string[] | undefined,
      package_configs: d.config.package_configs as Record<string, Record<string, unknown>> | undefined,
      enable_windows_update: d.config.enable_windows_update as boolean | undefined,
      post_install_commands: d.config.post_install_commands as string[] | undefined,
      ssh_keys: d.config.ssh_keys as string[] | undefined,
      extra_packages: d.config.extra_packages as string[] | undefined,
      post_commands: d.config.post_commands as string[] | undefined,
      network: d.config.network as DeploymentConfig['network'],
    },
    created_at: d.created_at,
    updated_at: d.completed_at || d.started_at || d.created_at,
  };
}

export const deploymentsApi = {
  list: async (status?: string): Promise<Deployment[]> => {
    const params: Record<string, string> = {};
    if (status) params.status = status;
    const response = await apiClient.get<PaginatedResponse<DeploymentBackend>>('/deployments', { params });
    return response.data.items.map(mapDeployment);
  },

  get: async (id: string): Promise<Deployment> => {
    const response = await apiClient.get<DeploymentBackend>(`/deployments/${id}`);
    return mapDeployment(response.data);
  },

  create: async (data: {
    vm_name: string;
    hypervisor_id: string;
    os_template_id: string;
    config: DeploymentConfig;
  }): Promise<Deployment> => {
    const payload: Record<string, unknown> = {
      vm_name: data.vm_name,
      hypervisor_id: data.hypervisor_id,
      os_template_id: data.os_template_id,
      cpu_count: data.config.cpu_count,
      ram_gb: data.config.ram_gb,
      disk_gb: data.config.disk_gb,
      hostname: data.config.hostname,
      admin_password: data.config.admin_password,
      network_switch: data.config.network_switch,
      vhdx_path: data.config.vhdx_path, // Emplacement personnalisé du VHDX
      ip_config: data.config.ip_config,
      domain_join: data.config.domain_join,
      // Services (RDP, WinRM, SSH)
      services: data.config.services,
      // Sécurité
      security: data.config.security,
      // Logiciels
      software_profile: data.config.software_profile,
      packages: data.config.packages,
      // Windows Update
      enable_windows_update: data.config.enable_windows_update,
      // Commandes post-install personnalisées
      post_install_commands: data.config.post_install_commands,
    };
    const response = await apiClient.post<DeploymentBackend>('/deployments', payload);
    return mapDeployment(response.data);
  },

  cancel: async (id: string): Promise<Deployment> => {
    const response = await apiClient.post<DeploymentBackend>(`/deployments/${id}/cancel`);
    return mapDeployment(response.data);
  },

  retry: async (id: string): Promise<Deployment> => {
    const response = await apiClient.post<DeploymentBackend>(`/deployments/${id}/start`);
    return mapDeployment(response.data);
  },

  resume: async (id: string): Promise<Deployment> => {
    const response = await apiClient.post<DeploymentBackend>(`/deployments/${id}/resume`);
    return mapDeployment(response.data);
  },

  getLogs: async (id: string): Promise<Deployment['logs']> => {
    interface LogBackend {
      id: string;
      step: string;
      message: string;
      level: string;
      details: Record<string, unknown>;
      created_at: string;
    }
    const response = await apiClient.get<LogBackend[]>(`/deployments/${id}/logs`);
    return response.data.map(log => ({
      id: log.id,
      deployment_id: id,
      step: log.step,
      level: log.level as 'debug' | 'info' | 'warning' | 'error',
      message: log.message,
      details: log.details || undefined,
      created_at: log.created_at,
    }));
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/deployments/${id}`);
  },

  // Approval workflow
  listPendingApprovals: async (): Promise<Deployment[]> => {
    const response = await apiClient.get<DeploymentBackend[]>('/deployments/pending-approval');
    return response.data.map(mapDeployment);
  },

  approve: async (id: string, note?: string): Promise<Deployment> => {
    const response = await apiClient.post<DeploymentBackend>(`/deployments/${id}/approve`, { note, auto_start: true });
    return mapDeployment(response.data);
  },

  reject: async (id: string, note: string): Promise<Deployment> => {
    const response = await apiClient.post<DeploymentBackend>(`/deployments/${id}/reject`, { note });
    return mapDeployment(response.data);
  },

  // Audit log
  getAuditLog: async (params?: { page?: number; page_size?: number; action?: string; username?: string }): Promise<AuditLogList> => {
    const response = await apiClient.get<AuditLogList>('/deployments/audit-log', { params });
    return response.data;
  },
};

// ============================================
// Dashboard / Stats API
// ============================================

export const dashboardApi = {
  getStats: async (): Promise<DashboardStats> => {
    try {
      // Stats disponibles via /realtime/stats
      const response = await apiClient.get<{
        hypervisors: { total: number };
        virtual_machines: { total: number; running: number; by_status: Record<string, number> };
        deployments: { total: number; in_progress: number; by_status: Record<string, number> };
      }>('/realtime/stats');
      
      const data = response.data;
      return {
        total_vms: data.virtual_machines.total,
        running_vms: data.virtual_machines.running,
        stopped_vms: data.virtual_machines.by_status?.stopped || 0,
        total_hypervisors: data.hypervisors.total,
        active_deployments: data.deployments.in_progress,
        completed_deployments: data.deployments.by_status?.completed || 0,
        failed_deployments: data.deployments.by_status?.failed || 0,
      };
    } catch {
      // Retourne des stats vides si l'API n'existe pas encore
      return {
        total_vms: 0,
        running_vms: 0,
        stopped_vms: 0,
        total_hypervisors: 0,
        active_deployments: 0,
        completed_deployments: 0,
        failed_deployments: 0,
      };
    }
  },
};

// ============================================
// Software Catalog API (Marketplace)
// ============================================

export const softwareApi = {
  // Lister les logiciels avec filtres
  list: async (params?: {
    page?: number;
    page_size?: number;
    category?: string;
    os_family?: string;
    search?: string;
    featured_only?: boolean;
    active_only?: boolean;
  }): Promise<SoftwareList> => {
    const response = await apiClient.get<SoftwareList>('/software-catalog', { params });
    return response.data;
  },

  // Obtenir un logiciel par ID
  get: async (id: string): Promise<SoftwarePackage> => {
    const response = await apiClient.get<SoftwarePackage>(`/software-catalog/${id}`);
    return response.data;
  },

  // Obtenir un logiciel par nom
  getByName: async (name: string): Promise<SoftwarePackage> => {
    const response = await apiClient.get<SoftwarePackage>(`/software-catalog/by-name/${name}`);
    return response.data;
  },

  // Lister les catégories
  getCategories: async (): Promise<SoftwareCategory_Info[]> => {
    const response = await apiClient.get<SoftwareCategory_Info[]>('/software-catalog/categories');
    return response.data;
  },

  // Lister les logiciels en vedette
  getFeatured: async (limit = 10): Promise<SoftwarePackage[]> => {
    const response = await apiClient.get<SoftwarePackage[]>('/software-catalog/featured', {
      params: { limit },
    });
    return response.data;
  },

  // Lister les profils
  getProfiles: async (): Promise<ProfileList> => {
    const response = await apiClient.get<ProfileList>('/software-catalog/profiles');
    return response.data;
  },

  // Obtenir un profil par nom
  getProfile: async (name: string): Promise<SoftwareProfile> => {
    const response = await apiClient.get<SoftwareProfile>(`/software-catalog/profiles/${name}`);
    return response.data;
  },

  // Initialiser le catalogue (seed)
  seedCatalog: async (): Promise<{ created: number; skipped: number }> => {
    const response = await apiClient.post<{ created: number; skipped: number }>('/software-catalog/seed');
    return response.data;
  },
};

// ============================================
// VNC API
// ============================================

export const vncApi = {
  installVNC: (vmId: string, config?: { port?: number; username?: string }) =>
    apiClient.post(`/vms/${vmId}/vnc/install`, config).then(r => r.data),

  checkStatus: (vmId: string, port?: number) =>
    apiClient.get(`/vms/${vmId}/vnc/status`, { params: { port } }).then(r => r.data),

  listSessions: () =>
    apiClient.get('/vnc/sessions').then(r => r.data),
};

// ============================================
// Admin - Gestion des utilisateurs
// ============================================

export const adminApi = {
  // Lister tous les utilisateurs
  listUsers: async (): Promise<AdminUser[]> => {
    const response = await apiClient.get<AdminUser[]>('/auth/admin/users');
    return response.data;
  },

  // Récupérer un utilisateur
  getUser: async (userId: string): Promise<AdminUser> => {
    const response = await apiClient.get<AdminUser>(`/auth/admin/users/${userId}`);
    return response.data;
  },

  // Créer un utilisateur
  createUser: async (data: CreateUserRequest): Promise<AdminUser> => {
    const response = await apiClient.post<AdminUser>('/auth/admin/users', data);
    return response.data;
  },

  // Modifier un utilisateur
  updateUser: async (userId: string, data: UpdateUserRequest): Promise<AdminUser> => {
    const response = await apiClient.patch<AdminUser>(`/auth/admin/users/${userId}`, data);
    return response.data;
  },

  // Supprimer un utilisateur
  deleteUser: async (userId: string): Promise<void> => {
    await apiClient.delete(`/auth/admin/users/${userId}`);
  },

  // Réinitialiser le mot de passe
  resetPassword: async (userId: string, data: ResetPasswordRequest): Promise<void> => {
    await apiClient.post(`/auth/admin/users/${userId}/reset-password`, data);
  },
};

// Export de l'instance pour usage avancé
export { apiClient };
