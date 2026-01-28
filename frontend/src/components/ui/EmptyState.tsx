import type { LucideIcon } from 'lucide-react';
import { Button } from './Button';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
    icon?: LucideIcon;
  };
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  const ActionIcon = action?.icon;

  return (
    <div className="flex flex-col items-center justify-center py-12 px-4">
      <div className="w-16 h-16 bg-light-200 dark:bg-dark-700 rounded-full flex items-center justify-center mb-4">
        <Icon size={32} className="text-gray-400 dark:text-dark-400" />
      </div>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">{title}</h3>
      {description && (
        <p className="text-gray-500 dark:text-dark-400 text-center max-w-sm mb-4">{description}</p>
      )}
      {action && (
        <Button onClick={action.onClick} leftIcon={ActionIcon && <ActionIcon size={18} />}>
          {action.label}
        </Button>
      )}
    </div>
  );
}
