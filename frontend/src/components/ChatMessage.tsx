import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Bot, User, Copy, Check } from 'lucide-react'
import { useState } from 'react'
import { motion } from 'framer-motion'
import SourceCard, { type Source } from './SourceCard'

interface Props {
  role: 'user' | 'assistant'
  content: string
  isStreaming?: boolean
  sources?: Source[]
}

export default function ChatMessage({ role, content, isStreaming, sources }: Props) {
  const [copied, setCopied] = useState(false)
  const isAssistant = role === 'assistant'

  const handleCopy = () => {
    navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={`flex gap-4 group ${isAssistant ? '' : 'flex-row-reverse'}`}
    >
      {/* Avatar */}
      <div className={`w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0 mt-1 shadow-sm ${
        isAssistant
          ? 'bg-[#111111] text-white'
          : 'bg-[#27272a] text-white'
      }`}>
        {isAssistant ? (
          <Bot size={18} className="text-white" />
        ) : (
          <User size={18} className="text-white" />
        )}
      </div>

      {/* Content column */}
      <div className={`max-w-[85%] relative ${isAssistant ? '' : 'items-end'}`}>
        {/* Message bubble */}
        <div className={`rounded-3xl px-5 py-4 shadow-sm ${
          isAssistant
            ? 'bg-white border border-[#e4e4e7] rounded-tl-sm text-[#111111]'
            : 'bg-[#111111] text-white rounded-tr-sm shadow-md'
        }`}>
          {isAssistant ? (
            <div className="markdown-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {content}
              </ReactMarkdown>
              {isStreaming && (
                <span className="inline-flex gap-1.5 ml-1.5 align-middle">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </span>
              )}
            </div>
          ) : (
            <p className="text-white text-base font-medium leading-relaxed">{content}</p>
          )}
        </div>

        {/* Source cards — shown below assistant messages */}
        {isAssistant && sources && sources.length > 0 && !isStreaming && (
          <SourceCard sources={sources} />
        )}

        {/* Copy button */}
        {isAssistant && content && !isStreaming && (
          <button
            onClick={handleCopy}
            className="absolute -bottom-6 left-2 opacity-0 group-hover:opacity-100 transition-opacity text-slate-500 hover:text-indigo-600 flex items-center gap-1.5 text-xs font-semibold bg-white/80 backdrop-blur-sm px-2 py-0.5 rounded-lg border border-slate-200/60 shadow-sm"
          >
            {copied ? <><Check size={12} className="text-emerald-500" /> Copied</> : <><Copy size={12} /> Copy</>}
          </button>
        )}
      </div>
    </motion.div>
  )
}
