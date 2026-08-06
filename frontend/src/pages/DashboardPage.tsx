import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  MessageSquare, Star, BookOpen, Calendar,
  Flame, ArrowRight, Brain, Zap, Clock, Send,
  Trophy, CheckCircle2, Sparkles, X
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { progressApi, chatApi } from '../services/api'

const SUBJECT_COLORS = [
  'from-indigo-500 to-violet-600',
  'from-violet-500 to-pink-600',
  'from-cyan-500 to-blue-600',
  'from-emerald-500 to-cyan-600',
  'from-orange-500 to-red-600',
  'from-rose-500 to-pink-600',
]

const SUBJECT_ICONS = ['⚛️', '🧬', '📐', '🌍', '📜', '💻']

export default function DashboardPage() {
  const { user } = useAuthStore()
  const navigate = useNavigate()

  // Quick Chat state on Dashboard
  const [quickPrompt, setQuickPrompt] = useState('')
  const [activeModal, setActiveModal] = useState<'sessions' | 'score' | 'topics' | 'streak' | null>(null)

  // Interactive Daily Goals State
  const [goals, setGoals] = useState([
    { id: 1, text: 'Ask AI Tutor a concept question', completed: true },
    { id: 2, text: 'Take a 5-question AI Quiz', completed: false },
    { id: 3, text: 'Review 5 Flashcards', completed: false },
  ])

  const toggleGoal = (id: number) => {
    setGoals(prev => prev.map(g => g.id === id ? { ...g, completed: !g.completed } : g))
  }

  const { data: progress } = useQuery({
    queryKey: ['progress-summary'],
    queryFn: () => progressApi.summary().then((r) => r.data),
  })

  const { data: sessions } = useQuery({
    queryKey: ['chat-sessions'],
    queryFn: () => chatApi.sessions().then((r) => r.data),
  })

  const recentSessions = sessions?.slice(0, 4) ?? []
  const lastSession = sessions?.[0] ?? null

  const hour = new Date().getHours()
  const timeGreeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'

  // Submit quick prompt from dashboard
  const handleQuickAsk = (e: React.FormEvent) => {
    e.preventDefault()
    if (!quickPrompt.trim()) return
    navigate('/chat', { state: { initialPrompt: quickPrompt } })
  }

  const completedGoalsCount = goals.filter(g => g.completed).length
  const goalPct = Math.round((completedGoalsCount / goals.length) * 100)

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8">
      {/* ─── HEADER & QUICK ASK BAR ─── */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col md:flex-row md:items-center justify-between gap-4"
      >
        <div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">
            {timeGreeting}, <span className="gradient-text">{user?.username}</span> 👋
          </h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Ready to learn something new today? Your AI Tutor is online.
          </p>
        </div>

        <button
          onClick={() => navigate('/chat')}
          className="btn-primary flex items-center gap-2 self-start md:self-auto shadow-lg shadow-indigo-500/20"
        >
          <Brain size={16} /> Ask AI Tutor
        </button>
      </motion.div>

      {/* ─── INTERACTIVE STAT CARDS ─── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-5">
        {/* Stat 1: Chat Sessions */}
        <motion.div
          whileHover={{ y: -3, scale: 1.01 }}
          onClick={() => setActiveModal('sessions')}
          className="glass-card p-6 cursor-pointer relative overflow-hidden group border border-slate-200/80"
        >
          <div className="flex items-start justify-between mb-4">
            <div className="w-12 h-12 rounded-2xl bg-[#111111] text-white flex items-center justify-center shadow-sm">
              <MessageSquare size={22} />
            </div>
            <span className="text-xs font-bold text-[#18181b] bg-[#f4f4f5] border border-[#e4e4e7] px-2.5 py-1 rounded-full group-hover:bg-[#e4e4e7] transition-colors">
              Details →
            </span>
          </div>
          <p className="text-3xl font-black text-[#111111] mb-1">{progress?.total_sessions ?? 0}</p>
          <p className="text-sm font-bold text-slate-700">Chat Sessions</p>
          <p className="text-xs text-slate-500 mt-0.5">Total conversations</p>
        </motion.div>

        {/* Stat 2: Avg Quiz Score */}
        <motion.div
          whileHover={{ y: -3, scale: 1.01 }}
          onClick={() => setActiveModal('score')}
          className="glass-card p-6 cursor-pointer relative overflow-hidden group border border-slate-200/80"
        >
          <div className="flex items-start justify-between mb-4">
            <div className="w-12 h-12 rounded-2xl bg-[#111111] text-white flex items-center justify-center shadow-sm">
              <Star size={22} />
            </div>
            <span className="text-xs font-bold text-[#18181b] bg-[#f4f4f5] border border-[#e4e4e7] px-2.5 py-1 rounded-full group-hover:bg-[#e4e4e7] transition-colors">
              Details →
            </span>
          </div>
          <p className="text-3xl font-black text-[#111111] mb-1">{progress?.avg_score ?? 0}%</p>
          <p className="text-sm font-bold text-slate-700">Avg Quiz Score</p>
          <p className="text-xs text-slate-500 mt-0.5">Across all quizzes</p>
        </motion.div>

        {/* Stat 3: Topics Explored */}
        <motion.div
          whileHover={{ y: -3, scale: 1.01 }}
          onClick={() => setActiveModal('topics')}
          className="glass-card p-6 cursor-pointer relative overflow-hidden group border border-slate-200/80"
        >
          <div className="flex items-start justify-between mb-4">
            <div className="w-12 h-12 rounded-2xl bg-[#111111] text-white flex items-center justify-center shadow-sm">
              <BookOpen size={22} />
            </div>
            <span className="text-xs font-bold text-[#18181b] bg-[#f4f4f5] border border-[#e4e4e7] px-2.5 py-1 rounded-full group-hover:bg-[#e4e4e7] transition-colors">
              Details →
            </span>
          </div>
          <p className="text-3xl font-black text-[#111111] mb-1">{progress?.topics_studied ?? 0}</p>
          <p className="text-sm font-bold text-slate-700">Topics Explored</p>
          <p className="text-xs text-slate-500 mt-0.5">Unique topics</p>
        </motion.div>

        {/* Stat 4: Day Streak */}
        <motion.div
          whileHover={{ y: -3, scale: 1.01 }}
          onClick={() => setActiveModal('streak')}
          className="glass-card p-6 cursor-pointer relative overflow-hidden group border border-slate-200/80"
        >
          <div className="flex items-start justify-between mb-4">
            <div className="w-12 h-12 rounded-2xl bg-[#111111] text-white flex items-center justify-center shadow-sm">
              <Flame size={22} className="text-orange-400" />
            </div>
            <span className="text-xs font-bold text-[#18181b] bg-[#f4f4f5] border border-[#e4e4e7] px-2.5 py-1 rounded-full group-hover:bg-[#e4e4e7] transition-colors">
              Details →
            </span>
          </div>
          <p className="text-3xl font-black text-[#111111] mb-1">{progress?.streak_days ?? 0}</p>
          <p className="text-sm font-bold text-slate-700">Day Streak</p>
          <p className="text-xs text-slate-500 mt-0.5">Keep it up!</p>
        </motion.div>
      </div>

      {/* ─── INTERACTIVE QUICK QUESTION SEARCH BAR ─── */}
      <div className="glass-card p-4 border border-indigo-100 bg-gradient-to-r from-indigo-50/50 via-white to-violet-50/50">
        <form onSubmit={handleQuickAsk} className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-indigo-600 text-white flex items-center justify-center flex-shrink-0 shadow-md shadow-indigo-600/20">
            <Sparkles size={18} />
          </div>
          <input
            type="text"
            value={quickPrompt}
            onChange={(e) => setQuickPrompt(e.target.value)}
            placeholder="Ask AI Tutor anything... (e.g., 'Explain Quantum Entanglement simply')"
            className="flex-1 bg-transparent text-sm font-medium text-slate-800 placeholder-slate-400 focus:outline-none"
          />
          <button
            type="submit"
            disabled={!quickPrompt.trim()}
            className="btn-primary py-2 px-4 text-xs flex items-center gap-1.5 disabled:opacity-40 shadow-sm"
          >
            Ask AI <Send size={12} />
          </button>
        </form>
      </div>

      {/* ─── HERO STUDY BANNER & DAILY GOAL WIDGET ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Continue Learning Banner */}
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="lg:col-span-2 relative overflow-hidden rounded-3xl p-7 flex flex-col justify-between"
          style={{
            background: 'linear-gradient(135deg, rgba(99,102,241,0.1) 0%, rgba(139,92,246,0.1) 50%, rgba(34,211,238,0.05) 100%)',
            border: '1px solid rgba(99,102,241,0.2)'
          }}
        >
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Zap size={15} className="text-amber-500" />
              <span className="text-xs font-bold text-indigo-600 uppercase tracking-widest">
                AI-Powered GraphRAG Learning
              </span>
            </div>
            <h2 className="text-2xl font-black text-slate-900 mb-1">
              {lastSession ? `Continue: "${lastSession.session_title}"` : 'Start your study session'}
            </h2>
            <p className="text-slate-600 text-xs max-w-lg leading-relaxed">
              {lastSession
                ? `Last active ${new Date(lastSession.started_at).toLocaleDateString()} — pick up right where you stopped.`
                : 'Your local GraphRAG AI tutor is ready. Upload PDFs, generate knowledge graphs, and test yourself with AI quizzes.'}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3 mt-6">
            {lastSession ? (
              <button
                onClick={() => navigate(`/chat/${lastSession.id}`)}
                className="btn-primary flex items-center gap-2 py-2.5 px-5 text-xs shadow-md shadow-indigo-500/20"
              >
                Resume Session <ArrowRight size={14} />
              </button>
            ) : (
              <button
                onClick={() => navigate('/chat')}
                className="btn-primary flex items-center gap-2 py-2.5 px-5 text-xs shadow-md shadow-indigo-500/20"
              >
                Start Chatting <ArrowRight size={14} />
              </button>
            )}
            <button
              onClick={() => navigate('/study-plan')}
              className="btn-ghost flex items-center gap-2 py-2.5 px-4 text-xs font-bold text-slate-700"
            >
              <Calendar size={14} className="text-indigo-600" /> Create Study Plan
            </button>
          </div>
        </motion.div>

        {/* Interactive Daily Goals Checklist */}
        <div className="glass-card p-6 border border-slate-200/80 flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Trophy size={16} className="text-amber-500" />
                <h3 className="font-bold text-slate-900 text-sm">Today's Study Goal</h3>
              </div>
              <span className="text-xs font-bold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full">
                {goalPct}%
              </span>
            </div>

            {/* Goal Progress bar */}
            <div className="w-full bg-slate-100 rounded-full h-1.5 mb-4">
              <motion.div
                className="bg-indigo-600 h-1.5 rounded-full"
                animate={{ width: `${goalPct}%` }}
                transition={{ duration: 0.4 }}
              />
            </div>

            {/* Goals List */}
            <div className="space-y-2">
              {goals.map((g) => (
                <button
                  key={g.id}
                  onClick={() => toggleGoal(g.id)}
                  className={`w-full p-2.5 rounded-xl border text-left transition-all flex items-center gap-2.5 cursor-pointer text-xs ${
                    g.completed
                      ? 'bg-emerald-50/50 border-emerald-200 text-emerald-900 font-medium line-through'
                      : 'bg-slate-50/60 border-slate-200 text-slate-700 hover:bg-slate-100'
                  }`}
                >
                  <CheckCircle2
                    size={16}
                    className={g.completed ? 'text-emerald-600 flex-shrink-0' : 'text-slate-300 flex-shrink-0'}
                  />
                  <span>{g.text}</span>
                </button>
              ))}
            </div>
          </div>

          <p className="text-[10px] text-slate-400 text-center font-medium">Click items to complete today's goals</p>
        </div>
      </div>

      {/* ─── RECENT SESSIONS ─── */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-slate-900">Recent Sessions</h2>
          <button
            onClick={() => navigate('/chat')}
            className="text-xs text-indigo-600 hover:text-indigo-700 font-bold transition-colors"
          >
            View all →
          </button>
        </div>

        {recentSessions.length === 0 ? (
          <div className="glass-card p-8 text-center border border-slate-200/70">
            <div className="w-14 h-14 rounded-2xl bg-indigo-50 flex items-center justify-center mx-auto mb-3 text-indigo-600 border border-indigo-100">
              <MessageSquare size={24} />
            </div>
            <p className="text-slate-800 font-bold mb-1">No sessions yet</p>
            <p className="text-slate-500 text-xs mb-4">Start a conversation with your AI tutor</p>
            <button onClick={() => navigate('/chat')} className="btn-primary text-xs">
              Start Learning
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {recentSessions.map((session: any, i: number) => (
              <motion.button
                key={session.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.07 }}
                onClick={() => navigate(`/chat/${session.id}`)}
                className="glass-card p-4 text-left group border border-slate-200/80 hover:border-indigo-300 transition-all cursor-pointer"
              >
                <div className="flex items-start gap-3">
                  <div
                    className={`w-10 h-10 rounded-xl bg-gradient-to-br ${
                      SUBJECT_COLORS[i % SUBJECT_COLORS.length]
                    } flex items-center justify-center text-lg flex-shrink-0 shadow-md`}
                  >
                    {SUBJECT_ICONS[i % SUBJECT_ICONS.length]}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-bold text-slate-900 text-sm truncate group-hover:text-indigo-600 transition-colors">
                      {session.session_title}
                    </p>
                    <div className="flex items-center gap-1.5 mt-1">
                      <Clock size={11} className="text-slate-400" />
                      <span className="text-[11px] text-slate-400 font-medium">
                        {new Date(session.started_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                  <ArrowRight
                    size={16}
                    className="text-slate-400 group-hover:text-indigo-600 group-hover:translate-x-1 transition-all mt-1"
                  />
                </div>
              </motion.button>
            ))}
          </div>
        )}
      </div>

      {/* ─── AI STUDY TOOLS & ROADMAP ─── */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-slate-900">AI Study Roadmap & Tools</h2>
          <button
            onClick={() => navigate('/study-plan')}
            className="text-xs text-indigo-600 hover:text-indigo-700 font-bold transition-colors"
          >
            View Study Plans →
          </button>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <motion.button
            whileHover={{ y: -3, scale: 1.02 }}
            onClick={() => navigate('/study-plan')}
            className="glass-card p-5 text-left border border-slate-200/80 hover:border-indigo-300 transition-all cursor-pointer flex items-center gap-3.5"
          >
            <div className="w-11 h-11 rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold text-lg border border-indigo-100 flex-shrink-0">
              📅
            </div>
            <div>
              <p className="text-xs font-bold text-slate-900">AI Study Roadmap</p>
              <p className="text-[11px] text-slate-500 mt-0.5">Custom day-by-day exam schedule</p>
            </div>
          </motion.button>

          <motion.button
            whileHover={{ y: -3, scale: 1.02 }}
            onClick={() => navigate('/chat')}
            className="glass-card p-5 text-left border border-slate-200/80 hover:border-indigo-300 transition-all cursor-pointer flex items-center gap-3.5"
          >
            <div className="w-11 h-11 rounded-2xl bg-violet-50 text-violet-600 flex items-center justify-center font-bold text-lg border border-violet-100 flex-shrink-0">
              🧠
            </div>
            <div>
              <p className="text-xs font-bold text-slate-900">GraphRAG AI Tutor</p>
              <p className="text-[11px] text-slate-500 mt-0.5">Upload PDFs & ask graph-aware questions</p>
            </div>
          </motion.button>

          <motion.button
            whileHover={{ y: -3, scale: 1.02 }}
            onClick={() => navigate('/progress')}
            className="glass-card p-5 text-left border border-slate-200/80 hover:border-indigo-300 transition-all cursor-pointer flex items-center gap-3.5"
          >
            <div className="w-11 h-11 rounded-2xl bg-emerald-50 text-emerald-600 flex items-center justify-center font-bold text-lg border border-emerald-100 flex-shrink-0">
              📈
            </div>
            <div>
              <p className="text-xs font-bold text-slate-900">Analytics & Mastery</p>
              <p className="text-[11px] text-slate-500 mt-0.5">Quiz scores, streaks & concept progress</p>
            </div>
          </motion.button>
        </div>
      </div>

      {/* ─── STAT DETAILS MODAL ─── */}
      <AnimatePresence>
        {activeModal && (
          <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md bg-white rounded-3xl p-6 shadow-2xl border border-slate-100 relative"
            >
              <button
                onClick={() => setActiveModal(null)}
                className="absolute top-5 right-5 text-slate-400 hover:text-slate-600 p-1 rounded-full hover:bg-slate-50"
              >
                <X size={18} />
              </button>

              {activeModal === 'sessions' && (
                <div className="space-y-4 text-center py-2">
                  <div className="w-12 h-12 rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center mx-auto">
                    <MessageSquare size={24} />
                  </div>
                  <h3 className="text-xl font-bold text-slate-900">Chat Sessions ({progress?.total_sessions ?? 0})</h3>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    You have participated in {progress?.total_sessions ?? 0} learning sessions powered by Ollama LLM and GraphRAG.
                  </p>
                  <button
                    onClick={() => { setActiveModal(null); navigate('/chat') }}
                    className="btn-primary w-full py-2.5 text-xs"
                  >
                    Open AI Tutor Chat
                  </button>
                </div>
              )}

              {activeModal === 'score' && (
                <div className="space-y-4 text-center py-2">
                  <div className="w-12 h-12 rounded-2xl bg-violet-50 text-violet-600 flex items-center justify-center mx-auto">
                    <Star size={24} />
                  </div>
                  <h3 className="text-xl font-bold text-slate-900">Average Score: {progress?.avg_score ?? 0}%</h3>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    Calculated from all stored quiz attempts. Take more quizzes to improve your mastery score!
                  </p>
                  <button
                    onClick={() => { setActiveModal(null); navigate('/progress') }}
                    className="btn-primary w-full py-2.5 text-xs"
                  >
                    View Analytics Details
                  </button>
                </div>
              )}

              {activeModal === 'topics' && (
                <div className="space-y-4 text-center py-2">
                  <div className="w-12 h-12 rounded-2xl bg-cyan-50 text-cyan-600 flex items-center justify-center mx-auto">
                    <BookOpen size={24} />
                  </div>
                  <h3 className="text-xl font-bold text-slate-900">Topics Explored ({progress?.topics_studied ?? 0})</h3>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    Unique topic areas indexed from your documents and study chats.
                  </p>
                  <button
                    onClick={() => { setActiveModal(null); navigate('/subjects') }}
                    className="btn-primary w-full py-2.5 text-xs"
                  >
                    Browse All Subjects
                  </button>
                </div>
              )}

              {activeModal === 'streak' && (
                <div className="space-y-4 text-center py-2">
                  <div className="w-12 h-12 rounded-2xl bg-orange-50 text-orange-600 flex items-center justify-center mx-auto">
                    <Flame size={24} className="animate-bounce" />
                  </div>
                  <h3 className="text-xl font-bold text-slate-900">{progress?.streak_days ?? 0} Day Learning Streak 🔥</h3>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    Study every day to maintain your streak and earn learning master badges!
                  </p>
                  <button
                    onClick={() => { setActiveModal(null); navigate('/progress') }}
                    className="btn-primary w-full py-2.5 text-xs"
                  >
                    View Activity Calendar
                  </button>
                </div>
              )}
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  )
}
