import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Trophy,
  Crown,
  Medal,
  Award,
  Search,
  Sparkles,
  Target,
  FileText,
  Brain,
  CheckCircle2,
  TrendingUp,
  Flame,
  UserCheck
} from 'lucide-react'
import { leaderboardApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'

interface RankedUser {
  user_id: string
  username: string
  email: string
  total_xp: number
  quizzes_taken: number
  avg_accuracy: number
  docs_uploaded: number
  badges: string[]
  is_current_user: boolean
  rank: number
}

interface LeaderboardData {
  rankings: RankedUser[]
  top_3: RankedUser[]
  current_user_rank: RankedUser | null
}

export default function LeaderboardPage() {
  const currentUser = useAuthStore((s) => s.user)
  const [data, setData] = useState<LeaderboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [activeTab, setActiveTab] = useState<'all' | 'top' | 'mine'>('all')

  useEffect(() => {
    fetchLeaderboard()
  }, [])

  const fetchLeaderboard = async () => {
    setLoading(true)
    try {
      const res = await leaderboardApi.getRankings()
      setData(res.data)
    } catch (error) {
      console.error('Failed to fetch leaderboard rankings:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="p-8 max-w-7xl mx-auto flex flex-col items-center justify-center min-h-[500px] space-y-4">
        <div className="w-12 h-12 border-4 border-slate-900 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm font-extrabold text-slate-600">Loading Student Leaderboard & Rankings...</p>
      </div>
    )
  }

  const rankings = data?.rankings || []
  const top3 = data?.top_3 || []
  const currentUserRank = data?.current_user_rank

  // Filter rankings based on search & tabs
  const filteredRankings = rankings.filter((user) => {
    const matchesSearch =
      user.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
      user.email.toLowerCase().includes(searchQuery.toLowerCase())

    if (!matchesSearch) return false

    if (activeTab === 'top') return user.rank <= 5
    if (activeTab === 'mine') return user.is_current_user
    return true
  })

  // Get podium order: 2nd (left), 1st (center), 3rd (right)
  const first = top3[0]
  const second = top3[1]
  const third = top3[2]

  return (
    <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-8 font-sans text-slate-800">
      
      {/* ─── HEADER ─── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <div className="w-11 h-11 rounded-2xl bg-amber-500 text-white flex items-center justify-center shadow-md">
              <Trophy size={24} />
            </div>
            <div>
              <h1 className="text-2xl font-black tracking-tight text-slate-900">
                Student Leaderboard
              </h1>
              <p className="text-xs font-semibold text-slate-500">
                Earn XP by completing AI quizzes, mastering topics, and indexing study PDFs
              </p>
            </div>
          </div>
        </div>

        {/* User Rank Quick Badge */}
        {currentUserRank && (
          <div className="bg-white border border-slate-200 p-3 px-5 rounded-2xl shadow-sm flex items-center gap-4">
            <div className="flex items-center gap-2">
              <Sparkles className="text-amber-500" size={18} />
              <div>
                <p className="text-[10px] font-black uppercase text-slate-400">Your Rank</p>
                <p className="text-lg font-black text-slate-900">#{currentUserRank.rank}</p>
              </div>
            </div>
            <div className="h-8 w-px bg-slate-200" />
            <div>
              <p className="text-[10px] font-black uppercase text-slate-400">Total Score</p>
              <p className="text-lg font-black text-amber-600">{currentUserRank.total_xp} XP</p>
            </div>
          </div>
        )}
      </div>

      {/* ─── TOP 3 PODIUM STAND ─── */}
      {top3.length > 0 && (
        <div className="bg-gradient-to-b from-slate-900 to-slate-950 rounded-3xl p-6 md:p-10 border border-slate-800 text-white shadow-xl relative overflow-hidden">
          {/* Subtle background glow */}
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-96 h-48 bg-amber-500/10 rounded-full blur-3xl pointer-events-none" />

          <div className="text-center mb-8">
            <span className="text-xs font-black uppercase tracking-widest text-amber-400 bg-amber-400/10 px-3 py-1 rounded-full border border-amber-400/20">
              Hall of Fame
            </span>
            <h2 className="text-xl font-black text-white mt-2">Top 3 Scholars</h2>
          </div>

          <div className="grid grid-cols-3 gap-3 md:gap-6 items-end max-w-3xl mx-auto pt-4">
            
            {/* 🥈 2ND PLACE PODIUM */}
            {second ? (
              <motion.div
                initial={{ y: 30, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ delay: 0.1 }}
                className="flex flex-col items-center"
              >
                <div className="relative mb-3 flex flex-col items-center">
                  <Medal size={24} className="text-slate-300 absolute -top-6" />
                  <div className="w-14 h-14 md:w-16 md:h-16 rounded-2xl bg-slate-800 border-2 border-slate-400 flex items-center justify-center font-black text-lg text-slate-200 shadow-lg">
                    {second.username[0]?.toUpperCase()}
                  </div>
                  <span className="text-xs font-extrabold text-slate-200 mt-2 truncate max-w-[90px] md:max-w-[120px]">
                    {second.username}
                  </span>
                  <span className="text-[11px] font-black text-slate-400">{second.total_xp} XP</span>
                </div>

                <div className="w-full bg-slate-800/80 border border-slate-700/80 rounded-t-2xl h-32 md:h-40 flex flex-col items-center justify-center p-2 shadow-inner">
                  <span className="text-2xl md:text-3xl font-black text-slate-300">2</span>
                  <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider">Silver</span>
                </div>
              </motion.div>
            ) : <div />}

            {/* 🥇 1ST PLACE PODIUM (ELEVATED CENTER) */}
            {first ? (
              <motion.div
                initial={{ y: 40, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ delay: 0.2 }}
                className="flex flex-col items-center"
              >
                <div className="relative mb-3 flex flex-col items-center">
                  <Crown size={32} className="text-amber-400 absolute -top-8 animate-bounce" />
                  <div className="w-16 h-16 md:w-20 md:h-20 rounded-2xl bg-gradient-to-br from-amber-400 to-amber-600 border-2 border-amber-300 flex items-center justify-center font-black text-2xl text-slate-950 shadow-xl shadow-amber-500/20">
                    {first.username[0]?.toUpperCase()}
                  </div>
                  <span className="text-sm font-black text-white mt-2 truncate max-w-[100px] md:max-w-[140px]">
                    {first.username}
                  </span>
                  <span className="text-xs font-black text-amber-400">{first.total_xp} XP</span>
                </div>

                <div className="w-full bg-gradient-to-t from-amber-600/30 to-amber-500/20 border border-amber-500/40 rounded-t-2xl h-44 md:h-52 flex flex-col items-center justify-center p-2 shadow-lg">
                  <span className="text-3xl md:text-4xl font-black text-amber-400">1</span>
                  <span className="text-[10px] font-black text-amber-300 uppercase tracking-wider">Gold Champion</span>
                </div>
              </motion.div>
            ) : <div />}

            {/* 🥉 3RD PLACE PODIUM */}
            {third ? (
              <motion.div
                initial={{ y: 30, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ delay: 0.3 }}
                className="flex flex-col items-center"
              >
                <div className="relative mb-3 flex flex-col items-center">
                  <Award size={24} className="text-amber-700 absolute -top-6" />
                  <div className="w-14 h-14 md:w-16 md:h-16 rounded-2xl bg-slate-800 border-2 border-amber-700 flex items-center justify-center font-black text-lg text-amber-500 shadow-lg">
                    {third.username[0]?.toUpperCase()}
                  </div>
                  <span className="text-xs font-extrabold text-slate-200 mt-2 truncate max-w-[90px] md:max-w-[120px]">
                    {third.username}
                  </span>
                  <span className="text-[11px] font-black text-slate-400">{third.total_xp} XP</span>
                </div>

                <div className="w-full bg-slate-800/80 border border-slate-700/80 rounded-t-2xl h-24 md:h-32 flex flex-col items-center justify-center p-2 shadow-inner">
                  <span className="text-2xl md:text-3xl font-black text-amber-600">3</span>
                  <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider">Bronze</span>
                </div>
              </motion.div>
            ) : <div />}

          </div>
        </div>
      )}

      {/* ─── CONTROLS & TAB FILTERS ─── */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-white p-3 rounded-2xl border border-slate-200 shadow-sm">
        
        {/* Filter Tabs */}
        <div className="flex items-center gap-1.5 bg-slate-100 p-1 rounded-xl w-full sm:w-auto">
          <button
            onClick={() => setActiveTab('all')}
            className={`px-4 py-2 rounded-lg text-xs font-extrabold transition-all flex-1 sm:flex-none ${
              activeTab === 'all' ? 'bg-slate-900 text-white shadow-sm' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            All Students ({rankings.length})
          </button>
          <button
            onClick={() => setActiveTab('top')}
            className={`px-4 py-2 rounded-lg text-xs font-extrabold transition-all flex-1 sm:flex-none ${
              activeTab === 'top' ? 'bg-slate-900 text-white shadow-sm' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Top 5
          </button>
          <button
            onClick={() => setActiveTab('mine')}
            className={`px-4 py-2 rounded-lg text-xs font-extrabold transition-all flex-1 sm:flex-none ${
              activeTab === 'mine' ? 'bg-slate-900 text-white shadow-sm' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            My Rank
          </button>
        </div>

        {/* Search Bar */}
        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3.5 top-2.5 text-slate-400" size={16} />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search student name..."
            className="w-full pl-10 pr-4 py-1.5 text-xs font-semibold rounded-xl bg-slate-50 border border-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900"
          />
        </div>

      </div>

      {/* ─── RANKINGS TABLE ─── */}
      <div className="bg-white rounded-3xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-[11px] font-black uppercase text-slate-400 tracking-wider">
                <th className="py-4 px-6">Rank</th>
                <th className="py-4 px-6">Student</th>
                <th className="py-4 px-6">Total XP</th>
                <th className="py-4 px-6">Quizzes Done</th>
                <th className="py-4 px-6">Avg Accuracy</th>
                <th className="py-4 px-6">PDFs Uploaded</th>
                <th className="py-4 px-6 text-right">Badges</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-sm font-semibold">
              {filteredRankings.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-400 text-xs font-bold">
                    No students match your search filter.
                  </td>
                </tr>
              ) : (
                filteredRankings.map((student) => {
                  const isCurrent = student.is_current_user
                  return (
                    <tr
                      key={student.user_id}
                      className={`transition-colors ${
                        isCurrent
                          ? 'bg-amber-500/10 border-l-4 border-l-amber-500 font-extrabold'
                          : 'hover:bg-slate-50/80'
                      }`}
                    >
                      {/* Rank Number & Icon */}
                      <td className="py-4 px-6">
                        <div className="flex items-center gap-2">
                          {student.rank === 1 ? (
                            <span className="w-7 h-7 rounded-lg bg-amber-400 text-slate-950 flex items-center justify-center font-black text-xs shadow-sm">
                              🥇
                            </span>
                          ) : student.rank === 2 ? (
                            <span className="w-7 h-7 rounded-lg bg-slate-300 text-slate-900 flex items-center justify-center font-black text-xs shadow-sm">
                              🥈
                            </span>
                          ) : student.rank === 3 ? (
                            <span className="w-7 h-7 rounded-lg bg-amber-700 text-white flex items-center justify-center font-black text-xs shadow-sm">
                              🥉
                            </span>
                          ) : (
                            <span className="w-7 h-7 rounded-lg bg-slate-100 text-slate-600 flex items-center justify-center font-extrabold text-xs">
                              #{student.rank}
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Student Info */}
                      <td className="py-4 px-6">
                        <div className="flex items-center gap-3">
                          <div
                            className={`w-9 h-9 rounded-xl flex items-center justify-center font-black text-xs text-white ${
                              isCurrent ? 'bg-amber-600' : 'bg-slate-900'
                            }`}
                          >
                            {student.username[0]?.toUpperCase()}
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-extrabold text-slate-900">{student.username}</span>
                              {isCurrent && (
                                <span className="text-[10px] font-black uppercase bg-amber-500 text-white px-2 py-0.5 rounded-full">
                                  You
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-slate-400 font-medium">{student.email}</p>
                          </div>
                        </div>
                      </td>

                      {/* Total XP */}
                      <td className="py-4 px-6 font-black text-amber-600">
                        {student.total_xp} XP
                      </td>

                      {/* Quizzes Taken */}
                      <td className="py-4 px-6 text-slate-700">
                        <div className="flex items-center gap-1.5">
                          <Brain size={15} className="text-slate-400" />
                          <span>{student.quizzes_taken}</span>
                        </div>
                      </td>

                      {/* Accuracy */}
                      <td className="py-4 px-6">
                        <div className="flex items-center gap-2">
                          <div className="w-16 bg-slate-100 h-2 rounded-full overflow-hidden">
                            <div
                              className="bg-emerald-500 h-full rounded-full"
                              style={{ width: `${Math.min(100, student.avg_accuracy)}%` }}
                            />
                          </div>
                          <span className="text-xs font-bold text-slate-700">{student.avg_accuracy}%</span>
                        </div>
                      </td>

                      {/* Documents Uploaded */}
                      <td className="py-4 px-6 text-slate-700">
                        <div className="flex items-center gap-1.5">
                          <FileText size={15} className="text-slate-400" />
                          <span>{student.docs_uploaded}</span>
                        </div>
                      </td>

                      {/* Badges List */}
                      <td className="py-4 px-6 text-right">
                        <div className="flex items-center justify-end gap-1.5 flex-wrap">
                          {student.badges.map((b, i) => (
                            <span
                              key={i}
                              className="text-[10px] font-extrabold bg-slate-100 text-slate-700 px-2 py-0.5 rounded-md border border-slate-200"
                            >
                              {b}
                            </span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  )
}
