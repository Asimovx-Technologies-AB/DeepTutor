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
  RotateCcw
} from 'lucide-react'
import { quizApi } from '../services/api'
import { useChatStore } from '../stores/chatStore'

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
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="card flex flex-col relative max-h-[90vh] overflow-y-auto"
      >
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-5 right-5 p-2 text-text-muted hover:text-text-primary rounded-full hover:bg-white/50 transition-colors z-20 cursor-pointer"
        >
          <X size={20} />
        </button>

        {/* ─── SETUP LAYER SCREEN ─── */}
        {setupStep ? (
          <div className="space-y-6 text-left">
            <div className="flex items-center gap-3 border-b border-border pb-4">
              <div className="w-10 h-10 rounded-[1.5rem] bg-brand-primary-soft border border-brand-primary/30 text-brand-primary flex items-center justify-center elevation-1">
                <Trophy size={20} />
              </div>
              <div>
                <h2 className="text-xl font-bold text-text-primary">Interactive AI Quiz</h2>
                <p className="text-xs text-text-secondary font-medium">Configure scope & difficulty from your materials</p>
              </div>
            </div>

            {/* Scope Selection */}
            <div>
              <label className="text-xs font-bold text-text-muted uppercase tracking-wider block mb-2">
                1. Select Quiz Scope
              </label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setScopeMode('all')}
                  className={`p-4 rounded-[1.5rem] border text-left transition-all flex items-start gap-3 cursor-pointer ${
                    scopeMode === 'all'
                      ? 'border-brand-primary bg-brand-primary-soft/60 text-brand-primary elevation-1 font-bold'
                      : 'border-border hover:border-brand-primary/40 text-text-primary hover:bg-white'
                  }`}
                >
                  <Layers size={20} className={scopeMode === 'all' ? 'text-brand-primary' : 'text-text-muted'} />
                  <div>
                    <p className="text-sm font-bold">Entire Document</p>
                    <p className="text-xs text-text-secondary mt-0.5 font-medium">All topics combined</p>
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => setScopeMode('specific')}
                  className={`p-4 rounded-[1.5rem] border text-left transition-all flex items-start gap-3 cursor-pointer ${
                    scopeMode === 'specific'
                      ? 'border-brand-primary bg-brand-primary-soft/60 text-brand-primary elevation-1 font-bold'
                      : 'border-border hover:border-brand-primary/40 text-text-primary hover:bg-white'
                  }`}
                >
                  <Target size={20} className={scopeMode === 'specific' ? 'text-brand-primary' : 'text-text-muted'} />
                  <div>
                    <p className="text-sm font-bold">Specific Topic</p>
                    <p className="text-xs text-text-secondary mt-0.5 font-medium">Focus on 1 concept</p>
                  </div>
                </button>
              </div>
            </div>

            {/* Specific Topic Autocomplete */}
            {scopeMode === 'specific' && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="space-y-3">
                <label className="text-xs font-bold text-text-muted uppercase tracking-wider block">
                  2. Choose Specific Concept
                </label>
                {availableTopics.length > 0 && (
                  <div className="flex flex-wrap gap-2 max-h-28 overflow-y-auto">
                    {availableTopics.map((topic) => (
                      <button
                        key={topic}
                        type="button"
                        onClick={() => { setSelectedTopic(topic); setCustomTopic(topic); }}
                        className={`text-xs px-3 py-2 rounded-[1.25rem] border transition-all cursor-pointer font-bold ${
                          customTopic === topic
                            ? 'bg-brand-primary text-white border-brand-primary elevation-1'
                            : 'bg-white/50 text-text-primary border-border hover:bg-black/5'
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
                  className="w-full bg-white/50 border border-border rounded-[1.25rem] px-4 py-3 text-xs font-bold text-text-primary outline-none focus:bg-white focus:border-brand-primary"
                />
              </motion.div>
            )}

            {/* Difficulty selection */}
            <div>
              <label className="text-xs font-bold text-text-muted uppercase tracking-wider block mb-2">
                Difficulty Level
              </label>
              <div className="flex gap-3">
                {(['easy', 'medium', 'hard'] as const).map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setDifficulty(d)}
                    className={`flex-1 py-2.5 rounded-[1.25rem] text-xs font-bold capitalize border transition-all cursor-pointer ${
                      difficulty === d
                        ? 'bg-brand-primary text-white border-brand-primary elevation-1'
                        : 'bg-white/50 text-text-secondary border-border hover:bg-black/5'
                    }`}
                  >
                    {d}
                  </button>
                ))}
              </div>
            </div>

            {/* Number of Questions selection */}
            <div>
              <label className="text-xs font-bold text-text-muted uppercase tracking-wider block mb-2">
                Number of Questions
              </label>
              <div className="flex gap-2">
                {[3, 5, 10, 15, 20].map((num) => (
                  <button
                    key={num}
                    type="button"
                    onClick={() => setNumQuestions(num)}
                    className={`flex-1 py-2 rounded-[1.25rem] text-xs font-bold border transition-all cursor-pointer ${
                      numQuestions === num
                        ? 'bg-brand-primary text-white border-brand-primary elevation-1'
                        : 'bg-white/50 text-text-secondary border-border hover:bg-black/5'
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
              className="btn-primary w-full py-3.5 px-6 font-bold text-sm elevation-1 flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
            >
              {generating ? (
                <>
                  <RefreshCw size={16} className="animate-spin" />
                  <span>Generating AI Quiz...</span>
                </>
              ) : (
                <>
                  <Sparkles size={16} />
                  <span>Start Quiz</span>
                </>
              )}
            </button>
          </div>
        ) : gameWon ? (
          /* ─── QUIZ COMPLETED SUMMARY SCREEN ─── */
          <div className="py-8 text-center space-y-6">
            <div className="w-20 h-20 bg-brand-primary-soft border border-brand-primary/30 text-brand-primary rounded-full flex items-center justify-center mx-auto elevation-2">
              <Trophy size={40} />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-text-primary">Quiz Completed!</h2>
              <p className="text-sm font-semibold text-text-secondary mt-1">
                You scored <span className="text-brand-primary font-bold">{correctCount}</span> out of <span className="font-bold text-text-primary">{totalQuestions}</span> questions correctly ({Math.round((correctCount / totalQuestions) * 100)}%)
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
                    className="btn-primary flex-1 py-3 px-6 text-xs font-bold elevation-1 cursor-pointer"
                  >
                    Retry Quiz
                  </button>
                  <button
                    onClick={onClose}
                    className="flex-1 py-3 px-6 text-xs font-bold rounded-[1.25rem] border border-border bg-white/50 text-text-primary hover:bg-black/5 cursor-pointer"
                  >
                    Close
                  </button>
                </>
              ) : (
                <button
                  onClick={() => setSetupStep(true)}
                  className="btn-primary w-full py-3 px-6 text-xs font-bold elevation-1 cursor-pointer"
                >
                  Take Another Quiz
                </button>
              )}
            </div>
          </div>
        ) : generating || !quiz ? (
          /* ─── GENERATING QUIZ LOADING SCREEN ─── */
          <div className="py-16 text-center space-y-5">
            <div className="w-16 h-16 bg-brand-primary-soft border border-brand-primary/30 text-brand-primary rounded-full flex items-center justify-center mx-auto elevation-2">
              <RefreshCw size={28} className="animate-spin" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-text-primary">Generating AI Quiz...</h2>
              <p className="text-sm font-medium text-text-secondary mt-1">
                Creating personalized questions from your study materials
              </p>
            </div>
            <div className="flex items-center justify-center gap-1.5 mt-4">
              {[0, 1, 2].map((i) => (
                <motion.div
                  key={i}
                  className="w-2.5 h-2.5 rounded-full bg-brand-primary"
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
            <div className="text-center">
              <h3 className="text-xs font-bold uppercase tracking-widest text-text-primary mb-2">
                QUIZ PROGRESS ({displayQNum}/{totalQuestions})
              </h3>
              <div className="w-full max-w-lg mx-auto border border-border rounded-full h-7 bg-black/5 relative p-1 overflow-hidden flex items-center justify-center">
                <div
                  className="bg-brand-primary h-full rounded-full transition-all duration-500 absolute left-1 top-1 bottom-1"
                  style={{ width: `calc(${progressPct}% - 8px)` }}
                />
                <span className="relative z-10 text-[11px] font-bold text-text-primary">
                  {progressPct}%
                </span>
              </div>
            </div>

            {/* Question Text */}
            <div className="text-left mt-6">
              <h2 className="text-lg sm:text-xl font-bold text-text-primary leading-snug">
                Question: {currentQuestion?.question_text}
              </h2>
            </div>

            {/* Option Cards */}
            <div className="space-y-3">
              {currentQuestion?.options.map((option, idx) => {
                const label = OPTION_LABELS[idx]
                const isSelected = selectedOpt === label
                const isCorrect = label === currentQuestion.correct_answer

                let cardStyle =
                  'bg-white/50 border-border text-text-primary hover:border-brand-primary/40 hover:bg-white'
                let circleStyle = 'border-border group-hover:border-brand-primary'

                if (isAnswered) {
                  if (isCorrect) {
                    cardStyle = 'bg-success-soft border-success text-success font-bold'
                    circleStyle = 'border-success bg-success text-white'
                  } else if (isSelected) {
                    cardStyle = 'bg-error-soft border-error text-error font-bold'
                    circleStyle = 'border-error bg-error text-white'
                  } else {
                    cardStyle = 'opacity-50 bg-white/50 border-border text-text-muted'
                  }
                } else if (isSelected) {
                  cardStyle = 'bg-brand-primary-soft border-brand-primary text-brand-primary font-bold elevation-1'
                  circleStyle = 'border-brand-primary bg-brand-primary text-white'
                }

                return (
                  <div
                    key={label}
                    onClick={() => handleOptionSelect(label)}
                    className={`w-full border rounded-[1.5rem] p-4 text-left font-bold text-sm flex items-center justify-between transition-all elevation-1 group cursor-pointer ${cardStyle}`}
                  >
                    <span>{label}) {option}</span>
                    <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0 transition-all ${circleStyle}`}>
                      {isSelected && <div className="w-2 h-2 rounded-full bg-white" />}
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
                className="p-4 bg-brand-primary-soft border border-brand-primary/30 rounded-[1.5rem] text-xs text-text-primary text-left leading-relaxed font-medium"
              >
                <span className="font-bold text-brand-primary flex items-center gap-1.5 mb-1">
                  <Brain size={14} /> Explanation:
                </span>
                <p>{currentQuestion?.explanation}</p>
              </motion.div>
            )}

            {/* Centered Action Button */}
            <div className="pt-4 flex justify-center">
              {!isAnswered ? (
                <button
                  onClick={handleChooseAnswer}
                  disabled={!selectedOpt}
                  className="btn-primary font-bold px-8 py-3 rounded-full text-sm elevation-1 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                >
                  Choose answer
                </button>
              ) : (
                <button
                  onClick={handleNext}
                  className="btn-primary font-bold px-8 py-3 rounded-full text-sm elevation-1 flex items-center gap-2 cursor-pointer"
                >
                  <span>{currentQIndex === totalQuestions - 1 ? 'Finish Quiz' : 'Next Question'}</span>
                  <ArrowRight size={16} />
                </button>
              )}
            </div>

          </div>
        )}
      </motion.div>
    </div>
  )
}
