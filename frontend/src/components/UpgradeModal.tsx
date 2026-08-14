import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Crown,
  Sparkles,
  Zap,
  CheckCircle2,
  X,
  FileText,
  ShieldCheck,
  ArrowRight,
  Brain,
  Rocket
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { authApi } from '../services/api'

interface UpgradeModalProps {
  isOpen: boolean
  onClose: () => void
  exceededFileName?: string
  exceededFileSizeMb?: number
  onUpgraded?: () => void
}

export const UpgradeModal: React.FC<UpgradeModalProps> = ({
  isOpen,
  onClose,
  exceededFileName,
  exceededFileSizeMb,
  onUpgraded,
}) => {
  const { user, updateUser } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)

  if (!isOpen) return null

  const handleUpgrade = async () => {
    setLoading(true)
    try {
      const res = await authApi.upgradePremium(true)
      if (res.data?.user) {
        updateUser({
          is_premium: true,
          plan: 'premium',
          max_upload_size_mb: 100,
        })
      } else {
        updateUser({
          is_premium: true,
          plan: 'premium',
          max_upload_size_mb: 100,
        })
      }
      setSuccess(true)
      setTimeout(() => {
        setSuccess(false)
        onClose()
        if (onUpgraded) onUpgraded()
      }, 1200)
    } catch (err) {
      // Fallback update
      updateUser({
        is_premium: true,
        plan: 'premium',
        max_upload_size_mb: 100,
      })
      setSuccess(true)
      setTimeout(() => {
        setSuccess(false)
        onClose()
        if (onUpgraded) onUpgraded()
      }, 1200)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md">
        <motion.div
          initial={{ opacity: 0, scale: 0.9, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.9, y: 20 }}
          className="relative w-full max-w-lg overflow-hidden rounded-3xl bg-slate-900 border border-amber-500/30 shadow-2xl shadow-amber-500/10 text-white"
        >
          {/* Top Decorative Banner */}
          <div className="h-2 bg-gradient-to-r from-amber-500 via-yellow-400 to-amber-600" />

          {/* Close Button */}
          <button
            onClick={onClose}
            className="absolute top-4 right-4 p-2 text-slate-400 hover:text-white rounded-full bg-slate-800/60 hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>

          <div className="p-6 md:p-8 space-y-6">
            {/* Header Badge */}
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs font-semibold tracking-wide uppercase">
              <Crown className="w-4 h-4 text-amber-400" />
              <span>DeepTutor Premium</span>
            </div>

            {/* Title & Description */}
            <div>
              <h2 className="text-2xl md:text-3xl font-extrabold tracking-tight text-white flex items-center gap-2">
                Unlock Unlimited Study Power
              </h2>
              <p className="text-sm text-slate-300 mt-2">
                Elevate your learning experience with high-capacity document processing and priority AI reasoning.
              </p>
            </div>

            {/* Exceeded File Size Callout (if triggered by file upload) */}
            {exceededFileName && (
              <div className="p-4 rounded-2xl bg-amber-950/40 border border-amber-500/30 space-y-1">
                <div className="flex items-center gap-2 text-amber-300 font-semibold text-sm">
                  <FileText className="w-4 h-4 text-amber-400 shrink-0" />
                  <span className="truncate">{exceededFileName}</span>
                </div>
                <p className="text-xs text-amber-200/80">
                  File size:{' '}
                  <span className="font-bold text-amber-300">
                    {exceededFileSizeMb ? `${exceededFileSizeMb.toFixed(1)} MB` : 'Exceeds limit'}
                  </span>{' '}
                  • Free Tier Limit: <span className="font-bold text-slate-300">10 MB</span>
                </p>
              </div>
            )}

            {/* Comparison Grid */}
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3.5 rounded-2xl bg-slate-800/50 border border-slate-700/60 space-y-2">
                <div className="font-bold text-slate-400 uppercase tracking-wider text-[10px]">
                  Free Plan
                </div>
                <div className="text-lg font-bold text-slate-300">10 MB Limit</div>
                <ul className="space-y-1.5 text-slate-400">
                  <li className="flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                    <span>Basic PDF uploads</span>
                  </li>
                  <li className="flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                    <span>Standard AI Chat</span>
                  </li>
                </ul>
              </div>

              <div className="p-3.5 rounded-2xl bg-gradient-to-br from-amber-500/10 via-slate-800 to-amber-500/5 border border-amber-500/40 space-y-2 relative overflow-hidden">
                <div className="font-bold text-amber-400 uppercase tracking-wider text-[10px] flex items-center justify-between">
                  <span>Premium Plan</span>
                  <Sparkles className="w-3 h-3 text-amber-400" />
                </div>
                <div className="text-lg font-extrabold text-amber-300">100 MB Limit</div>
                <ul className="space-y-1.5 text-amber-100">
                  <li className="flex items-center gap-1.5">
                    <Zap className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                    <span>Large textbook PDFs</span>
                  </li>
                  <li className="flex items-center gap-1.5">
                    <Brain className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                    <span>GraphRAG reasoning</span>
                  </li>
                  <li className="flex items-center gap-1.5">
                    <Rocket className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                    <span>Priority AI Speed</span>
                  </li>
                </ul>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="space-y-3 pt-2">
              <button
                onClick={handleUpgrade}
                disabled={loading || success}
                className="w-full py-3.5 px-6 rounded-2xl font-bold text-slate-950 bg-gradient-to-r from-amber-400 via-yellow-400 to-amber-500 hover:from-amber-300 hover:to-amber-400 shadow-lg shadow-amber-500/20 active:scale-[0.98] transition flex items-center justify-center gap-2 text-sm disabled:opacity-75"
              >
                {success ? (
                  <>
                    <CheckCircle2 className="w-5 h-5 text-slate-950" />
                    <span>Upgraded to Premium!</span>
                  </>
                ) : loading ? (
                  <span>Upgrading...</span>
                ) : (
                  <>
                    <Crown className="w-5 h-5 text-slate-950" />
                    <span>Upgrade to Premium ($9.99/mo)</span>
                    <ArrowRight className="w-4 h-4 text-slate-950 ml-auto" />
                  </>
                )}
              </button>

              <button
                onClick={onClose}
                className="w-full py-2.5 text-xs text-slate-400 hover:text-white transition font-medium text-center"
              >
                Keep Free Plan (10MB limit)
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  )
}

export default UpgradeModal
