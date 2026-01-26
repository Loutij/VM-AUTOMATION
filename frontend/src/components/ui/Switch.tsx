import { forwardRef, type InputHTMLAttributes } from 'react';

interface SwitchProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type' | 'onChange'> {
  label?: string;
  description?: string;
  checked?: boolean;
  onChange?: (checked: boolean) => void;
}

export const Switch = forwardRef<HTMLInputElement, SwitchProps>(
  ({ label, description, checked = false, onChange, disabled, id, className = '', ...props }, ref) => {
    const switchId = id || label?.toLowerCase().replace(/\s+/g, '-');

    const handleChange = () => {
      if (!disabled && onChange) {
        onChange(!checked);
      }
    };

    return (
      <div className={`flex items-center justify-between ${className}`}>
        {(label || description) && (
          <div className="flex-1 pr-4">
            {label && (
              <label
                htmlFor={switchId}
                className={`block text-sm font-medium ${disabled ? 'text-dark-500' : 'text-dark-100'} cursor-pointer`}
              >
                {label}
              </label>
            )}
            {description && (
              <p className={`text-sm ${disabled ? 'text-dark-600' : 'text-dark-400'} mt-0.5`}>
                {description}
              </p>
            )}
          </div>
        )}
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          disabled={disabled}
          onClick={handleChange}
          className={`
            relative inline-flex h-6 w-11 flex-shrink-0 rounded-full border-2 border-transparent
            transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 
            focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-dark-900
            ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}
            ${checked ? 'bg-primary-600' : 'bg-dark-600'}
          `}
        >
          <span
            aria-hidden="true"
            className={`
              pointer-events-none inline-block h-5 w-5 transform rounded-full
              bg-white shadow ring-0 transition duration-200 ease-in-out
              ${checked ? 'translate-x-5' : 'translate-x-0'}
            `}
          />
        </button>
        <input
          ref={ref}
          id={switchId}
          type="checkbox"
          checked={checked}
          onChange={() => onChange?.(!checked)}
          disabled={disabled}
          className="sr-only"
          {...props}
        />
      </div>
    );
  }
);

Switch.displayName = 'Switch';
