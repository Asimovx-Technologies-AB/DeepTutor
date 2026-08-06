import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Trophy,
  RefreshCw,
  X,
  Sparkles,
  ArrowRight,
  Brain,
  BookOpen,
  Target,
  Layers,
  CheckCircle2,
  SlidersHorizontal,
  Flame
} from 'lucide-react'
import axios from 'axios'
import { useAuthStore } from '../stores/authStore'
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
  sessionId: string
  isOpen: boolean
  onClose: () => void
}

const OPTION_LABELS = ['A', 'B', 'C', 'D']

export default function GamifiedQuizGame({ sessionId, isOpen, onClose }: Props) {
  const token = useAuthStore((s) => s.token)
  const activeSession = useChatStore((s) => s.activeSession)

  const [quiz, setQuiz] = useState<Quiz | null>(null)
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)

  // Topic selection & Setup layer state
  const [setupStep, setSetupStep] = useState(true) // true = topic selection layer, false = in game
  const [scopeMode, setScopeMode] = useState<'all' | 'specific'>('all')
  const [availableTopics, setAvailableTopics] = useState<string[]>([])
  const [selectedTopic, setSelectedTopic] = useState<string>('')
  const [customTopic, setCustomTopic] = useState<string>('')
  const [difficulty, setDifficulty] = useState<'easy' | 'medium' | 'hard'>('medium')

  // Game state (no life scheme)
  const [currentQIndex, setCurrentQIndex] = useState(0)
  const [score, setScore] = useState(0)
  const [correctCount, setCorrectCount] = useState(0)
  const [streak, setStreak] = useState(0)
  const [selectedOpt, setSelectedOpt] = useState<string | null>(null)
  const [isAnswered, setIsAnswered] = useState(false)
  const [gameWon, setGameWon] = useState(false)

  const [showAutocomplete, setShowAutocomplete] = useState(false)

  // Fetch AI topic suggestions from uploaded PDF documents for current session
  useEffect(() => {
    if (!isOpen) return
    const fetchSuggestions = async () => {
      try {
        const res = await axios.get('/api/quiz/suggestions', {
          params: { session_id: sessionId || activeSession?.id, topic_id: activeSession?.topic_id },
          headers: { Authorization: `Bearer ${token}` },
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
          'Reinforcement Learning from Human Feedback (RLHF)',
          'Model Evaluation & Benchmarks',
          'Hyperparameters & Optimization'
        ])
      }
    }
    fetchSuggestions()
  }, [isOpen, sessionId, activeSession, token])

  const filteredSuggestions = availableTopics.filter((t) =>
    customTopic.trim() ? t.toLowerCase().includes(customTopic.toLowerCase().trim()) : true
  )

  const [userAnswers, setUserAnswers] = useState<Record<string, string>>({})

  // Reset game state
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

  const triggerGenerate = async () => {
    setGenerating(true)
    const effectiveTopic =
      scopeMode === 'all'
        ? 'All Topics (Entire PDF)'
        : customTopic.trim() || selectedTopic || 'General Concepts'

    try {
      const res = await axios.post(
        '/api/quiz/generate',
        {
          session_id: sessionId,
          focus_topic: effectiveTopic,
          difficulty: difficulty,
          num_questions: 5,
        },
        { headers: { Authorization: `Bearer ${token}` } }
      )
      setQuiz(res.data)
      resetGame()
      setSetupStep(false)
    } catch (err: any) {
      alert(err.response?.data?.detail ?? 'Failed to generate quiz. Make sure a document is uploaded.')
    } finally {
      setGenerating(false)
    }
  }

  const handleOptionSelect = (optionLabel: string) => {
    if (isAnswered) return
    setSelectedOpt(optionLabel)
    setIsAnswered(true)

    const currentQ = quiz?.questions[currentQIndex]
    if (!currentQ) return

    setUserAnswers((prev) => ({ ...prev, [currentQ.id]: optionLabel }))

    const isCorrect = optionLabel === currentQ.correct_answer

    if (isCorrect) {
      const nextStreak = streak + 1
      setStreak(nextStreak)
      setCorrectCount((prev) => prev + 1)
      const multiplier = nextStreak >= 3 ? 3 : nextStreak >= 2 ? 2 : 1
      setScore((prev) => prev + 10 * multiplier)
    } else {
      setStreak(0)
    }
  }

  const handleNext = async () => {
    setSelectedOpt(null)
    setIsAnswered(false)

    if (quiz && currentQIndex < quiz.questions.length - 1) {
      setCurrentQIndex((prev) => prev + 1)
    } else {
      // Submit attempt to backend database
      if (quiz) {
        try {
          await axios.post(
            `/api/quiz/${quiz.id}/submit`,
            { answers: userAnswers },
            { headers: { Authorization: `Bearer ${token}` } }
          )
        } catch {
          /* ignore */
        }
      }
      setGameWon(true)
    }
  }

  const getRank = () => {
    if (score >= 40) return { label: 'Quiz Master 🏆', color: 'text-yellow-600' }
    if (score >= 25) return { label: 'Scholar 🎓', color: 'text-indigo-600' }
    return { label: 'Active Learner 📖', color: 'text-slate-600' }
  }

  if (!isOpen) return null

  const currentQuestion = quiz?.questions[currentQIndex]
  const totalQuestions = quiz?.questions.length ?? 5
  const progressPct = ((currentQIndex + 1) / totalQuestions) * 100

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
          className="absolute top-5 right-5 text-slate-400 hover:text-slate-700 transition-colors p-1.5 hover:bg-slate-100 rounded-full z-10"
        >
          <X size={18} />
        </button>

        {setupStep || !quiz ? (
          /* ─── LAYER 1: Interactive Topic & Scope Selection ─── */
          <div className="flex-1 flex flex-col justify-between py-2">
            <div>
              {/* Header */}
              <div className="flex items-center gap-3 mb-4">
                <div className="w-11 h-11 rounded-2xl bg-indigo-50 flex items-center justify-center text-indigo-600 border border-indigo-100">
                  <SlidersHorizontal size={22} />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-slate-900">Quiz Setup</h2>
                  <p className="text-xs text-slate-500">Choose what you want to study before starting</p>
                </div>
              </div>

              {/* Scope Options */}
              <div className="space-y-3 mt-5">
                <label className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
                  1. Select Quiz Scope
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
                        All topics & concepts combined
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
                      <p className="text-xs font-bold">Specific Topic</p>
                      <p className="text-[10px] text-slate-500 mt-0.5 leading-tight">
                        Target a single concept
                      </p>
                    </div>
                  </button>
                </div>
              </div>

              {/* Specific Topic Selector */}
              {scopeMode === 'specific' && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  className="mt-5 space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
                      2. Choose Topic to Focus On
                    </label>
                    <span className="text-[10px] font-extrabold text-indigo-600 bg-indigo-50 border border-indigo-100 px-2 py-0.5 rounded-full flex items-center gap-1">
                      <Sparkles size={10} /> Extracted from PDF
                    </span>
                  </div>

                  {/* AI Suggested PDF Topic Chips */}
                  {availableTopics.length > 0 && (
                    <div className="space-y-1.5">
                      <p className="text-[11px] font-semibold text-slate-500">✨ Click a suggested topic from your document:</p>
                      <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto pr-1">
                        {availableTopics.map((topic) => {
                          const isSel = (selectedTopic === topic && !customTopic) || customTopic.trim().toLowerCase() === topic.toLowerCase()
                          return (
                            <button
                              key={topic}
                              type="button"
                              onClick={() => {
                                setSelectedTopic(topic)
                                setCustomTopic(topic)
                                setShowAutocomplete(false)
                              }}
                              className={`text-xs px-3 py-1.5 rounded-xl border transition-all cursor-pointer flex items-center gap-1.5 ${
                                isSel
                                  ? 'bg-[#111111] text-white border-[#111111] font-semibold shadow-sm'
                                  : 'bg-slate-50 text-slate-700 border-slate-200 hover:border-slate-400 hover:bg-slate-100'
                              }`}
                            >
                              {isSel && <CheckCircle2 size={12} />}
                              <span>{topic}</span>
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  {/* Custom Topic Input with Live Autocomplete Dropdown */}
                  <div className="relative pt-1">
                    <input
                      type="text"
                      value={customTopic}
                      onFocus={() => setShowAutocomplete(true)}
                      onChange={(e) => {
                        setCustomTopic(e.target.value)
                        setShowAutocomplete(true)
                      }}
                      placeholder="Type or search topic (e.g. Transformer Architecture, RLHF)..."
                      className="w-full bg-white border border-slate-300 rounded-xl px-3.5 py-2.5 text-xs font-semibold text-slate-800 focus:outline-none focus:border-[#111111] shadow-sm"
                    />

                    {/* Live Autocomplete Dropdown Menu */}
                    <AnimatePresence>
                      {showAutocomplete && customTopic.trim() && filteredSuggestions.length > 0 && (
                        <motion.div
                          initial={{ opacity: 0, y: -4 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -4 }}
                          className="absolute left-0 right-0 top-full mt-1 bg-white border border-slate-200 rounded-2xl shadow-xl z-50 max-h-48 overflow-y-auto p-1.5 space-y-1"
                        >
                          <div className="px-2.5 py-1 text-[10px] font-extrabold uppercase text-slate-400 border-b border-slate-100 flex items-center justify-between">
                            <span>Matching PDF Topics</span>
                            <span>{filteredSuggestions.length} found</span>
                          </div>

                          {filteredSuggestions.map((item) => (
                            <div
                              key={item}
                              onClick={() => {
                                setCustomTopic(item)
                                setSelectedTopic(item)
                                setShowAutocomplete(false)
                              }}
                              className="px-3 py-2 rounded-xl text-xs font-bold text-slate-800 hover:bg-[#111111] hover:text-white cursor-pointer transition-colors flex items-center justify-between"
                            >
                              <div className="flex items-center gap-2">
                                <Sparkles size={12} className="text-indigo-500" />
                                <span>{item}</span>
                              </div>
                              <span className="text-[10px] text-slate-400 font-normal">Select ↵</span>
                            </div>
                          ))}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </motion.div>
              )}

              {/* Difficulty */}
              <div className="mt-5 space-y-2">
                <label className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
                  Difficulty Level
                </label>
                <div className="flex gap-2">
                  {(['easy', 'medium', 'hard'] as const).map((d) => {
                    const active = difficulty === d
                    return (
                      <button
                        key={d}
                        type="button"
                        onClick={() => setDifficulty(d)}
                        className={`flex-1 py-2 rounded-xl text-xs font-bold capitalize border transition-all cursor-pointer ${
                          active
                            ? d === 'easy'
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-400 shadow-sm'
                              : d === 'medium'
                              ? 'bg-amber-50 text-amber-700 border-amber-400 shadow-sm'
                              : 'bg-rose-50 text-rose-700 border-rose-400 shadow-sm'
                            : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'
                        }`}
                      >
                        {d}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>

            {/* Start Button */}
            <div className="pt-5 border-t border-slate-100 flex justify-end">
              <button
                onClick={triggerGenerate}
                disabled={generating}
                className="btn-primary w-full py-3 text-sm flex items-center justify-center gap-2 shadow-lg shadow-indigo-500/20"
              >
                {generating ? (
                  <>
                    <RefreshCw size={16} className="animate-spin" /> Generating Topic Quiz...
                  </>
                ) : (
                  <>
                    <Sparkles size={16} /> Start Quiz ({scopeMode === 'all' ? 'All Topics' : customTopic || selectedTopic || 'Custom Topic'})
                  </>
                )}
              </button>
            </div>
          </div>
        ) : gameWon ? (
          /* ─── Victory / Results Screen (No Game Over state needed) ─── */
          <div className="flex-1 flex flex-col items-center justify-center text-center py-6 space-y-6">
            <div className="w-16 h-16 rounded-2xl bg-indigo-50 flex items-center justify-center text-indigo-600 shadow-md border border-indigo-100">
              <Trophy size={30} />
            </div>
            <div>
              <h2 className="text-2xl font-extrabold text-slate-900">Quiz Completed!</h2>
              <p className="text-xs text-slate-500 mt-1.5">
                You answered {correctCount} of {totalQuestions} questions correctly.
              </p>
            </div>

            <div className="bg-slate-50 border border-slate-100 rounded-2xl p-5 w-full space-y-3">
              <div>
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total Score</p>
                <p className="text-4xl font-extrabold text-indigo-600 mt-1">{score} pts</p>
              </div>
              <p className={`text-sm font-extrabold ${getRank().color}`}>{getRank().label}</p>
            </div>

            <div className="flex gap-3 w-full pt-2">
              <button
                onClick={() => setSetupStep(true)}
                className="btn-primary flex-1 py-2.5 text-xs shadow-lg shadow-indigo-500/20 flex items-center justify-center gap-1.5"
              >
                <Layers size={14} /> Change Topic / New Quiz
              </button>
              <button
                onClick={resetGame}
                className="btn-ghost flex-1 py-2.5 text-xs text-slate-600 hover:text-slate-900 flex items-center justify-center gap-1.5"
              >
                <RefreshCw size={14} /> Retake Quiz
              </button>
            </div>
          </div>
        ) : (
          /* ─── Active Quiz Screen (No Lives) ─── */
          <div className="flex-1 flex flex-col justify-between">
            <div>
              {/* Top info bar */}
              <div className="flex items-center justify-between pb-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Score</span>
                  <span className="text-sm font-black text-indigo-600 bg-indigo-50 px-2.5 py-0.5 rounded-full">
                    {score}
                  </span>
                  {streak >= 2 && (
                    <span className="text-[10px] font-bold bg-amber-50 text-amber-600 border border-amber-100 px-2 py-0.5 rounded-full flex items-center gap-1 animate-pulse">
                      <Flame size={12} /> {streak}x Streak
                    </span>
                  )}
                </div>

                <button
                  onClick={() => setSetupStep(true)}
                  className="text-[11px] font-medium text-slate-400 hover:text-indigo-600 flex items-center gap-1 transition-colors"
                >
                  <Layers size={12} /> Change Topic
                </button>
              </div>

              {/* Progress Bar */}
              <div className="w-full bg-slate-100 rounded-full h-1.5 mb-4">
                <div
                  className="bg-indigo-600 h-1.5 rounded-full transition-all duration-300"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
            </div>

            {/* Question Card */}
            <div className="flex-1 flex flex-col justify-center my-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-indigo-600 uppercase tracking-widest bg-indigo-50 px-2.5 py-0.5 rounded-md">
                  Question {currentQIndex + 1} of {totalQuestions}
                </span>
                <span className="text-[10px] text-slate-400 font-medium">
                  {quiz?.title || 'Study Quiz'}
                </span>
              </div>

              <h3 className="text-base font-bold text-slate-900 leading-snug mt-3">
                {currentQuestion?.question_text}
              </h3>

              {/* Options */}
              <div className="space-y-2 mt-4">
                {currentQuestion?.options.map((option, idx) => {
                  const label = OPTION_LABELS[idx]
                  const isSelected = selectedOpt === label
                  const isCorrect = label === currentQuestion.correct_answer

                  let optStyle =
                    'border-slate-200/80 bg-white text-slate-800 hover:border-indigo-200 hover:bg-indigo-50/10'
                  let badgeStyle = 'bg-slate-100 text-slate-700'

                  if (isAnswered) {
                    if (isCorrect) {
                      optStyle =
                        'bg-emerald-50 border-emerald-500/50 text-emerald-900 font-bold shadow-sm'
                      badgeStyle = 'bg-emerald-500 text-white'
                    } else if (isSelected) {
                      optStyle = 'bg-rose-50 border-rose-500/50 text-rose-900 font-bold'
                      badgeStyle = 'bg-rose-500 text-white'
                    } else {
                      optStyle = 'opacity-50 border-slate-100 text-slate-400 bg-slate-50/50'
                    }
                  } else if (isSelected) {
                    optStyle = 'border-indigo-500 bg-indigo-50/30 text-indigo-900 font-bold shadow-sm'
                    badgeStyle = 'bg-indigo-600 text-white'
                  }

                  return (
                    <button
                      key={label}
                      disabled={isAnswered}
                      onClick={() => handleOptionSelect(label)}
                      className={`w-full text-left p-3 rounded-xl border transition-all text-xs flex items-center gap-3 cursor-pointer ${optStyle}`}
                    >
                      <span
                        className={`w-6 h-6 rounded-lg flex items-center justify-center text-[10px] font-extrabold flex-shrink-0 ${badgeStyle}`}
                      >
                        {label}
                      </span>
                      <span className="leading-normal">{option}</span>
                    </button>
                  )
                })}
              </div>

              {/* Explanation Box */}
              <AnimatePresence>
                {isAnswered && (
                  <motion.div
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="mt-3 p-3 bg-indigo-50/40 border border-indigo-100 rounded-xl text-[11px] text-slate-700 leading-relaxed"
                  >
                    <span className="font-bold text-indigo-700 flex items-center gap-1 mb-0.5">
                      <Brain size={12} /> Explanation:
                    </span>
                    <p>{currentQuestion?.explanation}</p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Actions */}
            <div className="flex justify-end pt-3 border-t border-slate-100 mt-2">
              <button
                onClick={handleNext}
                disabled={!isAnswered}
                className="btn-primary flex items-center gap-1.5 py-2 px-5 text-xs disabled:opacity-40 disabled:cursor-not-allowed shadow-md shadow-indigo-500/10"
              >
                {currentQIndex === totalQuestions - 1 ? 'Finish Quiz' : 'Next Question'}{' '}
                <ArrowRight size={13} />
              </button>
            </div>
          </div>
        )}
      </motion.div>
    </div>
  )
}
