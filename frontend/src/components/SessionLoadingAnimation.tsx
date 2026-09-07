import React, { useState, useEffect } from 'react'
import { BookOpen, Sparkles, Database, GraduationCap, Layers } from 'lucide-react'

interface SessionLoadingAnimationProps {
  sessionTitle?: string
  subject?: string
}

const LOADING_STEPS = [
  { text: 'Opening scholarly notebook workspace...', icon: BookOpen, subtext: 'Connecting to local SQLite database' },
  { text: 'Loading FTS5 full-text search index...', icon: Database, subtext: 'Preparing BM25 retrieval grounding' },
  { text: 'Synthesizing curriculum roadmap & topics...', icon: Layers, subtext: 'Extracting key concepts & difficulty levels' },
  { text: 'Initializing personal AI tutor space...', icon: GraduationCap, subtext: 'Configuring calibrated learning profile' },
]

export const SessionLoadingAnimation: React.FC<SessionLoadingAnimationProps> = ({
  sessionTitle,
  subject,
}) => {
  const [currentStepIndex, setCurrentStepIndex] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentStepIndex((prev) => (prev + 1) % LOADING_STEPS.length)
    }, 900)
    return () => clearInterval(interval)
  }, [])

  const CurrentIcon = LOADING_STEPS[currentStepIndex].icon

  return (
    <div className="flex flex-col items-center justify-center min-h-[420px] w-full p-8 rounded-3xl bg-gradient-to-b from-[#FCF9F8] via-[#F6F3F2]/80 to-[#FAF8F5] border border-[#E4E2E1] shadow-xs relative overflow-hidden select-none">
      {/* Background Decorative Academic Grids */}
      <div className="absolute inset-0 bg-[radial-gradient(#4E6053_1px,transparent_1px)] [background-size:24px_24px] opacity-10 pointer-events-none" />
      <div className="absolute -top-24 -left-24 w-64 h-64 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none animate-pulse" />
      <div className="absolute -bottom-24 -right-24 w-64 h-64 bg-amber-500/10 rounded-full blur-3xl pointer-events-none animate-pulse" />

      {/* Main Central Icon Container with Pulsing Ripple Rings */}
      <div className="relative mb-6 flex items-center justify-center">
        {/* Outer Pulsing Aura Rings */}
        <div className="absolute w-24 h-24 rounded-full bg-[#4E6053]/15 animate-ping duration-1000 opacity-60" />
        <div className="absolute w-32 h-32 rounded-full bg-[#775926]/10 animate-pulse duration-1500" />
        <div className="absolute w-20 h-20 rounded-2xl bg-white/90 border border-[#C3C8C1] shadow-md rotate-3 transition-transform duration-500" />
        
        {/* Core Glowing Icon Box */}
        <div className="relative w-20 h-20 rounded-2xl bg-gradient-to-br from-[#4E6053] to-[#394B3E] text-white flex items-center justify-center shadow-lg transform -rotate-3 transition-all duration-300">
          <CurrentIcon className="w-9 h-9 animate-bounce text-emerald-100" />
          <div className="absolute -top-1 -right-1 w-5 h-5 bg-amber-400 rounded-full flex items-center justify-center shadow-xs">
            <Sparkles className="w-3 h-3 text-amber-950 animate-spin" />
          </div>
        </div>
      </div>

      {/* Session Title & Subject Header */}
      <div className="text-center max-w-md mb-6 z-10">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#E7EFE9] border border-[#B8CCBB] text-[#394B3E] text-xs font-semibold tracking-wide uppercase mb-2">
          <Sparkles className="w-3.5 h-3.5 text-emerald-700" />
          {subject || 'Study Workspace'}
        </div>
        <h3 className="text-xl font-serif font-bold text-[#1B1C1C] truncate px-4">
          {sessionTitle || 'Switching Study Room...'}
        </h3>
      </div>

      {/* Animated Step Indicator */}
      <div className="flex items-center justify-center gap-2 mb-4 z-10">
        {LOADING_STEPS.map((step, idx) => (
          <div
            key={idx}
            className={`h-1.5 rounded-full transition-all duration-300 ${
              idx === currentStepIndex
                ? 'w-8 bg-[#4E6053] shadow-xs'
                : 'w-2 bg-[#C3C8C1] opacity-50'
            }`}
          />
        ))}
      </div>

      {/* Dynamic Status Label */}
      <div className="text-center z-10 min-h-[48px] flex flex-col items-center justify-center">
        <p className="text-sm font-medium text-[#1B1C1C] transition-all duration-300 animate-fade-in flex items-center gap-2">
          {LOADING_STEPS[currentStepIndex].text}
        </p>
        <p className="text-xs text-[#737873] mt-0.5 font-mono">
          {LOADING_STEPS[currentStepIndex].subtext}
        </p>
      </div>

      {/* Progress Shimmer Bar */}
      <div className="w-full max-w-xs h-1.5 bg-[#E4E2E1] rounded-full overflow-hidden mt-5 relative z-10">
        <div className="h-full bg-gradient-to-r from-[#4E6053] via-[#775926] to-[#4E6053] rounded-full w-full animate-pulse" />
      </div>

      {/* Skeleton Content Card Preview in Background */}
      <div className="w-full max-w-lg mt-8 p-4 bg-white/70 rounded-2xl border border-[#E4E2E1] space-y-3 z-10 opacity-70">
        <div className="flex items-center gap-3">
          <div className="w-6 h-6 rounded-full bg-[#E4E2E1] animate-pulse" />
          <div className="h-4 bg-[#E4E2E1] rounded-md w-1/3 animate-pulse" />
        </div>
        <div className="h-3 bg-[#F0EDED] rounded-md w-full animate-pulse" />
        <div className="h-3 bg-[#F0EDED] rounded-md w-4/5 animate-pulse" />
      </div>
    </div>
  )
}

export default SessionLoadingAnimation
