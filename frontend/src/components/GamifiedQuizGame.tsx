import { useState, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Trophy,
  RefreshCw,
  X,
  Sparkles,
  ArrowRight,
  Brain,
  Target,
  Layers,
  CheckCircle2,
  Flame,
  Check,
  RotateCcw,
  ChevronRight
} from 'lucide-react'
import { quizApi } from '../services/api'
import { useChatStore } from '../stores/chatStore'
import { useLanguageStore } from '../stores/languageStore'
import { useTranslation } from '../utils/translations'

interface Question {
  id: string
  question_text: string
  options: string[]
  correct_answer: string
  explanation: string
}

interface Quiz {
  id: string
  title: string
  questions: Question[]
}

interface Props {
  sessionId?: string
  isOpen: boolean
  onClose: () => void
  initialTopic?: string
  onQuizComplete?: (result: { score: number; total: number; percentage: number }) => void
}

const OPTION_LABELS = ['A', 'B', 'C', 'D']

export default function GamifiedQuizGame({
  sessionId,
  isOpen,
  onClose,
  initialTopic,
  onQuizComplete,
}: Props) {
  const queryClient = useQueryClient()
  const activeSession = useChatStore((s) => s.activeSession)
  const { uiLanguage, aiLanguage } = useLanguageStore()
  const t = useTranslation(uiLanguage)

  const [quiz, setQuiz] = useState<Quiz | null>(null)
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)

  // Setup layer state
  const [setupStep, setSetupStep] = useState(true)
  const [scopeMode, setScopeMode] = useState<'all' | 'specific'>(initialTopic ? 'specific' : 'all')
  const [availableTopics, setAvailableTopics] = useState<string[]>([])
  const [selectedTopic, setSelectedTopic] = useState<string>('')
  const [customTopic, setCustomTopic] = useState<string>(initialTopic || '')
  const [difficulty, setDifficulty] = useState<'easy' | 'medium' | 'hard'>('medium')
  const [numQuestions, setNumQuestions] = useState<number>(5)

  // Game state
  const [currentQIndex, setCurrentQIndex] = useState(0)
  const [score, setScore] = useState(0)
  const [correctCount, setCorrectCount] = useState(0)
  const [streak, setStreak] = useState(0)
  const [selectedOpt, setSelectedOpt] = useState<string | null>(null)
  const [isAnswered, setIsAnswered] = useState(false)
  const [gameWon, setGameWon] = useState(false)
  const [userAnswers, setUserAnswers] = useState<Record<string, string>>({})

  const resetGame = () => {
    setCurrentQIndex(0)
    setScore(0)
    setCorrectCount(0)
    setStreak(0)
    setSelectedOpt(null)
    setIsAnswered(false)
    setGameWon(false)
    setUserAnswers({})
  }

  const triggerGenerate = async (overrideTopic?: string) => {
    setGenerating(true)
    const effectiveTopic = overrideTopic || (
      scopeMode === 'all'
        ? 'All Topics (Entire PDF)'
        : customTopic.trim() || selectedTopic || 'General Study Concepts'
    )

    try {
      const targetTopicId = initialTopic || activeSession?.topic_id || (sessionId ? undefined : 'general')
      const res = await quizApi.generate({
        session_id: sessionId,
        topic_id: targetTopicId,
        custom_topic: effectiveTopic,
        difficulty: difficulty,
        num_questions: numQuestions,
        language: aiLanguage,
      })
      setQuiz(res.data)
      resetGame()
      setSetupStep(false)
    } catch (err: any) {
      console.error(err)
      alert(err.response?.data?.detail || 'Failed to generate quiz. Make sure you have uploaded a PDF document and Ollama is running.')
      if (overrideTopic) {
        onClose()
      } else {
        setSetupStep(true)
      }
    } finally {
      setGenerating(false)
    }
  }

  // Auto-generate quiz when opened with initialTopic from Study Plan
  useEffect(() => {
    if (!isOpen) {
      setQuiz(null)
      setSetupStep(true)
      setGenerating(false)
      return
    }
    if (initialTopic) {
      setCustomTopic(initialTopic)
      setScopeMode('specific')
      setSetupStep(false)
      setGenerating(true)
      triggerGenerate(initialTopic)
    }
  }, [isOpen, initialTopic])

  // Fetch extracted key topics from uploaded PDF documents
  useEffect(() => {
    if (!isOpen) return
    const fetchSuggestions = async () => {
      try {
        const res = await quizApi.suggestions({
          session_id: sessionId || activeSession?.id,
          topic_id: activeSession?.topic_id,
        })
        const suggestions: string[] = res.data?.suggestions || []
        setAvailableTopics(suggestions)
        if (suggestions.length > 0 && !selectedTopic) {
          setSelectedTopic(suggestions[0])
        }
      } catch {
        setAvailableTopics([
          'Transformer Architecture',
          'Self-Attention Mechanism',
          'Pre-training & Fine-tuning',
          'Reinforcement Learning (RLHF)',
          'Model Evaluation & Benchmarks'
        ])
      }
    }
    fetchSuggestions()
  }, [isOpen, sessionId, activeSession])

  const filteredSuggestions = availableTopics.filter((t) =>
    customTopic.trim() ? t.toLowerCase().includes(customTopic.toLowerCase().trim()) : true
  )

  const handleOptionSelect = (optLabel: string) => {
    if (isAnswered) return
    setSelectedOpt(optLabel)
  }

  const handleChooseAnswer = () => {
    if (!selectedOpt || !currentQuestion || isAnswered) return
    setIsAnswered(true)
    setUserAnswers((prev) => ({ ...prev, [currentQuestion.id]: selectedOpt }))
    
    const isCorrect = selectedOpt === currentQuestion.correct_answer

    if (isCorrect) {
      const addedPoints = 100 + streak * 20
      setScore((s) => s + addedPoints)
      setCorrectCount((c) => c + 1)
      setStreak((s) => s + 1)
    } else {
      setStreak(0)
    }
  }

  const handleNext = () => {
    if (!quiz) return
    if (currentQIndex < quiz.questions.length - 1) {
      setCurrentQIndex((i) => i + 1)
      setSelectedOpt(null)
      setIsAnswered(false)
    } else {
      setGameWon(true)
      const finalCorrect = selectedOpt === currentQuestion?.correct_answer ? correctCount + 1 : correctCount
      const finalTotal = quiz.questions.length
      const finalPct = finalTotal > 0 ? Math.round((finalCorrect / finalTotal) * 100) : 0

      onQuizComplete?.({ score: finalCorrect, total: finalTotal, percentage: finalPct })

      const answersPayload = { ...userAnswers }
      if (currentQuestion && selectedOpt) {
        answersPayload[currentQuestion.id] = selectedOpt
      }
      if (quiz?.id) {
        quizApi
          .submit(quiz.id, answersPayload)
          .then(() => {
            queryClient.invalidateQueries({ queryKey: ['progress-recent-quizzes'] })
            queryClient.invalidateQueries({ queryKey: ['progress-summary'] })
            queryClient.invalidateQueries({ queryKey: ['progress-analysis'] })
            queryClient.invalidateQueries({ queryKey: ['progress-weekly'] })
            queryClient.invalidateQueries({ queryKey: ['progress-topics'] })
            queryClient.invalidateQueries({ queryKey: ['progress-calendar'] })
          })
          .catch((err) => console.error('Error submitting quiz attempt:', err))
      }
    }
  }

  if (!isOpen) return null

  const currentQuestion = quiz?.questions[currentQIndex]
  const totalQuestions = quiz?.questions.length || 0
  const displayQNum = totalQuestions > 0 ? currentQIndex + 1 : 0
  const progressPct = totalQuestions > 0 ? Math.round(((currentQIndex + 1) / totalQuestions) * 100) : 0

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

        {/* ─── SETUP LAYER SCREEN ─── */}
        {setupStep ? (
          <div className="space-y-6 text-left">
            <div className="flex items-start gap-3.5 border-b border-slate-200/60 pb-5 pr-8">
              <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-50 to-white/90 backdrop-blur-md border border-indigo-200 text-indigo-600 flex items-center justify-center flex-shrink-0 shadow-xs">
                <Trophy size={22} />
              </div>
              <div className="space-y-0.5">
                <h2 className="text-xl sm:text-2xl font-black text-slate-800 tracking-tight">Interactive AI Quiz</h2>
                <p className="text-xs sm:text-sm text-slate-500 font-medium leading-relaxed">
                  Configure question scope, difficulty & question count from your materials
                </p>
              </div>
            </div>

            {/* Scope Selection */}
            <div className="space-y-2.5">
              <label className="text-xs font-black text-slate-800 uppercase tracking-wider block">
                1. Select Quiz Scope
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
                    <p className="text-sm font-black text-slate-800">Entire Document</p>
                    <p className="text-xs text-slate-500 mt-0.5 font-medium">All topics combined</p>
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
                    <Target size={16} />
                  </div>
                  <div>
                    <p className="text-sm font-black text-slate-800">Specific Topic</p>
                    <p className="text-xs text-slate-500 mt-0.5 font-medium">Focus on 1 concept</p>
                  </div>
                </button>
              </div>
            </div>

            {/* Specific Topic Autocomplete */}
            {scopeMode === 'specific' && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="space-y-3 pt-1">
                <label className="text-xs font-black text-slate-800 uppercase tracking-wider block">
                  2. Choose Specific Concept
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
                  placeholder="Or type topic name..."
                  className="w-full bg-white/70 backdrop-blur-md border border-white/90 rounded-2xl px-4 py-3 text-xs sm:text-sm font-medium text-slate-800 outline-none focus:bg-white focus:border-indigo-600 shadow-xs placeholder-slate-400"
                />
              </motion.div>
            )}

            {/* Difficulty selection */}
            <div className="space-y-2">
              <label className="text-xs font-black text-slate-800 uppercase tracking-wider block">
                Difficulty Level
              </label>
              <div className="p-1.5 bg-black/[0.04] backdrop-blur-md rounded-2xl border border-white/60 flex gap-1.5 shadow-inner">
                {(['easy', 'medium', 'hard'] as const).map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setDifficulty(d)}
                    className={`flex-1 py-2.5 rounded-xl text-xs font-black capitalize transition-all cursor-pointer ${
                      difficulty === d
                        ? 'bg-indigo-600 text-white shadow-xs'
                        : 'text-slate-500 hover:text-slate-800 hover:bg-white/60'
                    }`}
                  >
                    {d}
                  </button>
                ))}
              </div>
            </div>

            {/* Number of Questions selection */}
            <div className="space-y-2">
              <label className="text-xs font-black text-slate-800 uppercase tracking-wider block">
                Number of Questions
              </label>
              <div className="p-1.5 bg-black/[0.04] backdrop-blur-md rounded-2xl border border-white/60 flex gap-1.5 shadow-inner">
                {[3, 5, 10, 15, 20].map((num) => (
                  <button
                    key={num}
                    type="button"
                    onClick={() => setNumQuestions(num)}
                    className={`flex-1 py-2.5 rounded-xl text-xs font-black transition-all cursor-pointer ${
                      numQuestions === num
                        ? 'bg-indigo-600 text-white shadow-xs'
                        : 'text-slate-500 hover:text-slate-800 hover:bg-white/60'
                    }`}
                  >
                    {num} Qs
                  </button>
                ))}
              </div>
            </div>

            {/* Generate Button */}
            <button
              onClick={() => triggerGenerate()}
              disabled={generating}
              className="btn-primary w-full py-4 px-6 rounded-2xl font-black text-sm sm:text-base flex items-center justify-center gap-2.5 shadow-md shadow-indigo-600/25 hover:shadow-lg transition-all cursor-pointer disabled:opacity-50 mt-4"
            >
              {generating ? (
                <>
                  <RefreshCw size={18} className="animate-spin text-white" />
                  <span>Generating AI Quiz...</span>
                </>
              ) : (
                <>
                  <Sparkles size={18} />
                  <span>Start Quiz</span>
                </>
              )}
            </button>
          </div>
        ) : gameWon ? (
          /* ─── QUIZ COMPLETED SUMMARY SCREEN ─── */
          <div className="py-8 text-center space-y-6">
            <div className="w-20 h-20 bg-indigo-50 border border-indigo-200 text-indigo-600 rounded-full flex items-center justify-center mx-auto shadow-md shadow-indigo-600/20">
              <Trophy size={40} />
            </div>
            <div>
              <h2 className="text-2xl font-black text-slate-800">Quiz Completed!</h2>
              <p className="text-sm font-semibold text-slate-500 mt-1">
                You scored <span className="text-indigo-600 font-bold">{correctCount}</span> out of <span className="font-bold text-slate-800">{totalQuestions}</span> questions correctly ({Math.round((correctCount / totalQuestions) * 100)}%)
              </p>
            </div>
            <div className="flex gap-3 max-w-sm mx-auto pt-4">
              {initialTopic ? (
                <>
                  <button
                    onClick={() => {
                      resetGame()
                      setGenerating(true)
                      triggerGenerate(initialTopic)
                    }}
                    className="btn-primary flex-1 py-3 px-6 text-xs font-bold shadow-xs cursor-pointer"
                  >
                    Retry Quiz
                  </button>
                  <button
                    onClick={onClose}
                    className="flex-1 py-3 px-6 text-xs font-bold rounded-2xl border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 cursor-pointer shadow-xs"
                  >
                    Close
                  </button>
                </>
              ) : (
                <button
                  onClick={() => setSetupStep(true)}
                  className="btn-primary w-full py-3.5 px-6 text-xs font-bold shadow-xs cursor-pointer"
                >
                  Take Another Quiz
                </button>
              )}
            </div>
          </div>
        ) : generating || !quiz ? (
          /* ─── GENERATING QUIZ LOADING SCREEN ─── */
          <div className="py-16 text-center space-y-5">
            <div className="w-16 h-16 bg-indigo-50 border border-indigo-200 text-indigo-600 rounded-full flex items-center justify-center mx-auto shadow-sm">
              <RefreshCw size={28} className="animate-spin text-indigo-600" />
            </div>
            <div>
              <h2 className="text-xl font-black text-slate-800">Generating AI Quiz...</h2>
              <p className="text-sm font-medium text-slate-500 mt-1">
                Creating personalized questions from your study materials
              </p>
            </div>
            <div className="flex items-center justify-center gap-1.5 mt-4">
              {[0, 1, 2].map((i) => (
                <motion.div
                  key={i}
                  className="w-2.5 h-2.5 rounded-full bg-indigo-600"
                  animate={{ opacity: [0.3, 1, 0.3] }}
                  transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.3 }}
                />
              ))}
            </div>
          </div>
        ) : (
          /* ─── ACTIVE QUIZ SCREEN ─── */
          <div className="space-y-6">
            
            {/* QUIZ PROGRESS Header & Progress Bar */}
            <div className="text-center space-y-2">
              <div className="flex items-center justify-between text-xs font-black uppercase tracking-wider text-slate-500">
                <span>Question {displayQNum} of {totalQuestions}</span>
                <span className="text-indigo-600 font-black">{progressPct}% Completed</span>
              </div>
              <div className="w-full bg-slate-200/60 border border-slate-200 rounded-full h-3 p-0.5 overflow-hidden">
                <div
                  className="bg-indigo-600 h-full rounded-full transition-all duration-500"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
            </div>

            {/* Question Text */}
            <div className="text-left pt-2">
              <h2 className="text-base sm:text-lg font-black text-slate-800 leading-snug">
                {currentQuestion?.question_text}
              </h2>
            </div>

            {/* Option Cards */}
            <div className="space-y-2.5">
              {currentQuestion?.options.map((option, idx) => {
                const label = OPTION_LABELS[idx]
                const isSelected = selectedOpt === label
                const isCorrect = label === currentQuestion.correct_answer

                let cardStyle =
                  'bg-slate-50 border-slate-200 text-slate-800 hover:border-indigo-400/50 hover:bg-white'
                let badgeStyle = 'bg-white text-slate-500 border-slate-200'

                if (isAnswered) {
                  if (isCorrect) {
                    cardStyle = 'bg-emerald-50 border-2 border-emerald-500 text-emerald-900 font-bold shadow-xs'
                    badgeStyle = 'bg-emerald-600 text-white border-emerald-600'
                  } else if (isSelected) {
                    cardStyle = 'bg-rose-50 border-2 border-rose-400 text-rose-900 font-bold'
                    badgeStyle = 'bg-rose-600 text-white border-rose-600'
                  } else {
                    cardStyle = 'opacity-50 bg-slate-50 border-slate-200 text-slate-400'
                  }
                } else if (isSelected) {
                  cardStyle = 'bg-indigo-50 border-2 border-indigo-600 text-indigo-900 font-bold shadow-xs'
                  badgeStyle = 'bg-indigo-600 text-white border-indigo-600'
                }

                return (
                  <div
                    key={label}
                    onClick={() => handleOptionSelect(label)}
                    className={`w-full border rounded-2xl p-3.5 sm:p-4 text-left text-xs sm:text-sm flex items-center justify-between transition-all group cursor-pointer shadow-xs ${cardStyle}`}
                  >
                    <div className="flex items-center gap-3">
                      <span className={`w-6 h-6 rounded-lg border text-xs font-black flex items-center justify-center flex-shrink-0 transition-colors ${badgeStyle}`}>
                        {label}
                      </span>
                      <span className="font-medium text-slate-800">{option}</span>
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Explanation Box */}
            {isAnswered && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="p-4 bg-emerald-50 border border-emerald-200 rounded-2xl text-xs text-emerald-900 text-left leading-relaxed font-medium"
              >
                <span className="font-black text-emerald-800 flex items-center gap-1.5 mb-1 uppercase tracking-wider">
                  <Brain size={14} /> Explanation:
                </span>
                <p>{currentQuestion?.explanation}</p>
              </motion.div>
            )}

            {/* Action Button */}
            <div className="pt-2">
              {!isAnswered ? (
                <button
                  onClick={handleChooseAnswer}
                  disabled={!selectedOpt}
                  className="btn-primary w-full py-3.5 px-6 font-black rounded-2xl text-xs sm:text-sm shadow-md shadow-indigo-600/25 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                >
                  Confirm Answer
                </button>
              ) : (
                <button
                  onClick={handleNext}
                  className="btn-primary w-full py-3.5 px-6 font-black rounded-2xl text-xs sm:text-sm shadow-md shadow-indigo-600/25 flex items-center justify-center gap-2 cursor-pointer"
                >
                  <span>{currentQIndex === totalQuestions - 1 ? 'Finish Quiz' : 'Next Question'}</span>
                  <ChevronRight size={16} />
                </button>
              )}
            </div>

          </div>
        )}
      </motion.div>
    </div>
  )
}
