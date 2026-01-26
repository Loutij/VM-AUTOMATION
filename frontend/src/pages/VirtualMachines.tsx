import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Monitor,
  Play,
  Square,
  RotateCw,
  Trash2,
  MoreVertical,
  RefreshCw,
  Server,
  Cpu,
  MemoryStick,
  HardDrive,
  Network,
} from 'lucide-react';
import { Header } from '../components/layout';
import {
  DataTable,
  Button,
  ConfirmModal,
  StatusBadge,
  EmptyState,
  useToast,
  type Column,
} from '../components/ui';
import { vmsApi, hypervisorsApi } from '../services/api';
import type { VirtualMachine, Hypervisor } from '../types';

export function VirtualMachines() {
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  
  const [selectedVM, setSelectedVM] = useState<VirtualMachine | null>(null);
  const [actionModal, setActionModal] = useState<{
    type: 'stop' | 'restart' | 'delete' | null;
    vm: VirtualMachine | null;
  }>({ type: null, vm: null });
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null);
  const [selectedHypervisor, setSelectedHypervisor] = useState<string>('all');

  // Fetch VMs
  const { data: vms = [], isLoading: vmsLoading, refetch } = useQuery({
    queryKey: ['vms', selectedHypervisor],
    queryFn: () => vmsApi.list(selectedHypervisor === 'all' ? undefined : selectedHypervisor),
  });

  // Fetch hypervisors for filter
  const { data: hypervisors = [] } = useQuery({
    queryKey: ['hypervisors'],
    queryFn: hypervisorsApi.list,
  });

  // Start VM mutation
  const startMutation = useMutation({
    mutationFn: (id: string) => vmsApi.start(id),
    onSuccess: (vm) => {
      queryClient.invalidateQueries({ queryKey: ['vms'] });
      addToast({ type: 'success', title: `VM "${vm.name}" démarrée` });
    },
    onError: () => {
      addToast({ type: 'error', title: 'Erreur lors du démarrage' });
    },
  });

  // Stop VM mutation
  const stopMutation = useMutation({
    mutationFn: ({ id, force }: { id: string; force: boolean }) => vmsApi.stop(id, force),
    onSuccess: (vm) => {
      queryClient.invalidateQueries({ queryKey: ['vms'] });
      addToast({ type: 'success', title: `VM "${vm.name}" arrêtée` });
      closeActionModal();
    },
    onError: () => {
      addToast({ type: 'error', title: 'Erreur lors de l\'arrêt' });
    },
  });

  // Restart VM mutation
  const restartMutation = useMutation({
    mutationFn: (id: string) => vmsApi.restart(id),
    onSuccess: (vm) => {
      queryClient.invalidateQueries({ queryKey: ['vms'] });
      addToast({ type: 'success', title: `VM "${vm.name}" redémarrée` });
      closeActionModal();
    },
    onError: () => {
      addToast({ type: 'error', title: 'Erreur lors du redémarrage' });
    },
  });

  // Delete VM mutation
  const deleteMutation = useMutation({
    mutationFn: ({ id, deleteDisks }: { id: string; deleteDisks: boolean }) =>
      vmsApi.delete(id, deleteDisks),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vms'] });
      addToast({ type: 'success', title: 'VM supprimée' });
      closeActionModal();
    },
    onError: () => {
      addToast({ type: 'error', title: 'Erreur lors de la suppression' });
    },
  });

  const openActionModal = (type: 'stop' | 'restart' | 'delete', vm: VirtualMachine) => {
    setActionModal({ type, vm });
    setActiveDropdown(null);
  };

  const closeActionModal = () => {
    setActionModal({ type: null, vm: null });
  };

  const handleStart = (vm: VirtualMachine) => {
    startMutation.mutate(vm.id);
    setActiveDropdown(null);
  };

  const handleConfirmAction = () => {
    if (!actionModal.vm) return;

    switch (actionModal.type) {
      case 'stop':
        stopMutation.mutate({ id: actionModal.vm.id, force: false });
        break;
      case 'restart':
        restartMutation.mutate(actionModal.vm.id);
        break;
      case 'delete':
        deleteMutation.mutate({ id: actionModal.vm.id, deleteDisks: true });
        break;
    }
  };

  const formatMemory = (mb: number) => {
    if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
    return `${mb} MB`;
  };

  const columns: Column<VirtualMachine>[] = [
    {
      key: 'name',
      header: 'Nom',
      sortable: true,
      render: (vm) => (
        <div className="flex items-center gap-3">
          <div
            className={`w-8 h-8 rounded-lg flex items-center justify-center ${
              vm.state === 'running'
                ? 'bg-green-500/20'
                : vm.state === 'paused'
                ? 'bg-yellow-500/20'
                : 'bg-dark-600'
            }`}
          >
            <Monitor
              size={16}
              className={
                vm.state === 'running'
                  ? 'text-green-500'
                  : vm.state === 'paused'
                  ? 'text-yellow-500'
                  : 'text-dark-400'
              }
            />
          </div>
          <div>
            <span className="font-medium text-white">{vm.name}</span>
            {vm.os_type && (
              <p className="text-xs text-dark-400">{vm.os_type}</p>
            )}
          </div>
        </div>
      ),
    },
    {
      key: 'state',
      header: 'État',
      sortable: true,
      render: (vm) => <StatusBadge status={vm.state} />,
    },
    {
      key: 'cpu_count',
      header: 'Ressources',
      render: (vm) => (
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-1.5 text-dark-300">
            <Cpu size={14} />
            <span>{vm.cpu_count} vCPU</span>
          </div>
          <div className="flex items-center gap-1.5 text-dark-300">
            <MemoryStick size={14} />
            <span>{formatMemory(vm.memory_mb)}</span>
          </div>
          <div className="flex items-center gap-1.5 text-dark-300">
            <HardDrive size={14} />
            <span>{vm.disk_size_gb} GB</span>
          </div>
        </div>
      ),
    },
    {
      key: 'ip_address',
      header: 'Réseau',
      render: (vm) => (
        <div className="flex items-center gap-1.5 text-dark-300">
          <Network size={14} />
          <span className="font-mono text-sm">{vm.ip_address || '-'}</span>
        </div>
      ),
    },
  ];

  const renderActions = (vm: VirtualMachine) => {
    const isOpen = activeDropdown === vm.id;
    
    return (
      <div className="relative">
        <Button
          variant="ghost"
          size="sm"
          onClick={(e) => {
            e.stopPropagation();
            setActiveDropdown(isOpen ? null : vm.id);
          }}
          className="!p-1.5"
        >
          <MoreVertical size={16} />
        </Button>
        {isOpen && (
          <>
            <div
              className="fixed inset-0"
              style={{ zIndex: 9998 }}
              onClick={() => setActiveDropdown(null)}
            />
            <div 
              className="absolute right-0 mt-1 w-44 bg-dark-700 border border-dark-600 rounded-lg shadow-xl py-1"
              style={{ zIndex: 9999, top: '100%' }}
            >
              {vm.state !== 'running' && (
                <button
                  onClick={() => handleStart(vm)}
                  disabled={startMutation.isPending}
                  className="w-full flex items-center gap-2 px-4 py-2 text-sm text-green-500 hover:bg-dark-600 transition-colors disabled:opacity-50"
                >
                  <Play size={16} />
                  Démarrer
                </button>
              )}
              {vm.state === 'running' && (
                <>
                  <button
                    onClick={() => openActionModal('stop', vm)}
                    className="w-full flex items-center gap-2 px-4 py-2 text-sm text-yellow-500 hover:bg-dark-600 transition-colors"
                  >
                    <Square size={16} />
                    Arrêter
                  </button>
                  <button
                    onClick={() => openActionModal('restart', vm)}
                    className="w-full flex items-center gap-2 px-4 py-2 text-sm text-blue-500 hover:bg-dark-600 transition-colors"
                  >
                    <RotateCw size={16} />
                    Redémarrer
                  </button>
                </>
              )}
              <div className="border-t border-dark-600 my-1" />
              <button
                onClick={() => openActionModal('delete', vm)}
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
  };

  const getModalConfig = () => {
    const vm = actionModal.vm;
    if (!vm) return null;

    switch (actionModal.type) {
      case 'stop':
        return {
          title: 'Arrêter la VM',
          message: `Êtes-vous sûr de vouloir arrêter la VM "${vm.name}" ?`,
          confirmText: 'Arrêter',
          variant: 'primary' as const,
          isLoading: stopMutation.isPending,
        };
      case 'restart':
        return {
          title: 'Redémarrer la VM',
          message: `Êtes-vous sûr de vouloir redémarrer la VM "${vm.name}" ?`,
          confirmText: 'Redémarrer',
          variant: 'primary' as const,
          isLoading: restartMutation.isPending,
        };
      case 'delete':
        return {
          title: 'Supprimer la VM',
          message: `Êtes-vous sûr de vouloir supprimer la VM "${vm.name}" ? Les disques associés seront également supprimés. Cette action est irréversible.`,
          confirmText: 'Supprimer',
          variant: 'danger' as const,
          isLoading: deleteMutation.isPending,
        };
      default:
        return null;
    }
  };

  const modalConfig = getModalConfig();
  const runningCount = vms.filter((vm) => vm.state === 'running').length;
  const stoppedCount = vms.filter((vm) => vm.state === 'stopped').length;

  return (
    <div className="min-h-screen bg-dark-900">
      <Header title="Machines Virtuelles" />
      <div className="p-6">
        {/* Stats summary */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="card p-4 flex items-center gap-4">
            <div className="w-12 h-12 bg-primary-600/20 rounded-lg flex items-center justify-center">
              <Monitor size={24} className="text-primary-500" />
            </div>
            <div>
              <p className="text-2xl font-bold text-white">{vms.length}</p>
              <p className="text-sm text-dark-400">Total VMs</p>
            </div>
          </div>
          <div className="card p-4 flex items-center gap-4">
            <div className="w-12 h-12 bg-green-500/20 rounded-lg flex items-center justify-center">
              <Play size={24} className="text-green-500" />
            </div>
            <div>
              <p className="text-2xl font-bold text-white">{runningCount}</p>
              <p className="text-sm text-dark-400">En cours d'exécution</p>
            </div>
          </div>
          <div className="card p-4 flex items-center gap-4">
            <div className="w-12 h-12 bg-dark-600 rounded-lg flex items-center justify-center">
              <Square size={24} className="text-dark-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-white">{stoppedCount}</p>
              <p className="text-sm text-dark-400">Arrêtées</p>
            </div>
          </div>
        </div>

        {/* Filters and actions */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <div className="flex items-center gap-2">
            <Server size={18} className="text-dark-400 hidden sm:block" />
            <select
              value={selectedHypervisor}
              onChange={(e) => setSelectedHypervisor(e.target.value)}
              className="flex-1 sm:flex-none bg-dark-700 border border-dark-600 rounded-lg px-3 py-2 text-dark-100 text-sm focus:outline-none focus:border-primary-500"
            >
              <option value="all">Tous les hyperviseurs</option>
              {hypervisors.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.name}
                </option>
              ))}
            </select>
          </div>
          <Button
            variant="secondary"
            leftIcon={<RefreshCw size={18} />}
            onClick={() => refetch()}
            isLoading={vmsLoading}
          >
            Actualiser
          </Button>
        </div>

        {/* Data table */}
        {vms.length === 0 && !vmsLoading ? (
          <div className="card">
            <EmptyState
              icon={Monitor}
              title="Aucune machine virtuelle"
              description="Les VMs de vos hyperviseurs apparaîtront ici. Créez un déploiement pour commencer."
            />
          </div>
        ) : (
          <DataTable
            data={vms}
            columns={columns}
            keyExtractor={(vm) => vm.id}
            isLoading={vmsLoading}
            searchable
            searchPlaceholder="Rechercher une VM..."
            searchKeys={['name', 'ip_address', 'os_type']}
            actions={renderActions}
            emptyMessage="Aucune VM trouvée"
            emptyIcon={<Monitor size={40} className="text-dark-500" />}
          />
        )}

        {/* Action confirmation modal */}
        {modalConfig && (
          <ConfirmModal
            isOpen={actionModal.type !== null}
            onClose={closeActionModal}
            onConfirm={handleConfirmAction}
            title={modalConfig.title}
            message={modalConfig.message}
            confirmText={modalConfig.confirmText}
            variant={modalConfig.variant}
            isLoading={modalConfig.isLoading}
          />
        )}
      </div>
    </div>
  );
}
