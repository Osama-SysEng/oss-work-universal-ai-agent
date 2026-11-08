import { forwardRef, useRef, useEffect, useState, type ButtonHTMLAttributes } from 'react'
import { cn } from '../../lib/utils'
import { ChevronDown, X, Check } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { createPortal } from 'react-dom'

interface DropdownOption {
  value: string
  label: string
  icon?: React.ReactNode
  disabled?: boolean
  divider?: boolean
  danger?: boolean
}

interface DropdownProps {
  trigger: React.ReactNode
  options: DropdownOption[]
  onSelect?: (value: string) => void
  placeholder?: string
  value?: string
  className?: string
  disabled?: boolean
  align?: 'left' | 'right'
}

export function Dropdown({
  trigger,
  options,
  onSelect,
  placeholder,
  value,
  className,
  disabled,
  align = 'right',
}: DropdownProps) {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const [selectedValue, setSelectedValue] = useState(value)

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        triggerRef.current &&
        !triggerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleSelect = (optionValue: string) => {
    setSelectedValue(optionValue)
    onSelect?.(optionValue)
    setIsOpen(false)
  }

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      setIsOpen(false)
    }
  }

  const handleTriggerClick = () => {
    if (!disabled) {
      setIsOpen(!isOpen)
    }
  }

  const dropdownContent = (
    <motion.div
      ref={dropdownRef}
      className="absolute z-50 mt-2 min-w-[180px] card py-2 shadow-2xl animate-scale-in"
      style={{ right: align === 'right' ? 0 : 'auto', left: align === 'left' ? 0 : 'auto' }}
      initial={{ opacity: 0, scale: 0.95, y: -4 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95, y: -4 }}
      transition={{ type: 'spring', damping: 25, stiffness: 300 }}
      role="menu"
      onKeyDown={handleKeyDown}
    >
      {options.map((option, index) => {
        if (option.divider) {
          return <div key={`divider-${index}`} className="border-t border-dark-700 my-1" />
        }
        return (
          <motion.button
            key={option.value}
            role="menuitem"
            disabled={option.disabled}
            onClick={() => !option.disabled && handleSelect(option.value)}
            className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-left transition-colors hover:bg-dark-800 disabled:opacity-50 disabled:cursor-not-allowed rounded-none"
            onClick={() => !option.disabled && handleSelect(option.value)}
          >
            {option.icon && <span className="w-5 h-5 flex-shrink-0">{option.icon}</span>}
            <span className="flex-1 text-left">{option.label}</span>
          </motion.button>
        )
      })}
      {options.length === 0 && (
        <div className="px-4 py-4 text-center text-dark-400 text-sm">
          No options available
        </div>
      )}
    </motion.div>
  )

  const handleClickOutside = (event: MouseEvent) => {
    if (
      dropdownRef.current &&
      !dropdownRef.current.contains(event.target as Node) &&
      triggerRef.current &&
      !triggerRef.current.contains(event.target as Node)
    ) {
      setIsOpen(false)
    }
  }

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      document.addEventListener('keydown', handleKeyDown)
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen])

  const handleSelect = (optionValue: string) => {
    setSelectedValue(optionValue)
    onSelect?.(optionValue)
    setIsOpen(false)
  }

  return (
    <div className="relative inline-block" onKeyDown={handleKeyDown}>
      <button
        ref={triggerRef}
        type="button"
        onClick={handleTriggerClick}
        disabled={disabled}
        className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl font-medium transition-all duration-200 bg-dark-800 text-slate-100 hover:bg-dark-700 focus:outline-none focus:ring-2 focus:ring-oss-500/50 focus:ring-offset-2 focus:ring-offset-dark-950 border border-dark-600 disabled:opacity-50 disabled:cursor-not-allowed"
        onClick={handleTriggerClick}
        aria-haspopup="true"
        aria-expanded={isOpen}
      >
        {selectedValue
          ? options.find((o) => o.value === selectedValue)?.label || selectedValue
          : placeholder || 'Select...'}
        <ChevronDown className="w-4 h-4 transition-transform" />
      </button>

      <AnimatePresence>
        {isOpen && createPortal(dropdownContent, document.body)}
      </AnimatePresence>
    </div>
  )
})

Dropdown.displayName = 'Dropdown'