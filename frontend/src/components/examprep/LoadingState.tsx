import React, { useState, useEffect } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import { Brain, Sparkles, BookOpen, Layers } from 'lucide-react'
import { pulsingMascot } from '../../utils/animations'

const STATUS_STEPS = [
  'Reading and indexing your study material...',
  'Extracting key definitions and governing laws...',
  'Analyzing recurring questions & exam patterns...',
  'Structuring 5-minute notes & formula cheat sheets...',
  'Finalizing high-yield practice quiz questions...',
]

interface LoadingStateProps {
  customMessage?: string
}

export default function LoadingState({ customMessage }: LoadingStateProps) {
  const shouldReduceMotion = useReducedMotion()
  const [stepIndex, setStepIndex] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => {
      setStepIndex((prev) => (prev + 1) % STATUS_STEPS.length)
    }, 1800)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="py-12 px-4 max-w-xl mx-auto flex flex-col items-center justify-center text-center space-y-8">
      
      {/* ─── PULSING BRAIN / BOOK MASCOT ICON ─── */}
      <div className="relative">
        {/* Soft Radial Glow */}
        <motion.div
          animate={
            shouldReduceMotion
              ? undefined
              : {
                  scale: [1, 1.3, 1],
                  opacity: [0.35, 0.65, 0.35],
                }
          }
          transition={{ duration: 2.2, repeat: Infinity, ease: 'easeInOut' }}
          className="absolute -inset-4 bg-gradient-to-r from-[#F28A45]/30 to-[#0284C7]/30 rounded-full blur-xl pointer-events-none"
        />

        {/* Mascot Container */}
        <motion.div
          variants={shouldReduceMotion ? undefined : pulsingMascot}
          animate="pulse"
          className="relative w-20 h-20 rounded-3xl bg-gradient-to-br from-[#FFF0E4] to-white border-2 border-[#FED7AA] text-[#F28A45] flex items-center justify-center shadow-lg"
        >
          <Brain size={38} className="text-[#F28A45]" />
          <motion.div
            animate={{ rotate: [0, 360] }}
            transition={{ duration: 6, repeat: Infinity, ease: 'linear' }}
            className="absolute -top-1 -right-1 w-6 h-6 rounded-full bg-[#0284C7] text-white flex items-center justify-center shadow-xs"
          >
            <Sparkles size={12} />
          </motion.div>
        </motion.div>
      </div>

      {/* ─── CYCLING STATUS TEXT WITH ANIMATEPRESENCE ─── */}
      <div className="h-10 flex items-center justify-center">
        <AnimatePresence mode="wait">
          <motion.p
            key={customMessage || stepIndex}
            initial={{ opacity: 0, y: 8, filter: 'blur(2px)' }}
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            exit={{ opacity: 0, y: -8, filter: 'blur(2px)' }}
            transition={{ duration: 0.35 }}
            className="text-sm sm:text-base font-black text-[#20201D]"
          >
            {customMessage || STATUS_STEPS[stepIndex]}
          </motion.p>
        </AnimatePresence>
      </div>

      {/* ─── SHIMMER SKELETON LOADERS ─── */}
      <div className="w-full space-y-3 pt-2">
        <div className="h-5 w-4/5 mx-auto rounded-xl bg-gradient-to-r from-gray-200 via-gray-100 to-gray-200 animate-pulse" />
        <div className="h-4 w-full rounded-xl bg-gradient-to-r from-gray-200 via-gray-100 to-gray-200 animate-pulse delay-75" />
        <div className="h-4 w-2/3 mx-auto rounded-xl bg-gradient-to-r from-gray-200 via-gray-100 to-gray-200 animate-pulse delay-150" />
      </div>

    </div>
  )
}
