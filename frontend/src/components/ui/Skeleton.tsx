import { forwardRef } from 'react';

interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  variant?: 'text' | 'rectangular' | 'circular';
  animation?: 'pulse' | 'wave' | 'none';
  className?: string;
}

interface SkeletonCardProps {
  hasImage?: boolean;
  lines?: number;
  className?: string;
}

interface SkeletonTableProps {
  rows?: number;
  columns?: number;
  hasHeader?: boolean;
  className?: string;
}

// Skeleton de base
export const Skeleton = forwardRef<HTMLDivElement, SkeletonProps>(
  (
    {
      width,
      height,
      variant = 'rectangular',
      animation = 'pulse',
      className = '',
    },
    ref
  ) => {
    const variantClasses = {
      text: 'rounded',
      rectangular: 'rounded-lg',
      circular: 'rounded-full',
    };

    const animationClasses = {
      pulse: 'animate-pulse',
      wave: 'animate-skeleton-wave',
      none: '',
    };

    const style: React.CSSProperties = {
      width: typeof width === 'number' ? `${width}px` : width,
      height: typeof height === 'number' ? `${height}px` : height,
    };

    return (
      <div
        ref={ref}
        className={`bg-dark-700 ${variantClasses[variant]} ${animationClasses[animation]} ${className}`}
        style={style}
        aria-label="Chargement..."
        role="status"
      />
    );
  }
);

Skeleton.displayName = 'Skeleton';

// Skeleton pour une carte
export const SkeletonCard = forwardRef<HTMLDivElement, SkeletonCardProps>(
  ({ hasImage = true, lines = 3, className = '' }, ref) => {
    return (
      <div
        ref={ref}
        className={`card p-4 space-y-4 ${className}`}
      >
        {hasImage && (
          <Skeleton
            variant="rectangular"
            width="100%"
            height={160}
          />
        )}
        <div className="space-y-3">
          <Skeleton variant="text" width="60%" height={20} />
          {Array.from({ length: lines }).map((_, index) => (
            <Skeleton
              key={index}
              variant="text"
              width={index === lines - 1 ? '40%' : '100%'}
              height={14}
            />
          ))}
        </div>
      </div>
    );
  }
);

SkeletonCard.displayName = 'SkeletonCard';

// Skeleton pour un tableau
export const SkeletonTable = forwardRef<HTMLDivElement, SkeletonTableProps>(
  ({ rows = 5, columns = 4, hasHeader = true, className = '' }, ref) => {
    return (
      <div ref={ref} className={`overflow-hidden ${className}`}>
        <div className="card overflow-hidden">
          {hasHeader && (
            <div className="flex items-center gap-4 p-4 border-b border-dark-700 bg-dark-800/50">
              {Array.from({ length: columns }).map((_, index) => (
                <Skeleton
                  key={`header-${index}`}
                  variant="text"
                  width={index === 0 ? '15%' : '20%'}
                  height={16}
                  className="flex-shrink-0"
                />
              ))}
            </div>
          )}
          <div className="divide-y divide-dark-700">
            {Array.from({ length: rows }).map((_, rowIndex) => (
              <div
                key={`row-${rowIndex}`}
                className="flex items-center gap-4 p-4"
              >
                {Array.from({ length: columns }).map((_, colIndex) => (
                  <Skeleton
                    key={`cell-${rowIndex}-${colIndex}`}
                    variant="text"
                    width={colIndex === 0 ? '15%' : colIndex === columns - 1 ? '10%' : '20%'}
                    height={14}
                    className="flex-shrink-0"
                  />
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }
);

SkeletonTable.displayName = 'SkeletonTable';

// Skeleton pour stats
export function SkeletonStats({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="card p-4">
          <div className="flex items-center justify-between mb-3">
            <Skeleton variant="circular" width={40} height={40} />
            <Skeleton variant="text" width={60} height={24} />
          </div>
          <Skeleton variant="text" width="50%" height={14} className="mb-2" />
          <Skeleton variant="text" width="30%" height={12} />
        </div>
      ))}
    </div>
  );
}

// Skeleton pour formulaire
export function SkeletonForm({ fields = 4 }: { fields?: number }) {
  return (
    <div className="space-y-6">
      {Array.from({ length: fields }).map((_, index) => (
        <div key={index} className="space-y-2">
          <Skeleton variant="text" width={100} height={14} />
          <Skeleton variant="rectangular" width="100%" height={42} />
        </div>
      ))}
      <div className="flex gap-3 pt-4">
        <Skeleton variant="rectangular" width={100} height={40} />
        <Skeleton variant="rectangular" width={80} height={40} />
      </div>
    </div>
  );
}

// Skeleton pour liste
export function SkeletonList({ items = 5 }: { items?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: items }).map((_, index) => (
        <div key={index} className="flex items-center gap-4 p-4 bg-dark-800/50 rounded-lg">
          <Skeleton variant="circular" width={40} height={40} />
          <div className="flex-1 space-y-2">
            <Skeleton variant="text" width="40%" height={16} />
            <Skeleton variant="text" width="60%" height={12} />
          </div>
          <Skeleton variant="rectangular" width={80} height={32} />
        </div>
      ))}
    </div>
  );
}
