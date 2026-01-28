import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { Loader2 } from 'lucide-react';

type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary: 'bg-oto-500 hover:bg-oto-600 active:bg-oto-700 text-white border-transparent shadow-sm hover:shadow-md',
  secondary: 'bg-transparent hover:bg-oto-50 dark:hover:bg-dark-700 text-oto-600 dark:text-oto-400 border-2 border-oto-500 dark:border-oto-400',
  danger: 'bg-red-500 hover:bg-red-600 active:bg-red-700 text-white border-transparent shadow-sm',
  ghost: 'bg-transparent hover:bg-light-200 dark:hover:bg-dark-700 text-gray-600 dark:text-dark-300 hover:text-gray-900 dark:hover:text-white border-transparent',
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'px-3 py-1.5 text-xs gap-1.5',
  md: 'px-4 py-2 text-sm gap-2',
  lg: 'px-6 py-3 text-base gap-2',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = 'primary',
      size = 'md',
      isLoading = false,
      leftIcon,
      rightIcon,
      children,
      disabled,
      className = '',
      ...props
    },
    ref
  ) => {
    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={`
          inline-flex items-center justify-center font-semibold rounded-lg border
          uppercase tracking-wide
          transition-all duration-200 
          focus:outline-none focus:ring-2 focus:ring-oto-500 focus:ring-offset-2 
          dark:focus:ring-offset-dark-900 focus:ring-offset-white
          disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none
          ${variantClasses[variant]}
          ${sizeClasses[size]}
          ${className}
        `}
        {...props}
      >
        {isLoading ? (
          <Loader2 size={size === 'sm' ? 14 : 18} className="animate-spin" />
        ) : (
          leftIcon
        )}
        {children}
        {!isLoading && rightIcon}
      </button>
    );
  }
);

Button.displayName = 'Button';
