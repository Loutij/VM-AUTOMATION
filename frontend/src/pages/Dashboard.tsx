import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Monitor,
  Server,
  Rocket,
  CheckCircle,
  XCircle,
  PlayCircle,
  Activity,
  AlertTriangle,
} from 'lucide-react';
import { Header } from '../components/layout';
import { StatCard, StatusBadge } from '../components/ui';
import { vmsApi, hypervisorsApi, deploymentsApi } from '../services/api';
import type { VirtualMachine, Hypervisor, Deployment } from '../types';

export function Dashboard() {
  const navigate = useNavigate();
  const [vms, setVms] = useState<VirtualMachine[]>([]);
  const [hypervisors, setHypervisors] = useState<Hypervisor[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        const [vmsData, hypervisorsData, deploymentsData] = await Promise.allSettled([
          vmsApi.list(),
          hypervisorsApi.list(),
          deploymentsApi.list(),
        ]);

        if (vmsData.status === 'fulfilled') setVms(vmsData.value);
        if (hypervisorsData.status === 'fulfilled') setHypervisors(hypervisorsData.value);
        if (deploymentsData.status === 'fulfilled') setDeployments(deploymentsData.value);
      } catch (err) {
        setError('Erreur lors du chargement des données');
        console.error(err);
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, []);

  const runningVms = vms.filter((vm) => vm.state === 'running').length;
  const stoppedVms = vms.filter((vm) => vm.state === 'stopped').length;
  const activeDeployments = deployments.filter(
    (d) => !['completed', 'failed', 'cancelled'].includes(d.status)
  ).length;
  const completedDeployments = deployments.filter((d) => d.status === 'completed').length;
  const failedDeployments = deployments.filter((d) => d.status === 'failed').length;

  const recentDeployments = deployments
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 5);

  return (
    <div className="min-h-screen bg-dark-900">
      <Header title="Dashboard" />

      <div className="p-6">
        {/* Message d'erreur */}
        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-lg flex items-center gap-3 text-red-500">
            <AlertTriangle size={20} />
            <span>{error}</span>
          </div>
        )}

        {/* Stats cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <StatCard
            title="Total VMs"
            value={loading ? '...' : vms.length}
            icon={Monitor}
            color="blue"
          />
          <StatCard
            title="VMs en cours"
            value={loading ? '...' : runningVms}
            icon={PlayCircle}
            color="green"
          />
          <StatCard
            title="Hyperviseurs"
            value={loading ? '...' : hypervisors.length}
            icon={Server}
            color="purple"
          />
          <StatCard
            title="Déploiements actifs"
            value={loading ? '...' : activeDeployments}
            icon={Rocket}
            color="yellow"
          />
        </div>

        {/* Grille principale */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Déploiements récents */}
          <div className="lg:col-span-2 card p-6">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Rocket size={20} className="text-primary-500" />
              Déploiements récents
            </h2>
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500" />
              </div>
            ) : recentDeployments.length === 0 ? (
              <div className="text-center py-8 text-dark-400">
                <Rocket size={40} className="mx-auto mb-3 opacity-50" />
                <p>Aucun déploiement récent</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="text-left text-dark-400 text-sm border-b border-dark-700">
                      <th className="pb-3 font-medium">Nom</th>
                      <th className="pb-3 font-medium">Statut</th>
                      <th className="pb-3 font-medium">Progression</th>
                      <th className="pb-3 font-medium">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentDeployments.map((deployment) => (
                      <tr
                        key={deployment.id}
                        className="border-b border-dark-700/50 hover:bg-dark-800/50 transition-colors"
                      >
                        <td className="py-3 text-white font-medium">
                          {deployment.name}
                        </td>
                        <td className="py-3">
                          <StatusBadge status={deployment.status} size="sm" />
                        </td>
                        <td className="py-3">
                          <div className="flex items-center gap-2">
                            <div className="w-24 h-2 bg-dark-700 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-primary-500 transition-all"
                                style={{ width: `${deployment.progress}%` }}
                              />
                            </div>
                            <span className="text-sm text-dark-400">
                              {deployment.progress}%
                            </span>
                          </div>
                        </td>
                        <td className="py-3 text-dark-400 text-sm">
                          {new Date(deployment.created_at).toLocaleDateString('fr-FR')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Statistiques */}
          <div className="card p-6">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Activity size={20} className="text-primary-500" />
              Résumé
            </h2>
            <div className="space-y-4">
              <div className="flex items-center justify-between p-3 bg-dark-700/50 rounded-lg">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-green-500/10 rounded-lg flex items-center justify-center">
                    <CheckCircle size={20} className="text-green-500" />
                  </div>
                  <span className="text-dark-200">Déploiements réussis</span>
                </div>
                <span className="text-xl font-bold text-white">
                  {loading ? '...' : completedDeployments}
                </span>
              </div>

              <div className="flex items-center justify-between p-3 bg-dark-700/50 rounded-lg">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-red-500/10 rounded-lg flex items-center justify-center">
                    <XCircle size={20} className="text-red-500" />
                  </div>
                  <span className="text-dark-200">Déploiements échoués</span>
                </div>
                <span className="text-xl font-bold text-white">
                  {loading ? '...' : failedDeployments}
                </span>
              </div>

              <div className="flex items-center justify-between p-3 bg-dark-700/50 rounded-lg">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-blue-500/10 rounded-lg flex items-center justify-center">
                    <PlayCircle size={20} className="text-blue-500" />
                  </div>
                  <span className="text-dark-200">VMs actives</span>
                </div>
                <span className="text-xl font-bold text-white">
                  {loading ? '...' : runningVms}
                </span>
              </div>

              <div className="flex items-center justify-between p-3 bg-dark-700/50 rounded-lg">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-dark-600/50 rounded-lg flex items-center justify-center">
                    <Monitor size={20} className="text-dark-400" />
                  </div>
                  <span className="text-dark-200">VMs arrêtées</span>
                </div>
                <span className="text-xl font-bold text-white">
                  {loading ? '...' : stoppedVms}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Quick actions */}
        <div className="mt-6 card p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Actions rapides</h2>
          <div className="flex flex-wrap gap-3">
            <button 
              className="btn-primary flex items-center gap-2"
              onClick={() => navigate('/deployments/new')}
            >
              <Rocket size={18} />
              Nouveau déploiement
            </button>
            <button 
              className="btn-secondary flex items-center gap-2"
              onClick={() => navigate('/vms')}
            >
              <Monitor size={18} />
              Voir toutes les VMs
            </button>
            <button 
              className="btn-secondary flex items-center gap-2"
              onClick={() => navigate('/hypervisors')}
            >
              <Server size={18} />
              Ajouter un hyperviseur
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
