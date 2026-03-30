interface VNCStatusBadgeProps {
  status: 'unknown' | 'checking' | 'available' | 'unavailable' | 'installing';
}

export function VNCStatusBadge({ status }: VNCStatusBadgeProps) {
  const config = {
    unknown: { label: 'VNC: ?', bg: 'bg-gray-100 dark:bg-dark-700', text: 'text-gray-600 dark:text-gray-400' },
    checking: { label: 'VNC: ...', bg: 'bg-yellow-50 dark:bg-yellow-900/20', text: 'text-yellow-600 dark:text-yellow-400' },
    available: { label: 'VNC', bg: 'bg-green-50 dark:bg-green-900/20', text: 'text-green-600 dark:text-green-400' },
    unavailable: { label: 'VNC: Off', bg: 'bg-red-50 dark:bg-red-900/20', text: 'text-red-600 dark:text-red-400' },
    installing: { label: 'VNC: Install...', bg: 'bg-blue-50 dark:bg-blue-900/20', text: 'text-blue-600 dark:text-blue-400' },
  };

  const { label, bg, text } = config[status];

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${bg} ${text}`}>
      {status === 'checking' || status === 'installing' ? (
        <svg className="animate-spin -ml-0.5 mr-1 h-3 w-3" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      ) : null}
      {label}
    </span>
  );
}
