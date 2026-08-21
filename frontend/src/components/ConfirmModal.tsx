import { motion, AnimatePresence } from 'framer-motion'
import { AlertTriangle, Trash2, X, Check } from 'lucide-react'

interface ConfirmModalProps {
  isOpen: boolean
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  variant?: 'danger' | 'warning' | 'info'
  onConfirm: () => void
  onCancel: () => void
}

export default function ConfirmModal({
  isOpen,
  title = 'Are you sure?',
  message,
  confirmText = 'Delete',
  cancelText = 'Cancel',
  variant = 'danger',
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  if (!isOpen) return null

  const isDanger = variant === 'danger'

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs">
        <motion.div
          initial={{ opacity: 0, scale: 0.94, y: 8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          className="w-full max-w-md card p-6 space-y-5 max-h-[90vh] overflow-y-auto"
        >
          {/* Header */}
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <div
                className={`w-11 h-11 rounded-[1.5rem] flex items-center justify-center flex-shrink-0 ${
                  isDanger
                    ? 'bg-red-500/10 border border-red-500/20 text-red-600'
                    : 'bg-[#1CB0F6]/15 border border-[#1CB0F6]/30 text-[#1CB0F6]'
                }`}
              >
                {isDanger ? <Trash2 size={20} /> : <AlertTriangle size={20} />}
              </div>
              <div>
                <h3 className="font-semibold text-lg text-text-primary leading-tight">
                  {title}
                </h3>
                <p className="text-xs font-medium text-text-muted mt-0.5">Confirmation Required</p>
              </div>
            </div>
            <button
              onClick={onCancel}
              className="p-2 rounded-full text-text-muted hover:text-text-primary hover:bg-black/5 transition-all cursor-pointer"
            >
              <X size={18} />
            </button>
          </div>

          {/* Message Content */}
          <div className="p-4 rounded-[1.5rem] bg-white/50 border border-border text-xs sm:text-sm font-medium text-text-secondary leading-relaxed">
            {message}
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              onClick={onCancel}
              className="btn-ghost text-xs cursor-pointer"
            >
              {cancelText}
            </button>

            <button
              onClick={onConfirm}
              className={`btn-primary px-5 py-2.5 text-xs flex items-center gap-2 ${
                isDanger
                  ? '!bg-error !text-white !border-error hover:!bg-red-600'
                  : '!bg-success !text-white !border-success hover:!bg-emerald-600'
              }`}
            >
              {isDanger ? <Trash2 size={14} /> : <Check size={14} />}
              <span>{confirmText}</span>
            </button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  )
}
