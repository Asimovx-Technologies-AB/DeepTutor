import React, { useState, memo, useDeferredValue } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import { Bot, User, Copy, Check } from 'lucide-react'
import { motion } from 'framer-motion'
import SourceCard, { type Source } from './SourceCard'
import MermaidDiagram from './MermaidDiagram'

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
      <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 mt-1 elevation-1 ${
        isAssistant
          ? 'bg-brand-primary-soft text-brand-primary border border-brand-primary/20'
          : 'bg-brand-primary text-white'
      }`}>
        {isAssistant ? (
          <Bot size={18} className="text-brand-primary" />
        ) : (
          <User size={18} className="text-white" />
        )}
      </div>

      {/* Content column */}
      <div className={`max-w-[85%] relative ${isAssistant ? '' : 'items-end'}`}>
        {/* Message bubble */}
        <div className={`px-4 py-2 ${
          isAssistant
            ? content.includes("Topic Not Found") 
              ? 'bg-warning-soft border border-warning/40 rounded-[2rem] rounded-tl-sm text-text-primary px-5 py-4'
              : 'text-text-primary'
            : 'bg-brand-primary text-white rounded-[2rem] rounded-tr-sm shadow-sm px-5 py-3 font-medium'
        }`}>
          {isAssistant ? (
            <div className="markdown-content">
              {/* Grounding Badge (only for substantive answers) */}
              {grounding && grounding.formatted_badge && !content.includes("Topic Not Found") && (
                <div className="mb-2 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-success-soft text-success border border-success/30">
                  <span>{grounding.formatted_badge}</span>
                </div>
              )}
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkMath]}
                rehypePlugins={[rehypeKatex]}
                components={{
                  code({ node, className, children, ...props }: any) {
                    const match = /language-(\w+)/.exec(className || '')
                    const language = match ? match[1] : ''
                    const codeStr = String(children).replace(/\n$/, '')
                    if (language === 'mermaid') {
                      return <MermaidDiagram chart={codeStr} />
                    }
                    return (
                      <code className={className} {...props}>
                        {children}
                      </code>
                    )
                  },
                }}
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
            className="absolute -bottom-6 left-2 opacity-0 group-hover:opacity-100 transition-opacity text-text-muted hover:text-brand-primary flex items-center gap-1.5 text-xs font-semibold bg-white/90 backdrop-blur-sm px-2 py-0.5 rounded-lg border border-border shadow-sm cursor-pointer"
          >
            {copied ? <><Check size={12} className="text-success" /> Copied</> : <><Copy size={12} /> Copy</>}
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
