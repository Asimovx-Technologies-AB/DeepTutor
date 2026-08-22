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
  Lightbulb,
} from 'lucide-react'
import { flashcardsApi } from '../services/api'
import { useSubjectStore } from '../stores/subjectStore'
import { useChatStore } from '../stores/chatStore'
import { useLanguageStore } from '../stores/languageStore'
import { useTranslation } from '../utils/translations'

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

function formatMarkdownBullets(rawText: string): string {
  if (!rawText) return ''
  let text = rawText.trim()
  
  // Normalize inline bullet symbols (•, ●) and glued emoji markers to linebreaks
  text = text.replace(/\s*[•●]\s*/g, '\n\n- ')
  text = text.replace(/([^\n])\s*(📌|💡|📐|⚠️|🎯|🔹|🔸|⚡|✅|⭐)/g, '$1\n\n- $2')
  
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean)
  const formatted = lines.map(line => {
    let cleaned = line.replace(/^[•●]\s*/, '').trim()
    if (!cleaned.startsWith('-') && !cleaned.startsWith('*')) {
      return `- ${cleaned}`
    }
    return cleaned
  })
  
  return formatted.join('\n\n')
}

/**
 * Parses and renders the point-by-point structured card back in clean, natural markdown.
 */
function CardBackView({ rawContent }: { rawContent: string }) {
  if (!rawContent) return null

  return (
    <div className="text-sm sm:text-[15px] text-slate-800 leading-relaxed font-medium markdown-content space-y-3 px-2 sm:px-4 py-2 w-full text-left">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
        {formatMarkdownBullets(rawContent)}
      </ReactMarkdown>
    </div>
  )
}

export default function FlashcardsPage() {
  const { topicId } = useParams<{ topicId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const activeSession = useChatStore((s) => s.activeSession)

  const { uiLanguage, aiLanguage } = useLanguageStore()
  const t = useTranslation(uiLanguage)

  const [currentIndex, setCurrentIndex] = useState(0)
  const [isFlipped, setIsFlipped] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [viewMode, setViewMode] = useState<'single' | 'grid'>('single')
  const [gridFilter, setGridFilter] = useState<'all' | 'unmastered' | 'mastered'>('all')
  const [generating, setGenerating] = useState(false)
  const [showCompletionModal, setShowCompletionModal] = useState(false)
  const [showHint, setShowHint] = useState(false)

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
      const res = await flashcardsApi.generate({ topic_id: topicId, language: aiLanguage })
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
      <div className="p-6 max-w-xl mx-auto text-center mt-12">
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          className="bg-white border border-border shadow-md p-10 text-center rounded-[2rem] relative overflow-hidden"
        >
          <div className="absolute top-0 left-0 w-full h-32 bg-gradient-to-b from-[#FAF8F3] to-transparent pointer-events-none" />
          <div className="relative z-10">
            <img src="/images/flashcards_empty.jpg" alt="Study Deck" className="w-56 h-56 mx-auto rounded-[2rem] shadow-xl mb-8 object-cover border-4 border-white" />
            <h2 className="text-2xl font-black text-text-primary mb-3">Ready to Master {topicTitle}?</h2>
            <p className="text-text-secondary text-sm font-medium mb-8 max-w-sm mx-auto leading-relaxed">
              Generate an AI-powered visual flashcard deck to review key formulas, definitions, and mental models.
            </p>
            <div className="flex items-center justify-center gap-4">
              <button
                onClick={handleBackToChat}
                className="flex items-center gap-2 text-xs font-bold text-text-secondary hover:text-text-primary py-4 px-6 rounded-2xl bg-white border-2 border-border shadow-sm hover:shadow-md transition-all cursor-pointer"
              >
                <ArrowLeft size={16} /> Back to Chat
              </button>
              <button
                onClick={() => generateMutation.mutate()}
                disabled={generating}
                className="btn-primary flex items-center gap-2 font-black py-4 px-8 rounded-2xl cursor-pointer shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all text-sm"
                style={{ background: theme.primary || '#4F46E5', color: 'white' }}
              >
                <Sparkles size={16} /> Generate AI Deck
              </button>
            </div>
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
    <div className="p-6 max-w-2xl mx-auto space-y-6 bg-transparent min-h-[calc(100vh-4rem)]">
      {/* Header */}
      <div className="flex items-center justify-between bg-white border border-border p-3 rounded-[1.5rem] shadow-sm">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-2 text-[#777777] hover:text-text-primary transition-colors text-xs font-black cursor-pointer px-4 py-2 rounded-xl hover:bg-gray-50 border border-transparent hover:border-border"
        >
          <ArrowLeft size={16} />
          <span>{uiLanguage === 'sv' ? 'Tillbaka till chatten' : 'Back to Chat'}</span>
        </button>

        <div className="flex items-center gap-3">
          {/* View Mode Toggle */}
          <button
            onClick={() => setViewMode(viewMode === 'single' ? 'grid' : 'single')}
            className={`text-[11px] px-5 py-2.5 rounded-xl font-black flex items-center gap-2 transition-all cursor-pointer ${viewMode === 'single' ? 'bg-[#20201D] text-white shadow-md' : 'bg-white border-2 border-border text-text-secondary hover:text-text-primary hover:border-[#20201D]'}`}
          >
            {viewMode === 'single' ? <Grid size={14} /> : <Layers size={14} />}
            <span>{viewMode === 'single' ? (uiLanguage === 'sv' ? 'Rutnät' : 'Grid View') : (uiLanguage === 'sv' ? 'Fokusläge' : 'Focus Mode')}</span>
          </button>

          <button
            onClick={() => generateMutation.mutate()}
            disabled={generating}
            className="text-[11px] px-5 py-2.5 rounded-xl font-black flex items-center gap-2 transition-all cursor-pointer bg-white border-2 border-border text-[#4F46E5] hover:bg-[#EEF2FF] hover:border-[#4F46E5] shadow-sm"
          >
            <RefreshCw size={13} className={generating ? 'animate-spin' : ''} />
            <span>{uiLanguage === 'sv' ? 'Generera om' : 'Regenerate'}</span>
          </button>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="bg-white p-6 rounded-[1.5rem] border border-border shadow-sm space-y-5">
        <div className="flex items-center justify-between text-xs font-black text-[#777777]">
          <span className="bg-transparent border border-border px-4 py-1.5 rounded-full text-text-secondary">
            {viewMode === 'single' ? (uiLanguage === 'sv' ? `Kort ${currentIndex + 1} av ${cards.length}` : `Card ${currentIndex + 1} of ${cards.length}`) : (uiLanguage === 'sv' ? `${cards.length} alla kort` : `${cards.length} Total Cards`)}
          </span>
          <span className="bg-emerald-50 text-emerald-700 border border-emerald-200 px-4 py-1.5 rounded-full flex items-center gap-1.5 shadow-xs">
            <CheckCircle2 size={14} /> {completionPercentage}% {uiLanguage === 'sv' ? 'Bemästrade' : 'Mastered'} ({masteredCount}/{cards.length})
          </span>
        </div>

        <div className="w-full h-4 bg-gray-100 rounded-full overflow-hidden shadow-inner border border-gray-200/60">
          <motion.div
            className="h-full bg-gradient-to-r from-emerald-400 to-emerald-500 rounded-full relative"
            animate={{ width: `${completionPercentage}%` }}
            transition={{ duration: 0.6, ease: "easeOut" }}
          >
            <div className="absolute inset-0 bg-white/20 w-full h-full" style={{ backgroundImage: 'linear-gradient(45deg, rgba(255,255,255,.15) 25%, transparent 25%, transparent 50%, rgba(255,255,255,.15) 50%, rgba(255,255,255,.15) 75%, transparent 75%, transparent)', backgroundSize: '1rem 1rem' }} />
          </motion.div>
        </div>
      </div>

      {/* ─── SINGLE FOCUS CARD VIEW (3D FLIP) ─── */}
      {viewMode === 'single' ? (
        <div className="space-y-5">
          {/* Card Counter */}
          <div className="flex items-center justify-between text-xs font-black text-gray-500 px-2">
            <span>{uiLanguage === 'sv' ? `Kort ${currentIndex + 1} av ${cards.length}` : `Card ${currentIndex + 1} of ${cards.length}`}</span>
            <span className="text-gray-400">{uiLanguage === 'sv' ? 'Tryck Blanksteg eller Klicka för att vända 🔄' : 'Press Space or Click to Flip 🔄'}</span>
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
              <div className="absolute inset-0 w-full h-full backface-hidden bg-white border border-[#E2E8F0] border-t-4 border-t-[#4F46E5] rounded-[2rem] p-8 flex flex-col justify-between elevation-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-xs text-[#4F46E5] font-black uppercase tracking-wider">
                    <HelpCircle size={14} /> {uiLanguage === 'sv' ? 'Begrepp / Fråga' : 'Concept / Question'}
                  </div>

                  <button
                    type="button"
                    onClick={(e) => speakText(currentCard?.front || '', e)}
                    className="p-2 rounded-[1.25rem] text-[#AFAFAF] hover:text-[#4F46E5] hover:bg-[#EEF2FF] transition-colors cursor-pointer"
                    title="Listen to card audio"
                  >
                    <Volume2 size={18} />
                  </button>
                </div>

                <div className="flex-1 flex flex-col items-center justify-center text-center my-3">
                  <h2 className="text-xl font-black text-[#3C3C3C] leading-relaxed px-4">
                    {currentCard?.front}
                  </h2>

                  {showHint && (
                    <motion.p
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="mt-4 text-xs text-[#FFC800] bg-[#FFF0B3] border border-[#FFC800]/30 rounded-[1.25rem] px-4 py-2 font-bold"
                    >
                      {uiLanguage === 'sv' ? '💡 Tänk efter noggrant på begreppet...' : '💡 Think about the concept carefully...'}
                    </motion.p>
                  )}
                  {currentCard?.mastered && (
                    <span className="text-[11px] font-black bg-emerald-50 text-emerald-700 border border-emerald-200 px-2.5 py-1 rounded-full flex items-center gap-1">
                      <Check size={12} /> {uiLanguage === 'sv' ? 'Bemästrad' : 'Mastered'}
                    </span>
                  )}
                </div>

                <div className="flex items-center justify-center pt-3 border-t border-[#E2E8F0]/60">
                  <p className="text-xs text-[#AFAFAF] font-semibold">{uiLanguage === 'sv' ? 'Klicka på kortet för att vända 🔄' : 'Click Card to Flip 🔄'}</p>
                </div>
              </div>

              {/* ─── Back Side (Structured Point-by-Point Answer) ─── */}
              <div
                className="absolute inset-0 w-full h-full backface-hidden bg-white border border-slate-200 border-t-4 border-t-emerald-500 rounded-[2rem] p-6 sm:p-8 flex flex-col justify-between shadow-xl overflow-y-auto"
                style={{ transform: 'rotateY(180deg)' }}
              >
                <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                  <div className="flex items-center gap-1.5 text-xs text-emerald-700 font-black uppercase tracking-wider bg-emerald-50 border border-emerald-200 px-3 py-1 rounded-full shadow-2xs">
                    <CheckCircle2 size={14} /> {uiLanguage === 'sv' ? 'Punkt-för-punkt lösning' : 'Point-by-Point Solution'}
                  </div>

                  <button
                    type="button"
                    onClick={(e) => speakText(currentCard?.back || '', e)}
                    className="p-2 rounded-xl text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors cursor-pointer"
                    title="Listen to answer audio"
                  >
                    <Volume2 size={18} />
                  </button>
                </div>

                <div className="flex-1 flex items-center justify-center my-3 w-full">
                  <CardBackView rawContent={currentCard?.back || ''} />
                </div>

                <div className="flex items-center justify-end pt-3 border-t border-slate-100">
                  <p className="text-xs text-slate-400 font-semibold">{uiLanguage === 'sv' ? 'Klicka på kortet för att vända tillbaka 🔄' : 'Click Card to Flip Back 🔄'}</p>
                </div>
              </div>
            </motion.div>
          </div>

          {/* ─── Review Confidence Buttons (3-Tier Spaced Repetition) ─── */}
          <div className="grid grid-cols-2 gap-4 pt-3">
            <button
              onClick={() => handleReview(false)}
              className="flex items-center justify-center gap-2 py-4 bg-white border-2 border-border text-text-secondary hover:border-red-400 hover:bg-red-50 hover:text-red-600 font-black rounded-[1.5rem] cursor-pointer transition-all shadow-sm hover:shadow-md hover:-translate-y-0.5"
            >
              <AlertCircle size={18} />
              <span>{uiLanguage === 'sv' ? 'Behöver öva (←)' : 'Needs Practice (←)'}</span>
            </button>
            <button
              onClick={() => handleReview(true)}
              className="flex items-center justify-center gap-2 py-4 font-black rounded-[1.5rem] cursor-pointer shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all bg-gradient-to-br from-emerald-400 to-emerald-500 text-white border-none"
            >
              <CheckCircle2 size={18} />
              <span>{uiLanguage === 'sv' ? 'Bemästrad! (→)' : 'Mastered! (→)'}</span>
            </button>
          </div>

          {/* Navigation */}
          <div className="flex items-center justify-between text-sm px-2 text-[#777777]">
            <button
              onClick={handlePrev}
              className="hover:text-[#4F46E5] font-black transition-colors flex items-center gap-1 cursor-pointer"
            >
              <ChevronLeft size={16} /> {uiLanguage === 'sv' ? 'Föregående kort' : 'Previous Card'}
            </button>
            <span className="text-xs text-[#AFAFAF]">{uiLanguage === 'sv' ? 'Kortkommandon: Blanksteg / Piltangenter' : 'Shortcuts: Space / Arrow Keys'}</span>
            <button
              onClick={handleNext}
              className="hover:text-[#4F46E5] font-black transition-colors flex items-center gap-1 cursor-pointer"
            >
              {uiLanguage === 'sv' ? 'Nästa kort' : 'Next Card'} <ChevronRight size={16} />
            </button>
          </div>
        </div>
      ) : (
        /* ─── INTERACTIVE CHEAT-SHEET GRID VIEW ─── */
        <div className="space-y-6">
          <div className="flex items-center gap-3 bg-white p-2.5 rounded-[1.5rem] border border-border shadow-sm w-fit mx-auto md:mx-0">
            {(['all', 'unmastered', 'mastered'] as const).map((filter) => (
              <button
                key={filter}
                onClick={() => setGridFilter(filter)}
                className={`text-xs px-5 py-2 rounded-xl font-black transition-all cursor-pointer ${gridFilter === filter
                  ? 'bg-[#20201D] text-white shadow-md'
                  : 'bg-transparent text-text-secondary hover:bg-gray-100 hover:text-text-primary'
                  }`}
              >
                {filter === 'all' ? (uiLanguage === 'sv' ? 'Alla' : 'All') : filter === 'unmastered' ? (uiLanguage === 'sv' ? 'Otränade' : 'Unmastered') : (uiLanguage === 'sv' ? 'Bemästrade' : 'Mastered')}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 max-h-[600px] overflow-y-auto pr-2 custom-scrollbar">
            {filteredCards.map((card, idx) => (
              <motion.div
                key={card.id}
                onClick={() => {
                  setCurrentIndex(cards.findIndex((c) => c.id === card.id))
                  setViewMode('single')
                  setIsFlipped(false)
                }}
                className={`p-6 rounded-[1.75rem] border-2 transition-all text-left cursor-pointer flex flex-col justify-between space-y-4 hover:-translate-y-1 hover:shadow-lg ${card.mastered
                  ? 'bg-emerald-50/50 border-emerald-200 hover:border-emerald-400'
                  : 'bg-white border-border hover:border-brand-primary'
                  }`}
              >
                <div>
                  <span className={`text-[10px] font-black uppercase tracking-wider block mb-3 px-2.5 py-1 rounded-md w-fit ${card.mastered ? 'bg-emerald-100 text-emerald-700' : 'bg-orange-100 text-orange-700'}`}>
                    {card.mastered ? (uiLanguage === 'sv' ? 'Bemästrad' : 'Mastered') : (uiLanguage === 'sv' ? 'Behöver repeteras' : 'Needs Review')}
                  </span>
                  <p className="text-[15px] font-black text-text-primary leading-snug">{card.front}</p>
                </div>
                <div className="pt-4 border-t border-border flex items-center justify-between">
                  <span className="text-[12px] text-text-secondary line-clamp-2 font-medium max-w-[65%]">{card.back}</span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      handleReview(!card.mastered, card.id)
                    }}
                    className={`p-2 rounded-xl border-2 flex-shrink-0 cursor-pointer ml-3 transition-colors ${card.mastered
                      ? 'bg-emerald-500 text-white border-emerald-500 hover:bg-emerald-600'
                      : 'bg-white text-text-secondary border-border hover:border-emerald-400 hover:text-emerald-500'
                      }`}
                  >
                    <CheckCircle2 size={16} />
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
          <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
            <motion.div
              initial={{ scale: 0.9, opacity: 0, y: 20 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.9, opacity: 0, y: -20 }}
              className="bg-white rounded-[2rem] p-10 max-w-md w-full text-center border border-border shadow-2xl relative overflow-hidden"
            >
              <div className="absolute top-0 left-0 w-full h-40 bg-gradient-to-b from-amber-50 to-transparent pointer-events-none" />
              <div className="relative z-10 space-y-6">
                <img src="/images/flashcards_trophy.jpg" alt="Completed" className="w-44 h-44 mx-auto rounded-[2rem] shadow-xl object-cover border-4 border-white mb-2" />

                <div>
                  <h2 className="text-2xl font-black text-text-primary">Deck Mastered! 🎉</h2>
                  <p className="text-sm text-text-secondary mt-2 font-medium">
                    You reviewed all {cards.length} cards for <span className="font-bold text-text-primary">{topicTitle}</span>.
                  </p>
                </div>

                <div className="bg-transparent p-5 rounded-[1.5rem] border border-border flex items-center justify-around shadow-inner">
                  <div className="text-center">
                    <p className="text-3xl font-black text-emerald-500">{masteredCount}</p>
                    <p className="text-[10px] uppercase font-black text-emerald-800 tracking-wider mt-1">Mastered</p>
                  </div>
                  <div className="w-px h-12 bg-[#E7E1D8]" />
                  <div className="text-center">
                    <p className="text-3xl font-black text-amber-500">{cards.length - masteredCount}</p>
                    <p className="text-[10px] uppercase font-black text-amber-800 tracking-wider mt-1">Needs Study</p>
                  </div>
                  <div className="w-px h-12 bg-[#E7E1D8]" />
                  <div className="text-center">
                    <p className="text-3xl font-black text-orange-500">+{cards.length * 5}</p>
                    <p className="text-[10px] uppercase font-black text-orange-800 tracking-wider mt-1">XP Earned</p>
                  </div>
                </div>

                <div className="flex gap-4 pt-3">
                  <button
                    onClick={() => {
                      setShowCompletionModal(false)
                      setCurrentIndex(0)
                      setIsFlipped(false)
                    }}
                    className="flex-1 py-4 px-4 rounded-2xl border-2 border-border bg-white font-black text-sm text-text-secondary hover:border-[#20201D] hover:text-text-primary flex items-center justify-center gap-2 cursor-pointer shadow-sm hover:shadow-md transition-all"
                  >
                    <RotateCcw size={16} /> Review Again
                  </button>
                  <button
                    onClick={handleBackToChat}
                    className="flex-1 py-4 px-4 rounded-2xl bg-[#20201D] hover:bg-black text-white font-black text-sm flex items-center justify-center gap-2 cursor-pointer shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all"
                  >
                    <ArrowLeft size={16} /> Back to Chat
                  </button>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div >
  )
}
