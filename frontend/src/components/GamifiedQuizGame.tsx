import { useState, useEffect } from 'react'
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

  // Setup layer state
  const [setupStep, setSetupStep] = useState(true)
  const [scopeMode, setScopeMode] = useState<'all' | 'specific'>('all')
  const [availableTopics, setAvailableTopics] = useState<string[]>([])
  const [selectedTopic, setSelectedTopic] = useState<string>('')
  const [customTopic, setCustomTopic] = useState<string>('')
  const [difficulty, setDifficulty] = useState<'easy' | 'medium' | 'hard'>('medium')

  // Game state
  const [currentQIndex, setCurrentQIndex] = useState(0)
  const [score, setScore] = useState(0)
  const [correctCount, setCorrectCount] = useState(0)
  const [streak, setStreak] = useState(0)
  const [selectedOpt, setSelectedOpt] = useState<string | null>(null)
  const [isAnswered, setIsAnswered] = useState(false)
  const [gameWon, setGameWon] = useState(false)

  const [showAutocomplete, setShowAutocomplete] = useState(false)

  // Fetch topics from uploaded PDF documents
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
          'Reinforcement Learning (RLHF)',
          'Model Evaluation & Benchmarks'
        ])
      }
    }
    fetchSuggestions()
  }, [isOpen, sessionId, activeSession, token])

  const filteredSuggestions = availableTopics.filter((t) =>
    customTopic.trim() ? t.toLowerCase().includes(customTopic.toLowerCase().trim()) : true
  )

  const resetGame = () => {
    setCurrentQIndex(0)
    setScore(0)
    setCorrectCount(0)
    setStreak(0)
    setSelectedOpt(null)
    setIsAnswered(false)
    setGameWon(false)
  }

  const triggerGenerate = async () => {
    setGenerating(true)
    const effectiveTopic =
      scopeMode === 'all'
        ? 'All Topics (Entire PDF)'
        : customTopic.trim() || selectedTopic || 'General Study Concepts'

    try {
      const res = await axios.post(
        '/api/quiz/generate',
        {
          session_id: sessionId || activeSession?.id,
          topic_id: activeSession?.topic_id || 'general',
          custom_topic: effectiveTopic,
          difficulty: difficulty,
          num_questions: 5,
        },
        { headers: { Authorization: `Bearer ${token}` } }
      )
      setQuiz(res.data)
      resetGame()
      setSetupStep(false)
    } catch (err: any) {
      console.error(err)
      alert(err.response?.data?.detail || 'Failed to generate quiz. Make sure you have uploaded a PDF document and Ollama is running.')
      setSetupStep(true)
    } finally {
      setGenerating(false)
    }
  }

  const handleOptionSelect = (optLabel: string) => {
    if (isAnswered) return
    setSelectedOpt(optLabel)
  }

  const handleChooseAnswer = () => {
    if (!selectedOpt || !currentQuestion || isAnswered) return
    setIsAnswered(true)
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
        className="bg-white rounded-3xl p-6 sm:p-8 w-full max-w-2xl shadow-2xl border border-slate-200 flex flex-col relative max-h-[90vh] overflow-y-auto"
      >
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-5 right-5 p-2 text-slate-400 hover:text-slate-700 rounded-full hover:bg-slate-100 transition-colors z-20"
        >
          <X size={20} />
        </button>

        {/* ─── SETUP LAYER SCREEN ─── */}
        {setupStep ? (
          <div className="space-y-6 text-left">
            <div className="flex items-center gap-3 border-b border-slate-100 pb-4">
              <div className="w-10 h-10 rounded-2xl bg-[#004789] text-white flex items-center justify-center shadow-md">
                <Trophy size={20} />
              </div>
              <div>
                <h2 className="text-xl font-black text-slate-900">Interactive AI Quiz</h2>
                <p className="text-xs text-slate-500 font-medium">Configure scope & difficulty from your materials</p>
              </div>
            </div>

            {/* Scope Selection */}
            <div>
              <label className="text-xs font-bold text-slate-400 uppercase tracking-wider block mb-2">
                1. Select Quiz Scope
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
                  <Target size={20} className={scopeMode === 'specific' ? 'text-[#004789]' : 'text-slate-400'} />
                  <div>
                    <p className="text-sm font-extrabold">Specific Topic</p>
                    <p className="text-xs text-slate-500 mt-0.5">Focus on 1 concept</p>
                  </div>
                </button>
              </div>
            </div>

            {/* Specific Topic Autocomplete */}
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
                  placeholder="Or type topic name..."
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-xs font-semibold text-slate-800 outline-none focus:bg-white focus:border-[#004789]"
                />
              </motion.div>
            )}

            {/* Difficulty selection */}
            <div>
              <label className="text-xs font-bold text-slate-400 uppercase tracking-wider block mb-2">
                Difficulty Level
              </label>
              <div className="flex gap-3">
                {(['easy', 'medium', 'hard'] as const).map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setDifficulty(d)}
                    className={`flex-1 py-2.5 rounded-xl text-xs font-extrabold capitalize border transition-all ${
                      difficulty === d
                        ? 'bg-[#004789] text-white border-[#004789] shadow-md'
                        : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'
                    }`}
                  >
                    {d}
                  </button>
                ))}
              </div>
            </div>

            {/* Generate Button */}
            <button
              onClick={triggerGenerate}
              disabled={generating}
              className="w-full bg-[#004789] hover:bg-[#003566] text-white font-bold py-3.5 px-6 rounded-2xl text-sm shadow-lg shadow-blue-900/20 transition-all flex items-center justify-center gap-2"
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
            <div className="w-20 h-20 bg-amber-100 text-amber-600 rounded-full flex items-center justify-center mx-auto shadow-xl">
              <Trophy size={40} />
            </div>
            <div>
              <h2 className="text-2xl font-black text-slate-900">Quiz Completed!</h2>
              <p className="text-sm font-semibold text-slate-500 mt-1">
                You scored <span className="text-[#004789] font-bold">{correctCount}</span> out of <span className="font-bold">{totalQuestions}</span> questions correctly ({Math.round((correctCount / totalQuestions) * 100)}%)
              </p>
            </div>
            <div className="flex gap-4 max-w-sm mx-auto pt-4">
              <button
                onClick={() => setSetupStep(true)}
                className="w-full bg-[#004789] hover:bg-[#003566] text-white font-bold py-3 px-6 rounded-full text-xs shadow-md transition-all"
              >
                Take Another Quiz
              </button>
            </div>
          </div>
        ) : (
          /* ─── ACTIVE QUIZ SCREEN (MATCHING USER REFERENCE DESIGN) ─── */
          <div className="space-y-6">
            
            {/* QUIZ PROGRESS (0/2) Header & Progress Bar */}
            <div className="text-center">
              <h3 className="text-xs font-black uppercase tracking-widest text-slate-900 mb-2">
                QUIZ PROGRESS ({displayQNum}/{totalQuestions})
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

            {/* Question Text */}
            <div className="text-left mt-6">
              <h2 className="text-lg sm:text-xl font-bold text-slate-900 leading-snug">
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
                  'bg-[#f8fafc] border-slate-200/90 text-slate-800 hover:border-blue-400 hover:bg-[#f0f7ff]'
                let circleStyle = 'border-slate-300 group-hover:border-blue-500'

                if (isAnswered) {
                  if (isCorrect) {
                    cardStyle = 'bg-emerald-50 border-emerald-500 text-emerald-900 font-bold'
                    circleStyle = 'border-emerald-600 bg-emerald-600 text-white'
                  } else if (isSelected) {
                    cardStyle = 'bg-rose-50 border-rose-500 text-rose-900 font-bold'
                    circleStyle = 'border-rose-600 bg-rose-600 text-white'
                  } else {
                    cardStyle = 'opacity-50 bg-slate-50 border-slate-100 text-slate-400'
                  }
                } else if (isSelected) {
                  cardStyle = 'bg-blue-50/70 border-[#004789] text-[#004789] font-bold shadow-sm'
                  circleStyle = 'border-[#004789] bg-[#004789] text-white'
                }

                return (
                  <div
                    key={label}
                    onClick={() => handleOptionSelect(label)}
                    className={`w-full border rounded-2xl p-4 text-left font-medium text-sm flex items-center justify-between transition-all shadow-sm group cursor-pointer ${cardStyle}`}
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
                className="p-4 bg-blue-50/60 border border-blue-200 rounded-2xl text-xs text-slate-800 text-left leading-relaxed"
              >
                <span className="font-bold text-[#004789] flex items-center gap-1.5 mb-1">
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
                  className="bg-[#004789] hover:bg-[#003566] text-white font-bold px-8 py-3 rounded-full text-sm shadow-md disabled:opacity-40 disabled:cursor-not-allowed transition-all active:scale-[0.98]"
                >
                  Choose answer
                </button>
              ) : (
                <button
                  onClick={handleNext}
                  className="bg-[#004789] hover:bg-[#003566] text-white font-bold px-8 py-3 rounded-full text-sm shadow-md transition-all active:scale-[0.98] flex items-center gap-2"
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
