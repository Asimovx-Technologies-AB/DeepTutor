import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Trophy, RotateCcw, MessageSquare, CheckCircle,
  XCircle, ArrowLeft, Star, Sparkles, HelpCircle
} from 'lucide-react'
import {
  RadialBarChart, RadialBar, ResponsiveContainer,
  Tooltip, Cell, PieChart, Pie
} from 'recharts'
import { useSubjectStore } from '../stores/subjectStore'

const OPTION_LABELS = ['A', 'B', 'C', 'D']

function ScoreRing({ pct }: { pct: number }) {
  const data = [{ name: 'Score', value: pct }, { name: 'Remaining', value: 100 - pct }]
  const color = pct >= 80 ? '#58CC02' : pct >= 60 ? '#FFC800' : '#FF4B4B'

  return (
    <div className="relative w-40 h-40 mx-auto">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} cx="50%" cy="50%" innerRadius={52} outerRadius={68} startAngle={90} endAngle={-270} dataKey="value" strokeWidth={0}>
            <Cell fill={color} />
            <Cell fill="#E5E5E5" />
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-black text-[#3C3C3C]">{pct}%</span>
        <span className="text-xs text-[#777777] font-bold mt-0.5">Score</span>
      </div>
    </div>
  )
}

function getGrade(pct: number) {
  if (pct >= 90) return { label: 'Excellent!', color: 'text-[#58CC02]', emoji: '🏆' }
  if (pct >= 75) return { label: 'Great Job!', color: 'text-[#58CC02]', emoji: '🎉' }
  if (pct >= 60) return { label: 'Good Effort', color: 'text-[#FFC800]', emoji: '👍' }
  if (pct >= 40) return { label: 'Keep Practicing', color: 'text-[#4F46E5]', emoji: '📚' }
  return { label: 'Need More Study', color: 'text-[#FF4B4B]', emoji: '💪' }
}

export default function QuizResultPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const { topicId: routeTopicId } = useParams<{ topicId: string }>()

  const {
    score = 0,
    total = 0,
    pct = 0,
    answers = {},
    quiz = null,
    topicId = routeTopicId,
    subjectId: passedSubjectId,
  } = location.state ?? {}

  const grade = getGrade(pct)
  const questions = quiz?.questions ?? []

  // Resolve subject metadata from store
  const subjects = useSubjectStore((s) => s.subjects)
  const subjectTopics = useSubjectStore((s) => s.topics)

  let detectedSubjectId = passedSubjectId || ''
  let topicName = quiz?.title ? (quiz.title.replace('Quiz:', '') as string).trim() : ''

  if (!detectedSubjectId && topicId) {
    for (const [sId, topicsList] of Object.entries(subjectTopics)) {
      const found = topicsList.find((t) => t.id === topicId)
      if (found) {
        detectedSubjectId = sId
        topicName = topicName || found.title
        break
      }
    }
    if (!detectedSubjectId) {
      if (topicId.startsWith('math-') || topicId.startsWith('sslc-math')) detectedSubjectId = 'sslc-math'
      else if (topicId.startsWith('phys-') || topicId.startsWith('sslc-phys')) detectedSubjectId = 'sslc-physics'
      else if (topicId.startsWith('chem-') || topicId.startsWith('sslc-chem')) detectedSubjectId = 'sslc-chemistry'
    }
  }

  const isSubjectQuiz = Boolean(detectedSubjectId)
  const activeSubject = subjects.find((s) => s.id === detectedSubjectId)

  // Navigate to appropriate AI tutor
  const handleAskAITutor = (customQuestion?: string) => {
    const prompt = customQuestion || (
      isSubjectQuiz
        ? `Hi Deepy! I just completed the practice quiz on ${topicName || 'this chapter'} and scored ${score}/${total} (${pct}%). Can you help me review the core concepts and explain the solutions step-by-step?`
        : `I just completed a quiz on ${topicName || 'this topic'} and scored ${score}/${total} (${pct}%). Can you explain the key concepts?`
    )

    if (isSubjectQuiz && detectedSubjectId) {
      navigate(`/subjects/${detectedSubjectId}/chat/${topicId || ''}`, {
        state: { initialPrompt: prompt },
      })
    } else {
      navigate(`/chat/${topicId || ''}`, {
        state: { initialPrompt: prompt },
      })
    }
  }

  return (
    <div className="p-6 max-w-3xl mx-auto bg-[#F7F7F7]">
      {/* Header */}
      <div className="flex items-center justify-between">
        <motion.button
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        onClick={() => {
          if (isSubjectQuiz && detectedSubjectId) {
            navigate(`/subjects/${detectedSubjectId}`)
          } else {
            navigate(-1)
          }
        }}
        className="flex items-center gap-2 text-[#777777] hover:text-[#4F46E5] transition-colors mb-6 text-sm font-bold cursor-pointer"
      >
        <ArrowLeft size={16} /> Back to {isSubjectQuiz ? (activeSubject?.name || 'Subject') : 'Topic'}
      </motion.button>

      {isSubjectQuiz && detectedSubjectId && (
        <button
          onClick={() => navigate(`/subjects/${detectedSubjectId}`)}
          className="text-xs font-extrabold text-brand-primary hover:text-[#D97706] bg-orange-50 border border-orange-200 px-3 py-1.5 rounded-xl flex items-center gap-1 transition-all cursor-pointer shadow-2xs"
        >
          <span>{activeSubject?.name || 'Subject'} Page</span> →
        </button>
      )}
      </div>

      {/* Score Card */ }
  <motion.div
    initial={{ opacity: 0, scale: 0.96 }}
    animate={{ opacity: 1, scale: 1 }}
    transition={{ duration: 0.4 }}
    className="glass-card p-8 text-center mb-6 relative overflow-hidden border border-[#E2E8F0] elevation-1 bg-white rounded-[2rem]"
  >
    <div className="max-w-md mx-auto">
      <div className="text-5xl mb-2">{grade.emoji}</div>
      <h1 className={`text-2xl font-black mb-1 ${grade.color}`}>{grade.label}</h1>
      <p className="text-[#777777] text-sm font-medium mb-6">
        {quiz?.title ?? 'Practice Quiz'} • {new Date().toLocaleDateString()}
      </p>

      <ScoreRing pct={pct} />

      <div className="flex items-center justify-center gap-8 mt-6">
        <div className="text-center">
          <p className="text-2xl font-black text-[#58CC02]">{score}</p>
          <p className="text-xs text-[#777777] font-bold">Correct</p>
        </div>
        <div className="w-px h-10 bg-[#E2E8F0]" />
        <div className="text-center">
          <p className="text-2xl font-black text-[#3C3C3C]">{total}</p>
          <p className="text-xs text-[#777777] font-bold">Total</p>
        </div>
        <div className="w-px h-10 bg-[#E2E8F0]" />
        <div className="text-center">
          <p className="text-2xl font-black text-[#FF4B4B]">{total - score}</p>
          <p className="text-xs text-[#777777] font-bold">Wrong</p>
        </div>
      </div>
    </div>
  </motion.div>

  {/* Action buttons */ }
  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-8">
    {isSubjectQuiz && detectedSubjectId ? (
      <button
        onClick={() => navigate(`/subjects/${detectedSubjectId}`)}
        className="btn-ghost flex items-center justify-center gap-2 cursor-pointer font-extrabold border-border bg-white text-text-primary hover:bg-orange-50/50 shadow-2xs py-3 px-4 rounded-2xl text-xs"
      >
        🏛️ Subject Overview
      </button>
    ) : (
      <button
        onClick={() => navigate(-1)}
        className="btn-ghost flex items-center justify-center gap-2 cursor-pointer font-bold border-border bg-white text-text-primary hover:bg-[#FFF9F2] shadow-2xs py-3 px-4 rounded-2xl text-xs"
      >
        <ArrowLeft size={15} /> Back
      </button>
    )}
    <button
      onClick={() => navigate(`/quiz/${topicId}`)}
      className="btn-ghost flex-1 flex items-center justify-center gap-2 cursor-pointer font-bold border-[#E2E8F0] bg-white text-[#3C3C3C] hover:bg-[#FFFFFF] elevation-1 py-3 px-4 rounded-[1.5rem]"
    >
      <RotateCcw size={15} /> Retry Quiz
    </button>
    <button
      onClick={() => handleAskAITutor()}
      className="btn-primary flex-1 flex items-center justify-center gap-2 cursor-pointer font-black elevation-1 py-3 px-4 rounded-[1.5rem]"
    >
      <MessageSquare size={15} /> Ask Tutor
    </button>
  </div>

  {/* Answer review */ }
  {
    questions.length > 0 && (
      <div>
        <h2 className="text-lg font-black text-[#3C3C3C] mb-4 flex items-center gap-2">
          <Star size={18} className="text-[#FFC800]" /> Answer Review
        </h2>
        <div className="space-y-4">
          {questions.map((q: any, i: number) => {
            const userAnswer = answers[q.id]
            const isCorrect = userAnswer === q.correct_answer
            return (
              <motion.div
                key={q.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.07 }}
                className={`glass-card p-5 border rounded-[1.5rem] bg-white ${isCorrect ? 'border-[#58CC02]/30 bg-[#D7FFB8]/20' : 'border-[#FF4B4B]/30 bg-[#FFD1D1]/20'
                  }`}
              >
                <div className="flex items-start gap-3 mb-3">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${isCorrect ? 'bg-[#D7FFB8] text-[#58CC02]' : 'bg-[#FFD1D1] text-[#FF4B4B]'
                    }`}>
                    {isCorrect
                      ? <CheckCircle size={14} className="text-[#58CC02]" />
                      : <XCircle size={14} className="text-[#FF4B4B]" />}
                  </div>
                  <p className="text-sm font-extrabold text-[#3C3C3C] leading-relaxed">
                    <span className="text-[#AFAFAF] mr-2">Q{i + 1}.</span>
                    {q.question_text}
                  </p>
                </div>

                <div className="ml-9 space-y-1.5">
                  {(q.options ?? []).map((opt: string, idx: number) => {
                    const label = OPTION_LABELS[idx]
                    const isUser = label === userAnswer
                    const isCorrectOpt = label === q.correct_answer
                    return (
                      <div
                        key={label}
                        className={`text-xs px-3 py-2 rounded-[1.25rem] flex items-center gap-2 font-bold transition-all ${isCorrectOpt
                            ? 'bg-[#D7FFB8] text-[#46A302] border border-[#58CC02]/30'
                            : isUser && !isCorrect
                              ? 'bg-[#FFD1D1] text-[#FF4B4B] border border-[#FF4B4B]/30'
                              : 'bg-[#F7F7F7] border border-[#E2E8F0] text-[#777777]'
                          }`}
                      >
                        <span className="font-black">{label}.</span>
                        <span>{opt}</span>
                        {isCorrectOpt && <span className="ml-auto text-[10px] font-black text-[#58CC02]">✓ Correct</span>}
                        {isUser && !isCorrect && <span className="ml-auto text-[10px] font-black text-[#FF4B4B]">Your answer</span>}
                      </div>
                    )
                  })}
                </div>

                {q.explanation && (
                  <div className="ml-9 mt-3 p-3 rounded-[1.25rem] bg-[#EEF2FF] border border-[#4F46E5]/20 text-xs text-[#3C3C3C] flex items-start gap-2">
                    <Sparkles size={14} className="text-[#4F46E5] flex-shrink-0 mt-0.5" />
                    <div>
                      <span className="font-black text-[#4F46E5]">Explanation: </span>
                      <span>{q.explanation}</span>
                    </div>
                  </div>
                )}

                {!isCorrect && (
                  <div className="ml-9 mt-2 flex justify-end">
                    <button
                      onClick={() => {
                        const specificPrompt = `In the ${topicName || 'subject'} quiz, I missed Question ${i + 1}: "${q.question_text}". Can you explain why the correct answer is "${q.correct_answer}" and guide me through the concept?`
                        handleAskAITutor(specificPrompt)
                      }}
                      className="text-xs font-bold text-[#4F46E5] hover:text-[#D97706] flex items-center gap-1.5 py-1 px-2.5 rounded-lg hover:bg-[#EEF2FF] transition-colors cursor-pointer"
                    >
                      <MessageSquare size={13} /> Ask Tutor About This Question
                    </button>
                  </div>
                )}
              </motion.div>
            )
          })}
        </div>
      </div>
    )
  }
    </div >
  )
}
