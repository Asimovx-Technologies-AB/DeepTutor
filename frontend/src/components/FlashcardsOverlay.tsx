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
import { useAuthStore } from '../stores/authStore'
import { useChatStore } from '../stores/chatStore'
import { flashcardsApi, quizApi } from '../services/api'
import { useQueryClient } from '@tanstack/react-query'

interface Flashcard {
  id: string
  topic_id: string
  front: string
  back: string
  mastered: boolean
}

interface Props {
  sessionId?: string
  isOpen: boolean
  onClose: () => void
}

export default function FlashcardsOverlay({ sessionId, isOpen, onClose }: Props) {
  const activeSession = useChatStore((s) => s.activeSession)
  const queryClient = useQueryClient()

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
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="bg-white rounded-3xl p-6 sm:p-8 w-full max-w-2xl shadow-2xl border border-[#E7E1D8] flex flex-col relative max-h-[90vh] overflow-y-auto text-left"
      >
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-5 right-5 p-2 text-[#969188] hover:text-[#20201D] rounded-full hover:bg-[#FAF8F3] transition-colors z-20 cursor-pointer"
        >
          <X size={20} />
        </button>

        {setupStep || totalCards === 0 ? (
          /* ─── SETUP / GENERATOR VIEW ─── */
          <div className="space-y-6">
            <div className="flex items-center gap-3 border-b border-[#E7E1D8] pb-4">
              <div className="w-10 h-10 rounded-2xl bg-[#FFF0E4] border border-[#F28A45]/30 text-[#F28A45] flex items-center justify-center shadow-2xs">
                <BookOpen size={20} />
              </div>
              <div>
                <h2 className="text-xl font-black text-[#20201D]">AI Study Flashcards Deck</h2>
                <p className="text-xs text-[#6F6B63] font-medium">Generate interactive study cards from your uploaded PDF text</p>
              </div>
            </div>

            {/* Scope Selection */}
            <div>
              <label className="text-xs font-black text-[#969188] uppercase tracking-wider block mb-2">
                1. Select Flashcard Scope
              </label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setScopeMode('all')}
                  className={`p-4 rounded-2xl border text-left transition-all flex items-start gap-3 cursor-pointer ${
                    scopeMode === 'all'
                      ? 'border-[#F28A45] bg-[#FFF0E4]/60 text-[#F28A45] shadow-2xs font-black'
                      : 'border-[#E7E1D8] hover:border-[#F28A45]/40 text-[#20201D] hover:bg-[#FFF9F2]'
                  }`}
                >
                  <Layers size={20} className={scopeMode === 'all' ? 'text-[#F28A45]' : 'text-[#969188]'} />
                  <div>
                    <p className="text-sm font-black">Entire Document</p>
                    <p className="text-xs text-[#6F6B63] mt-0.5 font-medium">All topics combined</p>
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => setScopeMode('specific')}
                  className={`p-4 rounded-2xl border text-left transition-all flex items-start gap-3 cursor-pointer ${
                    scopeMode === 'specific'
                      ? 'border-[#F28A45] bg-[#FFF0E4]/60 text-[#F28A45] shadow-2xs font-black'
                      : 'border-[#E7E1D8] hover:border-[#F28A45]/40 text-[#20201D] hover:bg-[#FFF9F2]'
                  }`}
                >
                  <Sparkles size={20} className={scopeMode === 'specific' ? 'text-[#F28A45]' : 'text-[#969188]'} />
                  <div>
                    <p className="text-sm font-black">Specific Concept</p>
                    <p className="text-xs text-[#6F6B63] mt-0.5 font-medium">Target 1 topic</p>
                  </div>
                </button>
              </div>
            </div>

            {scopeMode === 'specific' && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="space-y-3">
                <label className="text-xs font-black text-[#969188] uppercase tracking-wider block">
                  2. Choose Specific Concept
                </label>
                {availableTopics.length > 0 && (
                  <div className="flex flex-wrap gap-2 max-h-28 overflow-y-auto">
                    {availableTopics.map((topic) => (
                      <button
                        key={topic}
                        type="button"
                        onClick={() => { setSelectedTopic(topic); setCustomTopic(topic); }}
                        className={`text-xs px-3 py-2 rounded-xl border transition-all cursor-pointer font-bold ${
                          customTopic === topic
                            ? 'bg-[#F28A45] text-white border-[#F28A45] shadow-2xs'
                            : 'bg-[#FAF8F3] text-[#20201D] border-[#E7E1D8] hover:bg-[#F4EFE7]'
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
                  className="w-full bg-[#FAF8F3] border border-[#E7E1D8] rounded-xl px-4 py-3 text-xs font-bold text-[#20201D] outline-none focus:bg-white focus:border-[#F28A45]"
                />
              </motion.div>
            )}

            <button
              onClick={triggerGenerate}
              disabled={generating}
              className="btn-primary w-full py-3.5 px-6 font-black text-sm shadow-2xs flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
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
              <h3 className="text-xs font-black uppercase tracking-widest text-[#20201D] mb-2">
                FLASHCARD PROGRESS ({currentIndex + 1}/{totalCards})
              </h3>
              <div className="w-full max-w-lg mx-auto border border-[#E7E1D8] rounded-full h-7 bg-[#F4EFE7] relative p-1 overflow-hidden flex items-center justify-center">
                <div
                  className="bg-[#F28A45] h-full rounded-full transition-all duration-500 absolute left-1 top-1 bottom-1"
                  style={{ width: `calc(${progressPct}% - 8px)` }}
                />
                <span className="relative z-10 text-[11px] font-black text-[#20201D]">
                  {progressPct}%
                </span>
              </div>
            </div>

            {/* Interactive Flip Card Container */}
            <div
              onClick={() => setIsFlipped(!isFlipped)}
              className="w-full bg-[#FAF8F3] border border-[#E7E1D8] hover:border-[#F28A45]/50 rounded-3xl p-8 shadow-2xs text-center flex flex-col items-center justify-center min-h-[240px] cursor-pointer transition-all relative overflow-hidden group select-none"
            >
              <div className="absolute top-4 right-4 text-[11px] font-extrabold text-[#969188] bg-white border border-[#E7E1D8] px-3 py-1 rounded-full flex items-center gap-1.5 shadow-2xs">
                <RotateCcw size={12} className="text-[#F28A45]" />
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
                    <span className="text-xs font-black text-[#F28A45] uppercase tracking-wider bg-[#FFF0E4] border border-[#F28A45]/20 px-3 py-1 rounded-full">
                      Question / Term
                    </span>
                    <h2 className="text-lg sm:text-xl font-black text-[#20201D] leading-snug max-w-xl mx-auto">
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
                    <span className="text-xs font-black text-[#4F8A68] uppercase tracking-wider bg-[#E3F0E5] border border-[#4F8A68]/20 px-3 py-1 rounded-full">
                      Answer / Explanation
                    </span>
                    <p className="text-base font-bold text-[#20201D] leading-relaxed max-w-xl mx-auto">
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
                className="flex items-center gap-2 px-5 py-3 rounded-full border border-[#E7E1D8] bg-white text-[#20201D] text-xs font-extrabold hover:bg-[#FFF9F2] disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-2xs cursor-pointer"
              >
                <ChevronLeft size={16} />
                <span>Previous</span>
              </button>

              <button
                onClick={() => setIsFlipped(!isFlipped)}
                className="btn-primary font-black px-8 py-3 rounded-full text-sm shadow-2xs cursor-pointer"
              >
                {isFlipped ? 'Show Question' : 'Reveal Answer'}
              </button>

              <button
                onClick={handleNext}
                disabled={currentIndex === totalCards - 1}
                className="flex items-center gap-2 px-5 py-3 rounded-full border border-[#E7E1D8] bg-white text-[#20201D] text-xs font-extrabold hover:bg-[#FFF9F2] disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-2xs cursor-pointer"
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
