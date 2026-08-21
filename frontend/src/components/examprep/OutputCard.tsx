import React, { useState } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import { ChevronDown, Sparkles } from 'lucide-react'
import { cardHover, accordionVariants, staggerItem } from '../../utils/animations'

interface OutputCardProps {
  title: string
  badge?: string
  icon?: React.ReactNode
  children: React.ReactNode
  collapsible?: boolean
  defaultExpanded?: boolean
  className?: string
}

export default function OutputCard({
  title,
  badge,
  icon,
  children,
  collapsible = false,
  defaultExpanded = true,
  className = '',
}: OutputCardProps) {
  const shouldReduceMotion = useReducedMotion()
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)

  return (
    <motion.div
      variants={shouldReduceMotion ? undefined : staggerItem}
      whileHover={shouldReduceMotion ? undefined : { y: -4, boxShadow: '0 12px 30px -8px rgba(79, 70, 229, 0.12)' }}
      className={`rounded-3xl border border-slate-200 bg-white p-5 sm:p-6 shadow-xs transition-shadow ${className}`}
    >
      <div
        onClick={() => collapsible && setIsExpanded(!isExpanded)}
        className={`flex items-center justify-between ${
          collapsible ? 'cursor-pointer select-none' : ''
        }`}
      >
        <div className="flex items-center gap-3 pr-2">
          {icon && (
            <div className="w-8 h-8 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center flex-shrink-0 shadow-xs border border-indigo-100">
              {icon}
            </div>
          )}
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-black text-slate-800">{title}</h3>
              {badge && (
                <span className="px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-600 text-[10px] font-black uppercase tracking-wider border border-indigo-200">
                  {badge}
                </span>
              )}
            </div>
          </div>
        </div>

        {collapsible && (
          <motion.div
            animate={{ rotate: isExpanded ? 180 : 0 }}
            transition={{ duration: 0.25 }}
            className="w-7 h-7 rounded-xl bg-slate-100 text-slate-500 flex items-center justify-center flex-shrink-0"
          >
            <ChevronDown size={16} />
          </motion.div>
        )}
      </div>

      {collapsible ? (
        <AnimatePresence initial={false}>
          {isExpanded && (
            <motion.div
              variants={shouldReduceMotion ? undefined : accordionVariants}
              initial="collapsed"
              animate="open"
              exit="collapsed"
            >
              <div className="pt-4 mt-2 border-t border-slate-200/80">{children}</div>
            </motion.div>
          )}
        </AnimatePresence>
      ) : (
        <div className="pt-4">{children}</div>
      )}
    </motion.div>
  )
}
