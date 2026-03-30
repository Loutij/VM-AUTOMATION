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
  AlertTriangle,
  Terminal,
} from 'lucide-react';
import { Header } from '../components/layout';
import { Button, Input, Select, Switch, Modal, useToast } from '../components/ui';
import { hypervisorsApi, templatesApi, deploymentsApi, softwareApi } from '../services/api';
import type { DeploymentConfig, SwitchType, SoftwareProfile, SoftwarePackage, ConfigField, StorageLocation } from '../types';

// Import du composant Marketplace pour la sélection à la carte
import { Marketplace } from './Marketplace';

// Services Windows
const WINDOWS_SERVICES = [
  { id: 'rdp', name: 'Bureau à distance (RDP)', description: 'Accès distant via RDP', default: true },
  { id: 'winrm', name: 'WinRM', description: 'Gestion PowerShell à distance', default: true },
  { id: 'ssh', name: 'OpenSSH Server', description: 'Accès SSH', default: false },
];

// Services Linux
const LINUX_SERVICES = [
  { id: 'ssh', name: 'OpenSSH Server', description: 'Accès distant via SSH', default: true },
];

interface DeploymentFormData {
  // Étape 1: Sélection hyperviseur et template
  hypervisor_id: string;
  os_template_id: string;
  // Étape 2: Configuration VM
  vm_name: string;
  hostname: string;
  cpu_count: number;
  ram_gb: number;
  disk_gb: number;
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
  // Linux-specific
  ssh_key: string;
  extra_packages: string;
  post_script: string;
  // VMware/ESXi-specific
  datastore: string;
  resource_pool: string;
  vm_folder: string;
  disk_format: string; // "thin" | "thick" | "eagerzeroedthick"
}

const defaultFormData: DeploymentFormData = {
  hypervisor_id: '',
  os_template_id: '',
  vm_name: '',
  hostname: '',
  cpu_count: 2,
  ram_gb: 4,
  disk_gb: 60,
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
  ssh_key: '',
  extra_packages: '',
  post_script: '',
  datastore: '',
  resource_pool: '',
  vm_folder: '',
  disk_format: 'thin',
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

  // State pour afficher les erreurs de validation
  const [showErrors, setShowErrors] = useState(false);

  // State pour le modal de création de switch
  const [isCreateSwitchModalOpen, setIsCreateSwitchModalOpen] = useState(false);
  const [newSwitchData, setNewSwitchData] = useState({
    name: '',
    switch_type: 'Internal' as SwitchType,
    net_adapter_name: '',
    allow_management_os: true,
    notes: '',
  });

  // State pour le modal de sélection de logiciels (marketplace)
  const [isMarketplaceModalOpen, setIsMarketplaceModalOpen] = useState(false);
  
  // State pour les configurations des packages
  const [packageConfigs, setPackageConfigs] = useState<Record<string, Record<string, unknown>>>({});
  const [configModalPackage, setConfigModalPackage] = useState<SoftwarePackage | null>(null);
  const [pendingConfigPackages, setPendingConfigPackages] = useState<SoftwarePackage[]>([]);

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

  // Fetch profils logiciels depuis la marketplace
  const { data: softwareProfilesData } = useQuery({
    queryKey: ['software-profiles'],
    queryFn: softwareApi.getProfiles,
  });

  const softwareProfiles: SoftwareProfile[] = softwareProfilesData?.profiles || [];

  // Fetch tous les packages pour obtenir leurs config_schema
  const { data: allSoftwareData } = useQuery({
    queryKey: ['all-software'],
    queryFn: () => softwareApi.list({ page_size: 500 }),
  });

  const allSoftware: SoftwarePackage[] = allSoftwareData?.items || [];

  // Fetch emplacements de stockage (dépend de l'hyperviseur sélectionné, Hyper-V uniquement)
  const selectedHypervisor = hypervisors.find((h) => h.id === formData.hypervisor_id);
  const isVMware = selectedHypervisor?.type === 'vmware';

  const { data: storageLocations = [], isLoading: storageLoading } = useQuery({
    queryKey: ['storage-locations', formData.hypervisor_id],
    queryFn: () => hypervisorsApi.getStorageLocations(formData.hypervisor_id, 20),
    enabled: !!formData.hypervisor_id && !isVMware,
  });

  // VMware-specific: Fetch datastores
  const { data: datastores = [], isLoading: datastoresLoading } = useQuery({
    queryKey: ['datastores', formData.hypervisor_id],
    queryFn: () => hypervisorsApi.listDatastores(formData.hypervisor_id),
    enabled: !!formData.hypervisor_id && isVMware,
  });

  // VMware-specific: Fetch resource pools
  const { data: resourcePools = [], isLoading: resourcePoolsLoading } = useQuery({
    queryKey: ['resource-pools', formData.hypervisor_id],
    queryFn: () => hypervisorsApi.listResourcePools(formData.hypervisor_id),
    enabled: !!formData.hypervisor_id && isVMware,
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
    // Note: formData.network_switch is intentionally excluded to prevent infinite loops
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [switches]);

  // Sélectionner automatiquement le disque C: par défaut ou le recommandé
  useEffect(() => {
    if (storageLocations.length > 0 && !formData.vhdx_path) {
      // Chercher le disque C: par défaut
      const defaultDisk = storageLocations.find((s: StorageLocation) => s.is_default);
      // Sinon prendre le recommandé
      const recommendedDisk = storageLocations.find((s: StorageLocation) => s.is_recommended);
      // Sinon prendre le premier
      const selectedDisk = defaultDisk || recommendedDisk || storageLocations[0];
      if (selectedDisk) {
        setFormData((prev) => ({ ...prev, vhdx_path: selectedDisk.path }));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageLocations]);

  // VMware: auto-sélectionner le premier datastore
  useEffect(() => {
    if (datastores.length > 0 && !formData.datastore && isVMware) {
      setFormData((prev) => ({ ...prev, datastore: datastores[0].name }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datastores, isVMware]);

  // Mutation pour créer le déploiement
  const createMutation = useMutation({
    mutationFn: (data: {
      vm_name: string;
      hypervisor_id: string;
      os_template_id: string;
      config: DeploymentConfig;
    }) => deploymentsApi.create(data),
    onSuccess: (deployment) => {
      addToast({
        type: 'success',
        title: 'Déploiement créé',
        message: `Le déploiement "${deployment.name}" a été lancé.`,
      });
      queryClient.invalidateQueries({ queryKey: ['deployments'] });
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

  // Template et profil sélectionnés
  const selectedTemplate = templates.find((t) => t.id === formData.os_template_id);
  const selectedProfile = softwareProfiles.find((p) => p.name === formData.software_profile);

  // Détection de la famille d'OS
  const isWindows = selectedTemplate?.os_family === 'windows' || !selectedTemplate;
  const isLinux = selectedTemplate?.os_family === 'linux';

  // Validation par étape avec messages d'erreur
  const getValidationErrors = (step: number): string[] => {
    const errors: string[] = [];
    switch (step) {
      case 1:
        if (!formData.hypervisor_id) errors.push('Sélectionnez un hyperviseur');
        if (!formData.os_template_id) errors.push('Sélectionnez un template OS');
        break;
      case 2:
        if (!formData.vm_name) errors.push('Le nom de la VM est obligatoire');
        if (formData.vm_name && !/^[a-zA-Z0-9_-]+$/.test(formData.vm_name)) {
          errors.push('Le nom de la VM ne doit contenir que des lettres, chiffres, tirets et underscores');
        }
        if (formData.cpu_count < 1) errors.push('Le nombre de CPUs doit être au moins 1');
        if (formData.ram_gb < 1) errors.push('La RAM doit être d\'au moins 1 Go');
        if (formData.disk_gb < 20) errors.push('Le disque doit être d\'au moins 20 Go');
        break;
      case 3:
        if (formData.use_static_ip && !formData.ip_address) {
          errors.push('L\'adresse IP est obligatoire pour la configuration statique');
        }
        if (formData.use_static_ip && formData.ip_address && 
            !/^(\d{1,3}\.){3}\d{1,3}$/.test(formData.ip_address)) {
          errors.push('Adresse IP invalide');
        }
        break;
      case 4:
        if (formData.admin_password !== formData.admin_password_confirm) {
          errors.push('Les mots de passe ne correspondent pas');
        }
        if (isWindows && formData.join_domain && !formData.domain_name) {
          errors.push('Le nom du domaine est obligatoire');
        }
        if (isWindows && formData.join_domain && !formData.domain_user) {
          errors.push('L\'utilisateur du domaine est obligatoire');
        }
        break;
    }
    return errors;
  };

  const validateStep = (step: number): boolean => {
    return getValidationErrors(step).length === 0;
  };

  const canProceed = validateStep(currentStep);
  const currentErrors = getValidationErrors(currentStep);

  const handleNext = () => {
    if (canProceed && currentStep < 5) {
      setShowErrors(false);
      setCurrentStep(currentStep + 1);
    } else {
      setShowErrors(true);
      // Afficher un toast avec les erreurs
      const errors = getValidationErrors(currentStep);
      if (errors.length > 0) {
        addToast({
          type: 'error',
          title: 'Formulaire incomplet',
          message: errors[0],
        });
      }
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
    const config: DeploymentConfig = {
      vm_name: formData.vm_name,
      cpu_count: formData.cpu_count,
      ram_gb: formData.ram_gb,
      disk_gb: formData.disk_gb,
      vhdx_path: formData.vhdx_path || undefined, // Emplacement du disque virtuel
      hostname: formData.hostname || formData.vm_name,
      admin_password: formData.admin_password || undefined,
      network_switch: formData.network_switch || undefined,
    };

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

    // Configuration spécifique Windows
    if (isWindows) {
      // Services à activer (RDP, WinRM, SSH)
      config.services = {
        enable_rdp: formData.enable_rdp,
        enable_winrm: formData.enable_winrm,
        enable_ssh: formData.enable_ssh,
      };

      // Windows Update
      config.enable_windows_update = formData.enable_windows_update;

      // Domaine AD
      if (formData.join_domain) {
        config.domain_join = {
          domain: formData.domain_name,
          user: formData.domain_user,
          password: formData.domain_password,
          ou: formData.domain_ou || undefined,
        };
      }
    }

    // Configuration spécifique Linux
    if (isLinux) {
      config.services = {
        enable_rdp: false,
        enable_winrm: false,
        enable_ssh: formData.enable_ssh,
      };
      config.ssh_keys = formData.ssh_key ? [formData.ssh_key] : [];
      config.extra_packages = formData.extra_packages
        ? formData.extra_packages.split(',').map(p => p.trim()).filter(Boolean)
        : [];
      config.post_commands = formData.post_script
        ? formData.post_script.split('\n').filter(Boolean)
        : [];
    }

    // Profil logiciels et packages
    if (formData.software_profile) {
      config.software_profile = formData.software_profile;
      // Les packages du profil seront résolus côté backend
    }

    // Packages personnalisés supplémentaires
    if (formData.custom_packages && formData.custom_packages.length > 0) {
      config.packages = formData.custom_packages;
      // Inclure les configurations des packages
      if (Object.keys(packageConfigs).length > 0) {
        config.package_configs = packageConfigs;
      }
    }

    // Commandes post-install personnalisées
    if (formData.post_install_commands.length > 0) {
      config.post_install_commands = formData.post_install_commands;
    }

    // VMware/ESXi-specific config
    if (isVMware) {
      // Override vhdx_path since it's Hyper-V specific
      delete config.vhdx_path;
      (config as Record<string, unknown>).datastore = formData.datastore || undefined;
      (config as Record<string, unknown>).resource_pool = formData.resource_pool || undefined;
      (config as Record<string, unknown>).vm_folder = formData.vm_folder || undefined;
      (config as Record<string, unknown>).disk_format = formData.disk_format || 'thin';
    }

    createMutation.mutate({
      vm_name: formData.vm_name,
      hypervisor_id: formData.hypervisor_id,
      os_template_id: formData.os_template_id,
      config: config,
    });
  };

  // Appliquer les valeurs par défaut du template
  const handleTemplateChange = (templateId: string) => {
    const template = templates.find((t) => t.id === templateId);
    const templateIsLinux = template?.os_family === 'linux';
    setFormData((prev) => ({
      ...prev,
      os_template_id: templateId,
      cpu_count: template?.min_cpu || prev.cpu_count,
      ram_gb: template?.min_ram_gb || prev.ram_gb,
      disk_gb: template?.min_disk_gb || prev.disk_gb,
      // Adapter les services selon l'OS
      enable_rdp: templateIsLinux ? false : true,
      enable_winrm: templateIsLinux ? false : true,
      enable_ssh: templateIsLinux ? true : prev.enable_ssh,
      enable_windows_update: templateIsLinux ? false : true,
      // Réinitialiser la jonction domaine pour Linux
      join_domain: templateIsLinux ? false : prev.join_domain,
    }));
  };


  // Gérer la fermeture du modal Marketplace et détecter les packages nécessitant configuration
  const handleMarketplaceClose = () => {
    setIsMarketplaceModalOpen(false);
    
    // Trouver les packages sélectionnés qui ont un config_schema
    const packagesNeedingConfig = formData.custom_packages
      .map(pkgName => allSoftware.find(s => s.name === pkgName))
      .filter((pkg): pkg is SoftwarePackage => 
        pkg !== undefined && 
        Boolean(pkg.config_schema?.fields) && 
        (pkg.config_schema?.fields?.length ?? 0) > 0 &&
        !packageConfigs[pkg.name] // Pas encore configuré
      );
    
    if (packagesNeedingConfig.length > 0) {
      setPendingConfigPackages(packagesNeedingConfig);
      setConfigModalPackage(packagesNeedingConfig[0]);
    }
  };

  // Sauvegarder la configuration d'un package
  const handleSavePackageConfig = (pkgName: string, config: Record<string, unknown>) => {
    setPackageConfigs(prev => ({ ...prev, [pkgName]: config }));
    
    // Passer au package suivant ou fermer
    const remaining = pendingConfigPackages.filter(p => p.name !== pkgName);
    setPendingConfigPackages(remaining);
    
    if (remaining.length > 0) {
      setConfigModalPackage(remaining[0]);
    } else {
      setConfigModalPackage(null);
    }
  };

  // Ignorer la configuration d'un package
  const handleSkipPackageConfig = () => {
    if (configModalPackage) {
      const remaining = pendingConfigPackages.filter(p => p.name !== configModalPackage.name);
      setPendingConfigPackages(remaining);
      
      if (remaining.length > 0) {
        setConfigModalPackage(remaining[0]);
      } else {
        setConfigModalPackage(null);
      }
    }
  };

  return (
    <div className="min-h-screen bg-light-100 dark:bg-dark-900">
      <Header title="Nouveau déploiement" />
      <div className="p-4 sm:p-6">
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
          <div className="flex items-center justify-between overflow-x-auto pb-2">
            {steps.map((step, index) => (
              <div key={step.id} className="flex items-center flex-shrink-0">
                <div
                  className={`flex items-center gap-2 cursor-pointer ${
                    currentStep === step.id
                      ? 'text-oto-500'
                      : currentStep > step.id
                      ? 'text-green-500'
                      : 'text-gray-400 dark:text-dark-400'
                  }`}
                  onClick={() => step.id < currentStep && setCurrentStep(step.id)}
                  title={step.name}
                >
                  <div
                    className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
                      currentStep === step.id
                        ? 'bg-oto-600'
                        : currentStep > step.id
                        ? 'bg-green-600'
                        : 'bg-light-200 dark:bg-dark-700'
                    }`}
                  >
                    {currentStep > step.id ? (
                      <Check size={20} />
                    ) : (
                      <step.icon size={20} />
                    )}
                  </div>
                  <span className="font-medium hidden lg:inline whitespace-nowrap">{step.name}</span>
                </div>
                {index < steps.length - 1 && (
                  <ChevronRight size={20} className="mx-1 md:mx-3 text-gray-300 dark:text-dark-600 flex-shrink-0" />
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
                <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                  Sélection de l'infrastructure
                </h2>
                <p className="text-gray-500 dark:text-dark-400">
                  Choisissez l'hyperviseur et le template OS pour votre VM.
                </p>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Sélection hyperviseur */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-dark-200 mb-2">
                    <Server size={16} className="inline mr-2" />
                    Hyperviseur
                  </label>
                  {hypervisorsLoading ? (
                    <div className="h-12 bg-light-200 dark:bg-dark-700 animate-pulse rounded-lg" />
                  ) : hypervisors.length === 0 ? (
                    <div className="p-4 bg-light-200 dark:bg-dark-700 rounded-lg text-gray-500 dark:text-dark-400 text-center">
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
                              ? 'border-oto-500 bg-oto-500/10'
                              : 'border-light-300 dark:border-dark-600 hover:border-oto-300 dark:hover:border-dark-500 bg-white dark:bg-dark-700/50'
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
                                ? 'border-oto-500'
                                : 'border-gray-300 dark:border-dark-500'
                            }`}
                          >
                            {formData.hypervisor_id === h.id && (
                              <div className="w-2 h-2 rounded-full bg-oto-500" />
                            )}
                          </div>
                          <div className="flex-1">
                            <p className="font-medium text-gray-900 dark:text-white">{h.name}</p>
                            <p className="text-sm text-gray-500 dark:text-dark-400">
                              {(h.type || 'hyperv').toUpperCase()} • {h.host}
                            </p>
                          </div>
                          <div
                            className={`w-2 h-2 rounded-full ${
                              h.is_active ? 'bg-green-500' : 'bg-red-500'
                            }`}
                          />
                        </label>
                      ))}
                    </div>
                  )}
                </div>

                {/* Sélection template */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-dark-200 mb-2">
                    <FileCode size={16} className="inline mr-2" />
                    Template OS
                  </label>
                  {templatesLoading ? (
                    <div className="h-12 bg-light-200 dark:bg-dark-700 animate-pulse rounded-lg" />
                  ) : templates.length === 0 ? (
                    <div className="p-4 bg-light-200 dark:bg-dark-700 rounded-lg text-gray-500 dark:text-dark-400 text-center">
                      Aucun template disponible.{' '}
                      <button
                        onClick={() => navigate('/templates')}
                        className="text-oto-500 hover:underline"
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
                            formData.os_template_id === t.id
                              ? 'border-oto-500 bg-oto-500/10'
                              : 'border-light-300 dark:border-dark-600 hover:border-oto-300 dark:hover:border-dark-500 bg-white dark:bg-dark-700/50'
                          }`}
                        >
                          <input
                            type="radio"
                            name="template"
                            value={t.id}
                            checked={formData.os_template_id === t.id}
                            onChange={() => handleTemplateChange(t.id)}
                            className="sr-only"
                          />
                          <div
                            className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
                              formData.os_template_id === t.id
                                ? 'border-oto-500'
                                : 'border-gray-300 dark:border-dark-500'
                            }`}
                          >
                            {formData.os_template_id === t.id && (
                              <div className="w-2 h-2 rounded-full bg-oto-500" />
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
                            <p className="font-medium text-gray-900 dark:text-white">{t.name}</p>
                            <p className="text-sm text-gray-500 dark:text-dark-400">{t.os_type}</p>
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
                <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                  Configuration des ressources
                </h2>
                <p className="text-gray-500 dark:text-dark-400">
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
                  <label className="block text-sm font-medium text-gray-700 dark:text-dark-200 mb-2">
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
                      className="flex-1 h-2 bg-light-200 dark:bg-dark-700 rounded-full appearance-none cursor-pointer accent-oto-500"
                    />
                    <span className="w-12 text-center font-medium text-gray-900 dark:text-white">
                      {formData.cpu_count}
                    </span>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-dark-200 mb-2">
                    <MemoryStick size={16} className="inline mr-2" />
                    RAM
                  </label>
                  <Select
                    value={formData.ram_gb.toString()}
                    onChange={(e) =>
                      setFormData({ ...formData, ram_gb: parseInt(e.target.value) })
                    }
                    options={[
                      { value: '1', label: '1 Go' },
                      { value: '2', label: '2 Go' },
                      { value: '4', label: '4 Go' },
                      { value: '8', label: '8 Go' },
                      { value: '16', label: '16 Go' },
                      { value: '32', label: '32 Go' },
                    ]}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-dark-200 mb-2">
                    <HardDrive size={16} className="inline mr-2" />
                    Disque
                  </label>
                  <Select
                    value={formData.disk_gb.toString()}
                    onChange={(e) =>
                      setFormData({ ...formData, disk_gb: parseInt(e.target.value) })
                    }
                    options={[
                      { value: '40', label: '40 Go' },
                      { value: '60', label: '60 Go' },
                      { value: '80', label: '80 Go' },
                      { value: '100', label: '100 Go' },
                      { value: '120', label: '120 Go' },
                      { value: '200', label: '200 Go' },
                      { value: '500', label: '500 Go' },
                    ]}
                  />
                </div>
              </div>

              {/* VMware: Datastore, Resource Pool, VM Folder, Disk Format */}
              {isVMware ? (
                <div className="space-y-6">
                  {/* Datastore */}
                  <div className="border border-light-300 dark:border-dark-600 rounded-lg p-4">
                    <h3 className="text-sm font-medium text-gray-700 dark:text-dark-200 mb-4 flex items-center gap-2">
                      <HardDrive size={16} />
                      Datastore
                    </h3>
                    {datastoresLoading ? (
                      <div className="flex items-center gap-2 text-gray-500 dark:text-dark-400 py-4">
                        <Loader2 size={16} className="animate-spin" />
                        Chargement des datastores...
                      </div>
                    ) : datastores.length > 0 ? (
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                        {datastores.map((ds) => {
                          const isSelected = formData.datastore === ds.name;
                          const usedGb = ds.capacity_gb - ds.free_gb;
                          const usedPercent = ds.capacity_gb > 0 ? (usedGb / ds.capacity_gb) * 100 : 0;
                          return (
                            <label
                              key={ds.name}
                              className={`p-4 rounded-lg border cursor-pointer transition-all ${
                                isSelected
                                  ? 'border-oto-500 bg-oto-500/10 ring-1 ring-oto-500'
                                  : 'border-light-300 dark:border-dark-600 hover:border-oto-300 dark:hover:border-dark-500 bg-white dark:bg-dark-700/30'
                              }`}
                            >
                              <input
                                type="radio"
                                name="datastore"
                                value={ds.name}
                                checked={isSelected}
                                onChange={() => setFormData({ ...formData, datastore: ds.name })}
                                className="sr-only"
                              />
                              <div className="flex items-center gap-2 mb-2">
                                <HardDrive size={18} className={isSelected ? 'text-oto-500' : 'text-gray-400 dark:text-dark-400'} />
                                <span className="font-bold text-gray-900 dark:text-white">{ds.name}</span>
                              </div>
                              <span className="text-xs px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded">{ds.type}</span>

                              {/* Barre de progression */}
                              <div className="h-2 bg-light-200 dark:bg-dark-600 rounded-full overflow-hidden mb-2 mt-2">
                                <div
                                  className={`h-full rounded-full transition-all ${
                                    usedPercent > 90 ? 'bg-red-500' :
                                    usedPercent > 70 ? 'bg-yellow-500' :
                                    'bg-oto-500'
                                  }`}
                                  style={{ width: `${usedPercent}%` }}
                                />
                              </div>

                              <div className="flex justify-between text-xs">
                                <span className="text-gray-500 dark:text-dark-400">
                                  {usedGb.toFixed(1)} Go utilisés
                                </span>
                                <span className={`font-medium ${
                                  ds.free_gb < 50 ? 'text-red-400' :
                                  ds.free_gb < 100 ? 'text-yellow-400' :
                                  'text-green-400'
                                }`}>
                                  {ds.free_gb.toFixed(1)} Go libres
                                </span>
                              </div>
                              <p className="text-xs text-gray-400 dark:text-dark-500 mt-1">
                                Capacité : {ds.capacity_gb.toFixed(1)} Go
                              </p>
                            </label>
                          );
                        })}
                      </div>
                    ) : (
                      <p className="text-sm text-gray-500 dark:text-dark-400">Aucun datastore disponible.</p>
                    )}
                  </div>

                  {/* Resource Pool (optional) */}
                  <div className="border border-light-300 dark:border-dark-600 rounded-lg p-4">
                    <h3 className="text-sm font-medium text-gray-700 dark:text-dark-200 mb-4 flex items-center gap-2">
                      <Server size={16} />
                      Resource Pool (optionnel)
                    </h3>
                    {resourcePoolsLoading ? (
                      <div className="flex items-center gap-2 text-gray-500 dark:text-dark-400 py-4">
                        <Loader2 size={16} className="animate-spin" />
                        Chargement des resource pools...
                      </div>
                    ) : resourcePools.length > 0 ? (
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                        {/* Option aucun */}
                        <label
                          className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                            !formData.resource_pool
                              ? 'border-oto-500 bg-oto-500/10'
                              : 'border-light-300 dark:border-dark-600 hover:border-oto-300 dark:hover:border-dark-500'
                          }`}
                        >
                          <input
                            type="radio"
                            name="resource_pool"
                            value=""
                            checked={!formData.resource_pool}
                            onChange={() => setFormData({ ...formData, resource_pool: '' })}
                            className="sr-only"
                          />
                          <p className="font-medium text-gray-900 dark:text-white">Par défaut</p>
                          <p className="text-xs text-gray-500 dark:text-dark-400 mt-1">Pas de resource pool spécifique</p>
                        </label>
                        {resourcePools.map((rp) => (
                          <label
                            key={rp.name}
                            className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                              formData.resource_pool === rp.name
                                ? 'border-oto-500 bg-oto-500/10'
                                : 'border-light-300 dark:border-dark-600 hover:border-oto-300 dark:hover:border-dark-500'
                            }`}
                          >
                            <input
                              type="radio"
                              name="resource_pool"
                              value={rp.name}
                              checked={formData.resource_pool === rp.name}
                              onChange={() => setFormData({ ...formData, resource_pool: rp.name })}
                              className="sr-only"
                            />
                            <p className="font-medium text-gray-900 dark:text-white">{rp.name}</p>
                            <div className="text-xs text-gray-500 dark:text-dark-400 mt-1">
                              {rp.cpu_limit != null && <span>CPU: {rp.cpu_limit} MHz</span>}
                              {rp.cpu_limit != null && rp.memory_limit_gb != null && <span> / </span>}
                              {rp.memory_limit_gb != null && <span>RAM: {rp.memory_limit_gb} Go</span>}
                            </div>
                          </label>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-gray-500 dark:text-dark-400">Aucun resource pool disponible.</p>
                    )}
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* VM Folder (optional) */}
                    <Input
                      label="Dossier VM (optionnel)"
                      value={formData.vm_folder}
                      onChange={(e) => setFormData({ ...formData, vm_folder: e.target.value })}
                      placeholder="Production/WebServers"
                      helperText="Dossier dans l'inventaire vSphere"
                    />

                    {/* Disk Format */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-dark-200 mb-2">
                        <HardDrive size={16} className="inline mr-2" />
                        Format de disque
                      </label>
                      <Select
                        value={formData.disk_format}
                        onChange={(e) =>
                          setFormData({ ...formData, disk_format: e.target.value })
                        }
                        options={[
                          { value: 'thin', label: 'Thin Provisioning' },
                          { value: 'thick', label: 'Thick (Lazy Zeroed)' },
                          { value: 'eagerzeroedthick', label: 'Thick (Eager Zeroed)' },
                        ]}
                      />
                      <p className="text-xs text-gray-500 dark:text-dark-400 mt-1">
                        Thin Provisioning alloue l'espace au fur et à mesure
                      </p>
                    </div>
                  </div>
                </div>
              ) : (
              /* Hyper-V: Emplacement du disque virtuel */
              <div className="border border-light-300 dark:border-dark-600 rounded-lg p-4">
                <h3 className="text-sm font-medium text-gray-700 dark:text-dark-200 mb-4 flex items-center gap-2">
                  <FolderOpen size={16} />
                  Emplacement du disque virtuel
                </h3>

                {/* Sélecteur de disque visuel */}
                {storageLoading ? (
                  <div className="flex items-center gap-2 text-gray-500 dark:text-dark-400 py-4">
                    <Loader2 size={16} className="animate-spin" />
                    Chargement des disques disponibles...
                  </div>
                ) : storageLocations.length > 0 ? (
                  <div className="space-y-4">
                    <p className="text-xs text-gray-500 dark:text-dark-400 mb-3">Sélectionnez un disque pour stocker le fichier VHDX :</p>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                      {storageLocations.map((storage: StorageLocation) => {
                        const isSelected = formData.vhdx_path === storage.path;
                        const usedPercent = 100 - storage.percent_free;
                        return (
                          <label
                            key={storage.drive_letter}
                            className={`p-4 rounded-lg border cursor-pointer transition-all ${
                              isSelected
                                ? 'border-oto-500 bg-oto-500/10 ring-1 ring-oto-500'
                                : 'border-light-300 dark:border-dark-600 hover:border-oto-300 dark:hover:border-dark-500 bg-white dark:bg-dark-700/30'
                            }`}
                          >
                            <input
                              type="radio"
                              name="storage_location"
                              value={storage.path}
                              checked={isSelected}
                              onChange={() => setFormData({ ...formData, vhdx_path: storage.path })}
                              className="sr-only"
                            />
                            <div className="flex items-center justify-between mb-2">
                              <div className="flex items-center gap-2">
                                <HardDrive size={18} className={isSelected ? 'text-oto-500' : 'text-gray-400 dark:text-dark-400'} />
                                <span className="font-bold text-gray-900 dark:text-white text-lg">{storage.drive_letter}:</span>
                              </div>
                              <div className="flex gap-1">
                                {storage.is_default && (
                                  <span className="text-xs px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded">Défaut</span>
                                )}
                                {storage.is_recommended && (
                                  <span className="text-xs px-2 py-0.5 bg-green-500/20 text-green-400 rounded">Recommandé</span>
                                )}
                              </div>
                            </div>

                            {/* Barre de progression */}
                            <div className="h-2 bg-light-200 dark:bg-dark-600 rounded-full overflow-hidden mb-2">
                              <div
                                className={`h-full rounded-full transition-all ${
                                  usedPercent > 90 ? 'bg-red-500' :
                                  usedPercent > 70 ? 'bg-yellow-500' :
                                  'bg-oto-500'
                                }`}
                                style={{ width: `${usedPercent}%` }}
                              />
                            </div>

                            <div className="flex justify-between text-xs">
                              <span className="text-gray-500 dark:text-dark-400">
                                {storage.used_gb.toFixed(1)} Go utilisés
                              </span>
                              <span className={`font-medium ${
                                storage.free_gb < 50 ? 'text-red-400' :
                                storage.free_gb < 100 ? 'text-yellow-400' :
                                'text-green-400'
                              }`}>
                                {storage.free_gb.toFixed(1)} Go libres
                              </span>
                            </div>
                            <p className="text-xs text-gray-400 dark:text-dark-500 mt-1 truncate">{storage.path}</p>
                          </label>
                        );
                      })}

                      {/* Option chemin personnalisé */}
                      <label
                        className={`p-4 rounded-lg border border-dashed cursor-pointer transition-all ${
                          formData.vhdx_path && !storageLocations.some((s: StorageLocation) => s.path === formData.vhdx_path)
                            ? 'border-oto-500 bg-oto-500/10'
                            : 'border-gray-300 dark:border-dark-500 hover:border-oto-300 dark:hover:border-dark-400'
                        }`}
                      >
                        <input
                          type="radio"
                          name="storage_location"
                          value="custom"
                          checked={formData.vhdx_path !== '' && !storageLocations.some((s: StorageLocation) => s.path === formData.vhdx_path)}
                          onChange={() => setFormData({ ...formData, vhdx_path: '' })}
                          className="sr-only"
                        />
                        <div className="flex items-center gap-2 mb-2">
                          <FolderOpen size={18} className="text-gray-400 dark:text-dark-400" />
                          <span className="font-medium text-gray-600 dark:text-dark-300">Chemin personnalisé</span>
                        </div>
                        <p className="text-xs text-gray-500 dark:text-dark-400">Spécifier un chemin manuel</p>
                      </label>
                    </div>

                    {/* Champ chemin personnalisé */}
                    {(formData.vhdx_path === '' || !storageLocations.some((s: StorageLocation) => s.path === formData.vhdx_path)) && (
                      <Input
                        label="Chemin personnalisé"
                        value={formData.vhdx_path}
                        onChange={(e) => setFormData({ ...formData, vhdx_path: e.target.value })}
                        placeholder="D:\VMs\VirtualHardDisks"
                        helperText="Entrez le chemin complet du dossier"
                      />
                    )}
                  </div>
                ) : (
                  <div className="space-y-3">
                    <p className="text-xs text-gray-500 dark:text-dark-400">Aucun disque disponible détecté. Entrez le chemin manuellement :</p>
                    <Input
                      label="Chemin du fichier VHDX"
                      value={formData.vhdx_path}
                      onChange={(e) => setFormData({ ...formData, vhdx_path: e.target.value })}
                      placeholder="G:\HyperV\VirtualHardDisks"
                      helperText="Laissez vide pour utiliser l'emplacement par défaut."
                    />
                  </div>
                )}

                <div className="mt-3 p-3 bg-light-100 dark:bg-dark-700/50 rounded-lg">
                  <p className="text-xs text-gray-500 dark:text-dark-400">
                    <strong className="text-gray-600 dark:text-dark-300">Fichier créé :</strong>{' '}
                    <code className="bg-light-200 dark:bg-dark-600 px-1 rounded text-gray-700 dark:text-gray-300">
                      {formData.vhdx_path || 'G:\\HyperV\\VirtualHardDisks'}\\{formData.vm_name || 'ma-vm'}.vhdx
                    </code>
                  </p>
                </div>
              </div>
              )}
            </div>
          )}

          {/* Étape 3: Réseau */}
          {currentStep === 3 && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                  Configuration réseau
                </h2>
                <p className="text-gray-500 dark:text-dark-400">
                  Configurez le switch virtuel, VLAN et les paramètres IP.
                </p>
              </div>

              {/* Sélection du switch */}
              <div className="border border-light-300 dark:border-dark-600 rounded-lg p-4">
                <h3 className="text-sm font-medium text-gray-700 dark:text-dark-200 mb-4 flex items-center gap-2">
                  <Wifi size={16} />
                  Switch virtuel
                </h3>
                
                {switchesLoading ? (
                  <div className="flex items-center gap-2 text-gray-500 dark:text-dark-400">
                    <Loader2 size={16} className="animate-spin" />
                    Chargement des switches...
                  </div>
                ) : switches.length === 0 ? (
                  <div className="text-center py-4">
                    <Network size={32} className="mx-auto mb-2 text-gray-400 dark:text-dark-500" />
                    <p className="text-gray-500 dark:text-dark-400 mb-3">Aucun switch virtuel trouvé</p>
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
                              ? 'border-oto-500 bg-oto-500/10'
                              : 'border-light-300 dark:border-dark-600 hover:border-oto-300 dark:hover:border-dark-500'
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
                            <Network size={16} className={formData.network_switch === sw.name ? 'text-oto-500' : 'text-gray-400 dark:text-dark-400'} />
                            <span className="font-medium text-gray-900 dark:text-white">{sw.name}</span>
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
                            <p className="text-xs text-gray-500 dark:text-dark-400 mt-1 truncate">{sw.notes}</p>
                          )}
                        </label>
                      ))}
                      
                      {/* Option pour créer un nouveau switch */}
                      <button
                        type="button"
                        onClick={() => setIsCreateSwitchModalOpen(true)}
                        className="p-3 rounded-lg border border-dashed border-gray-300 dark:border-dark-500 hover:border-oto-500 hover:bg-oto-500/5 transition-colors text-left"
                      >
                        <div className="flex items-center gap-2">
                          <Plus size={16} className="text-oto-500" />
                          <span className="font-medium text-oto-500 dark:text-primary-400">Créer un switch</span>
                        </div>
                        <p className="text-xs text-gray-500 dark:text-dark-400 mt-1">
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
              <div className="border border-light-300 dark:border-dark-600 rounded-lg p-4">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <span className="font-medium text-gray-900 dark:text-white">Configuration IP statique</span>
                    <p className="text-sm text-gray-500 dark:text-dark-400">Par défaut, DHCP sera utilisé</p>
                  </div>
                  <Switch
                    checked={formData.use_static_ip}
                    onChange={(checked) => setFormData({ ...formData, use_static_ip: checked })}
                  />
                </div>

                {formData.use_static_ip && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t border-light-200 dark:border-dark-600">
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
                <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                  Options avancées
                </h2>
                <p className="text-gray-500 dark:text-dark-400">
                  Configurez les services, logiciels et options de déploiement.
                </p>
              </div>

              {/* Mot de passe administrateur */}
              <div className="border border-light-300 dark:border-dark-600 rounded-lg p-4">
                <h3 className="text-sm font-medium text-gray-700 dark:text-dark-200 mb-4 flex items-center gap-2">
                  <Key size={16} />
                  {isLinux ? 'Compte root / admin' : 'Compte administrateur'}
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Input
                    label={isLinux ? 'Mot de passe root' : 'Mot de passe administrateur'}
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

              {/* Services Windows */}
              {isWindows && (
                <div className="border border-light-300 dark:border-dark-600 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-gray-700 dark:text-dark-200 mb-4 flex items-center gap-2">
                    <Shield size={16} />
                    Services à activer
                  </h3>
                  <div className="space-y-3">
                    {WINDOWS_SERVICES.map((service) => (
                      <div key={service.id} className="flex items-center justify-between">
                        <div>
                          <span className="font-medium text-gray-900 dark:text-white">{service.name}</span>
                          <p className="text-sm text-gray-500 dark:text-dark-400">{service.description}</p>
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
              )}

              {/* Services Linux */}
              {isLinux && (
                <div className="border border-light-300 dark:border-dark-600 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-gray-700 dark:text-dark-200 mb-4 flex items-center gap-2">
                    <Shield size={16} />
                    Services à activer
                  </h3>
                  <div className="space-y-3">
                    {LINUX_SERVICES.map((service) => (
                      <div key={service.id} className="flex items-center justify-between">
                        <div>
                          <span className="font-medium text-gray-900 dark:text-white">{service.name}</span>
                          <p className="text-sm text-gray-500 dark:text-dark-400">{service.description}</p>
                        </div>
                        <Switch
                          checked={formData.enable_ssh}
                          onChange={(checked) =>
                            setFormData({ ...formData, enable_ssh: checked })
                          }
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Windows Update - uniquement pour Windows */}
              {isWindows && (
                <div className="border border-light-300 dark:border-dark-600 rounded-lg p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <RefreshCw size={18} className="text-gray-400 dark:text-dark-400" />
                      <div>
                        <span className="font-medium text-gray-900 dark:text-white">Windows Update</span>
                        <p className="text-sm text-gray-500 dark:text-dark-400">
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
              )}

              {/* Profil logiciels */}
              <div className="border border-light-300 dark:border-dark-600 rounded-lg p-4">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-medium text-gray-700 dark:text-dark-200 flex items-center gap-2">
                    <Package size={16} />
                    Logiciels à installer
                  </h3>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setIsMarketplaceModalOpen(true)}
                  >
                    <Package size={14} className="mr-1" />
                    Sélection à la carte
                  </Button>
                </div>

                {/* Profils pré-définis */}
                <p className="text-xs text-gray-500 dark:text-dark-400 mb-3">Profils pré-configurés :</p>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {softwareProfiles.map((profile) => (
                    <label
                      key={profile.name}
                      className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                        formData.software_profile === profile.name && formData.custom_packages.length === 0
                          ? 'border-oto-500 bg-oto-500/10'
                          : 'border-light-300 dark:border-dark-600 hover:border-oto-300 dark:hover:border-dark-500'
                      }`}
                    >
                      <input
                        type="radio"
                        name="software_profile"
                        value={profile.name}
                        checked={formData.software_profile === profile.name && formData.custom_packages.length === 0}
                        onChange={(e) =>
                          setFormData({ ...formData, software_profile: e.target.value, custom_packages: [] })
                        }
                        className="sr-only"
                      />
                      <p className="font-medium text-gray-900 dark:text-white">{profile.display_name}</p>
                      <p className="text-xs text-gray-500 dark:text-dark-400 mt-1">{profile.description}</p>
                      <p className="text-xs text-oto-500 mt-1">{profile.package_count} packages</p>
                    </label>
                  ))}
                  <label
                    className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                      formData.software_profile === '' && formData.custom_packages.length === 0
                        ? 'border-oto-500 bg-oto-500/10'
                        : 'border-light-300 dark:border-dark-600 hover:border-oto-300 dark:hover:border-dark-500'
                    }`}
                  >
                    <input
                      type="radio"
                      name="software_profile"
                      value=""
                      checked={formData.software_profile === '' && formData.custom_packages.length === 0}
                      onChange={() => setFormData({ ...formData, software_profile: '', custom_packages: [] })}
                      className="sr-only"
                    />
                    <p className="font-medium text-gray-900 dark:text-white">Aucun</p>
                    <p className="text-xs text-gray-500 dark:text-dark-400 mt-1">Pas de logiciels supplémentaires</p>
                  </label>
                </div>

                {/* Packages personnalisés sélectionnés */}
                {formData.custom_packages.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-light-200 dark:border-dark-600">
                    <p className="text-xs text-gray-500 dark:text-dark-400 mb-2">Sélection personnalisée ({formData.custom_packages.length} packages) :</p>
                    <div className="flex flex-wrap gap-2">
                      {formData.custom_packages.map((pkg) => (
                        <span
                          key={pkg}
                          className="px-2 py-1 bg-oto-100 dark:bg-primary-500/20 text-oto-600 dark:text-primary-400 text-xs rounded-full flex items-center gap-1"
                        >
                          {pkg}
                          <button
                            type="button"
                            onClick={() =>
                              setFormData({
                                ...formData,
                                custom_packages: formData.custom_packages.filter((p) => p !== pkg),
                              })
                            }
                            className="hover:text-oto-700 dark:hover:text-white"
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Jonction domaine AD - uniquement pour Windows */}
              {isWindows && (
                <div className="border border-light-300 dark:border-dark-600 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <Building2 size={18} className="text-gray-400 dark:text-dark-400" />
                      <div>
                        <span className="font-medium text-gray-900 dark:text-white">Joindre un domaine Active Directory</span>
                        <p className="text-sm text-gray-500 dark:text-dark-400">Intégrer la VM au domaine AD</p>
                      </div>
                    </div>
                    <Switch
                      checked={formData.join_domain}
                      onChange={(checked) => setFormData({ ...formData, join_domain: checked })}
                    />
                  </div>

                  {formData.join_domain && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t border-light-200 dark:border-dark-600">
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
              )}

              {/* Configuration Linux */}
              {isLinux && (
                <div className="border border-light-300 dark:border-dark-600 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-gray-700 dark:text-dark-200 mb-4 flex items-center gap-2">
                    <Terminal size={16} />
                    Configuration Linux
                  </h3>
                  <div className="space-y-4">
                    {/* Clé SSH publique */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-dark-200 mb-2">
                        Clé SSH publique (optionnel)
                      </label>
                      <textarea
                        value={formData.ssh_key || ''}
                        onChange={(e) => setFormData(prev => ({ ...prev, ssh_key: e.target.value }))}
                        placeholder="ssh-rsa AAAAB3... user@host"
                        rows={3}
                        className="w-full px-4 py-2 bg-white dark:bg-dark-800 border border-light-200 dark:border-dark-600 rounded-lg text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-dark-400"
                      />
                    </div>

                    {/* Paquets additionnels */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-dark-200 mb-2">
                        Paquets additionnels (optionnel)
                      </label>
                      <input
                        type="text"
                        value={formData.extra_packages || ''}
                        onChange={(e) => setFormData(prev => ({ ...prev, extra_packages: e.target.value }))}
                        placeholder="nginx, docker.io, git, htop"
                        className="w-full px-4 py-2 bg-white dark:bg-dark-800 border border-light-200 dark:border-dark-600 rounded-lg text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-dark-400"
                      />
                      <p className="text-xs text-gray-400 mt-1">Séparés par des virgules</p>
                    </div>

                    {/* Script post-installation */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-dark-200 mb-2">
                        Script post-installation (optionnel)
                      </label>
                      <textarea
                        value={formData.post_script || ''}
                        onChange={(e) => setFormData(prev => ({ ...prev, post_script: e.target.value }))}
                        placeholder={"#!/bin/bash\napt update && apt upgrade -y"}
                        rows={4}
                        className="w-full px-4 py-2 bg-white dark:bg-dark-800 border border-light-200 dark:border-dark-600 rounded-lg text-sm font-mono text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-dark-400"
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Étape 5: Résumé */}
          {currentStep === 5 && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                  Résumé du déploiement
                </h2>
                <p className="text-gray-500 dark:text-dark-400">
                  Vérifiez les informations avant de lancer le déploiement.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {/* Infrastructure */}
                <div className="bg-light-100 dark:bg-dark-700/50 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-gray-500 dark:text-dark-400 mb-3 flex items-center gap-2">
                    <Server size={14} />
                    Infrastructure
                  </h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-600 dark:text-dark-300">Hyperviseur</span>
                      <span className="text-gray-900 dark:text-white font-medium">
                        {selectedHypervisor?.name || '-'}
                        {selectedHypervisor && (
                          <span className="ml-1 text-xs text-gray-500 dark:text-dark-400">
                            ({selectedHypervisor.type === 'vmware' ? 'VMware' : 'Hyper-V'})
                          </span>
                        )}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600 dark:text-dark-300">Template</span>
                      <span className="text-gray-900 dark:text-white font-medium">
                        {selectedTemplate?.name || '-'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Configuration VM */}
                <div className="bg-light-100 dark:bg-dark-700/50 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-gray-500 dark:text-dark-400 mb-3 flex items-center gap-2">
                    <Cpu size={14} />
                    Machine virtuelle
                  </h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-600 dark:text-dark-300">Nom</span>
                      <span className="text-gray-900 dark:text-white font-medium">{formData.vm_name || '-'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600 dark:text-dark-300">CPU / RAM / Disque</span>
                      <span className="text-gray-900 dark:text-white font-medium">
                        {formData.cpu_count} vCPU / {formData.ram_gb} Go / {formData.disk_gb} Go
                      </span>
                    </div>
                    {isVMware && formData.datastore && (
                      <div className="flex justify-between">
                        <span className="text-gray-600 dark:text-dark-300">Datastore</span>
                        <span className="text-gray-900 dark:text-white font-medium">{formData.datastore}</span>
                      </div>
                    )}
                    {isVMware && formData.resource_pool && (
                      <div className="flex justify-between">
                        <span className="text-gray-600 dark:text-dark-300">Resource Pool</span>
                        <span className="text-gray-900 dark:text-white font-medium">{formData.resource_pool}</span>
                      </div>
                    )}
                    {isVMware && formData.vm_folder && (
                      <div className="flex justify-between">
                        <span className="text-gray-600 dark:text-dark-300">Dossier VM</span>
                        <span className="text-gray-900 dark:text-white font-medium">{formData.vm_folder}</span>
                      </div>
                    )}
                    {isVMware && (
                      <div className="flex justify-between">
                        <span className="text-gray-600 dark:text-dark-300">Format disque</span>
                        <span className="text-gray-900 dark:text-white font-medium">
                          {formData.disk_format === 'thin' ? 'Thin Provisioning' :
                           formData.disk_format === 'thick' ? 'Thick (Lazy Zeroed)' :
                           'Thick (Eager Zeroed)'}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Réseau */}
                <div className="bg-light-100 dark:bg-dark-700/50 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-gray-500 dark:text-dark-400 mb-3 flex items-center gap-2">
                    <Network size={14} />
                    Réseau
                  </h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-600 dark:text-dark-300">Switch</span>
                      <span className="text-gray-900 dark:text-white font-medium">
                        {formData.network_switch}
                        {formData.vlan_id && ` (VLAN ${formData.vlan_id})`}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600 dark:text-dark-300">IP</span>
                      <span className="text-gray-900 dark:text-white font-medium">
                        {formData.use_static_ip ? formData.ip_address : 'DHCP'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Services */}
                <div className="bg-light-100 dark:bg-dark-700/50 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-gray-500 dark:text-dark-400 mb-3 flex items-center gap-2">
                    <Shield size={14} />
                    Services
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {isWindows && formData.enable_rdp && (
                      <span className="px-2 py-1 bg-blue-500/20 text-blue-400 text-xs rounded">RDP</span>
                    )}
                    {isWindows && formData.enable_winrm && (
                      <span className="px-2 py-1 bg-purple-500/20 text-purple-400 text-xs rounded">WinRM</span>
                    )}
                    {formData.enable_ssh && (
                      <span className="px-2 py-1 bg-green-500/20 text-green-400 text-xs rounded">SSH</span>
                    )}
                    {isWindows && formData.enable_windows_update && (
                      <span className="px-2 py-1 bg-yellow-500/20 text-yellow-400 text-xs rounded">Windows Update</span>
                    )}
                    {isLinux && formData.ssh_key && (
                      <span className="px-2 py-1 bg-teal-500/20 text-teal-400 text-xs rounded">Clé SSH</span>
                    )}
                    {isLinux && formData.extra_packages && (
                      <span className="px-2 py-1 bg-orange-500/20 text-orange-400 text-xs rounded">Paquets additionnels</span>
                    )}
                    {isLinux && formData.post_script && (
                      <span className="px-2 py-1 bg-indigo-500/20 text-indigo-400 text-xs rounded">Script post-install</span>
                    )}
                  </div>
                </div>

                {/* Logiciels */}
                <div className="bg-light-100 dark:bg-dark-700/50 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-gray-500 dark:text-dark-400 mb-3 flex items-center gap-2">
                    <Package size={14} />
                    Logiciels
                  </h3>
                  <div className="text-sm">
                    {formData.custom_packages.length > 0 ? (
                      <div>
                        <span className="text-gray-900 dark:text-white font-medium">Sélection personnalisée</span>
                        <div className="flex flex-wrap gap-1 mt-2">
                          {formData.custom_packages.slice(0, 5).map((pkg) => (
                            <span key={pkg} className="px-2 py-0.5 bg-oto-100 dark:bg-primary-500/20 text-oto-600 dark:text-primary-400 text-xs rounded">
                              {pkg}
                            </span>
                          ))}
                          {formData.custom_packages.length > 5 && (
                            <span className="text-xs text-gray-500 dark:text-dark-400">
                              +{formData.custom_packages.length - 5} autres
                            </span>
                          )}
                        </div>
                      </div>
                    ) : selectedProfile ? (
                      <div>
                        <span className="text-gray-900 dark:text-white font-medium">{selectedProfile.display_name}</span>
                        <p className="text-xs text-gray-500 dark:text-dark-400 mt-1">{selectedProfile.description}</p>
                      </div>
                    ) : (
                      <span className="text-gray-500 dark:text-dark-400">Aucun logiciel sélectionné</span>
                    )}
                  </div>
                </div>

                {/* Domaine - uniquement pour Windows */}
                {isWindows && (
                  <div className="bg-light-100 dark:bg-dark-700/50 rounded-lg p-4">
                    <h3 className="text-sm font-medium text-gray-500 dark:text-dark-400 mb-3 flex items-center gap-2">
                      <Building2 size={14} />
                      Domaine AD
                    </h3>
                    <div className="text-sm">
                      {formData.join_domain ? (
                        <div className="space-y-1">
                          <span className="text-gray-900 dark:text-white font-medium">{formData.domain_name}</span>
                          {formData.domain_ou && (
                            <p className="text-xs text-gray-500 dark:text-dark-400">OU: {formData.domain_ou}</p>
                          )}
                        </div>
                      ) : (
                        <span className="text-gray-500 dark:text-dark-400">Pas de jonction au domaine</span>
                      )}
                    </div>
                  </div>
                )}

                {/* Configuration Linux - résumé */}
                {isLinux && (
                  <div className="bg-light-100 dark:bg-dark-700/50 rounded-lg p-4">
                    <h3 className="text-sm font-medium text-gray-500 dark:text-dark-400 mb-3 flex items-center gap-2">
                      <Terminal size={14} />
                      Configuration Linux
                    </h3>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-600 dark:text-dark-300">Clé SSH</span>
                        <span className="text-gray-900 dark:text-white font-medium">
                          {formData.ssh_key ? 'Configurée' : 'Non configurée'}
                        </span>
                      </div>
                      {formData.extra_packages && (
                        <div className="flex justify-between">
                          <span className="text-gray-600 dark:text-dark-300">Paquets</span>
                          <span className="text-gray-900 dark:text-white font-medium">
                            {formData.extra_packages.split(',').filter(Boolean).length} paquet(s)
                          </span>
                        </div>
                      )}
                      {formData.post_script && (
                        <div className="flex justify-between">
                          <span className="text-gray-600 dark:text-dark-300">Script post-install</span>
                          <span className="text-gray-900 dark:text-white font-medium">Configuré</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Messages d'erreur de validation */}
          {showErrors && currentErrors.length > 0 && (
            <div className="mt-6 p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
              <div className="flex items-start gap-3">
                <AlertTriangle size={20} className="text-red-500 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="font-medium text-red-500">Veuillez corriger les erreurs suivantes :</p>
                  <ul className="mt-2 space-y-1">
                    {currentErrors.map((error, index) => (
                      <li key={index} className="text-sm text-red-400">• {error}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* Navigation */}
          <div className="flex items-center justify-between mt-8 pt-6 border-t border-light-200 dark:border-dark-700">
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
              >
                Suivant
              </Button>
            ) : (
              <Button
                leftIcon={<Rocket size={18} />}
                onClick={handleSubmit}
                isLoading={createMutation.isPending}
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

      {/* Modal Marketplace - Sélection à la carte */}
      <Modal
        isOpen={isMarketplaceModalOpen}
        onClose={() => setIsMarketplaceModalOpen(false)}
        title="Sélection des logiciels"
        size="xl"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsMarketplaceModalOpen(false)}>
              Annuler
            </Button>
            <Button onClick={handleMarketplaceClose}>
              Valider la sélection ({formData.custom_packages.length})
            </Button>
          </>
        }
      >
        <div className="h-[60vh] overflow-y-auto -mx-4 px-4">
          <Marketplace
            selectionMode={true}
            selectedPackages={formData.custom_packages}
            onSelectionChange={(packages) =>
              setFormData({ ...formData, custom_packages: packages, software_profile: '' })
            }
          />
        </div>
      </Modal>

      {/* Modal de configuration des packages */}
      {configModalPackage && configModalPackage.config_schema && (
        <Modal
          isOpen={!!configModalPackage}
          onClose={handleSkipPackageConfig}
          title={`Configuration de ${configModalPackage.display_name}`}
          size="md"
          footer={
            <>
              <Button variant="secondary" onClick={handleSkipPackageConfig}>
                Ignorer
              </Button>
              <Button
                onClick={() => {
                  const form = document.getElementById('pkg-config-form') as HTMLFormElement;
                  if (form) {
                    const formData = new FormData(form);
                    const config: Record<string, unknown> = {};
                    configModalPackage.config_schema?.fields.forEach(field => {
                      const value = formData.get(field.name);
                      if (value !== null && value !== '') {
                        config[field.name] = field.type === 'number' ? Number(value) : value;
                      }
                    });
                    handleSavePackageConfig(configModalPackage.name, config);
                  }
                }}
              >
                Enregistrer
              </Button>
            </>
          }
        >
          <form id="pkg-config-form" className="space-y-4">
            <p className="text-sm text-gray-500 dark:text-dark-400 mb-4">
              Ce logiciel nécessite une configuration. Remplissez les champs ci-dessous.
            </p>
            {configModalPackage.config_schema.fields.map((field: ConfigField) => (
              <div key={field.name}>
                <label className="block text-sm font-medium text-gray-700 dark:text-dark-200 mb-1">
                  {field.label}
                  {field.required && <span className="text-red-500 ml-1">*</span>}
                </label>
                {field.type === 'boolean' ? (
                  <input
                    type="checkbox"
                    name={field.name}
                    defaultChecked={field.default as boolean}
                    className="h-4 w-4 rounded border-light-300 dark:border-dark-600 bg-white dark:bg-dark-700"
                  />
                ) : field.type === 'select' && field.options ? (
                  <select
                    name={field.name}
                    defaultValue={field.default as string}
                    className="w-full px-3 py-2 bg-white dark:bg-dark-700 border border-light-300 dark:border-dark-600 rounded-lg text-gray-900 dark:text-white"
                    required={field.required}
                  >
                    {field.options.map(opt => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    type={field.type === 'number' ? 'number' : 'text'}
                    name={field.name}
                    defaultValue={field.default as string | number}
                    placeholder={field.placeholder || ''}
                    required={field.required}
                    className="w-full px-3 py-2 bg-white dark:bg-dark-700 border border-light-300 dark:border-dark-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-dark-400"
                  />
                )}
                {field.description && (
                  <p className="text-xs text-gray-500 dark:text-dark-400 mt-1">{field.description}</p>
                )}
              </div>
            ))}
          </form>
          {pendingConfigPackages.length > 1 && (
            <p className="text-xs text-gray-500 dark:text-dark-400 mt-4">
              {pendingConfigPackages.length - 1} autre(s) package(s) à configurer
            </p>
          )}
        </Modal>
      )}
    </div>
  );
}
