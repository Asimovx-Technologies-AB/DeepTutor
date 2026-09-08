import React from 'react'
import { Sparkles } from 'lucide-react'

interface SessionLoadingAnimationProps {
  sessionTitle?: string
  subject?: string
}

export const SessionLoadingAnimation: React.FC<SessionLoadingAnimationProps> = ({
  sessionTitle,
  subject,
}) => {
  return (
    <div className="flex flex-col items-center justify-center p-6 w-full max-w-sm mx-auto select-none">
      {/* Subject Pill */}
      <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-indigo-50 border border-indigo-100 text-indigo-600 text-xs font-bold uppercase tracking-wider mb-2.5">
        <Sparkles className="w-3.5 h-3.5 text-indigo-600 animate-spin" />
        {subject || 'Study Workspace'}
      </div>

      <h3 className="text-base font-bold text-slate-800 tracking-tight text-center mb-4 truncate max-w-xs">
        {sessionTitle || 'Loading Workspace...'}
      </h3>

      {/* Infinite Scrolling Line Progress Bar */}
      <div className="w-full max-w-[220px] h-1.5 bg-slate-100 rounded-full overflow-hidden relative border border-slate-200/80">
        <div className="absolute inset-y-0 h-full w-1/2 rounded-full bg-gradient-to-r from-transparent via-indigo-600 to-transparent animate-[scrolling_1.1s_infinite_linear]" />
      </div>

      <p className="text-xs text-slate-400 font-medium mt-2.5 animate-pulse">
        Connecting workspace...
      </p>

      <style>{`
        @keyframes scrolling {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(200%); }
        }
      `}</style>
    </div>
  )
}

export default SessionLoadingAnimation

