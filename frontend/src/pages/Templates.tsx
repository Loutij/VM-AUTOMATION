import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  FileCode,
  Plus,
  MoreVertical,
  Pencil,
  Trash2,
  Copy,
  RefreshCw,
  Monitor,
  Server,
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
} from '../components/ui';
import { templatesApi } from '../services/api';
import type { OSTemplate, OSFamily } from '../types';

interface TemplateFormData {
  name: string;
  os_family: OSFamily;
  os_version: string;
  description: string;
  iso_path: string;
  default_cpu: string;
  default_memory_mb: string;
  default_disk_gb: string;
}

const defaultFormData: TemplateFormData = {
  name: '',
  os_family: 'windows',
  os_version: '',
  description: '',
  iso_path: '',
  default_cpu: '2',
  default_memory_mb: '4096',
  default_disk_gb: '60',
};

export function Templates() {
  const queryClient = useQueryClient();
  const { addToast } = useToast();

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<OSTemplate | null>(null);
  const [formData, setFormData] = useState<TemplateFormData>(defaultFormData);
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null);
  const [filterFamily, setFilterFamily] = useState<'all' | OSFamily>('all');

  // Fetch templates
  const { data: templates = [], isLoading, refetch } = useQuery({
    queryKey: ['templates'],
    queryFn: templatesApi.list,
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
        os_version: template.os_version,
        description: template.description || '',
        iso_path: template.iso_path || '',
        default_cpu: template.default_cpu.toString(),
        default_memory_mb: template.default_memory_mb.toString(),
        default_disk_gb: template.default_disk_gb.toString(),
      });
    } else {
      setSelectedTemplate(null);
      setFormData(defaultFormData);
    }
    setIsModalOpen(true);
    setActiveDropdown(null);
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
      os_version: formData.os_version,
      description: formData.description || undefined,
      iso_path: formData.iso_path || undefined,
      default_cpu: parseInt(formData.default_cpu),
      default_memory_mb: parseInt(formData.default_memory_mb),
      default_disk_gb: parseInt(formData.default_disk_gb),
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
    setActiveDropdown(null);
  };

  const handleDuplicate = (template: OSTemplate) => {
    setSelectedTemplate(null);
    setFormData({
      name: `${template.name} (copie)`,
      os_family: template.os_family,
      os_version: template.os_version,
      description: template.description || '',
      iso_path: template.iso_path || '',
      default_cpu: template.default_cpu.toString(),
      default_memory_mb: template.default_memory_mb.toString(),
      default_disk_gb: template.default_disk_gb.toString(),
    });
    setIsModalOpen(true);
    setActiveDropdown(null);
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

  const formatMemory = (mb: number) => {
    if (mb >= 1024) return `${mb / 1024} GB`;
    return `${mb} MB`;
  };

  return (
    <div className="min-h-screen bg-dark-900">
      <Header title="Templates OS" />
      <div className="p-6">
        {/* Header actions */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-4">
            <div className="flex items-center bg-dark-800 rounded-lg p-1">
              <button
                onClick={() => setFilterFamily('all')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  filterFamily === 'all'
                    ? 'bg-primary-600 text-white'
                    : 'text-dark-300 hover:text-white'
                }`}
              >
                Tous
              </button>
              <button
                onClick={() => setFilterFamily('windows')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  filterFamily === 'windows'
                    ? 'bg-primary-600 text-white'
                    : 'text-dark-300 hover:text-white'
                }`}
              >
                Windows
              </button>
              <button
                onClick={() => setFilterFamily('linux')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  filterFamily === 'linux'
                    ? 'bg-primary-600 text-white'
                    : 'text-dark-300 hover:text-white'
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
                <div className="h-6 bg-dark-700 rounded w-3/4 mb-4" />
                <div className="h-4 bg-dark-700 rounded w-1/2 mb-2" />
                <div className="h-4 bg-dark-700 rounded w-2/3" />
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
                className="card p-6 hover:border-dark-600 transition-colors relative group"
              >
                {/* Actions dropdown */}
                <div className="absolute top-4 right-4">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      setActiveDropdown(activeDropdown === template.id ? null : template.id)
                    }
                    className="!p-1.5 opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <MoreVertical size={16} />
                  </Button>
                  {activeDropdown === template.id && (
                    <>
                      <div
                        className="fixed inset-0 z-10"
                        onClick={() => setActiveDropdown(null)}
                      />
                      <div className="absolute right-0 top-full mt-1 z-20 w-40 bg-dark-700 border border-dark-600 rounded-lg shadow-lg py-1">
                        <button
                          onClick={() => handleOpenModal(template)}
                          className="w-full flex items-center gap-2 px-4 py-2 text-sm text-dark-200 hover:bg-dark-600 transition-colors"
                        >
                          <Pencil size={16} />
                          Modifier
                        </button>
                        <button
                          onClick={() => handleDuplicate(template)}
                          className="w-full flex items-center gap-2 px-4 py-2 text-sm text-dark-200 hover:bg-dark-600 transition-colors"
                        >
                          <Copy size={16} />
                          Dupliquer
                        </button>
                        <button
                          onClick={() => handleDelete(template)}
                          className="w-full flex items-center gap-2 px-4 py-2 text-sm text-red-500 hover:bg-dark-600 transition-colors"
                        >
                          <Trash2 size={16} />
                          Supprimer
                        </button>
                      </div>
                    </>
                  )}
                </div>

                {/* Template content */}
                <div className="flex items-start gap-4">
                  <div
                    className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                      template.os_family === 'windows' ? 'bg-blue-500/20' : 'bg-orange-500/20'
                    }`}
                  >
                    {getOSIcon(template.os_family)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-white truncate pr-8">{template.name}</h3>
                    <p className="text-sm text-dark-400">{template.os_version}</p>
                  </div>
                </div>

                {template.description && (
                  <p className="mt-3 text-sm text-dark-300 line-clamp-2">
                    {template.description}
                  </p>
                )}

                {/* Default specs */}
                <div className="mt-4 pt-4 border-t border-dark-700 flex items-center gap-4 text-xs text-dark-400">
                  <span>{template.default_cpu} vCPU</span>
                  <span>{formatMemory(template.default_memory_mb)}</span>
                  <span>{template.default_disk_gb} GB</span>
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

            <Input
              label="Version OS"
              value={formData.os_version}
              onChange={(e) => setFormData({ ...formData, os_version: e.target.value })}
              placeholder="Server 2022 Standard"
              required
            />

            <Textarea
              label="Description"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="Description du template..."
              rows={3}
            />

            <Input
              label="Chemin ISO"
              value={formData.iso_path}
              onChange={(e) => setFormData({ ...formData, iso_path: e.target.value })}
              placeholder="C:\HyperV\ISOs\windows_server_2022.iso"
              helperText="Chemin vers le fichier ISO sur l'hyperviseur"
            />

            <div className="grid grid-cols-3 gap-4">
              <Input
                label="CPU par défaut"
                type="number"
                min="1"
                max="64"
                value={formData.default_cpu}
                onChange={(e) => setFormData({ ...formData, default_cpu: e.target.value })}
                required
              />
              <Input
                label="RAM par défaut (MB)"
                type="number"
                min="512"
                step="512"
                value={formData.default_memory_mb}
                onChange={(e) =>
                  setFormData({ ...formData, default_memory_mb: e.target.value })
                }
                required
              />
              <Input
                label="Disque par défaut (GB)"
                type="number"
                min="20"
                value={formData.default_disk_gb}
                onChange={(e) =>
                  setFormData({ ...formData, default_disk_gb: e.target.value })
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
      </div>
    </div>
  );
}
