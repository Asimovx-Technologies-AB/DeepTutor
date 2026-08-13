import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Trophy, Clock, ArrowLeft, ChevronRight, Brain, AlertCircle, Sparkles, RefreshCw } from 'lucide-react'
import { quizApi } from '../services/api'
import { useChatStore } from '../stores/chatStore'

const MOCK_QUIZ = {
  id: 'q1',
  title: 'Physics Fundamentals Quiz',
  difficulty: 'medium',
  time_limit_mins: 10,
  questions: [
    {
      id: 'q1', question_text: "What is Newton's First Law of Motion?",
      question_type: 'multiple_choice',
      options: ['Objects accelerate proportional to force', 'An object stays at rest or in uniform motion unless acted upon by a net force', 'For every action there is an equal opposite reaction', 'Energy cannot be created or destroyed'],
      correct_answer: 'B'
    },
    {
      id: 'q2', question_text: "Which formula represents kinetic energy?",
      question_type: 'multiple_choice',
      options: ['E = mc²', 'KE = ½mv²', 'F = ma', 'P = mv'],
      correct_answer: 'B'
    },
    {
      id: 'q3', question_text: "What is the SI unit of electric current?",
      question_type: 'multiple_choice',
      options: ['Volt', 'Watt', 'Ampere', 'Ohm'],
      correct_answer: 'C'
    },
    {
      id: 'q4', question_text: "The speed of light in a vacuum is approximately:",
      question_type: 'multiple_choice',
      options: ['3 × 10⁶ m/s', '3 × 10⁸ m/s', '3 × 10¹⁰ m/s', '3 × 10⁴ m/s'],
      correct_answer: 'B'
    },
    {
      id: 'q5', question_text: "Which of the following is a vector quantity?",
      question_type: 'multiple_choice',
      options: ['Mass', 'Temperature', 'Velocity', 'Speed'],
      correct_answer: 'C'
    },
  ]
}

const OPTION_LABELS = ['A', 'B', 'C', 'D']

export default function QuizPage() {
  const { topicId } = useParams<{ topicId: string }>()
  const navigate = useNavigate()
  const activeSession = useChatStore((s) => s.activeSession)
  const [currentQ, setCurrentQ] = useState(0)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [timeLeft, setTimeLeft] = useState(0)
  const [submitted, setSubmitted] = useState(false)
  const [generating, setGenerating] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const { data: quiz, isLoading } = useQuery({
    queryKey: ['quiz', topicId],
    queryFn: () => quizApi.list(topicId!).then((r) => r.data?.[0]),
  })

  const displayQuiz = quiz ?? MOCK_QUIZ
  const questions = displayQuiz?.questions ?? []
  const totalQ = questions.length
  const currentQuestion = questions[currentQ]
  const progress = ((currentQ + 1) / totalQ) * 100

  useEffect(() => {
    setCurrentQ(0)
    setAnswers({})
    setSubmitted(false)
  }, [topicId])

  useEffect(() => {
    if (displayQuiz?.time_limit_mins) {
      setTimeLeft(displayQuiz.time_limit_mins * 60)
    }
  }, [displayQuiz])

  useEffect(() => {
    if (timeLeft <= 0 || submitted) return
    timerRef.current = setInterval(() => {
      setTimeLeft((t) => {
        if (t <= 1) {
          handleSubmit()
          return 0
        }
        return t - 1
      })
    }, 1000)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [timeLeft, submitted])

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60).toString().padStart(2, '0')
    const s = (secs % 60).toString().padStart(2, '0')
    return `${m}:${s}`
  }

  const selectAnswer = (option: string) => {
    if (submitted) return
    setAnswers((prev) => ({ ...prev, [currentQuestion.id]: option }))
  }

  const handleSubmit = async () => {
    if (timerRef.current) clearInterval(timerRef.current)
    setSubmitted(true)
    // Calculate score locally for demo
    const score = questions.filter((q: any) => answers[q.id] === q.correct_answer).length
    const pct = Math.round((score / totalQ) * 100)
    try {
      await quizApi.submit(displayQuiz.id, answers)
    } catch { /* noop */ }
    navigate(`/quiz/${topicId}/result`, { state: { score, total: totalQ, pct, answers, quiz: displayQuiz } })
  }

  const generateQuiz = async () => {
    setGenerating(true)
    try {
      await quizApi.generate({
        topic_id: activeSession?.topic_id || topicId!,
        session_id: activeSession?.id,
        difficulty: 'medium',
      })
    } catch { /* noop */ }
    setGenerating(false)
  }

  if (isLoading) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        {[...Array(3)].map((_, i) => <div key={i} className="skeleton h-20 rounded-2xl mb-4" />)}
      </div>
    )
  }

  if (!questions.length) {
    return (
      <div className="p-6 max-w-2xl mx-auto text-center">
        <div className="glass-card p-12">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-yellow-500/20 to-orange-500/20 flex items-center justify-center mx-auto mb-4">
            <Trophy size={28} className="text-yellow-400" />
          </div>
          <h2 className="text-xl font-bold text-white mb-2">No quizzes yet</h2>
          <p className="text-slate-400 text-sm mb-6">Generate an AI-powered quiz for this topic</p>
          <button onClick={generateQuiz} disabled={generating} className="btn-primary flex items-center gap-2 mx-auto">
            {generating ? <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> Generating...</> : <><Sparkles size={15} /> Generate AI Quiz</>}
          </button>
        </div>
      </div>
    )
  }

  const timeWarning = timeLeft <= 60 && timeLeft > 0

  return (
    <div className="p-6 max-w-3xl mx-auto bg-[#FAF8F3]">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-4 mb-6">
        <button onClick={() => navigate(-1)} className="text-[#6F6B63] hover:text-[#F28A45] transition-colors cursor-pointer">
          <ArrowLeft size={18} />
        </button>
        <div className="flex-1">
          <h1 className="font-black text-[#20201D] text-lg">{displayQuiz.title}</h1>
          <p className="text-xs text-[#6F6B63] font-medium">Question {currentQ + 1} of {totalQ}</p>
        </div>
        {/* Timer */}
        <div className={`flex items-center gap-2 bg-white border border-[#E7E1D8] px-3 py-1.5 rounded-xl text-sm font-mono font-black shadow-2xs ${timeWarning ? 'text-[#C85C52] border-[#C85C52]/40 bg-[#FBE7E4]' : 'text-[#20201D]'}`}>
          <Clock size={14} className={timeWarning ? 'text-[#C85C52] animate-pulse' : 'text-[#F28A45]'} />
          {formatTime(timeLeft)}
        </div>
      </motion.div>

      {/* Progress bar */}
      <div className="progress-bar mb-6">
        <motion.div
          className="progress-fill"
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
        />
      </div>

      {/* Question card */}
      <AnimatePresence mode="wait">
        <motion.div
          key={currentQ}
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -20 }}
          transition={{ duration: 0.25 }}
          className="glass-card p-7 mb-6 border border-[#E7E1D8] shadow-2xs bg-white"
        >
          {/* Difficulty badge */}
          <div className="flex items-center gap-2 mb-4">
            <span className={`badge badge-${displayQuiz.difficulty}`}>{displayQuiz.difficulty}</span>
            <span className="text-xs text-[#969188] font-bold font-mono">Q{currentQ + 1}</span>
          </div>

          <h2 className="text-lg font-black text-[#20201D] leading-relaxed mb-6">
            {currentQuestion?.question_text}
          </h2>

          {/* Options */}
          <div className="space-y-3">
            {(currentQuestion?.options ?? []).map((option: string, idx: number) => {
              const label = OPTION_LABELS[idx]
              const selected = answers[currentQuestion.id] === label
              return (
                <button
                  key={label}
                  onClick={() => selectAnswer(label)}
                  className={`w-full text-left p-4 rounded-2xl border transition-all flex items-center gap-3 cursor-pointer ${
                    selected
                      ? 'bg-[#FFF0E4] border-[#F28A45] text-[#F28A45] font-black shadow-2xs'
                      : 'bg-white border-[#E7E1D8] text-[#20201D] hover:border-[#F28A45]/40 hover:bg-[#FFF9F2]'
                  }`}
                >
                  <span className={`w-7 h-7 rounded-xl flex items-center justify-center text-xs font-black flex-shrink-0 ${
                    selected ? 'bg-[#F28A45] text-white' : 'bg-[#F4EFE7] text-[#6F6B63]'
                  }`}>
                    {label}
                  </span>
                  <span className="text-sm font-bold">{option}</span>
                  {selected && <ChevronRight size={16} className="ml-auto text-[#F28A45]" />}
                </button>
              )
            })}
          </div>
        </motion.div>
      </AnimatePresence>

      {/* Navigation */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setCurrentQ(Math.max(0, currentQ - 1))}
          disabled={currentQ === 0}
          className="btn-ghost flex items-center gap-2 disabled:opacity-40 cursor-pointer font-bold"
        >
          <ArrowLeft size={15} /> Previous
        </button>

        <div className="flex gap-1.5">
          {questions.map((_: any, i: number) => (
            <button
              key={i}
              onClick={() => setCurrentQ(i)}
              className={`w-2 h-2 rounded-full transition-all cursor-pointer ${
                i === currentQ ? 'bg-[#F28A45] w-5' : answers[questions[i].id] ? 'bg-[#4F8A68]' : 'bg-[#E7E1D8]'
              }`}
            />
          ))}
        </div>

        {currentQ === totalQ - 1 ? (
          <button
            onClick={handleSubmit}
            className="btn-primary flex items-center gap-2 shadow-2xs cursor-pointer font-black"
            style={{ background: '#4F8A68' }}
          >
            <Trophy size={15} /> Submit Quiz
          </button>
        ) : (
          <button
            onClick={() => setCurrentQ(Math.min(totalQ - 1, currentQ + 1))}
            className="btn-primary flex items-center gap-2 shadow-2xs cursor-pointer font-black"
          >
            Next <ChevronRight size={15} />
          </button>
        )}
      </div>

      {/* Unanswered warning */}
      {Object.keys(answers).length < totalQ && currentQ === totalQ - 1 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mt-4 p-3 rounded-2xl bg-[#FFF3D8] border border-[#D99A32]/30 flex items-center gap-2 text-[#D99A32] text-xs font-bold"
        >
          <AlertCircle size={14} />
          {totalQ - Object.keys(answers).length} question(s) unanswered — you can still submit
        </motion.div>
      )}
    </div>
  )
}
