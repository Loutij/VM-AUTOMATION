import { Sun, Moon, Monitor } from 'lucide-react';
import { useTheme } from '../../contexts/ThemeContext';

interface ThemeToggleProps {
  showLabel?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

const sizeClasses = {
  sm: 'w-8 h-8',
  md: 'w-10 h-10',
  lg: 'w-12 h-12',
};

const iconSizes = {
  sm: 16,
  md: 18,
  lg: 20,
};

export function ThemeToggle({ showLabel = false, size = 'md' }: ThemeToggleProps) {
  const { resolvedTheme, toggleTheme } = useTheme();

  const isDark = resolvedTheme === 'dark';

  return (
    <button
      onClick={toggleTheme}
      className={`
        ${sizeClasses[size]}
        flex items-center justify-center gap-2
        rounded-lg
        bg-light-200 dark:bg-dark-700
        hover:bg-light-300 dark:hover:bg-dark-600
        text-gray-700 dark:text-dark-300
        hover:text-gray-900 dark:hover:text-white
        transition-all duration-200
        focus:outline-none focus:ring-2 focus:ring-oto-500 focus:ring-offset-2 
        dark:focus:ring-offset-dark-900
      `}
      title={isDark ? 'Passer en mode clair' : 'Passer en mode sombre'}
      aria-label={isDark ? 'Passer en mode clair' : 'Passer en mode sombre'}
    >
      {isDark ? (
        <Sun size={iconSizes[size]} className="text-yellow-500" />
      ) : (
        <Moon size={iconSizes[size]} className="text-oto-600" />
      )}
      {showLabel && (
        <span className="text-sm font-medium">
          {isDark ? 'Clair' : 'Sombre'}
        </span>
      )}
    </button>
  );
}

// Version dropdown pour plus d'options
interface ThemeDropdownProps {
  align?: 'left' | 'right';
}

export function ThemeDropdown({ align = 'right' }: ThemeDropdownProps) {
  const { theme, setTheme, resolvedTheme } = useTheme();

  const options = [
    { value: 'light' as const, label: 'Clair', icon: Sun },
    { value: 'dark' as const, label: 'Sombre', icon: Moon },
    { value: 'system' as const, label: 'Système', icon: Monitor },
  ];

  return (
    <div className="relative group">
      <button
        className="
          p-2 rounded-lg
          bg-light-200 dark:bg-dark-700
          hover:bg-light-300 dark:hover:bg-dark-600
          text-gray-700 dark:text-dark-300
          hover:text-gray-900 dark:hover:text-white
          transition-all duration-200
        "
        title="Thème"
      >
        {resolvedTheme === 'dark' ? (
          <Moon size={18} />
        ) : (
          <Sun size={18} />
        )}
      </button>
      
      <div 
        className={`
          absolute top-full mt-2 ${align === 'right' ? 'right-0' : 'left-0'}
          w-40 py-2
          bg-white dark:bg-dark-700
          border border-light-300 dark:border-dark-600
          rounded-lg shadow-lg
          opacity-0 invisible group-hover:opacity-100 group-hover:visible
          transition-all duration-200
          z-50
        `}
      >
        {options.map((option) => {
          const Icon = option.icon;
          const isActive = theme === option.value;
          
          return (
            <button
              key={option.value}
              onClick={() => setTheme(option.value)}
              className={`
                w-full flex items-center gap-3 px-4 py-2 text-sm
                ${isActive 
                  ? 'bg-oto-50 dark:bg-oto-900/30 text-oto-600 dark:text-oto-400' 
                  : 'text-gray-700 dark:text-dark-300 hover:bg-light-100 dark:hover:bg-dark-600'
                }
                transition-colors
              `}
            >
              <Icon size={16} />
              <span>{option.label}</span>
              {isActive && (
                <span className="ml-auto w-2 h-2 rounded-full bg-oto-500" />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
