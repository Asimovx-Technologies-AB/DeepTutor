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
      className="mt-4 space-y-2"
    >
      {/* Header */}
      <div className="flex items-center gap-2">
        <FileText size={15} className="text-indigo-600" />
        <span className="text-xs font-extrabold text-indigo-600 uppercase tracking-wider">
          Sources ({sources.length})
        </span>
      </div>

      {/* Source list */}
      {displayed.map((src, i) => (
        <div
          key={i}
          className="rounded-2xl border border-indigo-100 bg-white/90 shadow-sm overflow-hidden transition-all hover:border-indigo-200"
        >
          {/* Source header */}
          <button
            onClick={() => setExpanded(expanded === i ? null : i)}
            className="w-full flex items-center gap-3 px-3.5 py-2.5 text-left hover:bg-indigo-50/40 transition-colors"
          >
            <div className="w-8 h-8 rounded-xl bg-indigo-50 flex items-center justify-center flex-shrink-0">
              <FileText size={15} className="text-indigo-600" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-bold text-slate-800 truncate">{src.doc}</p>
              <p className="text-[11px] font-medium text-slate-500">Page {src.page}</p>
            </div>
            <ScoreBadge score={src.score} />
            {expanded === i ? (
              <ChevronUp size={15} className="text-slate-400 flex-shrink-0" />
            ) : (
              <ChevronDown size={15} className="text-slate-400 flex-shrink-0" />
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
                <div className="px-3.5 pb-3.5 pt-0">
                  <div className="bg-indigo-50/50 border border-indigo-100 rounded-xl p-3">
                    <p className="text-xs text-slate-700 leading-relaxed font-medium">{src.text}</p>
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
          className="text-xs font-bold text-indigo-600 hover:text-indigo-700 transition-colors flex items-center gap-1.5 px-1 py-1"
        >
          {showAll ? <><ChevronUp size={14} /> Show less</> : <><ChevronDown size={14} /> {sources.length - 3} more source(s)</>}
        </button>
      )}
    </motion.div>
  )
}
