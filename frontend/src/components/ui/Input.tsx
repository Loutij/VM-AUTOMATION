import { forwardRef, type InputHTMLAttributes, type ReactNode } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, helperText, leftIcon, rightIcon, className = '', id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');

    return (
      <div className="space-y-1.5">
        {label && (
          <label htmlFor={inputId} className="block text-sm font-medium text-gray-700 dark:text-dark-200">
            {label}
            {props.required && <span className="text-red-500 ml-1">*</span>}
          </label>
        )}
        <div className="relative">
          {leftIcon && (
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-dark-400">
              {leftIcon}
            </div>
          )}
          <input
            ref={ref}
            id={inputId}
            className={`
              w-full px-4 py-2.5 
              bg-white dark:bg-dark-700 
              border rounded-lg 
              text-gray-900 dark:text-dark-100 
              placeholder-gray-400 dark:placeholder-dark-400 
              focus:outline-none focus:ring-2 focus:ring-oto-500 focus:border-transparent
              transition-all duration-200 
              disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-light-100 dark:disabled:bg-dark-800
              ${leftIcon ? 'pl-10' : ''}
              ${rightIcon ? 'pr-10' : ''}
              ${error 
                ? 'border-red-500 focus:ring-red-500' 
                : 'border-light-300 dark:border-dark-600 hover:border-oto-300 dark:hover:border-dark-500'
              }
              ${className}
            `}
            {...props}
          />
          {rightIcon && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-dark-400">
              {rightIcon}
            </div>
          )}
        </div>
        {error && <p className="text-sm text-red-500">{error}</p>}
        {helperText && !error && <p className="text-sm text-gray-500 dark:text-dark-400">{helperText}</p>}
      </div>
    );
  }
);

Input.displayName = 'Input';

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, helperText, className = '', id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');

    return (
      <div className="space-y-1.5">
        {label && (
          <label htmlFor={inputId} className="block text-sm font-medium text-gray-700 dark:text-dark-200">
            {label}
            {props.required && <span className="text-red-500 ml-1">*</span>}
          </label>
        )}
        <textarea
          ref={ref}
          id={inputId}
          className={`
            w-full px-4 py-2.5 
            bg-white dark:bg-dark-700 
            border rounded-lg 
            text-gray-900 dark:text-dark-100 
            placeholder-gray-400 dark:placeholder-dark-400 
            focus:outline-none focus:ring-2 focus:ring-oto-500 focus:border-transparent
            transition-all duration-200 
            disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-light-100 dark:disabled:bg-dark-800
            resize-none
            ${error 
              ? 'border-red-500 focus:ring-red-500' 
              : 'border-light-300 dark:border-dark-600 hover:border-oto-300 dark:hover:border-dark-500'
            }
            ${className}
          `}
          {...props}
        />
        {error && <p className="text-sm text-red-500">{error}</p>}
        {helperText && !error && <p className="text-sm text-gray-500 dark:text-dark-400">{helperText}</p>}
      </div>
    );
  }
);

Textarea.displayName = 'Textarea';
