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
          exit={{ opacity: 0, scale: 0.94, y: 8 }}
          className="w-full max-w-md bg-[#FFFDF9] border border-[#E7E1D8] rounded-3xl p-6 shadow-2xl space-y-5 text-[#20201D]"
        >
          {/* Header */}
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <div
                className={`w-11 h-11 rounded-2xl flex items-center justify-center flex-shrink-0 ${
                  isDanger
                    ? 'bg-red-500/10 border border-red-500/20 text-red-600'
                    : 'bg-[#F28A45]/15 border border-[#F28A45]/30 text-[#F28A45]'
                }`}
              >
                {isDanger ? <Trash2 size={20} /> : <AlertTriangle size={20} />}
              </div>
              <div>
                <h3 className="font-black text-base sm:text-lg text-[#20201D] leading-tight">
                  {title}
                </h3>
                <p className="text-xs font-bold text-[#969188] mt-0.5">Confirmation Required</p>
              </div>
            </div>
            <button
              onClick={onCancel}
              className="p-2 rounded-xl text-[#969188] hover:text-[#20201D] hover:bg-black/5 transition-all cursor-pointer"
            >
              <X size={18} />
            </button>
          </div>

          {/* Message Content */}
          <div className="p-4 rounded-2xl bg-[#FAF8F3] border border-[#E7E1D8] text-xs sm:text-sm font-medium text-[#6F6B63] leading-relaxed">
            {message}
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              onClick={onCancel}
              className="px-4 py-2.5 rounded-xl border border-[#E7E1D8] text-xs font-black text-[#6F6B63] hover:bg-[#FAF8F3] transition-all cursor-pointer"
            >
              {cancelText}
            </button>

            <button
              onClick={onConfirm}
              className={`px-5 py-2.5 rounded-xl text-xs font-black text-white transition-all shadow-xs cursor-pointer active:scale-95 flex items-center gap-2 ${
                isDanger
                  ? 'bg-red-600 hover:bg-red-700'
                  : 'bg-[#F28A45] hover:bg-[#E07934]'
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
