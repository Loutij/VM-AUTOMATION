import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Monitor,
  Play,
  Square,
  RotateCw,
  Trash2,
  RefreshCw,
  Server,
  Cpu,
  MemoryStick,
  HardDrive,
  Network,
  Info,
  ExternalLink,
  Activity,
  CheckCircle,
  XCircle,
  Clock,
} from 'lucide-react';
import { Header } from '../components/layout';
import {
  DataTable,
  Button,
  ConfirmModal,
  StatusBadge,
  EmptyState,
  useToast,
  Dropdown,
  Modal,
  type Column,
} from '../components/ui';
import { vmsApi, hypervisorsApi } from '../services/api';
import type { VirtualMachine, VMDetails } from '../types';

export function VirtualMachines() {
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  
  const [actionModal, setActionModal] = useState<{
    type: 'stop' | 'restart' | 'delete' | null;
    vm: VirtualMachine | null;
  }>({ type: null, vm: null });
  const [selectedHypervisor, setSelectedHypervisor] = useState<string>('all');
  const [detailsModal, setDetailsModal] = useState<{ isOpen: boolean; vm: VirtualMachine | null }>({
    isOpen: false,
    vm: null,
  });
  const [vmDetails, setVmDetails] = useState<VMDetails | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);

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
  };

  const closeActionModal = () => {
    setActionModal({ type: null, vm: null });
  };

  const handleStart = (vm: VirtualMachine) => {
    startMutation.mutate(vm.id);
  };

  const handleOpenDetails = async (vm: VirtualMachine) => {
    setDetailsModal({ isOpen: true, vm });
    setVmDetails(null);
    setDetailsLoading(true);
    try {
      const details = await vmsApi.getDetails(vm.id);
      setVmDetails(details);
    } catch (error) {
      addToast({ type: 'error', title: 'Impossible de charger les détails' });
    } finally {
      setDetailsLoading(false);
    }
  };

  const handleDownloadRdp = (vm: VirtualMachine) => {
    const rdpUrl = vmsApi.getRdpUrl(vm.id, 'Administrator');
    window.open(rdpUrl, '_blank');
    addToast({ type: 'success', title: `Fichier RDP pour "${vm.name}" téléchargé` });
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
    const items = [];
    
    // Détails (toujours disponible)
    items.push({
      label: 'Détails',
      icon: <Info size={16} className="text-primary-500" />,
      onClick: () => handleOpenDetails(vm),
    });
    
    // Connexion RDP (si running et Windows)
    if (vm.state === 'running') {
      items.push({
        label: 'Connexion RDP',
        icon: <ExternalLink size={16} className="text-cyan-500" />,
        onClick: () => handleDownloadRdp(vm),
      });
    }
    
    if (vm.state !== 'running') {
      items.push({
        label: 'Démarrer',
        icon: <Play size={16} className="text-green-500" />,
        onClick: () => handleStart(vm),
        disabled: startMutation.isPending,
      });
    }
    
    if (vm.state === 'running') {
      items.push({
        label: 'Arrêter',
        icon: <Square size={16} className="text-yellow-500" />,
        onClick: () => openActionModal('stop', vm),
      });
      items.push({
        label: 'Redémarrer',
        icon: <RotateCw size={16} className="text-blue-500" />,
        onClick: () => openActionModal('restart', vm),
      });
    }
    
    items.push({
      label: 'Supprimer',
      icon: <Trash2 size={16} />,
      onClick: () => openActionModal('delete', vm),
      variant: 'danger' as const,
    });
    
    return <Dropdown items={items} />;
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

        {/* VM Details Modal */}
        <Modal
          isOpen={detailsModal.isOpen}
          onClose={() => setDetailsModal({ isOpen: false, vm: null })}
          title={`Détails de ${detailsModal.vm?.name || 'VM'}`}
          size="xl"
        >
          {detailsLoading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw size={32} className="animate-spin text-primary-500" />
              <span className="ml-3 text-dark-300">Chargement des détails...</span>
            </div>
          ) : vmDetails ? (
            <div className="space-y-6 max-h-[70vh] overflow-y-auto">
              {/* État et ressources en temps réel */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-dark-700 rounded-lg p-4">
                  <div className="flex items-center gap-2 text-dark-400 mb-1">
                    <Activity size={16} />
                    <span className="text-sm">État</span>
                  </div>
                  <StatusBadge status={vmDetails.general.state.toLowerCase() as VirtualMachine['state']} />
                </div>
                <div className="bg-dark-700 rounded-lg p-4">
                  <div className="flex items-center gap-2 text-dark-400 mb-1">
                    <Cpu size={16} />
                    <span className="text-sm">CPU</span>
                  </div>
                  <p className="text-xl font-bold text-white">{vmDetails.resources.cpu_usage_percent}%</p>
                  <p className="text-xs text-dark-400">{vmDetails.configuration.cpu_count} vCPU</p>
                </div>
                <div className="bg-dark-700 rounded-lg p-4">
                  <div className="flex items-center gap-2 text-dark-400 mb-1">
                    <MemoryStick size={16} />
                    <span className="text-sm">RAM</span>
                  </div>
                  <p className="text-xl font-bold text-white">{vmDetails.resources.ram_assigned_gb} GB</p>
                  <p className="text-xs text-dark-400">
                    {vmDetails.configuration.dynamic_memory 
                      ? `Dynamique (${vmDetails.configuration.ram_minimum_gb}-${vmDetails.configuration.ram_maximum_gb} GB)`
                      : 'Statique'
                    }
                  </p>
                </div>
                <div className="bg-dark-700 rounded-lg p-4">
                  <div className="flex items-center gap-2 text-dark-400 mb-1">
                    <Clock size={16} />
                    <span className="text-sm">Uptime</span>
                  </div>
                  <p className="text-lg font-medium text-white">{vmDetails.general.uptime || '-'}</p>
                </div>
              </div>

              {/* Configuration */}
              <div>
                <h4 className="text-sm font-medium text-dark-300 mb-3 flex items-center gap-2">
                  <Server size={16} />
                  Configuration
                </h4>
                <div className="bg-dark-700 rounded-lg p-4 grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <span className="text-dark-400">Génération:</span>
                    <span className="ml-2 text-white">Gen {vmDetails.general.generation}</span>
                  </div>
                  <div>
                    <span className="text-dark-400">Version:</span>
                    <span className="ml-2 text-white">{vmDetails.general.version}</span>
                  </div>
                  <div>
                    <span className="text-dark-400">Secure Boot:</span>
                    <span className="ml-2 text-white">{vmDetails.configuration.secure_boot ? 'Activé' : 'Désactivé'}</span>
                  </div>
                  <div>
                    <span className="text-dark-400">TPM:</span>
                    <span className="ml-2 text-white">{vmDetails.configuration.tpm_enabled ? 'Activé' : 'Non'}</span>
                  </div>
                  <div className="col-span-2">
                    <span className="text-dark-400">Chemin:</span>
                    <span className="ml-2 text-white font-mono text-xs">{vmDetails.general.path}</span>
                  </div>
                </div>
              </div>

              {/* Disques */}
              <div>
                <h4 className="text-sm font-medium text-dark-300 mb-3 flex items-center gap-2">
                  <HardDrive size={16} />
                  Disques ({vmDetails.disks.length})
                </h4>
                <div className="space-y-2">
                  {vmDetails.disks.map((disk, idx) => (
                    <div key={idx} className="bg-dark-700 rounded-lg p-3">
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="text-white font-medium">{disk.type || 'Disque'}</span>
                          {disk.size_gb && (
                            <span className="ml-2 text-dark-400">
                              {disk.size_used_gb ? `${disk.size_used_gb}/${disk.size_gb} GB` : `${disk.size_gb} GB`}
                            </span>
                          )}
                        </div>
                        <span className="text-xs text-dark-400">{disk.format}</span>
                      </div>
                      <p className="text-xs text-dark-500 font-mono mt-1 truncate">{disk.path}</p>
                      {disk.size_gb && disk.size_used_gb && (
                        <div className="mt-2 h-1.5 bg-dark-600 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-primary-500 rounded-full"
                            style={{ width: `${(disk.size_used_gb / disk.size_gb) * 100}%` }}
                          />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Réseau */}
              <div>
                <h4 className="text-sm font-medium text-dark-300 mb-3 flex items-center gap-2">
                  <Network size={16} />
                  Adaptateurs réseau ({vmDetails.network_adapters.length})
                </h4>
                <div className="space-y-2">
                  {vmDetails.network_adapters.map((nic, idx) => (
                    <div key={idx} className="bg-dark-700 rounded-lg p-3">
                      <div className="flex items-center justify-between">
                        <span className="text-white font-medium">{nic.name}</span>
                        <StatusBadge status={nic.status.toLowerCase() === 'ok' ? 'running' : 'stopped'} />
                      </div>
                      <div className="grid grid-cols-2 gap-2 mt-2 text-sm">
                        <div>
                          <span className="text-dark-400">Switch:</span>
                          <span className="ml-2 text-white">{nic.switch_name || '-'}</span>
                        </div>
                        <div>
                          <span className="text-dark-400">VLAN:</span>
                          <span className="ml-2 text-white">{nic.vlan_id || 'Aucun'}</span>
                        </div>
                        <div>
                          <span className="text-dark-400">MAC:</span>
                          <span className="ml-2 text-white font-mono text-xs">{nic.mac_address || '-'}</span>
                        </div>
                        <div>
                          <span className="text-dark-400">IP:</span>
                          <span className="ml-2 text-white font-mono">
                            {nic.ip_addresses?.length > 0 ? nic.ip_addresses.join(', ') : '-'}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Services d'intégration */}
              <div>
                <h4 className="text-sm font-medium text-dark-300 mb-3 flex items-center gap-2">
                  <CheckCircle size={16} />
                  Services d'intégration
                </h4>
                <div className="bg-dark-700 rounded-lg p-3">
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    {vmDetails.integration_services.map((svc, idx) => (
                      <div key={idx} className="flex items-center gap-2 text-sm">
                        {svc.enabled && svc.status === 'Ok' ? (
                          <CheckCircle size={14} className="text-green-500" />
                        ) : svc.enabled ? (
                          <XCircle size={14} className="text-yellow-500" />
                        ) : (
                          <XCircle size={14} className="text-dark-500" />
                        )}
                        <span className={svc.enabled ? 'text-white' : 'text-dark-400'}>{svc.name}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Checkpoints */}
              {vmDetails.checkpoints.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-dark-300 mb-3">
                    Checkpoints ({vmDetails.checkpoints.length})
                  </h4>
                  <div className="bg-dark-700 rounded-lg p-3 space-y-2">
                    {vmDetails.checkpoints.map((cp) => (
                      <div key={cp.id} className="flex items-center justify-between text-sm">
                        <span className="text-white">{cp.name}</span>
                        <span className="text-dark-400">{new Date(cp.creation_time).toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-8 text-dark-400">
              Impossible de charger les détails
            </div>
          )}
        </Modal>
      </div>
    </div>
  );
}
