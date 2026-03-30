import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Rocket,
  Plus,
  RefreshCw,
  X,
  RotateCw,
  ChevronRight,
  Clock,
  CheckCircle,
  XCircle,
  Loader2,
  FileText,
  Trash2,
  Wifi,
  WifiOff,
  Search,
  Copy,
  Download,
  Server,
  MonitorCog,
  Timer,
  Play,
} from 'lucide-react';
import { Header } from '../components/layout';
import {
  Button,
  Modal,
  ConfirmModal,
  StatusBadge,
  EmptyState,
  useToast,
} from '../components/ui';
import { deploymentsApi, hypervisorsApi, templatesApi } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { useDeploymentEvents, type DeploymentProgressPayload } from '../hooks/useWebSocket';
import type { Deployment, DeploymentStatus, DeploymentLog, Hypervisor, OSTemplate } from '../types';

// Etapes affichees dans l'interface
const displaySteps = [
  'pending',
  'creating_vm',
  'installing_os',
  'post_install',
  'installing_software',
  'completed',
] as const;

type DisplayStep = typeof displaySteps[number];

// Mapping current_step backend -> etape affichee
const stepToDisplayStep: Record<string, DisplayStep> = {
  'validating': 'creating_vm',
  'creating_vm': 'creating_vm',
  'mounting_iso': 'installing_os',
  'deploying_dism': 'installing_os',
  'configuring_network': 'installing_os',
  'starting_installation': 'installing_os',
  'waiting_vm_ready': 'installing_os',
  'post_configuration': 'post_install',
  'installing_software': 'installing_software',
  'finalizing': 'installing_software',
  'completed': 'completed',
  'failed': 'completed',
};

// Fonction pour obtenir l'etape affichee a partir du deploiement
const getDisplayStep = (deployment: Deployment): DisplayStep => {
  // Statuts terminaux
  if (deployment.status === 'completed') return 'completed';
  if (deployment.status === 'failed' || deployment.status === 'cancelled' || deployment.status === 'rejected') return 'completed';
  if (deployment.status === 'pending' || deployment.status === 'pending_approval') return 'pending';

  // Utiliser current_step pour les deploiements en cours
  if (deployment.current_step) {
    return stepToDisplayStep[deployment.current_step] || 'creating_vm';
  }

  return 'pending';
};

// Seuils de progression pour considerer qu'une etape visuelle est ATTEINTE
// Alignes sur les valeurs reelles du backend (11 etapes granulaires)
// pending=0, creating_vm=5-15, installing_os=25-65, post_install=75, installing_software=85-95
const displayStepProgress: Record<DisplayStep, number> = {
  'pending': 0,
  'creating_vm': 5,
  'installing_os': 25,
  'post_install': 75,
  'installing_software': 85,
  'completed': 100,
};

// Mapping current_step backend -> progression (fallback si deployment.progress n'est pas disponible)
const stepProgressFallback: Record<string, number> = {
  'validating': 5,
  'creating_vm': 15,
  'mounting_iso': 25,
  'deploying_dism': 35,
  'configuring_network': 45,
  'starting_installation': 55,
  'waiting_vm_ready': 65,
  'post_configuration': 75,
  'installing_software': 85,
  'finalizing': 95,
  'completed': 100,
  'failed': 0,
};

// Fonction pour obtenir la progression : utilise deployment.progress du backend comme source de verite
const getSynchronizedProgress = (deployment: Deployment): number => {
  // Statuts terminaux
  if (deployment.status === 'completed') return 100;
  if (deployment.status === 'failed' || deployment.status === 'cancelled' || deployment.status === 'rejected') return 0;
  if (deployment.status === 'pending' || deployment.status === 'pending_approval') return 0;

  // Utiliser deployment.progress du backend (calcule sur 11 etapes)
  if (deployment.progress != null && deployment.progress > 0) {
    return deployment.progress;
  }

  // Fallback : utiliser le mapping d'etapes si progress n'est pas encore disponible
  if (deployment.current_step) {
    return stepProgressFallback[deployment.current_step] || 10;
  }

  return 10;
};

// Estimation du temps restant basee sur le pourcentage de progression
const estimateRemainingTime = (deployment: Deployment): string | null => {
  const progress = getSynchronizedProgress(deployment);
  if (progress <= 0 || progress >= 100) return null;
  if (!['in_progress', 'creating_vm', 'installing_os', 'post_install', 'installing_software'].includes(deployment.status)) return null;

  const startDate = new Date(deployment.created_at);
  const now = new Date();
  const elapsedMs = now.getTime() - startDate.getTime();

  if (elapsedMs <= 0) return null;

  // Estimation lineaire : temps total = elapsed / (progress/100)
  const estimatedTotalMs = elapsedMs / (progress / 100);
  const remainingMs = estimatedTotalMs - elapsedMs;
  const remainingSec = Math.max(0, Math.floor(remainingMs / 1000));

  if (remainingSec < 60) return `~${remainingSec}s restantes`;
  if (remainingSec < 3600) return `~${Math.floor(remainingSec / 60)}m restantes`;
  return `~${Math.floor(remainingSec / 3600)}h ${Math.floor((remainingSec % 3600) / 60)}m restantes`;
};

type FilterStatus = 'all' | 'active' | 'completed' | 'failed' | 'cancelled';

const VALID_FILTERS: FilterStatus[] = ['all', 'active', 'completed', 'failed', 'cancelled'];

export function Deployments() {
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [searchParams, setSearchParams] = useSearchParams();

  // Lire le filtre depuis l'URL
  const urlStatus = searchParams.get('status') as FilterStatus | null;
  const urlSearch = searchParams.get('search') || '';
  const filterStatus: FilterStatus = urlStatus && VALID_FILTERS.includes(urlStatus) ? urlStatus : 'all';

  const [searchQuery, setSearchQuery] = useState(urlSearch);

  // Synchroniser le champ de recherche avec l'URL
  useEffect(() => {
    setSearchQuery(searchParams.get('search') || '');
  }, [searchParams]);

  const setFilterStatus = (status: FilterStatus) => {
    const params = new URLSearchParams(searchParams);
    if (status === 'all') {
      params.delete('status');
    } else {
      params.set('status', status);
    }
    setSearchParams(params, { replace: true });
  };

  const setSearchParam = (value: string) => {
    setSearchQuery(value);
    const params = new URLSearchParams(searchParams);
    if (value.trim()) {
      params.set('search', value.trim());
    } else {
      params.delete('search');
    }
    setSearchParams(params, { replace: true });
  };

  const [selectedDeployment, setSelectedDeployment] = useState<Deployment | null>(null);
  const [isLogsModalOpen, setIsLogsModalOpen] = useState(false);
  const [isCancelModalOpen, setIsCancelModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [deploymentLogs, setDeploymentLogs] = useState<DeploymentLog[]>([]);
  const [isLoadingLogs, setIsLoadingLogs] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [hoveredDeploymentId, setHoveredDeploymentId] = useState<string | null>(null);

  // Track previous statuses for animations
  const previousStatuses = useRef<Record<string, string>>({});

  // WebSocket pour les mises a jour temps reel
  const handleDeploymentProgress = useCallback((payload: DeploymentProgressPayload) => {
    // Mettre a jour directement les donnees du deploiement sans refetch
    queryClient.setQueryData<Deployment[]>(['deployments'], (oldData) => {
      if (!oldData) return oldData;

      return oldData.map((deployment) => {
        if (deployment.id === payload.deployment_id) {
          // Mettre a jour le deploiement avec les nouvelles donnees
          // Accepter current_step ou step pour compatibilite
          const currentStep = payload.current_step || (payload as any).step || deployment.current_step;
          const errorMsg = payload.message || (payload as any).error || deployment.error_message;

          return {
            ...deployment,
            status: payload.status as DeploymentStatus,
            progress: payload.progress ?? deployment.progress,
            current_step: currentStep,
            error_message: errorMsg,
          };
        }
        return deployment;
      });
    });

    // Optionnellement, invalider pour s'assurer que les donnees sont a jour
    // mais avec une priorite moindre que la mise a jour directe
    queryClient.invalidateQueries({ queryKey: ['deployments'] });
  }, [queryClient]);

  const { status: wsStatus, isConnected: wsConnected, fallbackPolling: wsFallbackPolling } = useDeploymentEvents(
    undefined, // ecouter tous les deploiements
    handleDeploymentProgress
  );

  // Activer le polling de secours si le WebSocket est en erreur ou déconnecté après échec de reconnexion
  const needsPolling = wsFallbackPolling || wsStatus === 'error';

  // Fetch deployments
  // Polling rapide (5s) si le WebSocket est indisponible, sinon polling lent (30s) en backup
  const { data: deployments = [], isLoading, refetch } = useQuery({
    queryKey: ['deployments'],
    queryFn: () => deploymentsApi.list(),
    refetchInterval: needsPolling ? 5000 : 30000,
  });

  // Fetch hypervisors and templates for display names
  const { data: hypervisors = [] } = useQuery({
    queryKey: ['hypervisors'],
    queryFn: () => hypervisorsApi.list(),
    staleTime: 60000,
  });

  const { data: templates = [] } = useQuery({
    queryKey: ['templates'],
    queryFn: () => templatesApi.list(),
    staleTime: 60000,
  });

  // Build lookup maps
  const hypervisorMap = useMemo(() => {
    const map: Record<string, Hypervisor> = {};
    hypervisors.forEach((h) => { map[h.id] = h; });
    return map;
  }, [hypervisors]);

  const templateMap = useMemo(() => {
    const map: Record<string, OSTemplate> = {};
    templates.forEach((t) => { map[t.id] = t; });
    return map;
  }, [templates]);

  // Cancel mutation
  const cancelMutation = useMutation({
    mutationFn: (id: string) => deploymentsApi.cancel(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deployments'] });
      addToast({ type: 'success', title: 'Déploiement annulé' });
      setIsCancelModalOpen(false);
      setSelectedDeployment(null);
    },
    onError: () => {
      addToast({ type: 'error', title: 'Erreur lors de l\'annulation' });
    },
  });

  // Retry mutation
  const retryMutation = useMutation({
    mutationFn: (id: string) => deploymentsApi.retry(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deployments'] });
      addToast({ type: 'success', title: 'Déploiement relancé' });
    },
    onError: () => {
      addToast({ type: 'error', title: 'Erreur lors de la relance' });
    },
  });

  // Resume mutation
  const resumeMutation = useMutation({
    mutationFn: (id: string) => deploymentsApi.resume(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deployments'] });
      addToast({ type: 'success', title: 'Déploiement repris' });
    },
    onError: () => {
      addToast({ type: 'error', title: 'Erreur lors de la reprise' });
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deploymentsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deployments'] });
      addToast({ type: 'success', title: 'Déploiement supprimé' });
      setIsDeleteModalOpen(false);
      setSelectedDeployment(null);
    },
    onError: () => {
      addToast({ type: 'error', title: 'Erreur lors de la suppression' });
    },
  });

  // Effect to track status changes for animations
  useEffect(() => {
    deployments.forEach((d) => {
      const prevStatus = previousStatuses.current[d.id];
      if (prevStatus && prevStatus !== d.status) {
        // Status changed - could trigger animation or notification here
        if (d.status === 'completed') {
          addToast({ type: 'success', title: `${d.name} terminé avec succès` });
        } else if (d.status === 'failed') {
          addToast({ type: 'error', title: `${d.name} a échoué` });
        } else if (d.status === 'cancelled') {
          addToast({ type: 'warning', title: `${d.name} annulé` });
        }
      }
      previousStatuses.current[d.id] = d.status;
    });
  }, [deployments, addToast]);

  const handleViewLogs = async (deployment: Deployment) => {
    setSelectedDeployment(deployment);
    setIsLogsModalOpen(true);
    setDeploymentLogs([]);
    setLogsError(null);
    setIsLoadingLogs(true);

    try {
      const logs = await deploymentsApi.getLogs(deployment.id);
      setDeploymentLogs(logs || []);
    } catch (error) {
      console.error('Erreur lors de la récupération des logs:', error);
      setLogsError('Impossible de charger les logs');
    } finally {
      setIsLoadingLogs(false);
    }
  };

  const handleCopyLogs = () => {
    if (deploymentLogs.length === 0) return;
    const text = deploymentLogs
      .map((log) => `[${new Date(log.created_at).toLocaleTimeString('fr-FR')}] [${log.level.toUpperCase()}] [${log.step}] ${log.message}`)
      .join('\n');
    navigator.clipboard.writeText(text).then(() => {
      addToast({ type: 'success', title: 'Logs copiés dans le presse-papiers' });
    }).catch(() => {
      addToast({ type: 'error', title: 'Impossible de copier les logs' });
    });
  };

  const handleExportLogs = () => {
    if (deploymentLogs.length === 0) return;
    const text = deploymentLogs
      .map((log) => `[${new Date(log.created_at).toLocaleTimeString('fr-FR')}] [${log.level.toUpperCase()}] [${log.step}] ${log.message}`)
      .join('\n');
    const header = `Logs - ${selectedDeployment?.name || 'Déploiement'}\nExporté le ${new Date().toLocaleString('fr-FR')}\n${'='.repeat(60)}\n\n`;
    const blob = new Blob([header + text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `logs-${selectedDeployment?.name || 'deployment'}-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    addToast({ type: 'success', title: 'Logs exportés' });
  };

  const handleCancel = (deployment: Deployment) => {
    setSelectedDeployment(deployment);
    setIsCancelModalOpen(true);
  };

  const handleRetry = (deployment: Deployment) => {
    retryMutation.mutate(deployment.id);
  };

  const handleResume = (deployment: Deployment) => {
    resumeMutation.mutate(deployment.id);
  };

  const handleDelete = (deployment: Deployment) => {
    setSelectedDeployment(deployment);
    setIsDeleteModalOpen(true);
  };

  // Filter by status
  const statusFiltered = deployments.filter((d) => {
    if (filterStatus === 'all') return true;
    if (filterStatus === 'active')
      return !['completed', 'failed', 'cancelled'].includes(d.status);
    if (filterStatus === 'completed') return d.status === 'completed';
    if (filterStatus === 'failed') return d.status === 'failed';
    if (filterStatus === 'cancelled') return d.status === 'cancelled';
    return true;
  });

  // Filter by search query
  const searchLower = urlSearch.toLowerCase();
  const filteredDeployments = searchLower
    ? statusFiltered.filter((d) =>
        d.name.toLowerCase().includes(searchLower) ||
        d.vm_name.toLowerCase().includes(searchLower)
      )
    : statusFiltered;

  const sortedDeployments = [...filteredDeployments].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  const activeCount = deployments.filter(
    (d) => !['completed', 'failed', 'cancelled'].includes(d.status)
  ).length;
  const completedCount = deployments.filter((d) => d.status === 'completed').length;
  const failedCount = deployments.filter((d) => d.status === 'failed').length;
  const cancelledCount = deployments.filter((d) => d.status === 'cancelled').length;

  const isActive = (status: DeploymentStatus) =>
    !['completed', 'failed', 'cancelled', 'rejected'].includes(status);

  const getStepIcon = (step: DisplayStep, deployment: Deployment) => {
    const currentDisplayStep = getDisplayStep(deployment);
    const currentIndex = displaySteps.indexOf(currentDisplayStep);
    const stepIndex = displaySteps.indexOf(step);
    const progress = getSynchronizedProgress(deployment);
    const stepThreshold = displayStepProgress[step];

    // Seuil de l'etape SUIVANTE pour savoir si cette etape est terminee
    const nextStep = displaySteps[stepIndex + 1];
    const nextThreshold = nextStep ? displayStepProgress[nextStep] : 100;

    // Deploiement terminé avec succès : toutes les etapes sont completees
    if (deployment.status === 'completed') {
      return <CheckCircle size={16} className="text-green-500" />;
    }

    // Deploiement echoue ou annule
    if (deployment.status === 'failed' || deployment.status === 'cancelled') {
      if (stepIndex < currentIndex) {
        return <CheckCircle size={16} className="text-green-500" />;
      }
      if (stepIndex === currentIndex) {
        return <XCircle size={16} className="text-red-500" />;
      }
      return <div className="w-4 h-4 rounded-full border-2 border-dark-600" />;
    }

    // Etape completee : la progression a depasse le seuil de l'etape suivante
    if (progress >= nextThreshold && nextThreshold > 0) {
      return <CheckCircle size={16} className="text-green-500" />;
    }

    // Etape en cours : la progression est entre le seuil de cette etape et celui de la suivante
    if (progress >= stepThreshold && progress < nextThreshold && deployment.status !== 'pending') {
      return <Loader2 size={16} className="text-oto-500 animate-spin" />;
    }

    // Etape future
    return <div className="w-4 h-4 rounded-full border-2 border-dark-600" />;
  };

  const formatDate = (date: string) => {
    return new Date(date).toLocaleString('fr-FR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatDuration = (start: string, end?: string) => {
    const startDate = new Date(start);
    const endDate = end ? new Date(end) : new Date();
    const diff = Math.floor((endDate.getTime() - startDate.getTime()) / 1000);

    if (diff < 60) return `${diff}s`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ${diff % 60}s`;
    return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m`;
  };

  // Stat card click helpers
  const statCards: { key: FilterStatus; label: string; value: number; icon: React.ReactNode; bgClass: string; iconClass: string }[] = [
    {
      key: 'all',
      label: 'Total',
      value: deployments.length,
      icon: <Rocket size={24} className="text-oto-500" />,
      bgClass: 'bg-oto-100 dark:bg-primary-600/20',
      iconClass: '',
    },
    {
      key: 'active',
      label: 'En cours',
      value: activeCount,
      icon: <Loader2 size={24} className={`text-blue-500 ${activeCount > 0 ? 'animate-spin' : ''}`} />,
      bgClass: 'bg-blue-100 dark:bg-blue-500/20',
      iconClass: '',
    },
    {
      key: 'completed',
      label: 'Terminés',
      value: completedCount,
      icon: <CheckCircle size={24} className="text-green-500" />,
      bgClass: 'bg-green-100 dark:bg-green-500/20',
      iconClass: '',
    },
    {
      key: 'failed',
      label: 'Échoués',
      value: failedCount,
      icon: <XCircle size={24} className="text-red-500" />,
      bgClass: 'bg-red-100 dark:bg-red-500/20',
      iconClass: '',
    },
    {
      key: 'cancelled',
      label: 'Annulés',
      value: cancelledCount,
      icon: <X size={24} className="text-yellow-500" />,
      bgClass: 'bg-yellow-100 dark:bg-yellow-500/20',
      iconClass: '',
    },
  ];

  return (
    <div className="min-h-screen bg-light-100 dark:bg-dark-900">
      <Header title="Déploiements" />
      <div className="p-4 sm:p-6">
        {/* Stats - Clickable */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          {statCards.map((card) => (
            <button
              key={card.key}
              onClick={() => setFilterStatus(card.key)}
              className={`card p-4 flex items-center gap-4 text-left transition-all duration-200 cursor-pointer
                hover:shadow-lg hover:-translate-y-0.5 active:translate-y-0
                ${filterStatus === card.key
                  ? 'ring-2 ring-oto-500 shadow-lg shadow-oto-500/10'
                  : 'hover:shadow-oto-500/5'
                }
              `}
            >
              <div className={`w-12 h-12 ${card.bgClass} rounded-lg flex items-center justify-center shrink-0`}>
                {card.icon}
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{card.value}</p>
                <p className="text-sm text-gray-500 dark:text-dark-400">{card.label}</p>
              </div>
            </button>
          ))}
        </div>

        {/* Search + Filters and actions */}
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 mb-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 w-full lg:w-auto">
            {/* Search */}
            <div className="relative w-full sm:w-72">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-dark-400" />
              <input
                type="text"
                placeholder="Rechercher un déploiement..."
                value={searchQuery}
                onChange={(e) => setSearchParam(e.target.value)}
                className="w-full pl-9 pr-4 py-2 bg-white dark:bg-dark-800 border border-light-200 dark:border-dark-600 rounded-lg text-sm text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-400 focus:outline-none focus:ring-2 focus:ring-oto-500 focus:border-transparent transition-all duration-200"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchParam('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-dark-200"
                >
                  <X size={14} />
                </button>
              )}
            </div>

            {/* Filter tabs */}
            <div className="flex items-center bg-white dark:bg-dark-800 rounded-lg p-1 flex-wrap gap-1 border border-light-200 dark:border-transparent">
              {(VALID_FILTERS).map((status) => (
                <button
                  key={status}
                  onClick={() => setFilterStatus(status)}
                  className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                    filterStatus === status
                      ? 'bg-oto-600 text-white'
                      : 'text-gray-600 dark:text-dark-300 hover:text-gray-900 dark:hover:text-white'
                  }`}
                >
                  {status === 'all' && `Tous (${deployments.length})`}
                  {status === 'active' && `En cours (${activeCount})`}
                  {status === 'completed' && `Terminés (${completedCount})`}
                  {status === 'failed' && `Échoués (${failedCount})`}
                  {status === 'cancelled' && `Annulés (${cancelledCount})`}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Indicateur de connexion temps reel */}
            <div
              className={`flex items-center gap-1.5 px-2 py-1 rounded text-xs ${
                wsConnected
                  ? 'bg-green-100 dark:bg-green-500/20 text-green-600 dark:text-green-400'
                  : 'bg-light-200 dark:bg-dark-600 text-gray-500 dark:text-dark-400'
              }`}
              title={wsConnected ? 'Mises à jour en temps réel actives' : 'Mises à jour par polling'}
            >
              {wsConnected ? <Wifi size={14} /> : <WifiOff size={14} />}
              <span>{wsConnected ? 'Live' : 'Polling'}</span>
            </div>
            <Button
              variant="secondary"
              leftIcon={<RefreshCw size={18} />}
              onClick={() => refetch()}
              isLoading={isLoading}
            >
              Actualiser
            </Button>
            <Link to="/deployments/new">
              <Button leftIcon={<Plus size={18} />}>Nouveau déploiement</Button>
            </Link>
          </div>
        </div>

        {/* Deployments list */}
        {isLoading ? (
          <div className="space-y-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="card p-6 animate-pulse">
                <div className="h-6 bg-light-200 dark:bg-dark-700 rounded w-1/4 mb-4" />
                <div className="h-4 bg-light-200 dark:bg-dark-700 rounded w-1/2" />
              </div>
            ))}
          </div>
        ) : sortedDeployments.length === 0 ? (
          <div className="card">
            <EmptyState
              icon={Rocket}
              title={urlSearch ? 'Aucun résultat' : 'Aucun déploiement'}
              description={
                urlSearch
                  ? `Aucun déploiement ne correspond à "${urlSearch}".`
                  : 'Lancez votre premier déploiement pour créer une machine virtuelle automatiquement.'
              }
            />
          </div>
        ) : (
          <div className="space-y-4">
            {sortedDeployments.map((deployment) => {
              const hypervisorName = hypervisorMap[deployment.hypervisor_id]?.name;
              const templateName = templateMap[deployment.os_template_id]?.name;
              const remaining = estimateRemainingTime(deployment);
              const ipAddress = deployment.config?.ip_config?.ip_address;

              return (
                <div
                  key={deployment.id}
                  className={`card p-6 transition-all duration-300 border-l-4 relative ${
                    deployment.status === 'completed'
                      ? 'border-l-green-500'
                      : deployment.status === 'failed'
                      ? 'border-l-red-500'
                      : deployment.status === 'cancelled'
                      ? 'border-l-yellow-500'
                      : deployment.status === 'rejected'
                      ? 'border-l-red-400'
                      : deployment.status === 'pending_approval'
                      ? 'border-l-orange-500'
                      : isActive(deployment.status)
                      ? 'border-l-blue-500'
                      : 'border-l-dark-600'
                  }`}
                  onMouseEnter={() => setHoveredDeploymentId(deployment.id)}
                  onMouseLeave={() => setHoveredDeploymentId(null)}
                >
                  {/* Tooltip au survol */}
                  {hoveredDeploymentId === deployment.id && (
                    <div className="absolute z-20 top-0 right-0 mt-[-8px] mr-4 translate-y-[-100%] bg-dark-800 dark:bg-dark-700 text-white text-xs rounded-lg px-4 py-3 shadow-xl border border-dark-600 pointer-events-none whitespace-nowrap">
                      <div className="flex flex-col gap-1.5">
                        <div className="flex items-center gap-2">
                          <span className="text-dark-400">VM :</span>
                          <span className="font-medium">{deployment.vm_name || deployment.name}</span>
                        </div>
                        {ipAddress && (
                          <div className="flex items-center gap-2">
                            <span className="text-dark-400">IP :</span>
                            <span className="font-mono">{ipAddress}</span>
                          </div>
                        )}
                        {hypervisorName && (
                          <div className="flex items-center gap-2">
                            <span className="text-dark-400">Hyperviseur :</span>
                            <span>{hypervisorName}</span>
                          </div>
                        )}
                        <div className="flex items-center gap-2">
                          <span className="text-dark-400">Durée :</span>
                          <span>{formatDuration(deployment.created_at, isActive(deployment.status) ? undefined : deployment.updated_at)}</span>
                        </div>
                      </div>
                      {/* Arrow */}
                      <div className="absolute bottom-0 right-8 translate-y-1/2 rotate-45 w-2.5 h-2.5 bg-dark-800 dark:bg-dark-700 border-r border-b border-dark-600" />
                    </div>
                  )}

                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <div className="flex items-center gap-3">
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{deployment.name}</h3>
                        <StatusBadge status={deployment.status} />
                      </div>
                      <div className="flex items-center gap-4 mt-2 text-sm text-gray-500 dark:text-dark-400">
                        <span className="flex items-center gap-1">
                          <Clock size={14} />
                          {formatDate(deployment.created_at)}
                        </span>
                        {isActive(deployment.status) ? (
                          <span>Durée: {formatDuration(deployment.created_at)}</span>
                        ) : (deployment.status === 'completed' || deployment.status === 'failed' || deployment.status === 'cancelled') ? (
                          <span>Durée: {formatDuration(deployment.created_at, deployment.updated_at)}</span>
                        ) : null}
                      </div>
                      {/* Hyperviseur et Template labels */}
                      <div className="flex items-center gap-3 mt-2 flex-wrap">
                        {hypervisorName && (
                          <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-light-200 dark:bg-dark-700 text-gray-500 dark:text-dark-400">
                            <Server size={11} />
                            {hypervisorName}
                          </span>
                        )}
                        {templateName && (
                          <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-light-200 dark:bg-dark-700 text-gray-500 dark:text-dark-400">
                            <MonitorCog size={11} />
                            {templateName}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        leftIcon={<FileText size={16} />}
                        onClick={() => handleViewLogs(deployment)}
                      >
                        Logs
                      </Button>
                      {isAdmin && isActive(deployment.status) && (
                        <Button
                          variant="ghost"
                          size="sm"
                          leftIcon={<X size={16} />}
                          onClick={() => handleCancel(deployment)}
                          className="text-red-500 hover:text-red-400"
                        >
                          Annuler
                        </Button>
                      )}
                      {isAdmin && deployment.status === 'failed' && deployment.vm_id && (
                        <Button
                          variant="secondary"
                          size="sm"
                          leftIcon={<Play size={16} />}
                          onClick={() => handleResume(deployment)}
                          isLoading={resumeMutation.isPending}
                        >
                          Reprendre
                        </Button>
                      )}
                      {isAdmin && deployment.status === 'failed' && (
                        <Button
                          variant="secondary"
                          size="sm"
                          leftIcon={<RotateCw size={16} />}
                          onClick={() => handleRetry(deployment)}
                          isLoading={retryMutation.isPending}
                        >
                          Relancer
                        </Button>
                      )}
                      {isAdmin && ['completed', 'failed', 'cancelled'].includes(deployment.status) && (
                        <Button
                          variant="ghost"
                          size="sm"
                          leftIcon={<Trash2 size={16} />}
                          onClick={() => handleDelete(deployment)}
                          className="text-red-500 hover:text-red-400 hover:bg-red-500/10"
                        >
                          Supprimer
                        </Button>
                      )}
                    </div>
                  </div>

                  {/* Progress bar */}
                  <div className="mb-4">
                    <div className="flex items-center justify-between text-sm mb-2">
                      <span className="text-gray-500 dark:text-dark-400">Progression</span>
                      <div className="flex items-center gap-3">
                        {remaining && (
                          <span className="flex items-center gap-1 text-xs text-blue-500 dark:text-blue-400">
                            <Timer size={12} />
                            {remaining}
                          </span>
                        )}
                        <span className="text-gray-900 dark:text-white font-medium">
                          {getSynchronizedProgress(deployment)}%
                        </span>
                      </div>
                    </div>
                    <div className="h-2 bg-light-200 dark:bg-dark-700 rounded-full overflow-hidden">
                      <div
                        className={`h-full transition-all duration-1000 ease-out ${
                          deployment.status === 'failed'
                            ? 'bg-red-500'
                            : deployment.status === 'completed'
                            ? 'bg-green-500'
                            : 'bg-primary-500'
                        }`}
                        style={{ width: `${getSynchronizedProgress(deployment)}%` }}
                      />
                    </div>
                  </div>

                  {/* Steps timeline */}
                  <div className="flex items-center gap-2 overflow-x-auto pb-2">
                    {displaySteps.slice(0, -1).map((step, index) => (
                      <div key={step} className="flex items-center">
                        <div className="flex items-center gap-2 px-3 py-1.5 bg-light-100 dark:bg-dark-700/50 rounded-lg whitespace-nowrap">
                          {getStepIcon(step, deployment)}
                          <span className="text-sm text-gray-600 dark:text-dark-300">
                            {step === 'pending' && (deployment.status === 'pending_approval' ? 'En attente de validation' : 'En attente')}
                            {step === 'creating_vm' && 'Création VM'}
                            {step === 'installing_os' && 'Installation OS'}
                            {step === 'post_install' && 'Post-install'}
                            {step === 'installing_software' && 'Logiciels'}
                          </span>
                        </div>
                        {index < displaySteps.length - 2 && (
                          <ChevronRight size={16} className="text-gray-300 dark:text-dark-600 mx-1" />
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Error message — masqué quand le déploiement est relancé */}
                  {deployment.error_message && !isActive(deployment.status) && (
                    <div className="mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                      <p className="text-sm text-red-400">{deployment.error_message}</p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Logs Modal */}
        <Modal
          isOpen={isLogsModalOpen}
          onClose={() => {
            setIsLogsModalOpen(false);
            setSelectedDeployment(null);
            setDeploymentLogs([]);
            setLogsError(null);
          }}
          title={`Logs - ${selectedDeployment?.name}`}
          size="lg"
          footer={
            deploymentLogs.length > 0 ? (
              <div className="flex items-center gap-2 w-full justify-end">
                <Button
                  variant="ghost"
                  size="sm"
                  leftIcon={<Copy size={16} />}
                  onClick={handleCopyLogs}
                >
                  Copier les logs
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  leftIcon={<Download size={16} />}
                  onClick={handleExportLogs}
                >
                  Exporter (.txt)
                </Button>
              </div>
            ) : undefined
          }
        >
          {isLoadingLogs ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 size={32} className="text-oto-500 animate-spin" />
              <span className="ml-3 text-gray-500 dark:text-dark-400">Chargement des logs...</span>
            </div>
          ) : logsError ? (
            <div className="text-center py-8">
              <XCircle size={40} className="mx-auto mb-3 text-red-500" />
              <p className="text-red-500 dark:text-red-400">{logsError}</p>
              <Button
                variant="secondary"
                size="sm"
                className="mt-4"
                onClick={() => selectedDeployment && handleViewLogs(selectedDeployment)}
              >
                Réessayer
              </Button>
            </div>
          ) : deploymentLogs.length > 0 ? (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {deploymentLogs.map((log) => (
                <div
                  key={log.id}
                  className={`p-3 rounded-lg text-sm ${
                    log.level === 'error'
                      ? 'bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20'
                      : log.level === 'info'
                      ? 'bg-green-50 dark:bg-green-500/10 border border-green-200 dark:border-green-500/20'
                      : log.level === 'warning'
                      ? 'bg-yellow-50 dark:bg-yellow-500/10 border border-yellow-200 dark:border-yellow-500/20'
                      : 'bg-light-100 dark:bg-dark-700/50 border border-light-200 dark:border-dark-600'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span
                      className={`font-medium ${
                        log.level === 'error'
                          ? 'text-red-600 dark:text-red-400'
                          : log.level === 'info'
                          ? 'text-green-600 dark:text-green-400'
                          : log.level === 'warning'
                          ? 'text-yellow-600 dark:text-yellow-400'
                          : 'text-blue-600 dark:text-blue-400'
                      }`}
                    >
                      [{log.step}]
                    </span>
                    <span className="text-xs text-gray-400 dark:text-dark-500">
                      {new Date(log.created_at).toLocaleTimeString('fr-FR')}
                    </span>
                  </div>
                  <p className="text-gray-700 dark:text-dark-200">{log.message}</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <FileText size={40} className="mx-auto mb-3 text-gray-400 dark:text-dark-500" />
              <p className="text-gray-500 dark:text-dark-400">Aucun log disponible pour ce déploiement</p>
              <p className="text-gray-400 dark:text-dark-500 text-sm mt-2">
                Les logs apparaîtront une fois le déploiement démarré
              </p>
            </div>
          )}
        </Modal>

        {/* Cancel confirmation modal */}
        <ConfirmModal
          isOpen={isCancelModalOpen}
          onClose={() => {
            setIsCancelModalOpen(false);
            setSelectedDeployment(null);
          }}
          onConfirm={() => selectedDeployment && cancelMutation.mutate(selectedDeployment.id)}
          title="Annuler le déploiement"
          message={`Êtes-vous sûr de vouloir annuler le déploiement "${selectedDeployment?.name}" ? Cette action arrêtera le processus en cours.`}
          confirmText="Annuler le déploiement"
          variant="danger"
          isLoading={cancelMutation.isPending}
        />

        {/* Delete confirmation modal */}
        <ConfirmModal
          isOpen={isDeleteModalOpen}
          onClose={() => {
            setIsDeleteModalOpen(false);
            setSelectedDeployment(null);
          }}
          onConfirm={() => selectedDeployment && deleteMutation.mutate(selectedDeployment.id)}
          title="Supprimer le déploiement"
          message={`Êtes-vous sûr de vouloir supprimer le déploiement "${selectedDeployment?.name}" ? Cette action est irréversible et supprimera également tous les logs associés.`}
          confirmText="Supprimer définitivement"
          variant="danger"
          isLoading={deleteMutation.isPending}
        />
      </div>
    </div>
  );
}
