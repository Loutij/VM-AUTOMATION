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

// Détails complets d'une VM depuis Hyper-V
export interface VMDetails {
  db_id?: string;
  general: {
    id: string;
    name: string;
    state: string;
    status: string;
    generation: number;
    version: string;
    path: string;
    notes?: string;
    uptime?: string;
  };
  configuration: {
    cpu_count: number;
    ram_startup_gb: number;
    ram_minimum_gb?: number;
    ram_maximum_gb?: number;
    dynamic_memory: boolean;
    secure_boot?: boolean;
    tpm_enabled?: boolean;
    checkpoint_type: string;
    automatic_start_action: string;
    automatic_stop_action: string;
  };
  resources: {
    cpu_usage_percent: number;
    ram_assigned_gb: number;
    ram_demand_gb: number;
  };
  disks: VMDiskInfo[];
  network_adapters: VMNetworkAdapterInfo[];
  integration_services: VMIntegrationService[];
  checkpoints: VMCheckpoint[];
}

export interface VMDiskInfo {
  path: string;
  controller_type: string;
  controller_number: number;
  controller_location: number;
  size_gb?: number;
  size_used_gb?: number;
  format?: string;
  type?: string;
  fragmentation_percent?: number;
}

export interface VMNetworkAdapterInfo {
  name: string;
  switch_name?: string;
  mac_address?: string;
  mac_type?: string;
  vlan_id?: number;
  ip_addresses: string[];
  status: string;
  bandwidth_weight?: number;
}

export interface VMIntegrationService {
  name: string;
  enabled: boolean;
  status: string;
}

export interface VMCheckpoint {
  id: string;
  name: string;
  creation_time: string;
  parent_id?: string;
}

export interface VMScreenshot {
  vm_id: string;
  vm_name: string;
  width: number;
  height: number;
  image: string; // data:image/png;base64,...
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
  vhdx_path?: string; // Emplacement personnalisé du disque virtuel
  network_switch?: string;
  hostname?: string;
  admin_password?: string;
  domain_join?: {
    domain: string;
    user?: string;
    password?: string;
    ou_path?: string;
  };
  ip_config?: {
    static_ip?: boolean;
    ip_address?: string;
    subnet_prefix?: number;
    gateway?: string;
    dns_server_1?: string;
    dns_server_2?: string;
  };
  // Services à activer
  services?: {
    enable_rdp?: boolean;
    enable_winrm?: boolean;
    enable_ssh?: boolean;
  };
  // Configuration sécurité
  security?: {
    configure_password_policy?: boolean;
    password_min_length?: number;
    password_complexity?: boolean;
    password_max_age?: number;
  };
  // Logiciels
  software_profile?: string; // minimal, tools, development, webserver, database, monitoring
  packages?: string[]; // Packages Chocolatey supplémentaires
  // Windows Update
  enable_windows_update?: boolean;
  // Commandes post-install personnalisées
  post_install_commands?: string[];
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

// Types pour les switches virtuels
export type SwitchType = 'Internal' | 'External' | 'Private';

export interface VirtualSwitch {
  name: string;
  switch_type: SwitchType;
  interface_description?: string;
  notes?: string;
}

export interface CreateSwitchRequest {
  name: string;
  switch_type: SwitchType;
  net_adapter_name?: string;
  allow_management_os?: boolean;
  notes?: string;
}

export interface PhysicalAdapter {
  name: string;
  description: string;
  status: string;
  link_speed: string;
  mac_address: string;
}

// Types pour les paramètres de l'application
export interface AppSettings {
  // Paramètres généraux
  language: 'fr' | 'en';
  theme: 'dark' | 'light' | 'system';
  
  // Notifications
  notifications: {
    enabled: boolean;
    deploymentComplete: boolean;
    deploymentFailed: boolean;
    vmStateChange: boolean;
    sound: boolean;
  };
  
  // Valeurs par défaut pour les déploiements
  defaultDeployment: {
    cpu_count: number;
    memory_mb: number;
    disk_size_gb: number;
    network_switch: string;
  };
  
  // Paramètres d'affichage
  display: {
    itemsPerPage: number;
    autoRefresh: boolean;
    refreshInterval: number; // secondes
  };
}

export const DEFAULT_SETTINGS: AppSettings = {
  language: 'fr',
  theme: 'dark',
  notifications: {
    enabled: true,
    deploymentComplete: true,
    deploymentFailed: true,
    vmStateChange: false,
    sound: false,
  },
  defaultDeployment: {
    cpu_count: 2,
    memory_mb: 4096,
    disk_size_gb: 60,
    network_switch: 'Default Switch',
  },
  display: {
    itemsPerPage: 10,
    autoRefresh: true,
    refreshInterval: 30,
  },
};

// ==============================================
// Types pour la Marketplace de logiciels
// ==============================================

export type SoftwareCategory =
  | 'windows_role'
  | 'remote_access'
  | 'database'
  | 'webserver'
  | 'development'
  | 'runtime'
  | 'monitoring'
  | 'security'
  | 'utilities'
  | 'browser'
  | 'containers'
  | 'file_transfer'
  | 'network'
  | 'backup'
  | 'other';

export interface SoftwarePackage {
  id: string;
  name: string;
  display_name: string;
  version: string;
  description?: string;
  short_description?: string;
  category: SoftwareCategory;
  tags: string[];
  os_family?: 'windows' | 'linux';
  package_manager: string;
  package_id: string;
  install_command_windows?: string;
  install_command_linux?: string;
  default_config: Record<string, unknown>;
  config_schema?: {
    fields: ConfigField[];
  };
  icon?: string;
  website?: string;
  documentation_url?: string;
  dependencies: string[];
  conflicts: string[];
  is_active: boolean;
  is_featured: boolean;
  install_time_minutes: number;
  install_count: number;
  created_at: string;
  updated_at?: string;
}

export interface ConfigField {
  name: string;
  type: 'string' | 'number' | 'boolean' | 'select';
  label: string;
  description?: string;
  required?: boolean;
  default?: unknown;
  options?: { value: string; label: string }[];
}

export interface SoftwareCategory_Info {
  id: string;
  name: string;
  description: string;
  icon: string;
  emoji?: string;
  count: number;
}

export interface SoftwareProfile {
  name: string;
  display_name: string;
  description: string;
  icon: string;
  packages: string[];
  package_count: number;
}

export interface SoftwareList {
  items: SoftwarePackage[];
  total: number;
  page: number;
  page_size: number;
  categories: Record<string, number>;
}

export interface ProfileList {
  profiles: SoftwareProfile[];
}
