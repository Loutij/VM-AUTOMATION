import type { LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string | number;
  icon: LucideIcon;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  color?: 'blue' | 'green' | 'red' | 'yellow' | 'purple';
}

const colorClasses = {
  blue: 'bg-oto-100 dark:bg-oto-500/10 text-oto-600 dark:text-oto-400',
  green: 'bg-green-100 dark:bg-green-500/10 text-green-600 dark:text-green-400',
  red: 'bg-red-100 dark:bg-red-500/10 text-red-600 dark:text-red-400',
  yellow: 'bg-yellow-100 dark:bg-yellow-500/10 text-yellow-600 dark:text-yellow-400',
  purple: 'bg-purple-100 dark:bg-purple-500/10 text-purple-600 dark:text-purple-400',
};

export function StatCard({
  title,
  value,
  icon: Icon,
  trend,
  color = 'blue',
}: StatCardProps) {
  return (
    <div className="card p-6">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-gray-500 dark:text-dark-400 font-medium uppercase tracking-wide">{title}</p>
          <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-white">{value}</p>
          {trend && (
            <p
              className={`mt-2 text-sm font-medium ${
                trend.isPositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
              }`}
            >
              {trend.isPositive ? '+' : '-'}
              {Math.abs(trend.value)}%
              <span className="text-gray-400 dark:text-dark-400 ml-1 font-normal">vs hier</span>
            </p>
          )}
        </div>
        <div className={`p-3 rounded-xl ${colorClasses[color]}`}>
          <Icon size={24} />
        </div>
      </div>
    </div>
  );
}
