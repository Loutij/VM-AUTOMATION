import { useEffect, useState, useCallback, useMemo } from 'react';
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
  Wifi,
  WifiOff,
  BarChart3,
  List,
} from 'lucide-react';
import { Header } from '../components/layout';
import { StatCard, StatusBadge } from '../components/ui';
import { vmsApi, hypervisorsApi, deploymentsApi } from '../services/api';
import { useDeploymentEvents } from '../hooks/useWebSocket';
import type { VirtualMachine, Hypervisor, Deployment } from '../types';

export function Dashboard() {
  const navigate = useNavigate();
  const [vms, setVms] = useState<VirtualMachine[]>([]);
  const [hypervisors, setHypervisors] = useState<Hypervisor[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // WebSocket pour les mises a jour temps reel
  const handleDeploymentProgress = useCallback(() => {
    // Recharger les donnees quand un evenement arrive
    loadDashboardData();
  }, []);

  const { isConnected: wsConnected } = useDeploymentEvents(
    undefined,
    handleDeploymentProgress
  );

  async function loadDashboardData() {
    try {
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
    }
  }

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        await loadDashboardData();
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

  // Graphique d'activite des 7 derniers jours
  const activityData = useMemo(() => {
    const now = new Date();
    const days: { label: string; date: string; count: number }[] = [];

    for (let i = 6; i >= 0; i--) {
      const date = new Date(now);
      date.setDate(date.getDate() - i);
      const dateStr = date.toISOString().split('T')[0];
      const dayLabel = date.toLocaleDateString('fr-FR', { weekday: 'short' });

      const count = deployments.filter((d) => {
        const deployDate = new Date(d.created_at).toISOString().split('T')[0];
        return deployDate === dateStr;
      }).length;

      days.push({ label: dayLabel, date: dateStr, count });
    }

    return days;
  }, [deployments]);

  const maxActivity = Math.max(...activityData.map((d) => d.count), 1);

  return (
    <div className="min-h-screen bg-light-100 dark:bg-dark-900 transition-colors">
      <Header title="Dashboard" />

      <div className="p-4 sm:p-6">
        {/* Indicateur de connexion temps reel */}
        <div className="flex items-center justify-end mb-4">
          <div
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
              wsConnected
                ? 'bg-green-100 dark:bg-green-500/20 text-green-600 dark:text-green-400'
                : 'bg-light-200 dark:bg-dark-600 text-gray-500 dark:text-dark-400'
            }`}
            title={wsConnected ? 'Mises à jour en temps réel actives' : 'Mises à jour par polling'}
          >
            {wsConnected ? <Wifi size={14} /> : <WifiOff size={14} />}
            <span>{wsConnected ? 'Temps réel' : 'Hors ligne'}</span>
            <span
              className={`inline-block w-2 h-2 rounded-full ${
                wsConnected ? 'bg-green-500 animate-pulse' : 'bg-gray-400 dark:bg-dark-500'
              }`}
            />
          </div>
        </div>

        {/* Message d'erreur */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-lg flex items-center gap-3 text-red-600 dark:text-red-400">
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
            href="/vms"
          />
          <StatCard
            title="VMs en cours"
            value={loading ? '...' : runningVms}
            icon={PlayCircle}
            color="green"
            href="/vms?state=running"
          />
          <StatCard
            title="Hyperviseurs"
            value={loading ? '...' : hypervisors.length}
            icon={Server}
            color="purple"
            href="/hypervisors"
          />
          <StatCard
            title="Déploiements actifs"
            value={loading ? '...' : activeDeployments}
            icon={Rocket}
            color="yellow"
            href="/deployments?status=in_progress"
          />
        </div>

        {/* Graphique d'activite des 7 derniers jours */}
        <div className="card p-6 mb-8">
          <h2 className="text-lg font-bold uppercase tracking-tight text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <BarChart3 size={20} className="text-oto-500" />
            Activité des 7 derniers jours
          </h2>
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-oto-500" />
            </div>
          ) : (
            <div className="flex items-end gap-3 h-40">
              {activityData.map((day) => {
                const heightPercent = maxActivity > 0 ? (day.count / maxActivity) * 100 : 0;
                return (
                  <div key={day.date} className="flex-1 flex flex-col items-center gap-2">
                    <span className="text-xs font-bold text-gray-900 dark:text-white">
                      {day.count}
                    </span>
                    <div className="w-full flex items-end justify-center" style={{ height: '100px' }}>
                      <div
                        className="w-full max-w-[48px] rounded-t-lg bg-oto-500/80 hover:bg-oto-500 transition-all duration-300 relative group"
                        style={{
                          height: `${Math.max(heightPercent, 4)}%`,
                          minHeight: day.count > 0 ? '8px' : '4px',
                        }}
                      >
                        <div className="absolute -top-8 left-1/2 -translate-x-1/2 bg-dark-800 dark:bg-dark-700 text-white text-xs px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none">
                          {day.count} déploiement{day.count !== 1 ? 's' : ''}
                        </div>
                      </div>
                    </div>
                    <span className="text-xs text-gray-500 dark:text-dark-400 capitalize">
                      {day.label}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Grille principale */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Deploiements recents */}
          <div className="lg:col-span-2 card p-6">
            <h2 className="text-lg font-bold uppercase tracking-tight text-gray-900 dark:text-white mb-4 flex items-center gap-2">
              <Rocket size={20} className="text-oto-500" />
              Déploiements récents
            </h2>
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-oto-500" />
              </div>
            ) : recentDeployments.length === 0 ? (
              <div className="text-center py-8 text-gray-400 dark:text-dark-400">
                <Rocket size={40} className="mx-auto mb-3 opacity-50" />
                <p>Aucun déploiement récent</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="text-left text-oto-700 dark:text-dark-400 text-sm border-b border-light-200 dark:border-dark-700 bg-oto-50 dark:bg-transparent">
                      <th className="pb-3 px-2 font-semibold uppercase tracking-wide">Nom</th>
                      <th className="pb-3 px-2 font-semibold uppercase tracking-wide">Statut</th>
                      <th className="pb-3 px-2 font-semibold uppercase tracking-wide">Progression</th>
                      <th className="pb-3 px-2 font-semibold uppercase tracking-wide">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentDeployments.map((deployment, index) => (
                      <tr
                        key={deployment.id}
                        className={`border-b border-light-200 dark:border-dark-700/50 hover:bg-oto-100 dark:hover:bg-dark-700/70 transition-colors cursor-pointer ${
                          index % 2 === 1 ? 'bg-light-50 dark:bg-dark-800/20' : ''
                        }`}
                        onClick={() => navigate(`/deployments?selected=${deployment.id}`)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') navigate(`/deployments?selected=${deployment.id}`);
                        }}
                      >
                        <td className="py-3 px-2 text-gray-900 dark:text-white font-medium">
                          {deployment.name}
                        </td>
                        <td className="py-3 px-2">
                          <StatusBadge status={deployment.status} size="sm" />
                        </td>
                        <td className="py-3 px-2">
                          <div className="flex items-center gap-2">
                            <div className="w-24 h-2 bg-light-200 dark:bg-dark-700 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-oto-500 transition-all rounded-full"
                                style={{ width: `${deployment.progress}%` }}
                              />
                            </div>
                            <span className="text-sm text-gray-500 dark:text-dark-400 font-medium">
                              {deployment.progress}%
                            </span>
                          </div>
                        </td>
                        <td className="py-3 px-2 text-gray-500 dark:text-dark-400 text-sm">
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
            <h2 className="text-lg font-bold uppercase tracking-tight text-gray-900 dark:text-white mb-4 flex items-center gap-2">
              <Activity size={20} className="text-oto-500" />
              Résumé
            </h2>
            <div className="space-y-4">
              <div className="flex items-center justify-between p-3 bg-light-100 dark:bg-dark-700/50 rounded-lg border border-light-200 dark:border-transparent">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-green-100 dark:bg-green-500/10 rounded-lg flex items-center justify-center">
                    <CheckCircle size={20} className="text-green-600 dark:text-green-400" />
                  </div>
                  <span className="text-gray-700 dark:text-dark-200">Déploiements réussis</span>
                </div>
                <span className="text-xl font-bold text-gray-900 dark:text-white">
                  {loading ? '...' : completedDeployments}
                </span>
              </div>

              <div className="flex items-center justify-between p-3 bg-light-100 dark:bg-dark-700/50 rounded-lg border border-light-200 dark:border-transparent">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-red-100 dark:bg-red-500/10 rounded-lg flex items-center justify-center">
                    <XCircle size={20} className="text-red-600 dark:text-red-400" />
                  </div>
                  <span className="text-gray-700 dark:text-dark-200">Déploiements échoués</span>
                </div>
                <span className="text-xl font-bold text-gray-900 dark:text-white">
                  {loading ? '...' : failedDeployments}
                </span>
              </div>

              <div className="flex items-center justify-between p-3 bg-light-100 dark:bg-dark-700/50 rounded-lg border border-light-200 dark:border-transparent">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-oto-100 dark:bg-oto-500/10 rounded-lg flex items-center justify-center">
                    <PlayCircle size={20} className="text-oto-600 dark:text-oto-400" />
                  </div>
                  <span className="text-gray-700 dark:text-dark-200">VMs actives</span>
                </div>
                <span className="text-xl font-bold text-gray-900 dark:text-white">
                  {loading ? '...' : runningVms}
                </span>
              </div>

              <div className="flex items-center justify-between p-3 bg-light-100 dark:bg-dark-700/50 rounded-lg border border-light-200 dark:border-transparent">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-gray-100 dark:bg-dark-600/50 rounded-lg flex items-center justify-center">
                    <Monitor size={20} className="text-gray-500 dark:text-dark-400" />
                  </div>
                  <span className="text-gray-700 dark:text-dark-200">VMs arrêtées</span>
                </div>
                <span className="text-xl font-bold text-gray-900 dark:text-white">
                  {loading ? '...' : stoppedVms}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Quick actions */}
        <div className="mt-6 card p-6">
          <h2 className="text-lg font-bold uppercase tracking-tight text-gray-900 dark:text-white mb-4">Actions rapides</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <button
              className="flex items-center gap-3 p-4 rounded-xl bg-oto-500 hover:bg-oto-600 text-white transition-all duration-200 hover:shadow-lg hover:shadow-oto-500/25 hover:-translate-y-0.5 active:translate-y-0"
              onClick={() => navigate('/deployments/new')}
            >
              <div className="w-10 h-10 bg-white/20 rounded-lg flex items-center justify-center">
                <Rocket size={22} />
              </div>
              <span className="font-semibold">Nouveau déploiement</span>
            </button>
            <button
              className="flex items-center gap-3 p-4 rounded-xl bg-white dark:bg-dark-800 border border-light-200 dark:border-dark-700 hover:border-oto-500/50 dark:hover:border-oto-500/50 text-gray-900 dark:text-white transition-all duration-200 hover:shadow-lg hover:shadow-oto-500/10 hover:-translate-y-0.5 active:translate-y-0"
              onClick={() => navigate('/vms')}
            >
              <div className="w-10 h-10 bg-blue-100 dark:bg-blue-500/10 rounded-lg flex items-center justify-center">
                <Monitor size={22} className="text-blue-600 dark:text-blue-400" />
              </div>
              <span className="font-semibold">Voir toutes les VMs</span>
            </button>
            <button
              className="flex items-center gap-3 p-4 rounded-xl bg-white dark:bg-dark-800 border border-light-200 dark:border-dark-700 hover:border-oto-500/50 dark:hover:border-oto-500/50 text-gray-900 dark:text-white transition-all duration-200 hover:shadow-lg hover:shadow-oto-500/10 hover:-translate-y-0.5 active:translate-y-0"
              onClick={() => navigate('/hypervisors')}
            >
              <div className="w-10 h-10 bg-purple-100 dark:bg-purple-500/10 rounded-lg flex items-center justify-center">
                <Server size={22} className="text-purple-600 dark:text-purple-400" />
              </div>
              <span className="font-semibold">Ajouter un hyperviseur</span>
            </button>
            <button
              className="flex items-center gap-3 p-4 rounded-xl bg-white dark:bg-dark-800 border border-light-200 dark:border-dark-700 hover:border-oto-500/50 dark:hover:border-oto-500/50 text-gray-900 dark:text-white transition-all duration-200 hover:shadow-lg hover:shadow-oto-500/10 hover:-translate-y-0.5 active:translate-y-0"
              onClick={() => navigate('/deployments')}
            >
              <div className="w-10 h-10 bg-yellow-100 dark:bg-yellow-500/10 rounded-lg flex items-center justify-center">
                <List size={22} className="text-yellow-600 dark:text-yellow-400" />
              </div>
              <span className="font-semibold">Voir les déploiements</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
