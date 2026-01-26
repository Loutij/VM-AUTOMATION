import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Rocket,
  ArrowLeft,
  Server,
  FileCode,
  Cpu,
  MemoryStick,
  HardDrive,
  Network,
  Key,
  Globe,
  ChevronRight,
  ChevronLeft,
  Check,
  Settings,
  Package,
  Shield,
  RefreshCw,
  Building2,
  Plus,
  Loader2,
  Wifi,
  FolderOpen,
} from 'lucide-react';
import { Header } from '../components/layout';
import { Button, Input, Select, Switch, Modal, useToast } from '../components/ui';
import { hypervisorsApi, templatesApi, deploymentsApi } from '../services/api';
import type { DeploymentConfig, SwitchType } from '../types';

// Profils logiciels disponibles
const SOFTWARE_PROFILES = [
  { id: 'minimal', name: 'Minimal', description: '7zip, Notepad++', packages: ['7zip', 'notepadplusplus'] },
  { id: 'tools', name: 'Outils système', description: '+ Sysinternals, Process Explorer', packages: ['7zip', 'notepadplusplus', 'sysinternals'] },
  { id: 'development', name: 'Développement', description: 'Git, VS Code, Node.js, Python', packages: ['git', 'vscode', 'nodejs', 'python'] },
  { id: 'webserver', name: 'Serveur Web', description: 'IIS, URL Rewrite', packages: ['iis-webserver', 'urlrewrite'] },
  { id: 'database', name: 'Base de données', description: 'SQL Server Express, SSMS', packages: ['sql-server-express', 'ssms'] },
  { id: 'monitoring', name: 'Monitoring', description: 'Zabbix Agent', packages: ['zabbix-agent'] },
];

// Services Windows
const WINDOWS_SERVICES = [
  { id: 'rdp', name: 'Bureau à distance (RDP)', description: 'Accès distant via RDP', default: true },
  { id: 'winrm', name: 'WinRM', description: 'Gestion PowerShell à distance', default: true },
  { id: 'ssh', name: 'OpenSSH Server', description: 'Accès SSH', default: false },
];

interface DeploymentFormData {
  // Étape 1: Sélection hyperviseur et template
  hypervisor_id: string;
  template_id: string;
  // Étape 2: Configuration VM
  vm_name: string;
  hostname: string;
  cpu_count: number;
  memory_mb: number;
  disk_size_gb: number;
  vhdx_path: string; // Emplacement du disque virtuel
  // Étape 3: Réseau
  network_switch: string;
  vlan_id: number | null;
  use_static_ip: boolean;
  ip_address: string;
  subnet_prefix: number;
  gateway: string;
  dns_primary: string;
  dns_secondary: string;
  // Étape 4: Options avancées
  admin_password: string;
  admin_password_confirm: string;
  // Services
  enable_rdp: boolean;
  enable_winrm: boolean;
  enable_ssh: boolean;
  // Mises à jour
  enable_windows_update: boolean;
  // Logiciels
  software_profile: string;
  custom_packages: string[];
  // Domaine AD
  join_domain: boolean;
  domain_name: string;
  domain_user: string;
  domain_password: string;
  domain_ou: string;
  // Post-install
  post_install_commands: string[];
}

const defaultFormData: DeploymentFormData = {
  hypervisor_id: '',
  template_id: '',
  vm_name: '',
  hostname: '',
  cpu_count: 2,
  memory_mb: 4096,
  disk_size_gb: 60,
  vhdx_path: '', // Vide = utiliser le chemin par défaut de l'hyperviseur
  network_switch: '',
  vlan_id: null,
  use_static_ip: false,
  ip_address: '',
  subnet_prefix: 24,
  gateway: '',
  dns_primary: '8.8.8.8',
  dns_secondary: '8.8.4.4',
  admin_password: '',
  admin_password_confirm: '',
  enable_rdp: true,
  enable_winrm: true,
  enable_ssh: false,
  enable_windows_update: true,
  software_profile: '',
  custom_packages: [],
  join_domain: false,
  domain_name: '',
  domain_user: '',
  domain_password: '',
  domain_ou: '',
  post_install_commands: [],
};

const steps = [
  { id: 1, name: 'Infrastructure', icon: Server },
  { id: 2, name: 'Ressources', icon: Cpu },
  { id: 3, name: 'Réseau', icon: Network },
  { id: 4, name: 'Options', icon: Settings },
  { id: 5, name: 'Résumé', icon: Check },
];

export function NewDeployment() {
  const navigate = useNavigate();
  const { addToast } = useToast();
  const [currentStep, setCurrentStep] = useState(1);
  const [formData, setFormData] = useState<DeploymentFormData>(defaultFormData);

  const queryClient = useQueryClient();

  // State pour le modal de création de switch
  const [isCreateSwitchModalOpen, setIsCreateSwitchModalOpen] = useState(false);
  const [newSwitchData, setNewSwitchData] = useState({
    name: '',
    switch_type: 'Internal' as SwitchType,
    net_adapter_name: '',
    allow_management_os: true,
    notes: '',
  });

  // Fetch hyperviseurs
  const { data: hypervisors = [], isLoading: hypervisorsLoading } = useQuery({
    queryKey: ['hypervisors'],
    queryFn: hypervisorsApi.list,
  });

  // Fetch templates
  const { data: templates = [], isLoading: templatesLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: templatesApi.list,
  });

  // Fetch switches (dépend de l'hyperviseur sélectionné)
  const { data: switches = [], isLoading: switchesLoading } = useQuery({
    queryKey: ['switches', formData.hypervisor_id],
    queryFn: () => hypervisorsApi.listSwitches(formData.hypervisor_id),
    enabled: !!formData.hypervisor_id,
  });

  // Fetch adaptateurs physiques (pour créer des switches externes)
  const { data: physicalAdapters = [], isLoading: adaptersLoading } = useQuery({
    queryKey: ['physical-adapters', formData.hypervisor_id],
    queryFn: () => hypervisorsApi.listPhysicalAdapters(formData.hypervisor_id),
    enabled: !!formData.hypervisor_id && isCreateSwitchModalOpen,
  });

  // Mutation pour créer un switch
  const createSwitchMutation = useMutation({
    mutationFn: (data: typeof newSwitchData) =>
      hypervisorsApi.createSwitch(formData.hypervisor_id, {
        name: data.name,
        switch_type: data.switch_type,
        net_adapter_name: data.switch_type === 'External' ? data.net_adapter_name : undefined,
        allow_management_os: data.allow_management_os,
        notes: data.notes || undefined,
      }),
    onSuccess: (createdSwitch) => {
      addToast({ type: 'success', title: 'Switch créé', message: `Le switch "${createdSwitch.name}" a été créé.` });
      queryClient.invalidateQueries({ queryKey: ['switches', formData.hypervisor_id] });
      setFormData({ ...formData, network_switch: createdSwitch.name });
      setIsCreateSwitchModalOpen(false);
      setNewSwitchData({
        name: '',
        switch_type: 'Internal',
        net_adapter_name: '',
        allow_management_os: true,
        notes: '',
      });
    },
    onError: (error: Error) => {
      addToast({ type: 'error', title: 'Erreur', message: error.message || 'Impossible de créer le switch.' });
    },
  });

  // Sélectionner automatiquement le premier switch si disponible
  useEffect(() => {
    if (switches.length > 0 && !formData.network_switch) {
      setFormData((prev) => ({ ...prev, network_switch: switches[0].name }));
    }
  }, [switches]);

  // Mutation pour créer le déploiement
  const createMutation = useMutation({
    mutationFn: (data: {
      name: string;
      hypervisor_id: string;
      template_id: string;
      config: DeploymentConfig;
    }) => deploymentsApi.create(data),
    onSuccess: (deployment) => {
      addToast({
        type: 'success',
        title: 'Déploiement créé',
        message: `Le déploiement "${deployment.name}" a été lancé.`,
      });
      navigate('/deployments');
    },
    onError: () => {
      addToast({
        type: 'error',
        title: 'Erreur',
        message: 'Impossible de créer le déploiement.',
      });
    },
  });

  // Hyperviseur et template sélectionnés
  const selectedHypervisor = hypervisors.find((h) => h.id === formData.hypervisor_id);
  const selectedTemplate = templates.find((t) => t.id === formData.template_id);
  const selectedProfile = SOFTWARE_PROFILES.find((p) => p.id === formData.software_profile);

  // Validation par étape
  const validateStep = (step: number): boolean => {
    switch (step) {
      case 1:
        return !!formData.hypervisor_id && !!formData.template_id;
      case 2:
        return (
          !!formData.vm_name &&
          formData.cpu_count >= 1 &&
          formData.memory_mb >= 512 &&
          formData.disk_size_gb >= 20
        );
      case 3:
        if (formData.use_static_ip && !formData.ip_address) return false;
        return true;
      case 4:
        if (formData.admin_password !== formData.admin_password_confirm) return false;
        if (formData.join_domain && (!formData.domain_name || !formData.domain_user)) return false;
        return true;
      default:
        return true;
    }
  };

  const canProceed = validateStep(currentStep);

  const handleNext = () => {
    if (canProceed && currentStep < 5) {
      setCurrentStep(currentStep + 1);
    }
  };

  const handlePrevious = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleSubmit = () => {
    // Valider toutes les étapes
    for (let i = 1; i <= 4; i++) {
      if (!validateStep(i)) {
        setCurrentStep(i);
        addToast({
          type: 'error',
          title: 'Formulaire incomplet',
          message: `Veuillez compléter l'étape ${i}.`,
        });
        return;
      }
    }

    // Construire la config complète
    const config: DeploymentConfig & Record<string, unknown> = {
      vm_name: formData.vm_name,
      cpu_count: formData.cpu_count,
      memory_mb: formData.memory_mb,
      disk_size_gb: formData.disk_size_gb,
      hostname: formData.hostname || formData.vm_name,
      admin_password: formData.admin_password || undefined,
      network_switch: formData.network_switch || undefined,
    };

    // Ajouter VLAN si défini
    if (formData.vlan_id) {
      config.vlan_id = formData.vlan_id;
    }

    // Configuration IP
    if (formData.use_static_ip) {
      config.ip_config = {
        static_ip: true,
        ip_address: formData.ip_address,
        subnet_prefix: formData.subnet_prefix,
        gateway: formData.gateway,
        dns_server_1: formData.dns_primary,
        dns_server_2: formData.dns_secondary,
      };
    }

    // Services
    config.services = {
      enable_rdp: formData.enable_rdp,
      enable_winrm: formData.enable_winrm,
      enable_ssh: formData.enable_ssh,
    };

    // Windows Update
    config.enable_windows_update = formData.enable_windows_update;

    // Logiciels
    if (formData.software_profile) {
      config.software_profile = formData.software_profile;
      const profile = SOFTWARE_PROFILES.find((p) => p.id === formData.software_profile);
      if (profile) {
        config.packages = profile.packages;
      }
    }

    // Domaine AD
    if (formData.join_domain) {
      config.domain_join = {
        domain: formData.domain_name,
        user: formData.domain_user,
        password: formData.domain_password,
        ou_path: formData.domain_ou || undefined,
      };
    }

    // Commandes post-install
    if (formData.post_install_commands.length > 0) {
      config.post_install_commands = formData.post_install_commands;
    }

    createMutation.mutate({
      name: formData.vm_name,
      hypervisor_id: formData.hypervisor_id,
      template_id: formData.template_id,
      config: config as DeploymentConfig,
    });
  };

  // Appliquer les valeurs par défaut du template
  const handleTemplateChange = (templateId: string) => {
    const template = templates.find((t) => t.id === templateId);
    setFormData((prev) => ({
      ...prev,
      template_id: templateId,
      cpu_count: template?.default_cpu || prev.cpu_count,
      memory_mb: template?.default_memory_mb || prev.memory_mb,
      disk_size_gb: template?.default_disk_gb || prev.disk_size_gb,
    }));
  };

  const formatMemory = (mb: number) => {
    if (mb >= 1024) return `${mb / 1024} GB`;
    return `${mb} MB`;
  };

  return (
    <div className="min-h-screen bg-dark-900">
      <Header title="Nouveau déploiement" />
      <div className="p-6">
        {/* Bouton retour */}
        <Button
          variant="ghost"
          leftIcon={<ArrowLeft size={18} />}
          onClick={() => navigate('/deployments')}
          className="mb-6"
        >
          Retour aux déploiements
        </Button>

        {/* Progress steps */}
        <div className="card p-6 mb-6">
          <div className="flex items-center justify-between overflow-x-auto">
            {steps.map((step, index) => (
              <div key={step.id} className="flex items-center flex-shrink-0">
                <div
                  className={`flex items-center gap-2 cursor-pointer ${
                    currentStep === step.id
                      ? 'text-primary-500'
                      : currentStep > step.id
                      ? 'text-green-500'
                      : 'text-dark-400'
                  }`}
                  onClick={() => step.id < currentStep && setCurrentStep(step.id)}
                >
                  <div
                    className={`w-10 h-10 rounded-full flex items-center justify-center ${
                      currentStep === step.id
                        ? 'bg-primary-600'
                        : currentStep > step.id
                        ? 'bg-green-600'
                        : 'bg-dark-700'
                    }`}
                  >
                    {currentStep > step.id ? (
                      <Check size={20} />
                    ) : (
                      <step.icon size={20} />
                    )}
                  </div>
                  <span className="font-medium hidden md:inline">{step.name}</span>
                </div>
                {index < steps.length - 1 && (
                  <ChevronRight size={20} className="mx-2 md:mx-4 text-dark-600" />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Formulaire */}
        <div className="card p-6">
          {/* Étape 1: Infrastructure */}
          {currentStep === 1 && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-semibold text-white mb-2">
                  Sélection de l'infrastructure
                </h2>
                <p className="text-dark-400">
                  Choisissez l'hyperviseur et le template OS pour votre VM.
                </p>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Sélection hyperviseur */}
                <div>
                  <label className="block text-sm font-medium text-dark-200 mb-2">
                    <Server size={16} className="inline mr-2" />
                    Hyperviseur
                  </label>
                  {hypervisorsLoading ? (
                    <div className="h-12 bg-dark-700 animate-pulse rounded-lg" />
                  ) : hypervisors.length === 0 ? (
                    <div className="p-4 bg-dark-700 rounded-lg text-dark-400 text-center">
                      Aucun hyperviseur configuré.{' '}
                      <button
                        onClick={() => navigate('/hypervisors')}
                        className="text-primary-500 hover:underline"
                      >
                        En ajouter un
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {hypervisors.map((h) => (
                        <label
                          key={h.id}
                          className={`flex items-center gap-3 p-4 rounded-lg border cursor-pointer transition-colors ${
                            formData.hypervisor_id === h.id
                              ? 'border-primary-500 bg-primary-500/10'
                              : 'border-dark-600 hover:border-dark-500 bg-dark-700/50'
                          }`}
                        >
                          <input
                            type="radio"
                            name="hypervisor"
                            value={h.id}
                            checked={formData.hypervisor_id === h.id}
                            onChange={(e) =>
                              setFormData({ ...formData, hypervisor_id: e.target.value })
                            }
                            className="sr-only"
                          />
                          <div
                            className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
                              formData.hypervisor_id === h.id
                                ? 'border-primary-500'
                                : 'border-dark-500'
                            }`}
                          >
                            {formData.hypervisor_id === h.id && (
                              <div className="w-2 h-2 rounded-full bg-primary-500" />
                            )}
                          </div>
                          <div className="flex-1">
                            <p className="font-medium text-white">{h.name}</p>
                            <p className="text-sm text-dark-400">
                              {h.type.toUpperCase()} • {h.host}
                            </p>
                          </div>
                          <div
                            className={`w-2 h-2 rounded-full ${
                              h.is_connected ? 'bg-green-500' : 'bg-red-500'
                            }`}
                          />
                        </label>
                      ))}
                    </div>
                  )}
                </div>

                {/* Sélection template */}
                <div>
                  <label className="block text-sm font-medium text-dark-200 mb-2">
                    <FileCode size={16} className="inline mr-2" />
                    Template OS
                  </label>
                  {templatesLoading ? (
                    <div className="h-12 bg-dark-700 animate-pulse rounded-lg" />
                  ) : templates.length === 0 ? (
                    <div className="p-4 bg-dark-700 rounded-lg text-dark-400 text-center">
                      Aucun template disponible.{' '}
                      <button
                        onClick={() => navigate('/templates')}
                        className="text-primary-500 hover:underline"
                      >
                        En créer un
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-2 max-h-80 overflow-y-auto">
                      {templates.map((t) => (
                        <label
                          key={t.id}
                          className={`flex items-center gap-3 p-4 rounded-lg border cursor-pointer transition-colors ${
                            formData.template_id === t.id
                              ? 'border-primary-500 bg-primary-500/10'
                              : 'border-dark-600 hover:border-dark-500 bg-dark-700/50'
                          }`}
                        >
                          <input
                            type="radio"
                            name="template"
                            value={t.id}
                            checked={formData.template_id === t.id}
                            onChange={() => handleTemplateChange(t.id)}
                            className="sr-only"
                          />
                          <div
                            className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
                              formData.template_id === t.id
                                ? 'border-primary-500'
                                : 'border-dark-500'
                            }`}
                          >
                            {formData.template_id === t.id && (
                              <div className="w-2 h-2 rounded-full bg-primary-500" />
                            )}
                          </div>
                          <div
                            className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                              t.os_family === 'windows'
                                ? 'bg-blue-500/20'
                                : 'bg-orange-500/20'
                            }`}
                          >
                            {t.os_family === 'windows' ? (
                              <Globe size={20} className="text-blue-400" />
                            ) : (
                              <Server size={20} className="text-orange-400" />
                            )}
                          </div>
                          <div className="flex-1">
                            <p className="font-medium text-white">{t.name}</p>
                            <p className="text-sm text-dark-400">{t.os_version}</p>
                          </div>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Étape 2: Ressources */}
          {currentStep === 2 && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-semibold text-white mb-2">
                  Configuration des ressources
                </h2>
                <p className="text-dark-400">
                  Définissez le nom et les ressources de votre VM.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <Input
                  label="Nom de la VM"
                  value={formData.vm_name}
                  onChange={(e) => setFormData({ ...formData, vm_name: e.target.value })}
                  placeholder="ma-nouvelle-vm"
                  required
                  helperText="Nom unique pour identifier la VM"
                />
                <Input
                  label="Nom d'hôte"
                  value={formData.hostname}
                  onChange={(e) => setFormData({ ...formData, hostname: e.target.value })}
                  placeholder={formData.vm_name || 'hostname'}
                  helperText="Laissez vide pour utiliser le nom de la VM"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div>
                  <label className="block text-sm font-medium text-dark-200 mb-2">
                    <Cpu size={16} className="inline mr-2" />
                    CPUs
                  </label>
                  <div className="flex items-center gap-3">
                    <input
                      type="range"
                      min="1"
                      max="16"
                      value={formData.cpu_count}
                      onChange={(e) =>
                        setFormData({ ...formData, cpu_count: parseInt(e.target.value) })
                      }
                      className="flex-1 h-2 bg-dark-700 rounded-full appearance-none cursor-pointer accent-primary-500"
                    />
                    <span className="w-12 text-center font-medium text-white">
                      {formData.cpu_count}
                    </span>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-dark-200 mb-2">
                    <MemoryStick size={16} className="inline mr-2" />
                    RAM
                  </label>
                  <Select
                    value={formData.memory_mb.toString()}
                    onChange={(e) =>
                      setFormData({ ...formData, memory_mb: parseInt(e.target.value) })
                    }
                    options={[
                      { value: '1024', label: '1 GB' },
                      { value: '2048', label: '2 GB' },
                      { value: '4096', label: '4 GB' },
                      { value: '8192', label: '8 GB' },
                      { value: '16384', label: '16 GB' },
                      { value: '32768', label: '32 GB' },
                    ]}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-dark-200 mb-2">
                    <HardDrive size={16} className="inline mr-2" />
                    Disque
                  </label>
                  <Select
                    value={formData.disk_size_gb.toString()}
                    onChange={(e) =>
                      setFormData({ ...formData, disk_size_gb: parseInt(e.target.value) })
                    }
                    options={[
                      { value: '40', label: '40 GB' },
                      { value: '60', label: '60 GB' },
                      { value: '80', label: '80 GB' },
                      { value: '100', label: '100 GB' },
                      { value: '120', label: '120 GB' },
                      { value: '200', label: '200 GB' },
                      { value: '500', label: '500 GB' },
                    ]}
                  />
                </div>
              </div>

              {/* Emplacement du disque virtuel */}
              <div className="border border-dark-600 rounded-lg p-4">
                <h3 className="text-sm font-medium text-dark-200 mb-4 flex items-center gap-2">
                  <FolderOpen size={16} />
                  Emplacement du disque virtuel
                </h3>
                <Input
                  label="Chemin du fichier VHDX"
                  value={formData.vhdx_path}
                  onChange={(e) => setFormData({ ...formData, vhdx_path: e.target.value })}
                  placeholder="C:\Hyper-V\Virtual Hard Disks"
                  helperText="Laissez vide pour utiliser l'emplacement par défaut de l'hyperviseur. Le fichier sera nommé automatiquement d'après le nom de la VM."
                />
                <div className="mt-3 p-3 bg-dark-700/50 rounded-lg">
                  <p className="text-xs text-dark-400">
                    <strong className="text-dark-300">Exemple :</strong> Si le chemin est{' '}
                    <code className="bg-dark-600 px-1 rounded">C:\Hyper-V\Disks</code> et le nom de la VM est{' '}
                    <code className="bg-dark-600 px-1 rounded">{formData.vm_name || 'ma-vm'}</code>, le disque sera créé à{' '}
                    <code className="bg-dark-600 px-1 rounded">
                      {formData.vhdx_path || 'C:\\Hyper-V\\Disks'}\\{formData.vm_name || 'ma-vm'}.vhdx
                    </code>
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Étape 3: Réseau */}
          {currentStep === 3 && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-semibold text-white mb-2">
                  Configuration réseau
                </h2>
                <p className="text-dark-400">
                  Configurez le switch virtuel, VLAN et les paramètres IP.
                </p>
              </div>

              {/* Sélection du switch */}
              <div className="border border-dark-600 rounded-lg p-4">
                <h3 className="text-sm font-medium text-dark-200 mb-4 flex items-center gap-2">
                  <Wifi size={16} />
                  Switch virtuel
                </h3>
                
                {switchesLoading ? (
                  <div className="flex items-center gap-2 text-dark-400">
                    <Loader2 size={16} className="animate-spin" />
                    Chargement des switches...
                  </div>
                ) : switches.length === 0 ? (
                  <div className="text-center py-4">
                    <Network size={32} className="mx-auto mb-2 text-dark-500" />
                    <p className="text-dark-400 mb-3">Aucun switch virtuel trouvé</p>
                    <Button
                      variant="secondary"
                      size="sm"
                      leftIcon={<Plus size={16} />}
                      onClick={() => setIsCreateSwitchModalOpen(true)}
                    >
                      Créer un switch
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                      {switches.map((sw) => (
                        <label
                          key={sw.name}
                          className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                            formData.network_switch === sw.name
                              ? 'border-primary-500 bg-primary-500/10'
                              : 'border-dark-600 hover:border-dark-500'
                          }`}
                        >
                          <input
                            type="radio"
                            name="network_switch"
                            value={sw.name}
                            checked={formData.network_switch === sw.name}
                            onChange={(e) =>
                              setFormData({ ...formData, network_switch: e.target.value })
                            }
                            className="sr-only"
                          />
                          <div className="flex items-center gap-2">
                            <Network size={16} className={formData.network_switch === sw.name ? 'text-primary-500' : 'text-dark-400'} />
                            <span className="font-medium text-white">{sw.name}</span>
                          </div>
                          <div className="mt-1 flex items-center gap-2">
                            <span className={`text-xs px-2 py-0.5 rounded ${
                              sw.switch_type === 'External' ? 'bg-green-500/20 text-green-400' :
                              sw.switch_type === 'Internal' ? 'bg-blue-500/20 text-blue-400' :
                              'bg-purple-500/20 text-purple-400'
                            }`}>
                              {sw.switch_type}
                            </span>
                          </div>
                          {sw.notes && (
                            <p className="text-xs text-dark-400 mt-1 truncate">{sw.notes}</p>
                          )}
                        </label>
                      ))}
                      
                      {/* Option pour créer un nouveau switch */}
                      <button
                        type="button"
                        onClick={() => setIsCreateSwitchModalOpen(true)}
                        className="p-3 rounded-lg border border-dashed border-dark-500 hover:border-primary-500 hover:bg-primary-500/5 transition-colors text-left"
                      >
                        <div className="flex items-center gap-2">
                          <Plus size={16} className="text-primary-500" />
                          <span className="font-medium text-primary-400">Créer un switch</span>
                        </div>
                        <p className="text-xs text-dark-400 mt-1">
                          Ajouter un nouveau switch virtuel
                        </p>
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* VLAN */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <Input
                  label="VLAN ID (optionnel)"
                  type="number"
                  min="1"
                  max="4094"
                  value={formData.vlan_id?.toString() || ''}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      vlan_id: e.target.value ? parseInt(e.target.value) : null,
                    })
                  }
                  placeholder="Ex: 100"
                  helperText="Laissez vide pour pas de VLAN"
                />
              </div>

              {/* Configuration IP statique */}
              <div className="border border-dark-600 rounded-lg p-4">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <span className="font-medium text-white">Configuration IP statique</span>
                    <p className="text-sm text-dark-400">Par défaut, DHCP sera utilisé</p>
                  </div>
                  <Switch
                    checked={formData.use_static_ip}
                    onChange={(checked) => setFormData({ ...formData, use_static_ip: checked })}
                  />
                </div>

                {formData.use_static_ip && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t border-dark-600">
                    <Input
                      label="Adresse IP"
                      value={formData.ip_address}
                      onChange={(e) =>
                        setFormData({ ...formData, ip_address: e.target.value })
                      }
                      placeholder="192.168.1.100"
                      required
                    />
                    <Input
                      label="Préfixe sous-réseau"
                      type="number"
                      min="1"
                      max="32"
                      value={formData.subnet_prefix.toString()}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          subnet_prefix: parseInt(e.target.value) || 24,
                        })
                      }
                      placeholder="24"
                    />
                    <Input
                      label="Passerelle"
                      value={formData.gateway}
                      onChange={(e) =>
                        setFormData({ ...formData, gateway: e.target.value })
                      }
                      placeholder="192.168.1.1"
                    />
                    <Input
                      label="DNS primaire"
                      value={formData.dns_primary}
                      onChange={(e) =>
                        setFormData({ ...formData, dns_primary: e.target.value })
                      }
                      placeholder="8.8.8.8"
                    />
                    <Input
                      label="DNS secondaire"
                      value={formData.dns_secondary}
                      onChange={(e) =>
                        setFormData({ ...formData, dns_secondary: e.target.value })
                      }
                      placeholder="8.8.4.4"
                    />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Étape 4: Options avancées */}
          {currentStep === 4 && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-semibold text-white mb-2">
                  Options avancées
                </h2>
                <p className="text-dark-400">
                  Configurez les services, logiciels et options de déploiement.
                </p>
              </div>

              {/* Mot de passe administrateur */}
              <div className="border border-dark-600 rounded-lg p-4">
                <h3 className="text-sm font-medium text-dark-200 mb-4 flex items-center gap-2">
                  <Key size={16} />
                  Compte administrateur
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Input
                    label="Mot de passe administrateur"
                    type="password"
                    value={formData.admin_password}
                    onChange={(e) =>
                      setFormData({ ...formData, admin_password: e.target.value })
                    }
                    placeholder="••••••••"
                  />
                  <Input
                    label="Confirmer le mot de passe"
                    type="password"
                    value={formData.admin_password_confirm}
                    onChange={(e) =>
                      setFormData({ ...formData, admin_password_confirm: e.target.value })
                    }
                    placeholder="••••••••"
                    error={
                      formData.admin_password_confirm &&
                      formData.admin_password !== formData.admin_password_confirm
                        ? 'Les mots de passe ne correspondent pas'
                        : undefined
                    }
                  />
                </div>
              </div>

              {/* Services */}
              <div className="border border-dark-600 rounded-lg p-4">
                <h3 className="text-sm font-medium text-dark-200 mb-4 flex items-center gap-2">
                  <Shield size={16} />
                  Services à activer
                </h3>
                <div className="space-y-3">
                  {WINDOWS_SERVICES.map((service) => (
                    <div key={service.id} className="flex items-center justify-between">
                      <div>
                        <span className="font-medium text-white">{service.name}</span>
                        <p className="text-sm text-dark-400">{service.description}</p>
                      </div>
                      <Switch
                        checked={
                          service.id === 'rdp'
                            ? formData.enable_rdp
                            : service.id === 'winrm'
                            ? formData.enable_winrm
                            : formData.enable_ssh
                        }
                        onChange={(checked) => {
                          if (service.id === 'rdp') {
                            setFormData({ ...formData, enable_rdp: checked });
                          } else if (service.id === 'winrm') {
                            setFormData({ ...formData, enable_winrm: checked });
                          } else {
                            setFormData({ ...formData, enable_ssh: checked });
                          }
                        }}
                      />
                    </div>
                  ))}
                </div>
              </div>

              {/* Windows Update */}
              <div className="border border-dark-600 rounded-lg p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <RefreshCw size={18} className="text-dark-400" />
                    <div>
                      <span className="font-medium text-white">Windows Update</span>
                      <p className="text-sm text-dark-400">
                        Installer les mises à jour après l'installation
                      </p>
                    </div>
                  </div>
                  <Switch
                    checked={formData.enable_windows_update}
                    onChange={(checked) =>
                      setFormData({ ...formData, enable_windows_update: checked })
                    }
                  />
                </div>
              </div>

              {/* Profil logiciels */}
              <div className="border border-dark-600 rounded-lg p-4">
                <h3 className="text-sm font-medium text-dark-200 mb-4 flex items-center gap-2">
                  <Package size={16} />
                  Profil logiciels (optionnel)
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {SOFTWARE_PROFILES.map((profile) => (
                    <label
                      key={profile.id}
                      className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                        formData.software_profile === profile.id
                          ? 'border-primary-500 bg-primary-500/10'
                          : 'border-dark-600 hover:border-dark-500'
                      }`}
                    >
                      <input
                        type="radio"
                        name="software_profile"
                        value={profile.id}
                        checked={formData.software_profile === profile.id}
                        onChange={(e) =>
                          setFormData({ ...formData, software_profile: e.target.value })
                        }
                        className="sr-only"
                      />
                      <p className="font-medium text-white">{profile.name}</p>
                      <p className="text-xs text-dark-400 mt-1">{profile.description}</p>
                    </label>
                  ))}
                  <label
                    className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                      formData.software_profile === ''
                        ? 'border-primary-500 bg-primary-500/10'
                        : 'border-dark-600 hover:border-dark-500'
                    }`}
                  >
                    <input
                      type="radio"
                      name="software_profile"
                      value=""
                      checked={formData.software_profile === ''}
                      onChange={() => setFormData({ ...formData, software_profile: '' })}
                      className="sr-only"
                    />
                    <p className="font-medium text-white">Aucun</p>
                    <p className="text-xs text-dark-400 mt-1">Pas de logiciels supplémentaires</p>
                  </label>
                </div>
              </div>

              {/* Jonction domaine AD */}
              <div className="border border-dark-600 rounded-lg p-4">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <Building2 size={18} className="text-dark-400" />
                    <div>
                      <span className="font-medium text-white">Joindre un domaine Active Directory</span>
                      <p className="text-sm text-dark-400">Intégrer la VM au domaine AD</p>
                    </div>
                  </div>
                  <Switch
                    checked={formData.join_domain}
                    onChange={(checked) => setFormData({ ...formData, join_domain: checked })}
                  />
                </div>

                {formData.join_domain && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t border-dark-600">
                    <Input
                      label="Nom du domaine"
                      value={formData.domain_name}
                      onChange={(e) =>
                        setFormData({ ...formData, domain_name: e.target.value })
                      }
                      placeholder="exemple.local"
                      required
                    />
                    <Input
                      label="Utilisateur (domaine\\user)"
                      value={formData.domain_user}
                      onChange={(e) =>
                        setFormData({ ...formData, domain_user: e.target.value })
                      }
                      placeholder="DOMAINE\\admin"
                      required
                    />
                    <Input
                      label="Mot de passe domaine"
                      type="password"
                      value={formData.domain_password}
                      onChange={(e) =>
                        setFormData({ ...formData, domain_password: e.target.value })
                      }
                      placeholder="••••••••"
                    />
                    <Input
                      label="OU cible (optionnel)"
                      value={formData.domain_ou}
                      onChange={(e) =>
                        setFormData({ ...formData, domain_ou: e.target.value })
                      }
                      placeholder="OU=Servers,DC=exemple,DC=local"
                    />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Étape 5: Résumé */}
          {currentStep === 5 && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-semibold text-white mb-2">
                  Résumé du déploiement
                </h2>
                <p className="text-dark-400">
                  Vérifiez les informations avant de lancer le déploiement.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {/* Infrastructure */}
                <div className="bg-dark-700/50 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-dark-400 mb-3 flex items-center gap-2">
                    <Server size={14} />
                    Infrastructure
                  </h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-dark-300">Hyperviseur</span>
                      <span className="text-white font-medium">
                        {selectedHypervisor?.name || '-'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-dark-300">Template</span>
                      <span className="text-white font-medium">
                        {selectedTemplate?.name || '-'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Configuration VM */}
                <div className="bg-dark-700/50 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-dark-400 mb-3 flex items-center gap-2">
                    <Cpu size={14} />
                    Machine virtuelle
                  </h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-dark-300">Nom</span>
                      <span className="text-white font-medium">{formData.vm_name || '-'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-dark-300">CPU / RAM / Disque</span>
                      <span className="text-white font-medium">
                        {formData.cpu_count} vCPU / {formatMemory(formData.memory_mb)} / {formData.disk_size_gb} GB
                      </span>
                    </div>
                  </div>
                </div>

                {/* Réseau */}
                <div className="bg-dark-700/50 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-dark-400 mb-3 flex items-center gap-2">
                    <Network size={14} />
                    Réseau
                  </h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-dark-300">Switch</span>
                      <span className="text-white font-medium">
                        {formData.network_switch}
                        {formData.vlan_id && ` (VLAN ${formData.vlan_id})`}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-dark-300">IP</span>
                      <span className="text-white font-medium">
                        {formData.use_static_ip ? formData.ip_address : 'DHCP'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Services */}
                <div className="bg-dark-700/50 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-dark-400 mb-3 flex items-center gap-2">
                    <Shield size={14} />
                    Services
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {formData.enable_rdp && (
                      <span className="px-2 py-1 bg-blue-500/20 text-blue-400 text-xs rounded">RDP</span>
                    )}
                    {formData.enable_winrm && (
                      <span className="px-2 py-1 bg-purple-500/20 text-purple-400 text-xs rounded">WinRM</span>
                    )}
                    {formData.enable_ssh && (
                      <span className="px-2 py-1 bg-green-500/20 text-green-400 text-xs rounded">SSH</span>
                    )}
                    {formData.enable_windows_update && (
                      <span className="px-2 py-1 bg-yellow-500/20 text-yellow-400 text-xs rounded">Windows Update</span>
                    )}
                  </div>
                </div>

                {/* Logiciels */}
                <div className="bg-dark-700/50 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-dark-400 mb-3 flex items-center gap-2">
                    <Package size={14} />
                    Logiciels
                  </h3>
                  <div className="text-sm">
                    {selectedProfile ? (
                      <div>
                        <span className="text-white font-medium">{selectedProfile.name}</span>
                        <p className="text-xs text-dark-400 mt-1">{selectedProfile.description}</p>
                      </div>
                    ) : (
                      <span className="text-dark-400">Aucun profil sélectionné</span>
                    )}
                  </div>
                </div>

                {/* Domaine */}
                <div className="bg-dark-700/50 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-dark-400 mb-3 flex items-center gap-2">
                    <Building2 size={14} />
                    Domaine AD
                  </h3>
                  <div className="text-sm">
                    {formData.join_domain ? (
                      <div className="space-y-1">
                        <span className="text-white font-medium">{formData.domain_name}</span>
                        {formData.domain_ou && (
                          <p className="text-xs text-dark-400">OU: {formData.domain_ou}</p>
                        )}
                      </div>
                    ) : (
                      <span className="text-dark-400">Pas de jonction au domaine</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Navigation */}
          <div className="flex items-center justify-between mt-8 pt-6 border-t border-dark-700">
            <Button
              variant="secondary"
              leftIcon={<ChevronLeft size={18} />}
              onClick={handlePrevious}
              disabled={currentStep === 1}
            >
              Précédent
            </Button>

            {currentStep < 5 ? (
              <Button
                rightIcon={<ChevronRight size={18} />}
                onClick={handleNext}
                disabled={!canProceed}
              >
                Suivant
              </Button>
            ) : (
              <Button
                leftIcon={<Rocket size={18} />}
                onClick={handleSubmit}
                isLoading={createMutation.isPending}
                disabled={!canProceed}
              >
                Lancer le déploiement
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Modal de création de switch */}
      <Modal
        isOpen={isCreateSwitchModalOpen}
        onClose={() => setIsCreateSwitchModalOpen(false)}
        title="Créer un switch virtuel"
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsCreateSwitchModalOpen(false)}>
              Annuler
            </Button>
            <Button
              onClick={() => createSwitchMutation.mutate(newSwitchData)}
              isLoading={createSwitchMutation.isPending}
              disabled={!newSwitchData.name || (newSwitchData.switch_type === 'External' && !newSwitchData.net_adapter_name)}
            >
              Créer le switch
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Nom du switch"
            value={newSwitchData.name}
            onChange={(e) => setNewSwitchData({ ...newSwitchData, name: e.target.value })}
            placeholder="Mon-Switch"
            required
          />

          <Select
            label="Type de switch"
            value={newSwitchData.switch_type}
            onChange={(e) => setNewSwitchData({ ...newSwitchData, switch_type: e.target.value as SwitchType })}
            options={[
              { value: 'Internal', label: 'Interne - Communication entre VMs et l\'hôte' },
              { value: 'External', label: 'Externe - Accès au réseau physique' },
              { value: 'Private', label: 'Privé - Communication entre VMs uniquement' },
            ]}
            helperText={
              newSwitchData.switch_type === 'External'
                ? 'Les VMs pourront accéder au réseau physique'
                : newSwitchData.switch_type === 'Internal'
                ? 'Les VMs pourront communiquer entre elles et avec l\'hôte'
                : 'Les VMs pourront uniquement communiquer entre elles'
            }
          />

          {newSwitchData.switch_type === 'External' && (
            <>
              <Select
                label="Adaptateur réseau physique"
                value={newSwitchData.net_adapter_name}
                onChange={(e) => setNewSwitchData({ ...newSwitchData, net_adapter_name: e.target.value })}
                options={
                  adaptersLoading
                    ? [{ value: '', label: 'Chargement...', disabled: true }]
                    : physicalAdapters.length === 0
                    ? [{ value: '', label: 'Aucun adaptateur disponible', disabled: true }]
                    : [
                        { value: '', label: 'Sélectionner un adaptateur...', disabled: true },
                        ...physicalAdapters.map((adapter) => ({
                          value: adapter.name,
                          label: `${adapter.name} - ${adapter.description} (${adapter.link_speed})`,
                        })),
                      ]
                }
                required
              />

              <Switch
                label="Autoriser l'OS hôte à utiliser l'adaptateur"
                description="Permet à l'hôte Hyper-V de partager l'adaptateur réseau avec les VMs"
                checked={newSwitchData.allow_management_os}
                onChange={(checked) => setNewSwitchData({ ...newSwitchData, allow_management_os: checked })}
              />
            </>
          )}

          <Input
            label="Notes (optionnel)"
            value={newSwitchData.notes}
            onChange={(e) => setNewSwitchData({ ...newSwitchData, notes: e.target.value })}
            placeholder="Description du switch..."
          />
        </div>
      </Modal>
    </div>
  );
}
