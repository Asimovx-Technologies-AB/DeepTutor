import { useState, useCallback, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  ArrowLeft,
  Sparkles,
  BookOpen,
  CheckCircle2,
  RefreshCw,
  AlertCircle,
  HelpCircle,
  Volume2,
  Lightbulb,
  Grid,
  Layers,
  ChevronLeft,
  ChevronRight
} from 'lucide-react'
import { flashcardsApi } from '../services/api'
import { useSubjectStore } from '../stores/subjectStore'

interface Flashcard {
  id: string
  topic_id: string
  front: string
  back: string
  mastered: boolean
}

export default function FlashcardsPage() {
  const { topicId } = useParams<{ topicId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [currentIndex, setCurrentIndex] = useState(0)
  const [isFlipped, setIsFlipped] = useState(false)
  const [showHint, setShowHint] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [viewMode, setViewMode] = useState<'single' | 'grid'>('single')
  const [gridFilter, setGridFilter] = useState<'all' | 'unmastered' | 'mastered'>('all')
  const [generating, setGenerating] = useState(false)

  // Fetch flashcards
  const { data: cards = [], isLoading } = useQuery<Flashcard[]>({
    queryKey: ['flashcards', topicId],
    queryFn: async () => {
      const res = await flashcardsApi.byTopic(topicId || 'general')
      return res.data
    },
  })

  // Generate mutation
  const generateMutation = useMutation({
    mutationFn: async () => {
      setGenerating(true)
      const res = await flashcardsApi.generate({ topic_id: topicId })
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['flashcards', topicId] })
      queryClient.invalidateQueries({ queryKey: ['progress-summary'] })
      queryClient.invalidateQueries({ queryKey: ['progress-calendar'] })
      setGenerating(false)
      setCurrentIndex(0)
      setIsFlipped(false)
      setShowHint(false)
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
      queryClient.invalidateQueries({ queryKey: ['progress-summary'] })
      queryClient.invalidateQueries({ queryKey: ['progress-calendar'] })
    },
  })

  const currentCard = cards[currentIndex]

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

  const handleReview = (mastered: boolean, cardId?: string) => {
    const idToReview = cardId || currentCard?.id
    if (!idToReview) return
    reviewMutation.mutate({ cardId: idToReview, mastered })

    // Update real subject and topic progress
    if (topicId) {
      const subjectState = useSubjectStore.getState()
      for (const [sId, sTopics] of Object.entries(subjectState.topics)) {
        if (sTopics.some((t) => t.id === topicId)) {
          const masteredCount = cards.filter((c) => (c.id === idToReview ? mastered : c.mastered)).length
          const totalCards = Math.max(cards.length, 1)
          const newPct = Math.round((masteredCount / totalCards) * 100)
          subjectState.updateTopicProgress(sId, topicId, newPct)
          break
        }
      }
    }

    if (viewMode === 'single') {
      handleNext()
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
      if (viewMode !== 'single' || cards.length === 0) return
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
    [viewMode, cards, currentIndex]
  )

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  if (isLoading) {
    return (
      <div className="p-6 max-w-2xl mx-auto space-y-4">
        <div className="skeleton h-8 w-48 mb-6" />
        <div className="skeleton h-80 w-full rounded-2xl" />
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
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500/20 to-violet-500/20 flex items-center justify-center mx-auto mb-4">
            <BookOpen size={28} className="text-indigo-500" />
          </div>
          <h2 className="text-xl font-bold text-slate-800 mb-2">No flashcards yet</h2>
          <p className="text-slate-500 text-sm mb-6 leading-relaxed">
            Generate study flashcards automatically using local AI from your uploaded PDF text.
          </p>
          <button
            onClick={() => generateMutation.mutate()}
            disabled={generating}
            className="btn-primary flex items-center gap-2 mx-auto"
          >
            {generating ? (
              <>
                <RefreshCw size={15} className="animate-spin" /> Generating Card Deck...
              </>
            ) : (
              <>
                <Sparkles size={15} /> Generate AI Flashcards
              </>
            )}
          </button>
        </motion.div>
      </div>
    )
  }

  const masteredCount = cards.filter((c) => c.mastered).length
  const completionPercentage = Math.round((masteredCount / cards.length) * 100)

  const filteredCards = cards.filter((c) => {
    if (gridFilter === 'mastered') return c.mastered
    if (gridFilter === 'unmastered') return !c.mastered
    return true
  })

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-6 bg-[#FAF8F3]">
      {/* Header */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-2 text-[#6F6B63] hover:text-[#F28A45] transition-colors text-sm font-bold cursor-pointer"
        >
          <ArrowLeft size={16} /> Back to Topic
        </button>

        <div className="flex items-center gap-2">
          {/* View toggle */}
          <button
            onClick={() => setViewMode(viewMode === 'single' ? 'grid' : 'single')}
            className="text-xs px-3 py-1.5 rounded-xl border border-[#E7E1D8] bg-white text-[#20201D] hover:bg-[#FFF9F2] font-black flex items-center gap-1.5 transition-all cursor-pointer shadow-2xs"
          >
            {viewMode === 'single' ? <Grid size={14} /> : <Layers size={14} />}
            <span>{viewMode === 'single' ? 'Grid View' : 'Card View'}</span>
          </button>

          <button
            onClick={() => generateMutation.mutate()}
            disabled={generating}
            className="text-xs text-[#F28A45] hover:text-[#DF7635] font-black flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            <RefreshCw size={12} className={generating ? 'animate-spin' : ''} /> Regenerate Deck
          </button>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-black text-[#6F6B63]">
          <span>
            {viewMode === 'single' ? `Card ${currentIndex + 1} of ${cards.length}` : `${cards.length} Total Cards`}
          </span>
          <span className="text-[#4F8A68]">
            {completionPercentage}% Mastered ({masteredCount}/{cards.length})
          </span>
        </div>
        <div className="progress-bar">
          <motion.div
            className="progress-fill"
            animate={{ width: `${completionPercentage}%` }}
            transition={{ duration: 0.4 }}
          />
        </div>
      </div>

      {/* SINGLE CARD VIEW */}
      {viewMode === 'single' ? (
        <div className="space-y-6">
          <div
            className="perspective-1000 h-96 w-full cursor-pointer relative"
            onClick={() => setIsFlipped(!isFlipped)}
          >
            <motion.div
              className="relative w-full h-full duration-500 transform-style-3d"
              animate={{ rotateY: isFlipped ? 180 : 0 }}
              transition={{ duration: 0.5, ease: 'easeOut' }}
            >
              {/* Front Side */}
              <div className="absolute inset-0 w-full h-full backface-hidden bg-white border border-[#E7E1D8] border-t-4 border-t-[#F28A45] rounded-3xl p-8 flex flex-col justify-between shadow-xs">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-xs text-[#F28A45] font-black uppercase tracking-wider">
                    <HelpCircle size={14} /> Concept / Question
                  </div>

                  <button
                    type="button"
                    onClick={(e) => speakText(currentCard?.front || '', e)}
                    className="p-2 rounded-xl text-[#969188] hover:text-[#F28A45] hover:bg-[#FFF0E4] transition-colors cursor-pointer"
                    title="Listen to card audio"
                  >
                    <Volume2 size={18} />
                  </button>
                </div>

                <div className="flex-1 flex flex-col items-center justify-center text-center my-3">
                  <h2 className="text-xl font-black text-[#20201D] leading-relaxed px-4">
                    {currentCard?.front}
                  </h2>

                  {showHint && (
                    <motion.p
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="mt-4 text-xs text-[#D99A32] bg-[#FFF3D8] border border-[#D99A32]/30 rounded-xl px-4 py-2 font-bold"
                    >
                      💡 Hint: {currentCard?.back.slice(0, 30)}...
                    </motion.p>
                  )}
                </div>

                <div className="flex items-center justify-between pt-3 border-t border-[#E7E1D8]/60">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      setShowHint(!showHint)
                    }}
                    className="text-xs font-black text-[#D99A32] hover:text-[#B57C20] flex items-center gap-1 cursor-pointer"
                  >
                    <Lightbulb size={14} /> {showHint ? 'Hide Hint' : 'Reveal Hint'}
                  </button>
                  <p className="text-xs text-[#969188] font-semibold">Click Card to Flip 🔄</p>
                </div>
              </div>

              {/* Back Side */}
              <div
                className="absolute inset-0 w-full h-full backface-hidden bg-white border border-[#E7E1D8] border-t-4 border-t-[#4F8A68] rounded-3xl p-8 flex flex-col justify-between shadow-xs"
                style={{ transform: 'rotateY(180deg)' }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-xs text-[#4F8A68] font-black uppercase tracking-wider">
                    <CheckCircle2 size={14} /> Answer / Explanation
                  </div>

                  <button
                    type="button"
                    onClick={(e) => speakText(currentCard?.back || '', e)}
                    className="p-2 rounded-xl text-[#969188] hover:text-[#4F8A68] hover:bg-[#E3F0E5] transition-colors cursor-pointer"
                    title="Listen to answer audio"
                  >
                    <Volume2 size={18} />
                  </button>
                </div>

                <div className="flex-1 flex items-center justify-center text-center">
                  <p className="text-base text-[#20201D] leading-relaxed px-4 font-bold">
                    {currentCard?.back}
                  </p>
                </div>

                <div className="flex items-center justify-end pt-3 border-t border-[#E7E1D8]/60">
                  <p className="text-xs text-[#969188] font-semibold">Click Card to Flip Back 🔄</p>
                </div>
              </div>
            </motion.div>
          </div>

          {/* Review Actions */}
          <div className="grid grid-cols-2 gap-4">
            <button
              onClick={() => handleReview(false)}
              className="btn-ghost flex items-center justify-center gap-2 py-3.5 border-[#C85C52]/40 text-[#C85C52] hover:bg-[#FBE7E4] font-black rounded-2xl cursor-pointer"
            >
              <AlertCircle size={16} /> Needs Study (←)
            </button>
            <button
              onClick={() => handleReview(true)}
              className="btn-primary flex items-center justify-center gap-2 py-3.5 font-black rounded-2xl cursor-pointer shadow-2xs"
              style={{ background: '#4F8A68' }}
            >
              <CheckCircle2 size={16} /> Mastered (→)
            </button>
          </div>

          {/* Navigation */}
          <div className="flex items-center justify-between text-sm px-2 text-[#6F6B63]">
            <button
              onClick={handlePrev}
              className="hover:text-[#F28A45] font-black transition-colors flex items-center gap-1 cursor-pointer"
            >
              <ChevronLeft size={16} /> Previous Card
            </button>
            <span className="text-xs text-[#969188]">Shortcuts: Space / Arrow Keys</span>
            <button
              onClick={handleNext}
              className="hover:text-[#F28A45] font-black transition-colors flex items-center gap-1 cursor-pointer"
            >
              Next Card <ChevronRight size={16} />
            </button>
          </div>
        </div>
      ) : (
        /* DECK GRID VIEW */
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            {(['all', 'unmastered', 'mastered'] as const).map((filter) => (
              <button
                key={filter}
                onClick={() => setGridFilter(filter)}
                className={`text-xs px-3 py-1.5 rounded-xl capitalize font-black transition-all cursor-pointer ${
                  gridFilter === filter
                    ? 'bg-[#F28A45] text-white shadow-2xs'
                    : 'bg-[#F4EFE7] text-[#6F6B63] hover:text-[#20201D]'
                }`}
              >
                {filter}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-[500px] overflow-y-auto pr-1">
            {filteredCards.map((card) => (
              <div
                key={card.id}
                onClick={() => {
                  setCurrentIndex(cards.findIndex((c) => c.id === card.id))
                  setViewMode('single')
                  setIsFlipped(false)
                }}
                className={`p-4 rounded-2xl border transition-all text-left cursor-pointer flex flex-col justify-between space-y-3 ${
                  card.mastered
                    ? 'bg-[#E3F0E5]/50 border-[#4F8A68]/40 hover:border-[#4F8A68]'
                    : 'bg-white border-[#E7E1D8] hover:border-[#F28A45]'
                }`}
              >
                <div>
                  <span className="text-[10px] font-black text-[#F28A45] uppercase tracking-wider block mb-1">
                    Concept
                  </span>
                  <p className="text-xs font-extrabold text-[#20201D] leading-snug">{card.front}</p>
                </div>
                <div className="pt-2 border-t border-[#E7E1D8]/60 flex items-center justify-between">
                  <span className="text-[11px] text-[#6F6B63] line-clamp-2 font-medium">{card.back}</span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      handleReview(!card.mastered, card.id)
                    }}
                    className={`p-1.5 rounded-xl border flex-shrink-0 cursor-pointer ml-2 ${
                      card.mastered
                        ? 'bg-[#4F8A68] text-white border-[#4F8A68]'
                        : 'bg-[#FAF8F3] text-[#969188] border-[#E7E1D8] hover:text-[#4F8A68]'
                    }`}
                  >
                    <CheckCircle2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <style>{`
        .perspective-1000 { perspective: 1000px; }
        .transform-style-3d { transform-style: preserve-3d; }
        .backface-hidden { backface-visibility: hidden; }
      `}</style>
    </div>
  )
}
