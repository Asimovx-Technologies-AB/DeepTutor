import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Trophy, Clock, ArrowLeft, ChevronRight, Sparkles, RefreshCw, AlertCircle, CheckCircle2, BookOpen } from 'lucide-react'
import { quizApi } from '../services/api'
import { useChatStore } from '../stores/chatStore'
import { useSubjectStore } from '../stores/subjectStore'

const OPTION_LABELS = ['A', 'B', 'C', 'D']

export default function QuizPage() {
  const { topicId } = useParams<{ topicId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const activeSession = useChatStore((s) => s.activeSession)
  const [currentQ, setCurrentQ] = useState(0)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [timeLeft, setTimeLeft] = useState(0)
  const [submitted, setSubmitted] = useState(false)
  const [generating, setGenerating] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Find topic metadata from subject store
  const subjects = useSubjectStore((s) => s.subjects)
  const subjectTopics = useSubjectStore((s) => s.topics)

  let currentTopicMeta: any = null
  let currentSubjectMeta: any = null

  for (const [sId, topics] of Object.entries(subjectTopics)) {
    const found = topics.find((t) => t.id === topicId)
    if (found) {
      currentTopicMeta = found
      currentSubjectMeta = subjects.find((s) => s.id === sId)
      break
    }
  }

  const topicName = currentTopicMeta?.name || (topicId ? topicId.replace(/[-_]/g, ' ').toUpperCase() : 'Topic Quiz')

  const { data: quizzes, isLoading, refetch } = useQuery({
    queryKey: ['quiz', topicId],
    queryFn: () => quizApi.list(topicId!).then((r) => r.data),
    enabled: !!topicId,
  })

  const activeQuiz = Array.isArray(quizzes) && quizzes.length > 0 ? quizzes[0] : null
  const questions = activeQuiz?.questions ?? []
  const totalQ = questions.length
  const currentQuestion = questions[currentQ]
  const progress = totalQ > 0 ? ((currentQ + 1) / totalQ) * 100 : 0

  useEffect(() => {
    setCurrentQ(0)
    setAnswers({})
    setSubmitted(false)
  }, [topicId])

  // If no quiz exists after loading, auto-trigger quiz generation for curriculum topics
  useEffect(() => {
    if (!isLoading && !activeQuiz && !generating && topicId) {
      generateQuiz()
    }
  }, [isLoading, activeQuiz, topicId])

  useEffect(() => {
    if (activeQuiz?.time_limit_mins) {
      setTimeLeft(activeQuiz.time_limit_mins * 60)
    } else if (questions.length > 0) {
      setTimeLeft(10 * 60) // default 10 mins
    }
  }, [activeQuiz, questions.length])

  useEffect(() => {
    if (timeLeft <= 0 || submitted || totalQ === 0) return
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
  }, [timeLeft, submitted, totalQ])

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60).toString().padStart(2, '0')
    const s = (secs % 60).toString().padStart(2, '0')
    return `${m}:${s}`
  }

  const selectAnswer = (option: string) => {
    if (submitted || !currentQuestion) return
    setAnswers((prev) => ({ ...prev, [currentQuestion.id]: option }))
  }

  const handleSubmit = async () => {
    if (timerRef.current) clearInterval(timerRef.current)
    setSubmitted(true)

    // Calculate score
    const score = questions.filter((q: any) => answers[q.id] === q.correct_answer).length
    const pct = totalQ > 0 ? Math.round((score / totalQ) * 100) : 0

    // Update real subject and topic progress
    if (topicId && currentSubjectMeta) {
      const subjectState = useSubjectStore.getState()
      subjectState.updateTopicProgress(currentSubjectMeta.id, topicId, pct)
    }

    if (activeQuiz?.id) {
      try {
        await quizApi.submit(activeQuiz.id, answers)
        queryClient.invalidateQueries({ queryKey: ['progress-summary'] })
        queryClient.invalidateQueries({ queryKey: ['progress-recent-quizzes'] })
        queryClient.invalidateQueries({ queryKey: ['progress-weekly'] })
        queryClient.invalidateQueries({ queryKey: ['progress-topics'] })
        queryClient.invalidateQueries({ queryKey: ['progress-analysis'] })
      } catch (err) {
        console.error('Failed to submit quiz to database:', err)
      }
    }

    navigate(`/quiz/${topicId}/result`, {
      state: {
        score,
        total: totalQ,
        pct,
        answers,
        quiz: activeQuiz,
        topicId,
        subjectId: currentSubjectMeta?.id,
      },
    })
  }

  const generateQuiz = async () => {
    if (generating) return
    setGenerating(true)
    try {
      const res = await quizApi.generate({
        topic_id: topicId!,
        difficulty: 'medium',
        num_questions: 5,
      })
      if (res.data) {
        queryClient.setQueryData(['quiz', topicId], [res.data])
        setCurrentQ(0)
        setAnswers({})
        setSubmitted(false)
      }
    } catch (err) {
      console.error('Failed to generate quiz:', err)
    } finally {
      setGenerating(false)
    }
  }

  if (isLoading || (generating && !questions.length)) {
    return (
      <div className="min-h-[70vh] flex flex-col items-center justify-center p-6 max-w-xl mx-auto text-center">
        <div className="w-16 h-16 rounded-3xl bg-amber-50 border border-amber-200 flex items-center justify-center mb-5 animate-pulse shadow-sm">
          <Sparkles className="w-8 h-8 text-amber-600 animate-spin" />
        </div>
        <h2 className="text-xl font-black text-[#20201D] mb-2">Generating 10th Standard Practice Quiz...</h2>
        <p className="text-sm text-[#6F6B63] max-w-md">
          DeepTutor is generating 5 curriculum-grounded multiple choice questions from your Kerala SCERT textbook for <span className="font-bold text-[#20201D]">{topicName}</span>.
        </p>
      </div>
    )
  }

  if (!questions.length) {
    return (
      <div className="p-6 max-w-2xl mx-auto text-center pt-16">
        <div className="glass-card p-12 bg-white border border-[#E7E1D8] shadow-sm rounded-3xl">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-amber-100 to-orange-100 flex items-center justify-center mx-auto mb-4 border border-amber-200">
            <Trophy size={28} className="text-amber-600" />
          </div>
          <h2 className="text-xl font-black text-[#20201D] mb-2">Ready to Test Your Knowledge?</h2>
          <p className="text-[#6F6B63] text-sm mb-6">
            Generate an AI-powered practice quiz for <span className="font-bold text-[#20201D]">{topicName}</span>.
          </p>
          <button
            onClick={generateQuiz}
            disabled={generating}
            className="btn-primary flex items-center gap-2 mx-auto font-bold py-3 px-6 rounded-2xl cursor-pointer"
          >
            {generating ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Generating Questions...
              </>
            ) : (
              <>
                <Sparkles size={16} /> Generate Practice Quiz
              </>
            )}
          </button>
        </div>
      </div>
    )
  }

  const timeWarning = timeLeft <= 60 && timeLeft > 0

  return (
    <div className="p-6 max-w-3xl mx-auto bg-[#FAF8F3] min-h-[90vh]">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-4 mb-6">
        <button
          onClick={() => navigate(-1)}
          className="w-10 h-10 rounded-xl bg-white border border-[#E7E1D8] flex items-center justify-center text-[#6F6B63] hover:text-[#F28A45] hover:border-[#F28A45]/40 transition-all cursor-pointer shadow-2xs"
          title="Go Back"
        >
          <ArrowLeft size={18} />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            {currentSubjectMeta && (
              <span className="text-[11px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded-md bg-amber-100 text-amber-800 border border-amber-200">
                {currentSubjectMeta.name}
              </span>
            )}
            <span className="text-xs text-[#6F6B63] font-medium">Question {currentQ + 1} of {totalQ}</span>
          </div>
          <h1 className="font-black text-[#20201D] text-lg truncate">{activeQuiz?.title || topicName}</h1>
        </div>

        {/* Regenerate Button */}
        <button
          onClick={generateQuiz}
          disabled={generating}
          className="text-xs font-bold text-[#6F6B63] hover:text-[#F28A45] flex items-center gap-1.5 px-3 py-2 bg-white border border-[#E7E1D8] rounded-xl cursor-pointer shadow-2xs hover:border-[#F28A45]/40 transition-all disabled:opacity-50"
          title="Generate fresh questions"
        >
          <RefreshCw size={13} className={generating ? 'animate-spin text-[#F28A45]' : ''} />
          <span className="hidden sm:inline">New Questions</span>
        </button>

        {/* Timer */}
        <div className={`flex items-center gap-2 bg-white border px-3.5 py-2 rounded-xl text-sm font-mono font-black shadow-2xs ${timeWarning ? 'text-[#C85C52] border-[#C85C52]/40 bg-[#FBE7E4]' : 'text-[#20201D] border-[#E7E1D8]'}`}>
          <Clock size={15} className={timeWarning ? 'text-[#C85C52] animate-pulse' : 'text-[#F28A45]'} />
          {formatTime(timeLeft)}
        </div>
      </motion.div>

      {/* Progress bar */}
      <div className="w-full bg-[#E7E1D8] h-2 rounded-full mb-6 overflow-hidden">
        <motion.div
          className="h-full bg-[#F28A45] rounded-full"
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
          transition={{ duration: 0.2 }}
          className="glass-card p-7 mb-6 border border-[#E7E1D8] shadow-sm bg-white rounded-3xl"
        >
          {/* Badge */}
          <div className="flex items-center justify-between gap-2 mb-4">
            <span className="badge badge-medium text-xs font-bold px-2.5 py-1 rounded-lg bg-[#FFF0E4] text-[#D97706] border border-[#F28A45]/20">
              Kerala SSLC Standard
            </span>
            <span className="text-xs text-[#969188] font-bold font-mono">Q{currentQ + 1} / {totalQ}</span>
          </div>

          <h2 className="text-base sm:text-lg font-black text-[#20201D] leading-relaxed mb-6">
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
                  className={`w-full text-left p-4 rounded-2xl border transition-all flex items-center gap-3.5 cursor-pointer ${selected
                      ? 'bg-[#FFF0E4] border-[#F28A45] text-[#20201D] font-bold shadow-2xs'
                      : 'bg-white border-[#E7E1D8] text-[#20201D] hover:border-[#F28A45]/50 hover:bg-[#FFF9F2]'
                    }`}
                >
                  <span className={`w-8 h-8 rounded-xl flex items-center justify-center text-xs font-black flex-shrink-0 transition-all ${selected ? 'bg-[#F28A45] text-white shadow-2xs' : 'bg-[#F4EFE7] text-[#6F6B63]'
                    }`}>
                    {label}
                  </span>
                  <span className="text-sm font-semibold flex-1 leading-relaxed">{option}</span>
                  {selected && <CheckCircle2 size={18} className="text-[#F28A45] flex-shrink-0" />}
                </button>
              )
            })}
          </div>
        </motion.div>
      </AnimatePresence>

      {/* Navigation */}
      <div className="flex items-center justify-between pt-2">
        <button
          onClick={() => setCurrentQ(Math.max(0, currentQ - 1))}
          disabled={currentQ === 0}
          className="btn-ghost flex items-center gap-2 disabled:opacity-30 cursor-pointer font-bold text-sm text-[#6F6B63] hover:text-[#20201D] px-4 py-2.5 rounded-xl border border-[#E7E1D8] bg-white shadow-2xs"
        >
          <ArrowLeft size={16} /> Previous
        </button>

        <div className="flex gap-1.5 items-center">
          {questions.map((_: any, i: number) => (
            <button
              key={i}
              onClick={() => setCurrentQ(i)}
              className={`rounded-full transition-all cursor-pointer ${i === currentQ
                  ? 'bg-[#F28A45] w-6 h-2.5'
                  : answers[questions[i].id]
                    ? 'bg-[#4F8A68] w-2.5 h-2.5'
                    : 'bg-[#E7E1D8] w-2.5 h-2.5 hover:bg-[#969188]'
                }`}
              title={`Go to Question ${i + 1}`}
            />
          ))}
        </div>

        {currentQ === totalQ - 1 ? (
          <button
            onClick={handleSubmit}
            className="btn-primary flex items-center gap-2 shadow-sm cursor-pointer font-black text-sm px-6 py-2.5 rounded-xl text-white transition-all hover:opacity-95"
            style={{ background: '#4F8A68' }}
          >
            <Trophy size={16} /> Submit Quiz
          </button>
        ) : (
          <button
            onClick={() => setCurrentQ(Math.min(totalQ - 1, currentQ + 1))}
            className="btn-primary flex items-center gap-2 shadow-sm cursor-pointer font-black text-sm px-5 py-2.5 rounded-xl text-white transition-all hover:opacity-95"
          >
            Next <ChevronRight size={16} />
          </button>
        )}
      </div>

      {/* Unanswered warning */}
      {Object.keys(answers).length < totalQ && currentQ === totalQ - 1 && (
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-6 p-3.5 rounded-2xl bg-[#FFF3D8] border border-[#D99A32]/30 flex items-center gap-2.5 text-[#B45309] text-xs font-bold"
        >
          <AlertCircle size={16} className="flex-shrink-0 text-[#D99A32]" />
          <span>You have {totalQ - Object.keys(answers).length} unanswered question(s) — you can still submit when ready!</span>
        </motion.div>
      )}
    </div>
  )
}
