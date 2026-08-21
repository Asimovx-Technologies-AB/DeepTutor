import { useState, useCallback, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import {
  ArrowLeft,
  Sparkles,
  BookOpen,
  CheckCircle2,
  RefreshCw,
  AlertCircle,
  HelpCircle,
  Volume2,
  Grid,
  Layers,
  ChevronLeft,
  ChevronRight,
  Trophy,
  RotateCcw,
  MessageSquare,
  Check,
  Flame,
  Zap,
} from 'lucide-react'
import { flashcardsApi } from '../services/api'
import { useSubjectStore } from '../stores/subjectStore'
import { useChatStore } from '../stores/chatStore'

interface Flashcard {
  id: string
  topic_id: string
  front: string
  back: string
  mastered: boolean
}

/**
 * Strips raw markdown bold artifacts like `**Bold: **` or unclosed asterisks `*`
 * while preserving valid LaTeX math `$formula$`.
 */
function cleanMarkdownText(text: string): string {
  if (!text) return ''
  return text
    // Replace broken bold labels like `**Core Meaning: **` with clean text
    .replace(/\*\*\s*([^*]+?)\s*:\s*\*\*/g, '$1:')
    .replace(/\*\*\s*([^*]+?)\s*\*\*/g, '$1')
    // Remove standalone stray asterisks
    .replace(/(^|\s)\*+(\s|$)/g, '$1$2')
    .trim()
}

/**
 * Parses and renders the 3-part structured card back with dedicated aesthetic boxes.
 */
function CardBackView({ rawContent }: { rawContent: string }) {
  if (!rawContent) return null

  // Normalize markers
  let text = rawContent
    .replace(/([^\n])\s*(🎯|💡|🔑)/g, '$1\n\n$2')
    .replace(/\*\*\s*Core Meaning:\s*\*\*/gi, '🎯 Core Meaning:')
    .replace(/\*\*\s*Analogy:\s*\*\*/gi, '💡 Analogy:')
    .replace(/\*\*\s*Exam Tip[^:]*:\s*\*\*/gi, '🔑 Exam Tip / Formula:')

  // Match 3 parts
  const coreMatch = text.match(/🎯\s*(?:Core Meaning|Meaning|Definition)?\s*:?\s*([\s\S]*?)(?=(?:💡|🔑|$))/i)
  const analogyMatch = text.match(/💡\s*(?:Analogy|Mental Model|Example)?\s*:?\s*([\s\S]*?)(?=(?:🔑|$))/i)
  const tipMatch = text.match(/🔑\s*(?:Exam Tip|Exam Rule|Formula|Key Rule)?\s*:?\s*([\s\S]*?)$/i)

  const core = coreMatch ? cleanMarkdownText(coreMatch[1]) : ''
  const analogy = analogyMatch ? cleanMarkdownText(analogyMatch[1]) : ''
  const tip = tipMatch ? cleanMarkdownText(tipMatch[1]) : ''

  const isStructured = Boolean(core || analogy || tip)

  if (isStructured) {
    return (
      <div className="space-y-3 text-left w-full">
        {/* Core Meaning Card */}
        {core && (
          <div className="bg-emerald-50/70 border border-emerald-200/80 rounded-2xl p-3.5 space-y-1 shadow-2xs">
            <div className="flex items-center gap-1.5 text-xs font-black text-emerald-800 uppercase tracking-wide">
              <span>🎯 Core Meaning</span>
            </div>
            <div className="text-xs sm:text-sm text-gray-800 leading-relaxed font-medium markdown-content">
              <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                {core}
              </ReactMarkdown>
            </div>
          </div>
        )}

        {/* Real-Life Analogy Card */}
        {analogy && (
          <div className="bg-amber-50/70 border border-amber-200/80 rounded-2xl p-3.5 space-y-1 shadow-2xs">
            <div className="flex items-center gap-1.5 text-xs font-black text-amber-800 uppercase tracking-wide">
              <span>💡 Real-Life Analogy</span>
            </div>
            <div className="text-xs sm:text-sm text-gray-800 leading-relaxed font-medium markdown-content">
              <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                {analogy}
              </ReactMarkdown>
            </div>
          </div>
        )}

        {/* Exam Tip & Formula Card */}
        {tip && (
          <div className="bg-orange-50/70 border border-orange-200/80 rounded-2xl p-3.5 space-y-1 shadow-2xs">
            <div className="flex items-center gap-1.5 text-xs font-black text-orange-800 uppercase tracking-wide">
              <span>🔑 Exam Tip & Formula</span>
            </div>
            <div className="text-xs sm:text-sm text-gray-800 leading-relaxed font-semibold markdown-content">
              <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                {tip}
              </ReactMarkdown>
            </div>
          </div>
        )}
      </div>
    )
  }

  // Fallback for unstructured single text
  return (
    <div className="text-left py-2 text-xs sm:text-sm text-gray-800 leading-relaxed font-medium markdown-content">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
        {cleanMarkdownText(rawContent)}
      </ReactMarkdown>
    </div>
  )
}

export default function FlashcardsPage() {
  const { topicId } = useParams<{ topicId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const activeSession = useChatStore((s) => s.activeSession)

  const [currentIndex, setCurrentIndex] = useState(0)
  const [isFlipped, setIsFlipped] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [viewMode, setViewMode] = useState<'single' | 'grid'>('single')
  const [gridFilter, setGridFilter] = useState<'all' | 'unmastered' | 'mastered'>('all')
  const [generating, setGenerating] = useState(false)
  const [showCompletionModal, setShowCompletionModal] = useState(false)

  // Subject metadata detection
  const subjects = useSubjectStore((s) => s.subjects)
  const subjectTopics = useSubjectStore((s) => s.topics)

  let currentTopicMeta: any = null
  let currentSubjectMeta: any = null

  for (const [sId, topics] of Object.entries(subjectTopics)) {
    const found = topics.find((t) => t.id === topicId)
    if (found) {
      currentTopicMeta = found
      currentSubjectMeta = subjects.find((s) => s.id === sId)
      break
    }
  }

  const topicTitle = currentTopicMeta?.name || (topicId ? topicId.replace(/[-_]/g, ' ').toUpperCase() : 'Study Deck')

  // Theme color accents based on subject
  const getThemeAccent = () => {
    if (!currentSubjectMeta) return { primary: '#F97316', bg: '#FFF7ED', border: 'border-orange-200', text: 'text-orange-600' }
    const cat = currentSubjectMeta.id?.toLowerCase() || ''
    if (cat.includes('phys')) return { primary: '#F59E0B', bg: '#FFFBEB', border: 'border-amber-200', text: 'text-amber-600' }
    if (cat.includes('chem')) return { primary: '#10B981', bg: '#ECFDF5', border: 'border-emerald-200', text: 'text-emerald-600' }
    if (cat.includes('math')) return { primary: '#6366F1', bg: '#EEF2FF', border: 'border-indigo-200', text: 'text-indigo-600' }
    return { primary: '#F97316', bg: '#FFF7ED', border: 'border-orange-200', text: 'text-orange-600' }
  }
  const theme = getThemeAccent()

  // Fetch flashcards
  const { data: cards = [], isLoading } = useQuery<Flashcard[]>({
    queryKey: ['flashcards', topicId],
    queryFn: async () => {
      const res = await flashcardsApi.byTopic(topicId || 'general')
      return res.data
    },
  })

  // Auto generate deck if empty
  useEffect(() => {
    if (!isLoading && cards.length === 0 && !generating && topicId) {
      generateMutation.mutate()
    }
  }, [isLoading, cards.length, topicId])

  // Generate mutation
  const generateMutation = useMutation({
    mutationFn: async () => {
      setGenerating(true)
      const res = await flashcardsApi.generate({ topic_id: topicId })
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['flashcards', topicId] })
      setGenerating(false)
      setCurrentIndex(0)
      setIsFlipped(false)
      setShowCompletionModal(false)
    },
    onError: () => {
      setGenerating(false)
    },
  })

  // Review mutation
  const reviewMutation = useMutation({
    mutationFn: async ({ cardId, mastered }: { cardId: string; mastered: boolean }) => {
      await flashcardsApi.review(topicId || 'general', cardId, mastered)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['flashcards', topicId] })
    },
  })

  const currentCard = cards[currentIndex]
  const masteredCount = cards.filter((c) => c.mastered).length
  const completionPercentage = cards.length > 0 ? Math.round((masteredCount / cards.length) * 100) : 0

  const handleNext = () => {
    setIsFlipped(false)
    setTimeout(() => {
      if (currentIndex === cards.length - 1) {
        setShowCompletionModal(true)
      } else {
        setCurrentIndex((prev) => (prev + 1) % cards.length)
      }
    }, 150)
  }

  const handlePrev = () => {
    setIsFlipped(false)
    setTimeout(() => {
      setCurrentIndex((prev) => (prev - 1 + cards.length) % cards.length)
    }, 150)
  }

  const handleReview = (mastered: boolean, cardId?: string) => {
    const idToReview = cardId || currentCard?.id
    if (!idToReview) return
    reviewMutation.mutate({ cardId: idToReview, mastered })

    if (topicId) {
      const subjectState = useSubjectStore.getState()
      for (const [sId, sTopics] of Object.entries(subjectState.topics)) {
        if (sTopics.some((t) => t.id === topicId)) {
          const newMasteredCount = cards.filter((c) => (c.id === idToReview ? mastered : c.mastered)).length
          const totalCards = Math.max(cards.length, 1)
          const newPct = Math.round((newMasteredCount / totalCards) * 100)
          subjectState.updateTopicProgress(sId, topicId, newPct)
          break
        }
      }
    }

    if (viewMode === 'single') {
      handleNext()
    }
  }

  const handleBackToChat = () => {
    if (currentSubjectMeta && topicId) {
      navigate(`/subjects/${currentSubjectMeta.id}/chat/${topicId}`)
    } else if (activeSession?.id) {
      navigate(`/chat/${activeSession.id}`)
    } else {
      navigate(-1)
    }
  }

  const handleAskTutorAboutCard = (card: Flashcard) => {
    const prompt = `Can you explain the flashcard concept: "${card.front}" in depth with examples?`
    if (currentSubjectMeta && topicId) {
      navigate(`/subjects/${currentSubjectMeta.id}/chat/${topicId}`, {
        state: { initialPrompt: prompt },
      })
    } else if (activeSession?.id) {
      navigate(`/chat/${activeSession.id}`, {
        state: { initialPrompt: prompt },
      })
    } else {
      navigate('/chat', { state: { initialPrompt: prompt } })
    }
  }

  // Text-To-Speech
  const speakText = (text: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    if (!('speechSynthesis' in window)) return
    if (isSpeaking) {
      window.speechSynthesis.cancel()
      setIsSpeaking(false)
      return
    }
    const cleanText = text.replace(/[*_#`$]/g, '').replace(/🎯|💡|🔑/g, '')
    const utterance = new SpeechSynthesisUtterance(cleanText)
    utterance.rate = 0.95
    utterance.onend = () => setIsSpeaking(false)
    utterance.onerror = () => setIsSpeaking(false)
    setIsSpeaking(true)
    window.speechSynthesis.speak(utterance)
  }

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (viewMode !== 'single' || cards.length === 0 || showCompletionModal) return
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault()
        setIsFlipped((prev) => !prev)
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        handleReview(true)
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault()
        handleReview(false)
      } else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
        e.preventDefault()
        setIsFlipped((prev) => !prev)
      }
    },
    [viewMode, cards.length, showCompletionModal, currentCard]
  )

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  if (isLoading || (generating && cards.length === 0)) {
    return (
      <div className="p-6 max-w-2xl mx-auto space-y-4">
        <div className="skeleton h-8 w-48 mb-6" />
        <div className="skeleton h-80 w-full rounded-[1.5rem]" />
      </div>
    )
  }

  if (cards.length === 0) {
    return (
      <div className="p-6 max-w-xl mx-auto text-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="glass-card p-12 text-center"
        >
          <div className="w-16 h-16 rounded-[1.5rem] bg-gradient-to-br from-indigo-500/20 to-violet-500/20 flex items-center justify-center mx-auto mb-4">
            <BookOpen size={28} className="text-indigo-500" />
          </div>
          <h2 className="text-xl font-black text-[#20201D]">Ready to Master {topicTitle}?</h2>
          <p className="text-[#6F6B63] text-sm">
            Generate an AI-powered visual flashcard deck to review key formulas, definitions, and mental models.
          </p>
          <div className="flex items-center justify-center gap-3 pt-2">
            <button
              onClick={handleBackToChat}
              className="flex items-center gap-2 text-xs font-bold text-[#6F6B63] hover:text-[#F28A45] py-3 px-5 rounded-2xl bg-white border border-[#E7E1D8] shadow-2xs cursor-pointer"
            >
              <ArrowLeft size={14} /> Back to Chat
            </button>
            <button
              onClick={() => generateMutation.mutate()}
              disabled={generating}
              className="btn-primary flex items-center gap-2 font-bold py-3 px-6 rounded-2xl cursor-pointer"
            >
              <Sparkles size={16} /> Generate AI Deck
            </button>
          </div>
        </motion.div>
      </div>
    )
  }

  const filteredCards = cards.filter((c) => {
    if (gridFilter === 'mastered') return c.mastered
    if (gridFilter === 'unmastered') return !c.mastered
    return true
  })

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-6 bg-[#F7F7F7]">
      {/* Header */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-2 text-[#777777] hover:text-[#1CB0F6] transition-colors text-sm font-bold cursor-pointer"
        >
          <ArrowLeft size={14} />
          <span>Back to Chat</span>
        </button>

        <div className="flex items-center gap-2">
          {/* View Mode Toggle */}
          <button
            onClick={() => setViewMode(viewMode === 'single' ? 'grid' : 'single')}
            className="text-xs px-3 py-1.5 rounded-[1.25rem] border border-[#E2E8F0] bg-white text-[#3C3C3C] hover:bg-[#FFFFFF] font-black flex items-center gap-1.5 transition-all cursor-pointer elevation-1"
          >
            {viewMode === 'single' ? <Grid size={14} /> : <Layers size={14} />}
            <span>{viewMode === 'single' ? 'Cheat Sheet View' : 'Focus Mode'}</span>
          </button>

          <button
            onClick={() => generateMutation.mutate()}
            disabled={generating}
            className="text-xs text-[#1CB0F6] hover:text-[#1899D6] font-black flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            <RefreshCw size={13} className={generating ? 'animate-spin' : ''} />
            <span>Regenerate</span>
          </button>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-black text-[#777777]">
          <span>
            {viewMode === 'single' ? `Card ${currentIndex + 1} of ${cards.length}` : `${cards.length} Total Cards`}
          </span>
          <span className="text-[#58CC02]">
            {completionPercentage}% Mastered ({masteredCount}/{cards.length})
          </span>
        </div>

        <div className="w-full sm:w-auto flex items-center gap-4 bg-[#FAF8F3] px-4 py-2.5 rounded-2xl border border-[#E7E1D8]">
          <div className="w-10 h-10 rounded-xl bg-orange-100 flex items-center justify-center text-orange-600">
            <Flame size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2 text-xs font-black text-[#20201D]">
              <span>{masteredCount} of {cards.length} Mastered</span>
              <span className="text-emerald-600">({completionPercentage}%)</span>
            </div>
            <div className="w-36 h-2 bg-gray-200 rounded-full mt-1.5 overflow-hidden">
              <motion.div
                className="h-full bg-emerald-500 rounded-full"
                animate={{ width: `${completionPercentage}%` }}
                transition={{ duration: 0.4 }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* ─── SINGLE FOCUS CARD VIEW (3D FLIP) ─── */}
      {viewMode === 'single' ? (
        <div className="space-y-5">
          {/* Card Counter */}
          <div className="flex items-center justify-between text-xs font-black text-gray-500 px-2">
            <span>Card {currentIndex + 1} of {cards.length}</span>
            <span className="text-gray-400">Press Space or Click to Flip 🔄</span>
          </div>

          {/* 3D Interactive Flip Container */}
          <div
            className="perspective-1000 min-h-[420px] w-full cursor-pointer relative select-none"
            onClick={() => setIsFlipped(!isFlipped)}
            style={{ perspective: 1000, WebkitPerspective: 1000 }}
          >
            <motion.div
              className="relative w-full h-full min-h-[420px]"
              animate={{ rotateY: isFlipped ? 180 : 0 }}
              transition={{ duration: 0.5, ease: [0.23, 1, 0.32, 1] }}
              style={{
                transformStyle: 'preserve-3d',
                WebkitTransformStyle: 'preserve-3d',
              }}
            >
              {/* Front Side */}
              <div className="absolute inset-0 w-full h-full backface-hidden bg-white border border-[#E2E8F0] border-t-4 border-t-[#1CB0F6] rounded-[2rem] p-8 flex flex-col justify-between elevation-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-xs text-[#1CB0F6] font-black uppercase tracking-wider">
                    <HelpCircle size={14} /> Concept / Question
                  </div>

                  <button
                    type="button"
                    onClick={(e) => speakText(currentCard?.front || '', e)}
                    className="p-2 rounded-[1.25rem] text-[#AFAFAF] hover:text-[#1CB0F6] hover:bg-[#DDF4FF] transition-colors cursor-pointer"
                    title="Listen to card audio"
                  >
                    <Volume2 size={18} />
                  </button>
                </div>

                <div className="flex-1 flex flex-col items-center justify-center text-center my-3">
                  <h2 className="text-xl font-black text-[#3C3C3C] leading-relaxed px-4">
                    {currentCard?.front}
                  </h2>

                  {currentCard?.mastered && (
                    <span className="text-[11px] font-black bg-emerald-50 text-emerald-700 border border-emerald-200 px-2.5 py-1 rounded-full flex items-center gap-1 mt-4">
                      <Check size={12} /> Mastered
                    </span>
                  )}
                </div>

                <div className="flex items-center justify-center pt-3 border-t border-[#E2E8F0]/60">
                  <p className="text-xs text-[#AFAFAF] font-semibold">Click Card to Flip 🔄</p>
                </div>
              </div>

          {/* ─── Back Side (Structured 3-Part Answer) ─── */}
          <div
            className="absolute inset-0 w-full h-full backface-hidden bg-white border border-[#E2E8F0] border-t-4 border-t-[#58CC02] rounded-[2rem] p-8 flex flex-col justify-between elevation-2"
            style={{ transform: 'rotateY(180deg)' }}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-xs text-[#58CC02] font-black uppercase tracking-wider">
                <CheckCircle2 size={14} /> Answer / Explanation
              </div>

              <button
                type="button"
                onClick={(e) => speakText(currentCard?.back || '', e)}
                className="p-2 rounded-[1.25rem] text-[#AFAFAF] hover:text-[#58CC02] hover:bg-[#D7FFB8] transition-colors cursor-pointer"
                title="Listen to answer audio"
              >
                <Volume2 size={18} />
              </button>
            </div>

            <div className="flex-1 flex items-center justify-center text-center">
              <p className="text-base text-[#3C3C3C] leading-relaxed px-4 font-bold">
                {currentCard?.back}
              </p>
            </div>

            <div className="flex items-center justify-end pt-3 border-t border-[#E2E8F0]/60">
              <p className="text-xs text-[#AFAFAF] font-semibold">Click Card to Flip Back 🔄</p>
            </div>
          </div>
        </motion.div>
          </div>

          {/* ─── Review Confidence Buttons (3-Tier Spaced Repetition) ─── */ }
  <div className="grid grid-cols-2 gap-3 pt-2">
    <button
      onClick={() => handleReview(false)}
      className="btn-ghost flex items-center justify-center gap-2 py-3.5 border-[#FF4B4B]/40 text-[#FF4B4B] hover:bg-[#FFD1D1] font-black rounded-[1.5rem] cursor-pointer"
    >
      <AlertCircle size={16} />
      <span>Needs Practice (←)</span>
    </button>
    <button
      onClick={() => handleReview(true)}
      className="btn-primary flex items-center justify-center gap-2 py-3.5 font-black rounded-[1.5rem] cursor-pointer elevation-1"
      style={{ background: '#58CC02' }}
    >
      <CheckCircle2 size={16} />
      <span>Mastered! (→)</span>
    </button>
  </div>

  {/* Navigation */ }
  <div className="flex items-center justify-between text-sm px-2 text-[#777777]">
    <button
      onClick={handlePrev}
      className="hover:text-[#1CB0F6] font-black transition-colors flex items-center gap-1 cursor-pointer"
    >
      <ChevronLeft size={16} /> Previous Card
    </button>
    <span className="text-xs text-[#AFAFAF]">Shortcuts: Space / Arrow Keys</span>
    <button
      onClick={handleNext}
      className="hover:text-[#1CB0F6] font-black transition-colors flex items-center gap-1 cursor-pointer"
    >
      Next Card <ChevronRight size={16} />
    </button>
  </div>
        </div >
      ) : (
    /* ─── INTERACTIVE CHEAT-SHEET GRID VIEW ─── */
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {(['all', 'unmastered', 'mastered'] as const).map((filter) => (
          <button
            key={filter}
            onClick={() => setGridFilter(filter)}
            className={`text-xs px-3 py-1.5 rounded-[1.25rem] capitalize font-black transition-all cursor-pointer ${gridFilter === filter
                ? 'bg-[#1CB0F6] text-white elevation-1'
                : 'bg-[#E5E5E5] text-[#777777] hover:text-[#3C3C3C]'
              }`}
          >
            {filter}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-h-[600px] overflow-y-auto pr-1">
        {filteredCards.map((card, idx) => (
          <motion.div
            key={card.id}
            onClick={() => {
              setCurrentIndex(cards.findIndex((c) => c.id === card.id))
              setViewMode('single')
              setIsFlipped(false)
            }}
            className={`p-4 rounded-[1.5rem] border transition-all text-left cursor-pointer flex flex-col justify-between space-y-3 ${card.mastered
                ? 'bg-[#D7FFB8]/50 border-[#58CC02]/40 hover:border-[#58CC02]'
                : 'bg-white border-[#E2E8F0] hover:border-[#1CB0F6]'
              }`}
          >
            <div>
              <span className="text-[10px] font-black text-[#1CB0F6] uppercase tracking-wider block mb-1">
                Concept
              </span>
              <p className="text-xs font-extrabold text-[#3C3C3C] leading-snug">{card.front}</p>
            </div>
            <div className="pt-2 border-t border-[#E2E8F0]/60 flex items-center justify-between">
              <span className="text-[11px] text-[#777777] line-clamp-2 font-medium">{card.back}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  handleReview(!card.mastered, card.id)
                }}
                className={`p-1.5 rounded-[1.25rem] border flex-shrink-0 cursor-pointer ml-2 ${card.mastered
                    ? 'bg-[#58CC02] text-white border-[#58CC02]'
                    : 'bg-[#F7F7F7] text-[#AFAFAF] border-[#E2E8F0] hover:text-[#58CC02]'
                  }`}
              >
                {card.mastered ? 'Mark for Review' : 'Mark as Mastered'}
              </button>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  )
}

{/* ─── Celebration Completion Modal ─── */ }
<AnimatePresence>
  {showCompletionModal && (
    <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.9, opacity: 0 }}
        className="bg-white rounded-3xl p-8 max-w-md w-full text-center border border-[#E7E1D8] shadow-2xl space-y-5"
      >
        <div className="w-20 h-20 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center mx-auto shadow-inner">
          <Trophy size={36} />
        </div>
        <div>
          <h2 className="text-2xl font-black text-[#20201D]">Deck Review Completed! 🎉</h2>
          <p className="text-sm text-gray-500 mt-1">
            You reviewed all {cards.length} cards for <span className="font-bold text-gray-800">{topicTitle}</span>.
          </p>
        </div>

        <div className="bg-[#FAF8F3] p-4 rounded-2xl border border-[#E7E1D8] flex items-center justify-around">
          <div>
            <p className="text-2xl font-black text-emerald-600">{masteredCount}</p>
            <p className="text-xs font-bold text-gray-500">Mastered</p>
          </div>
          <div className="w-px h-8 bg-gray-200" />
          <div>
            <p className="text-2xl font-black text-amber-600">{cards.length - masteredCount}</p>
            <p className="text-xs font-bold text-gray-500">Needs Study</p>
          </div>
          <div className="w-px h-8 bg-gray-200" />
          <div>
            <p className="text-2xl font-black text-orange-600">+{cards.length * 5} XP</p>
            <p className="text-xs font-bold text-gray-500">Earned</p>
          </div>
        </div>

        <div className="flex gap-3 pt-2">
          <button
            onClick={() => {
              setShowCompletionModal(false)
              setCurrentIndex(0)
              setIsFlipped(false)
            }}
            className="flex-1 py-3 px-4 rounded-2xl border border-[#E7E1D8] bg-white font-bold text-xs hover:bg-gray-50 flex items-center justify-center gap-2 cursor-pointer shadow-2xs"
          >
            <RotateCcw size={14} /> Review Again
          </button>
          <button
            onClick={handleBackToChat}
            className="flex-1 py-3 px-4 rounded-2xl bg-orange-600 hover:bg-orange-700 text-white font-black text-xs flex items-center justify-center gap-2 cursor-pointer shadow-sm"
          >
            <ArrowLeft size={14} /> Back to Chat
          </button>
        </div>
      </motion.div>
    </div>
  )}
</AnimatePresence>
    </div >
  )
}
