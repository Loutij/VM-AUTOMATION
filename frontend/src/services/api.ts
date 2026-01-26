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
} from '../types';

// Configuration de base
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

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

// Helper pour retry avec backoff
async function withRetry<T>(
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
    const response = await apiClient.get<HealthCheck>('/health');
    return response.data;
  },
};

// ============================================
// Hypervisors API
// ============================================

export const hypervisorsApi = {
  list: async (): Promise<Hypervisor[]> => {
    const response = await apiClient.get<Hypervisor[]>('/hypervisors');
    return response.data;
  },

  get: async (id: string): Promise<Hypervisor> => {
    const response = await apiClient.get<Hypervisor>(`/hypervisors/${id}`);
    return response.data;
  },

  create: async (data: Partial<Hypervisor>): Promise<Hypervisor> => {
    const response = await apiClient.post<Hypervisor>('/hypervisors', data);
    return response.data;
  },

  update: async (id: string, data: Partial<Hypervisor>): Promise<Hypervisor> => {
    const response = await apiClient.put<Hypervisor>(`/hypervisors/${id}`, data);
    return response.data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/hypervisors/${id}`);
  },

  testConnection: async (id: string): Promise<{ connected: boolean; message: string }> => {
    const response = await apiClient.post(`/hypervisors/${id}/test`);
    return response.data;
  },
};

// ============================================
// Virtual Machines API
// ============================================

export const vmsApi = {
  list: async (hypervisorId?: string): Promise<VirtualMachine[]> => {
    const params = hypervisorId ? { hypervisor_id: hypervisorId } : {};
    const response = await apiClient.get<VirtualMachine[]>('/vms', { params });
    return response.data;
  },

  get: async (id: string): Promise<VirtualMachine> => {
    const response = await apiClient.get<VirtualMachine>(`/vms/${id}`);
    return response.data;
  },

  start: async (id: string): Promise<VirtualMachine> => {
    const response = await apiClient.post<VirtualMachine>(`/vms/${id}/start`);
    return response.data;
  },

  stop: async (id: string, force = false): Promise<VirtualMachine> => {
    const response = await apiClient.post<VirtualMachine>(`/vms/${id}/stop`, { force });
    return response.data;
  },

  restart: async (id: string): Promise<VirtualMachine> => {
    const response = await apiClient.post<VirtualMachine>(`/vms/${id}/restart`);
    return response.data;
  },

  delete: async (id: string, deleteDisks = false): Promise<void> => {
    await apiClient.delete(`/vms/${id}`, { params: { delete_disks: deleteDisks } });
  },
};

// ============================================
// Templates API
// ============================================

export const templatesApi = {
  list: async (): Promise<OSTemplate[]> => {
    const response = await apiClient.get<OSTemplate[]>('/templates');
    return response.data;
  },

  get: async (id: string): Promise<OSTemplate> => {
    const response = await apiClient.get<OSTemplate>(`/templates/${id}`);
    return response.data;
  },

  create: async (data: Partial<OSTemplate>): Promise<OSTemplate> => {
    const response = await apiClient.post<OSTemplate>('/templates', data);
    return response.data;
  },

  update: async (id: string, data: Partial<OSTemplate>): Promise<OSTemplate> => {
    const response = await apiClient.put<OSTemplate>(`/templates/${id}`, data);
    return response.data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/templates/${id}`);
  },
};

// ============================================
// Deployments API
// ============================================

export const deploymentsApi = {
  list: async (status?: string): Promise<Deployment[]> => {
    const params = status ? { status } : {};
    const response = await apiClient.get<Deployment[]>('/deployments', { params });
    return response.data;
  },

  get: async (id: string): Promise<Deployment> => {
    const response = await apiClient.get<Deployment>(`/deployments/${id}`);
    return response.data;
  },

  create: async (data: {
    name: string;
    hypervisor_id: string;
    template_id: string;
    config: DeploymentConfig;
  }): Promise<Deployment> => {
    const response = await apiClient.post<Deployment>('/deployments', data);
    return response.data;
  },

  cancel: async (id: string): Promise<Deployment> => {
    const response = await apiClient.post<Deployment>(`/deployments/${id}/cancel`);
    return response.data;
  },

  retry: async (id: string): Promise<Deployment> => {
    const response = await apiClient.post<Deployment>(`/deployments/${id}/retry`);
    return response.data;
  },

  getLogs: async (id: string): Promise<Deployment['logs']> => {
    const response = await apiClient.get(`/deployments/${id}/logs`);
    return response.data;
  },
};

// ============================================
// Dashboard / Stats API
// ============================================

export const dashboardApi = {
  getStats: async (): Promise<DashboardStats> => {
    // Cette route peut ne pas exister encore, on gère l'erreur
    try {
      const response = await apiClient.get<DashboardStats>('/dashboard/stats');
      return response.data;
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
