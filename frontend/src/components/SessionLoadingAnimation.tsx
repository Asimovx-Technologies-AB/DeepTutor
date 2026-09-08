import React, { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { BookOpen, Sparkles, FileText, Layers, Brain } from 'lucide-react'

interface SessionLoadingAnimationProps {
  sessionTitle?: string
  subject?: string
}

const LOADING_PHASES = [
  { label: 'Opening workspace', detail: 'Loading notebook memory and document index', icon: BookOpen },
  { label: 'Retrieving course context', detail: 'Grounding syllabus topics and formula references', icon: FileText },
  { label: 'Structuring curriculum map', detail: 'Extracting key concepts & difficulty levels', icon: Layers },
  { label: 'Preparing AI tutor', detail: 'Calibrating personalized study profile', icon: Brain },
]

export const SessionLoadingAnimation: React.FC<SessionLoadingAnimationProps> = ({
  sessionTitle,
  subject,
}) => {
  const [phaseIndex, setPhaseIndex] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => {
      setPhaseIndex((prev) => (prev + 1) % LOADING_PHASES.length)
    }, 1200)
    return () => clearInterval(interval)
  }, [])

  const currentPhase = LOADING_PHASES[phaseIndex]
  const PhaseIcon = currentPhase.icon

  return (
    <div className="flex flex-col items-center justify-center min-h-[380px] w-full max-w-xl mx-auto p-8 rounded-3xl bg-white border border-slate-200/90 shadow-sm relative overflow-hidden select-none font-sans">
      {/* Background Subtle Gradient Glow */}
      <div className="absolute inset-0 bg-radial from-indigo-50/40 via-transparent to-transparent pointer-events-none" />

      {/* Top Header & Subject Badge */}
      <div className="flex flex-col items-center text-center mb-7 z-10">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-indigo-50 border border-indigo-100 text-indigo-700 text-[11px] font-bold tracking-wide uppercase mb-2 shadow-2xs">
          <Sparkles size={12} className="text-indigo-600" />
          <span>{subject || 'Study Workspace'}</span>
        </div>

        <h3 className="text-lg font-serif font-bold text-slate-900 truncate max-w-md px-2">
          {sessionTitle || 'Loading Study Room...'}
        </h3>
      </div>

      {/* Center Scrolling Status Ticker */}
      <div className="w-full max-w-md bg-slate-50 border border-slate-200/80 rounded-2xl p-4 mb-6 z-10 relative overflow-hidden shadow-2xs">
        {/* Subtle Shimmer Overlay on Ticker */}
        <div className="flex items-center gap-3.5">
          <div className="w-10 h-10 rounded-xl bg-white border border-slate-200 text-indigo-600 flex items-center justify-center shrink-0 shadow-2xs">
            <PhaseIcon size={18} className="text-indigo-600" />
          </div>

          <div className="min-w-0 flex-1 h-11 relative overflow-hidden flex flex-col justify-center">
            <AnimatePresence mode="wait">
              <motion.div
                key={phaseIndex}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -12 }}
                transition={{ duration: 0.25, ease: 'easeInOut' }}
                className="flex flex-col"
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-slate-900 truncate">{currentPhase.label}</span>
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-indigo-600 animate-ping" />
                </div>
                <p className="text-[11px] text-slate-500 truncate mt-0.5 font-medium">
                  {currentPhase.detail}
                </p>
              </motion.div>
            </AnimatePresence>
          </div>
        </div>

        {/* Minimalist Linear Progress Bar */}
        <div className="w-full h-1 bg-slate-200/80 rounded-full overflow-hidden mt-3 relative">
          <motion.div
            className="h-full bg-indigo-600 rounded-full"
            initial={{ x: '-100%', width: '40%' }}
            animate={{ x: '250%' }}
            transition={{ repeat: Infinity, duration: 1.4, ease: 'easeInOut' }}
          />
        </div>
      </div>

      {/* Clean Skeleton Notebook Layout Preview */}
      <div className="w-full max-w-md bg-slate-50/50 rounded-2xl border border-slate-100 p-4 space-y-2.5 z-10">
        <div className="flex items-center gap-2.5">
          <div className="w-5 h-5 rounded-lg bg-slate-200 animate-pulse shrink-0" />
          <div className="h-3.5 bg-slate-200 rounded-md w-2/5 animate-pulse" />
        </div>
        <div className="space-y-1.5 pt-1">
          <div className="h-2.5 bg-slate-200/80 rounded w-full animate-pulse" />
          <div className="h-2.5 bg-slate-200/80 rounded w-4/5 animate-pulse" />
          <div className="h-2.5 bg-slate-200/60 rounded w-3/5 animate-pulse" />
        </div>
      </div>

      {/* Step Indicators */}
      <div className="flex items-center justify-center gap-1.5 mt-5 z-10">
        {LOADING_PHASES.map((_, idx) => (
          <div
            key={idx}
            className={`h-1.5 rounded-full transition-all duration-300 ${
              idx === phaseIndex ? 'w-6 bg-indigo-600' : 'w-1.5 bg-slate-200'
            }`}
          />
        ))}
      </div>
    </div>
  )
}

export default SessionLoadingAnimation
