import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  BarChart, Bar, Cell
} from 'recharts'
import { TrendingUp, Flame, BookOpen, Trophy, Sparkles, Target, HelpCircle } from 'lucide-react'
import { progressApi } from '../services/api'

const INTENSITY_COLORS = [
  'bg-slate-100',
  'bg-indigo-200',
  'bg-indigo-400',
  'bg-indigo-600',
  'bg-indigo-700',
]

const CUSTOM_TOOLTIP = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div className="glass-strong rounded-xl px-3 py-2 text-xs border border-indigo-100 shadow-md">
      <p className="text-slate-500 mb-1 font-bold">{label}</p>
      {payload.map((p: any) => (
        <p key={p.name} style={{ color: p.color }} className="font-semibold">
          {p.name}: <span className="font-extrabold">{p.value}</span>
        </p>
      ))}
    </div>
  )
}

function StatBadge({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: any
  label: string
  value: string | number
  color: string
}) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="glass-card p-5 flex items-center gap-4 border border-slate-200/80 shadow-sm"
    >
      <div
        className={`w-11 h-11 rounded-2xl bg-gradient-to-br ${color} flex items-center justify-center shadow-md flex-shrink-0`}
      >
        <Icon size={20} className="text-white" />
      </div>
      <div>
        <p className="text-2xl font-black text-slate-900">{value}</p>
        <p className="text-xs font-bold text-slate-500">{label}</p>
      </div>
    </motion.div>
  )
}

export default function ProgressPage() {
  const { data: summary } = useQuery({
    queryKey: ['progress-summary'],
    queryFn: () => progressApi.summary().then((r) => r.data),
  })

  const { data: weeklyData = [] } = useQuery({
    queryKey: ['progress-weekly'],
    queryFn: () => progressApi.weekly().then((r) => r.data),
  })

  const { data: recentQuizzes = [] } = useQuery({
    queryKey: ['progress-recent-quizzes'],
    queryFn: () => progressApi.recentQuizzes().then((r) => r.data),
  })

  const { data: calendarDays = [] } = useQuery({
    queryKey: ['progress-calendar'],
    queryFn: () => progressApi.calendar().then((r) => r.data),
  })

  const { data: topicProgress = [] } = useQuery({
    queryKey: ['progress-topics'],
    queryFn: () => progressApi.topics().then((r) => r.data),
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

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-center gap-2 mb-1">
          <Sparkles size={16} className="text-indigo-600" />
          <span className="text-xs font-extrabold text-indigo-600 uppercase tracking-widest">
            Learning Analytics
          </span>
        </div>
        <h1 className="text-3xl font-black text-slate-900 mb-1">Your Progress</h1>
        <p className="text-slate-500 text-sm">Track your real-time learning journey and quiz performance</p>
      </motion.div>

      {/* Real-time Stats row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatBadge
          icon={Flame}
          label="Day Streak"
          value={`${summary?.streak_days ?? 0} days`}
          color="from-orange-500 to-red-600"
        />
        <StatBadge
          icon={Trophy}
          label="Quizzes Taken"
          value={summary?.quizzes_taken ?? 0}
          color="from-amber-500 to-orange-600"
        />
        <StatBadge
          icon={TrendingUp}
          label="Avg Score"
          value={`${summary?.avg_score ?? 0}%`}
          color="from-emerald-500 to-teal-600"
        />
        <StatBadge
          icon={BookOpen}
          label="Topics Studied"
          value={summary?.topics_studied ?? 0}
          color="from-indigo-500 to-violet-600"
        />
      </div>

      {/* Charts row 1 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Weekly Activity - area chart */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass-card p-6 lg:col-span-2 border border-slate-200/80 shadow-sm"
        >
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="font-bold text-slate-900 text-base mb-0.5">Weekly Activity</h2>
              <p className="text-xs text-slate-500">Real sessions & quiz scores this week</p>
            </div>
            <div className="flex items-center gap-3 text-xs text-slate-500 font-semibold">
              <span className="flex items-center gap-1">
                <span className="w-3 h-1 bg-indigo-600 inline-block rounded" /> Sessions
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-1 bg-violet-400 inline-block rounded" /> Score%
              </span>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={210}>
            <AreaChart data={weeklyData}>
              <defs>
                <linearGradient id="gradSessions" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradScore" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#a78bfa" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#a78bfa" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(99,102,241,0.08)" />
              <XAxis dataKey="day" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
              <Tooltip content={<CUSTOM_TOOLTIP />} />
              <Area
                type="monotone"
                dataKey="sessions"
                name="Sessions"
                stroke="#6366f1"
                fill="url(#gradSessions)"
                strokeWidth={2.5}
                dot={{ fill: '#6366f1', r: 4 }}
              />
              <Area
                type="monotone"
                dataKey="score"
                name="Score %"
                stroke="#a78bfa"
                fill="url(#gradScore)"
                strokeWidth={2.5}
                dot={{ fill: '#a78bfa', r: 4 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </motion.div>

        {/* Subject Radar */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="glass-card p-6 border border-slate-200/80 shadow-sm flex flex-col justify-between"
        >
          <div className="mb-4">
            <h2 className="font-bold text-slate-900 text-base mb-0.5">Topic Mastery</h2>
            <p className="text-xs text-slate-500">Performance across indexed topics</p>
          </div>
          <ResponsiveContainer width="100%" height={210}>
            <RadarChart data={radarData}>
              <PolarGrid stroke="rgba(99,102,241,0.15)" />
              <PolarAngleAxis dataKey="subject" tick={{ fontSize: 10, fill: '#475569', fontWeight: 600 }} />
              <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} axisLine={false} />
              <Radar
                name="Score"
                dataKey="score"
                stroke="#6366f1"
                fill="#6366f1"
                fillOpacity={0.25}
                strokeWidth={2.5}
                dot={{ fill: '#6366f1', r: 4 }}
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
          className="glass-card p-6 border border-slate-200/80 shadow-sm"
        >
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="font-bold text-slate-900 text-base mb-0.5">Recent Quiz Attempts</h2>
              <p className="text-xs text-slate-500">Your latest quiz scores from database</p>
            </div>
            {recentQuizzes.length > 0 && (
              <span className="text-xs font-bold text-indigo-600 bg-indigo-50 px-2.5 py-0.5 rounded-full">
                {recentQuizzes.length} Attempts Recorded
              </span>
            )}
          </div>

          {recentQuizzes.length === 0 ? (
            <div className="text-center py-12 border border-dashed border-slate-200 rounded-2xl">
              <HelpCircle size={28} className="text-slate-300 mx-auto mb-2" />
              <p className="text-xs font-bold text-slate-500">No quiz attempts recorded yet</p>
              <p className="text-[11px] text-slate-400 mt-0.5">Take a quiz in AI Tutor to see your scores here!</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={190}>
              <BarChart data={recentQuizzes} barSize={32}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(99,102,241,0.08)" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#64748b', fontWeight: 600 }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} />
                <Tooltip content={<CUSTOM_TOOLTIP />} />
                <Bar dataKey="score" name="Score %" radius={[8, 8, 0, 0]}>
                  {recentQuizzes.map((entry: any, i: number) => (
                    <Cell
                      key={i}
                      fill={entry.score >= 80 ? '#10b981' : entry.score >= 50 ? '#f59e0b' : '#ef4444'}
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
          className="glass-card p-6 border border-slate-200/80 shadow-sm flex flex-col justify-between"
        >
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="font-bold text-slate-900 text-base mb-0.5">Activity Calendar</h2>
              <p className="text-xs text-slate-500">Recorded learning activity (Last 5 weeks)</p>
            </div>
            <div className="flex items-center gap-1.5 bg-orange-50 border border-orange-100 px-3 py-1 rounded-full">
              <Flame size={15} className="text-orange-500 animate-pulse" />
              <span className="text-xs font-black text-orange-600">{summary?.streak_days ?? 0} day streak</span>
            </div>
          </div>

          {/* Calendar grid */}
          <div className="flex gap-1.5 flex-wrap justify-center py-2">
            {['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((d, i) => (
              <div key={i} className="w-7 text-center text-[10px] text-slate-400 font-extrabold mb-1">
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

          <div className="flex items-center justify-between mt-3 text-[11px] text-slate-400 font-semibold">
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
        className="glass-card p-6 border border-slate-200/80 shadow-sm"
      >
        <div className="flex items-center gap-2 mb-5">
          <Target size={18} className="text-indigo-600" />
          <h2 className="font-bold text-slate-900 text-base">Topic Progress Breakdown</h2>
        </div>

        {topicProgress.length === 0 ? (
          <div className="p-6 text-center text-xs font-semibold text-slate-400 border border-dashed border-slate-200 rounded-2xl">
            No topic data yet. Start chat sessions or upload document PDFs to track mastery!
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
                <div key={i} className="flex items-center gap-4">
                  <div className="w-36 flex-shrink-0">
                    <p className="text-xs font-bold text-slate-800 truncate">{item.subject || item.topic}</p>
                    <span className={`badge ${badge_class} mt-0.5 inline-block text-[9px]`}>
                      {mastery_label}
                    </span>
                  </div>
                  <div className="flex-1">
                    <div className="progress-bar">
                      <motion.div
                        className="progress-fill"
                        initial={{ width: 0 }}
                        animate={{ width: `${mastery}%` }}
                        transition={{ delay: i * 0.08, duration: 0.7, ease: 'easeOut' }}
                      />
                    </div>
                  </div>
                  <span className="text-xs font-black text-slate-700 w-12 text-right">{mastery}%</span>
                </div>
              )
            })}
          </div>
        )}
      </motion.div>
    </div>
  )
}
