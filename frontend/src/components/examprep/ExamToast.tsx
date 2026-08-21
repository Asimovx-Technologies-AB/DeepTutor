import React, { useEffect } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react'
import { toastVariants } from '../../utils/animations'

export interface ToastMessage {
  id: string
  type: 'success' | 'error' | 'info'
  title: string
  message: string
}

interface ExamToastProps {
  toasts: ToastMessage[]
  onDismiss: (id: string) => void
}

export default function ExamToast({ toasts, onDismiss }: ExamToastProps) {
  const shouldReduceMotion = useReducedMotion()

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-3 pointer-events-none max-w-sm w-full">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div
            key={t.id}
            variants={shouldReduceMotion ? undefined : toastVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            className={`pointer-events-auto p-4 rounded-2xl border shadow-xl flex items-start gap-3 bg-white ${
              t.type === 'success'
                ? 'border-[#10B981]/40 text-[#065F46]'
                : t.type === 'error'
                ? 'border-[#C85C52]/40 text-[#7A1E15]'
                : 'border-[#0284C7]/40 text-[#0369A1]'
            }`}
          >
            <div className="mt-0.5 flex-shrink-0">
              {t.type === 'success' ? (
                <CheckCircle2 size={18} className="text-[#10B981]" />
              ) : t.type === 'error' ? (
                <AlertCircle size={18} className="text-[#C85C52]" />
              ) : (
                <Info size={18} className="text-[#0284C7]" />
              )}
            </div>

            <div className="flex-1 min-w-0">
              <h4 className="text-xs font-black text-[#20201D] leading-none mb-1">{t.title}</h4>
              <p className="text-[11px] text-[#6F6B63] font-medium leading-relaxed">{t.message}</p>
            </div>

            <button
              onClick={() => onDismiss(t.id)}
              className="text-[#969188] hover:text-[#20201D] transition-colors p-0.5 -mt-0.5 -mr-0.5"
            >
              <X size={14} />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}
