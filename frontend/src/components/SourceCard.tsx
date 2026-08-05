import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { FileText, ChevronDown, ChevronUp, ExternalLink, Star } from 'lucide-react'

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
  const color =
    pct >= 80 ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' :
    pct >= 60 ? 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20' :
                'text-slate-400 bg-white/5 border-white/10'
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${color}`}>
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
      className="mt-3 space-y-1.5"
    >
      {/* Header */}
      <div className="flex items-center gap-1.5">
        <FileText size={11} className="text-indigo-400" />
        <span className="text-[11px] font-semibold text-indigo-400 uppercase tracking-wider">
          Sources ({sources.length})
        </span>
      </div>

      {/* Source list */}
      {displayed.map((src, i) => (
        <div
          key={i}
          className="rounded-xl border border-[rgba(99,102,241,0.12)] bg-[rgba(15,15,26,0.6)] overflow-hidden"
        >
          {/* Source header */}
          <button
            onClick={() => setExpanded(expanded === i ? null : i)}
            className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-white/3 transition-colors"
          >
            <div className="w-6 h-6 rounded-lg bg-indigo-500/15 flex items-center justify-center flex-shrink-0">
              <FileText size={11} className="text-indigo-400" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[11px] font-semibold text-slate-300 truncate">{src.doc}</p>
              <p className="text-[10px] text-slate-600">Page {src.page}</p>
            </div>
            <ScoreBadge score={src.score} />
            {expanded === i ? (
              <ChevronUp size={12} className="text-slate-500 flex-shrink-0" />
            ) : (
              <ChevronDown size={12} className="text-slate-500 flex-shrink-0" />
            )}
          </button>

          {/* Expanded text */}
          <AnimatePresence>
            {expanded === i && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden"
              >
                <div className="px-3 pb-3 pt-0">
                  <div className="bg-[rgba(99,102,241,0.05)] border border-[rgba(99,102,241,0.1)] rounded-lg p-2.5">
                    <p className="text-[11px] text-slate-400 leading-relaxed">{src.text}</p>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      ))}

      {/* Show more */}
      {sources.length > 3 && (
        <button
          onClick={() => setShowAll(!showAll)}
          className="text-[11px] text-indigo-400 hover:text-indigo-300 transition-colors flex items-center gap-1 px-1"
        >
          {showAll ? <><ChevronUp size={11} /> Show less</> : <><ChevronDown size={11} /> {sources.length - 3} more source(s)</>}
        </button>
      )}
    </motion.div>
  )
}
