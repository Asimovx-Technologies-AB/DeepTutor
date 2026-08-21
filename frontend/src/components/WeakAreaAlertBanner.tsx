import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { AlertTriangle, MessageSquare, ArrowRight, X } from 'lucide-react'
import { progressApi } from '../services/api'

export default function WeakAreaAlertBanner() {
  const navigate = useNavigate()
  const [dismissed, setDismissed] = useState(false)

  const { data: analysis } = useQuery({
    queryKey: ['progress-analysis'],
    queryFn: () => progressApi.analysis().then((r) => r.data),
    staleTime: 30000,
  })

  if (dismissed || !analysis || !analysis.has_weakness) {
    return null
  }

  const weakTopic = analysis.primary_weakness
  const alert = analysis.alert

  const handleAskAI = () => {
    const prompt = `Can you explain the core concepts of '${weakTopic.subject}' in simple terms with examples? I need help improving my understanding.`
    navigate('/chat', { state: { initialPrompt: prompt } })
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -12 }}
        className="relative overflow-hidden rounded-[2rem] border border-[#4F46E5]/30 bg-gradient-to-r from-[#EEF2FF] via-[#FFFFFF] to-[#EEF2FF] p-5 sm:p-6 elevation-2 text-[#3C3C3C]"
      >
        {/* Decorative background glow */}
        <div className="absolute -right-10 -bottom-10 w-40 h-40 bg-[#4F46E5]/10 rounded-full blur-2xl pointer-events-none" />

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 relative z-10">
          <div className="flex items-start gap-3.5">
            <div className="w-10 h-10 rounded-[1.5rem] bg-[#4F46E5]/20 border border-[#4F46E5]/40 flex items-center justify-center text-[#4F46E5] flex-shrink-0 mt-0.5 elevation-1">
              <AlertTriangle size={20} />
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-black uppercase tracking-wider text-[#4F46E5] bg-[#4F46E5]/15 px-2.5 py-0.5 rounded-full border border-[#4F46E5]/30">
                  Automated Study Alert
                </span>
                <span className="text-xs font-extrabold text-[#777777]">
                  Mastery: <strong className="text-[#4F46E5] font-black">{weakTopic.score}%</strong>
                </span>
              </div>
              <h3 className="font-black text-base sm:text-lg text-[#3C3C3C] leading-snug">
                {alert.title}
              </h3>
              <p className="text-xs sm:text-sm font-medium text-[#777777] leading-relaxed max-w-2xl">
                {alert.message}
              </p>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2.5 flex-wrap self-end md:self-center flex-shrink-0">
            <button
              onClick={handleAskAI}
              className="flex items-center gap-2 text-xs font-black px-4 py-2.5 rounded-[1.25rem] bg-[#4F46E5] text-white hover:bg-[#4338CA] transition-all elevation-1 cursor-pointer active:scale-95"
            >
              <MessageSquare size={15} className="text-white" />
              <span>Ask AI Tutor for Help</span>
              <ArrowRight size={14} />
            </button>

            <button
              onClick={() => setDismissed(true)}
              className="p-2.5 rounded-[1.25rem] text-[#AFAFAF] hover:text-[#3C3C3C] hover:bg-black/5 transition-all cursor-pointer"
              title="Dismiss Alert"
            >
              <X size={18} />
            </button>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
