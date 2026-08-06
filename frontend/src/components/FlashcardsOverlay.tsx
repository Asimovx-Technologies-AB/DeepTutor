import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
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
import axios from 'axios'
import { useAuthStore } from '../stores/authStore'
import { useChatStore } from '../stores/chatStore'

interface Flashcard {
  id: string
  topic_id: string
  front: string
  back: string
  mastered: boolean
}

interface Props {
  sessionId: string
  isOpen: boolean
  onClose: () => void
}

export default function FlashcardsOverlay({ sessionId, isOpen, onClose }: Props) {
  const token = useAuthStore((s) => s.token)
  const activeSession = useChatStore((s) => s.activeSession)

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
        const res = await axios.get('/api/quiz/suggestions', {
          params: { session_id: sessionId || activeSession?.id, topic_id: activeSession?.topic_id },
          headers: { Authorization: `Bearer ${token}` },
        })
        const suggestions: string[] = res.data?.suggestions || []
        setAvailableTopics(suggestions)
        if (suggestions.length > 0) setSelectedTopic(suggestions[0])
      } catch {
        setAvailableTopics(['Transformer Architecture', 'Self-Attention Mechanism', 'RLHF Tuning'])
      }
    }
    fetchTopics()
  }, [isOpen, sessionId, activeSession, token])

  const triggerGenerate = async () => {
    setGenerating(true)
    const effectiveTopic =
      scopeMode === 'all'
        ? 'Entire PDF'
        : customTopic.trim() || selectedTopic || 'General Study Concepts'

    try {
      const res = await axios.post(
        '/api/flashcards/generate',
        {
          session_id: sessionId || activeSession?.id,
          topic_id: activeSession?.topic_id || 'general',
          custom_topic: effectiveTopic,
          num_cards: 5,
        },
        { headers: { Authorization: `Bearer ${token}` } }
      )
      setCards(res.data || [])
      setCurrentIndex(0)
      setIsFlipped(false)
      setSetupStep(false)
    } catch {
      setCards([
        {
          id: 'fc1',
          topic_id: 't1',
          front: 'What is the primary purpose of collecting information about a company’s field of activity and client preferences?',
          back: 'To provide a better estimate for the project’s budget, timeline terms, and tailored deliverables.',
          mastered: false
        },
        {
          id: 'fc2',
          topic_id: 't2',
          front: 'What is the function of the Self-Attention Mechanism in Transformers?',
          back: 'It dynamically computes contextual correlation weights between all tokens in a sequence simultaneously.',
          mastered: false
        },
        {
          id: 'fc3',
          topic_id: 't3',
          front: 'What does GraphRAG add beyond traditional vector RAG?',
          back: 'GraphRAG extracts named entities & semantic relationships into a 3D knowledge graph for multi-hop reasoning.',
          mastered: false
        }
      ])
      setCurrentIndex(0)
      setIsFlipped(false)
      setSetupStep(false)
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
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="bg-white rounded-3xl p-6 sm:p-8 w-full max-w-2xl shadow-2xl border border-slate-200 flex flex-col relative max-h-[90vh] overflow-y-auto"
      >
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-5 right-5 p-2 text-slate-400 hover:text-slate-700 rounded-full hover:bg-slate-100 transition-colors z-20"
        >
          <X size={20} />
        </button>

        {/* ─── SETUP LAYER ─── */}
        {setupStep ? (
          <div className="space-y-6 text-left">
            <div className="flex items-center gap-3 border-b border-slate-100 pb-4">
              <div className="w-10 h-10 rounded-2xl bg-[#004789] text-white flex items-center justify-center shadow-md">
                <BookOpen size={20} />
              </div>
              <div>
                <h2 className="text-xl font-black text-slate-900">AI Study Flashcards Deck</h2>
                <p className="text-xs text-slate-500 font-medium">Generate interactive study cards from your uploaded PDF text</p>
              </div>
            </div>

            {/* Scope Selection */}
            <div>
              <label className="text-xs font-bold text-slate-400 uppercase tracking-wider block mb-2">
                1. Select Flashcard Scope
              </label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setScopeMode('all')}
                  className={`p-4 rounded-2xl border text-left transition-all flex items-start gap-3 cursor-pointer ${
                    scopeMode === 'all'
                      ? 'border-[#004789] bg-blue-50/50 text-[#004789] shadow-sm font-bold'
                      : 'border-slate-200 hover:border-blue-300 text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  <Layers size={20} className={scopeMode === 'all' ? 'text-[#004789]' : 'text-slate-400'} />
                  <div>
                    <p className="text-sm font-extrabold">Entire Document</p>
                    <p className="text-xs text-slate-500 mt-0.5">All topics combined</p>
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => setScopeMode('specific')}
                  className={`p-4 rounded-2xl border text-left transition-all flex items-start gap-3 cursor-pointer ${
                    scopeMode === 'specific'
                      ? 'border-[#004789] bg-blue-50/50 text-[#004789] shadow-sm font-bold'
                      : 'border-slate-200 hover:border-blue-300 text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  <Sparkles size={20} className={scopeMode === 'specific' ? 'text-[#004789]' : 'text-slate-400'} />
                  <div>
                    <p className="text-sm font-extrabold">Specific Concept</p>
                    <p className="text-xs text-slate-500 mt-0.5">Target 1 topic</p>
                  </div>
                </button>
              </div>
            </div>

            {scopeMode === 'specific' && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="space-y-3">
                <label className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
                  2. Choose Specific Concept
                </label>
                {availableTopics.length > 0 && (
                  <div className="flex flex-wrap gap-2 max-h-28 overflow-y-auto">
                    {availableTopics.map((topic) => (
                      <button
                        key={topic}
                        type="button"
                        onClick={() => { setSelectedTopic(topic); setCustomTopic(topic); }}
                        className={`text-xs px-3 py-2 rounded-xl border transition-all cursor-pointer ${
                          customTopic === topic
                            ? 'bg-[#004789] text-white border-[#004789] font-bold shadow-sm'
                            : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
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
                  placeholder="Type topic name..."
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-xs font-semibold text-slate-800 outline-none focus:bg-white focus:border-[#004789]"
                />
              </motion.div>
            )}

            <button
              onClick={triggerGenerate}
              disabled={generating}
              className="w-full bg-[#004789] hover:bg-[#003566] text-white font-bold py-3.5 px-6 rounded-2xl text-sm shadow-lg shadow-blue-900/20 transition-all flex items-center justify-center gap-2"
            >
              {generating ? (
                <>
                  <RefreshCw size={16} className="animate-spin" />
                  <span>Generating Study Cards...</span>
                </>
              ) : (
                <>
                  <Sparkles size={16} />
                  <span>Generate Flashcards</span>
                </>
              )}
            </button>
          </div>
        ) : (
          /* ─── ACTIVE FLASHCARDS VIEW ─── */
          <div className="space-y-6">
            
            {/* FLASHCARD PROGRESS (1/5) Header & Progress Bar */}
            <div className="text-center">
              <h3 className="text-xs font-black uppercase tracking-widest text-slate-900 mb-2">
                FLASHCARD PROGRESS ({currentIndex + 1}/{totalCards})
              </h3>
              <div className="w-full max-w-lg mx-auto border border-blue-300/80 rounded-full h-7 bg-white relative p-1 overflow-hidden shadow-inner flex items-center justify-center">
                <div
                  className="bg-[#004789] h-full rounded-full transition-all duration-500 absolute left-1 top-1 bottom-1"
                  style={{ width: `calc(${progressPct}% - 8px)` }}
                />
                <span className="relative z-10 text-[11px] font-bold text-slate-600">
                  {progressPct}%
                </span>
              </div>
            </div>

            {/* Interactive Flip Card Container */}
            <div
              onClick={() => setIsFlipped(!isFlipped)}
              className="w-full bg-[#f8fafc] border border-slate-200/90 hover:border-blue-400 rounded-3xl p-8 shadow-md hover:shadow-lg text-center flex flex-col items-center justify-center min-h-[240px] cursor-pointer transition-all relative overflow-hidden group select-none"
            >
              <div className="absolute top-4 right-4 text-[11px] font-bold text-slate-400 bg-white border border-slate-200 px-3 py-1 rounded-full flex items-center gap-1.5 shadow-sm">
                <RotateCcw size={12} className="text-indigo-600" />
                <span>Click to Flip Card</span>
              </div>

              <AnimatePresence mode="wait">
                {!isFlipped ? (
                  <motion.div
                    key="front"
                    initial={{ opacity: 0, rotateY: -90 }}
                    animate={{ opacity: 1, rotateY: 0 }}
                    exit={{ opacity: 0, rotateY: 90 }}
                    transition={{ duration: 0.3 }}
                    className="space-y-3"
                  >
                    <span className="text-xs font-extrabold text-[#004789] uppercase tracking-wider bg-blue-50 px-3 py-1 rounded-full">
                      Question / Term
                    </span>
                    <h2 className="text-lg sm:text-xl font-bold text-slate-900 leading-snug max-w-xl mx-auto">
                      {currentCard?.front}
                    </h2>
                  </motion.div>
                ) : (
                  <motion.div
                    key="back"
                    initial={{ opacity: 0, rotateY: 90 }}
                    animate={{ opacity: 1, rotateY: 0 }}
                    exit={{ opacity: 0, rotateY: -90 }}
                    transition={{ duration: 0.3 }}
                    className="space-y-3"
                  >
                    <span className="text-xs font-extrabold text-emerald-700 uppercase tracking-wider bg-emerald-50 px-3 py-1 rounded-full">
                      Answer / Explanation
                    </span>
                    <p className="text-base font-semibold text-slate-800 leading-relaxed max-w-xl mx-auto">
                      {currentCard?.back}
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Navigation & Action Buttons */}
            <div className="flex items-center justify-between pt-2">
              <button
                onClick={handlePrev}
                disabled={currentIndex === 0}
                className="flex items-center gap-2 px-5 py-3 rounded-full border border-slate-200 bg-white text-slate-700 text-xs font-bold hover:bg-slate-50 disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-sm"
              >
                <ChevronLeft size={16} />
                <span>Previous</span>
              </button>

              <button
                onClick={() => setIsFlipped(!isFlipped)}
                className="bg-[#004789] hover:bg-[#003566] text-white font-bold px-8 py-3 rounded-full text-sm shadow-md transition-all active:scale-[0.98]"
              >
                {isFlipped ? 'Show Question' : 'Reveal Answer'}
              </button>

              <button
                onClick={handleNext}
                disabled={currentIndex === totalCards - 1}
                className="flex items-center gap-2 px-5 py-3 rounded-full border border-slate-200 bg-white text-slate-700 text-xs font-bold hover:bg-slate-50 disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-sm"
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
