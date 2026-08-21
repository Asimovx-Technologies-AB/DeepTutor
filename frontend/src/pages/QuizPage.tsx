import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Trophy, Clock, ArrowLeft, ChevronRight, Sparkles, RefreshCw, AlertCircle, CheckCircle2, BookOpen } from 'lucide-react'
import { quizApi } from '../services/api'
import { useChatStore } from '../stores/chatStore'
import { useSubjectStore } from '../stores/subjectStore'

const OPTION_LABELS = ['A', 'B', 'C', 'D']

export default function QuizPage() {
  const { topicId: rawTopicId } = useParams<{ topicId?: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const locationState = (location.state || {}) as any
  const queryClient = useQueryClient()
  const activeSession = useChatStore((s) => s.activeSession)

  const effectiveTopicId = (rawTopicId || locationState.topicId || 'math-10-1').trim()
  const focusTopic = locationState.focusTopic || locationState.title || ''

  const [currentQ, setCurrentQ] = useState(0)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [timeLeft, setTimeLeft] = useState(0)
  const [submitted, setSubmitted] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Find topic metadata from subject store
  const subjects = useSubjectStore((s) => s.subjects)
  const subjectTopics = useSubjectStore((s) => s.topics)

  let currentTopicMeta: any = null
  let currentSubjectMeta: any = null

  for (const [sId, topics] of Object.entries(subjectTopics)) {
    const found = topics.find((t) => t.id === effectiveTopicId)
    if (found) {
      currentTopicMeta = found
      currentSubjectMeta = subjects.find((s) => s.id === sId)
      break
    }
  }

  const topicName = focusTopic || currentTopicMeta?.title || currentTopicMeta?.name || (effectiveTopicId ? effectiveTopicId.replace(/[-_]/g, ' ').toUpperCase() : 'Class 10 Practice Quiz')

  const isNoteQuiz = Boolean(locationState.noteId || locationState.noteContent || locationState.forceGenerate)

  const { data: quizzes, isLoading, refetch } = useQuery({
    queryKey: ['quiz', effectiveTopicId, locationState.noteId || 'default'],
    queryFn: () => quizApi.list(effectiveTopicId).then((r) => r.data),
    enabled: !!effectiveTopicId && !isNoteQuiz,
  })

  const [activeQuizData, setActiveQuizData] = useState<any>(null)
  const activeQuiz = activeQuizData || (Array.isArray(quizzes) && quizzes.length > 0 ? quizzes[0] : null)
  const questions = activeQuiz?.questions ?? []
  const totalQ = questions.length
  const currentQuestion = questions[currentQ]
  const progress = totalQ > 0 ? ((currentQ + 1) / totalQ) * 100 : 0

  useEffect(() => {
    setCurrentQ(0)
    setAnswers({})
    setSubmitted(false)
    setErrorMsg(null)
    setActiveQuizData(null)
  }, [effectiveTopicId, locationState.noteId])

  // If navigated from a Smart Note or no quiz exists, generate a dedicated quiz
  useEffect(() => {
    if (isNoteQuiz) {
      generateQuiz()
    } else if (!isLoading && !activeQuiz && !generating && effectiveTopicId) {
      generateQuiz()
    }
  }, [isLoading, isNoteQuiz, effectiveTopicId, locationState.noteId])

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

    // Update real subject and topic progress & quiz score
    if (effectiveTopicId && currentSubjectMeta) {
      const subjectState = useSubjectStore.getState()
      subjectState.recordQuizResult(currentSubjectMeta.id, effectiveTopicId, score, totalQ, pct)
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

    navigate(`/quiz/${effectiveTopicId}/result`, {
      state: {
        score,
        total: totalQ,
        pct,
        answers,
        quiz: activeQuiz,
        topicId: effectiveTopicId,
        subjectId: currentSubjectMeta?.id,
      },
    })
  }

  const generateQuiz = async () => {
    if (generating) return
    setGenerating(true)
    setErrorMsg(null)
    try {
      const res = await quizApi.generate({
        topic_id: effectiveTopicId,
        note_id: locationState.noteId || undefined,
        note_content: locationState.noteContent || undefined,
        focus_topic: focusTopic || locationState.title || undefined,
        difficulty: 'medium',
        num_questions: 5,
      })
      if (res.data) {
        setActiveQuizData(res.data)
        queryClient.setQueryData(['quiz', effectiveTopicId, locationState.noteId || 'default'], [res.data])
        setCurrentQ(0)
        setAnswers({})
        setSubmitted(false)
      }
    } catch (err: any) {
      console.error('Failed to generate quiz:', err)
      setErrorMsg(err.response?.data?.detail || 'Failed to generate quiz questions. Click below to try again.')
    } finally {
      setGenerating(false)
    }
  }

  const handleBackToChat = () => {
    if (currentSubjectMeta && effectiveTopicId) {
      navigate(`/subjects/${currentSubjectMeta.id}/chat/${effectiveTopicId}`)
    } else if (activeSession?.id) {
      navigate(`/chat/${activeSession.id}`)
    } else {
      navigate(-1)
    }
  }

  if (isLoading || (generating && !questions.length)) {
    return (
      <div className="min-h-[70vh] flex flex-col items-center justify-center p-6 max-w-xl mx-auto text-center">
        <div className="w-16 h-16 rounded-[2rem] bg-amber-50 border border-amber-200 flex items-center justify-center mb-5 animate-pulse elevation-3">
          <Sparkles className="w-8 h-8 text-amber-600 animate-spin" />
        </div>
        <h2 className="text-xl font-black text-[#3C3C3C] mb-2">Generating 10th Standard Practice Quiz...</h2>
        <p className="text-sm text-[#777777] max-w-md">
          Indie-Tutor is generating 5 curriculum-grounded multiple choice questions from your Kerala SCERT textbook for <span className="font-bold text-[#3C3C3C]">{topicName}</span>.
        </p>
        <button
          onClick={handleBackToChat}
          className="flex items-center gap-2 text-xs font-bold text-[#6F6B63] hover:text-[#F28A45] transition-colors py-2 px-4 rounded-xl bg-white border border-[#E7E1D8] shadow-2xs cursor-pointer"
        >
          <ArrowLeft size={14} /> Back to Chat
        </button>
      </div>
    )
  }

  if (!questions.length) {
    return (
      <div className="p-6 max-w-2xl mx-auto text-center pt-16">
        <div className="glass-card p-12 bg-white border border-[#E7E1D8] shadow-sm rounded-3xl space-y-4">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-amber-100 to-orange-100 flex items-center justify-center mx-auto mb-2 border border-amber-200">
            <Trophy size={28} className="text-amber-600" />
          </div>
          <h2 className="text-xl font-black text-[#20201D]">Ready to Test Your Knowledge?</h2>
          <p className="text-[#6F6B63] text-sm max-w-md mx-auto">
            Generate an AI-powered practice quiz for <span className="font-bold text-[#20201D]">{topicName}</span>.
          </p>

          {errorMsg && (
            <div className="p-3.5 rounded-2xl bg-red-50 border border-red-200 text-red-700 text-xs font-semibold max-w-md mx-auto flex items-center gap-2 text-left">
              <AlertCircle size={16} className="flex-shrink-0 text-red-500" />
              <span>{errorMsg}</span>
            </div>
          )}

          <div className="flex items-center justify-center gap-3 pt-2">
            <button
              onClick={handleBackToChat}
              className="flex items-center gap-2 text-xs font-bold text-[#6F6B63] hover:text-[#F28A45] transition-colors py-3 px-5 rounded-2xl bg-white border border-[#E7E1D8] shadow-2xs cursor-pointer"
            >
              <ArrowLeft size={14} /> Back to Chat
            </button>
            <button
              onClick={generateQuiz}
              disabled={generating}
              className="btn-primary flex items-center gap-2 font-bold py-3 px-6 rounded-2xl cursor-pointer"
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
      </div>
    )
  }

  const timeWarning = timeLeft <= 60 && timeLeft > 0

  return (
    <div className="p-6 max-w-3xl mx-auto bg-[#F7F7F7] min-h-[90vh]">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-4 mb-6">
        <button
          onClick={() => navigate(-1)}
          className="w-10 h-10 rounded-[1.25rem] bg-white border border-[#E2E8F0] flex items-center justify-center text-[#777777] hover:text-[#1CB0F6] hover:border-[#1CB0F6]/40 transition-all cursor-pointer elevation-1"
          title="Go Back"
        >
          <ArrowLeft size={15} />
          <span>Back to Chat</span>
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            {currentSubjectMeta && (
              <span className="text-[11px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded-md bg-amber-100 text-amber-800 border border-amber-200">
                {currentSubjectMeta.name}
              </span>
            )}
            <span className="text-xs text-[#777777] font-medium">Question {currentQ + 1} of {totalQ}</span>
          </div>
          <h1 className="font-black text-[#3C3C3C] text-lg truncate">{activeQuiz?.title || topicName}</h1>
        </div>

        {/* Regenerate Button */}
        <button
          onClick={generateQuiz}
          disabled={generating}
          className="text-xs font-bold text-[#777777] hover:text-[#1CB0F6] flex items-center gap-1.5 px-3 py-2 bg-white border border-[#E2E8F0] rounded-[1.25rem] cursor-pointer elevation-1 hover:border-[#1CB0F6]/40 transition-all disabled:opacity-50"
          title="Generate fresh questions"
        >
          <RefreshCw size={13} className={generating ? 'animate-spin text-[#1CB0F6]' : ''} />
          <span className="hidden sm:inline">New Questions</span>
        </button>

        {/* Timer */}
        <div className={`flex items-center gap-2 bg-white border px-3.5 py-2 rounded-[1.25rem] text-sm font-mono font-black elevation-1 ${timeWarning ? 'text-[#FF4B4B] border-[#FF4B4B]/40 bg-[#FFD1D1]' : 'text-[#3C3C3C] border-[#E2E8F0]'}`}>
          <Clock size={15} className={timeWarning ? 'text-[#FF4B4B] animate-pulse' : 'text-[#1CB0F6]'} />
          {formatTime(timeLeft)}
        </div>
      </motion.div>

      {/* Progress bar */}
      <div className="w-full bg-[#E2E8F0] h-2 rounded-full mb-6 overflow-hidden">
        <motion.div
          className="h-full bg-[#1CB0F6] rounded-full"
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
          className="glass-card p-7 mb-6 border border-[#E2E8F0] elevation-3 bg-white rounded-[2rem]"
        >
          {/* Badge */}
          <div className="flex items-center justify-between gap-2 mb-4">
            <span className="badge badge-medium text-xs font-bold px-2.5 py-1 rounded-lg bg-[#DDF4FF] text-[#D97706] border border-[#1CB0F6]/20">
              Kerala SSLC Standard
            </span>
            <span className="text-xs text-[#AFAFAF] font-bold font-mono">Q{currentQ + 1} / {totalQ}</span>
          </div>

          <h2 className="text-base sm:text-lg font-black text-[#3C3C3C] leading-relaxed mb-6">
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
                  className={`w-full text-left p-4 rounded-[1.5rem] border transition-all flex items-center gap-3.5 cursor-pointer ${selected
                    ? 'bg-[#DDF4FF] border-[#1CB0F6] text-[#3C3C3C] font-bold elevation-1'
                    : 'bg-white border-[#E2E8F0] text-[#3C3C3C] hover:border-[#1CB0F6]/50 hover:bg-[#FFFFFF]'
                    }`}
                >
                  <span className={`w-8 h-8 rounded-[1.25rem] flex items-center justify-center text-xs font-black flex-shrink-0 transition-all ${selected ? 'bg-[#1CB0F6] text-white elevation-1' : 'bg-[#E5E5E5] text-[#777777]'
                    }`}>
                    {label}
                  </span>
                  <span className="text-sm font-semibold flex-1 leading-relaxed">{option}</span>
                  {selected && <CheckCircle2 size={18} className="text-[#1CB0F6] flex-shrink-0" />}
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
          className="btn-ghost flex items-center gap-2 disabled:opacity-30 cursor-pointer font-bold text-sm text-[#777777] hover:text-[#3C3C3C] px-4 py-2.5 rounded-[1.25rem] border border-[#E2E8F0] bg-white elevation-1"
        >
          <ArrowLeft size={16} /> Previous
        </button>

        <div className="flex gap-1.5 items-center">
          {questions.map((_: any, i: number) => (
            <button
              key={i}
              onClick={() => setCurrentQ(i)}
              className={`rounded-full transition-all cursor-pointer ${i === currentQ
                ? 'bg-[#1CB0F6] w-6 h-2.5'
                : answers[questions[i].id]
                  ? 'bg-[#58CC02] w-2.5 h-2.5'
                  : 'bg-[#E2E8F0] w-2.5 h-2.5 hover:bg-[#AFAFAF]'
                }`}
              title={`Go to Question ${i + 1}`}
            />
          ))}
        </div>

        {currentQ === totalQ - 1 ? (
          <button
            onClick={handleSubmit}
            className="btn-primary flex items-center gap-2 elevation-3 cursor-pointer font-black text-sm px-6 py-2.5 rounded-[1.25rem] text-white transition-all hover:opacity-95"
            style={{ background: '#58CC02' }}
          >
            <Trophy size={16} /> Submit Quiz
          </button>
        ) : (
          <button
            onClick={() => setCurrentQ(Math.min(totalQ - 1, currentQ + 1))}
            className="btn-primary flex items-center gap-2 elevation-3 cursor-pointer font-black text-sm px-5 py-2.5 rounded-[1.25rem] text-white transition-all hover:opacity-95"
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
          className="mt-6 p-3.5 rounded-[1.5rem] bg-[#FFF0B3] border border-[#FFC800]/30 flex items-center gap-2.5 text-[#B45309] text-xs font-bold"
        >
          <AlertCircle size={16} className="flex-shrink-0 text-[#FFC800]" />
          <span>You have {totalQ - Object.keys(answers).length} unanswered question(s) — you can still submit when ready!</span>
        </motion.div>
      )}
    </div>
  )
}
