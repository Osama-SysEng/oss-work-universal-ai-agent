import { forwardRef, type InputHTMLAttributes, useId } from 'react'
import { cn } from '../../lib/utils'
import { X } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  helperText?: string
  leftIcon?: React.ReactNode
  rightIcon?: React.ReactNode
  clearable?: boolean
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, helperText, leftIcon, rightIcon, clearable, value, onChange, id: providedId, ...props }, ref) => {
    const generatedId = useId()
    const id = providedId || generatedId
    const errorId = id + '-error'
    const helperId = id + '-helper'

    return (
      <div className="w-full">
        {label && (
          <label htmlFor={id} className="label">
            {label}
          </label>
        )}
        <div className="relative">
          {props.leftIcon && (
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-dark-400 pointer-events-none">
              {leftIcon}
            </div>
          )}
          <input
            ref={ref}
            id={id}
            className="w-full px-4 py-3 rounded-xl bg-dark-800/50 border border-dark-600 text-slate-100 placeholder:text-dark-400 focus:border-oss-500 focus:ring-2 focus:ring-oss-500/20 focus:bg-dark-800 transition-all duration-200 disabled:bg-dark-900 disabled:cursor-not-allowed disabled:opacity-50 pr-10"
            ref={ref}
            aria-invalid={error ? 'true' : 'false'}
            aria-describedby={error ? errorId : helperText ? helperId : undefined}
            {...props}
            onChange={(e) => props.onChange?.(e)}
          />
          {props.leftIcon && (
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-dark-400 pointer-events-none">
              {leftIcon}
            </div>
          )}
          <AnimatePresence>
            {clearable && value && (
              <motion.button
                type="button"
                className="absolute right-3 top-1/2 -translate-y-1/2 text-dark-400 hover:text-slate-200 transition-colors p-1"
                onClick={(e) => {
                  e.preventDefault()
                  props.onChange?.({ target: { value: '' } } as React.ChangeEvent<HTMLInputElement>)
                }}
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
              >
                <X className="w-4 h-4" />
              </motion.button>
            )}
          </AnimatePresence>
          {rightIcon && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2 text-dark-400 pointer-events-none">
              {rightIcon}
            </div>
          )}
        </div>
        <AnimatePresence>
          {error && (
            <motion.p
              id={errorId}
              className="mt-1.5 text-sm text-red-400 flex items-center gap-1"
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
            >
              <svg className="w-3.5 h-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              {error}
            </motion.p>
          )}
          {!error && helperText && (
            <p id={helperId} className="mt-1.5 text-sm text-dark-400">
              {helperText}
            </p>
          )}
        </AnimatePresence>
      </div>
    )
  })
)

Input.displayName = 'Input'