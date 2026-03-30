import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Server,
  Plus,
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
  EmptyState,
  useToast,
  Dropdown,
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
  // VMware-specific
  datacenter: string;
  cluster: string;
  default_datastore: string;
  default_resource_pool: string;
}

const defaultFormData: HypervisorFormData = {
  name: '',
  type: 'hyperv',
  host: '',
  port: '',
  username: '',
  password: '',
  datacenter: '',
  cluster: '',
  default_datastore: 'datastore1',
  default_resource_pool: '',
};

const DEFAULT_PORTS: Record<string, string> = {
  hyperv: '5986',
  vmware: '443',
};

export function Hypervisors() {
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [selectedHypervisor, setSelectedHypervisor] = useState<Hypervisor | null>(null);
  const [formData, setFormData] = useState<HypervisorFormData>(defaultFormData);

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
        datacenter: hypervisor.datacenter || '',
        cluster: hypervisor.cluster || '',
        default_datastore: hypervisor.default_datastore || 'datastore1',
        default_resource_pool: hypervisor.default_resource_pool || '',
      });
    } else {
      setSelectedHypervisor(null);
      setFormData(defaultFormData);
    }
    setIsModalOpen(true);
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
      // VMware-specific fields
      ...(formData.type === 'vmware' && {
        datacenter: formData.datacenter || undefined,
        cluster: formData.cluster || undefined,
        default_datastore: formData.default_datastore || undefined,
        default_resource_pool: formData.default_resource_pool || undefined,
      }),
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
  };

  const handleTestConnection = (hypervisor: Hypervisor) => {
    testConnectionMutation.mutate(hypervisor.id);
  };

  const columns: Column<Hypervisor>[] = [
    {
      key: 'name',
      header: 'Nom',
      sortable: true,
      render: (h) => (
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-oto-100 dark:bg-primary-600/20 rounded-lg flex items-center justify-center">
            <Server size={16} className="text-oto-500" />
          </div>
          <span className="font-medium text-gray-900 dark:text-white">{h.name}</span>
        </div>
      ),
    },
    {
      key: 'type',
      header: 'Type',
      sortable: true,
      render: (h) => (
        <span className="px-2 py-1 bg-light-200 dark:bg-dark-700 rounded text-sm text-gray-700 dark:text-gray-300">
          {h.type === 'vmware' ? 'VMware ESXi' : 'Hyper-V'}
        </span>
      ),
    },
    {
      key: 'host',
      header: 'Hôte',
      sortable: true,
      render: (h) => <span className="font-mono text-sm">{h.host}</span>,
    },
    {
      key: 'is_active',
      header: 'Statut',
      render: (h) => (
        <div className="flex items-center gap-2">
          {h.is_active ? (
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
    <Dropdown
      items={[
        {
          label: 'Tester la connexion',
          icon: <Plug size={16} />,
          onClick: () => handleTestConnection(hypervisor),
        },
        {
          label: 'Modifier',
          icon: <Pencil size={16} />,
          onClick: () => handleOpenModal(hypervisor),
        },
        {
          label: 'Supprimer',
          icon: <Trash2 size={16} />,
          onClick: () => handleDelete(hypervisor),
          variant: 'danger',
        },
      ]}
    />
  );

  return (
    <div className="min-h-screen bg-light-100 dark:bg-dark-900">
      <Header title="Hyperviseurs" />
      <div className="p-4 sm:p-6">
        {/* Header actions */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <p className="text-gray-500 dark:text-dark-400 text-sm sm:text-base">
            Gérez vos connexions aux serveurs Hyper-V et VMware
          </p>
          <div className="flex items-center gap-2 sm:gap-3">
            <Button
              variant="secondary"
              leftIcon={<RefreshCw size={18} />}
              onClick={() => refetch()}
              isLoading={isLoading}
              className="flex-1 sm:flex-none"
            >
              <span className="hidden sm:inline">Actualiser</span>
              <span className="sm:hidden">Actualiser</span>
            </Button>
            <Button
              leftIcon={<Plus size={18} />}
              onClick={() => handleOpenModal()}
              className="flex-1 sm:flex-none"
            >
              <span className="hidden sm:inline">Ajouter un hyperviseur</span>
              <span className="sm:hidden">Ajouter</span>
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
            emptyIcon={<Server size={40} className="text-gray-400 dark:text-dark-500" />}
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
              onChange={(e) => {
                const newType = e.target.value as 'hyperv' | 'vmware';
                setFormData({
                  ...formData,
                  type: newType,
                  port: DEFAULT_PORTS[newType] || '',
                });
              }}
              options={[
                { value: 'hyperv', label: 'Hyper-V' },
                { value: 'vmware', label: 'VMware ESXi' },
              ]}
              required
            />
            <Input
              label="Hôte"
              value={formData.host}
              onChange={(e) => setFormData({ ...formData, host: e.target.value })}
              placeholder={formData.type === 'vmware' ? '192.168.1.100 ou vcenter.domain.local' : '192.168.1.100 ou hyperv.domain.local'}
              required
            />
            <Input
              label="Port"
              type="number"
              value={formData.port}
              onChange={(e) => setFormData({ ...formData, port: e.target.value })}
              placeholder={formData.type === 'vmware' ? '443 (vSphere)' : '5986 (WinRM)'}
              helperText={`Par défaut : ${formData.type === 'vmware' ? '443' : '5986'}`}
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

            {/* VMware-specific fields */}
            {formData.type === 'vmware' && (
              <div className="space-y-4 pt-2 border-t border-gray-200 dark:border-dark-600">
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  Configuration VMware
                </p>
                <Input
                  label="Datacenter"
                  value={formData.datacenter}
                  onChange={(e) => setFormData({ ...formData, datacenter: e.target.value })}
                  placeholder="ha-datacenter"
                  helperText="Nom du datacenter vSphere"
                />
                <Input
                  label="Cluster"
                  value={formData.cluster}
                  onChange={(e) => setFormData({ ...formData, cluster: e.target.value })}
                  placeholder="MonCluster"
                  helperText="Nom du cluster (optionnel pour ESXi standalone)"
                />
                <Input
                  label="Datastore par défaut"
                  value={formData.default_datastore}
                  onChange={(e) => setFormData({ ...formData, default_datastore: e.target.value })}
                  placeholder="datastore1"
                  helperText="Datastore utilisé par défaut pour les VMs"
                />
                <Input
                  label="Resource Pool"
                  value={formData.default_resource_pool}
                  onChange={(e) => setFormData({ ...formData, default_resource_pool: e.target.value })}
                  placeholder="Resources"
                  helperText="Resource pool (optionnel)"
                />
              </div>
            )}
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
