import { forwardRef, type SelectHTMLAttributes } from 'react';
import { ChevronDown } from 'lucide-react';

interface Option {
  value: string;
  label: string;
  disabled?: boolean;
}

interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'children'> {
  label?: string;
  error?: string;
  helperText?: string;
  options: Option[];
  placeholder?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, helperText, options, placeholder, className = '', id, ...props }, ref) => {
    const selectId = id || label?.toLowerCase().replace(/\s+/g, '-');

    return (
      <div className="space-y-1.5">
        {label && (
          <label htmlFor={selectId} className="block text-sm font-medium text-gray-700 dark:text-dark-200">
            {label}
            {props.required && <span className="text-red-500 ml-1">*</span>}
          </label>
        )}
        <div className="relative">
          <select
            ref={ref}
            id={selectId}
            className={`
              w-full px-4 py-2.5 pr-10 
              bg-white dark:bg-dark-700 
              border rounded-lg 
              text-gray-900 dark:text-dark-100 
              focus:outline-none focus:ring-2 focus:ring-oto-500 focus:border-transparent
              transition-all duration-200 
              disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-light-100 dark:disabled:bg-dark-800
              appearance-none cursor-pointer
              ${error 
                ? 'border-red-500 focus:ring-red-500' 
                : 'border-light-300 dark:border-dark-600 hover:border-oto-300 dark:hover:border-dark-500'
              }
              ${className}
            `}
            {...props}
          >
            {placeholder && (
              <option value="" disabled className="text-gray-400 dark:text-dark-400">
                {placeholder}
              </option>
            )}
            {options.map((option) => (
              <option key={option.value} value={option.value} disabled={option.disabled}>
                {option.label}
              </option>
            ))}
          </select>
          <ChevronDown
            size={18}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-dark-400 pointer-events-none"
          />
        </div>
        {error && <p className="text-sm text-red-500">{error}</p>}
        {helperText && !error && <p className="text-sm text-gray-500 dark:text-dark-400">{helperText}</p>}
      </div>
    );
  }
);

Select.displayName = 'Select';
