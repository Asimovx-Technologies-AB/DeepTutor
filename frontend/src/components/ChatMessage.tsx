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
      className={`flex gap-3 group ${isAssistant ? '' : 'flex-row-reverse'}`}
    >
      {/* Avatar */}
      <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 mt-1 ${
        isAssistant
          ? 'bg-gradient-to-br from-indigo-500 to-violet-600 shadow-lg animate-pulse-glow'
          : 'bg-gradient-to-br from-slate-600 to-slate-700'
      }`}>
        {isAssistant ? (
          <Bot size={14} className="text-white" />
        ) : (
          <User size={14} className="text-white" />
        )}
      </div>

      {/* Content column */}
      <div className={`max-w-[78%] relative ${isAssistant ? '' : 'items-end'}`}>
        {/* Message bubble */}
        <div className={`rounded-2xl px-4 py-3 ${
          isAssistant
            ? 'glass border border-[rgba(99,102,241,0.15)] rounded-tl-sm'
            : 'bg-gradient-to-br from-indigo-600 to-violet-600 rounded-tr-sm shadow-lg'
        }`}>
          {isAssistant ? (
            <div className="markdown-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {content}
              </ReactMarkdown>
              {isStreaming && (
                <span className="inline-flex gap-1 ml-1 align-middle">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </span>
              )}
            </div>
          ) : (
            <p className="text-white text-sm leading-relaxed">{content}</p>
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
            className="absolute -bottom-5 left-1 opacity-0 group-hover:opacity-100 transition-opacity text-slate-600 hover:text-slate-400 flex items-center gap-1 text-[10px]"
          >
            {copied ? <><Check size={10} className="text-emerald-400" /> Copied</> : <><Copy size={10} /> Copy</>}
          </button>
        )}
      </div>
    </motion.div>
  )
}
