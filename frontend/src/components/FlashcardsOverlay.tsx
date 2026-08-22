import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import {
  BookOpen,
  X,
  Sparkles,
  RefreshCw,
  RotateCcw,
  ChevronLeft,
  ChevronRight,
  Layers,
  CheckCircle2,
  Brain
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useChatStore } from '../stores/chatStore'
import { useLanguageStore } from '../stores/languageStore'
import { useTranslation } from '../utils/translations'
import { flashcardsApi, quizApi } from '../services/api'
import { useQueryClient } from '@tanstack/react-query'

interface Flashcard {
  id: string
  topic_id: string
  front: string
  back: string
  mastered: boolean
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

interface Props {
  sessionId?: string
  isOpen: boolean
  onClose: () => void
}

export default function FlashcardsOverlay({ sessionId, isOpen, onClose }: Props) {
  const activeSession = useChatStore((s) => s.activeSession)
  const queryClient = useQueryClient()
  const { uiLanguage, aiLanguage } = useLanguageStore()
  const t = useTranslation(uiLanguage)

  const [cards, setCards] = useState<Flashcard[]>([])
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)

  // Interactive View States
  const [setupStep, setSetupStep] = useState(true)
  const [scopeMode, setScopeMode] = useState<'all' | 'specific'>('all')
  const [availableTopics, setAvailableTopics] = useState<string[]>([])
  const [selectedTopic, setSelectedTopic] = useState<string>('')
  const [customTopic, setCustomTopic] = useState<string>('')

  // Card interaction state
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isFlipped, setIsFlipped] = useState(false)

  useEffect(() => {
    if (!isOpen) return
    const fetchTopics = async () => {
      try {
        const res = await quizApi.suggestions({
          session_id: sessionId || activeSession?.id,
          topic_id: activeSession?.topic_id,
        })
        const suggestions: string[] = res.data?.suggestions || []
        setAvailableTopics(suggestions)
        if (suggestions.length > 0) setSelectedTopic(suggestions[0])
      } catch {
        setAvailableTopics(['Transformer Architecture', 'Self-Attention Mechanism', 'RLHF Tuning'])
      }
    }
    fetchTopics()
  }, [isOpen, sessionId, activeSession])

  const triggerGenerate = async () => {
    setGenerating(true)
    const effectiveTopic =
      scopeMode === 'all'
        ? 'Entire PDF'
        : customTopic.trim() || selectedTopic || 'General Study Concepts'

    try {
      const res = await flashcardsApi.generate({
        session_id: sessionId || activeSession?.id,
        topic_id: activeSession?.topic_id || 'general',
        custom_topic: effectiveTopic,
        num_cards: 5,
        language: aiLanguage,
      })
      setCards(res.data || [])
      setCurrentIndex(0)
      setIsFlipped(false)
      setSetupStep(false)
      queryClient.invalidateQueries({ queryKey: ['progress-summary'] })
      queryClient.invalidateQueries({ queryKey: ['progress-calendar'] })
    } catch (err: any) {
      console.error(err)
      alert(err.response?.data?.detail || 'Failed to generate flashcards. Make sure you have uploaded a PDF document and Ollama is running.')
      setSetupStep(true)
    } finally {
      setGenerating(false)
    }
  }

  const handleNext = () => {
    if (currentIndex < cards.length - 1) {
      setCurrentIndex((i) => i + 1)
      setIsFlipped(false)
    }
  }

  const handlePrev = () => {
    if (currentIndex > 0) {
      setCurrentIndex((i) => i - 1)
      setIsFlipped(false)
    }
  }

  if (!isOpen) return null

  const currentCard = cards[currentIndex]
  const totalCards = cards.length
  const progressPct = totalCards > 0 ? Math.round(((currentIndex + 1) / totalCards) * 100) : 0

  return (
    <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-md flex items-center justify-center p-4 sm:p-6">
      <motion.div
        initial={{ opacity: 0, scale: 0.94, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.94, y: 12 }}
        transition={{ duration: 0.25, ease: 'easeOut' }}
        className="w-full max-w-lg sm:max-w-xl bg-white/80 backdrop-blur-2xl backdrop-saturate-150 rounded-3xl border border-white/70 shadow-[0_25px_60px_-15px_rgba(0,0,0,0.2),0_0_0_1px_rgba(255,255,255,0.9)_inset] p-6 sm:p-8 flex flex-col relative max-h-[90vh] overflow-y-auto text-left"
      >
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-5 right-5 w-9 h-9 rounded-full bg-white/80 backdrop-blur-md hover:bg-white text-[#6F6B63] hover:text-[#20201D] border border-white/80 flex items-center justify-center transition-all z-20 cursor-pointer shadow-xs"
          title="Close modal"
        >
          <X size={18} />
        </button>

        {setupStep || totalCards === 0 ? (
          /* ─── SETUP / GENERATOR VIEW ─── */
          <div className="space-y-6">
            <div className="flex items-start gap-3.5 border-b border-slate-200/60 pb-5 pr-8">
              <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-50 to-white/90 backdrop-blur-md border border-indigo-200 text-indigo-600 flex items-center justify-center flex-shrink-0 shadow-xs">
                <BookOpen size={22} />
              </div>
              <div className="space-y-0.5">
                <h2 className="text-xl sm:text-2xl font-black text-slate-800 tracking-tight">{t.flashcards.title}</h2>
                <p className="text-xs sm:text-sm text-slate-500 font-medium leading-relaxed">
                  {t.flashcards.subtitle}
                </p>
              </div>
            </div>

            {/* Scope Selection */}
            <div className="space-y-2.5">
              <label className="text-xs font-black text-slate-800 uppercase tracking-wider block">
                1. {uiLanguage === 'sv' ? 'VÄLJ STUDIEOMRÅDE' : 'SELECT FLASHCARD SCOPE'}
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                <button
                  type="button"
                  onClick={() => setScopeMode('all')}
                  className={`p-4 rounded-2xl border text-left transition-all flex items-start gap-3.5 cursor-pointer select-none ${
                    scopeMode === 'all'
                      ? 'border-2 border-indigo-600 bg-indigo-50/90 backdrop-blur-md text-slate-800 shadow-[0_4px_20px_rgba(79,70,229,0.18)]'
                      : 'border border-white/80 bg-white/60 backdrop-blur-md hover:bg-white/90 text-slate-600 hover:border-white shadow-2xs'
                  }`}
                >
                  <div className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 ${
                    scopeMode === 'all' ? 'bg-indigo-600 text-white shadow-xs' : 'bg-white/80 text-slate-500 shadow-2xs border border-white'
                  }`}>
                    <Layers size={16} />
                  </div>
                  <div>
                    <p className="text-sm font-black text-slate-800">{uiLanguage === 'sv' ? 'Hela dokumentet' : 'Entire Document'}</p>
                    <p className="text-xs text-slate-500 mt-0.5 font-medium">{uiLanguage === 'sv' ? 'Alla avsnitt sammanslagna' : 'All topics combined'}</p>
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => setScopeMode('specific')}
                  className={`p-4 rounded-2xl border text-left transition-all flex items-start gap-3.5 cursor-pointer select-none ${
                    scopeMode === 'specific'
                      ? 'border-2 border-indigo-600 bg-indigo-50/90 backdrop-blur-md text-slate-800 shadow-[0_4px_20px_rgba(79,70,229,0.18)]'
                      : 'border border-white/80 bg-white/60 backdrop-blur-md hover:bg-white/90 text-slate-600 hover:border-white shadow-2xs'
                  }`}
                >
                  <div className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 ${
                    scopeMode === 'specific' ? 'bg-indigo-600 text-white shadow-xs' : 'bg-white/80 text-slate-500 shadow-2xs border border-white'
                  }`}>
                    <Sparkles size={16} />
                  </div>
                  <div>
                    <p className="text-sm font-black text-slate-800">{uiLanguage === 'sv' ? 'Specifikt begrepp' : 'Specific Concept'}</p>
                    <p className="text-xs text-slate-500 mt-0.5 font-medium">{uiLanguage === 'sv' ? 'Fokusera på 1 ämne' : 'Target 1 topic'}</p>
                  </div>
                </button>
              </div>
            </div>

            {scopeMode === 'specific' && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="space-y-3 pt-1">
                <label className="text-xs font-black text-slate-800 uppercase tracking-wider block">
                  2. {uiLanguage === 'sv' ? 'VÄLJ SPECIFIKT BEGREPP' : 'CHOOSE SPECIFIC CONCEPT'}
                </label>
                {availableTopics.length > 0 && (
                  <div className="flex flex-wrap gap-2 max-h-28 overflow-y-auto p-1">
                    {availableTopics.map((topic) => (
                      <button
                        key={topic}
                        type="button"
                        onClick={() => { setSelectedTopic(topic); setCustomTopic(topic); }}
                        className={`text-xs px-3.5 py-1.5 rounded-xl border transition-all cursor-pointer font-bold ${
                          customTopic === topic
                            ? 'bg-indigo-600 text-white border-indigo-600 shadow-xs'
                            : 'bg-white/70 backdrop-blur-sm text-slate-600 border-white/80 hover:bg-white hover:text-slate-800'
                        }`}
                      >
                        {topic}
                      </button>
                    ))}
                  </div>
                )}
                <input
                  type="text"
                  value={customTopic}
                  onChange={(e) => setCustomTopic(e.target.value)}
                  placeholder={uiLanguage === 'sv' ? 'Eller skriv begreppsnamn...' : 'Or type topic name...'}
                  className="w-full bg-white/70 backdrop-blur-md border border-white/90 rounded-2xl px-4 py-3 text-xs sm:text-sm font-medium text-slate-800 outline-none focus:bg-white focus:border-indigo-600 shadow-xs placeholder-slate-400"
                />
              </motion.div>
            )}

            <button
              onClick={triggerGenerate}
              disabled={generating}
              className="btn-primary w-full py-4 px-6 rounded-2xl font-black text-sm sm:text-base flex items-center justify-center gap-2.5 shadow-md shadow-indigo-600/25 hover:shadow-lg transition-all cursor-pointer disabled:opacity-50 mt-4"
            >
              {generating ? (
                <>
                  <RefreshCw size={18} className="animate-spin text-white" />
                  <span>{uiLanguage === 'sv' ? 'Skapar studiekort...' : 'Generating Study Cards...'}</span>
                </>
              ) : (
                <>
                  <Sparkles size={18} />
                  <span>{uiLanguage === 'sv' ? 'Generera studiekort' : 'Generate Flashcards'}</span>
                </>
              )}
            </button>
          </div>
        ) : (
          /* ─── ACTIVE FLASHCARDS VIEW ─── */
          <div className="space-y-6">
            
            {/* FLASHCARD PROGRESS Header & Progress Bar */}
            <div className="space-y-2 pr-12">
              <div className="flex items-center justify-between text-xs font-black uppercase tracking-wider text-slate-500">
                <span>Card {currentIndex + 1} of {totalCards}</span>
                <span className="text-indigo-600 font-black">{progressPct}% Completed</span>
              </div>
              <div className="w-full bg-slate-200/60 backdrop-blur-sm border border-white/60 rounded-full h-3 p-0.5 overflow-hidden">
                <div
                  className="bg-indigo-600 h-full rounded-full transition-all duration-500"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
            </div>

            {/* Interactive Flip Card Container */}
            <div
              onClick={() => setIsFlipped(!isFlipped)}
              className="w-full bg-white/60 backdrop-blur-xl border border-white/90 hover:border-indigo-400/50 rounded-3xl p-5 sm:p-7 text-center flex flex-col items-center justify-center min-h-[280px] cursor-pointer transition-all relative overflow-hidden group select-none shadow-sm"
            >
              <div className="absolute top-4 right-4 text-[11px] font-black text-slate-500 bg-white border border-slate-200 px-3 py-1 rounded-full flex items-center gap-1.5 shadow-2xs">
                <RotateCcw size={12} className="text-indigo-600" />
                <span>Click to Flip</span>
              </div>

              <AnimatePresence mode="wait">
                {!isFlipped ? (
                  <motion.div
                    key="front"
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    transition={{ duration: 0.2 }}
                    className="space-y-3 max-w-xl mx-auto py-6"
                  >
                    <span className="text-xs font-black text-indigo-600 uppercase tracking-wider bg-indigo-50 border border-indigo-200 px-3.5 py-1 rounded-full">
                      Concept / Question
                    </span>
                    <h2 className="text-lg sm:text-xl font-black text-slate-800 leading-snug pt-2">
                      {currentCard?.front}
                    </h2>
                  </motion.div>
                ) : (
                  <motion.div
                    key="back"
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    transition={{ duration: 0.2 }}
                    className="space-y-3 w-full text-left max-w-xl mx-auto"
                  >
                    <div className="text-center mb-1">
                      <span className="text-xs font-black text-emerald-700 uppercase tracking-wider bg-emerald-50 border border-emerald-200 px-3.5 py-1 rounded-full inline-flex items-center gap-1.5 shadow-2xs">
                        <CheckCircle2 size={13} />
                        Point-by-Point Solution
                      </span>
                    </div>
                    
                    <div className="text-sm sm:text-[15px] text-slate-800 leading-relaxed font-medium markdown-content space-y-3.5 px-2 sm:px-4 py-2">
                      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                        {formatMarkdownBullets(currentCard?.back || '')}
                      </ReactMarkdown>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Navigation & Action Buttons */}
            <div className="flex items-center justify-between pt-2">
              <button
                onClick={handlePrev}
                disabled={currentIndex === 0}
                className="flex items-center gap-2 px-5 py-3 rounded-2xl border border-slate-200 bg-white/70 text-slate-800 text-xs font-black hover:bg-white disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-2xs cursor-pointer"
              >
                <ChevronLeft size={16} />
                <span>Previous</span>
              </button>

              <button
                onClick={() => setIsFlipped(!isFlipped)}
                className="btn-primary font-black px-7 py-3 rounded-2xl text-xs sm:text-sm shadow-md shadow-indigo-600/25 cursor-pointer"
              >
                {isFlipped ? 'Show Question' : 'Reveal Answer'}
              </button>

              <button
                onClick={handleNext}
                disabled={currentIndex === totalCards - 1}
                className="flex items-center gap-2 px-5 py-3 rounded-2xl border border-slate-200 bg-white/70 text-slate-800 text-xs font-black hover:bg-white disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-2xs cursor-pointer"
              >
                <span>Next</span>
                <ChevronRight size={16} />
              </button>
            </div>

          </div>
        )}
      </motion.div>
    </div>
  )
}
