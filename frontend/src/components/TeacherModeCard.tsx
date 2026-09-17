import React, { useState } from 'react'
import { motion } from 'framer-motion'
import { Lightbulb, CheckCircle2, HelpCircle, ArrowRight, Sparkles, BookOpen, SkipForward } from 'lucide-react'

export interface CheckpointOption {
  id: string
  label: string
  text: string
}

export interface CheckpointData {
  question: string
  options: CheckpointOption[]
}

interface TeacherModeCardProps {
  checkpoint: CheckpointData
  onSelectOption: (optionText: string) => void
  onActionClick?: (action: string) => void
  disabled?: boolean
}

export function parseCheckpointFromMarkdown(content: string): {
  beforeText: string
  checkpoint: CheckpointData | null
} {
  const marker = '### 💡 Interactive Checkpoint'
  if (!content.includes(marker)) {
    return { beforeText: content, checkpoint: null }
  }

  const parts = content.split(marker)
  const beforeText = parts[0].trim()
  const checkpointPart = parts[1].trim()

  const lines = checkpointPart.split('\n').map((l) => l.trim()).filter(Boolean)
  const options: CheckpointOption[] = []
  const questionLines: string[] = []

  const optionRegex = /^([A-D])\.\s*(.+)$/

  for (const line of lines) {
    const match = line.match(optionRegex)
    if (match) {
      options.push({
        id: match[1],
        label: `Option ${match[1]}`,
        text: match[2].trim(),
      })
    } else if (options.length === 0) {
      questionLines.push(line)
    }
  }

  if (options.length >= 2) {
    return {
      beforeText,
      checkpoint: {
        question: questionLines.join(' '),
        options,
      },
    }
  }

  return { beforeText: content, checkpoint: null }
}

export const TeacherModeCard: React.FC<TeacherModeCardProps> = ({
  checkpoint,
  onSelectOption,
  onActionClick,
  disabled = false,
}) => {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [hasSubmitted, setHasSubmitted] = useState(false)

  const handleSelect = (opt: CheckpointOption) => {
    if (disabled || hasSubmitted) return
    setSelectedId(opt.id)
  }

  const handleSubmit = () => {
    if (!selectedId || disabled || hasSubmitted) return
    const opt = checkpoint.options.find((o) => o.id === selectedId)
    if (opt) {
      setHasSubmitted(true)
      onSelectOption(opt.id)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="mt-5 rounded-2xl border border-brand-primary/25 bg-gradient-to-br from-brand-primary-soft/40 via-white to-brand-primary-soft/20 p-5 shadow-md"
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold bg-brand-primary text-white shadow-xs">
          <Lightbulb size={13} className="text-amber-200" />
          <span>Interactive Checkpoint</span>
        </div>
        <span className="text-[11px] font-medium text-text-muted">
          Select the best answer to proceed
        </span>
      </div>

      {/* Question */}
      <p className="text-sm font-semibold text-text-primary mb-4 leading-relaxed">
        {checkpoint.question}
      </p>

      {/* Options */}
      <div className="space-y-2 mb-4">
        {checkpoint.options.map((opt) => {
          const isSelected = selectedId === opt.id
          return (
            <button
              key={opt.id}
              type="button"
              disabled={disabled || hasSubmitted}
              onClick={() => handleSelect(opt)}
              className={`w-full text-left p-3 rounded-xl border transition-all duration-150 flex items-start gap-3 cursor-pointer ${isSelected
                  ? 'border-brand-primary bg-brand-primary-soft text-brand-primary font-semibold shadow-xs ring-1 ring-brand-primary/30'
                  : 'border-border bg-white/80 hover:bg-brand-primary-soft/40 hover:border-brand-primary/40 text-text-primary'
                }`}
            >
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold transition-colors ${isSelected
                    ? 'bg-brand-primary text-white'
                    : 'bg-brand-primary/10 text-brand-primary'
                  }`}
              >
                {opt.id}
              </div>
              <span className="text-xs sm:text-sm leading-snug pt-0.5">{opt.text}</span>
            </button>
          )
        })}
      </div>

      {/* Submit Button */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-brand-primary/15">
        <button
          type="button"
          disabled={!selectedId || disabled || hasSubmitted}
          onClick={handleSubmit}
          className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all duration-150 shadow-sm ${selectedId && !hasSubmitted && !disabled
              ? 'bg-brand-primary text-white hover:bg-brand-primary/90 cursor-pointer shadow-md'
              : 'bg-border/60 text-text-muted cursor-not-allowed'
            }`}
        >
          <span>Submit Answer</span>
          <ArrowRight size={13} />
        </button>

        {/* Quick Teacher Actions */}
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => onActionClick?.('Explain with an analogy')}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold text-text-secondary bg-white hover:bg-brand-primary-soft border border-border transition-colors cursor-pointer"
          >
            <Sparkles size={11} className="text-amber-500" />
            <span>Analogy</span>
          </button>
          <button
            type="button"
            onClick={() => onActionClick?.('Explain this simpler')}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold text-text-secondary bg-white hover:bg-brand-primary-soft border border-border transition-colors cursor-pointer"
          >
            <BookOpen size={11} className="text-indigo-500" />
            <span>Simpler</span>
          </button>
          <button
            type="button"
            onClick={() => onActionClick?.('I have a doubt about this')}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold text-text-secondary bg-white hover:bg-brand-primary-soft border border-border transition-colors cursor-pointer"
          >
            <HelpCircle size={11} className="text-teal-500" />
            <span>Doubt</span>
          </button>
          <button
            type="button"
            onClick={() => onActionClick?.('Skip this concept')}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold text-text-muted bg-white hover:bg-border/50 border border-border transition-colors cursor-pointer"
          >
            <SkipForward size={11} />
            <span>Skip</span>
          </button>
        </div>
      </div>
    </motion.div>
  )
}

export default TeacherModeCard
