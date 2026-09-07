import React, { type ButtonHTMLAttributes } from 'react'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'success'
  size?: 'sm' | 'md' | 'lg' | 'icon'
  isLoading?: boolean
  leftIcon?: React.ReactNode
  rightIcon?: React.ReactNode
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className = '',
      variant = 'primary',
      size = 'md',
      isLoading = false,
      leftIcon,
      rightIcon,
      children,
      disabled,
      ...props
    },
    ref
  ) => {
    // Base styles: pill shape, crisp typography, consistent transition
    const baseStyles =
      'inline-flex items-center justify-center font-extrabold rounded-[1.5rem] transition-all cursor-pointer active:scale-95 disabled:opacity-50 disabled:pointer-events-none'

    // Size variations
    const sizeStyles = {
      sm: 'px-4 py-2 text-xs gap-1.5',
      md: 'px-6 py-3 text-sm gap-2',
      lg: 'px-8 py-4 text-base gap-2.5',
      icon: 'w-10 h-10 p-0',
    }

    // Variant variations
    const variantStyles = {
      primary:
        'bg-blue-600 text-white shadow-md shadow-blue-500/20 hover:bg-blue-700 hover:shadow-lg hover:-translate-y-0.5',
      secondary:
        'bg-blue-50 text-blue-700 border border-blue-200 hover:bg-blue-100 shadow-sm',
      ghost:
        'bg-transparent text-slate-700 hover:text-slate-900 hover:bg-slate-100',
      danger:
        'bg-red-600 text-white shadow-md shadow-red-500/20 hover:bg-red-700 hover:shadow-lg',
      success:
        'bg-emerald-600 text-white shadow-md shadow-emerald-500/20 hover:bg-emerald-700 hover:shadow-lg',
    }

    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={`${baseStyles} ${sizeStyles[size]} ${variantStyles[variant]} ${className}`}
        {...props}
      >
        {isLoading ? (
          <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
        ) : leftIcon ? (
          <span className="flex-shrink-0">{leftIcon}</span>
        ) : null}
        
        {children && <span>{children}</span>}
        
        {!isLoading && rightIcon && (
          <span className="flex-shrink-0">{rightIcon}</span>
        )}
      </button>
    )
  }
)

Button.displayName = 'Button'
