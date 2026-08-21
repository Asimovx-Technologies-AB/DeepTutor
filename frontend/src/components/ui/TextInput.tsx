import React, { type InputHTMLAttributes } from 'react'

export interface TextInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  leftIcon?: React.ReactNode
  rightIcon?: React.ReactNode
}

export const TextInput = React.forwardRef<HTMLInputElement, TextInputProps>(
  ({ className = '', label, error, leftIcon, rightIcon, id, ...props }, ref) => {
    // Generate a unique ID if a label is provided but no id is passed
    const inputId = id || (label ? `input-${label.toLowerCase().replace(/\s+/g, '-')}` : undefined)

    return (
      <div className="flex flex-col gap-1.5 w-full">
        {label && (
          <label htmlFor={inputId} className="text-xs font-bold text-text-primary pl-1">
            {label}
          </label>
        )}
        <div className="relative group">
          {leftIcon && (
            <div className="absolute left-4 top-1/2 -translate-y-1/2 text-text-muted group-focus-within:text-info transition-colors">
              {leftIcon}
            </div>
          )}
          <input
            ref={ref}
            id={inputId}
            className={`
              w-full py-3.5 text-sm font-bold bg-white text-text-primary placeholder-text-muted
              border rounded-[1.5rem] shadow-sm transition-all outline-none
              focus:ring-4
              ${leftIcon ? 'pl-11' : 'pl-5'}
              ${rightIcon ? 'pr-11' : 'pr-5'}
              ${
                error
                  ? 'border-error focus:border-error focus:ring-error/20'
                  : 'border-border focus:border-info focus:ring-info/20 hover:border-info/30'
              }
              ${className}
            `}
            {...props}
          />
          {rightIcon && (
            <div className="absolute right-4 top-1/2 -translate-y-1/2 text-text-muted">
              {rightIcon}
            </div>
          )}
        </div>
        {error && <span className="text-[11px] font-semibold text-error pl-1">{error}</span>}
      </div>
    )
  }
)

TextInput.displayName = 'TextInput'
