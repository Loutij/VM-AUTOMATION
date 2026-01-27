import axios from 'axios';
import type { AxiosError, AxiosInstance } from 'axios';
import type {
  Hypervisor,
  VirtualMachine,
  OSTemplate,
  Deployment,
  DeploymentConfig,
  DashboardStats,
  HealthCheck,
  VirtualSwitch,
  CreateSwitchRequest,
  PhysicalAdapter,
} from '../types';

// Configuration de base
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

// Instance Axios configurée
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

// Intercepteur pour les erreurs
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const message = (error.response?.data as { detail?: string })?.detail || error.message;
    console.error('API Error:', message);
    return Promise.reject(error);
  }
);

// Helper pour retry avec backoff (exporté pour usage externe)
export async function withRetry<T>(
  fn: () => Promise<T>,
  retries = 3,
  delay = 1000
): Promise<T> {
  try {
    return await fn();
  } catch (error) {
    if (retries > 0) {
      await new Promise((resolve) => setTimeout(resolve, delay));
      return withRetry(fn, retries - 1, Math.min(delay * 2, 30000));
    }
    throw error;
  }
}

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

// ============================================
// Hypervisors API
// ============================================

// Type backend pour hypervisor
interface HypervisorBackend {
  id: string;
  name: string;
  hypervisor_type: string;
  host: string;
  port: number;
  use_ssl: boolean;
  username: string;
  is_active: boolean;
  created_at: string;
  updated_at: string | null;
}

// Mapper backend vers frontend
function mapHypervisor(h: HypervisorBackend): Hypervisor {
  return {
    id: h.id,
    name: h.name,
    type: h.hypervisor_type as 'hyperv' | 'vmware',
    host: h.host,
    port: h.port,
    username: h.username,
    is_connected: h.is_active,
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
    const payload = {
      name: data.name,
      hypervisor_type: data.type,
      host: data.host,
      port: data.port || 5985,
      use_ssl: false,
      username: data.username,
      password: (data as { password?: string }).password,
    };
    const response = await apiClient.post<HypervisorBackend>('/hypervisors', payload);
    return mapHypervisor(response.data);
  },

  update: async (id: string, data: Partial<Hypervisor>): Promise<Hypervisor> => {
    const payload: Record<string, unknown> = {};
    if (data.name) payload.name = data.name;
    if (data.host) payload.host = data.host;
    if (data.port) payload.port = data.port;
    if (data.username) payload.username = data.username;
    if ((data as { password?: string }).password) payload.password = (data as { password?: string }).password;
    
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
  os_template_id: string | null;
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
    memory_mb: vm.ram_gb * 1024,
    disk_size_gb: vm.disk_gb,
    ip_address: vm.ip_address || undefined,
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

  delete: async (id: string, deleteDisks = false): Promise<void> => {
    await apiClient.delete(`/vms/${id}`, { params: { delete_disks: deleteDisks } });
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
    os_version: t.os_type,
    description: undefined,
    iso_path: t.iso_path,
    default_cpu: t.min_cpu,
    default_memory_mb: t.min_ram_gb * 1024,
    default_disk_gb: t.min_disk_gb,
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
      os_type: data.os_version,
      architecture: 'x64',
      iso_path: data.iso_path || '/path/to/iso',
      min_cpu: data.default_cpu || 2,
      min_ram_gb: Math.ceil((data.default_memory_mb || 4096) / 1024),
      min_disk_gb: data.default_disk_gb || 60,
    };
    const response = await apiClient.post<TemplateBackend>('/templates', payload);
    return mapTemplate(response.data);
  },

  update: async (id: string, data: Partial<OSTemplate>): Promise<OSTemplate> => {
    const payload: Record<string, unknown> = {};
    if (data.name) payload.name = data.name;
    if (data.iso_path) payload.iso_path = data.iso_path;
    if (data.default_cpu) payload.min_cpu = data.default_cpu;
    if (data.default_memory_mb) payload.min_ram_gb = Math.ceil(data.default_memory_mb / 1024);
    if (data.default_disk_gb) payload.min_disk_gb = data.default_disk_gb;
    
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
  current_step: string | null;
  error_message: string | null;
  config: Record<string, unknown>;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

// Mapper backend vers frontend
function mapDeployment(d: DeploymentBackend): Deployment {
  // Calculer la progression basée sur le statut
  const progressMap: Record<string, number> = {
    pending: 0,
    creating_vm: 20,
    installing_os: 50,
    post_install: 75,
    installing_software: 90,
    completed: 100,
    failed: 0,
    cancelled: 0,
  };
  
  return {
    id: d.id,
    name: d.vm_name,
    hypervisor_id: d.hypervisor_id,
    template_id: d.os_template_id,
    vm_id: d.vm_id || undefined,
    status: d.status as Deployment['status'],
    progress: progressMap[d.status] || 0,
    error_message: d.error_message || undefined,
    config: {
      vm_name: d.vm_name,
      cpu_count: (d.config.cpu_count as number) || 2,
      memory_mb: ((d.config.ram_gb as number) || 4) * 1024,
      disk_size_gb: (d.config.disk_gb as number) || 60,
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
    name: string;
    hypervisor_id: string;
    template_id: string;
    config: DeploymentConfig;
  }): Promise<Deployment> => {
    const payload = {
      vm_name: data.name,
      hypervisor_id: data.hypervisor_id,
      template_id: data.template_id,
      cpu_count: data.config.cpu_count,
      ram_gb: Math.ceil(data.config.memory_mb / 1024),
      disk_gb: data.config.disk_size_gb,
      hostname: data.config.hostname,
      admin_password: data.config.admin_password,
      network_switch: data.config.network_switch,
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
      status: log.level as 'info' | 'success' | 'warning' | 'error',
      message: log.message,
      created_at: log.created_at,
    }));
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/deployments/${id}`);
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

// Export de l'instance pour usage avancé
export { apiClient };
