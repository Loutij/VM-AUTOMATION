import { forwardRef } from 'react';
import { CheckCircle, XCircle, Loader2, Clock, AlertCircle } from 'lucide-react';

// Types
type StepStatus = 'pending' | 'active' | 'completed' | 'error' | 'warning';

interface ProgressStep {
  id: string;
  label: string;
  description?: string;
  status: StepStatus;
  timestamp?: string;
  error?: string;
}

interface ProgressBarProps {
  value: number;
  max?: number;
  size?: 'sm' | 'md' | 'lg';
  color?: 'primary' | 'success' | 'warning' | 'error';
  showLabel?: boolean;
  animated?: boolean;
  className?: string;
}

interface ProgressTimelineProps {
  steps: ProgressStep[];
  orientation?: 'horizontal' | 'vertical';
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

interface ProgressCircleProps {
  value: number;
  max?: number;
  size?: number;
  strokeWidth?: number;
  color?: 'primary' | 'success' | 'warning' | 'error';
  showLabel?: boolean;
  className?: string;
}

// Couleurs par statut - OTO style
const statusColors = {
  pending: 'bg-gray-200 dark:bg-dark-600 text-gray-500 dark:text-dark-400 border-gray-300 dark:border-dark-600',
  active: 'bg-oto-500 text-white border-oto-500 animate-pulse',
  completed: 'bg-green-500 text-white border-green-500',
  error: 'bg-red-500 text-white border-red-500',
  warning: 'bg-yellow-500 text-white border-yellow-500',
};

const statusLineColors = {
  pending: 'bg-gray-200 dark:bg-dark-600',
  active: 'bg-oto-500',
  completed: 'bg-green-500',
  error: 'bg-red-500',
  warning: 'bg-yellow-500',
};

const progressColors = {
  primary: 'bg-oto-500',
  success: 'bg-green-500',
  warning: 'bg-yellow-500',
  error: 'bg-red-500',
};

const progressBgColors = {
  primary: 'bg-oto-100 dark:bg-oto-500/20',
  success: 'bg-green-100 dark:bg-green-500/20',
  warning: 'bg-yellow-100 dark:bg-yellow-500/20',
  error: 'bg-red-100 dark:bg-red-500/20',
};

// Icônes par statut
function StatusIcon({ status, size = 16 }: { status: StepStatus; size?: number }) {
  switch (status) {
    case 'completed':
      return <CheckCircle size={size} />;
    case 'error':
      return <XCircle size={size} />;
    case 'warning':
      return <AlertCircle size={size} />;
    case 'active':
      return <Loader2 size={size} className="animate-spin" />;
    default:
      return <Clock size={size} />;
  }
}

// Barre de progression simple
export const ProgressBar = forwardRef<HTMLDivElement, ProgressBarProps>(
  (
    {
      value,
      max = 100,
      size = 'md',
      color = 'primary',
      showLabel = false,
      animated = true,
      className = '',
    },
    ref
  ) => {
    const percentage = Math.min(Math.max((value / max) * 100, 0), 100);
    
    const sizeClasses = {
      sm: 'h-1',
      md: 'h-2',
      lg: 'h-3',
    };

    return (
      <div ref={ref} className={`w-full ${className}`}>
        {showLabel && (
          <div className="flex justify-between mb-1">
            <span className="text-sm text-gray-500 dark:text-dark-300">Progression</span>
            <span className="text-sm text-gray-900 dark:text-white font-medium">{Math.round(percentage)}%</span>
          </div>
        )}
        <div className={`w-full ${progressBgColors[color]} rounded-full overflow-hidden ${sizeClasses[size]}`}>
          <div
            className={`h-full ${progressColors[color]} rounded-full transition-all duration-500 ease-out ${
              animated && percentage < 100 ? 'animate-progress-stripes' : ''
            }`}
            style={{ width: `${percentage}%` }}
            role="progressbar"
            aria-valuenow={value}
            aria-valuemin={0}
            aria-valuemax={max}
          />
        </div>
      </div>
    );
  }
);

ProgressBar.displayName = 'ProgressBar';

// Timeline de progression
export const ProgressTimeline = forwardRef<HTMLDivElement, ProgressTimelineProps>(
  ({ steps, orientation = 'vertical', size = 'md', className = '' }, ref) => {
    const isVertical = orientation === 'vertical';
    
    const stepSizes = {
      sm: { circle: 'w-6 h-6', icon: 14, line: 'w-0.5', gap: 'gap-2' },
      md: { circle: 'w-8 h-8', icon: 16, line: 'w-0.5', gap: 'gap-3' },
      lg: { circle: 'w-10 h-10', icon: 20, line: 'w-1', gap: 'gap-4' },
    };

    const currentSize = stepSizes[size];

    if (isVertical) {
      return (
        <div ref={ref} className={`space-y-0 ${className}`}>
          {steps.map((step, index) => {
            const isLast = index === steps.length - 1;
            const isCompleted = step.status === 'completed';
            const isActive = step.status === 'active';
            
            return (
              <div key={step.id} className="flex">
                {/* Colonne icône + ligne */}
                <div className="flex flex-col items-center">
                  {/* Cercle avec icône */}
                  <div
                    className={`${currentSize.circle} rounded-full flex items-center justify-center border-2 ${statusColors[step.status]}`}
                  >
                    <StatusIcon status={step.status} size={currentSize.icon} />
                  </div>
                  
                  {/* Ligne vers le suivant */}
                  {!isLast && (
                    <div
                      className={`${currentSize.line} flex-1 min-h-[2rem] ${
                        isCompleted ? statusLineColors.completed : statusLineColors.pending
                      }`}
                    />
                  )}
                </div>
                
                {/* Contenu */}
                <div className={`ml-3 pb-6 ${isLast ? 'pb-0' : ''}`}>
                  <div className="flex items-center gap-2">
                    <span
                      className={`font-medium ${
                        isActive
                          ? 'text-oto-500'
                          : isCompleted
                          ? 'text-green-600 dark:text-green-400'
                          : step.status === 'error'
                          ? 'text-red-600 dark:text-red-400'
                          : 'text-gray-500 dark:text-dark-300'
                      }`}
                    >
                      {step.label}
                    </span>
                    {step.timestamp && (
                      <span className="text-xs text-gray-400 dark:text-dark-500">{step.timestamp}</span>
                    )}
                  </div>
                  {step.description && (
                    <p className="text-sm text-gray-500 dark:text-dark-400 mt-0.5">{step.description}</p>
                  )}
                  {step.error && (
                    <p className="text-sm text-red-600 dark:text-red-400 mt-1 p-2 bg-red-100 dark:bg-red-500/10 rounded">
                      {step.error}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      );
    }

    // Version horizontale
    return (
      <div ref={ref} className={`flex items-start ${currentSize.gap} ${className}`}>
        {steps.map((step, index) => {
          const isLast = index === steps.length - 1;
          const isCompleted = step.status === 'completed';
          const isActive = step.status === 'active';

          return (
            <div key={step.id} className="flex items-center flex-1">
              <div className="flex flex-col items-center">
                {/* Cercle avec icône */}
                <div
                  className={`${currentSize.circle} rounded-full flex items-center justify-center border-2 ${statusColors[step.status]}`}
                >
                  <StatusIcon status={step.status} size={currentSize.icon} />
                </div>
                
                {/* Label */}
                <span
                  className={`mt-2 text-xs text-center max-w-[80px] ${
                    isActive
                      ? 'text-oto-500 font-medium'
                      : isCompleted
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-gray-500 dark:text-dark-400'
                  }`}
                >
                  {step.label}
                </span>
              </div>
              
              {/* Ligne de connexion */}
              {!isLast && (
                <div
                  className={`flex-1 h-0.5 mx-2 ${
                    isCompleted ? statusLineColors.completed : statusLineColors.pending
                  }`}
                  style={{ marginTop: `-${parseInt(currentSize.circle.split('-')[1]) * 4}px` }}
                />
              )}
            </div>
          );
        })}
      </div>
    );
  }
);

ProgressTimeline.displayName = 'ProgressTimeline';

// Progression circulaire
export const ProgressCircle = forwardRef<HTMLDivElement, ProgressCircleProps>(
  (
    {
      value,
      max = 100,
      size = 80,
      strokeWidth = 8,
      color = 'primary',
      showLabel = true,
      className = '',
    },
    ref
  ) => {
    const percentage = Math.min(Math.max((value / max) * 100, 0), 100);
    const radius = (size - strokeWidth) / 2;
    const circumference = radius * 2 * Math.PI;
    const offset = circumference - (percentage / 100) * circumference;

    const strokeColors = {
      primary: 'stroke-oto-500',
      success: 'stroke-green-500',
      warning: 'stroke-yellow-500',
      error: 'stroke-red-500',
    };

    return (
      <div ref={ref} className={`relative inline-flex items-center justify-center ${className}`}>
        <svg width={size} height={size} className="transform -rotate-90">
          {/* Cercle de fond */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="transparent"
            stroke="currentColor"
            strokeWidth={strokeWidth}
            className="text-gray-200 dark:text-dark-700"
          />
          {/* Cercle de progression */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="transparent"
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            className={`${strokeColors[color]} transition-all duration-500 ease-out`}
          />
        </svg>
        {showLabel && (
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-lg font-bold text-gray-900 dark:text-white">{Math.round(percentage)}%</span>
          </div>
        )}
      </div>
    );
  }
);

ProgressCircle.displayName = 'ProgressCircle';

// Export types
export type { ProgressStep, StepStatus, ProgressBarProps, ProgressTimelineProps, ProgressCircleProps };
