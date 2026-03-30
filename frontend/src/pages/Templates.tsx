import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  FileCode,
  Plus,
  Pencil,
  Trash2,
  Copy,
  RefreshCw,
  Monitor,
  Server,
  FolderOpen,
  Loader2,
  HardDrive,
  Languages,
} from 'lucide-react';
import { Header } from '../components/layout';
import {
  Button,
  Modal,
  ConfirmModal,
  Input,
  Textarea,
  Select,
  EmptyState,
  useToast,
  Dropdown,
} from '../components/ui';
import { templatesApi, hypervisorsApi, type ISOInfo } from '../services/api';
import type { OSTemplate, OSFamily, Hypervisor } from '../types';

// Liste des langues d'installation supportées
const INSTALL_LOCALES = [
  { value: 'fr-FR', label: 'Français (France)' },
  { value: 'en-US', label: 'English (United States)' },
  { value: 'en-GB', label: 'English (United Kingdom)' },
  { value: 'de-DE', label: 'Deutsch (Deutschland)' },
  { value: 'es-ES', label: 'Español (España)' },
  { value: 'it-IT', label: 'Italiano (Italia)' },
  { value: 'pt-BR', label: 'Português (Brasil)' },
  { value: 'nl-NL', label: 'Nederlands (Nederland)' },
  { value: 'pl-PL', label: 'Polski (Polska)' },
  { value: 'ru-RU', label: 'Русский (Россия)' },
  { value: 'ja-JP', label: '日本語 (日本)' },
  { value: 'zh-CN', label: '简体中文 (中国)' },
];

interface TemplateFormData {
  name: string;
  os_family: OSFamily;
  os_type: string;
  description: string;
  iso_path: string;
  min_cpu: string;
  min_ram_gb: string;
  min_disk_gb: string;
  install_locale: string;
}

const defaultFormData: TemplateFormData = {
  name: '',
  os_family: 'windows',
  os_type: '',
  description: '',
  iso_path: '',
  min_cpu: '2',
  min_ram_gb: '4',
  min_disk_gb: '60',
  install_locale: 'fr-FR',
};

export function Templates() {
  const queryClient = useQueryClient();
  const { addToast } = useToast();

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isIsoPickerOpen, setIsIsoPickerOpen] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<OSTemplate | null>(null);
  const [formData, setFormData] = useState<TemplateFormData>(defaultFormData);
  const [filterFamily, setFilterFamily] = useState<'all' | OSFamily>('all');
  const [selectedHypervisorForIso, setSelectedHypervisorForIso] = useState<string>('');

  // Fetch templates
  const { data: templates = [], isLoading, refetch } = useQuery({
    queryKey: ['templates'],
    queryFn: templatesApi.list,
  });

  // Fetch hypervisors (pour le sélecteur d'ISO)
  const { data: hypervisors = [] } = useQuery({
    queryKey: ['hypervisors'],
    queryFn: hypervisorsApi.list,
  });

  // Fetch ISOs depuis l'hyperviseur sélectionné
  const { data: isos = [], isLoading: isosLoading } = useQuery({
    queryKey: ['isos', selectedHypervisorForIso],
    queryFn: () => hypervisorsApi.listIsos(selectedHypervisorForIso),
    enabled: !!selectedHypervisorForIso && isIsoPickerOpen,
  });

  // Create mutation
  const createMutation = useMutation({
    mutationFn: (data: Partial<OSTemplate>) => templatesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['templates'] });
      addToast({ type: 'success', title: 'Template créé avec succès' });
      handleCloseModal();
    },
    onError: () => {
      addToast({ type: 'error', title: 'Erreur lors de la création' });
    },
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<OSTemplate> }) =>
      templatesApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['templates'] });
      addToast({ type: 'success', title: 'Template modifié avec succès' });
      handleCloseModal();
    },
    onError: () => {
      addToast({ type: 'error', title: 'Erreur lors de la modification' });
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => templatesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['templates'] });
      addToast({ type: 'success', title: 'Template supprimé' });
      setIsDeleteModalOpen(false);
      setSelectedTemplate(null);
    },
    onError: () => {
      addToast({ type: 'error', title: 'Erreur lors de la suppression' });
    },
  });

  const handleOpenModal = (template?: OSTemplate) => {
    if (template) {
      setSelectedTemplate(template);
      setFormData({
        name: template.name,
        os_family: template.os_family,
        os_type: template.os_type,
        description: template.description || '',
        iso_path: template.iso_path || '',
        min_cpu: template.min_cpu.toString(),
        min_ram_gb: template.min_ram_gb.toString(),
        min_disk_gb: template.min_disk_gb.toString(),
        install_locale: template.install_locale || 'fr-FR',
      });
    } else {
      setSelectedTemplate(null);
      setFormData(defaultFormData);
    }
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedTemplate(null);
    setFormData(defaultFormData);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload = {
      name: formData.name,
      os_family: formData.os_family,
      os_type: formData.os_type,
      description: formData.description || undefined,
      iso_path: formData.iso_path || undefined,
      min_cpu: parseInt(formData.min_cpu),
      min_ram_gb: parseInt(formData.min_ram_gb),
      min_disk_gb: parseInt(formData.min_disk_gb),
      install_locale: formData.install_locale,
    };

    if (selectedTemplate) {
      updateMutation.mutate({ id: selectedTemplate.id, data: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  const handleDelete = (template: OSTemplate) => {
    setSelectedTemplate(template);
    setIsDeleteModalOpen(true);
  };

  const handleDuplicate = (template: OSTemplate) => {
    setSelectedTemplate(null);
    setFormData({
      name: `${template.name} (copie)`,
      os_family: template.os_family,
      os_type: template.os_type,
      description: template.description || '',
      iso_path: template.iso_path || '',
      min_cpu: template.min_cpu.toString(),
      min_ram_gb: template.min_ram_gb.toString(),
      min_disk_gb: template.min_disk_gb.toString(),
      install_locale: template.install_locale || 'fr-FR',
    });
    setIsModalOpen(true);
  };

  const filteredTemplates =
    filterFamily === 'all'
      ? templates
      : templates.filter((t) => t.os_family === filterFamily);

  const getOSIcon = (family: OSFamily) => {
    return family === 'windows' ? (
      <Monitor size={20} className="text-blue-400" />
    ) : (
      <Server size={20} className="text-orange-400" />
    );
  };


  return (
    <div className="min-h-screen bg-light-100 dark:bg-dark-900">
      <Header title="Templates" />
      <div className="p-4 sm:p-6">
        {/* Header actions */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-4">
            <div className="flex items-center bg-white dark:bg-dark-800 rounded-lg p-1 border border-light-200 dark:border-transparent">
              <button
                onClick={() => setFilterFamily('all')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  filterFamily === 'all'
                    ? 'bg-oto-600 text-white'
                    : 'text-gray-600 dark:text-dark-300 hover:text-gray-900 dark:hover:text-white'
                }`}
              >
                Tous
              </button>
              <button
                onClick={() => setFilterFamily('windows')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  filterFamily === 'windows'
                    ? 'bg-oto-600 text-white'
                    : 'text-gray-600 dark:text-dark-300 hover:text-gray-900 dark:hover:text-white'
                }`}
              >
                Windows
              </button>
              <button
                onClick={() => setFilterFamily('linux')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  filterFamily === 'linux'
                    ? 'bg-oto-600 text-white'
                    : 'text-gray-600 dark:text-dark-300 hover:text-gray-900 dark:hover:text-white'
                }`}
              >
                Linux
              </button>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="secondary"
              leftIcon={<RefreshCw size={18} />}
              onClick={() => refetch()}
              isLoading={isLoading}
            >
              Actualiser
            </Button>
            <Button leftIcon={<Plus size={18} />} onClick={() => handleOpenModal()}>
              Créer un template
            </Button>
          </div>
        </div>

        {/* Templates grid */}
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="card p-6 animate-pulse">
                <div className="h-6 bg-light-200 dark:bg-dark-700 rounded w-3/4 mb-4" />
                <div className="h-4 bg-light-200 dark:bg-dark-700 rounded w-1/2 mb-2" />
                <div className="h-4 bg-light-200 dark:bg-dark-700 rounded w-2/3" />
              </div>
            ))}
          </div>
        ) : filteredTemplates.length === 0 ? (
          <div className="card">
            <EmptyState
              icon={FileCode}
              title="Aucun template"
              description="Créez votre premier template pour automatiser l'installation des systèmes d'exploitation."
              action={{
                label: 'Créer un template',
                onClick: () => handleOpenModal(),
                icon: Plus,
              }}
            />
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredTemplates.map((template) => (
              <div
                key={template.id}
                className="card p-6 hover:border-oto-300 dark:hover:border-dark-600 transition-colors relative group"
              >
                {/* Actions dropdown */}
                <div className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity">
                  <Dropdown
                    items={[
                      {
                        label: 'Modifier',
                        icon: <Pencil size={16} />,
                        onClick: () => handleOpenModal(template),
                      },
                      {
                        label: 'Dupliquer',
                        icon: <Copy size={16} />,
                        onClick: () => handleDuplicate(template),
                      },
                      {
                        label: 'Supprimer',
                        icon: <Trash2 size={16} />,
                        onClick: () => handleDelete(template),
                        variant: 'danger',
                      },
                    ]}
                  />
                </div>

                {/* Template content */}
                <div className="flex items-start gap-4">
                  <div
                    className={`w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 ${
                      template.os_family === 'windows' ? 'bg-blue-500/20' : 'bg-orange-500/20'
                    }`}
                  >
                    {getOSIcon(template.os_family)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-gray-900 dark:text-white pr-8 break-words" title={template.name}>
                      {template.name}
                    </h3>
                    <p className="text-sm text-gray-500 dark:text-dark-400">{template.os_type}</p>
                  </div>
                </div>

                {template.description && (
                  <p className="mt-3 text-sm text-gray-600 dark:text-dark-300 line-clamp-2">
                    {template.description}
                  </p>
                )}

                {/* Default specs */}
                <div className="mt-4 pt-4 border-t border-light-200 dark:border-dark-700 flex items-center justify-between text-xs text-gray-500 dark:text-dark-400">
                  <div className="flex items-center gap-4">
                    <span>{template.min_cpu} vCPU</span>
                    <span>{template.min_ram_gb} Go</span>
                    <span>{template.min_disk_gb} Go</span>
                  </div>
                  {template.install_locale && (
                    <div className="flex items-center gap-1.5 text-gray-600 dark:text-dark-300">
                      <Languages size={12} />
                      <span>{template.install_locale}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Add/Edit Modal */}
        <Modal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          title={selectedTemplate ? 'Modifier le template' : 'Créer un template'}
          size="lg"
          footer={
            <>
              <Button variant="secondary" onClick={handleCloseModal}>
                Annuler
              </Button>
              <Button
                onClick={handleSubmit}
                isLoading={createMutation.isPending || updateMutation.isPending}
              >
                {selectedTemplate ? 'Enregistrer' : 'Créer'}
              </Button>
            </>
          }
        >
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Nom du template"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="Windows Server 2022"
                required
              />
              <Select
                label="Famille OS"
                value={formData.os_family}
                onChange={(e) =>
                  setFormData({ ...formData, os_family: e.target.value as OSFamily })
                }
                options={[
                  { value: 'windows', label: 'Windows' },
                  { value: 'linux', label: 'Linux' },
                ]}
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Type d'OS"
                value={formData.os_type}
                onChange={(e) => setFormData({ ...formData, os_type: e.target.value })}
                placeholder="Server 2022 Standard"
                required
              />
              <Select
                label="Langue d'installation"
                value={formData.install_locale}
                onChange={(e) => setFormData({ ...formData, install_locale: e.target.value })}
                options={INSTALL_LOCALES}
                required
              />
            </div>

            <Textarea
              label="Description"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="Description du template..."
              rows={3}
            />

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-dark-200 mb-2">
                Chemin ISO
              </label>
              <div className="flex gap-2">
                <Input
                  value={formData.iso_path}
                  onChange={(e) => setFormData({ ...formData, iso_path: e.target.value })}
                  placeholder="G:\HyperV\ISOs\windows_server_2022.iso"
                  className="flex-1"
                />
                <Button
                  type="button"
                  variant="secondary"
                  leftIcon={<FolderOpen size={16} />}
                  onClick={() => {
                    if (hypervisors.length > 0 && !selectedHypervisorForIso) {
                      setSelectedHypervisorForIso(hypervisors[0].id);
                    }
                    setIsIsoPickerOpen(true);
                  }}
                >
                  Parcourir
                </Button>
              </div>
              <p className="mt-1 text-xs text-gray-500 dark:text-dark-400">
                Chemin vers le fichier ISO sur l'hyperviseur
              </p>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <Input
                label="CPU par défaut"
                type="number"
                min="1"
                max="64"
                value={formData.min_cpu}
                onChange={(e) => setFormData({ ...formData, min_cpu: e.target.value })}
                required
              />
              <Input
                label="RAM par défaut (Go)"
                type="number"
                min="1"
                step="1"
                value={formData.min_ram_gb}
                onChange={(e) =>
                  setFormData({ ...formData, min_ram_gb: e.target.value })
                }
                required
              />
              <Input
                label="Disque par défaut (Go)"
                type="number"
                min="20"
                value={formData.min_disk_gb}
                onChange={(e) =>
                  setFormData({ ...formData, min_disk_gb: e.target.value })
                }
                required
              />
            </div>
          </form>
        </Modal>

        {/* Delete confirmation modal */}
        <ConfirmModal
          isOpen={isDeleteModalOpen}
          onClose={() => {
            setIsDeleteModalOpen(false);
            setSelectedTemplate(null);
          }}
          onConfirm={() => selectedTemplate && deleteMutation.mutate(selectedTemplate.id)}
          title="Supprimer le template"
          message={`Êtes-vous sûr de vouloir supprimer le template "${selectedTemplate?.name}" ? Cette action est irréversible.`}
          confirmText="Supprimer"
          variant="danger"
          isLoading={deleteMutation.isPending}
        />

        {/* ISO Picker Modal */}
        <Modal
          isOpen={isIsoPickerOpen}
          onClose={() => setIsIsoPickerOpen(false)}
          title="Sélectionner un fichier ISO"
          size="lg"
        >
          <div className="space-y-4">
            {/* Sélecteur d'hyperviseur */}
            <Select
              label="Hyperviseur"
              value={selectedHypervisorForIso}
              onChange={(e) => setSelectedHypervisorForIso(e.target.value)}
              options={[
                { value: '', label: 'Sélectionner un hyperviseur...', disabled: true },
                ...hypervisors.map((h: Hypervisor) => ({
                  value: h.id,
                  label: `${h.name} (${h.host})`,
                })),
              ]}
            />

            {/* Liste des ISOs */}
            {selectedHypervisorForIso && (
              <div className="border border-light-300 dark:border-dark-600 rounded-lg overflow-hidden">
                <div className="bg-light-100 dark:bg-dark-700 px-4 py-2 text-sm font-medium text-gray-600 dark:text-dark-300 flex items-center gap-2">
                  <HardDrive size={16} />
                  Fichiers ISO disponibles
                </div>
                
                {isosLoading ? (
                  <div className="p-8 text-center text-gray-500 dark:text-dark-400">
                    <Loader2 size={24} className="animate-spin mx-auto mb-2" />
                    Chargement des ISOs...
                  </div>
                ) : isos.length === 0 ? (
                  <div className="p-8 text-center text-gray-500 dark:text-dark-400">
                    Aucun fichier ISO trouvé sur cet hyperviseur
                  </div>
                ) : (
                  <div className="max-h-80 overflow-y-auto divide-y divide-light-200 dark:divide-dark-700">
                    {isos.map((iso: ISOInfo) => (
                      <button
                        key={iso.full_path}
                        type="button"
                        onClick={() => {
                          setFormData({ ...formData, iso_path: iso.full_path });
                          setIsIsoPickerOpen(false);
                        }}
                        className="w-full px-4 py-3 text-left hover:bg-light-100 dark:hover:bg-dark-700/50 transition-colors flex items-center justify-between gap-4"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="font-medium text-gray-900 dark:text-white truncate">{iso.name}</p>
                          <p className="text-xs text-gray-500 dark:text-dark-400 truncate">{iso.full_path}</p>
                        </div>
                        <div className="text-right text-sm text-gray-500 dark:text-dark-400 flex-shrink-0">
                          <p>{iso.size_gb} Go</p>
                          <p className="text-xs">{iso.last_modified}</p>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </Modal>
      </div>
    </div>
  );
}
