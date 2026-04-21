// Types pour les hyperviseurs
export interface Hypervisor {
  id: string;
  name: string;
  type: 'hyperv' | 'vmware';
  host: string;
  port?: number;
  username: string;
  is_active: boolean;
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
  ram_gb: number;  // Aligned with backend (was memory_mb)
  disk_gb: number; // Aligned with backend (was disk_size_gb)
  os_type?: string;
  ip_address?: string;
  network_switch?: string;
  vlan_id?: number;
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

// Méthode de déploiement : via ISO ou clonage d'un template vSphere
export type DeploymentMethod = 'iso' | 'clone';

export interface OSTemplate {
  id: string;
  name: string;
  os_family: OSFamily;
  os_type: string;  // Aligned with backend (was os_version)
  description?: string;
  iso_path?: string;
  unattend_template?: string;
  min_cpu: number;     // Aligned with backend (was default_cpu)
  min_ram_gb: number;  // Aligned with backend (was default_memory_mb)
  min_disk_gb: number; // Aligned with backend (was default_disk_gb)
  install_locale?: string;  // Langue d'installation (ex: fr-FR, en-US)
  // Déploiement par clone vSphere
  deployment_method?: DeploymentMethod;   // 'iso' (défaut) ou 'clone'
  vsphere_template_name?: string;         // Nom du template vSphere à cloner
  updated_at?: string;
  created_at: string;
}

// Types pour les déploiements
export type DeploymentStatus =
  | 'pending_approval'
  | 'pending'
  | 'in_progress'
  | 'creating_vm'
  | 'installing_os'
  | 'post_install'
  | 'installing_software'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'rejected';

export interface DeploymentLog {
  id: string;
  deployment_id: string;
  step: string;
  level: 'debug' | 'info' | 'warning' | 'error';
  message: string;
  details?: Record<string, any>;
  created_at: string;
}

export interface Deployment {
  id: string;
  vm_name: string;  // Aligned with backend
  name: string;     // Alias for vm_name (for display)
  hypervisor_id: string;
  os_template_id: string;  // Aligned with backend (was template_id)
  vm_id?: string;
  status: DeploymentStatus;
  progress: number;
  current_step?: string;  // Étape courante du déploiement
  error_message?: string;
  config: DeploymentConfig;
  logs?: DeploymentLog[];
  created_at: string;
  updated_at: string;
  // Approval workflow
  requested_by_username?: string;
  reviewed_by_username?: string;
  reviewed_at?: string;
  review_note?: string;
}

// Audit log
export interface AuditLogEntry {
  id: string;
  user_id: string;
  username: string;
  action: string;
  resource_type: string;
  resource_id?: string;
  details?: Record<string, any>;
  created_at: string;
}

export interface AuditLogList {
  items: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
}

// Template vSphere disponible pour le clonage
export interface VSphereTemplate {
  name: string;
  guest_os?: string;
  num_cpu?: number;
  memory_mb?: number;
  path?: string;
}

export interface DeploymentConfig {
  vm_name: string;
  cpu_count: number;
  ram_gb: number;  // Aligned with backend (was memory_mb)
  disk_gb: number; // Aligned with backend (was disk_size_gb)
  vhdx_path?: string; // Emplacement personnalisé du disque virtuel
  network_switch?: string;
  // Méthode de déploiement
  deployment_method?: DeploymentMethod;    // 'iso' (défaut) ou 'clone'
  vsphere_template_name?: string;          // Template vSphere à cloner (si clone)
  hostname?: string;
  admin_password?: string;
  domain_join?: {
    domain: string;
    user?: string;
    password?: string;
    ou?: string;
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
  package_configs?: Record<string, Record<string, unknown>>; // Configurations par package
  // Windows Update
  enable_windows_update?: boolean;
  // Commandes post-install personnalisées
  post_install_commands?: string[];
  // Linux-specific
  ssh_keys?: string[];
  extra_packages?: string[];
  post_commands?: string[];
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
  status: 'healthy' | 'unhealthy' | 'degraded';
  timestamp: string;
  version: string;
  environment: string;
  checks: {
    database: {
      status: 'healthy' | 'unhealthy';
      host?: string;
      error?: string;
    };
    redis: {
      status: 'healthy' | 'unhealthy' | 'unknown';
      message?: string;
    };
    celery: {
      status: 'healthy' | 'unhealthy' | 'unknown';
      message?: string;
    };
  };
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

// Types pour les emplacements de stockage
export interface StorageLocation {
  drive_letter: string;
  path: string;
  total_gb: number;
  free_gb: number;
  used_gb: number;
  percent_free: number;
  is_default: boolean;
  is_recommended: boolean;
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
    ram_gb: number;
    disk_gb: number;
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
    ram_gb: 4,
    disk_gb: 60,
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
  placeholder?: string;
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

// Types pour l'administration des utilisateurs
export type UserRole = 'admin' | 'user';

export interface AdminUser {
  id: string;
  username: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  role: UserRole;
  created_at: string;
}

export interface CreateUserRequest {
  username: string;
  email: string;
  password: string;
  full_name?: string;
}

export interface UpdateUserRequest {
  full_name?: string | null;
  is_active?: boolean;
  role?: UserRole;
}

export interface ResetPasswordRequest {
  new_password: string;
}

// Types pour l'inventaire logiciel
export interface ChocoPackage {
  Name: string;
  Version: string;
  Source: string;
}

export interface InstalledProgram {
  DisplayName: string;
  DisplayVersion: string | null;
  Publisher: string | null;
  InstallDate: string | null;
  EstimatedSize: number | null;
}

export interface WindowsFeature {
  FeatureName?: string;
  Name?: string;
  DisplayName?: string;
  State?: string;
  InstallState?: string;
}

export interface ServiceInfo {
  Name?: string;
  name?: string;
  DisplayName?: string;
  Status?: string;
  status?: string;
  StartType?: string;
}

export interface WindowsUpdate {
  HotFixID: string;
  Description?: string;
  InstalledOn?: string;
  InstalledBy?: string;
}

export interface SystemInfo {
  hostname?: string;
  os_name?: string;
  os_version?: string;
  os_build?: string;
  last_boot?: string;
  uptime_hours?: number;
  os_info?: string;
  kernel?: string;
  uptime?: string;
}

export interface SoftwareInventory {
  vm_id: string;
  vm_name: string;
  os_type: string;
  timestamp: string;
  system_info?: SystemInfo;
  chocolatey_packages?: ChocoPackage[];
  installed_programs?: InstalledProgram[];
  windows_features?: WindowsFeature[];
  running_services?: ServiceInfo[];
  recent_updates?: WindowsUpdate[];
  // Linux
  packages?: { name: string; version: string; status?: string }[];
  snap_packages?: { name: string; version: string; source?: string }[];
  flatpak_packages?: { name: string; version: string; source?: string }[];
  total_packages: number;
}

// VNC Types
export interface VNCStatus {
  reachable: boolean;
  is_vnc?: boolean;
  server_version?: string;
  vm_ip?: string;
  port: number;
  error?: string;
}

export interface VNCInstallResult {
  success: boolean;
  step: string;
  vnc_port?: number;
  vnc_display?: number;
  vm_ip?: string;
  protocol?: string;
  error?: string | null;
}

export interface VNCSession {
  vm_id: string;
  vm_ip: string;
  vnc_port: number;
  running: boolean;
}
