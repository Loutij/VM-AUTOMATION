import { useState, useEffect, useRef, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
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
import { deploymentsApi } from '../services/api';
import { useDeploymentEvents } from '../hooks/useWebSocket';
import type { Deployment, DeploymentStatus, DeploymentLog } from '../types';

// Étapes affichées dans l'interface
const displaySteps = [
  'pending',
  'creating_vm',
  'installing_os',
  'post_install',
  'installing_software',
  'completed',
] as const;

type DisplayStep = typeof displaySteps[number];

// Mapping current_step backend -> étape affichée
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

// Fonction pour obtenir l'étape affichée à partir du déploiement
const getDisplayStep = (deployment: Deployment): DisplayStep => {
  // Statuts terminaux
  if (deployment.status === 'completed') return 'completed';
  if (deployment.status === 'failed' || deployment.status === 'cancelled') return 'completed';
  if (deployment.status === 'pending') return 'pending';
  
  // Utiliser current_step pour les déploiements en cours
  if (deployment.current_step) {
    return stepToDisplayStep[deployment.current_step] || 'creating_vm';
  }
  
  return 'pending';
};

export function Deployments() {
  const queryClient = useQueryClient();
  const { addToast } = useToast();

  const [filterStatus, setFilterStatus] = useState<'all' | 'active' | 'completed' | 'failed' | 'cancelled'>(
    'all'
  );
  const [selectedDeployment, setSelectedDeployment] = useState<Deployment | null>(null);
  const [isLogsModalOpen, setIsLogsModalOpen] = useState(false);
  const [isCancelModalOpen, setIsCancelModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [deploymentLogs, setDeploymentLogs] = useState<DeploymentLog[]>([]);
  const [isLoadingLogs, setIsLoadingLogs] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);
  
  // Track previous statuses for animations
  const previousStatuses = useRef<Record<string, string>>({});

  // Fetch deployments
  const { data: deployments = [], isLoading, refetch } = useQuery({
    queryKey: ['deployments'],
    queryFn: () => deploymentsApi.list(),
    refetchInterval: 5000, // Auto-refresh every 5 seconds for active deployments
  });

  // WebSocket pour les mises à jour temps réel
  const handleDeploymentProgress = useCallback(() => {
    // Rafraîchir immédiatement quand un événement WebSocket arrive
    queryClient.invalidateQueries({ queryKey: ['deployments'] });
  }, [queryClient]);

  const { isConnected: wsConnected } = useDeploymentEvents(
    undefined, // écouter tous les déploiements
    handleDeploymentProgress
  );

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

  const handleCancel = (deployment: Deployment) => {
    setSelectedDeployment(deployment);
    setIsCancelModalOpen(true);
  };

  const handleRetry = (deployment: Deployment) => {
    retryMutation.mutate(deployment.id);
  };

  const handleDelete = (deployment: Deployment) => {
    setSelectedDeployment(deployment);
    setIsDeleteModalOpen(true);
  };

  const filteredDeployments = deployments.filter((d) => {
    if (filterStatus === 'all') return true;
    if (filterStatus === 'active')
      return !['completed', 'failed', 'cancelled'].includes(d.status);
    if (filterStatus === 'completed') return d.status === 'completed';
    if (filterStatus === 'failed') return d.status === 'failed';
    if (filterStatus === 'cancelled') return d.status === 'cancelled';
    return true;
  });

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
    !['completed', 'failed', 'cancelled'].includes(status);

  const getStepIcon = (step: DisplayStep, deployment: Deployment) => {
    const currentDisplayStep = getDisplayStep(deployment);
    const currentIndex = displaySteps.indexOf(currentDisplayStep);
    const stepIndex = displaySteps.indexOf(step);

    if (deployment.status === 'failed' || deployment.status === 'cancelled') {
      if (stepIndex <= currentIndex) {
        return <XCircle size={16} className="text-red-500" />;
      }
      return <div className="w-4 h-4 rounded-full border-2 border-dark-600" />;
    }

    if (stepIndex < currentIndex || deployment.status === 'completed') {
      return <CheckCircle size={16} className="text-green-500" />;
    }
    if (stepIndex === currentIndex && deployment.status !== 'pending') {
      return <Loader2 size={16} className="text-primary-500 animate-spin" />;
    }
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

  return (
    <div className="min-h-screen bg-light-100 dark:bg-dark-900">
      <Header title="Déploiements" />
      <div className="p-6">
        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          <div className="card p-4 flex items-center gap-4">
            <div className="w-12 h-12 bg-oto-100 dark:bg-primary-600/20 rounded-lg flex items-center justify-center">
              <Rocket size={24} className="text-oto-500" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{deployments.length}</p>
              <p className="text-sm text-gray-500 dark:text-dark-400">Total</p>
            </div>
          </div>
          <div className="card p-4 flex items-center gap-4">
            <div className="w-12 h-12 bg-blue-100 dark:bg-blue-500/20 rounded-lg flex items-center justify-center">
              <Loader2 size={24} className={`text-blue-500 ${activeCount > 0 ? 'animate-spin' : ''}`} />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{activeCount}</p>
              <p className="text-sm text-gray-500 dark:text-dark-400">En cours</p>
            </div>
          </div>
          <div className="card p-4 flex items-center gap-4">
            <div className="w-12 h-12 bg-green-100 dark:bg-green-500/20 rounded-lg flex items-center justify-center">
              <CheckCircle size={24} className="text-green-500" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{completedCount}</p>
              <p className="text-sm text-gray-500 dark:text-dark-400">Terminés</p>
            </div>
          </div>
          <div className="card p-4 flex items-center gap-4">
            <div className="w-12 h-12 bg-red-100 dark:bg-red-500/20 rounded-lg flex items-center justify-center">
              <XCircle size={24} className="text-red-500" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{failedCount}</p>
              <p className="text-sm text-gray-500 dark:text-dark-400">Échoués</p>
            </div>
          </div>
          <div className="card p-4 flex items-center gap-4">
            <div className="w-12 h-12 bg-yellow-100 dark:bg-yellow-500/20 rounded-lg flex items-center justify-center">
              <X size={24} className="text-yellow-500" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{cancelledCount}</p>
              <p className="text-sm text-gray-500 dark:text-dark-400">Annulés</p>
            </div>
          </div>
        </div>

        {/* Filters and actions */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center bg-white dark:bg-dark-800 rounded-lg p-1 flex-wrap gap-1 border border-light-200 dark:border-transparent">
            {(['all', 'active', 'completed', 'failed', 'cancelled'] as const).map((status) => (
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
          <div className="flex items-center gap-3">
            {/* Indicateur de connexion temps réel */}
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
              title="Aucun déploiement"
              description="Lancez votre premier déploiement pour créer une machine virtuelle automatiquement."
            />
          </div>
        ) : (
          <div className="space-y-4">
            {sortedDeployments.map((deployment) => (
              <div 
                key={deployment.id} 
                className={`card p-6 transition-all duration-300 border-l-4 ${
                  deployment.status === 'completed' 
                    ? 'border-l-green-500' 
                    : deployment.status === 'failed' 
                    ? 'border-l-red-500' 
                    : deployment.status === 'cancelled'
                    ? 'border-l-yellow-500'
                    : isActive(deployment.status)
                    ? 'border-l-blue-500'
                    : 'border-l-dark-600'
                }`}
              >
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
                      {isActive(deployment.status) && (
                        <span>Durée: {formatDuration(deployment.created_at)}</span>
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
                    {isActive(deployment.status) && (
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
                    {deployment.status === 'failed' && (
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
                    {['completed', 'failed', 'cancelled'].includes(deployment.status) && (
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
                    <span className="text-gray-900 dark:text-white font-medium">{deployment.progress}%</span>
                  </div>
                  <div className="h-2 bg-light-200 dark:bg-dark-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full transition-all duration-500 ${
                        deployment.status === 'failed'
                          ? 'bg-red-500'
                          : deployment.status === 'completed'
                          ? 'bg-green-500'
                          : 'bg-primary-500'
                      }`}
                      style={{ width: `${deployment.progress}%` }}
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
                          {step === 'pending' && 'En attente'}
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

                {/* Error message */}
                {deployment.error_message && (
                  <div className="mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                    <p className="text-sm text-red-400">{deployment.error_message}</p>
                  </div>
                )}
              </div>
            ))}
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
