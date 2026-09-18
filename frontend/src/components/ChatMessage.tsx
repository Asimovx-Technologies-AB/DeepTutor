import React, { useState, memo, useDeferredValue } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import { Bot, User, Copy, Check, Image, Lightbulb, HelpCircle, Sparkles } from 'lucide-react'
import { motion } from 'framer-motion'
import SourceCard, { type Source } from './SourceCard'

import InlineSVGDiagram from './InlineSVGDiagram'
import StudyNotesCard, { isStudyNotesContent } from './StudyNotesCard'
import FlashcardQuizCard, { parseQuizDataFromContent } from './FlashcardQuizCard'
import TeacherModeCard, { parseCheckpointFromMarkdown } from './TeacherModeCard'
import ExamReportCard, { isExamReportContent } from './ExamReportCard'

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
  export_ready?: boolean
  response_format?: string
  flashcard_quiz?: any
  suggestedQuestions?: string[]
  socraticFollowUp?: string
  onSuggestionClick?: (question: string) => void
}

const ChatMessageComponent = ({
  role,
  content,
  isStreaming,
  sources,
  grounding,
  export_ready,
  response_format,
  flashcard_quiz,
  suggestedQuestions,
  socraticFollowUp,
  onSuggestionClick,
}: Props) => {
  const [copied, setCopied] = useState(false)
  const isAssistant = role === 'assistant'

  const isStudyNotes = isStudyNotesContent({
    role,
    content,
    export_ready,
    response_format
  })

  const isExamReport = isAssistant && isExamReportContent({
    role,
    content,
    response_format
  })

  const parsedCheckpoint = parseCheckpointFromMarkdown(content)
  const hasCheckpoint = Boolean(parsedCheckpoint.checkpoint)

  // Use React deferred value during streaming so UI thread stays responsive
  const deferredContent = useDeferredValue(content)
  const displayContent = isStreaming
    ? deferredContent
    : (hasCheckpoint ? parsedCheckpoint.beforeText : content)

  const handleCopy = () => {
    navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // If interactive checkpoint card is active, avoid duplicating option chips
  const visibleSuggestions = hasCheckpoint
    ? (suggestedQuestions || []).filter((q) => !q.toLowerCase().startsWith('option ') && q.length > 2)
    : (suggestedQuestions || [])
  const hasSuggestions = isAssistant && !isStreaming && visibleSuggestions.length > 0
  const hasFollowUp = isAssistant && !isStreaming && socraticFollowUp && socraticFollowUp.trim()

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
              ? 'bg-brand-primary-soft border border-brand-primary/20 rounded-[2rem] rounded-tl-sm text-text-primary px-5 py-4 shadow-sm'
              : 'text-text-primary'
            : 'bg-brand-primary text-white rounded-[2rem] rounded-tr-sm shadow-sm px-5 py-3 font-medium'
        }`}>
          {isAssistant ? (
            <div className="markdown-content">
              {/* Study Notes Document Attachment Card */}
              {isStudyNotes && (
                <StudyNotesCard markdown={content} className="mb-3" />
              )}

              {/* Exam Performance Report Card */}
              {isExamReport && (
                <ExamReportCard markdown={content} className="mb-3" />
              )}

              {/* Flashcard & Quiz Direct Prop Renderer or Parsed Plain Text */}
              {(() => {
                const quizToRender = flashcard_quiz || parseQuizDataFromContent(content)
                if (quizToRender) {
                  return <FlashcardQuizCard quizData={quizToRender} className="mb-3" />
                }
                return null
              })()}

              {/* Grounding Badge (only for substantive answers) */}
              {grounding && grounding.formatted_badge && !content.includes("Topic Not Found") && (
                <div className="mb-2 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-success-soft text-success border border-success/30">
                  <span>{grounding.formatted_badge}</span>
                </div>
              )}
              {(() => {
                const isPlainFlashcard = content.includes('Front of Card') && content.includes('Back of Card')
                const displayContent = isPlainFlashcard
                  ? (content.split('🗂️')[0].split('Front of Card')[0].trim() || 'Here is your interactive study flashcard deck:')
                  : content

                return (
                  <ReactMarkdown
                    remarkPlugins={[remarkMath, remarkGfm]}
                    rehypePlugins={[rehypeKatex]}
                    components={{
                  h3({ node, children, ...props }: any) {
                    const text = React.Children.toArray(children).join('')
                    if (text.includes('Interactive Checkpoint') || text.includes('💡')) {
                      return (
                        <div className="mt-6 mb-3 flex items-center gap-2 text-xs font-bold text-brand-primary uppercase tracking-wider bg-brand-primary-soft/80 px-3.5 py-1.5 rounded-xl border border-brand-primary/25 w-fit shadow-xs">
                          <Lightbulb size={15} className="text-brand-primary" />
                          <span>Interactive Checkpoint</span>
                        </div>
                      )
                    }
                    return (
                      <h3 className="text-base sm:text-lg font-bold text-text-primary mt-5 mb-2 tracking-tight" {...props}>
                        {children}
                      </h3>
                    )
                  },
                  hr({ ...props }: any) {
                    return <hr className="my-5 border-t border-border/70" {...props} />
                  },
                  table({ children, ...props }: any) {
                    return (
                      <div className="my-4 overflow-x-auto rounded-xl border border-border shadow-xs bg-white">
                        <table className="w-full text-left border-collapse" {...props}>
                          {children}
                        </table>
                      </div>
                    )
                  },
                  pre({ node, children, ...props }: any) {
                    const child = React.Children.toArray(children)[0] as any
                    const className = child?.props?.className || ''
                    const childStr = String(child?.props?.children || '')
                    if (
                      className.includes('language-svg') ||
                      className.includes('language-flashcard_quiz') ||
                      className.includes('language-flashcard-quiz') ||
                      (childStr.includes('<svg') && childStr.includes('</svg>'))
                    ) {
                      return <>{children}</>
                    }
                    return <pre {...props}>{children}</pre>
                  },
                  code({ node, className, children, ...props }: any) {
                    const match = /language-(\w+)/.exec(className || '')
                    const language = match ? match[1] : ''
                    const codeStr = String(children).replace(/\n$/, '')
                    if (language === 'svg' || (codeStr.includes('<svg') && codeStr.includes('</svg>'))) {
                      return <InlineSVGDiagram svg={codeStr} />
                    }
                    if (language === 'flashcard_quiz' || language === 'flashcard-quiz') {
                      try {
                        const quizData = JSON.parse(codeStr)
                        return <FlashcardQuizCard quizData={quizData} />
                      } catch {
                        return (
                          <div className="my-3 p-4 rounded-2xl bg-indigo-50/70 border border-indigo-100 flex items-center gap-3 text-xs font-semibold text-indigo-700 animate-pulse">
                            <Sparkles size={16} className="text-indigo-600 animate-spin" />
                            <span>Synthesizing your interactive practice quiz & flashcards...</span>
                          </div>
                        )
                      }
                    }
                    return (
                      <code className={className} {...props}>
                        {children}
                      </code>
                    )
                  },
                  img({ node, src, alt, ...props }: any) {
                    return (
                      <span className="block my-4 max-w-full overflow-hidden rounded-2xl border border-border/80 shadow-md bg-white p-2.5 transition-all hover:shadow-lg">
                        <img
                          src={src}
                          alt={alt || 'AI Verified Educational Diagram'}
                          className="w-full max-h-[460px] object-contain rounded-xl mx-auto block bg-white"
                          loading="lazy"
                          onError={(e: any) => {
                            e.currentTarget.parentElement.style.display = 'none'
                          }}
                          {...props}
                        />
                        {alt && (
                          <span className="text-center text-xs font-semibold text-text-muted mt-2 px-2 flex items-center justify-center gap-1.5">
                            <Image size={13} className="opacity-70" />
                            <span>{alt}</span>
                          </span>
                        )}
                      </span>
                    )
                  },
                }}
              >
                {displayContent}
              </ReactMarkdown>
                )
              })()}
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

        {/* ── Interactive Teacher Mode Checkpoint Card ──────────────── */}
        {isAssistant && !isStreaming && hasCheckpoint && parsedCheckpoint.checkpoint && (
          <TeacherModeCard
            checkpoint={parsedCheckpoint.checkpoint}
            onSelectOption={(opt) => onSuggestionClick?.(opt)}
            onActionClick={(act) => onSuggestionClick?.(act)}
          />
        )}

        {/* Source cards */}
        {isAssistant && sources && sources.length > 0 && !isStreaming && !content.includes("Topic Not Found") && (
          <SourceCard sources={sources} />
        )}

        {/* ── Socratic Follow-Up Callout ─────────────────────────────── */}
        {hasFollowUp && !content.includes("### 💡") && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15, duration: 0.25 }}
            className="mt-3 flex items-start gap-2.5 bg-amber-50 border border-amber-200 rounded-2xl px-4 py-3 shadow-sm"
          >
            <Lightbulb size={16} className="text-amber-500 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-[11px] font-bold text-amber-600 uppercase tracking-wide mb-1">
                Checkpoint Question
              </p>
              <p className="text-sm text-amber-900 leading-relaxed font-medium">
                {socraticFollowUp}
              </p>
            </div>
          </motion.div>
        )}

        {/* ── Suggested Question Chips ───────────────────────────────── */}
        {hasSuggestions && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.25 }}
            className="mt-3 flex flex-wrap gap-2"
          >
            {visibleSuggestions.map((q, i) => (
              <button
                key={i}
                onClick={() => onSuggestionClick?.(q)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold
                           bg-brand-primary/8 text-brand-primary border border-brand-primary/20
                           hover:bg-brand-primary hover:text-white hover:border-brand-primary
                           transition-all duration-150 cursor-pointer shadow-sm"
              >
                <HelpCircle size={11} />
                {q}
              </button>
            ))}
          </motion.div>
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
  if (prevProps.isStreaming !== nextProps.isStreaming) return false
  if (prevProps.content !== nextProps.content) return false
  if (prevProps.sources !== nextProps.sources) return false
  if (prevProps.grounding !== nextProps.grounding) return false
  if (prevProps.suggestedQuestions !== nextProps.suggestedQuestions) return false
  if (prevProps.socraticFollowUp !== nextProps.socraticFollowUp) return false
  return true
})
