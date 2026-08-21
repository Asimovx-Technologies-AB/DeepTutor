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
                ? 'border-emerald-200 text-emerald-800'
                : t.type === 'error'
                ? 'border-rose-200 text-rose-800'
                : 'border-indigo-200 text-indigo-800'
            }`}
          >
            <div className="mt-0.5 flex-shrink-0">
              {t.type === 'success' ? (
                <CheckCircle2 size={18} className="text-emerald-500" />
              ) : t.type === 'error' ? (
                <AlertCircle size={18} className="text-rose-500" />
              ) : (
                <Info size={18} className="text-indigo-600" />
              )}
            </div>

            <div className="flex-1 min-w-0">
              <h4 className="text-xs font-black text-slate-800 leading-none mb-1">{t.title}</h4>
              <p className="text-[11px] text-slate-500 font-medium leading-relaxed">{t.message}</p>
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
