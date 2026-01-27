import type { VMState, DeploymentStatus } from '../../types';

type BadgeVariant = 'success' | 'warning' | 'error' | 'info' | 'default';

interface StatusBadgeProps {
  status: VMState | DeploymentStatus | string;
  size?: 'sm' | 'md';
}

const statusConfig: Record<string, { variant: BadgeVariant; label: string }> = {
  // VM States
  running: { variant: 'success', label: 'En cours d\'exécution' },
  stopped: { variant: 'default', label: 'Arrêtée' },
  paused: { variant: 'warning', label: 'En pause' },
  saved: { variant: 'info', label: 'Sauvegardée' },
  unknown: { variant: 'default', label: 'Inconnu' },
  
  // Deployment States
  pending: { variant: 'info', label: 'En attente' },
  creating_vm: { variant: 'info', label: 'Création VM' },
  installing_os: { variant: 'info', label: 'Installation OS' },
  post_install: { variant: 'info', label: 'Post-installation' },
  installing_software: { variant: 'info', label: 'Installation logiciels' },
  completed: { variant: 'success', label: 'Terminé' },
  failed: { variant: 'error', label: 'Échec' },
  cancelled: { variant: 'warning', label: 'Annulé' },
};

const variantClasses: Record<BadgeVariant, string> = {
  success: 'bg-green-500/10 text-green-500 border-green-500/20',
  warning: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
  error: 'bg-red-500/10 text-red-500 border-red-500/20',
  info: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  default: 'bg-dark-600/50 text-dark-300 border-dark-500/20',
};

export function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const config = statusConfig[status] || { variant: 'default', label: status };
  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm';

  return (
    <span
      className={`inline-flex items-center font-medium rounded-full border ${variantClasses[config.variant]} ${sizeClasses}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full mr-2 ${
          config.variant === 'success'
            ? 'bg-green-500'
            : config.variant === 'warning'
            ? 'bg-yellow-500'
            : config.variant === 'error'
            ? 'bg-red-500'
            : config.variant === 'info'
            ? 'bg-blue-500 animate-pulse'
            : 'bg-dark-400'
        }`}
      />
      {config.label}
    </span>
  );
}
