import { motion, AnimatePresence } from 'framer-motion'
import { AlertTriangle, Trash2, X, AlertCircle, Loader2 } from 'lucide-react'

export interface ConfirmModalProps {
  isOpen: boolean
  title?: string
  subtitle?: string
  message?: string
  itemName?: string
  warningNote?: string
  confirmText?: string
  cancelText?: string
  variant?: 'danger' | 'warning' | 'info'
  isLoading?: boolean
  onConfirm: () => void | Promise<void>
  onCancel: () => void
}

export default function ConfirmModal({
  isOpen,
  title = 'Delete Study Material?',
  subtitle,
  message,
  itemName,
  warningNote,
  confirmText = 'Delete Permanently',
  cancelText = 'Cancel',
  variant = 'danger',
  isLoading = false,
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  if (!isOpen) return null

  const isDanger = variant === 'danger'

  const description =
    subtitle ||
    message ||
    (itemName
      ? `This will permanently delete '${itemName}', including all associated AI study notes, flashcards, vector search indexes, and chat history. This action cannot be undone.`
      : 'This action will permanently delete this item and all associated AI study notes, flashcards, and chat history. This action cannot be undone.')

  const warning =
    warningNote ||
    'Permanent Data Removal: All extracted topics, quizzes, and practice records will be wiped.'

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
          {/* Backdrop Blur Overlay */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={isLoading ? undefined : onCancel}
            className="fixed inset-0 bg-black/45 backdrop-blur-md"
          />

          {/* Modal Container */}
          <motion.div
            initial={{ opacity: 0, scale: 0.92, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.94, y: 8 }}
            transition={{ type: 'spring', damping: 25, stiffness: 350 }}
            className="relative w-full max-w-md bg-white rounded-[28px] shadow-[0_25px_60px_-15px_rgba(0,0,0,0.2)] border border-slate-100 overflow-hidden p-6 sm:p-8 flex flex-col items-center text-center z-10"
          >
            {/* Top-Right Close Button */}
            <button
              aria-label="Close modal"
              disabled={isLoading}
              onClick={onCancel}
              className="absolute top-4 right-4 text-slate-400 hover:text-slate-700 hover:bg-slate-100 p-2 rounded-full transition-colors cursor-pointer disabled:opacity-50"
            >
              <X size={18} />
            </button>

            {/* Centered Soft Icon Container */}
            <div
              className={`w-16 h-16 rounded-full flex items-center justify-center mb-5 ring-8 transition-transform ${
                isDanger
                  ? 'bg-rose-50 text-rose-600 border border-rose-100 ring-rose-50/60'
                  : 'bg-amber-50 text-amber-600 border border-amber-100 ring-amber-50/60'
              }`}
            >
              {isDanger ? <Trash2 size={26} className="stroke-[2.2]" /> : <AlertTriangle size={26} className="stroke-[2.2]" />}
            </div>

            {/* Typography */}
            <h3 className="text-xl sm:text-2xl font-black text-[#2D2D2D] tracking-tight mb-2">
              {title}
            </h3>
            <p className="text-sm font-medium text-slate-500 mb-5 max-w-sm leading-relaxed">
              {description}
            </p>

            {/* Warning Callout Box */}
            <div className="w-full bg-rose-50/70 p-3.5 sm:p-4 rounded-2xl border border-rose-200/60 mb-6 flex items-start gap-3 text-left">
              <AlertCircle size={18} className="text-rose-600 shrink-0 mt-0.5" />
              <p className="text-xs font-semibold text-rose-900 leading-relaxed">
                {warning}
              </p>
            </div>

            {/* Action Buttons */}
            <div className="w-full flex flex-col-reverse sm:flex-row gap-3">
              <button
                type="button"
                disabled={isLoading}
                onClick={onCancel}
                className="w-full sm:w-1/2 py-3.5 px-5 rounded-2xl border border-slate-200 text-slate-700 font-bold text-sm hover:bg-slate-50 hover:border-slate-300 transition-all cursor-pointer disabled:opacity-50"
              >
                {cancelText}
              </button>

              <button
                type="button"
                disabled={isLoading}
                onClick={onConfirm}
                className={`w-full sm:w-1/2 py-3.5 px-5 rounded-2xl font-bold text-sm text-white shadow-lg transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 ${
                  isDanger
                    ? 'bg-gradient-to-r from-rose-600 to-red-600 shadow-rose-600/25 hover:shadow-rose-600/40 hover:-translate-y-0.5'
                    : 'bg-gradient-to-r from-amber-600 to-yellow-600 shadow-amber-600/25 hover:shadow-amber-600/40 hover:-translate-y-0.5'
                }`}
              >
                {isLoading ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  isDanger && <Trash2 size={16} />
                )}
                <span>{isLoading ? 'Deleting...' : confirmText}</span>
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )
}
