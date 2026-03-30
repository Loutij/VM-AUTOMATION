import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams, useNavigate } from 'react-router-dom';
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
  Camera,
  Maximize2,
  CloudDownload,
  Tag,
  Pause,
  Save,
  Terminal,
  Download,
  Package,
  Search,
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
import { vmsApi, hypervisorsApi, vncApi } from '../services/api';
import { VNCInstallModal } from '../components/vm/VNCInstallModal';
import type { VirtualMachine, VMDetails, VMState, SoftwareInventory } from '../types';

// Types pour les filtres d'état
type StateFilter = 'all' | VMState;

const stateFilterLabels: Record<StateFilter, string> = {
  all: 'Tous',
  running: 'Running',
  stopped: 'Stopped',
  paused: 'Paused',
  saved: 'Saved',
  unknown: 'Unknown',
};

const stateFilters: StateFilter[] = ['all', 'running', 'stopped', 'paused', 'saved'];

export function VirtualMachines() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { addToast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();

  // Lire les filtres depuis l'URL
  const stateFilter = (searchParams.get('state') as StateFilter) || 'all';
  const hypervisorFilter = searchParams.get('hypervisor_id') || 'all';
  const searchFilter = searchParams.get('search') || '';

  // Fonction utilitaire pour mettre à jour les query params
  const updateParams = useCallback((updates: Record<string, string | null>) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      for (const [key, value] of Object.entries(updates)) {
        if (value === null || value === '' || value === 'all') {
          next.delete(key);
        } else {
          next.set(key, value);
        }
      }
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const setStateFilter = useCallback((state: StateFilter) => {
    updateParams({ state: state === 'all' ? null : state });
  }, [updateParams]);

  const setHypervisorFilter = useCallback((id: string) => {
    updateParams({ hypervisor_id: id === 'all' ? null : id });
  }, [updateParams]);

  const setSearchFilter = useCallback((search: string) => {
    updateParams({ search: search || null });
  }, [updateParams]);

  const resetAllFilters = useCallback(() => {
    setSearchParams({}, { replace: true });
  }, [setSearchParams]);

  const [actionModal, setActionModal] = useState<{
    type: 'stop' | 'restart' | 'delete' | null;
    vm: VirtualMachine | null;
  }>({ type: null, vm: null });
  const [bulkActionModal, setBulkActionModal] = useState<{
    type: 'start' | 'stop' | 'restart' | 'delete' | null;
  }>({ type: null });
  const [bulkActionLoading, setBulkActionLoading] = useState(false);
  const [detailsModal, setDetailsModal] = useState<{ isOpen: boolean; vm: VirtualMachine | null }>({
    isOpen: false,
    vm: null,
  });
  const [vmDetails, setVmDetails] = useState<VMDetails | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);

  // Bulk selection
  const [selectedVmIds, setSelectedVmIds] = useState<Set<string>>(new Set());

  // Screenshot modal
  const [screenshotModal, setScreenshotModal] = useState<{ isOpen: boolean; vm: VirtualMachine | null }>({
    isOpen: false,
    vm: null,
  });
  const [screenshotData, setScreenshotData] = useState<string | null>(null);
  const [screenshotLoading, setScreenshotLoading] = useState(false);
  const [screenshotError, setScreenshotError] = useState<string | null>(null);

  // VNC install modal
  const [vncInstallModal, setVncInstallModal] = useState<{ isOpen: boolean; vm: VirtualMachine | null }>({
    isOpen: false,
    vm: null,
  });
  // VNC status cache per VM id
  const [, setVncStatuses] = useState<Record<string, 'unknown' | 'checking' | 'available' | 'unavailable' | 'installing'>>({});

  // Software inventory modal
  const [inventoryModal, setInventoryModal] = useState<{ isOpen: boolean; vm: VirtualMachine | null }>({
    isOpen: false,
    vm: null,
  });
  const [inventoryData, setInventoryData] = useState<SoftwareInventory | null>(null);
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [inventoryError, setInventoryError] = useState<string | null>(null);
  const [inventoryTab, setInventoryTab] = useState<'choco' | 'programs' | 'features' | 'services' | 'updates' | 'linux' | 'snap'>('choco');
  const [inventorySearch, setInventorySearch] = useState('');

  // Etats pour la synchronisation automatique
  const [isAutoSyncing, setIsAutoSyncing] = useState(false);
  const syncIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch VMs
  const { data: vms = [], isLoading: vmsLoading, refetch } = useQuery({
    queryKey: ['vms', hypervisorFilter],
    queryFn: () => vmsApi.list(hypervisorFilter === 'all' ? undefined : hypervisorFilter),
  });

  // Fetch hypervisors for filter
  const { data: hypervisors = [] } = useQuery({
    queryKey: ['hypervisors'],
    queryFn: hypervisorsApi.list,
  });

  // Filtrer les VMs par etat (cote client, apres le fetch par hyperviseur)
  const filteredVms = useMemo(() => {
    if (stateFilter === 'all') return vms;
    return vms.filter((vm) => vm.state === stateFilter);
  }, [vms, stateFilter]);

  // Compteurs sur les VMs non-filtrees (toutes les VMs du fetch)
  const totalCount = vms.length;
  const runningCount = vms.filter((vm) => vm.state === 'running').length;
  const stoppedCount = vms.filter((vm) => vm.state === 'stopped').length;

  // Determiner si un filtre est actif
  const hasActiveFilter = stateFilter !== 'all' || hypervisorFilter !== 'all' || searchFilter !== '';

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
    mutationFn: ({ id, deleteDisks, force }: { id: string; deleteDisks: boolean; force?: boolean }) =>
      vmsApi.delete(id, { deleteDisks, force }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vms'] });
      addToast({ type: 'success', title: 'VM supprimée' });
      closeActionModal();
    },
    onError: () => {
      addToast({ type: 'error', title: 'Erreur lors de la suppression' });
    },
  });

  // Sync VMs mutation
  const syncMutation = useMutation({
    mutationFn: (hypervisorId: string) => hypervisorsApi.syncVms(hypervisorId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['vms'] });
      if (result.success) {
        const messages: string[] = [];
        if (result.imported > 0) messages.push(`${result.imported} importée(s)`);
        if (result.updated > 0) messages.push(`${result.updated} mise(s) à jour`);
        if (result.marked_missing > 0) messages.push(`${result.marked_missing} marquée(s) absente(s)`);

        addToast({
          type: 'success',
          title: 'Synchronisation terminée',
          message: messages.length > 0 ? messages.join(', ') : 'Aucun changement',
        });
      } else {
        addToast({
          type: 'warning',
          title: 'Synchronisation avec erreurs',
          message: result.errors.join(', '),
        });
      }
    },
    onError: () => {
      addToast({ type: 'error', title: 'Erreur lors de la synchronisation' });
    },
  });

  // Fonction de synchronisation automatique (sans toast)
  const performAutoSync = useCallback(async () => {
    if (isAutoSyncing || syncMutation.isPending || vmsLoading || hypervisors.length === 0) {
      return;
    }

    setIsAutoSyncing(true);
    try {
      if (hypervisorFilter === 'all') {
        for (const hypervisor of hypervisors) {
          try {
            await hypervisorsApi.syncVms(hypervisor.id);
          } catch (error) {
            console.error(`Auto-sync error for hypervisor ${hypervisor.name}:`, error);
          }
        }
      } else {
        try {
          await hypervisorsApi.syncVms(hypervisorFilter);
        } catch (error) {
          console.error(`Auto-sync error for hypervisor ${hypervisorFilter}:`, error);
        }
      }
      queryClient.invalidateQueries({ queryKey: ['vms'] });
    } catch (error) {
      console.error('Auto-sync error:', error);
    } finally {
      setIsAutoSyncing(false);
    }
  }, [hypervisorFilter, hypervisors, queryClient, isAutoSyncing, syncMutation.isPending, vmsLoading]);

  // Effet pour la synchronisation periodique (toutes les 5 minutes)
  useEffect(() => {
    if (hypervisors.length === 0) return;

    syncIntervalRef.current = setInterval(() => {
      performAutoSync();
    }, 300000);

    return () => {
      if (syncIntervalRef.current) {
        clearInterval(syncIntervalRef.current);
        syncIntervalRef.current = null;
      }
    };
  }, [performAutoSync, hypervisors.length]);

  // Gestion de la visibilite de la page pour mettre en pause la synchronisation
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden) {
        if (syncIntervalRef.current) {
          clearInterval(syncIntervalRef.current);
          syncIntervalRef.current = null;
        }
      } else {
        if (!syncIntervalRef.current && hypervisors.length > 0) {
          syncIntervalRef.current = setInterval(() => {
            performAutoSync();
          }, 300000);
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [performAutoSync, hypervisors.length]);

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
    const rdpUrl = vmsApi.getRdpUrl(vm.id);
    window.open(rdpUrl, '_blank');
    addToast({
      type: 'success',
      title: `Fichier RDP pour "${vm.name}" téléchargé`,
      message: 'Identifiants: .\\otoroot / tooroto'
    });
  };

  const handleCaptureScreenshot = async (vm: VirtualMachine) => {
    setScreenshotModal({ isOpen: true, vm });
    setScreenshotData(null);
    setScreenshotError(null);
    setScreenshotLoading(true);
    try {
      const result = await vmsApi.getScreenshot(vm.id, 1024, 768);
      setScreenshotData(result.image);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erreur lors de la capture';
      setScreenshotError(message);
    } finally {
      setScreenshotLoading(false);
    }
  };

  const handleRefreshScreenshot = async () => {
    if (!screenshotModal.vm) return;
    setScreenshotLoading(true);
    setScreenshotError(null);
    try {
      const result = await vmsApi.getScreenshot(screenshotModal.vm.id, 1024, 768);
      setScreenshotData(result.image);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erreur lors de la capture';
      setScreenshotError(message);
    } finally {
      setScreenshotLoading(false);
    }
  };


  const handleOpenVncInstall = (vm: VirtualMachine) => {
    setVncInstallModal({ isOpen: true, vm });
  };

  const handleOpenInventory = async (vm: VirtualMachine) => {
    setInventoryModal({ isOpen: true, vm });
    setInventoryData(null);
    setInventoryError(null);
    setInventoryLoading(true);
    setInventoryTab('choco');
    setInventorySearch('');
    try {
      const data = await vmsApi.getSoftwareInventory(vm.id);
      setInventoryData(data);
      // Auto-select the right tab based on OS
      if (data.os_type !== 'windows' && data.packages && data.packages.length > 0) {
        setInventoryTab('linux');
      }
    } catch (error) {
      const axiosErr = error as { response?: { data?: { detail?: string } }; message?: string };
      const message = axiosErr.response?.data?.detail || axiosErr.message || 'Impossible de récupérer l\'inventaire logiciel';
      setInventoryError(message);
    } finally {
      setInventoryLoading(false);
    }
  };

  const handleVncInstall = useCallback(async (config: { port: number; username: string; password: string }) => {
    const vm = vncInstallModal.vm;
    if (!vm) return;
    setVncStatuses(prev => ({ ...prev, [vm.id]: 'installing' }));
    try {
      await vncApi.installVNC(vm.id, { port: config.port, username: config.username });
      setVncStatuses(prev => ({ ...prev, [vm.id]: 'available' }));
      addToast({ type: 'success', title: `VNC installé sur "${vm.name}"` });
    } catch (err) {
      setVncStatuses(prev => ({ ...prev, [vm.id]: 'unavailable' }));
      throw err;
    }
  }, [vncInstallModal.vm, addToast]);

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
        const forceDelete = actionModal.vm.state === 'unknown';
        deleteMutation.mutate({ id: actionModal.vm.id, deleteDisks: true, force: forceDelete });
        break;
    }
  };

  // Bulk actions
  const selectedVms = useMemo(() => {
    return filteredVms.filter((vm) => selectedVmIds.has(vm.id));
  }, [filteredVms, selectedVmIds]);

  const handleBulkConfirm = async () => {
    if (selectedVms.length === 0 || !bulkActionModal.type) return;
    setBulkActionLoading(true);
    let successCount = 0;
    let errorCount = 0;

    for (const vm of selectedVms) {
      try {
        switch (bulkActionModal.type) {
          case 'start':
            if (vm.state !== 'running') {
              await vmsApi.start(vm.id);
              successCount++;
            }
            break;
          case 'stop':
            if (vm.state === 'running') {
              await vmsApi.stop(vm.id, false);
              successCount++;
            }
            break;
          case 'restart':
            if (vm.state === 'running') {
              await vmsApi.restart(vm.id);
              successCount++;
            }
            break;
          case 'delete':
            await vmsApi.delete(vm.id, { deleteDisks: true, force: vm.state === 'unknown' });
            successCount++;
            break;
        }
      } catch {
        errorCount++;
      }
    }

    queryClient.invalidateQueries({ queryKey: ['vms'] });
    const actionLabel = { start: 'démarrée', stop: 'arrêtée', restart: 'redémarrée', delete: 'supprimée' }[bulkActionModal.type];
    if (successCount > 0) {
      addToast({ type: 'success', title: `${successCount} VM${successCount > 1 ? 's' : ''} ${actionLabel}${successCount > 1 ? 's' : ''}` });
    }
    if (errorCount > 0) {
      addToast({ type: 'error', title: `${errorCount} erreur${errorCount > 1 ? 's' : ''} lors de l'action groupée` });
    }
    setBulkActionLoading(false);
    setBulkActionModal({ type: null });
    setSelectedVmIds(new Set());
  };

  const getBulkModalConfig = () => {
    const count = selectedVms.length;
    switch (bulkActionModal.type) {
      case 'start':
        return {
          title: `Démarrer ${count} VM${count > 1 ? 's' : ''}`,
          message: `Voulez-vous démarrer les ${count} VM sélectionnées ?`,
          confirmText: 'Démarrer tout',
          variant: 'primary' as const,
        };
      case 'stop':
        return {
          title: `Arrêter ${count} VM${count > 1 ? 's' : ''}`,
          message: `Voulez-vous arrêter les ${count} VM sélectionnées ?`,
          confirmText: 'Arrêter tout',
          variant: 'primary' as const,
        };
      case 'restart':
        return {
          title: `Redémarrer ${count} VM${count > 1 ? 's' : ''}`,
          message: `Voulez-vous redémarrer les ${count} VM sélectionnées ?`,
          confirmText: 'Redémarrer tout',
          variant: 'primary' as const,
        };
      case 'delete':
        return {
          title: `Supprimer ${count} VM${count > 1 ? 's' : ''}`,
          message: `Êtes-vous sûr de vouloir supprimer les ${count} VM sélectionnées ? Les disques associés seront également supprimés. Cette action est irréversible.`,
          confirmText: 'Supprimer tout',
          variant: 'danger' as const,
        };
      default:
        return null;
    }
  };

  // Clear selection when filters change
  useEffect(() => {
    setSelectedVmIds(new Set());
  }, [stateFilter, hypervisorFilter]);


  // Indicateur de statut en ligne (point colore)
  const getStatusDot = (state: VMState) => {
    switch (state) {
      case 'running':
        return 'bg-green-500';
      case 'stopped':
        return 'bg-red-500';
      case 'paused':
        return 'bg-yellow-500';
      case 'saved':
        return 'bg-blue-500';
      default:
        return 'bg-gray-400';
    }
  };

  const columns: Column<VirtualMachine>[] = [
    {
      key: 'name',
      header: 'Nom',
      sortable: true,
      render: (vm) => (
        <div className="flex items-center gap-3">
          <div className="relative">
            <div
              className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                vm.state === 'running'
                  ? 'bg-green-500/20'
                  : vm.state === 'paused'
                  ? 'bg-yellow-500/20'
                  : 'bg-light-200 dark:bg-dark-600'
              }`}
            >
              <Monitor
                size={16}
                className={
                  vm.state === 'running'
                    ? 'text-green-500'
                    : vm.state === 'paused'
                    ? 'text-yellow-500'
                    : 'text-gray-400 dark:text-dark-400'
                }
              />
            </div>
            {/* Indicateur en ligne (point vert/rouge) */}
            <span
              className={`absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-white dark:border-dark-800 ${getStatusDot(vm.state)}`}
            />
          </div>
          <div>
            <span className="font-medium text-gray-900 dark:text-white">{vm.name}</span>
            {vm.os_type && (
              <p className="text-xs text-gray-500 dark:text-dark-400">{vm.os_type}</p>
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
      header: 'CPU',
      sortable: true,
      render: (vm) => (
        <div className="flex items-center gap-1.5 text-sm text-gray-600 dark:text-dark-300">
          <Cpu size={14} />
          <span>{vm.cpu_count} vCPU</span>
        </div>
      ),
    },
    {
      key: 'ram_gb',
      header: 'RAM',
      sortable: true,
      render: (vm) => (
        <div className="flex items-center gap-1.5 text-sm text-gray-600 dark:text-dark-300">
          <MemoryStick size={14} />
          <span>{vm.ram_gb} Go</span>
        </div>
      ),
    },
    {
      key: 'disk_gb',
      header: 'Disque',
      sortable: true,
      render: (vm) => (
        <div className="flex items-center gap-1.5 text-sm text-gray-600 dark:text-dark-300">
          <HardDrive size={14} />
          <span>{vm.disk_gb} Go</span>
        </div>
      ),
    },
    {
      key: 'ip_address',
      header: 'Réseau',
      render: (vm) => (
        <div className="flex items-center gap-1.5 text-gray-600 dark:text-dark-300">
          <Network size={14} />
          <span className="font-mono text-sm">{vm.ip_address || '-'}</span>
        </div>
      ),
    },
    {
      key: 'vlan_id',
      header: 'VLAN',
      sortable: true,
      render: (vm) => (
        <div className="flex items-center gap-1.5 text-gray-600 dark:text-dark-300">
          <Tag size={14} />
          <span className="font-mono text-sm">
            {vm.vlan_id ? `VLAN ${vm.vlan_id}` : '-'}
          </span>
        </div>
      ),
    },
  ];

  const renderActions = (vm: VirtualMachine) => {
    const items = [];

    // Details (toujours disponible)
    items.push({
      label: 'Détails',
      icon: <Info size={16} className="text-primary-500" />,
      onClick: () => handleOpenDetails(vm),
    });

    // Aperçu écran (si running)
    if (vm.state === 'running') {
      items.push({
        label: 'Aperçu écran',
        icon: <Camera size={16} className="text-purple-500" />,
        onClick: () => handleCaptureScreenshot(vm),
      });
    }

    // Console interactive (si running)
    if (vm.state === 'running') {
      items.push({
        label: 'Console',
        icon: <Monitor size={16} className="text-indigo-500" />,
        onClick: () => navigate(`/vms/${vm.id}/console`),
      });
      items.push({
        label: 'VNC (noVNC)',
        icon: <Monitor size={16} className="text-blue-500" />,
        onClick: () => navigate(`/vms/${vm.id}/vnc`),
      });
      items.push({
        label: 'Terminal',
        icon: <Terminal size={16} className="text-green-500" />,
        onClick: () => navigate(`/vms/${vm.id}/console?tab=terminal`),
      });
    }

    // Connexion RDP (si running)
    if (vm.state === 'running') {
      items.push({
        label: 'Connexion RDP',
        icon: <ExternalLink size={16} className="text-cyan-500" />,
        onClick: () => handleDownloadRdp(vm),
      });
    }

    // Installer VNC (si running)
    if (vm.state === 'running') {
      items.push({
        label: 'Installer VNC',
        icon: <Download size={16} className="text-teal-500" />,
        onClick: () => handleOpenVncInstall(vm),
      });
    }

    // Inventaire logiciel (si running)
    if (vm.state === 'running') {
      items.push({
        label: 'Inventaire logiciel',
        icon: <Package size={16} className="text-orange-500" />,
        onClick: () => handleOpenInventory(vm),
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

  // Icone pour les filtres d'etat
  const getStateFilterIcon = (state: StateFilter) => {
    switch (state) {
      case 'running': return <Play size={14} />;
      case 'stopped': return <Square size={14} />;
      case 'paused': return <Pause size={14} />;
      case 'saved': return <Save size={14} />;
      default: return null;
    }
  };

  const bulkActionsBar = (
    <div className="flex items-center gap-2">
      <Button size="sm" variant="secondary" leftIcon={<Play size={14} />} onClick={() => setBulkActionModal({ type: 'start' })}>
        Démarrer
      </Button>
      <Button size="sm" variant="secondary" leftIcon={<Square size={14} />} onClick={() => setBulkActionModal({ type: 'stop' })}>
        Arrêter
      </Button>
      <Button size="sm" variant="secondary" leftIcon={<RotateCw size={14} />} onClick={() => setBulkActionModal({ type: 'restart' })}>
        Redémarrer
      </Button>
      <Button size="sm" variant="danger" leftIcon={<Trash2 size={14} />} onClick={() => setBulkActionModal({ type: 'delete' })}>
        Supprimer
      </Button>
    </div>
  );

  const bulkModalConfig = getBulkModalConfig();

  return (
    <div className="min-h-screen bg-light-100 dark:bg-dark-900">
      <Header title="Machines Virtuelles" />
      <div className="p-4 sm:p-6">
        {/* Stats summary - Cliquables */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          {/* Total VMs */}
          <button
            onClick={resetAllFilters}
            className={`card p-4 flex items-center gap-4 text-left transition-all hover:shadow-md ${
              !hasActiveFilter
                ? 'ring-2 ring-oto-500 dark:ring-primary-500'
                : ''
            }`}
          >
            <div className="w-12 h-12 bg-oto-100 dark:bg-primary-600/20 rounded-lg flex items-center justify-center">
              <Monitor size={24} className="text-oto-500 dark:text-primary-500" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{totalCount}</p>
              <p className="text-sm text-gray-500 dark:text-dark-400">Total VMs</p>
            </div>
          </button>
          {/* VMs en cours */}
          <button
            onClick={() => setStateFilter('running')}
            className={`card p-4 flex items-center gap-4 text-left transition-all hover:shadow-md ${
              stateFilter === 'running'
                ? 'ring-2 ring-green-500'
                : ''
            }`}
          >
            <div className="w-12 h-12 bg-green-100 dark:bg-green-500/20 rounded-lg flex items-center justify-center">
              <Play size={24} className="text-green-600 dark:text-green-500" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{runningCount}</p>
              <p className="text-sm text-gray-500 dark:text-dark-400">En cours d'exécution</p>
            </div>
          </button>
          {/* VMs arretees */}
          <button
            onClick={() => setStateFilter('stopped')}
            className={`card p-4 flex items-center gap-4 text-left transition-all hover:shadow-md ${
              stateFilter === 'stopped'
                ? 'ring-2 ring-gray-500 dark:ring-dark-400'
                : ''
            }`}
          >
            <div className="w-12 h-12 bg-gray-100 dark:bg-dark-600 rounded-lg flex items-center justify-center">
              <Square size={24} className="text-gray-400 dark:text-dark-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{stoppedCount}</p>
              <p className="text-sm text-gray-500 dark:text-dark-400">Arrêtées</p>
            </div>
          </button>
        </div>

        {/* Filtres par etat (pills) + dropdown hyperviseur */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-4">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            {/* Boutons de filtre par etat */}
            <div className="flex items-center bg-white dark:bg-dark-800 rounded-lg p-1 flex-wrap gap-1 border border-light-200 dark:border-transparent">
              {stateFilters.map((state) => (
                <button
                  key={state}
                  onClick={() => setStateFilter(state)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    stateFilter === state
                      ? 'bg-oto-600 text-white'
                      : 'text-gray-600 dark:text-dark-300 hover:text-gray-900 dark:hover:text-white'
                  }`}
                >
                  {getStateFilterIcon(state)}
                  {stateFilterLabels[state]}
                </button>
              ))}
            </div>

            {/* Dropdown hyperviseur */}
            <div className="flex items-center gap-2">
              <Server size={18} className="text-gray-400 dark:text-dark-400 hidden sm:block" />
              <select
                value={hypervisorFilter}
                onChange={(e) => setHypervisorFilter(e.target.value)}
                className="flex-1 sm:flex-none bg-white dark:bg-dark-700 border border-light-300 dark:border-dark-600 rounded-lg px-3 py-2 text-gray-900 dark:text-dark-100 text-sm focus:outline-none focus:ring-2 focus:ring-oto-500"
              >
                <option value="all">Tous les hyperviseurs</option>
                {hypervisors.map((h) => (
                  <option key={h.id} value={h.id}>
                    {h.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-2">
            {hypervisorFilter !== 'all' && (
              <Button
                variant="primary"
                leftIcon={<CloudDownload size={18} />}
                onClick={() => syncMutation.mutate(hypervisorFilter)}
                isLoading={syncMutation.isPending}
                disabled={syncMutation.isPending || isAutoSyncing}
                title="Synchronise les VMs entre Hyper-V et la base de données"
              >
                Synchroniser avec Hyper-V
              </Button>
            )}
            {hypervisorFilter === 'all' && hypervisors.length > 0 && (
              <Button
                variant="primary"
                leftIcon={<CloudDownload size={18} />}
                onClick={() => {
                  hypervisors.forEach((h) => syncMutation.mutate(h.id));
                }}
                isLoading={syncMutation.isPending}
                disabled={syncMutation.isPending || isAutoSyncing}
                title="Synchronise les VMs de tous les hyperviseurs"
              >
                Synchroniser tout
              </Button>
            )}
            <Button
              variant="secondary"
              leftIcon={<RefreshCw size={18} />}
              onClick={() => refetch()}
              isLoading={vmsLoading}
            >
              Actualiser
            </Button>
          </div>
        </div>

        {/* Compteur de resultats (quand un filtre est actif) */}
        {hasActiveFilter && (
          <div className="mb-4 text-sm text-gray-500 dark:text-dark-400">
            <span className="font-medium text-gray-700 dark:text-dark-200">{filteredVms.length}</span>
            {' '}VM{filteredVms.length !== 1 ? 's' : ''} trouvée{filteredVms.length !== 1 ? 's' : ''}
            {stateFilter !== 'all' && (
              <span> avec l'état <span className="font-medium text-gray-700 dark:text-dark-200">{stateFilterLabels[stateFilter]}</span></span>
            )}
            {hypervisorFilter !== 'all' && (
              <span> sur <span className="font-medium text-gray-700 dark:text-dark-200">{hypervisors.find(h => h.id === hypervisorFilter)?.name || hypervisorFilter}</span></span>
            )}
            {searchFilter && (
              <span> correspondant à "<span className="font-medium text-gray-700 dark:text-dark-200">{searchFilter}</span>"</span>
            )}
            <button
              onClick={resetAllFilters}
              className="ml-2 text-oto-500 hover:text-oto-600 dark:text-primary-400 dark:hover:text-primary-300 underline"
            >
              Réinitialiser les filtres
            </button>
          </div>
        )}

        {/* Data table */}
        {filteredVms.length === 0 && !vmsLoading ? (
          <div className="card">
            <EmptyState
              icon={Monitor}
              title={hasActiveFilter ? 'Aucune VM ne correspond aux filtres' : 'Aucune machine virtuelle'}
              description={
                hasActiveFilter
                  ? 'Essayez de modifier vos filtres ou de réinitialiser la recherche.'
                  : 'Les VMs de vos hyperviseurs apparaîtront ici. Créez un déploiement pour commencer.'
              }
            />
            {hasActiveFilter && (
              <div className="flex justify-center pb-6">
                <Button variant="secondary" onClick={resetAllFilters}>
                  Réinitialiser les filtres
                </Button>
              </div>
            )}
          </div>
        ) : (
          <DataTable
            data={filteredVms}
            columns={columns}
            keyExtractor={(vm) => vm.id}
            isLoading={vmsLoading}
            searchable
            searchPlaceholder="Rechercher une VM..."
            searchKeys={['name', 'ip_address', 'os_type']}
            searchValue={searchFilter}
            onSearchChange={setSearchFilter}
            actions={renderActions}
            onRowClick={handleOpenDetails}
            emptyMessage="Aucune VM trouvée"
            emptyIcon={<Monitor size={40} className="text-gray-400 dark:text-dark-500" />}
            selectable
            selectedKeys={selectedVmIds}
            onSelectionChange={setSelectedVmIds}
            bulkActions={bulkActionsBar}
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

        {/* Bulk action confirmation modal */}
        {bulkModalConfig && (
          <ConfirmModal
            isOpen={bulkActionModal.type !== null}
            onClose={() => setBulkActionModal({ type: null })}
            onConfirm={handleBulkConfirm}
            title={bulkModalConfig.title}
            message={bulkModalConfig.message}
            confirmText={bulkModalConfig.confirmText}
            variant={bulkModalConfig.variant}
            isLoading={bulkActionLoading}
          />
        )}

        {/* Screenshot Modal */}
        <Modal
          isOpen={screenshotModal.isOpen}
          onClose={() => setScreenshotModal({ isOpen: false, vm: null })}
          title={`Aperçu - ${screenshotModal.vm?.name || 'VM'}`}
          size="xl"
        >
          <div className="space-y-4">
            {/* Toolbar */}
            <div className="flex items-center justify-between">
              <p className="text-sm text-gray-500 dark:text-dark-400">
                Capture d'écran en temps reel de la VM
              </p>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleRefreshScreenshot}
                  disabled={screenshotLoading}
                >
                  <RefreshCw size={16} className={screenshotLoading ? 'animate-spin' : ''} />
                  Actualiser
                </Button>
                {screenshotData && (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => window.open(screenshotData, '_blank')}
                  >
                    <Maximize2 size={16} />
                    Plein écran
                  </Button>
                )}
              </div>
            </div>

            {/* Screenshot display */}
            <div className="bg-gray-900 dark:bg-black rounded-lg overflow-hidden min-h-[400px] flex items-center justify-center">
              {screenshotLoading ? (
                <div className="flex flex-col items-center gap-3 text-gray-400 dark:text-dark-400">
                  <RefreshCw size={32} className="animate-spin" />
                  <span>Capture en cours...</span>
                </div>
              ) : screenshotError ? (
                <div className="flex flex-col items-center gap-3 text-red-400 p-8 text-center">
                  <XCircle size={32} />
                  <span>{screenshotError}</span>
                  <Button size="sm" variant="secondary" onClick={handleRefreshScreenshot}>
                    Réessayer
                  </Button>
                </div>
              ) : screenshotData ? (
                <img
                  src={screenshotData}
                  alt={`Screenshot de ${screenshotModal.vm?.name}`}
                  className="max-w-full max-h-[600px] object-contain"
                />
              ) : (
                <span className="text-gray-400 dark:text-dark-400">Aucune image</span>
              )}
            </div>

            {/* Info */}
            <p className="text-xs text-gray-400 dark:text-dark-500 text-center">
              Cliquez sur "Actualiser" pour mettre à jour l'image
            </p>
          </div>
        </Modal>

        {/* VM Details Modal */}
        <Modal
          isOpen={detailsModal.isOpen}
          onClose={() => setDetailsModal({ isOpen: false, vm: null })}
          title={`Détails de ${detailsModal.vm?.name || 'VM'}`}
          size="xl"
        >
          {detailsLoading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw size={32} className="animate-spin text-oto-500" />
              <span className="ml-3 text-gray-600 dark:text-dark-300">Chargement des détails...</span>
            </div>
          ) : vmDetails ? (
            <div className="space-y-6 max-h-[70vh] overflow-y-auto">
              {/* Etat et ressources en temps reel */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-light-100 dark:bg-dark-700 rounded-lg p-4">
                  <div className="flex items-center gap-2 text-gray-500 dark:text-dark-400 mb-1">
                    <Activity size={16} />
                    <span className="text-sm">État</span>
                  </div>
                  <StatusBadge status={vmDetails.general.state.toLowerCase() as VirtualMachine['state']} />
                </div>
                <div className="bg-light-100 dark:bg-dark-700 rounded-lg p-4">
                  <div className="flex items-center gap-2 text-gray-500 dark:text-dark-400 mb-1">
                    <Cpu size={16} />
                    <span className="text-sm">CPU</span>
                  </div>
                  <p className="text-xl font-bold text-gray-900 dark:text-white">{vmDetails.resources.cpu_usage_percent}%</p>
                  <p className="text-xs text-gray-500 dark:text-dark-400">{vmDetails.configuration.cpu_count} vCPU</p>
                </div>
                <div className="bg-light-100 dark:bg-dark-700 rounded-lg p-4">
                  <div className="flex items-center gap-2 text-gray-500 dark:text-dark-400 mb-1">
                    <MemoryStick size={16} />
                    <span className="text-sm">RAM</span>
                  </div>
                  <p className="text-xl font-bold text-gray-900 dark:text-white">{vmDetails.resources.ram_assigned_gb} Go</p>
                  <p className="text-xs text-gray-500 dark:text-dark-400">
                    {vmDetails.configuration.dynamic_memory
                      ? `Dynamique (${vmDetails.configuration.ram_minimum_gb}-${vmDetails.configuration.ram_maximum_gb} Go)`
                      : 'Statique'
                    }
                  </p>
                </div>
                <div className="bg-light-100 dark:bg-dark-700 rounded-lg p-4">
                  <div className="flex items-center gap-2 text-gray-500 dark:text-dark-400 mb-1">
                    <Clock size={16} />
                    <span className="text-sm">Uptime</span>
                  </div>
                  <p className="text-lg font-medium text-gray-900 dark:text-white">{vmDetails.general.uptime || '-'}</p>
                </div>
              </div>

              {/* Configuration */}
              <div>
                <h4 className="text-sm font-medium text-gray-600 dark:text-dark-300 mb-3 flex items-center gap-2">
                  <Server size={16} />
                  Configuration
                </h4>
                <div className="bg-light-100 dark:bg-dark-700 rounded-lg p-4 grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <span className="text-gray-500 dark:text-dark-400">Generation:</span>
                    <span className="ml-2 text-gray-900 dark:text-white">Gen {vmDetails.general.generation}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 dark:text-dark-400">Version:</span>
                    <span className="ml-2 text-gray-900 dark:text-white">{vmDetails.general.version}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 dark:text-dark-400">Secure Boot:</span>
                    <span className="ml-2 text-gray-900 dark:text-white">{vmDetails.configuration.secure_boot ? 'Activé' : 'Désactivé'}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 dark:text-dark-400">TPM:</span>
                    <span className="ml-2 text-gray-900 dark:text-white">{vmDetails.configuration.tpm_enabled ? 'Activé' : 'Non'}</span>
                  </div>
                  <div className="col-span-2">
                    <span className="text-gray-500 dark:text-dark-400">Chemin:</span>
                    <span className="ml-2 text-gray-900 dark:text-white font-mono text-xs">{vmDetails.general.path}</span>
                  </div>
                </div>
              </div>

              {/* Disques */}
              <div>
                <h4 className="text-sm font-medium text-gray-600 dark:text-dark-300 mb-3 flex items-center gap-2">
                  <HardDrive size={16} />
                  Disques ({vmDetails.disks.length})
                </h4>
                <div className="space-y-2">
                  {vmDetails.disks.map((disk, idx) => (
                    <div key={idx} className="bg-light-100 dark:bg-dark-700 rounded-lg p-3">
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="text-gray-900 dark:text-white font-medium">{disk.type || 'Disque'}</span>
                          {disk.size_gb && (
                            <span className="ml-2 text-gray-500 dark:text-dark-400">
                              {disk.size_used_gb ? `${disk.size_used_gb}/${disk.size_gb} Go` : `${disk.size_gb} Go`}
                            </span>
                          )}
                        </div>
                        <span className="text-xs text-gray-500 dark:text-dark-400">{disk.format}</span>
                      </div>
                      <p className="text-xs text-gray-400 dark:text-dark-500 font-mono mt-1 truncate">{disk.path}</p>
                      {disk.size_gb && disk.size_used_gb && (
                        <div className="mt-2 h-1.5 bg-light-200 dark:bg-dark-600 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-oto-500 rounded-full"
                            style={{ width: `${(disk.size_used_gb / disk.size_gb) * 100}%` }}
                          />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Reseau */}
              <div>
                <h4 className="text-sm font-medium text-gray-600 dark:text-dark-300 mb-3 flex items-center gap-2">
                  <Network size={16} />
                  Adaptateurs réseau ({vmDetails.network_adapters.length})
                </h4>
                <div className="space-y-2">
                  {vmDetails.network_adapters.map((nic, idx) => (
                    <div key={idx} className="bg-light-100 dark:bg-dark-700 rounded-lg p-3">
                      <div className="flex items-center justify-between">
                        <span className="text-gray-900 dark:text-white font-medium">{nic.name}</span>
                        <StatusBadge status={nic.status.toLowerCase() === 'ok' ? 'running' : 'stopped'} />
                      </div>
                      <div className="grid grid-cols-2 gap-2 mt-2 text-sm">
                        <div>
                          <span className="text-gray-500 dark:text-dark-400">Switch:</span>
                          <span className="ml-2 text-gray-900 dark:text-white">{nic.switch_name || '-'}</span>
                        </div>
                        <div>
                          <span className="text-gray-500 dark:text-dark-400">VLAN:</span>
                          <span className="ml-2 text-gray-900 dark:text-white">{nic.vlan_id || 'Aucun'}</span>
                        </div>
                        <div>
                          <span className="text-gray-500 dark:text-dark-400">MAC:</span>
                          <span className="ml-2 text-gray-900 dark:text-white font-mono text-xs">{nic.mac_address || '-'}</span>
                        </div>
                        <div>
                          <span className="text-gray-500 dark:text-dark-400">IP:</span>
                          <span className="ml-2 text-gray-900 dark:text-white font-mono">
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
                <h4 className="text-sm font-medium text-gray-600 dark:text-dark-300 mb-3 flex items-center gap-2">
                  <CheckCircle size={16} />
                  Services d'intégration
                </h4>
                <div className="bg-light-100 dark:bg-dark-700 rounded-lg p-3">
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    {vmDetails.integration_services.map((svc, idx) => (
                      <div key={idx} className="flex items-center gap-2 text-sm">
                        {svc.enabled && svc.status === 'Ok' ? (
                          <CheckCircle size={14} className="text-green-500" />
                        ) : svc.enabled ? (
                          <XCircle size={14} className="text-yellow-500" />
                        ) : (
                          <XCircle size={14} className="text-gray-400 dark:text-dark-500" />
                        )}
                        <span className={svc.enabled ? 'text-gray-900 dark:text-white' : 'text-gray-500 dark:text-dark-400'}>{svc.name}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Checkpoints */}
              {vmDetails.checkpoints.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-gray-600 dark:text-dark-300 mb-3">
                    Checkpoints ({vmDetails.checkpoints.length})
                  </h4>
                  <div className="bg-light-100 dark:bg-dark-700 rounded-lg p-3 space-y-2">
                    {vmDetails.checkpoints.map((cp) => (
                      <div key={cp.id} className="flex items-center justify-between text-sm">
                        <span className="text-gray-900 dark:text-white">{cp.name}</span>
                        <span className="text-gray-500 dark:text-dark-400">{new Date(cp.creation_time).toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-500 dark:text-dark-400">
              Impossible de charger les détails
            </div>
          )}
        </Modal>
        {/* Software Inventory Modal */}
        <Modal
          isOpen={inventoryModal.isOpen}
          onClose={() => setInventoryModal({ isOpen: false, vm: null })}
          title={`Inventaire logiciel - ${inventoryModal.vm?.name || 'VM'}`}
          size="xl"
        >
          {inventoryLoading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw size={32} className="animate-spin text-oto-500" />
              <span className="ml-3 text-gray-600 dark:text-dark-300">Analyse des logiciels installés...</span>
            </div>
          ) : inventoryError ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <XCircle size={40} className="text-red-400" />
              <p className="text-red-400 font-medium">Erreur</p>
              <p className="text-sm text-gray-500 dark:text-dark-400 max-w-md">{inventoryError}</p>
              <Button size="sm" variant="secondary" onClick={() => inventoryModal.vm && handleOpenInventory(inventoryModal.vm)}>
                Réessayer
              </Button>
            </div>
          ) : inventoryData ? (
            <div className="space-y-4 max-h-[70vh] overflow-y-auto">
              {/* System Info */}
              {inventoryData.system_info && (
                <div className="bg-light-100 dark:bg-dark-700 rounded-lg p-4 grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
                  <div>
                    <span className="text-gray-500 dark:text-dark-400">Hostname</span>
                    <p className="font-medium text-gray-900 dark:text-white">{inventoryData.system_info.hostname || '-'}</p>
                  </div>
                  {inventoryData.os_type === 'windows' ? (
                    <>
                      <div>
                        <span className="text-gray-500 dark:text-dark-400">OS</span>
                        <p className="font-medium text-gray-900 dark:text-white">{inventoryData.system_info.os_name || '-'}</p>
                      </div>
                      <div>
                        <span className="text-gray-500 dark:text-dark-400">Build</span>
                        <p className="font-medium text-gray-900 dark:text-white">{inventoryData.system_info.os_version || '-'} ({inventoryData.system_info.os_build || '?'})</p>
                      </div>
                      <div>
                        <span className="text-gray-500 dark:text-dark-400">Uptime</span>
                        <p className="font-medium text-gray-900 dark:text-white">{inventoryData.system_info.uptime_hours ? `${inventoryData.system_info.uptime_hours}h` : '-'}</p>
                      </div>
                    </>
                  ) : (
                    <>
                      <div>
                        <span className="text-gray-500 dark:text-dark-400">OS</span>
                        <p className="font-medium text-gray-900 dark:text-white">{inventoryData.system_info.os_info || '-'}</p>
                      </div>
                      <div>
                        <span className="text-gray-500 dark:text-dark-400">Kernel</span>
                        <p className="font-medium text-gray-900 dark:text-white">{inventoryData.system_info.kernel || '-'}</p>
                      </div>
                      <div>
                        <span className="text-gray-500 dark:text-dark-400">Uptime</span>
                        <p className="font-medium text-gray-900 dark:text-white">{inventoryData.system_info.uptime || '-'}</p>
                      </div>
                    </>
                  )}
                  <div>
                    <span className="text-gray-500 dark:text-dark-400">Total logiciels</span>
                    <p className="font-medium text-gray-900 dark:text-white">{inventoryData.total_packages}</p>
                  </div>
                  <div>
                    <span className="text-gray-500 dark:text-dark-400">Scan</span>
                    <p className="font-medium text-gray-900 dark:text-white">{new Date(inventoryData.timestamp).toLocaleString()}</p>
                  </div>
                </div>
              )}

              {/* Search */}
              <div className="relative">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-dark-400" />
                <input
                  type="text"
                  value={inventorySearch}
                  onChange={(e) => setInventorySearch(e.target.value)}
                  placeholder="Filtrer par nom..."
                  className="w-full pl-9 pr-4 py-2 bg-white dark:bg-dark-700 border border-light-300 dark:border-dark-600 rounded-lg text-sm text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-400 focus:outline-none focus:ring-2 focus:ring-oto-500"
                />
              </div>

              {/* Tabs */}
              <div className="flex flex-wrap items-center bg-white dark:bg-dark-800 rounded-lg p-1 border border-light-200 dark:border-transparent gap-1">
                {inventoryData.os_type === 'windows' && (
                  <>
                    {([
                      ['choco', 'Chocolatey', inventoryData.chocolatey_packages?.length || 0],
                      ['programs', 'Programmes', inventoryData.installed_programs?.length || 0],
                      ['features', 'Features', inventoryData.windows_features?.length || 0],
                      ['services', 'Services', inventoryData.running_services?.length || 0],
                      ['updates', 'Updates', inventoryData.recent_updates?.length || 0],
                    ] as const).map(([key, label, count]) => (
                      <button
                        key={key}
                        onClick={() => setInventoryTab(key)}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                          inventoryTab === key
                            ? 'bg-oto-600 text-white'
                            : 'text-gray-600 dark:text-dark-300 hover:text-gray-900 dark:hover:text-white'
                        }`}
                      >
                        {label}
                        <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                          inventoryTab === key ? 'bg-white/20' : 'bg-light-200 dark:bg-dark-600'
                        }`}>{count}</span>
                      </button>
                    ))}
                  </>
                )}
                {inventoryData.os_type === 'linux' && (
                  <>
                    {([
                      ['linux', 'Packages', inventoryData.packages?.length || 0],
                      ['snap', 'Snap', inventoryData.snap_packages?.length || 0],
                      ['services', 'Services', inventoryData.running_services?.length || 0],
                    ] as const).map(([key, label, count]) => (
                      count > 0 || key === 'linux' ? (
                        <button
                          key={key}
                          onClick={() => setInventoryTab(key)}
                          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                            inventoryTab === key
                              ? 'bg-oto-600 text-white'
                              : 'text-gray-600 dark:text-dark-300 hover:text-gray-900 dark:hover:text-white'
                          }`}
                        >
                          {label}
                          <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                            inventoryTab === key ? 'bg-white/20' : 'bg-light-200 dark:bg-dark-600'
                          }`}>{count}</span>
                        </button>
                      ) : null
                    ))}
                  </>
                )}
              </div>

              {/* Table renderer helper */}
              {(() => {
                const s = inventorySearch.toLowerCase();
                const tableClass = "border border-light-200 dark:border-dark-600 rounded-lg overflow-hidden";
                const thClass = "text-left px-4 py-2 font-medium text-gray-600 dark:text-dark-300";
                const tdName = "px-4 py-2 text-gray-900 dark:text-white font-medium";
                const tdMono = "px-4 py-2 text-gray-600 dark:text-dark-300 font-mono text-xs";
                const tdSub = "px-4 py-2 text-gray-500 dark:text-dark-400";
                const emptyRow = (cols: number, msg: string) => (
                  <tr><td colSpan={cols} className="px-4 py-8 text-center text-gray-500 dark:text-dark-400">{msg}</td></tr>
                );

                if (inventoryTab === 'choco') {
                  const items = (inventoryData.chocolatey_packages || []).filter(p => !s || p.Name?.toLowerCase().includes(s));
                  return (
                    <div className={tableClass}><table className="w-full text-sm">
                      <thead><tr className="bg-light-100 dark:bg-dark-700"><th className={thClass}>Nom</th><th className={thClass}>Version</th><th className={thClass}>Source</th></tr></thead>
                      <tbody className="divide-y divide-light-200 dark:divide-dark-600">
                        {items.length ? items.map((p, i) => (
                          <tr key={i} className="hover:bg-light-50 dark:hover:bg-dark-700/50">
                            <td className={tdName}>{p.Name}</td><td className={tdMono}>{p.Version}</td><td className={tdSub}>{p.Source}</td>
                          </tr>
                        )) : emptyRow(3, s ? 'Aucun résultat' : 'Aucun package Chocolatey')}
                      </tbody>
                    </table></div>
                  );
                }
                if (inventoryTab === 'programs') {
                  const items = (inventoryData.installed_programs || []).filter(p => !s || p.DisplayName?.toLowerCase().includes(s));
                  return (
                    <div className={tableClass}><table className="w-full text-sm">
                      <thead><tr className="bg-light-100 dark:bg-dark-700"><th className={thClass}>Nom</th><th className={thClass}>Version</th><th className={thClass}>Éditeur</th></tr></thead>
                      <tbody className="divide-y divide-light-200 dark:divide-dark-600">
                        {items.length ? items.map((p, i) => (
                          <tr key={i} className="hover:bg-light-50 dark:hover:bg-dark-700/50">
                            <td className={tdName}>{p.DisplayName}</td><td className={tdMono}>{p.DisplayVersion || '-'}</td><td className={tdSub}>{p.Publisher || '-'}</td>
                          </tr>
                        )) : emptyRow(3, s ? 'Aucun résultat' : 'Aucun programme')}
                      </tbody>
                    </table></div>
                  );
                }
                if (inventoryTab === 'features') {
                  const items = (inventoryData.windows_features || []).filter(f => !s || (f.FeatureName || f.Name || f.DisplayName || '').toLowerCase().includes(s));
                  return (
                    <div className={tableClass}><table className="w-full text-sm">
                      <thead><tr className="bg-light-100 dark:bg-dark-700"><th className={thClass}>Feature</th><th className={thClass}>État</th></tr></thead>
                      <tbody className="divide-y divide-light-200 dark:divide-dark-600">
                        {items.length ? items.map((f, i) => (
                          <tr key={i} className="hover:bg-light-50 dark:hover:bg-dark-700/50">
                            <td className={tdName}>{f.FeatureName || f.Name || f.DisplayName}</td>
                            <td className={tdSub}><span className="inline-flex px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">{f.State || f.InstallState || 'Enabled'}</span></td>
                          </tr>
                        )) : emptyRow(2, s ? 'Aucun résultat' : 'Aucune feature activée')}
                      </tbody>
                    </table></div>
                  );
                }
                if (inventoryTab === 'services') {
                  const items = (inventoryData.running_services || []).filter(sv => !s || (sv.DisplayName || sv.Name || sv.name || '').toLowerCase().includes(s));
                  return (
                    <div className={tableClass}><table className="w-full text-sm">
                      <thead><tr className="bg-light-100 dark:bg-dark-700"><th className={thClass}>Service</th><th className={thClass}>Nom</th><th className={thClass}>État</th></tr></thead>
                      <tbody className="divide-y divide-light-200 dark:divide-dark-600">
                        {items.length ? items.map((sv, i) => (
                          <tr key={i} className="hover:bg-light-50 dark:hover:bg-dark-700/50">
                            <td className={tdMono}>{sv.Name || sv.name}</td>
                            <td className={tdName}>{sv.DisplayName || '-'}</td>
                            <td className={tdSub}><span className="inline-flex px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">{sv.Status || sv.status || 'Running'}</span></td>
                          </tr>
                        )) : emptyRow(3, s ? 'Aucun résultat' : 'Aucun service')}
                      </tbody>
                    </table></div>
                  );
                }
                if (inventoryTab === 'updates') {
                  const items = (inventoryData.recent_updates || []).filter(u => !s || u.HotFixID?.toLowerCase().includes(s) || u.Description?.toLowerCase().includes(s));
                  return (
                    <div className={tableClass}><table className="w-full text-sm">
                      <thead><tr className="bg-light-100 dark:bg-dark-700"><th className={thClass}>KB</th><th className={thClass}>Description</th><th className={thClass}>Installé le</th></tr></thead>
                      <tbody className="divide-y divide-light-200 dark:divide-dark-600">
                        {items.length ? items.map((u, i) => (
                          <tr key={i} className="hover:bg-light-50 dark:hover:bg-dark-700/50">
                            <td className={tdName}>{u.HotFixID}</td>
                            <td className={tdSub}>{u.Description || '-'}</td>
                            <td className={tdMono}>{u.InstalledOn ? new Date(u.InstalledOn).toLocaleDateString() : '-'}</td>
                          </tr>
                        )) : emptyRow(3, s ? 'Aucun résultat' : 'Aucune mise à jour')}
                      </tbody>
                    </table></div>
                  );
                }
                if (inventoryTab === 'linux') {
                  const items = (inventoryData.packages || []).filter(p => !s || p.name?.toLowerCase().includes(s));
                  return (
                    <div className={tableClass}><table className="w-full text-sm">
                      <thead><tr className="bg-light-100 dark:bg-dark-700"><th className={thClass}>Package</th><th className={thClass}>Version</th></tr></thead>
                      <tbody className="divide-y divide-light-200 dark:divide-dark-600">
                        {items.length ? items.map((p, i) => (
                          <tr key={i} className="hover:bg-light-50 dark:hover:bg-dark-700/50">
                            <td className={tdName}>{p.name}</td><td className={tdMono}>{p.version}</td>
                          </tr>
                        )) : emptyRow(2, s ? 'Aucun résultat' : 'Aucun package')}
                      </tbody>
                    </table></div>
                  );
                }
                if (inventoryTab === 'snap') {
                  const items = (inventoryData.snap_packages || []).filter(p => !s || p.name?.toLowerCase().includes(s));
                  return (
                    <div className={tableClass}><table className="w-full text-sm">
                      <thead><tr className="bg-light-100 dark:bg-dark-700"><th className={thClass}>Package</th><th className={thClass}>Version</th><th className={thClass}>Source</th></tr></thead>
                      <tbody className="divide-y divide-light-200 dark:divide-dark-600">
                        {items.length ? items.map((p, i) => (
                          <tr key={i} className="hover:bg-light-50 dark:hover:bg-dark-700/50">
                            <td className={tdName}>{p.name}</td><td className={tdMono}>{p.version}</td><td className={tdSub}>{p.source || 'snap'}</td>
                          </tr>
                        )) : emptyRow(3, s ? 'Aucun résultat' : 'Aucun snap')}
                      </tbody>
                    </table></div>
                  );
                }
                return null;
              })()}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-500 dark:text-dark-400">
              Impossible de charger l'inventaire logiciel
            </div>
          )}
        </Modal>

        {/* VNC Install Modal */}
        <VNCInstallModal
          isOpen={vncInstallModal.isOpen}
          onClose={() => setVncInstallModal({ isOpen: false, vm: null })}
          vmId={vncInstallModal.vm?.id || ''}
          vmName={vncInstallModal.vm?.name || ''}
          osFamily={vncInstallModal.vm?.os_type?.toLowerCase().includes('windows') ? 'windows' : 'linux'}
          onInstall={handleVncInstall}
        />
      </div>
    </div>
  );
}
