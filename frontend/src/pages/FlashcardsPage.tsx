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
      <div className="min-h-[75vh] flex flex-col items-center justify-center p-6 max-w-xl mx-auto text-center">
        <div className="w-16 h-16 rounded-3xl bg-orange-100 border border-orange-200 flex items-center justify-center mb-5 animate-pulse shadow-sm">
          <Sparkles className="w-8 h-8 text-orange-600 animate-spin" />
        </div>
        <h2 className="text-xl font-black text-[#20201D] mb-2">Creating Visual Study Flashcards...</h2>
        <p className="text-sm text-[#6F6B63] max-w-md mb-6">
          Generating curriculum-grounded concept cards with intuitive analogies and exam rules for <span className="font-bold text-[#20201D]">{topicTitle}</span>.
        </p>
        <button
          onClick={handleBackToChat}
          className="flex items-center gap-2 text-xs font-bold text-[#6F6B63] hover:text-[#F28A45] transition-colors py-2 px-4 rounded-xl bg-white border border-[#E7E1D8] shadow-2xs cursor-pointer"
        >
          <ArrowLeft size={14} /> Back to Chat
        </button>
      </div>
    )
  }

  if (cards.length === 0) {
    return (
      <div className="p-6 max-w-xl mx-auto text-center pt-16">
        <div className="glass-card p-10 bg-white border border-[#E7E1D8] rounded-3xl shadow-sm space-y-4">
          <div className="w-16 h-16 rounded-2xl bg-orange-100 flex items-center justify-center mx-auto text-orange-600">
            <BookOpen size={28} />
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
        </div>
      </div>
    )
  }

  const filteredCards = cards.filter((c) => {
    if (gridFilter === 'mastered') return c.mastered
    if (gridFilter === 'unmastered') return !c.mastered
    return true
  })

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6 bg-[#FAF8F3] min-h-[90vh] text-[#20201D] font-sans">
      {/* ─── Top Header Navigation Bar ─── */}
      <div className="flex items-center justify-between">
        <button
          onClick={handleBackToChat}
          className="flex items-center gap-2 text-xs font-extrabold text-[#6F6B63] hover:text-[#F28A45] transition-colors py-2 px-3.5 rounded-xl bg-white border border-[#E7E1D8] shadow-2xs cursor-pointer"
        >
          <ArrowLeft size={14} />
          <span>Back to Chat</span>
        </button>

        <div className="flex items-center gap-2">
          {/* View Mode Toggle */}
          <button
            onClick={() => setViewMode(viewMode === 'single' ? 'grid' : 'single')}
            className="text-xs px-3 py-2 rounded-xl border border-[#E7E1D8] bg-white text-[#20201D] hover:bg-orange-50/50 font-bold flex items-center gap-1.5 transition-all cursor-pointer shadow-2xs"
          >
            {viewMode === 'single' ? <Grid size={14} /> : <Layers size={14} />}
            <span>{viewMode === 'single' ? 'Cheat Sheet View' : 'Focus Mode'}</span>
          </button>

          <button
            onClick={() => generateMutation.mutate()}
            disabled={generating}
            className="text-xs px-3 py-2 rounded-xl bg-white border border-[#E7E1D8] hover:border-orange-300 text-orange-600 font-bold flex items-center gap-1.5 transition-colors cursor-pointer shadow-2xs"
            title="Generate a fresh deck of cards"
          >
            <RefreshCw size={13} className={generating ? 'animate-spin' : ''} />
            <span>Regenerate</span>
          </button>
        </div>
      </div>

      {/* ─── Subject Banner & Mastery Tracker ─── */}
      <div className="bg-white border border-[#E7E1D8] rounded-3xl p-5 shadow-2xs flex flex-col sm:flex-row items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            {currentSubjectMeta && (
              <span className={`text-[11px] font-black uppercase tracking-wider px-2.5 py-0.5 rounded-full border ${theme.bg} ${theme.text} ${theme.border}`}>
                {currentSubjectMeta.name}
              </span>
            )}
            <span className="text-[11px] font-extrabold text-gray-500 uppercase tracking-wider">
              {topicTitle}
            </span>
          </div>
          <h1 className="text-lg font-black text-[#20201D]">Interactive Study Cards</h1>
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
              {/* ─── Front Side ─── */}
              <div
                className="absolute inset-0 w-full h-full bg-gradient-to-b from-white to-[#FFFDF9] border-2 border-orange-200/80 rounded-3xl p-8 flex flex-col justify-between shadow-sm hover:shadow-md transition-shadow"
                style={{
                  backfaceVisibility: 'hidden',
                  WebkitBackfaceVisibility: 'hidden',
                  transform: 'rotateY(0deg)',
                }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs font-black uppercase tracking-wider text-orange-600 bg-orange-50 px-3 py-1 rounded-full border border-orange-200">
                    <HelpCircle size={14} />
                    <span>Concept / Question</span>
                  </div>

                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={(e) => speakText(currentCard?.front || '', e)}
                      className="p-2 rounded-xl text-gray-400 hover:text-orange-600 hover:bg-orange-50 transition-colors cursor-pointer"
                      title="Listen to card audio"
                    >
                      <Volume2 size={18} />
                    </button>
                    {currentCard?.mastered && (
                      <span className="text-[11px] font-black bg-emerald-50 text-emerald-700 border border-emerald-200 px-2.5 py-1 rounded-full flex items-center gap-1">
                        <Check size={12} /> Mastered
                      </span>
                    )}
                  </div>
                </div>

                <div className="my-auto text-center py-6">
                  <h2 className="text-xl sm:text-2xl font-black text-[#20201D] leading-snug px-4">
                    {cleanMarkdownText(currentCard?.front || '')}
                  </h2>
                </div>

                <div className="flex items-center justify-between pt-4 border-t border-[#E7E1D8]/70 text-xs text-gray-500 font-bold">
                  <span className="flex items-center gap-1 text-orange-600">
                    <Zap size={14} /> Tap anywhere to flip
                  </span>
                  <span>Space / Enter</span>
                </div>
              </div>

              {/* ─── Back Side (Structured 3-Part Answer) ─── */}
              <div
                className="absolute inset-0 w-full h-full bg-white border-2 border-emerald-300 rounded-3xl p-6 sm:p-7 flex flex-col justify-between shadow-md overflow-hidden"
                style={{
                  backfaceVisibility: 'hidden',
                  WebkitBackfaceVisibility: 'hidden',
                  transform: 'rotateY(180deg)',
                }}
              >
                <div className="flex items-center justify-between pb-2.5 border-b border-[#E7E1D8]/70">
                  <div className="flex items-center gap-2 text-xs font-black uppercase tracking-wider text-emerald-700 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-200">
                    <CheckCircle2 size={14} />
                    <span>Detailed Breakdown</span>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={(e) => speakText(currentCard?.back || '', e)}
                      className="p-2 rounded-xl text-gray-400 hover:text-emerald-700 hover:bg-emerald-50 transition-colors cursor-pointer"
                      title="Listen to explanation"
                    >
                      <Volume2 size={18} />
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        if (currentCard) handleAskTutorAboutCard(currentCard)
                      }}
                      className="text-xs font-black text-orange-600 hover:text-orange-700 bg-orange-50 hover:bg-orange-100 border border-orange-200 px-3 py-1.5 rounded-xl flex items-center gap-1.5 transition-colors cursor-pointer"
                    >
                      <MessageSquare size={13} />
                      <span>Ask Tutor</span>
                    </button>
                  </div>
                </div>

                {/* Structured Clean Content */}
                <div className="my-auto py-2 overflow-y-auto max-h-[300px] pr-1">
                  <CardBackView rawContent={currentCard?.back || ''} />
                </div>

                <div className="flex items-center justify-between pt-2.5 border-t border-[#E7E1D8]/70 text-xs text-gray-500 font-bold">
                  <span>How well did you know this?</span>
                  <span className="text-gray-400">Click to Flip Back 🔄</span>
                </div>
              </div>
            </motion.div>
          </div>

          {/* ─── Review Confidence Buttons (3-Tier Spaced Repetition) ─── */}
          <div className="grid grid-cols-2 gap-3 pt-2">
            <button
              onClick={() => handleReview(false)}
              className="flex items-center justify-center gap-2 py-3.5 px-4 rounded-2xl bg-white border-2 border-red-200 text-red-600 hover:bg-red-50 font-black text-sm shadow-2xs hover:shadow-xs transition-all cursor-pointer"
            >
              <AlertCircle size={16} />
              <span>Needs Practice (←)</span>
            </button>
            <button
              onClick={() => handleReview(true)}
              className="flex items-center justify-center gap-2 py-3.5 px-4 rounded-2xl bg-emerald-600 hover:bg-emerald-700 text-white font-black text-sm shadow-sm hover:shadow-md transition-all cursor-pointer"
            >
              <CheckCircle2 size={16} />
              <span>Mastered! (→)</span>
            </button>
          </div>

          {/* Navigation Controls */}
          <div className="flex items-center justify-between text-xs font-extrabold text-[#6F6B63] px-2 pt-1">
            <button
              onClick={handlePrev}
              className="hover:text-orange-600 transition-colors flex items-center gap-1 cursor-pointer"
            >
              <ChevronLeft size={16} /> Previous Card
            </button>
            <span className="text-gray-400">Keyboard: Space to Flip • Arrows to Review</span>
            <button
              onClick={handleNext}
              className="hover:text-orange-600 transition-colors flex items-center gap-1 cursor-pointer"
            >
              Next Card <ChevronRight size={16} />
            </button>
          </div>
        </div>
      ) : (
        /* ─── INTERACTIVE CHEAT-SHEET GRID VIEW ─── */
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {(['all', 'unmastered', 'mastered'] as const).map((filter) => (
                <button
                  key={filter}
                  onClick={() => setGridFilter(filter)}
                  className={`text-xs px-3.5 py-1.5 rounded-xl capitalize font-extrabold transition-all cursor-pointer ${
                    gridFilter === filter
                      ? 'bg-orange-600 text-white shadow-2xs'
                      : 'bg-white border border-[#E7E1D8] text-gray-600 hover:text-gray-900'
                  }`}
                >
                  {filter}
                </button>
              ))}
            </div>
            <span className="text-xs font-bold text-gray-500">
              Showing {filteredCards.length} cards
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-h-[600px] overflow-y-auto pr-1">
            {filteredCards.map((card, idx) => (
              <motion.div
                key={card.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.04 }}
                className={`bg-white rounded-2xl border p-5 shadow-2xs flex flex-col justify-between space-y-3 transition-all ${
                  card.mastered ? 'border-emerald-200 bg-emerald-50/20' : 'border-[#E7E1D8]'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[11px] font-black text-gray-400">Card #{idx + 1}</span>
                    {card.mastered ? (
                      <span className="text-[10px] font-black bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-md">
                        Mastered
                      </span>
                    ) : (
                      <span className="text-[10px] font-black bg-amber-100 text-amber-800 px-2 py-0.5 rounded-md">
                        Review Needed
                      </span>
                    )}
                  </div>
                  <h3 className="text-sm font-black text-[#20201D] mb-3">{cleanMarkdownText(card.front)}</h3>
                  <div className="bg-[#FAF8F3] p-3.5 rounded-2xl border border-gray-100">
                    <CardBackView rawContent={card.back} />
                  </div>
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-gray-100">
                  <button
                    onClick={() => handleAskTutorAboutCard(card)}
                    className="text-[11px] font-bold text-orange-600 hover:text-orange-700 flex items-center gap-1 cursor-pointer"
                  >
                    <MessageSquare size={12} /> Ask Tutor
                  </button>
                  <button
                    onClick={() => handleReview(!card.mastered, card.id)}
                    className={`text-[11px] font-bold px-2.5 py-1 rounded-lg transition-colors cursor-pointer ${
                      card.mastered
                        ? 'bg-red-50 text-red-600 hover:bg-red-100'
                        : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                    }`}
                  >
                    {card.mastered ? 'Mark for Review' : 'Mark as Mastered'}
                  </button>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      )}

      {/* ─── Celebration Completion Modal ─── */}
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
    </div>
  )
}
