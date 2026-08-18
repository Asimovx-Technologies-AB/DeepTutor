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
  const color = pct >= 80 ? '#4F8A68' : pct >= 60 ? '#D99A32' : '#C85C52'

  return (
    <div className="relative w-40 h-40 mx-auto">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} cx="50%" cy="50%" innerRadius={52} outerRadius={68} startAngle={90} endAngle={-270} dataKey="value" strokeWidth={0}>
            <Cell fill={color} />
            <Cell fill="#F4EFE7" />
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-black text-[#20201D]">{pct}%</span>
        <span className="text-xs text-[#6F6B63] font-bold mt-0.5">Score</span>
      </div>
    </div>
  )
}

function getGrade(pct: number) {
  if (pct >= 90) return { label: 'Excellent!', color: 'text-[#4F8A68]', emoji: '🏆' }
  if (pct >= 75) return { label: 'Great Job!', color: 'text-[#4F8A68]', emoji: '🎉' }
  if (pct >= 60) return { label: 'Good Effort', color: 'text-[#D99A32]', emoji: '👍' }
  if (pct >= 40) return { label: 'Keep Practicing', color: 'text-[#F28A45]', emoji: '📚' }
  return { label: 'Need More Study', color: 'text-[#C85C52]', emoji: '💪' }
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
  let topicName = quiz?.title ? quiz.title.replace('Quiz:', '').strip() : ''

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
    <div className="p-6 max-w-3xl mx-auto bg-[#FAF8F3]">
      {/* Header */}
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
        className="flex items-center gap-2 text-[#6F6B63] hover:text-[#F28A45] transition-colors mb-6 text-sm font-bold cursor-pointer"
      >
        <ArrowLeft size={16} /> Back to {isSubjectQuiz ? (activeSubject?.name || 'Subject') : 'Topic'}
      </motion.button>

      {/* Score card */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4 }}
        className="glass-card p-8 text-center mb-6 relative overflow-hidden border border-[#E7E1D8] shadow-2xs bg-white rounded-3xl"
      >
        <div className="relative">
          <div className="text-5xl mb-2">{grade.emoji}</div>
          <h1 className={`text-2xl font-black mb-1 ${grade.color}`}>{grade.label}</h1>
          <p className="text-[#6F6B63] text-sm font-medium mb-6">
            {quiz?.title ?? 'Practice Quiz'} • {new Date().toLocaleDateString()}
          </p>

          <ScoreRing pct={pct} />

          <div className="flex items-center justify-center gap-8 mt-6">
            <div className="text-center">
              <p className="text-2xl font-black text-[#4F8A68]">{score}</p>
              <p className="text-xs text-[#6F6B63] font-bold">Correct</p>
            </div>
            <div className="w-px h-10 bg-[#E7E1D8]" />
            <div className="text-center">
              <p className="text-2xl font-black text-[#20201D]">{total}</p>
              <p className="text-xs text-[#6F6B63] font-bold">Total</p>
            </div>
            <div className="w-px h-10 bg-[#E7E1D8]" />
            <div className="text-center">
              <p className="text-2xl font-black text-[#C85C52]">{total - score}</p>
              <p className="text-xs text-[#6F6B63] font-bold">Wrong</p>
            </div>
          </div>
        </div>
      </motion.div>

      {/* Action buttons */}
      <div className="flex gap-3 mb-8">
        <button
          onClick={() => navigate(`/quiz/${topicId}`)}
          className="btn-ghost flex-1 flex items-center justify-center gap-2 cursor-pointer font-bold border-[#E7E1D8] bg-white text-[#20201D] hover:bg-[#FFF9F2] shadow-2xs py-3 px-4 rounded-2xl"
        >
          <RotateCcw size={15} /> Retry Quiz
        </button>
        <button
          onClick={() => handleAskAITutor()}
          className="btn-primary flex-1 flex items-center justify-center gap-2 cursor-pointer font-black shadow-2xs py-3 px-4 rounded-2xl"
        >
          <MessageSquare size={15} /> Ask {isSubjectQuiz ? `${activeSubject?.name || 'Subject'} Tutor` : 'AI Tutor'}
        </button>
      </div>

      {/* Answer review */}
      {questions.length > 0 && (
        <div>
          <h2 className="text-lg font-black text-[#20201D] mb-4 flex items-center gap-2">
            <Star size={18} className="text-[#D99A32]" /> Answer Review
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
                  className={`glass-card p-5 border rounded-2xl bg-white ${
                    isCorrect ? 'border-[#4F8A68]/30 bg-[#E3F0E5]/20' : 'border-[#C85C52]/30 bg-[#FBE7E4]/20'
                  }`}
                >
                  <div className="flex items-start gap-3 mb-3">
                    <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${
                      isCorrect ? 'bg-[#E3F0E5] text-[#4F8A68]' : 'bg-[#FBE7E4] text-[#C85C52]'
                    }`}>
                      {isCorrect
                        ? <CheckCircle size={14} className="text-[#4F8A68]" />
                        : <XCircle size={14} className="text-[#C85C52]" />}
                    </div>
                    <p className="text-sm font-extrabold text-[#20201D] leading-relaxed">
                      <span className="text-[#969188] mr-2">Q{i + 1}.</span>
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
                          className={`text-xs px-3 py-2 rounded-xl flex items-center gap-2 font-bold transition-all ${
                            isCorrectOpt
                              ? 'bg-[#E3F0E5] text-[#35654B] border border-[#4F8A68]/30'
                              : isUser && !isCorrect
                              ? 'bg-[#FBE7E4] text-[#C85C52] border border-[#C85C52]/30'
                              : 'bg-[#FAF8F3] border border-[#E7E1D8] text-[#6F6B63]'
                          }`}
                        >
                          <span className="font-black">{label}.</span>
                          <span>{opt}</span>
                          {isCorrectOpt && <span className="ml-auto text-[10px] font-black text-[#4F8A68]">✓ Correct</span>}
                          {isUser && !isCorrect && <span className="ml-auto text-[10px] font-black text-[#C85C52]">Your answer</span>}
                        </div>
                      )
                    })}
                  </div>

                  {q.explanation && (
                    <div className="ml-9 mt-3 p-3 rounded-xl bg-[#FFF0E4] border border-[#F28A45]/20 text-xs text-[#20201D] flex items-start gap-2">
                      <Sparkles size={14} className="text-[#F28A45] flex-shrink-0 mt-0.5" />
                      <div>
                        <span className="font-black text-[#F28A45]">Explanation: </span>
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
                        className="text-xs font-bold text-[#F28A45] hover:text-[#D97706] flex items-center gap-1.5 py-1 px-2.5 rounded-lg hover:bg-[#FFF0E4] transition-colors cursor-pointer"
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
      )}
    </div>
  )
}
