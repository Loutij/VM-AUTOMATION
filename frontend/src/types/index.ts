// Types pour les hyperviseurs
export interface Hypervisor {
  id: string;
  name: string;
  type: 'hyperv' | 'vmware';
  host: string;
  port?: number;
  username: string;
  is_connected: boolean;
  vm_count?: number;
  created_at: string;
  updated_at: string;
}

// Types pour les VMs
export type VMState = 'running' | 'stopped' | 'paused' | 'saved' | 'unknown';

export interface VirtualMachine {
  id: string;
  name: string;
  hypervisor_id: string;
  state: VMState;
  cpu_count: number;
  memory_mb: number;
  disk_size_gb: number;
  os_type?: string;
  ip_address?: string;
  created_at: string;
  updated_at: string;
}

// Types pour les templates OS
export type OSFamily = 'windows' | 'linux';

export interface OSTemplate {
  id: string;
  name: string;
  os_family: OSFamily;
  os_version: string;
  description?: string;
  iso_path?: string;
  unattend_template?: string;
  default_cpu: number;
  default_memory_mb: number;
  default_disk_gb: number;
  created_at: string;
}

// Types pour les déploiements
export type DeploymentStatus = 
  | 'pending'
  | 'creating_vm'
  | 'installing_os'
  | 'post_install'
  | 'installing_software'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface DeploymentLog {
  id: string;
  deployment_id: string;
  step: string;
  status: 'info' | 'success' | 'warning' | 'error';
  message: string;
  created_at: string;
}

export interface Deployment {
  id: string;
  name: string;
  hypervisor_id: string;
  template_id: string;
  vm_id?: string;
  status: DeploymentStatus;
  progress: number;
  error_message?: string;
  config: DeploymentConfig;
  logs?: DeploymentLog[];
  created_at: string;
  updated_at: string;
}

export interface DeploymentConfig {
  vm_name: string;
  cpu_count: number;
  memory_mb: number;
  disk_size_gb: number;
  network_switch?: string;
  hostname?: string;
  admin_password?: string;
  domain_join?: {
    domain: string;
    ou_path?: string;
  };
  network?: {
    dhcp: boolean;
    ip_address?: string;
    subnet_mask?: string;
    gateway?: string;
    dns_servers?: string[];
  };
}

// Types pour l'API
export interface ApiResponse<T> {
  data: T;
  message?: string;
}

export interface ApiError {
  detail: string;
  status_code: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// Types pour les statistiques du dashboard
export interface DashboardStats {
  total_vms: number;
  running_vms: number;
  stopped_vms: number;
  total_hypervisors: number;
  active_deployments: number;
  completed_deployments: number;
  failed_deployments: number;
}

export interface HealthCheck {
  status: 'healthy' | 'unhealthy';
  database: boolean;
  redis: boolean;
  hypervisors: {
    name: string;
    connected: boolean;
  }[];
}
