import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis
} from 'recharts'
import {
  Award, TrendingUp, BookOpen, Clock, Flame, Zap, Target,
  CheckCircle2, AlertTriangle, HelpCircle, FileText, ChevronRight,
  Download, Printer, Sparkles, User, ShieldCheck, Search, Filter,
  ArrowUpRight, ArrowRight, X, ExternalLink, Brain, Layers, RefreshCw, MessageSquare
} from 'lucide-react'
import { progressApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'

const CUSTOM_TOOLTIP = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-white/95 backdrop-blur-md rounded-xl p-3 text-xs border border-[#E7E1D8] shadow-md">
      <p className="text-[#6F6B63] mb-1 font-bold">{label}</p>
      {payload.map((p: any) => (
        <p key={p.name} style={{ color: p.color }} className="font-semibold">
          {p.name}: <span className="font-extrabold">{p.value}%</span>
        </p>
      ))}
    </div>
  )
}

export default function StudentRecordsPage() {
  const { user } = useAuthStore()
  const navigate = useNavigate()

  const [activeTab, setActiveTab] = useState<'all' | 'quizzes' | 'sessions' | 'notes'>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedAttempt, setSelectedAttempt] = useState<any | null>(null)

  const { data: record, isLoading, refetch } = useQuery({
    queryKey: ['student-record'],
    queryFn: () => progressApi.studentRecord().then((r) => r.data),
    staleTime: 30_000,
  })

  const student = record?.student || {}
  const scholarRank = record?.scholar_rank || {}
  const metrics = record?.metrics || {}
  const diagnostic = record?.diagnostic || {}
  const subjectCompetencies = record?.subject_competencies || []
  const quizAttempts = record?.quiz_attempts || []
  const recentSessions = record?.recent_sessions || []
  const savedNotes = record?.saved_notes || []

  // Score timeline chart data
  const scoreTrendData = useMemo(() => {
    if (!quizAttempts || quizAttempts.length === 0) {
      return [
        { date: 'Initial', title: 'Diagnostic Baseline', score: 70 },
        { date: 'Week 1', title: 'Practice Benchmark', score: 75 },
        { date: 'Current', title: 'Current Standing', score: metrics?.avg_quiz_score || 80 },
      ]
    }
    return [...quizAttempts].reverse().map((a: any, idx: number) => ({
      date: a.attempted_at ? a.attempted_at.split('T')[0].slice(5) : `Quiz ${idx + 1}`,
      title: a.quiz_title || 'Quiz Attempt',
      score: a.percentage || 0,
    }))
  }, [quizAttempts, metrics?.avg_quiz_score])

  // Unified activities list
  const allActivities = useMemo(() => {
    const list: any[] = []

    // 1. Quizzes
    quizAttempts.forEach((q: any) => {
      list.push({
        id: `quiz_${q.id}`,
        rawId: q.id,
        category: 'quiz',
        title: q.quiz_title,
        topic: q.topic_id,
        date: q.attempted_at,
        scoreText: `${q.percentage}%`,
        subText: `${q.score}/${q.total_questions} correct`,
        status: q.percentage >= 70 ? 'Mastered' : 'Needs Review',
        isPassed: q.percentage >= 70,
        rawObj: q,
      })
    })

    // 2. Study Sessions
    recentSessions.forEach((s: any) => {
      list.push({
        id: `session_${s.id}`,
        rawId: s.id,
        category: 'session',
        title: s.title || 'AI Learning Session',
        topic: s.topic_id || 'general',
        date: s.started_at,
        scoreText: `${s.messages_count || 0} msgs`,
        subText: 'Interactive dialog',
        status: 'AI Tutor Session',
        isPassed: true,
        rawObj: s,
      })
    })

    // 3. Smart Notes
    savedNotes.forEach((n: any) => {
      list.push({
        id: `note_${n.id}`,
        rawId: n.id,
        category: 'note',
        title: n.title,
        topic: n.subject || 'General',
        date: n.created_at,
        scoreText: `${n.high_yield_topics?.length || 0} Concepts`,
        subText: `${n.pyq_doc_names?.length || 0} PYQ Papers`,
        status: 'PYQ Synthesized',
        isPassed: true,
        rawObj: n,
      })
    })

    // Sort chronologically (newest first)
    return list.sort((a, b) => {
      const dateA = a.date ? new Date(a.date).getTime() : 0
      const dateB = b.date ? new Date(b.date).getTime() : 0
      return dateB - dateA
    })
  }, [quizAttempts, recentSessions, savedNotes])

  // Filtered records for activity history table
  const filteredActivities = useMemo(() => {
    return allActivities.filter((item) => {
      if (activeTab === 'quizzes' && item.category !== 'quiz') return false
      if (activeTab === 'sessions' && item.category !== 'session') return false
      if (activeTab === 'notes' && item.category !== 'note') return false

      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase()
        const matchTitle = (item.title || '').toLowerCase().includes(query)
        const matchTopic = (item.topic || '').toLowerCase().includes(query)
        return matchTitle || matchTopic
      }
      return true
    })
  }, [allActivities, activeTab, searchQuery])

  const readinessScore = metrics?.exam_readiness_score ?? 75
  const readinessLabel = metrics?.readiness_label ?? 'Good Standing'
  const readinessStatus = metrics?.readiness_status ?? 'Solid Progress'

  const handlePrintReport = () => {
    window.print()
  }

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-8 bg-[#FAF8F3] text-[#20201D] font-sans antialiased">
      
      {/* ─── 1. TOP HEADER & REPORT CARD ACTION ─── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[#E7E1D8]/70 pb-6 print:hidden">
        <div>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-[#FFF0E4] border border-[#F28A45]/30 flex items-center justify-center text-[#F28A45] shadow-xs">
              <Award size={22} />
            </div>
            <div>
              <h1 className="text-2xl sm:text-3xl font-extrabold text-[#20201D] tracking-tight flex items-center gap-2">
                <span>Student Performance Record</span>
                <span className="flex items-center gap-1 text-[11px] font-bold text-[#4F8A68] bg-[#E3F0E5] px-2.5 py-0.5 rounded-full border border-[#4F8A68]/20">
                  <span className="w-2 h-2 rounded-full bg-[#4F8A68] animate-pulse" />
                  Live Monitored
                </span>
              </h1>
              <p className="text-xs sm:text-sm text-[#6F6B63] mt-0.5 font-medium">
                Real-time tracking of academic performance, attempt logs, subject competencies, and AI diagnostic appraisal.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={() => refetch()}
            className="p-2.5 rounded-xl border border-[#E7E1D8] text-[#6F6B63] hover:text-[#20201D] hover:bg-[#F4EFE7] transition-all"
            title="Refresh Records"
          >
            <RefreshCw size={17} className={isLoading ? 'animate-spin' : ''} />
          </button>
          <button
            onClick={handlePrintReport}
            className="btn-primary font-bold text-xs sm:text-sm py-2.5 px-4 rounded-xl flex items-center gap-2 shadow-xs transition-all active:scale-[0.98] cursor-pointer"
          >
            <Printer size={16} />
            <span>Print Academic Report Card</span>
          </button>
        </div>
      </div>

      {/* ─── 2. HERO PROFILE & EXAM READINESS OVERVIEW ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Student Profile Card */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="lg:col-span-2 bg-white rounded-3xl p-6 sm:p-7 border border-[#E7E1D8] shadow-xs relative overflow-hidden flex flex-col justify-between"
        >
          <div className="absolute top-0 right-0 w-80 h-80 bg-gradient-to-bl from-[#FFF0E4]/60 via-[#FAF8F3]/20 to-transparent rounded-bl-full pointer-events-none" />
          
          <div>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-[#E7E1D8]/60">
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-[#20201D] to-[#4F4A42] text-white flex items-center justify-center text-2xl font-black shadow-md border-2 border-white">
                  {student?.username?.[0]?.toUpperCase() || user?.username?.[0]?.toUpperCase() || 'S'}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-xl sm:text-2xl font-black text-[#20201D]">
                      {student?.username || user?.username || 'Student'}
                    </h2>
                    <span className="text-[11px] font-black uppercase tracking-wider bg-[#FFF0E4] text-[#F28A45] px-2.5 py-0.5 rounded-full border border-[#F28A45]/30">
                      {scholarRank?.level_title || 'Scholar'}
                    </span>
                  </div>
                  <p className="text-xs text-[#969188] font-medium mt-0.5">
                    {student?.email || user?.email || 'student@deeptutor.ai'} • Enrolled since {student?.member_since ? new Date(student.member_since).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : '2026'}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 sm:self-center">
                <div className="bg-[#FAF8F3] border border-[#E7E1D8] px-3 py-2 rounded-xl text-center min-w-[70px]">
                  <p className="text-[10px] uppercase font-bold text-[#969188]">Streak</p>
                  <p className="text-base font-black text-[#F28A45] flex items-center justify-center gap-1">
                    <Flame size={14} className="fill-[#F28A45]" />
                    {scholarRank?.streak_days || 1}d
                  </p>
                </div>
                <div className="bg-[#FAF8F3] border border-[#E7E1D8] px-3 py-2 rounded-xl text-center min-w-[70px]">
                  <p className="text-[10px] uppercase font-bold text-[#969188]">Level</p>
                  <p className="text-base font-black text-[#4F8A68]">
                    Lv. {scholarRank?.level || 1}
                  </p>
                </div>
                <div className="bg-[#FAF8F3] border border-[#E7E1D8] px-3 py-2 rounded-xl text-center min-w-[80px]">
                  <p className="text-[10px] uppercase font-bold text-[#969188]">Total XP</p>
                  <p className="text-base font-black text-[#20201D]">
                    {scholarRank?.total_xp?.toLocaleString() || 0}
                  </p>
                </div>
              </div>
            </div>

            {/* Level Progression Bar */}
            <div className="pt-5 space-y-2">
              <div className="flex justify-between items-center text-xs">
                <span className="font-bold text-[#6F6B63] flex items-center gap-1.5">
                  <Sparkles size={14} className="text-[#F28A45]" />
                  <span>XP Progress to Level {(scholarRank?.level || 1) + 1}</span>
                </span>
                <span className="font-black text-[#20201D]">
                  {scholarRank?.xp_in_level || 0} / {scholarRank?.xp_for_next || 250} XP
                </span>
              </div>
              <div className="w-full h-3 bg-[#F4EFE7] rounded-full overflow-hidden p-0.5 border border-[#E7E1D8]">
                <div
                  className="h-full bg-gradient-to-r from-[#F28A45] to-[#DF7635] rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(100, Math.round(((scholarRank?.xp_in_level || 0) / (scholarRank?.xp_for_next || 250)) * 100))}%` }}
                />
              </div>
            </div>
          </div>

          {/* Quick Stat Pill Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-6 mt-4 border-t border-[#E7E1D8]/60">
            <div className="bg-[#FAF8F3] p-3 rounded-2xl border border-[#E7E1D8]/80">
              <p className="text-[11px] font-bold text-[#6F6B63]">Quiz Accuracy</p>
              <p className="text-xl font-black text-[#20201D] mt-0.5">{metrics?.avg_quiz_score || 0}%</p>
              <span className="text-[10px] text-[#4F8A68] font-bold">Over {metrics?.total_quizzes_taken || 0} tests</span>
            </div>
            <div className="bg-[#FAF8F3] p-3 rounded-2xl border border-[#E7E1D8]/80">
              <p className="text-[11px] font-bold text-[#6F6B63]">Flashcards</p>
              <p className="text-xl font-black text-[#20201D] mt-0.5">{metrics?.flashcards_mastered || 0}</p>
              <span className="text-[10px] text-[#969188] font-bold">Concepts Mastered</span>
            </div>
            <div className="bg-[#FAF8F3] p-3 rounded-2xl border border-[#E7E1D8]/80">
              <p className="text-[11px] font-bold text-[#6F6B63]">Study Sessions</p>
              <p className="text-xl font-black text-[#20201D] mt-0.5">{metrics?.total_sessions || 0}</p>
              <span className="text-[10px] text-[#F28A45] font-bold">AI Tutor Dialogs</span>
            </div>
            <div className="bg-[#FAF8F3] p-3 rounded-2xl border border-[#E7E1D8]/80">
              <p className="text-[11px] font-bold text-[#6F6B63]">Smart Notes</p>
              <p className="text-xl font-black text-[#20201D] mt-0.5">{metrics?.notes_generated || 0}</p>
              <span className="text-[10px] text-[#A99BCB] font-bold">PYQ Synthesis</span>
            </div>
          </div>
        </motion.div>

        {/* Right: Exam Readiness Gauge */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-white rounded-3xl p-6 sm:p-7 border border-[#E7E1D8] shadow-xs flex flex-col justify-between"
        >
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-black text-[#969188] uppercase tracking-wider">Exam Readiness Index</span>
              <span className="p-1.5 rounded-xl bg-[#E3F0E5] text-[#4F8A68]">
                <ShieldCheck size={16} />
              </span>
            </div>

            <div className="flex flex-col items-center justify-center my-6">
              <div className="relative w-36 h-36 flex items-center justify-center">
                <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
                  <circle
                    cx="50"
                    cy="50"
                    r="40"
                    className="text-[#F4EFE7]"
                    strokeWidth="10"
                    stroke="currentColor"
                    fill="transparent"
                  />
                  <circle
                    cx="50"
                    cy="50"
                    r="40"
                    className="text-[#F28A45] transition-all duration-1000 ease-out"
                    strokeWidth="10"
                    strokeDasharray={251.2}
                    strokeDashoffset={251.2 - (251.2 * readinessScore) / 100}
                    strokeLinecap="round"
                    stroke="currentColor"
                    fill="transparent"
                  />
                </svg>
                <div className="absolute flex flex-col items-center">
                  <span className="text-3xl font-black text-[#20201D] tracking-tight">{readinessScore}%</span>
                  <span className="text-[10px] font-bold text-[#6F6B63] uppercase tracking-wider">{readinessStatus}</span>
                </div>
              </div>
              <p className="text-sm font-extrabold text-[#20201D] mt-2 text-center">{readinessLabel}</p>
            </div>
          </div>

          <div className="space-y-2 bg-[#FAF8F3] p-3.5 rounded-2xl border border-[#E7E1D8] text-xs">
            <div className="flex justify-between text-[#6F6B63]">
              <span>Quiz Accuracy Factor</span>
              <span className="font-black text-[#20201D]">45% Weight</span>
            </div>
            <div className="flex justify-between text-[#6F6B63]">
              <span>Study Streak & Consistency</span>
              <span className="font-black text-[#20201D]">20% Weight</span>
            </div>
            <div className="flex justify-between text-[#6F6B63]">
              <span>Syllabus Coverage</span>
              <span className="font-black text-[#20201D]">20% Weight</span>
            </div>
            <div className="flex justify-between text-[#6F6B63]">
              <span>Flashcard Recall Rate</span>
              <span className="font-black text-[#20201D]">15% Weight</span>
            </div>
          </div>
        </motion.div>
      </div>

      {/* ─── 3. PERFORMANCE TRAJECTORY & COMPETENCIES ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Score Evolution Trend Chart */}
        <div className="lg:col-span-2 bg-white rounded-3xl p-6 sm:p-7 border border-[#E7E1D8] shadow-xs">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-6">
            <div>
              <h3 className="text-base font-extrabold text-[#20201D] flex items-center gap-2">
                <TrendingUp size={18} className="text-[#F28A45]" />
                <span>Quiz Score Accuracy Trajectory</span>
              </h3>
              <p className="text-xs text-[#6F6B63] mt-0.5">Chronological progression across test attempts</p>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="inline-block w-3 h-3 rounded-full bg-[#F28A45]" />
              <span className="font-bold text-[#6F6B63]">Accuracy %</span>
            </div>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={scoreTrendData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="scoreGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#F28A45" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#F28A45" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#E7E1D8" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: '#969188', fontSize: 11, fontWeight: 600 }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 100]} tick={{ fill: '#969188', fontSize: 11, fontWeight: 600 }} axisLine={false} tickLine={false} />
                <Tooltip content={<CUSTOM_TOOLTIP />} />
                <Area type="monotone" dataKey="score" stroke="#F28A45" strokeWidth={3} fillOpacity={1} fill="url(#scoreGradient)" name="Accuracy" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Right: Subject Competencies Bar Chart */}
        <div className="bg-white rounded-3xl p-6 sm:p-7 border border-[#E7E1D8] shadow-xs flex flex-col justify-between">
          <div>
            <h3 className="text-base font-extrabold text-[#20201D] flex items-center gap-2 mb-1">
              <Layers size={18} className="text-[#4F8A68]" />
              <span>Subject Competency Breakdown</span>
            </h3>
            <p className="text-xs text-[#6F6B63] mb-5">Mastery across curriculum streams</p>

            <div className="space-y-4">
              {subjectCompetencies.map((sc: any) => {
                const isWeak = sc.score > 0 && sc.score < 70
                const isStrong = sc.score >= 75
                const colorClass = isWeak ? 'from-[#C85C52] to-[#DF7635]' : isStrong ? 'from-[#4F8A68] to-[#35654B]' : 'from-[#F28A45] to-[#D99A32]'

                return (
                  <div key={sc.subject} className="space-y-1.5">
                    <div className="flex justify-between items-center text-xs">
                      <span className="font-extrabold text-[#20201D]">{sc.subject}</span>
                      <span className="font-black text-[#20201D]">
                        {sc.score > 0 ? `${sc.score}%` : 'Not tested'}
                      </span>
                    </div>
                    <div className="w-full h-2.5 bg-[#F4EFE7] rounded-full overflow-hidden border border-[#E7E1D8]">
                      <div
                        className={`h-full bg-gradient-to-r ${colorClass} rounded-full`}
                        style={{ width: `${Math.max(4, sc.score)}%` }}
                      />
                    </div>
                    <div className="flex justify-between text-[10px] text-[#969188]">
                      <span>{sc.quizzes_taken} tests • {sc.sessions_count} sessions</span>
                      {isWeak && <span className="text-[#C85C52] font-bold">Needs review</span>}
                      {isStrong && <span className="text-[#4F8A68] font-bold">High mastery</span>}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="mt-6 pt-4 border-t border-[#E7E1D8]/60">
            <button
              onClick={() => navigate('/notes')}
              className="w-full py-2.5 px-3 rounded-xl bg-[#FFF0E4] text-[#F28A45] hover:bg-[#F28A45] hover:text-white font-extrabold text-xs transition-all flex items-center justify-center gap-1.5 cursor-pointer shadow-2xs"
            >
              <FileText size={14} />
              <span>Generate Subject Smart Notes</span>
            </button>
          </div>
        </div>
      </div>

      {/* ─── 4. AI DIAGNOSTIC APPRAISAL CARD ─── */}
      <div className="bg-gradient-to-br from-[#FFF9F2] via-white to-[#FAF8F3] rounded-3xl p-6 sm:p-7 border-2 border-[#F28A45]/30 shadow-xs relative overflow-hidden">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-6">
          <div className="space-y-3 flex-1">
            <div className="flex items-center gap-2">
              <span className="px-3 py-1 rounded-full bg-[#F28A45] text-white text-[11px] font-black uppercase tracking-wider flex items-center gap-1.5 shadow-2xs">
                <Brain size={13} />
                AI Tutor Diagnostic Appraisal
              </span>
              <span className="text-xs text-[#969188]">
                Updated {diagnostic?.last_evaluated ? new Date(diagnostic.last_evaluated).toLocaleDateString() : 'Today'}
              </span>
            </div>

            <p className="text-sm sm:text-base font-semibold text-[#20201D] leading-relaxed">
              {diagnostic?.summary || 'Performance is steady. Regular quiz practice and topic revision will reinforce conceptual retention.'}
            </p>

            <div className="bg-white/80 backdrop-blur-xs p-4 rounded-2xl border border-[#E7E1D8] space-y-1">
              <p className="text-[11px] font-black text-[#F28A45] uppercase tracking-wider">Recommended Next Action:</p>
              <p className="text-xs sm:text-sm font-bold text-[#20201D]">
                {diagnostic?.recommended_action || 'Complete a 5-question quiz on your recent chapter and review 5 flashcards.'}
              </p>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row md:flex-col gap-2 min-w-[200px]">
            <button
              onClick={() => navigate('/chat')}
              className="btn-primary font-bold text-xs py-3 px-4 rounded-xl flex items-center justify-center gap-2 shadow-xs cursor-pointer"
            >
              <Sparkles size={15} />
              <span>Ask AI Tutor to Clarify</span>
            </button>
            <button
              onClick={() => navigate('/study-plan')}
              className="bg-white hover:bg-[#F4EFE7] border border-[#E7E1D8] text-[#20201D] font-bold text-xs py-3 px-4 rounded-xl flex items-center justify-center gap-2 transition-all cursor-pointer"
            >
              <span>View 7-Day Study Plan</span>
              <ChevronRight size={15} />
            </button>
          </div>
        </div>
      </div>

      {/* ─── 5. DETAILED ATTEMPTS & ACTIVITY LOGS ─── */}
      <div className="bg-white rounded-3xl p-6 sm:p-7 border border-[#E7E1D8] shadow-xs space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h3 className="text-lg font-black text-[#20201D] flex items-center gap-2">
              <FileText size={20} className="text-[#F28A45]" />
              <span>Monitored Activity Logs & Attempt Audits</span>
            </h3>
            <p className="text-xs text-[#6F6B63]">Detailed history of quizzes, question answers, study sessions, and notes</p>
          </div>

          <div className="flex items-center gap-2">
            <div className="relative">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#969188]" />
              <input
                type="text"
                placeholder="Search logs..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-3 py-2 text-xs rounded-xl bg-[#FAF8F3] border border-[#E7E1D8] focus:outline-none focus:border-[#F28A45] w-48 sm:w-60 font-medium"
              />
            </div>
          </div>
        </div>

        {/* Tab Selector */}
        <div className="flex items-center gap-2 border-b border-[#E7E1D8] pb-3">
          <button
            onClick={() => setActiveTab('all')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              activeTab === 'all' ? 'bg-[#20201D] text-white' : 'text-[#6F6B63] hover:bg-[#F4EFE7]'
            }`}
          >
            All Activity ({quizAttempts.length + recentSessions.length + savedNotes.length})
          </button>
          <button
            onClick={() => setActiveTab('quizzes')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              activeTab === 'quizzes' ? 'bg-[#20201D] text-white' : 'text-[#6F6B63] hover:bg-[#F4EFE7]'
            }`}
          >
            Quiz Tests ({quizAttempts.length})
          </button>
          <button
            onClick={() => setActiveTab('sessions')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              activeTab === 'sessions' ? 'bg-[#20201D] text-white' : 'text-[#6F6B63] hover:bg-[#F4EFE7]'
            }`}
          >
            Study Sessions ({recentSessions.length})
          </button>
          <button
            onClick={() => setActiveTab('notes')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              activeTab === 'notes' ? 'bg-[#20201D] text-white' : 'text-[#6F6B63] hover:bg-[#F4EFE7]'
            }`}
          >
            Smart Notes ({savedNotes.length})
          </button>
        </div>

        {/* Activities & Attempt Table */}
        <div className="overflow-x-auto">
          {filteredActivities.length === 0 ? (
            <div className="text-center py-12 text-[#969188]">
              <p className="text-sm font-semibold">
                {activeTab === 'quizzes'
                  ? 'No quiz attempts recorded yet.'
                  : activeTab === 'sessions'
                  ? 'No study sessions recorded yet.'
                  : activeTab === 'notes'
                  ? 'No smart notes generated yet.'
                  : 'No activity records found matching your filter.'}
              </p>
              <button
                onClick={() => {
                  if (activeTab === 'notes') navigate('/notes')
                  else if (activeTab === 'sessions') navigate('/chat')
                  else navigate('/quiz/general')
                }}
                className="mt-3 text-xs text-[#F28A45] font-extrabold hover:underline cursor-pointer"
              >
                {activeTab === 'notes'
                  ? 'Generate high-yield notes with PYQs →'
                  : activeTab === 'sessions'
                  ? 'Start a new AI learning session →'
                  : 'Take a practice quiz now →'}
              </button>
            </div>
          ) : (
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-[#E7E1D8] text-[#969188] uppercase font-black tracking-wider text-[10px]">
                  <th className="py-3 px-3">Date</th>
                  <th className="py-3 px-3">Activity / Record Title</th>
                  <th className="py-3 px-3">Type / Topic</th>
                  <th className="py-3 px-3 text-center">Score / Volume</th>
                  <th className="py-3 px-3 text-center">Status</th>
                  <th className="py-3 px-3 text-right">Audit & Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E7E1D8]/60">
                {filteredActivities.map((act: any) => {
                  const isQuiz = act.category === 'quiz'
                  const isSession = act.category === 'session'
                  const isNote = act.category === 'note'

                  return (
                    <tr key={act.id} className="hover:bg-[#FAF8F3] transition-colors group">
                      <td className="py-3 px-3 text-[#6F6B63] font-medium whitespace-nowrap">
                        {act.date ? new Date(act.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'Recently'}
                      </td>
                      <td className="py-3 px-3 font-extrabold text-[#20201D]">
                        <div className="flex items-center gap-2">
                          <span className={`p-1 rounded-lg ${
                            isQuiz ? 'bg-[#FFF0E4] text-[#F28A45]' : isSession ? 'bg-[#E0F2FE] text-[#0284C7]' : 'bg-[#F0ECF7] text-[#A99BCB]'
                          }`}>
                            {isQuiz ? <Target size={13} /> : isSession ? <MessageSquare size={13} /> : <FileText size={13} />}
                          </span>
                          <span className="truncate max-w-xs">{act.title}</span>
                        </div>
                      </td>
                      <td className="py-3 px-3 text-[#6F6B63] font-semibold">
                        <span className="px-2 py-0.5 rounded-md bg-[#F4EFE7] text-[#20201D] text-[11px]">
                          {act.topic}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-center font-black text-sm text-[#20201D]">
                        {act.scoreText}
                        <span className="text-[10px] text-[#969188] font-normal block">
                          {act.subText}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-center">
                        {isQuiz ? (
                          <span
                            className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-black ${
                              act.isPassed
                                ? 'bg-[#E3F0E5] text-[#4F8A68] border border-[#4F8A68]/20'
                                : 'bg-[#FBE7E4] text-[#C85C52] border border-[#C85C52]/20'
                            }`}
                          >
                            {act.isPassed ? <CheckCircle2 size={11} /> : <AlertTriangle size={11} />}
                            {act.status}
                          </span>
                        ) : isSession ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-black bg-[#E0F2FE] text-[#0284C7] border border-[#0284C7]/20">
                            <Sparkles size={11} />
                            {act.status}
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-black bg-[#FFF0E4] text-[#F28A45] border border-[#F28A45]/30">
                            <Zap size={11} />
                            {act.status}
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-3 text-right">
                        {isQuiz ? (
                          <button
                            onClick={() => setSelectedAttempt(act.rawObj)}
                            className="px-3 py-1 rounded-xl bg-white hover:bg-[#FAF8F3] border border-[#E7E1D8] text-[#20201D] font-bold text-xs shadow-2xs hover:border-[#F28A45] hover:text-[#F28A45] transition-all cursor-pointer inline-flex items-center gap-1"
                          >
                            <span>Review Questions</span>
                            <ChevronRight size={13} />
                          </button>
                        ) : isSession ? (
                          <button
                            onClick={() => navigate('/chat/' + act.rawId)}
                            className="px-3 py-1 rounded-xl bg-white hover:bg-[#E0F2FE]/40 border border-[#E7E1D8] text-[#0284C7] font-bold text-xs shadow-2xs hover:border-[#0284C7] transition-all cursor-pointer inline-flex items-center gap-1"
                          >
                            <span>Open Session</span>
                            <ExternalLink size={12} />
                          </button>
                        ) : (
                          <button
                            onClick={() => navigate('/notes')}
                            className="px-3 py-1 rounded-xl bg-white hover:bg-[#FFF0E4]/50 border border-[#E7E1D8] text-[#F28A45] font-bold text-xs shadow-2xs hover:border-[#F28A45] transition-all cursor-pointer inline-flex items-center gap-1"
                          >
                            <span>View Note</span>
                            <ArrowRight size={12} />
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* ─── 6. QUESTION-BY-QUESTION REVIEW MODAL ─── */}
      <AnimatePresence>
        {selectedAttempt && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#20201D]/60 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="bg-white rounded-3xl max-w-2xl w-full max-h-[85vh] flex flex-col shadow-2xl border border-[#E7E1D8] overflow-hidden"
            >
              {/* Modal Header */}
              <div className="p-6 border-b border-[#E7E1D8] flex items-center justify-between bg-[#FAF8F3]">
                <div>
                  <span className="text-[11px] font-black text-[#F28A45] uppercase tracking-wider">Question-by-Question Audit</span>
                  <h3 className="text-lg font-black text-[#20201D]">{selectedAttempt.quiz_title}</h3>
                  <p className="text-xs text-[#6F6B63]">
                    Score: <span className="font-extrabold text-[#20201D]">{selectedAttempt.score}/{selectedAttempt.total_questions} ({selectedAttempt.percentage}%)</span>
                  </p>
                </div>
                <button
                  onClick={() => setSelectedAttempt(null)}
                  className="p-2 rounded-xl text-[#969188] hover:text-[#20201D] hover:bg-[#E7E1D8]/60 transition-colors cursor-pointer"
                >
                  <X size={18} />
                </button>
              </div>

              {/* Questions List */}
              <div className="p-6 overflow-y-auto space-y-5 flex-1 bg-[#FAF8F3]/50">
                {selectedAttempt.questions_review?.length === 0 ? (
                  <p className="text-center text-xs text-[#969188] py-8">
                    Detailed question snapshot not recorded for this historical attempt.
                  </p>
                ) : (
                  selectedAttempt.questions_review?.map((q: any, idx: number) => {
                    const isCorrect = q.is_correct
                    return (
                      <div
                        key={q.id || idx}
                        className={`p-4 rounded-2xl border ${
                          isCorrect ? 'bg-white border-[#4F8A68]/30' : 'bg-white border-[#C85C52]/30'
                        } shadow-xs space-y-3`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <p className="text-xs font-bold text-[#20201D] leading-relaxed">
                            <span className="font-black text-[#969188] mr-1.5">Q{idx + 1}.</span>
                            {q.question_text}
                          </p>
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-black uppercase flex-shrink-0 ${
                              isCorrect ? 'bg-[#E3F0E5] text-[#4F8A68]' : 'bg-[#FBE7E4] text-[#C85C52]'
                            }`}
                          >
                            {isCorrect ? 'Correct' : 'Incorrect'}
                          </span>
                        </div>

                        {/* Options */}
                        {q.options && q.options.length > 0 && (
                          <div className="space-y-1.5 pl-2">
                            {q.options.map((opt: string, optIdx: number) => {
                              const letter = String.fromCharCode(65 + optIdx)
                              const isUserPick = q.user_answer === letter
                              const isCorrectPick = q.correct_answer === letter

                              let optBg = 'bg-[#FAF8F3] text-[#6F6B63] border-transparent'
                              if (isCorrectPick) {
                                optBg = 'bg-[#E3F0E5] text-[#4F8A68] border-[#4F8A68]/40 font-bold'
                              } else if (isUserPick && !isCorrect) {
                                optBg = 'bg-[#FBE7E4] text-[#C85C52] border-[#C85C52]/40 font-bold'
                              }

                              return (
                                <div
                                  key={optIdx}
                                  className={`px-3 py-1.5 rounded-xl text-xs border ${optBg} flex items-center justify-between`}
                                >
                                  <span><strong className="mr-1">{letter}.</strong> {opt}</span>
                                  {isCorrectPick && <span className="text-[10px] uppercase font-black text-[#4F8A68]">Correct Answer</span>}
                                  {isUserPick && !isCorrect && <span className="text-[10px] uppercase font-black text-[#C85C52]">Your Choice</span>}
                                </div>
                              )
                            })}
                          </div>
                        )}

                        {/* Explanation */}
                        {q.explanation && (
                          <div className="p-3 bg-[#FAF8F3] rounded-xl text-xs text-[#6F6B63] border border-[#E7E1D8]/60">
                            <span className="font-bold text-[#20201D] block mb-0.5">Explanation:</span>
                            {q.explanation}
                          </div>
                        )}
                      </div>
                    )
                  })
                )}
              </div>

              {/* Modal Footer */}
              <div className="p-4 border-t border-[#E7E1D8] bg-white flex justify-end">
                <button
                  onClick={() => setSelectedAttempt(null)}
                  className="btn-primary font-bold text-xs py-2 px-5 rounded-xl cursor-pointer"
                >
                  Close Audit
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ─── 7. PRINTABLE ACADEMIC REPORT CARD TEMPLATE (Visible on Print) ─── */}
      <div className="hidden print:block bg-white p-8 text-[#20201D] font-sans">
        <div className="border-b-2 border-[#20201D] pb-4 mb-6 flex justify-between items-start">
          <div>
            <h1 className="text-3xl font-black tracking-tight">DeepTutor AI</h1>
            <p className="text-xs uppercase tracking-widest text-[#F28A45] font-bold">Official Student Academic Performance Record</p>
          </div>
          <div className="text-right text-xs">
            <p><strong>Date of Issue:</strong> {new Date().toLocaleDateString()}</p>
            <p><strong>Student ID:</strong> {student?.id || 'DT-2026'}</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 text-xs mb-6 border p-4 rounded-lg bg-[#FAF8F3]">
          <div>
            <p><strong>Student Name:</strong> {student?.username || 'Student'}</p>
            <p><strong>Email Address:</strong> {student?.email || 'N/A'}</p>
            <p><strong>Scholar Standing:</strong> {scholarRank?.level_title || 'Scholar'}</p>
          </div>
          <div>
            <p><strong>Exam Readiness Index:</strong> {readinessScore}% ({readinessLabel})</p>
            <p><strong>Overall Quiz Accuracy:</strong> {metrics?.avg_quiz_score || 0}%</p>
            <p><strong>Total Quizzes Evaluated:</strong> {metrics?.total_quizzes_taken || 0}</p>
          </div>
        </div>

        <h3 className="font-bold text-sm mb-2 uppercase tracking-wide">Curriculum Competency Breakdown</h3>
        <table className="w-full text-xs border-collapse border border-[#E7E1D8] mb-6">
          <thead>
            <tr className="bg-[#F4EFE7]">
              <th className="border p-2 text-left">Subject Stream</th>
              <th className="border p-2 text-center">Score %</th>
              <th className="border p-2 text-center">Tests Taken</th>
              <th className="border p-2 text-left">Mastery Grade</th>
            </tr>
          </thead>
          <tbody>
            {subjectCompetencies.map((sc: any) => (
              <tr key={sc.subject}>
                <td className="border p-2">{sc.subject}</td>
                <td className="border p-2 text-center font-bold">{sc.score}%</td>
                <td className="border p-2 text-center">{sc.quizzes_taken}</td>
                <td className="border p-2 font-bold">{sc.score >= 80 ? 'A (Excellent)' : sc.score >= 65 ? 'B (Proficient)' : 'C (Developing)'}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="border p-4 rounded-lg bg-[#FAF8F3] text-xs space-y-2 mb-8">
          <p className="font-bold uppercase text-[#F28A45]">AI Academic Counselor Appraisal</p>
          <p>{diagnostic?.summary || 'Consistent performance maintained.'}</p>
        </div>

        <div className="flex justify-between items-end pt-12 text-xs border-t border-[#E7E1D8]">
          <div>
            <p className="font-bold">DeepTutor Academic Registry</p>
            <p className="text-[#969188]">Digitally Verified Record</p>
          </div>
          <div className="text-right">
            <div className="w-36 border-b border-[#20201D] mb-1" />
            <p className="font-bold">Authorized AI Evaluator</p>
          </div>
        </div>
      </div>

    </div>
  )
}
