import { useState } from 'react';
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
import type { Deployment, DeploymentStatus, DeploymentLog } from '../types';

const statusOrder: DeploymentStatus[] = [
  'pending',
  'creating_vm',
  'installing_os',
  'post_install',
  'installing_software',
  'completed',
];

export function Deployments() {
  const queryClient = useQueryClient();
  const { addToast } = useToast();

  const [filterStatus, setFilterStatus] = useState<'all' | 'active' | 'completed' | 'failed'>(
    'all'
  );
  const [selectedDeployment, setSelectedDeployment] = useState<Deployment | null>(null);
  const [isLogsModalOpen, setIsLogsModalOpen] = useState(false);
  const [isCancelModalOpen, setIsCancelModalOpen] = useState(false);

  // Fetch deployments
  const { data: deployments = [], isLoading, refetch } = useQuery({
    queryKey: ['deployments'],
    queryFn: () => deploymentsApi.list(),
    refetchInterval: 5000, // Auto-refresh every 5 seconds for active deployments
  });

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

  const handleViewLogs = (deployment: Deployment) => {
    setSelectedDeployment(deployment);
    setIsLogsModalOpen(true);
  };

  const handleCancel = (deployment: Deployment) => {
    setSelectedDeployment(deployment);
    setIsCancelModalOpen(true);
  };

  const handleRetry = (deployment: Deployment) => {
    retryMutation.mutate(deployment.id);
  };

  const filteredDeployments = deployments.filter((d) => {
    if (filterStatus === 'all') return true;
    if (filterStatus === 'active')
      return !['completed', 'failed', 'cancelled'].includes(d.status);
    if (filterStatus === 'completed') return d.status === 'completed';
    if (filterStatus === 'failed') return d.status === 'failed';
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

  const isActive = (status: DeploymentStatus) =>
    !['completed', 'failed', 'cancelled'].includes(status);

  const getStepIcon = (step: DeploymentStatus, currentStatus: DeploymentStatus) => {
    const currentIndex = statusOrder.indexOf(currentStatus);
    const stepIndex = statusOrder.indexOf(step);

    if (currentStatus === 'failed' || currentStatus === 'cancelled') {
      if (stepIndex <= currentIndex) {
        return <XCircle size={16} className="text-red-500" />;
      }
      return <div className="w-4 h-4 rounded-full border-2 border-dark-600" />;
    }

    if (stepIndex < currentIndex || currentStatus === 'completed') {
      return <CheckCircle size={16} className="text-green-500" />;
    }
    if (stepIndex === currentIndex) {
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
    <div className="min-h-screen bg-dark-900">
      <Header title="Déploiements" />
      <div className="p-6">
        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div className="card p-4 flex items-center gap-4">
            <div className="w-12 h-12 bg-primary-600/20 rounded-lg flex items-center justify-center">
              <Rocket size={24} className="text-primary-500" />
            </div>
            <div>
              <p className="text-2xl font-bold text-white">{deployments.length}</p>
              <p className="text-sm text-dark-400">Total</p>
            </div>
          </div>
          <div className="card p-4 flex items-center gap-4">
            <div className="w-12 h-12 bg-blue-500/20 rounded-lg flex items-center justify-center">
              <Loader2 size={24} className="text-blue-500 animate-spin" />
            </div>
            <div>
              <p className="text-2xl font-bold text-white">{activeCount}</p>
              <p className="text-sm text-dark-400">En cours</p>
            </div>
          </div>
          <div className="card p-4 flex items-center gap-4">
            <div className="w-12 h-12 bg-green-500/20 rounded-lg flex items-center justify-center">
              <CheckCircle size={24} className="text-green-500" />
            </div>
            <div>
              <p className="text-2xl font-bold text-white">{completedCount}</p>
              <p className="text-sm text-dark-400">Terminés</p>
            </div>
          </div>
          <div className="card p-4 flex items-center gap-4">
            <div className="w-12 h-12 bg-red-500/20 rounded-lg flex items-center justify-center">
              <XCircle size={24} className="text-red-500" />
            </div>
            <div>
              <p className="text-2xl font-bold text-white">{failedCount}</p>
              <p className="text-sm text-dark-400">Échoués</p>
            </div>
          </div>
        </div>

        {/* Filters and actions */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center bg-dark-800 rounded-lg p-1">
            {(['all', 'active', 'completed', 'failed'] as const).map((status) => (
              <button
                key={status}
                onClick={() => setFilterStatus(status)}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  filterStatus === status
                    ? 'bg-primary-600 text-white'
                    : 'text-dark-300 hover:text-white'
                }`}
              >
                {status === 'all' && 'Tous'}
                {status === 'active' && 'En cours'}
                {status === 'completed' && 'Terminés'}
                {status === 'failed' && 'Échoués'}
              </button>
            ))}
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
                <div className="h-6 bg-dark-700 rounded w-1/4 mb-4" />
                <div className="h-4 bg-dark-700 rounded w-1/2" />
              </div>
            ))}
          </div>
        ) : sortedDeployments.length === 0 ? (
          <div className="card">
            <EmptyState
              icon={Rocket}
              title="Aucun déploiement"
              description="Lancez votre premier déploiement pour créer une machine virtuelle automatiquement."
              action={{
                label: 'Nouveau déploiement',
                onClick: () => {},
                icon: Plus,
              }}
            />
          </div>
        ) : (
          <div className="space-y-4">
            {sortedDeployments.map((deployment) => (
              <div key={deployment.id} className="card p-6">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <div className="flex items-center gap-3">
                      <h3 className="text-lg font-semibold text-white">{deployment.name}</h3>
                      <StatusBadge status={deployment.status} />
                    </div>
                    <div className="flex items-center gap-4 mt-2 text-sm text-dark-400">
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
                  </div>
                </div>

                {/* Progress bar */}
                <div className="mb-4">
                  <div className="flex items-center justify-between text-sm mb-2">
                    <span className="text-dark-400">Progression</span>
                    <span className="text-white font-medium">{deployment.progress}%</span>
                  </div>
                  <div className="h-2 bg-dark-700 rounded-full overflow-hidden">
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
                  {statusOrder.slice(0, -1).map((step, index) => (
                    <div key={step} className="flex items-center">
                      <div className="flex items-center gap-2 px-3 py-1.5 bg-dark-700/50 rounded-lg whitespace-nowrap">
                        {getStepIcon(step, deployment.status)}
                        <span className="text-sm text-dark-300">
                          {step === 'pending' && 'En attente'}
                          {step === 'creating_vm' && 'Création VM'}
                          {step === 'installing_os' && 'Installation OS'}
                          {step === 'post_install' && 'Post-install'}
                          {step === 'installing_software' && 'Logiciels'}
                        </span>
                      </div>
                      {index < statusOrder.length - 2 && (
                        <ChevronRight size={16} className="text-dark-600 mx-1" />
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
          }}
          title={`Logs - ${selectedDeployment?.name}`}
          size="lg"
        >
          {selectedDeployment?.logs && selectedDeployment.logs.length > 0 ? (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {selectedDeployment.logs.map((log) => (
                <div
                  key={log.id}
                  className={`p-3 rounded-lg text-sm ${
                    log.status === 'error'
                      ? 'bg-red-500/10 border border-red-500/20'
                      : log.status === 'success'
                      ? 'bg-green-500/10 border border-green-500/20'
                      : log.status === 'warning'
                      ? 'bg-yellow-500/10 border border-yellow-500/20'
                      : 'bg-dark-700/50 border border-dark-600'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span
                      className={`font-medium ${
                        log.status === 'error'
                          ? 'text-red-400'
                          : log.status === 'success'
                          ? 'text-green-400'
                          : log.status === 'warning'
                          ? 'text-yellow-400'
                          : 'text-blue-400'
                      }`}
                    >
                      [{log.step}]
                    </span>
                    <span className="text-xs text-dark-500">
                      {new Date(log.created_at).toLocaleTimeString('fr-FR')}
                    </span>
                  </div>
                  <p className="text-dark-200">{log.message}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-dark-400 text-center py-8">Aucun log disponible</p>
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
      </div>
    </div>
  );
}
