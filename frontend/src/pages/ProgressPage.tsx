import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  BarChart, Bar, Cell
} from 'recharts'
import { TrendingUp, Flame, BookOpen, Trophy, Sparkles, Target, HelpCircle, Download, Award, Layers, Calendar, AlertTriangle, CheckCircle2, MessageSquare, ArrowRight, ShieldAlert } from 'lucide-react'
import { progressApi } from '../services/api'


const INTENSITY_COLORS = [
  'bg-[#E5E5E5]',
  'bg-[#D7FFB8]',
  'bg-[#58CC02]/60',
  'bg-[#58CC02]',
  'bg-[#46A302]',
]

const CUSTOM_TOOLTIP = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div className="glass-strong rounded-[1.25rem] px-3 py-2 text-xs border border-[#E2E8F0] elevation-2">
      <p className="text-[#777777] mb-1 font-extrabold">{label}</p>
      {payload.map((p: any) => (
        <p key={p.name} style={{ color: p.color }} className="font-bold">
          {p.name}: <span className="font-black">{p.value}</span>
        </p>
      ))}
    </div>
  )
}

function StatBadge({
  icon: Icon,
  label,
  value,
  bgStyle,
}: {
  icon: any
  label: string
  value: string | number
  bgStyle: string
}) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="glass-card p-5 flex items-center gap-4 border border-[#E2E8F0] elevation-1"
    >
      <div
        className={`w-11 h-11 rounded-[1.5rem] ${bgStyle} flex items-center justify-center elevation-1 flex-shrink-0 border`}
      >
        <Icon size={20} />
      </div>
      <div>
        <p className="text-2xl font-black text-[#3C3C3C]">{value}</p>
        <p className="text-xs font-bold text-[#777777]">{label}</p>
      </div>
    </motion.div>
  )
}

export default function ProgressPage() {
  const navigate = useNavigate()

  const { data: summary } = useQuery({
    queryKey: ['progress-summary'],
    queryFn: () => progressApi.summary().then((r) => r.data),
    staleTime: 60_000,
  })

  const { data: analysis } = useQuery({
    queryKey: ['progress-analysis'],
    queryFn: () => progressApi.analysis().then((r) => r.data),
    staleTime: 30_000,
  })

  const { data: weeklyData = [] } = useQuery({
    queryKey: ['progress-weekly'],
    queryFn: () => progressApi.weekly().then((r) => r.data),
    staleTime: 60_000,
  })

  const { data: recentQuizzes = [] } = useQuery({
    queryKey: ['progress-recent-quizzes'],
    queryFn: () => progressApi.recentQuizzes().then((r) => r.data),
    staleTime: 60_000,
  })

  const { data: calendarDays = [] } = useQuery({
    queryKey: ['progress-calendar'],
    queryFn: () => progressApi.calendar().then((r) => r.data),
    staleTime: 60_000,
  })

  const { data: topicProgress = [] } = useQuery({
    queryKey: ['progress-topics'],
    queryFn: () => progressApi.topics().then((r) => r.data),
    staleTime: 60_000,
  })

  // Subject radar data from actual topicProgress or defaults
  const radarData =
    topicProgress.length > 0
      ? topicProgress.map((t: any) => ({
          subject: t.subject || t.topic,
          score: t.score || t.mastery || 0,
        }))
      : [
          { subject: 'General Concepts', score: summary?.avg_score || 0 },
        ]

  const xpForNext = summary?.xp_for_next ?? 250
  const xpInLevel = summary?.xp_in_level ?? 0
  const levelPct = Math.min(100, Math.round((xpInLevel / xpForNext) * 100))

  const handleExportReport = () => {
    const reportText = `================================================
  DEEPTUTOR AI - LEARNING PROGRESS REPORT
================================================
Generated: ${new Date().toLocaleDateString()} ${new Date().toLocaleTimeString()}

[STUDY XP & LEVEL]
- Level: Level ${summary?.level ?? 1} (${summary?.level_title ?? 'Novice Scholar'})
- Total XP: ${summary?.total_xp ?? 0} XP
- XP in Current Level: ${xpInLevel} / ${xpForNext} XP

[PERFORMANCE SUMMARY]
- Day Streak: ${summary?.streak_days ?? 0} Days
- Total Sessions: ${summary?.total_sessions ?? 0}
- Quizzes Taken: ${summary?.quizzes_taken ?? 0}
- Average Quiz Score: ${summary?.avg_score ?? 0}%
- Topics Studied: ${summary?.topics_studied ?? 0}
- Flashcards Mastered: ${summary?.flashcards_mastered ?? 0}
- Study Plan Days Completed: ${summary?.completed_plan_days ?? 0}

[RECENT QUIZ ATTEMPTS]
${recentQuizzes.map((q: any) => `- ${q.full_name || q.name}: ${q.score}% (${q.date})`).join('\n') || 'None'}

================================================`
    const blob = new Blob([reportText], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `Indie-Tutor_Learning_Report_${new Date().toISOString().split('T')[0]}.txt`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="p-4 sm:p-6 max-w-7xl mx-auto space-y-6 sm:space-y-8 bg-[#F7F7F7]">
      {/* Header with Export Action */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Sparkles size={16} className="text-[#1CB0F6]" />
            <span className="text-xs font-black text-[#1CB0F6] uppercase tracking-widest bg-[#DDF4FF] px-2.5 py-0.5 rounded-full border border-[#1CB0F6]/20">
              Learning Analytics & Mastery
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-black text-[#3C3C3C] mb-1">Your Progress</h1>
          <p className="text-[#777777] text-xs sm:text-sm font-medium">Track real-time learning stats, XP levels, and quiz performance</p>
        </div>

        <button
          onClick={handleExportReport}
          className="btn-primary py-2.5 px-4 text-xs font-extrabold flex items-center gap-2 self-start sm:self-auto elevation-1 cursor-pointer"
        >
          <Download size={15} /> Export Report
        </button>
      </motion.div>

      {/* Level & XP Progression Banner */}
      <motion.div
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        className="glass-card p-6 border border-[#E2E8F0] bg-gradient-to-r from-[#3C3C3C] via-[#353531] to-[#3C3C3C] text-white rounded-[2rem] elevation-2 flex flex-col md:flex-row items-center justify-between gap-6"
      >
        <div className="flex items-center gap-4 text-left w-full md:w-auto">
          <div className="w-16 h-16 rounded-[1.5rem] bg-[#DDF4FF] flex items-center justify-center flex-shrink-0 elevation-2 border border-[#1CB0F6]/30 p-2">
            <Award size={32} className="text-[#1CB0F6]" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-extrabold uppercase tracking-wider bg-white/20 px-2.5 py-0.5 rounded-full text-white">
                Level {summary?.level ?? 1}
              </span>
              <span className="text-xs font-black text-[#1CB0F6]">
                {summary?.level_title ?? 'Novice Scholar'}
              </span>
            </div>
            <h2 className="text-2xl font-black mt-1">{summary?.total_xp ?? 0} Total XP</h2>
            <p className="text-xs text-[#E2E8F0] mt-0.5 font-medium">Earn XP by completing quizzes, sessions, flashcards & study plans</p>
          </div>
        </div>

        <div className="w-full md:w-80 space-y-2">
          <div className="flex justify-between text-xs font-extrabold text-[#E2E8F0]">
            <span>Progress to Level {(summary?.level ?? 1) + 1}</span>
            <span>{xpInLevel} / {xpForNext} XP</span>
          </div>
          <div className="w-full bg-[#353531] rounded-full h-3 p-0.5 border border-[#E2E8F0]/30 overflow-hidden">
            <motion.div
              className="bg-[#1CB0F6] h-full rounded-full"
              initial={{ width: 0 }}
              animate={{ width: `${levelPct}%` }}
              transition={{ duration: 0.8, ease: 'easeOut' }}
            />
          </div>
        </div>
      </motion.div>

      {/* Automated AI Performance & Weak Area Analysis Banner */}
      {analysis?.alert && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className={`p-5 rounded-[2rem] border elevation-2 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 ${
            analysis.alert.level === 'warning'
              ? 'bg-[#FFF0B3] border-[#FFC800]/40 text-[#5C3E00]'
              : analysis.alert.level === 'info'
              ? 'bg-[#EBF3FB] border-[#5A9BD5]/40 text-[#1B4B75]'
              : 'bg-[#D7FFB8] border-[#58CC02]/40 text-[#1C472E]'
          }`}
        >
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-[1.25rem] bg-white/60 elevation-1 mt-0.5">
              {analysis.alert.level === 'warning' ? (
                <ShieldAlert size={20} className="text-[#FFC800]" />
              ) : (
                <CheckCircle2 size={20} className="text-[#58CC02]" />
              )}
            </div>
            <div>
              <h3 className="font-extrabold text-sm mb-0.5">{analysis.alert.title}</h3>
              <p className="text-xs font-medium opacity-90">{analysis.alert.message}</p>
            </div>
          </div>

          {analysis.has_weakness && analysis.primary_weakness && (
            <button
              onClick={() => navigate(`/quiz/${analysis.primary_weakness.topic_id}`)}
              className="btn-primary py-2 px-3.5 text-xs font-bold flex items-center gap-1.5 whitespace-nowrap cursor-pointer elevation-1 self-end md:self-auto"
            >
              Practice {analysis.primary_weakness.subject} <ArrowRight size={14} />
            </button>
          )}
        </motion.div>
      )}

      {/* Real-time Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <StatBadge
          icon={Flame}
          label="Day Streak"
          value={`${summary?.streak_days ?? 0} days`}
          bgStyle="bg-[#FFF0B3] text-[#FFC800] border-[#FFC800]/30"
        />
        <StatBadge
          icon={Trophy}
          label="Quizzes Taken"
          value={summary?.quizzes_taken ?? 0}
          bgStyle="bg-[#DDF4FF] text-[#1CB0F6] border-[#1CB0F6]/30"
        />
        <StatBadge
          icon={TrendingUp}
          label="Avg Score"
          value={`${summary?.avg_score ?? 0}%`}
          bgStyle="bg-[#D7FFB8] text-[#58CC02] border-[#58CC02]/30"
        />
        <StatBadge
          icon={Layers}
          label="Flashcards Mastered"
          value={summary?.flashcards_mastered ?? 0}
          bgStyle="bg-[#F0ECF7] text-[#A99BCB] border-[#A99BCB]/30"
        />
      </div>

      {/* Charts row 1 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Weekly Activity - area chart */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass-card p-6 lg:col-span-2 border border-[#E2E8F0] elevation-1"
        >
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="font-black text-[#3C3C3C] text-base mb-0.5">Weekly Activity</h2>
              <p className="text-xs text-[#777777] font-medium">Real sessions & quiz scores this week</p>
            </div>
            <div className="flex items-center gap-3 text-xs text-[#777777] font-bold">
              <span className="flex items-center gap-1">
                <span className="w-3 h-1 bg-[#1CB0F6] inline-block rounded" /> Sessions
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-1 bg-[#58CC02] inline-block rounded" /> Score%
              </span>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={210}>
            <AreaChart data={weeklyData}>
              <defs>
                <linearGradient id="gradSessions" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#1CB0F6" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#1CB0F6" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradScore" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#58CC02" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#58CC02" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
              <XAxis dataKey="day" tick={{ fontSize: 11, fill: '#777777' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#777777' }} axisLine={false} tickLine={false} />
              <Tooltip content={<CUSTOM_TOOLTIP />} />
              <Area
                type="monotone"
                dataKey="sessions"
                name="Sessions"
                stroke="#1CB0F6"
                fill="url(#gradSessions)"
                strokeWidth={2.5}
                dot={{ fill: '#1CB0F6', r: 4 }}
              />
              <Area
                type="monotone"
                dataKey="score"
                name="Score %"
                stroke="#58CC02"
                fill="url(#gradScore)"
                strokeWidth={2.5}
                dot={{ fill: '#58CC02', r: 4 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </motion.div>

        {/* Subject Radar */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="glass-card p-6 border border-[#E2E8F0] elevation-1 flex flex-col justify-between"
        >
          <div className="mb-4">
            <h2 className="font-black text-[#3C3C3C] text-base mb-0.5">Topic Mastery</h2>
            <p className="text-xs text-[#777777] font-medium">Performance across indexed topics</p>
          </div>
          <ResponsiveContainer width="100%" height={210}>
            <RadarChart data={radarData}>
              <PolarGrid stroke="#E2E8F0" />
              <PolarAngleAxis dataKey="subject" tick={{ fontSize: 10, fill: '#3C3C3C', fontWeight: 700 }} />
              <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} axisLine={false} />
              <Radar
                name="Score"
                dataKey="score"
                stroke="#1CB0F6"
                fill="#1CB0F6"
                fillOpacity={0.25}
                strokeWidth={2.5}
                dot={{ fill: '#1CB0F6', r: 4 }}
              />
            </RadarChart>
          </ResponsiveContainer>
        </motion.div>
      </div>

      {/* Charts row 2 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Quiz Scores Bar Chart */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="glass-card p-6 border border-[#E2E8F0] elevation-1"
        >
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="font-black text-[#3C3C3C] text-base mb-0.5">Recent Quiz Attempts</h2>
              <p className="text-xs text-[#777777] font-medium">Your latest quiz scores from database</p>
            </div>
            {recentQuizzes.length > 0 && (
              <span className="text-xs font-black text-[#58CC02] bg-[#D7FFB8] px-2.5 py-0.5 rounded-full border border-[#58CC02]/20">
                {recentQuizzes.length} Attempts Recorded
              </span>
            )}
          </div>

          {recentQuizzes.length === 0 ? (
            <div className="text-center py-10 px-4 border border-dashed border-[#E2E8F0] rounded-[1.5rem] bg-[#FFFFFF]/50 flex flex-col items-center justify-center">
              <div className="w-12 h-12 rounded-[1.5rem] bg-[#DDF4FF] border border-[#1CB0F6]/30 flex items-center justify-center mb-3 text-[#1CB0F6] elevation-1">
                <Trophy size={22} />
              </div>
              <p className="text-sm font-black text-[#3C3C3C]">No quiz attempts recorded yet</p>
              <p className="text-xs text-[#777777] mt-1 mb-4 max-w-xs font-medium">
                Test your knowledge by taking an AI-generated quiz from your study materials!
              </p>
              <button
                onClick={() => navigate('/topics')}
                className="btn-primary py-2 px-4 text-xs font-extrabold flex items-center gap-1.5 cursor-pointer elevation-1"
              >
                <Sparkles size={14} /> Start AI Quiz
              </button>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={190}>
              <BarChart data={recentQuizzes} barSize={32}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#777777', fontWeight: 600 }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#777777' }} axisLine={false} tickLine={false} />
                <Tooltip content={<CUSTOM_TOOLTIP />} />
                <Bar dataKey="score" name="Score %" radius={[8, 8, 0, 0]}>
                  {recentQuizzes.map((entry: any, i: number) => (
                    <Cell
                      key={i}
                      fill={entry.score >= 80 ? '#58CC02' : entry.score >= 50 ? '#FFC800' : '#FF4B4B'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </motion.div>

        {/* Activity Streak Calendar */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
          className="glass-card p-6 border border-[#E2E8F0] elevation-1 flex flex-col justify-between"
        >
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="font-black text-[#3C3C3C] text-base mb-0.5">Activity Calendar</h2>
              <p className="text-xs text-[#777777] font-medium">Recorded learning activity (Last 5 weeks)</p>
            </div>
            <div className="flex items-center gap-1.5 bg-[#DDF4FF] border border-[#1CB0F6]/30 px-3 py-1 rounded-full">
              <Flame size={15} className="text-[#1CB0F6]" />
              <span className="text-xs font-black text-[#1CB0F6]">{summary?.streak_days ?? 0} day streak</span>
            </div>
          </div>

          {/* Calendar grid */}
          <div className="flex gap-1.5 flex-wrap justify-center py-2">
            {['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((d, i) => (
              <div key={i} className="w-7 text-center text-[10px] text-[#AFAFAF] font-black mb-1">
                {d}
              </div>
            ))}
            {calendarDays.map((day: any, i: number) => (
              <div
                key={i}
                className={`w-7 h-7 rounded-lg transition-all ${
                  day.active ? INTENSITY_COLORS[day.intensity || 1] : INTENSITY_COLORS[0]
                }`}
                title={day.active ? `${day.date}: ${day.intensity} activities recorded` : `${day.date}: No activity`}
              />
            ))}
          </div>

          <div className="flex items-center justify-between mt-3 text-[11px] text-[#AFAFAF] font-bold">
            <span>Less</span>
            <div className="flex gap-1">
              {INTENSITY_COLORS.map((c, i) => (
                <div key={i} className={`w-3.5 h-3.5 rounded-sm ${c}`} />
              ))}
            </div>
            <span>More</span>
          </div>
        </motion.div>
      </div>

      {/* Topic Progress List */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="glass-card p-6 border border-[#E2E8F0] elevation-1"
      >
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <Target size={18} className="text-[#1CB0F6]" />
            <h2 className="font-black text-[#3C3C3C] text-base">Topic Progress Breakdown</h2>
          </div>
          {topicProgress.length > 0 && (
            <span className="text-xs font-bold text-[#777777]">
              {topicProgress.length} Indexed Topics
            </span>
          )}
        </div>

        {topicProgress.length === 0 ? (
          <div className="p-8 text-center text-xs font-bold text-[#AFAFAF] border border-dashed border-[#E2E8F0] rounded-[1.5rem]">
            No topic data recorded yet. Upload a PDF document or start an AI chat session to track topic mastery!
          </div>
        ) : (
          <div className="space-y-4">
            {topicProgress.map((item: any, i: number) => {
              const mastery = item.mastery ?? item.score ?? 0
              const mastery_label =
                mastery >= 80 ? 'Expert' : mastery >= 60 ? 'Proficient' : mastery >= 40 ? 'Learning' : 'Beginner'
              const badge_class =
                mastery >= 80 ? 'badge-easy' : mastery >= 60 ? 'badge-medium' : 'badge-hard'

              return (
                <div key={i} className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-[1.5rem] bg-[#E5E5E5]/50 border border-[#E2E8F0]/60 hover:border-[#1CB0F6]/30 transition-all">
                  <div className="w-full sm:w-48 flex-shrink-0">
                    <p className="text-xs font-black text-[#3C3C3C] truncate">{item.subject || item.topic}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className={`badge ${badge_class} inline-block text-[9px]`}>
                        {mastery_label}
                      </span>
                      <span className="text-[10px] text-[#777777] font-bold">
                        {item.quizzes_taken} quizzes • {item.sessions_count} sessions
                      </span>
                    </div>
                  </div>

                  <div className="flex-1 w-full">
                    <div className="progress-bar">
                      <motion.div
                        className="progress-fill"
                        initial={{ width: 0 }}
                        animate={{ width: `${mastery}%` }}
                        transition={{ delay: i * 0.08, duration: 0.7, ease: 'easeOut' }}
                      />
                    </div>
                  </div>

                  <div className="flex items-center justify-between sm:justify-end gap-3 w-full sm:w-auto">
                    <span className="text-xs font-black text-[#3C3C3C]">{mastery}%</span>
                    <button
                      onClick={() => navigate(`/quiz/${item.topic_id}`)}
                      className="py-1 px-3 rounded-lg text-[11px] font-extrabold bg-white border border-[#E2E8F0] text-[#3C3C3C] hover:bg-[#DDF4FF] hover:border-[#1CB0F6]/40 hover:text-[#1CB0F6] transition-all cursor-pointer elevation-1"
                    >
                      Quiz
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </motion.div>
    </div>
  )
}
