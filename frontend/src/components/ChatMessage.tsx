import React, { useState, memo, useDeferredValue } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import { Bot, User, Copy, Check } from 'lucide-react'
import { motion } from 'framer-motion'
import SourceCard, { type Source } from './SourceCard'

interface Props {
  role: 'user' | 'assistant'
  content: string
  isStreaming?: boolean
  sources?: Source[]
  grounding?: {
    grounding_score?: number
    formatted_badge?: string
    verified?: boolean
  }
}

const ChatMessageComponent = ({ role, content, isStreaming, sources, grounding }: Props) => {
  const [copied, setCopied] = useState(false)
  const isAssistant = role === 'assistant'
  
  // Use React 19 deferred value during streaming so UI thread stays responsive to scrolling and typing
  const deferredContent = useDeferredValue(content)
  const displayContent = isStreaming ? deferredContent : content

  const handleCopy = () => {
    navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={`flex gap-4 group ${isAssistant ? '' : 'flex-row-reverse'}`}
    >
      {/* Avatar */}
      <div className={`w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0 mt-1 shadow-2xs ${
        isAssistant
          ? 'bg-[#FFF0E4] text-[#F28A45] border border-[#F28A45]/30'
          : 'bg-[#20201D] text-white'
      }`}>
        {isAssistant ? (
          <Bot size={18} className="text-[#F28A45]" />
        ) : (
          <User size={18} className="text-white" />
        )}
      </div>

      {/* Content column */}
      <div className={`max-w-[85%] relative ${isAssistant ? '' : 'items-end'}`}>
        {/* Message bubble */}
        <div className={`rounded-3xl px-5 py-4 shadow-2xs ${
          isAssistant
            ? 'bg-white border border-[#E7E1D8] rounded-tl-sm text-[#20201D]'
            : 'bg-[#F28A45] text-white rounded-tr-sm shadow-xs font-semibold'
        }`}>
          {isAssistant ? (
            <div className="markdown-content">
              {/* Grounding Badge (only for substantive answers) */}
              {grounding && grounding.formatted_badge && !content.includes("Topic Not Found") && (
                <div className="mb-2 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-extrabold bg-[#EBF6EE] text-[#4F8A68] border border-[#4F8A68]/30">
                  <span>{grounding.formatted_badge}</span>
                </div>
              )}
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkMath]}
                rehypePlugins={[rehypeKatex]}
              >
                {displayContent}
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
            <p className="text-white text-base font-semibold leading-relaxed">{content}</p>
          )}
        </div>

        {/* Source cards — shown below assistant messages when not a missing topic notice */}
        {isAssistant && sources && sources.length > 0 && !isStreaming && !content.includes("Topic Not Found") && (
          <SourceCard sources={sources} />
        )}

        {/* Copy button */}
        {isAssistant && content && !isStreaming && (
          <button
            onClick={handleCopy}
            className="absolute -bottom-6 left-2 opacity-0 group-hover:opacity-100 transition-opacity text-[#969188] hover:text-[#F28A45] flex items-center gap-1.5 text-xs font-bold bg-white/90 backdrop-blur-sm px-2 py-0.5 rounded-lg border border-[#E7E1D8] shadow-2xs cursor-pointer"
          >
            {copied ? <><Check size={12} className="text-[#4F8A68]" /> Copied</> : <><Copy size={12} /> Copy</>}
          </button>
        )}
      </div>
    </motion.div>
  )
}

export default memo(ChatMessageComponent, (prevProps, nextProps) => {
  // Only re-render if streaming state or content or sources changed
  if (prevProps.isStreaming !== nextProps.isStreaming) return false
  if (prevProps.content !== nextProps.content) return false
  if (prevProps.sources !== nextProps.sources) return false
  if (prevProps.grounding !== nextProps.grounding) return false
  return true
})
