import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
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
} from 'lucide-react';
import { Header } from '../components/layout';
import { Button, Input, Select, useToast } from '../components/ui';
import { hypervisorsApi, templatesApi, deploymentsApi } from '../services/api';
import type { Hypervisor, OSTemplate } from '../types';

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
  network_switch: string;
  // Étape 3: Configuration système
  admin_password: string;
  admin_password_confirm: string;
  // Configuration IP (optionnelle)
  use_static_ip: boolean;
  ip_address: string;
  subnet_prefix: number;
  gateway: string;
  dns_primary: string;
  dns_secondary: string;
}

const defaultFormData: DeploymentFormData = {
  hypervisor_id: '',
  template_id: '',
  vm_name: '',
  hostname: '',
  cpu_count: 2,
  memory_mb: 4096,
  disk_size_gb: 60,
  network_switch: 'Default Switch',
  admin_password: '',
  admin_password_confirm: '',
  use_static_ip: false,
  ip_address: '',
  subnet_prefix: 24,
  gateway: '',
  dns_primary: '8.8.8.8',
  dns_secondary: '8.8.4.4',
};

const steps = [
  { id: 1, name: 'Infrastructure', icon: Server },
  { id: 2, name: 'Ressources', icon: Cpu },
  { id: 3, name: 'Système', icon: Key },
  { id: 4, name: 'Résumé', icon: Check },
];

export function NewDeployment() {
  const navigate = useNavigate();
  const { addToast } = useToast();
  const [currentStep, setCurrentStep] = useState(1);
  const [formData, setFormData] = useState<DeploymentFormData>(defaultFormData);

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

  // Mutation pour créer le déploiement
  const createMutation = useMutation({
    mutationFn: (data: {
      name: string;
      hypervisor_id: string;
      template_id: string;
      config: {
        cpu_count: number;
        memory_mb: number;
        disk_size_gb: number;
        hostname?: string;
        admin_password?: string;
        network_switch?: string;
      };
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
        if (formData.admin_password !== formData.admin_password_confirm) return false;
        if (formData.use_static_ip && !formData.ip_address) return false;
        return true;
      default:
        return true;
    }
  };

  const canProceed = validateStep(currentStep);

  const handleNext = () => {
    if (canProceed && currentStep < 4) {
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
    for (let i = 1; i <= 3; i++) {
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

    createMutation.mutate({
      name: formData.vm_name,
      hypervisor_id: formData.hypervisor_id,
      template_id: formData.template_id,
      config: {
        cpu_count: formData.cpu_count,
        memory_mb: formData.memory_mb,
        disk_size_gb: formData.disk_size_gb,
        hostname: formData.hostname || formData.vm_name,
        admin_password: formData.admin_password || undefined,
        network_switch: formData.network_switch || undefined,
      },
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
          <div className="flex items-center justify-between">
            {steps.map((step, index) => (
              <div key={step.id} className="flex items-center">
                <div
                  className={`flex items-center gap-3 cursor-pointer ${
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
                  <span className="font-medium hidden sm:inline">{step.name}</span>
                </div>
                {index < steps.length - 1 && (
                  <ChevronRight size={20} className="mx-4 text-dark-600" />
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

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
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

              <Input
                label="Switch réseau"
                value={formData.network_switch}
                onChange={(e) => setFormData({ ...formData, network_switch: e.target.value })}
                placeholder="Default Switch"
                leftIcon={<Network size={18} />}
                helperText="Nom du switch virtuel Hyper-V"
              />
            </div>
          )}

          {/* Étape 3: Configuration système */}
          {currentStep === 3 && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-semibold text-white mb-2">
                  Configuration système
                </h2>
                <p className="text-dark-400">
                  Configurez le mot de passe administrateur et les paramètres réseau.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <Input
                  label="Mot de passe administrateur"
                  type="password"
                  value={formData.admin_password}
                  onChange={(e) =>
                    setFormData({ ...formData, admin_password: e.target.value })
                  }
                  placeholder="••••••••"
                  leftIcon={<Key size={18} />}
                />
                <Input
                  label="Confirmer le mot de passe"
                  type="password"
                  value={formData.admin_password_confirm}
                  onChange={(e) =>
                    setFormData({ ...formData, admin_password_confirm: e.target.value })
                  }
                  placeholder="••••••••"
                  leftIcon={<Key size={18} />}
                  error={
                    formData.admin_password_confirm &&
                    formData.admin_password !== formData.admin_password_confirm
                      ? 'Les mots de passe ne correspondent pas'
                      : undefined
                  }
                />
              </div>

              {/* Configuration IP statique */}
              <div className="border border-dark-600 rounded-lg p-4">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.use_static_ip}
                    onChange={(e) =>
                      setFormData({ ...formData, use_static_ip: e.target.checked })
                    }
                    className="w-4 h-4 rounded border-dark-500 bg-dark-700 text-primary-500 focus:ring-primary-500"
                  />
                  <div>
                    <span className="font-medium text-white">
                      Utiliser une IP statique
                    </span>
                    <p className="text-sm text-dark-400">
                      Par défaut, DHCP sera utilisé
                    </p>
                  </div>
                </label>

                {formData.use_static_ip && (
                  <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
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
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Étape 4: Résumé */}
          {currentStep === 4 && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-semibold text-white mb-2">
                  Résumé du déploiement
                </h2>
                <p className="text-dark-400">
                  Vérifiez les informations avant de lancer le déploiement.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Infrastructure */}
                <div className="bg-dark-700/50 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-dark-400 mb-3">
                    Infrastructure
                  </h3>
                  <div className="space-y-2">
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
                    <div className="flex justify-between">
                      <span className="text-dark-300">Système</span>
                      <span className="text-white font-medium">
                        {selectedTemplate?.os_version || '-'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Configuration VM */}
                <div className="bg-dark-700/50 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-dark-400 mb-3">
                    Machine virtuelle
                  </h3>
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <span className="text-dark-300">Nom</span>
                      <span className="text-white font-medium">
                        {formData.vm_name || '-'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-dark-300">Hostname</span>
                      <span className="text-white font-medium">
                        {formData.hostname || formData.vm_name || '-'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Ressources */}
                <div className="bg-dark-700/50 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-dark-400 mb-3">Ressources</h3>
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <span className="text-dark-300">CPU</span>
                      <span className="text-white font-medium">
                        {formData.cpu_count} vCPU
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-dark-300">RAM</span>
                      <span className="text-white font-medium">
                        {formatMemory(formData.memory_mb)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-dark-300">Disque</span>
                      <span className="text-white font-medium">
                        {formData.disk_size_gb} GB
                      </span>
                    </div>
                  </div>
                </div>

                {/* Réseau */}
                <div className="bg-dark-700/50 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-dark-400 mb-3">Réseau</h3>
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <span className="text-dark-300">Switch</span>
                      <span className="text-white font-medium">
                        {formData.network_switch || 'Default Switch'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-dark-300">Configuration IP</span>
                      <span className="text-white font-medium">
                        {formData.use_static_ip ? formData.ip_address : 'DHCP'}
                      </span>
                    </div>
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

            {currentStep < 4 ? (
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
    </div>
  );
}
