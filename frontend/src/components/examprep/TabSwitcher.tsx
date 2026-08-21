import React from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { Zap, Table, FileText, Trophy } from 'lucide-react'

export type TabKey = 'smart_notes' | 'cheat_sheet' | 'important_qa' | 'practice_quiz'

interface TabOption {
  key: TabKey
  label: string
  icon: React.ReactNode
}

const TAB_OPTIONS: TabOption[] = [
  { key: 'smart_notes', label: 'Smart Notes', icon: <Zap size={14} /> },
  { key: 'cheat_sheet', label: 'Cheat Sheet', icon: <Table size={14} /> },
  { key: 'important_qa', label: 'Important Q&A', icon: <FileText size={14} /> },
  { key: 'practice_quiz', label: 'Practice Quiz', icon: <Trophy size={14} /> },
]

interface TabSwitcherProps {
  activeTab: TabKey
  onSelectTab: (tab: TabKey) => void
  className?: string
}

export default function TabSwitcher({ activeTab, onSelectTab, className = '' }: TabSwitcherProps) {
  const shouldReduceMotion = useReducedMotion()

  return (
    <div className={`flex flex-wrap items-center gap-1.5 p-1.5 bg-[#FAF8F3] rounded-2xl border border-[#E7E1D8] shadow-2xs ${className}`}>
      {TAB_OPTIONS.map((tab) => {
        const isActive = activeTab === tab.key

        return (
          <motion.button
            key={tab.key}
            onClick={() => onSelectTab(tab.key)}
            whileTap={shouldReduceMotion ? undefined : { scale: 0.95 }}
            className={`relative px-4 py-2 rounded-xl text-xs font-bold transition-colors cursor-pointer select-none flex items-center gap-2 z-10 ${
              isActive ? 'text-white' : 'text-[#6F6B63] hover:text-[#20201D]'
            }`}
          >
            {/* Sliding Pill Background with layoutId */}
            {isActive && (
              <motion.div
                layoutId="exam-tab-indicator"
                transition={
                  shouldReduceMotion
                    ? { duration: 0 }
                    : { type: 'spring', stiffness: 450, damping: 32 }
                }
                className="absolute inset-0 bg-[#F28A45] rounded-xl shadow-xs -z-10"
              />
            )}

            <span className="relative z-10">{tab.icon}</span>
            <span className="relative z-10 whitespace-nowrap">{tab.label}</span>
          </motion.button>
        )
      })}
    </div>
  )
}
