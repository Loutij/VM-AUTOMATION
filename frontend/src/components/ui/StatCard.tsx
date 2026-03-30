import { useNavigate } from 'react-router-dom';
import { TrendingUp, TrendingDown } from 'lucide-react';
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
  onClick?: () => void;
  href?: string;
  active?: boolean;
  subtitle?: string;
}

const colorClasses = {
  blue: 'bg-oto-100 dark:bg-oto-500/10 text-oto-600 dark:text-oto-400',
  green: 'bg-green-100 dark:bg-green-500/10 text-green-600 dark:text-green-400',
  red: 'bg-red-100 dark:bg-red-500/10 text-red-600 dark:text-red-400',
  yellow: 'bg-yellow-100 dark:bg-yellow-500/10 text-yellow-600 dark:text-yellow-400',
  purple: 'bg-purple-100 dark:bg-purple-500/10 text-purple-600 dark:text-purple-400',
};

const activeColorClasses: Record<string, string> = {
  blue: 'border-oto-500 dark:border-oto-400 bg-oto-50/50 dark:bg-oto-500/5',
  green: 'border-green-500 dark:border-green-400 bg-green-50/50 dark:bg-green-500/5',
  red: 'border-red-500 dark:border-red-400 bg-red-50/50 dark:bg-red-500/5',
  yellow: 'border-yellow-500 dark:border-yellow-400 bg-yellow-50/50 dark:bg-yellow-500/5',
  purple: 'border-purple-500 dark:border-purple-400 bg-purple-50/50 dark:bg-purple-500/5',
};

export function StatCard({
  title,
  value,
  icon: Icon,
  trend,
  color = 'blue',
  onClick,
  href,
  active = false,
  subtitle,
}: StatCardProps) {
  const navigate = useNavigate();
  const isClickable = !!(onClick || href);

  const handleClick = () => {
    if (onClick) {
      onClick();
    } else if (href) {
      navigate(href);
    }
  };

  return (
    <div
      className={`card p-6 transition-all duration-200 ${
        isClickable
          ? 'cursor-pointer hover:shadow-lg hover:shadow-oto-500/10 hover:-translate-y-0.5 hover:border-oto-500/30 active:translate-y-0'
          : ''
      } ${active ? `border-2 ${activeColorClasses[color]}` : ''}`}
      onClick={isClickable ? handleClick : undefined}
      role={isClickable ? 'button' : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={isClickable ? (e) => { if (e.key === 'Enter' || e.key === ' ') handleClick(); } : undefined}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-gray-500 dark:text-dark-400 font-medium uppercase tracking-wide">{title}</p>
          <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-white">{value}</p>
          {subtitle && (
            <p className="mt-1 text-sm text-gray-500 dark:text-dark-400">{subtitle}</p>
          )}
          {trend && (
            <div
              className={`mt-2 flex items-center gap-1 text-sm font-medium ${
                trend.isPositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
              }`}
            >
              {trend.isPositive ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
              <span>
                {trend.isPositive ? '+' : '-'}
                {Math.abs(trend.value)}%
              </span>
              <span className="text-gray-400 dark:text-dark-400 ml-0.5 font-normal">vs hier</span>
            </div>
          )}
        </div>
        <div className={`p-3 rounded-xl ${colorClasses[color]}`}>
          <Icon size={24} />
        </div>
      </div>
    </div>
  );
}
