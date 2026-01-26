import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Server,
  Plus,
  MoreVertical,
  Pencil,
  Trash2,
  Plug,
  CheckCircle,
  XCircle,
  RefreshCw,
} from 'lucide-react';
import { Header } from '../components/layout';
import {
  DataTable,
  Button,
  Modal,
  ConfirmModal,
  Input,
  Select,
  StatusBadge,
  EmptyState,
  useToast,
  type Column,
} from '../components/ui';
import { hypervisorsApi } from '../services/api';
import type { Hypervisor } from '../types';

interface HypervisorFormData {
  name: string;
  type: 'hyperv' | 'vmware';
  host: string;
  port: string;
  username: string;
  password: string;
}

const defaultFormData: HypervisorFormData = {
  name: '',
  type: 'hyperv',
  host: '',
  port: '',
  username: '',
  password: '',
};

export function Hypervisors() {
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [selectedHypervisor, setSelectedHypervisor] = useState<Hypervisor | null>(null);
  const [formData, setFormData] = useState<HypervisorFormData>(defaultFormData);
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null);

  // Fetch hypervisors
  const { data: hypervisors = [], isLoading, refetch } = useQuery({
    queryKey: ['hypervisors'],
    queryFn: hypervisorsApi.list,
  });

  // Create mutation
  const createMutation = useMutation({
    mutationFn: (data: Partial<Hypervisor>) => hypervisorsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hypervisors'] });
      addToast({ type: 'success', title: 'Hyperviseur créé avec succès' });
      handleCloseModal();
    },
    onError: () => {
      addToast({ type: 'error', title: 'Erreur lors de la création' });
    },
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Hypervisor> }) =>
      hypervisorsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hypervisors'] });
      addToast({ type: 'success', title: 'Hyperviseur modifié avec succès' });
      handleCloseModal();
    },
    onError: () => {
      addToast({ type: 'error', title: 'Erreur lors de la modification' });
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => hypervisorsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hypervisors'] });
      addToast({ type: 'success', title: 'Hyperviseur supprimé' });
      setIsDeleteModalOpen(false);
      setSelectedHypervisor(null);
    },
    onError: () => {
      addToast({ type: 'error', title: 'Erreur lors de la suppression' });
    },
  });

  // Test connection mutation
  const testConnectionMutation = useMutation({
    mutationFn: (id: string) => hypervisorsApi.testConnection(id),
    onSuccess: (result) => {
      if (result.connected) {
        addToast({ type: 'success', title: 'Connexion réussie', message: result.message });
      } else {
        addToast({ type: 'error', title: 'Connexion échouée', message: result.message });
      }
      queryClient.invalidateQueries({ queryKey: ['hypervisors'] });
    },
    onError: () => {
      addToast({ type: 'error', title: 'Erreur lors du test de connexion' });
    },
  });

  const handleOpenModal = (hypervisor?: Hypervisor) => {
    if (hypervisor) {
      setSelectedHypervisor(hypervisor);
      setFormData({
        name: hypervisor.name,
        type: hypervisor.type,
        host: hypervisor.host,
        port: hypervisor.port?.toString() || '',
        username: hypervisor.username,
        password: '',
      });
    } else {
      setSelectedHypervisor(null);
      setFormData(defaultFormData);
    }
    setIsModalOpen(true);
    setActiveDropdown(null);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedHypervisor(null);
    setFormData(defaultFormData);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload = {
      name: formData.name,
      type: formData.type,
      host: formData.host,
      port: formData.port ? parseInt(formData.port) : undefined,
      username: formData.username,
      ...(formData.password && { password: formData.password }),
    };

    if (selectedHypervisor) {
      updateMutation.mutate({ id: selectedHypervisor.id, data: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  const handleDelete = (hypervisor: Hypervisor) => {
    setSelectedHypervisor(hypervisor);
    setIsDeleteModalOpen(true);
    setActiveDropdown(null);
  };

  const handleTestConnection = (hypervisor: Hypervisor) => {
    testConnectionMutation.mutate(hypervisor.id);
    setActiveDropdown(null);
  };

  const columns: Column<Hypervisor>[] = [
    {
      key: 'name',
      header: 'Nom',
      sortable: true,
      render: (h) => (
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-primary-600/20 rounded-lg flex items-center justify-center">
            <Server size={16} className="text-primary-500" />
          </div>
          <span className="font-medium text-white">{h.name}</span>
        </div>
      ),
    },
    {
      key: 'type',
      header: 'Type',
      sortable: true,
      render: (h) => (
        <span className="px-2 py-1 bg-dark-700 rounded text-sm capitalize">{h.type}</span>
      ),
    },
    {
      key: 'host',
      header: 'Hôte',
      sortable: true,
      render: (h) => <span className="font-mono text-sm">{h.host}</span>,
    },
    {
      key: 'is_connected',
      header: 'Statut',
      render: (h) => (
        <div className="flex items-center gap-2">
          {h.is_connected ? (
            <>
              <CheckCircle size={16} className="text-green-500" />
              <span className="text-green-500">Connecté</span>
            </>
          ) : (
            <>
              <XCircle size={16} className="text-red-500" />
              <span className="text-red-500">Déconnecté</span>
            </>
          )}
        </div>
      ),
    },
    {
      key: 'vm_count',
      header: 'VMs',
      sortable: true,
      render: (h) => <span>{h.vm_count ?? '-'}</span>,
    },
  ];

  const renderActions = (hypervisor: Hypervisor) => (
    <div className="relative">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setActiveDropdown(activeDropdown === hypervisor.id ? null : hypervisor.id)}
        className="!p-1.5"
      >
        <MoreVertical size={16} />
      </Button>
      {activeDropdown === hypervisor.id && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setActiveDropdown(null)}
          />
          <div className="absolute right-0 top-full mt-1 z-20 w-48 bg-dark-700 border border-dark-600 rounded-lg shadow-lg py-1">
            <button
              onClick={() => handleTestConnection(hypervisor)}
              className="w-full flex items-center gap-2 px-4 py-2 text-sm text-dark-200 hover:bg-dark-600 transition-colors"
            >
              <Plug size={16} />
              Tester la connexion
            </button>
            <button
              onClick={() => handleOpenModal(hypervisor)}
              className="w-full flex items-center gap-2 px-4 py-2 text-sm text-dark-200 hover:bg-dark-600 transition-colors"
            >
              <Pencil size={16} />
              Modifier
            </button>
            <button
              onClick={() => handleDelete(hypervisor)}
              className="w-full flex items-center gap-2 px-4 py-2 text-sm text-red-500 hover:bg-dark-600 transition-colors"
            >
              <Trash2 size={16} />
              Supprimer
            </button>
          </div>
        </>
      )}
    </div>
  );

  return (
    <div className="min-h-screen bg-dark-900">
      <Header title="Hyperviseurs" />
      <div className="p-6">
        {/* Header actions */}
        <div className="flex items-center justify-between mb-6">
          <p className="text-dark-400">
            Gérez vos connexions aux serveurs Hyper-V et VMware
          </p>
          <div className="flex items-center gap-3">
            <Button
              variant="secondary"
              leftIcon={<RefreshCw size={18} />}
              onClick={() => refetch()}
              isLoading={isLoading}
            >
              Actualiser
            </Button>
            <Button
              leftIcon={<Plus size={18} />}
              onClick={() => handleOpenModal()}
            >
              Ajouter un hyperviseur
            </Button>
          </div>
        </div>

        {/* Data table */}
        {hypervisors.length === 0 && !isLoading ? (
          <div className="card">
            <EmptyState
              icon={Server}
              title="Aucun hyperviseur configuré"
              description="Ajoutez votre premier hyperviseur pour commencer à créer des machines virtuelles."
              action={{
                label: 'Ajouter un hyperviseur',
                onClick: () => handleOpenModal(),
                icon: Plus,
              }}
            />
          </div>
        ) : (
          <DataTable
            data={hypervisors}
            columns={columns}
            keyExtractor={(h) => h.id}
            isLoading={isLoading}
            searchable
            searchPlaceholder="Rechercher un hyperviseur..."
            searchKeys={['name', 'host']}
            actions={renderActions}
            emptyMessage="Aucun hyperviseur trouvé"
            emptyIcon={<Server size={40} className="text-dark-500" />}
          />
        )}

        {/* Add/Edit Modal */}
        <Modal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          title={selectedHypervisor ? 'Modifier l\'hyperviseur' : 'Ajouter un hyperviseur'}
          size="md"
          footer={
            <>
              <Button variant="secondary" onClick={handleCloseModal}>
                Annuler
              </Button>
              <Button
                onClick={handleSubmit}
                isLoading={createMutation.isPending || updateMutation.isPending}
              >
                {selectedHypervisor ? 'Enregistrer' : 'Ajouter'}
              </Button>
            </>
          }
        >
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              label="Nom"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="Mon Hyperviseur"
              required
            />
            <Select
              label="Type"
              value={formData.type}
              onChange={(e) =>
                setFormData({ ...formData, type: e.target.value as 'hyperv' | 'vmware' })
              }
              options={[
                { value: 'hyperv', label: 'Hyper-V' },
                { value: 'vmware', label: 'VMware vSphere' },
              ]}
              required
            />
            <Input
              label="Hôte"
              value={formData.host}
              onChange={(e) => setFormData({ ...formData, host: e.target.value })}
              placeholder="192.168.1.100 ou hyperv.domain.local"
              required
            />
            <Input
              label="Port"
              type="number"
              value={formData.port}
              onChange={(e) => setFormData({ ...formData, port: e.target.value })}
              placeholder="5985 (WinRM) ou 443 (vSphere)"
              helperText="Laissez vide pour utiliser le port par défaut"
            />
            <Input
              label="Utilisateur"
              value={formData.username}
              onChange={(e) => setFormData({ ...formData, username: e.target.value })}
              placeholder="administrator"
              required
            />
            <Input
              label="Mot de passe"
              type="password"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              placeholder={selectedHypervisor ? '••••••••' : 'Mot de passe'}
              required={!selectedHypervisor}
              helperText={selectedHypervisor ? 'Laissez vide pour conserver le mot de passe actuel' : undefined}
            />
          </form>
        </Modal>

        {/* Delete confirmation modal */}
        <ConfirmModal
          isOpen={isDeleteModalOpen}
          onClose={() => {
            setIsDeleteModalOpen(false);
            setSelectedHypervisor(null);
          }}
          onConfirm={() => selectedHypervisor && deleteMutation.mutate(selectedHypervisor.id)}
          title="Supprimer l'hyperviseur"
          message={`Êtes-vous sûr de vouloir supprimer l'hyperviseur "${selectedHypervisor?.name}" ? Cette action est irréversible.`}
          confirmText="Supprimer"
          variant="danger"
          isLoading={deleteMutation.isPending}
        />
      </div>
    </div>
  );
}
