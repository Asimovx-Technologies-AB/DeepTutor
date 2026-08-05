import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  BookOpen,
  X,
  Sparkles,
  RefreshCw,
  HelpCircle,
  CheckCircle2,
  AlertCircle,
  Volume2,
  Lightbulb,
  Grid,
  Layers,
  SlidersHorizontal,
  Target,
  ChevronLeft,
  ChevronRight
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

  // Interactive View Modes
  const [setupStep, setSetupStep] = useState(true) // Setup / Topic Selection screen
  const [viewMode, setViewMode] = useState<'single' | 'grid'>('single') // Single flip vs Deck grid
  const [gridFilter, setGridFilter] = useState<'all' | 'unmastered' | 'mastered'>('all')

  // Setup / Topic Scope state
  const [scopeMode, setScopeMode] = useState<'all' | 'specific'>('all')
  const [availableTopics, setAvailableTopics] = useState<string[]>([])
  const [selectedTopic, setSelectedTopic] = useState<string>('')
  const [customTopic, setCustomTopic] = useState<string>('')

  // Card interaction state
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isFlipped, setIsFlipped] = useState(false)
  const [showHint, setShowHint] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)

  // Fetch topics from knowledge graph for active session
  useEffect(() => {
    if (!isOpen || !activeSession?.topic_id) return
    const fetchGraphTopics = async () => {
      try {
        const res = await axios.get(`/api/documents/topic/${activeSession.topic_id}/graph`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        const entities = res.data?.graph?.nodes || []
        const uniqueNames: string[] = Array.from(
          new Set(
            entities
              .map((e: any) => e.name || e.id)
              .filter((n: string) => n && n.length > 2 && n.length < 35)
          )
        )
        setAvailableTopics(uniqueNames.slice(0, 10))
        if (uniqueNames.length > 0) {
          setSelectedTopic(uniqueNames[0])
        }
      } catch {
        setAvailableTopics([])
      }
    }
    fetchGraphTopics()
  }, [isOpen, activeSession, token])

  // Load existing flashcards for session
  const loadCards = async () => {
    setLoading(true)
    try {
      const res = await axios.get(`/api/flashcards/session/${sessionId}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      const loaded: Flashcard[] = res.data || []
      setCards(loaded)
      if (loaded.length > 0) {
        setSetupStep(false)
      } else {
        setSetupStep(true)
      }
    } catch {
      setCards([])
      setSetupStep(true)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (isOpen) {
      loadCards()
      setCurrentIndex(0)
      setIsFlipped(false)
      setShowHint(false)
    }
  }, [isOpen, sessionId])

  // Generate deck
  const triggerGenerate = async () => {
    setGenerating(true)
    const effectiveTopic =
      scopeMode === 'all'
        ? 'All Topics (Entire PDF)'
        : customTopic.trim() || selectedTopic || 'General Concepts'

    try {
      const res = await axios.post(
        '/api/flashcards/generate',
        { session_id: sessionId, focus_topic: effectiveTopic },
        { headers: { Authorization: `Bearer ${token}` } }
      )
      setCards(res.data || [])
      setCurrentIndex(0)
      setIsFlipped(false)
      setShowHint(false)
      setSetupStep(false)
    } catch (err: any) {
      alert(err.response?.data?.detail ?? 'Failed to generate flashcards. Make sure a document is uploaded.')
    } finally {
      setGenerating(false)
    }
  }

  // Handle Review (Mastered vs Needs Study)
  const handleReview = async (mastered: boolean, cardIndex = currentIndex) => {
    const targetCard = cards[cardIndex]
    if (!targetCard) return

    const updated = [...cards]
    updated[cardIndex] = { ...targetCard, mastered }
    setCards(updated)

    try {
      await axios.post(
        `/api/flashcards/${targetCard.topic_id}/cards/${targetCard.id}/review`,
        { mastered },
        { headers: { Authorization: `Bearer ${token}` } }
      )
    } catch {
      /* ignore */
    }

    if (viewMode === 'single') {
      handleNext()
    }
  }

  const handleNext = () => {
    setIsFlipped(false)
    setShowHint(false)
    setTimeout(() => {
      setCurrentIndex((prev) => (prev + 1) % cards.length)
    }, 150)
  }

  const handlePrev = () => {
    setIsFlipped(false)
    setShowHint(false)
    setTimeout(() => {
      setCurrentIndex((prev) => (prev - 1 + cards.length) % cards.length)
    }, 150)
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
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = 0.95
    utterance.onend = () => setIsSpeaking(false)
    utterance.onerror = () => setIsSpeaking(false)
    setIsSpeaking(true)
    window.speechSynthesis.speak(utterance)
  }

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!isOpen || setupStep || viewMode !== 'single') return
      if (e.key === ' ' || e.key === 'Enter' || e.key === 'ArrowUp' || e.key === 'ArrowDown') {
        e.preventDefault()
        setIsFlipped((prev) => !prev)
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        handleReview(true)
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault()
        handleReview(false)
      }
    },
    [isOpen, setupStep, viewMode, cards, currentIndex]
  )

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  if (!isOpen) return null

  const masteredCount = cards.filter((c) => c.mastered).length
  const completionPercentage = cards.length > 0 ? Math.round((masteredCount / cards.length) * 100) : 0
  const currentCard = cards[currentIndex]

  // Filtered cards for Grid View
  const filteredCards = cards.filter((c) => {
    if (gridFilter === 'mastered') return c.mastered
    if (gridFilter === 'unmastered') return !c.mastered
    return true
  })

  return (
    <div className="fixed inset-0 z-50 bg-[#0f172a]/70 backdrop-blur-md flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.98 }}
        className="w-full max-w-xl bg-white rounded-3xl p-7 shadow-2xl border border-slate-100 relative overflow-hidden flex flex-col justify-between"
        style={{ minHeight: '540px' }}
      >
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-5 right-5 text-slate-400 hover:text-slate-700 transition-colors p-1.5 hover:bg-slate-100 rounded-full z-10 cursor-pointer"
        >
          <X size={18} />
        </button>

        {loading ? (
          <div className="flex-1 flex flex-col items-center justify-center py-10">
            <RefreshCw size={28} className="text-indigo-600 animate-spin mb-4" />
            <p className="text-sm text-slate-600 font-medium">Preparing study cards...</p>
          </div>
        ) : setupStep || cards.length === 0 ? (
          /* ─── LAYER 1: Interactive Topic Setup ─── */
          <div className="flex-1 flex flex-col justify-between py-2">
            <div>
              <div className="flex items-center gap-3 mb-4">
                <div className="w-11 h-11 rounded-2xl bg-indigo-50 flex items-center justify-center text-indigo-600 border border-indigo-100">
                  <BookOpen size={22} />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-slate-900">Study Flashcards</h2>
                  <p className="text-xs text-slate-500">Select what topic to generate study cards for</p>
                </div>
              </div>

              {/* Scope options */}
              <div className="space-y-3 mt-5">
                <label className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
                  1. Select Card Scope
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => setScopeMode('all')}
                    className={`p-3.5 rounded-2xl border text-left transition-all flex items-start gap-3 cursor-pointer ${
                      scopeMode === 'all'
                        ? 'border-indigo-500 bg-indigo-50/40 text-indigo-900 shadow-sm'
                        : 'border-slate-200 hover:border-indigo-200 text-slate-700 hover:bg-slate-50'
                    }`}
                  >
                    <BookOpen
                      size={20}
                      className={scopeMode === 'all' ? 'text-indigo-600 mt-0.5' : 'text-slate-400 mt-0.5'}
                    />
                    <div>
                      <p className="text-xs font-bold">Entire PDF</p>
                      <p className="text-[10px] text-slate-500 mt-0.5 leading-tight">
                        Deck covering all main concepts
                      </p>
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() => setScopeMode('specific')}
                    className={`p-3.5 rounded-2xl border text-left transition-all flex items-start gap-3 cursor-pointer ${
                      scopeMode === 'specific'
                        ? 'border-indigo-500 bg-indigo-50/40 text-indigo-900 shadow-sm'
                        : 'border-slate-200 hover:border-indigo-200 text-slate-700 hover:bg-slate-50'
                    }`}
                  >
                    <Target
                      size={20}
                      className={scopeMode === 'specific' ? 'text-indigo-600 mt-0.5' : 'text-slate-400 mt-0.5'}
                    />
                    <div>
                      <p className="text-xs font-bold">Specific Concept</p>
                      <p className="text-[10px] text-slate-500 mt-0.5 leading-tight">
                        Target a single key topic
                      </p>
                    </div>
                  </button>
                </div>
              </div>

              {/* Specific Topic Chips & Input */}
              {scopeMode === 'specific' && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  className="mt-5 space-y-3"
                >
                  <label className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
                    2. Pick a Topic
                  </label>
                  {availableTopics.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto pr-1">
                      {availableTopics.map((topic) => {
                        const isSel = selectedTopic === topic && !customTopic
                        return (
                          <button
                            key={topic}
                            type="button"
                            onClick={() => {
                              setSelectedTopic(topic)
                              setCustomTopic('')
                            }}
                            className={`text-xs px-3 py-1.5 rounded-xl border transition-all cursor-pointer flex items-center gap-1.5 ${
                              isSel
                                ? 'bg-indigo-600 text-white border-indigo-600 font-semibold shadow-sm'
                                : 'bg-slate-50 text-slate-700 border-slate-200 hover:border-indigo-300'
                            }`}
                          >
                            {isSel && <CheckCircle2 size={12} />}
                            <span>{topic}</span>
                          </button>
                        )
                      })}
                    </div>
                  )}

                  <input
                    type="text"
                    value={customTopic}
                    onChange={(e) => setCustomTopic(e.target.value)}
                    placeholder="Or type a custom concept..."
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-xs text-slate-800 focus:outline-none focus:border-indigo-500"
                  />
                </motion.div>
              )}

              {/* Deck Summary if cards already exist */}
              {cards.length > 0 && (
                <div className="mt-5 p-3.5 bg-slate-50 border border-slate-200/80 rounded-2xl flex items-center justify-between">
                  <div className="text-xs">
                    <span className="font-bold text-slate-800 block">Existing Deck Loaded</span>
                    <span className="text-slate-500 text-[11px]">
                      {cards.length} cards ({masteredCount} mastered)
                    </span>
                  </div>
                  <button
                    onClick={() => setSetupStep(false)}
                    className="text-xs font-bold text-indigo-600 hover:underline cursor-pointer"
                  >
                    Resume Study →
                  </button>
                </div>
              )}
            </div>

            {/* Action button */}
            <div className="pt-5 border-t border-slate-100 flex justify-end">
              <button
                onClick={triggerGenerate}
                disabled={generating}
                className="btn-primary w-full py-3 text-sm flex items-center justify-center gap-2 shadow-lg shadow-indigo-500/20"
              >
                {generating ? (
                  <>
                    <RefreshCw size={16} className="animate-spin" /> Compiling Smart Cards...
                  </>
                ) : (
                  <>
                    <Sparkles size={16} /> Generate Deck (
                    {scopeMode === 'all' ? 'All Topics' : customTopic || selectedTopic || 'Custom Topic'})
                  </>
                )}
              </button>
            </div>
          </div>
        ) : (
          /* ─── LAYER 2: Interactive Card Deck Review ─── */
          <div className="flex-1 flex flex-col justify-between">
            {/* Header & Controls */}
            <div>
              <div className="flex items-center justify-between pb-3">
                {/* Progress Stats */}
                <div className="flex items-center gap-2">
                  <span className="text-xs font-extrabold text-slate-800">
                    {viewMode === 'single' ? `Card ${currentIndex + 1} / ${cards.length}` : `${cards.length} Cards`}
                  </span>
                  <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-100 px-2 py-0.5 rounded-full flex items-center gap-1">
                    <CheckCircle2 size={11} /> {completionPercentage}% Mastered ({masteredCount}/{cards.length})
                  </span>
                </div>

                {/* Controls (View toggle & setup layer) */}
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => setViewMode(viewMode === 'single' ? 'grid' : 'single')}
                    className={`p-1.5 rounded-xl border text-xs flex items-center gap-1 transition-all cursor-pointer ${
                      viewMode === 'grid'
                        ? 'bg-indigo-50 border-indigo-200 text-indigo-600 font-bold'
                        : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                    }`}
                    title={viewMode === 'single' ? 'Switch to Deck Grid View' : 'Switch to Single Card View'}
                  >
                    {viewMode === 'single' ? <Grid size={14} /> : <Layers size={14} />}
                    <span className="text-[10px] font-semibold">{viewMode === 'single' ? 'Grid' : 'Cards'}</span>
                  </button>

                  <button
                    onClick={() => setSetupStep(true)}
                    className="p-1.5 rounded-xl border border-slate-200 text-slate-500 hover:text-indigo-600 hover:bg-slate-50 transition-all text-xs cursor-pointer"
                    title="Change Topic / Setup"
                  >
                    <SlidersHorizontal size={14} />
                  </button>
                </div>
              </div>

              {/* Progress bar */}
              <div className="w-full bg-slate-100 rounded-full h-1.5 mb-4">
                <motion.div
                  className="bg-indigo-600 h-1.5 rounded-full"
                  animate={{ width: `${completionPercentage}%` }}
                  transition={{ duration: 0.4 }}
                />
              </div>
            </div>

            {/* ─── SINGLE CARD FLIP VIEW ─── */}
            {viewMode === 'single' ? (
              <div className="flex-1 flex flex-col justify-between">
                {/* Flippable 3D Card Container */}
                <div
                  className="perspective-1000 h-64 w-full cursor-pointer my-2 relative"
                  onClick={() => setIsFlipped(!isFlipped)}
                >
                  <motion.div
                    className="relative w-full h-full duration-500 transform-style-3d"
                    animate={{ rotateY: isFlipped ? 180 : 0 }}
                    transition={{ duration: 0.5, ease: 'easeOut' }}
                  >
                    {/* Front (Concept / Question) */}
                    <div className="absolute inset-0 w-full h-full backface-hidden bg-white border border-slate-200/90 border-t-4 border-t-indigo-600 rounded-3xl p-6 flex flex-col justify-between shadow-lg hover:shadow-xl transition-shadow">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-extrabold text-indigo-600 uppercase tracking-widest bg-indigo-50 px-2.5 py-0.5 rounded-md flex items-center gap-1">
                          <HelpCircle size={11} /> Concept / Question
                        </span>

                        <div className="flex items-center gap-1">
                          {/* Audio button */}
                          <button
                            type="button"
                            onClick={(e) => speakText(currentCard?.front || '', e)}
                            className={`p-1.5 rounded-lg transition-colors cursor-pointer ${
                              isSpeaking ? 'bg-indigo-100 text-indigo-600' : 'text-slate-400 hover:text-indigo-600 hover:bg-slate-50'
                            }`}
                            title="Listen to audio"
                          >
                            <Volume2 size={15} />
                          </button>
                        </div>
                      </div>

                      <div className="flex-1 flex flex-col items-center justify-center text-center my-2 px-2">
                        <h3 className="text-base font-extrabold text-slate-900 leading-snug">
                          {currentCard?.front}
                        </h3>

                        {/* Hint box if enabled */}
                        {showHint && (
                          <motion.p
                            initial={{ opacity: 0, y: 4 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="mt-3 text-xs text-amber-700 bg-amber-50 border border-amber-200/70 rounded-xl px-3 py-1.5 font-medium"
                          >
                            💡 Hint: {currentCard?.back.slice(0, 25)}...
                          </motion.p>
                        )}
                      </div>

                      <div className="flex items-center justify-between pt-2 border-t border-slate-100">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            setShowHint(!showHint)
                          }}
                          className="text-[10px] font-bold text-amber-600 hover:text-amber-700 flex items-center gap-1 cursor-pointer"
                        >
                          <Lightbulb size={12} /> {showHint ? 'Hide Hint' : 'Reveal Hint'}
                        </button>

                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                          Click to flip 🔄
                        </span>
                      </div>
                    </div>

                    {/* Back (Answer / Definition) */}
                    <div
                      className="absolute inset-0 w-full h-full backface-hidden bg-white border border-slate-200/90 border-t-4 border-t-emerald-500 rounded-3xl p-6 flex flex-col justify-between shadow-lg hover:shadow-xl transition-shadow"
                      style={{ transform: 'rotateY(180deg)' }}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-extrabold text-emerald-700 uppercase tracking-widest bg-emerald-50 px-2.5 py-0.5 rounded-md flex items-center gap-1">
                          <CheckCircle2 size={11} /> Answer / Definition
                        </span>

                        <button
                          type="button"
                          onClick={(e) => speakText(currentCard?.back || '', e)}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-emerald-600 hover:bg-slate-50 transition-colors cursor-pointer"
                          title="Listen to answer"
                        >
                          <Volume2 size={15} />
                        </button>
                      </div>

                      <div className="flex-1 flex items-center justify-center text-center my-2 px-2">
                        <p className="text-sm font-semibold text-slate-800 leading-relaxed">
                          {currentCard?.back}
                        </p>
                      </div>

                      <div className="flex items-center justify-end pt-2 border-t border-slate-100">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                          Click to flip back 🔄
                        </span>
                      </div>
                    </div>
                  </motion.div>
                </div>

                {/* Rating Actions */}
                <div className="grid grid-cols-2 gap-3 mt-3">
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      handleReview(false)
                    }}
                    className="btn-ghost flex items-center justify-center gap-2 py-3 border-rose-200 text-rose-600 hover:bg-rose-50 text-xs font-bold rounded-2xl cursor-pointer"
                  >
                    <AlertCircle size={15} /> Needs Study (←)
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      handleReview(true)
                    }}
                    className="btn-primary flex items-center justify-center gap-2 py-3 text-xs font-bold rounded-2xl cursor-pointer shadow-md shadow-emerald-500/10"
                    style={{ background: 'linear-gradient(135deg, #10b981, #059669)' }}
                  >
                    <CheckCircle2 size={15} /> Mastered (→)
                  </button>
                </div>

                {/* Bottom Navigation & Shortcuts */}
                <div className="flex items-center justify-between text-xs text-slate-400 mt-4 pt-3 border-t border-slate-100">
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      handlePrev()
                    }}
                    className="hover:text-indigo-600 font-bold flex items-center gap-1 cursor-pointer"
                  >
                    <ChevronLeft size={14} /> Previous
                  </button>

                  <span className="text-[10px] text-slate-400">
                    Keys: <kbd className="px-1 py-0.5 bg-slate-100 rounded text-[9px]">Space</kbd> Flip ·{' '}
                    <kbd className="px-1 py-0.5 bg-slate-100 rounded text-[9px]">←/→</kbd> Rate
                  </span>

                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      handleNext()
                    }}
                    className="hover:text-indigo-600 font-bold flex items-center gap-1 cursor-pointer"
                  >
                    Next <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            ) : (
              /* ─── DECK GRID VIEW ─── */
              <div className="flex-1 flex flex-col justify-between my-2">
                {/* Filter Tabs */}
                <div className="flex items-center gap-2 mb-3">
                  {(['all', 'unmastered', 'mastered'] as const).map((filter) => (
                    <button
                      key={filter}
                      onClick={() => setGridFilter(filter)}
                      className={`text-xs px-3 py-1 rounded-xl capitalize font-semibold transition-all cursor-pointer ${
                        gridFilter === filter
                          ? 'bg-indigo-600 text-white shadow-sm'
                          : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                      }`}
                    >
                      {filter}
                    </button>
                  ))}
                </div>

                {/* Grid Cards Container */}
                <div className="flex-1 overflow-y-auto max-h-80 pr-1 space-y-2.5">
                  {filteredCards.length === 0 ? (
                    <div className="text-center py-10 text-slate-400 text-xs">No cards match this filter.</div>
                  ) : (
                    filteredCards.map((card, idx) => (
                      <div
                        key={card.id}
                        onClick={() => {
                          setCurrentIndex(cards.findIndex((c) => c.id === card.id))
                          setViewMode('single')
                          setIsFlipped(false)
                        }}
                        className={`p-3.5 rounded-2xl border transition-all text-left cursor-pointer flex items-start justify-between gap-3 ${
                          card.mastered
                            ? 'bg-emerald-50/40 border-emerald-200/80 hover:border-emerald-400'
                            : 'bg-slate-50/60 border-slate-200/80 hover:border-indigo-300'
                        }`}
                      >
                        <div className="flex-1 space-y-1">
                          <p className="text-xs font-bold text-slate-900 leading-snug">{card.front}</p>
                          <p className="text-[11px] text-slate-600 leading-normal">{card.back}</p>
                        </div>

                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            const realIdx = cards.findIndex((c) => c.id === card.id)
                            handleReview(!card.mastered, realIdx)
                          }}
                          className={`p-1.5 rounded-xl border flex-shrink-0 cursor-pointer transition-colors ${
                            card.mastered
                              ? 'bg-emerald-500 text-white border-emerald-500'
                              : 'bg-white text-slate-400 border-slate-200 hover:text-emerald-600'
                          }`}
                          title={card.mastered ? 'Mark as Needs Study' : 'Mark as Mastered'}
                        >
                          <CheckCircle2 size={16} />
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </motion.div>

      <style>{`
        .perspective-1000 { perspective: 1000px; }
        .transform-style-3d { transform-style: preserve-3d; }
        .backface-hidden { backface-visibility: hidden; }
      `}</style>
    </div>
  )
}
