import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import { CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-react';

type ToastType = 'success' | 'error' | 'warning' | 'info';

interface Toast {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
}

interface ToastContextType {
  toasts: Toast[];
  addToast: (toast: Omit<Toast, 'id'>) => void;
  removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextType | null>(null);

const toastConfig: Record<ToastType, { icon: typeof CheckCircle; bgClass: string; iconClass: string }> = {
  success: {
    icon: CheckCircle,
    bgClass: 'bg-green-50 dark:bg-green-500/10 border-green-200 dark:border-green-500/20',
    iconClass: 'text-green-600 dark:text-green-400',
  },
  error: {
    icon: XCircle,
    bgClass: 'bg-red-50 dark:bg-red-500/10 border-red-200 dark:border-red-500/20',
    iconClass: 'text-red-600 dark:text-red-400',
  },
  warning: {
    icon: AlertTriangle,
    bgClass: 'bg-yellow-50 dark:bg-yellow-500/10 border-yellow-200 dark:border-yellow-500/20',
    iconClass: 'text-yellow-600 dark:text-yellow-400',
  },
  info: {
    icon: Info,
    bgClass: 'bg-oto-50 dark:bg-oto-500/10 border-oto-200 dark:border-oto-500/20',
    iconClass: 'text-oto-600 dark:text-oto-400',
  },
};

function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: () => void }) {
  const config = toastConfig[toast.type];
  const Icon = config.icon;

  return (
    <div
      className={`flex items-start gap-3 p-4 rounded-lg border shadow-lg ${config.bgClass} animate-in slide-in-from-right duration-300`}
    >
      <Icon size={20} className={`flex-shrink-0 mt-0.5 ${config.iconClass}`} />
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-gray-900 dark:text-white">{toast.title}</p>
        {toast.message && (
          <p className="mt-1 text-sm text-gray-600 dark:text-dark-300">{toast.message}</p>
        )}
      </div>
      <button
        onClick={onRemove}
        className="flex-shrink-0 p-1 rounded hover:bg-gray-200 dark:hover:bg-dark-700 transition-colors"
      >
        <X size={16} className="text-gray-400 dark:text-dark-400" />
      </button>
    </div>
  );
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((toast: Omit<Toast, 'id'>) => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { ...toast, id }]);

    // Auto-remove after 5 seconds
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast }}>
      {children}
      {/* Toast container */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-96">
        {toasts.map((toast) => (
          <ToastItem
            key={toast.id}
            toast={toast}
            onRemove={() => removeToast(toast.id)}
          />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}
