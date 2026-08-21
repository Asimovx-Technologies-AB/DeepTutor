import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { FileText, ChevronDown, ChevronUp, Plus, Minus } from 'lucide-react'

export interface Source {
  doc: string
  page: number
  score: number
  text: string
}

interface Props {
  sources: Source[]
}

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  return (
    <span className="text-[11px] font-black px-2 py-0.5 rounded-full bg-[#D7FFB8] text-[#58CC02] border border-[#58CC02]/30">
      {pct}%
    </span>
  )
}

export default function SourceCard({ sources }: Props) {
  const [expanded, setExpanded] = useState<number | null>(null)
  const [showAll, setShowAll] = useState(false)

  const displayed = showAll ? sources : sources.slice(0, 3)

  if (!sources.length) return null

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-4 space-y-2 text-left"
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <div className="w-5 h-5 rounded-md bg-[#EEF2FF] text-[#4F46E5] flex items-center justify-center border border-[#4F46E5]/30">
          <FileText size={12} />
        </div>
        <span className="text-xs font-black text-[#3C3C3C]">
          Sources ({sources.length})
        </span>
      </div>

      {/* Source list */}
      <div className="space-y-2">
        {displayed.map((src, i) => (
          <div
            key={i}
            className="rounded-[1.5rem] border border-[#E2E8F0] bg-white elevation-1 overflow-hidden transition-all hover:border-[#4F46E5]/40"
          >
            {/* Source header */}
            <button
              onClick={() => setExpanded(expanded === i ? null : i)}
              className="w-full flex items-center gap-3 px-3.5 py-3 text-left hover:bg-[#FFFFFF] transition-colors cursor-pointer"
            >
              <div className="w-8 h-8 rounded-[1.25rem] bg-[#F0ECF7] text-[#A99BCB] border border-[#A99BCB]/30 flex items-center justify-center flex-shrink-0 elevation-1">
                <FileText size={15} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-black text-[#3C3C3C] truncate">{src.doc}</p>
                <p className="text-[11px] font-bold text-[#AFAFAF]">Page {src.page}</p>
              </div>
              <ScoreBadge score={src.score} />
              {expanded === i ? (
                <ChevronUp size={15} className="text-[#AFAFAF] flex-shrink-0" />
              ) : (
                <ChevronDown size={15} className="text-[#AFAFAF] flex-shrink-0" />
              )}
            </button>

            {/* Expanded text snippet */}
            <AnimatePresence>
              {expanded === i && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <div className="px-3.5 pb-3.5 pt-0">
                    <div className="bg-[#FFFFFF] border border-[#E2E8F0] rounded-[1.25rem] p-3">
                      <p className="text-xs text-[#3C3C3C] leading-relaxed font-medium">{src.text}</p>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ))}
      </div>

      {/* Show more button */}
      {sources.length > 3 && (
        <button
          onClick={() => setShowAll(!showAll)}
          className="text-xs font-black text-[#4F46E5] hover:text-[#4338CA] transition-colors flex items-center gap-1.5 pt-1 px-1 cursor-pointer"
        >
          {showAll ? (
            <><Minus size={13} /> Show less</>
          ) : (
            <><Plus size={13} /> {sources.length - 3} more source(s)</>
          )}
        </button>
      )}
    </motion.div>
  )
}
