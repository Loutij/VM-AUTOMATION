import type { VMState, DeploymentStatus } from '../../types';

type BadgeVariant = 'success' | 'warning' | 'error' | 'info' | 'default';

interface StatusBadgeProps {
  status: VMState | DeploymentStatus | string;
  size?: 'sm' | 'md';
}

// Statuses that represent an ongoing/active process
const activeStatuses = new Set([
  'running',
  'in_progress',
  'installing',
  'creating_vm',
  'installing_os',
  'post_install',
  'installing_software',
  'pending',
  'pending_approval',
]);

const statusConfig: Record<string, { variant: BadgeVariant; label: string }> = {
  // VM States
  running: { variant: 'success', label: 'En cours d\'exécution' },
  stopped: { variant: 'default', label: 'Arrêtée' },
  paused: { variant: 'warning', label: 'En pause' },
  saved: { variant: 'info', label: 'Sauvegardée' },
  unknown: { variant: 'default', label: 'Inconnu' },

  // Deployment States
  pending_approval: { variant: 'warning', label: 'En attente de validation' },
  rejected: { variant: 'error', label: 'Refusé' },
  pending: { variant: 'info', label: 'En attente' },
  in_progress: { variant: 'info', label: 'En cours' },
  installing: { variant: 'info', label: 'Installation' },
  creating_vm: { variant: 'info', label: 'Création VM' },
  installing_os: { variant: 'info', label: 'Installation OS' },
  post_install: { variant: 'info', label: 'Post-installation' },
  installing_software: { variant: 'info', label: 'Installation logiciels' },
  completed: { variant: 'success', label: 'Terminé' },
  failed: { variant: 'error', label: 'Échec' },
  cancelled: { variant: 'warning', label: 'Annulé' },
};

const variantClasses: Record<BadgeVariant, string> = {
  success: 'bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400 border-green-200 dark:border-green-500/20',
  warning: 'bg-yellow-100 dark:bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 border-yellow-200 dark:border-yellow-500/20',
  error: 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/20',
  info: 'bg-oto-100 dark:bg-oto-500/10 text-oto-700 dark:text-oto-400 border-oto-200 dark:border-oto-500/20',
  default: 'bg-gray-100 dark:bg-dark-600/50 text-gray-600 dark:text-dark-300 border-gray-200 dark:border-dark-500/20',
};

const dotClasses: Record<BadgeVariant, string> = {
  success: 'bg-green-500',
  warning: 'bg-yellow-500',
  error: 'bg-red-500',
  info: 'bg-oto-500',
  default: 'bg-gray-400 dark:bg-dark-400',
};

export function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const config = statusConfig[status] || { variant: 'default', label: status };
  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm';
  const isActive = activeStatuses.has(status);

  return (
    <span
      className={`inline-flex items-center font-medium rounded-full border ${variantClasses[config.variant]} ${sizeClasses}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full mr-2 ${dotClasses[config.variant]} ${isActive ? 'animate-pulse' : ''}`}
      />
      {config.label}
    </span>
  );
}
