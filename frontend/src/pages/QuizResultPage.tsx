import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Trophy, RotateCcw, MessageSquare, CheckCircle, XCircle, ArrowLeft, Star } from 'lucide-react'
import {
  RadialBarChart, RadialBar, ResponsiveContainer,
  Tooltip, Cell, PieChart, Pie
} from 'recharts'

const OPTION_LABELS = ['A', 'B', 'C', 'D']

function ScoreRing({ pct }: { pct: number }) {
  const data = [{ name: 'Score', value: pct }, { name: 'Remaining', value: 100 - pct }]
  const color = pct >= 80 ? '#10b981' : pct >= 60 ? '#f59e0b' : '#ef4444'

  return (
    <div className="relative w-40 h-40 mx-auto">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} cx="50%" cy="50%" innerRadius={52} outerRadius={68} startAngle={90} endAngle={-270} dataKey="value" strokeWidth={0}>
            <Cell fill={color} />
            <Cell fill="rgba(255,255,255,0.04)" />
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold text-white">{pct}%</span>
        <span className="text-xs text-slate-500 mt-0.5">Score</span>
      </div>
    </div>
  )
}

function getGrade(pct: number) {
  if (pct >= 90) return { label: 'Excellent!', color: 'text-emerald-400', emoji: '🏆' }
  if (pct >= 75) return { label: 'Great Job!', color: 'text-green-400', emoji: '🎉' }
  if (pct >= 60) return { label: 'Good Effort', color: 'text-yellow-400', emoji: '👍' }
  if (pct >= 40) return { label: 'Keep Practicing', color: 'text-orange-400', emoji: '📚' }
  return { label: 'Need More Study', color: 'text-red-400', emoji: '💪' }
}

export default function QuizResultPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const { topicId } = useParams<{ topicId: string }>()

  const { score = 0, total = 0, pct = 0, answers = {}, quiz = null } = location.state ?? {}
  const grade = getGrade(pct)
  const questions = quiz?.questions ?? []

  return (
    <div className="p-6 max-w-3xl mx-auto">
      {/* Header */}
      <motion.button
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        onClick={() => navigate(-1)}
        className="flex items-center gap-2 text-slate-400 hover:text-white transition-colors mb-6 text-sm font-medium"
      >
        <ArrowLeft size={16} /> Back to Topic
      </motion.button>

      {/* Score card */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4 }}
        className="glass-card p-8 text-center mb-6 relative overflow-hidden"
      >
        {/* Background glow */}
        <div className={`absolute inset-0 opacity-5 ${pct >= 60 ? 'bg-emerald-500' : 'bg-red-500'}`} />

        <div className="relative">
          <div className="text-5xl mb-2">{grade.emoji}</div>
          <h1 className={`text-2xl font-bold mb-1 ${grade.color}`}>{grade.label}</h1>
          <p className="text-slate-400 text-sm mb-6">
            {quiz?.title ?? 'Quiz'} • {new Date().toLocaleDateString()}
          </p>

          <ScoreRing pct={pct} />

          <div className="flex items-center justify-center gap-8 mt-6">
            <div className="text-center">
              <p className="text-2xl font-bold text-emerald-400">{score}</p>
              <p className="text-xs text-slate-500">Correct</p>
            </div>
            <div className="w-px h-10 bg-white/10" />
            <div className="text-center">
              <p className="text-2xl font-bold text-slate-300">{total}</p>
              <p className="text-xs text-slate-500">Total</p>
            </div>
            <div className="w-px h-10 bg-white/10" />
            <div className="text-center">
              <p className="text-2xl font-bold text-red-400">{total - score}</p>
              <p className="text-xs text-slate-500">Wrong</p>
            </div>
          </div>
        </div>
      </motion.div>

      {/* Action buttons */}
      <div className="flex gap-3 mb-8">
        <button
          onClick={() => navigate(`/quiz/${topicId}`)}
          className="btn-ghost flex-1 flex items-center justify-center gap-2"
        >
          <RotateCcw size={15} /> Retry Quiz
        </button>
        <button
          onClick={() => navigate('/chat')}
          className="btn-primary flex-1 flex items-center justify-center gap-2"
        >
          <MessageSquare size={15} /> Ask AI Tutor
        </button>
      </div>

      {/* Answer review */}
      {questions.length > 0 && (
        <div>
          <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <Star size={18} className="text-yellow-400" /> Answer Review
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
                  className={`glass-card p-5 border ${isCorrect ? 'border-emerald-500/20' : 'border-red-500/20'}`}
                >
                  <div className="flex items-start gap-3 mb-3">
                    <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${isCorrect ? 'bg-emerald-500/20' : 'bg-red-500/20'}`}>
                      {isCorrect
                        ? <CheckCircle size={14} className="text-emerald-400" />
                        : <XCircle size={14} className="text-red-400" />}
                    </div>
                    <p className="text-sm font-medium text-slate-200 leading-relaxed">
                      <span className="text-slate-500 mr-2">Q{i + 1}.</span>
                      {q.question_text}
                    </p>
                  </div>

                  <div className="ml-9 space-y-1.5">
                    {(q.options ?? []).map((opt: string, idx: number) => {
                      const label = OPTION_LABELS[idx]
                      const isUser = label === userAnswer
                      const isCorrectOpt = label === q.correct_answer
                      return (
                        <div key={label} className={`text-xs px-3 py-1.5 rounded-lg flex items-center gap-2 ${
                          isCorrectOpt ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/20' :
                          isUser && !isCorrect ? 'bg-red-500/15 text-red-300 border border-red-500/20' :
                          'text-slate-500'
                        }`}>
                          <span className="font-bold">{label}.</span>
                          <span>{opt}</span>
                          {isCorrectOpt && <span className="ml-auto text-[10px] font-semibold text-emerald-400">✓ Correct</span>}
                          {isUser && !isCorrect && <span className="ml-auto text-[10px] font-semibold text-red-400">Your answer</span>}
                        </div>
                      )
                    })}
                  </div>

                  {q.explanation && (
                    <div className="ml-9 mt-3 p-3 rounded-xl bg-indigo-500/8 border border-indigo-500/15 text-xs text-slate-400">
                      <span className="font-semibold text-indigo-400">💡 Explanation: </span>
                      {q.explanation}
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
