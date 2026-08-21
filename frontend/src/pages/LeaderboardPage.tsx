import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
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
  const [searchQuery, setSearchQuery] = useState('')
  const [activeTab, setActiveTab] = useState<'all' | 'top' | 'mine'>('all')

  const { data, isLoading: loading } = useQuery<LeaderboardData>({
    queryKey: ['leaderboard-rankings'],
    queryFn: () => leaderboardApi.getRankings().then((r) => r.data),
    staleTime: 60_000,
  })

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
    <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-8 font-sans text-[#3C3C3C] bg-[#F7F7F7]">
      
      {/* ─── HEADER ─── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-[#E2E8F0]">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <div className="w-11 h-11 rounded-[1.5rem] bg-[#EEF2FF] border border-[#4F46E5]/30 flex items-center justify-center p-2 elevation-1">
              <img src="/assets/illustrations/gold_medal.png" alt="Leaderboard" className="w-full h-full object-contain" />
            </div>
            <div>
              <h1 className="text-2xl font-black tracking-tight text-[#3C3C3C]">
                Student Leaderboard
              </h1>
              <p className="text-xs font-medium text-[#777777]">
                Earn XP by completing AI quizzes, mastering topics, and indexing study PDFs
              </p>
            </div>
          </div>
        </div>

        {/* User Rank Quick Badge */}
        {currentUserRank && (
          <div className="bg-white border border-[#E2E8F0] p-3 px-5 rounded-[1.5rem] elevation-1 flex items-center gap-4">
            <div className="flex items-center gap-2">
              <Sparkles className="text-[#4F46E5]" size={18} />
              <div>
                <p className="text-[10px] font-black uppercase text-[#AFAFAF]">Your Rank</p>
                <p className="text-lg font-black text-[#3C3C3C]">#{currentUserRank.rank}</p>
              </div>
            </div>
            <div className="h-8 w-px bg-[#E2E8F0]" />
            <div>
              <p className="text-[10px] font-black uppercase text-[#AFAFAF]">Total Score</p>
              <p className="text-lg font-black text-[#4F46E5]">{currentUserRank.total_xp} XP</p>
            </div>
          </div>
        )}
      </div>

      {/* ─── TOP 3 PODIUM STAND ─── */}
      {top3.length > 0 && (
        <div className="bg-gradient-to-b from-[#3C3C3C] to-[#353531] rounded-[2rem] p-6 md:p-10 border border-[#E2E8F0]/20 text-white elevation-2 relative overflow-hidden">
          {/* Subtle background glow */}
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-96 h-48 bg-[#4F46E5]/15 rounded-full blur-3xl pointer-events-none" />

          <div className="text-center mb-8">
            <span className="text-xs font-black uppercase tracking-widest text-[#4F46E5] bg-[#EEF2FF]/10 px-3 py-1 rounded-full border border-[#4F46E5]/30">
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
                  <Medal size={24} className="text-[#E2E8F0] absolute -top-6" />
                  <div className="w-14 h-14 md:w-16 md:h-16 rounded-[1.5rem] bg-[#353531] border-2 border-[#E2E8F0] flex items-center justify-center font-black text-lg text-[#E2E8F0] elevation-1">
                    {second.username[0]?.toUpperCase()}
                  </div>
                  <span className="text-xs font-extrabold text-[#E2E8F0] mt-2 truncate max-w-[90px] md:max-w-[120px]">
                    {second.username}
                  </span>
                  <span className="text-[11px] font-black text-[#AFAFAF]">{second.total_xp} XP</span>
                </div>

                <div className="w-full bg-[#353531]/80 border border-[#E2E8F0]/20 rounded-t-2xl h-32 md:h-40 flex flex-col items-center justify-center p-2">
                  <span className="text-2xl md:text-3xl font-black text-[#E2E8F0]">2</span>
                  <span className="text-[10px] font-black text-[#AFAFAF] uppercase tracking-wider">Silver</span>
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
                  <Crown size={32} className="text-[#4F46E5] absolute -top-8" />
                  <div className="w-16 h-16 md:w-20 md:h-20 rounded-[1.5rem] bg-[#4F46E5] border-2 border-[#EEF2FF] flex items-center justify-center font-black text-2xl text-white elevation-2">
                    {first.username[0]?.toUpperCase()}
                  </div>
                  <span className="text-sm font-black text-white mt-2 truncate max-w-[100px] md:max-w-[140px]">
                    {first.username}
                  </span>
                  <span className="text-xs font-black text-[#4F46E5]">{first.total_xp} XP</span>
                </div>

                <div className="w-full bg-[#4F46E5]/20 border border-[#4F46E5]/40 rounded-t-2xl h-44 md:h-52 flex flex-col items-center justify-center p-2">
                  <span className="text-3xl md:text-4xl font-black text-[#4F46E5]">1</span>
                  <span className="text-[10px] font-black text-[#EEF2FF] uppercase tracking-wider">Gold Champion</span>
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
                  <Award size={24} className="text-[#FFC800] absolute -top-6" />
                  <div className="w-14 h-14 md:w-16 md:h-16 rounded-[1.5rem] bg-[#353531] border-2 border-[#FFC800] flex items-center justify-center font-black text-lg text-[#FFC800] elevation-1">
                    {third.username[0]?.toUpperCase()}
                  </div>
                  <span className="text-xs font-extrabold text-[#E2E8F0] mt-2 truncate max-w-[90px] md:max-w-[120px]">
                    {third.username}
                  </span>
                  <span className="text-[11px] font-black text-[#AFAFAF]">{third.total_xp} XP</span>
                </div>

                <div className="w-full bg-[#353531]/80 border border-[#E2E8F0]/20 rounded-t-2xl h-24 md:h-32 flex flex-col items-center justify-center p-2">
                  <span className="text-2xl md:text-3xl font-black text-[#FFC800]">3</span>
                  <span className="text-[10px] font-black text-[#AFAFAF] uppercase tracking-wider">Bronze</span>
                </div>
              </motion.div>
            ) : <div />}

          </div>
        </div>
      )}

      {/* ─── CONTROLS & TAB FILTERS ─── */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-white p-3 rounded-[1.5rem] border border-[#E2E8F0] elevation-1">
        
        {/* Filter Tabs */}
        <div className="flex items-center gap-1.5 bg-[#E5E5E5] p-1 rounded-[1.25rem] w-full sm:w-auto">
          <button
            onClick={() => setActiveTab('all')}
            className={`px-4 py-2 rounded-lg text-xs font-black transition-all flex-1 sm:flex-none cursor-pointer ${
              activeTab === 'all' ? 'bg-[#4F46E5] text-white elevation-1' : 'text-[#777777] hover:text-[#3C3C3C]'
            }`}
          >
            All Students ({rankings.length})
          </button>
          <button
            onClick={() => setActiveTab('top')}
            className={`px-4 py-2 rounded-lg text-xs font-black transition-all flex-1 sm:flex-none cursor-pointer ${
              activeTab === 'top' ? 'bg-[#4F46E5] text-white elevation-1' : 'text-[#777777] hover:text-[#3C3C3C]'
            }`}
          >
            Top 5
          </button>
          <button
            onClick={() => setActiveTab('mine')}
            className={`px-4 py-2 rounded-lg text-xs font-black transition-all flex-1 sm:flex-none cursor-pointer ${
              activeTab === 'mine' ? 'bg-[#4F46E5] text-white elevation-1' : 'text-[#777777] hover:text-[#3C3C3C]'
            }`}
          >
            My Rank
          </button>
        </div>

        {/* Search Bar */}
        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3.5 top-2.5 text-[#AFAFAF]" size={16} />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search student name..."
            className="w-full pl-10 pr-4 py-1.5 text-xs font-bold rounded-[1.25rem] bg-white border border-[#E2E8F0] text-[#3C3C3C] placeholder-[#AFAFAF] focus:outline-none focus:border-[#4F46E5] focus:ring-2 focus:ring-[#4F46E5]/20"
          />
        </div>

      </div>

      {/* ─── RANKINGS TABLE ─── */}
      <div className="bg-white rounded-[2rem] border border-[#E2E8F0] elevation-1 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-[#F7F7F7] border-b border-[#E2E8F0] text-[11px] font-black uppercase text-[#AFAFAF] tracking-wider">
                <th className="py-4 px-6">Rank</th>
                <th className="py-4 px-6">Student</th>
                <th className="py-4 px-6">Total XP</th>
                <th className="py-4 px-6">Quizzes Done</th>
                <th className="py-4 px-6">Avg Accuracy</th>
                <th className="py-4 px-6">PDFs Uploaded</th>
                <th className="py-4 px-6 text-right">Badges</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E2E8F0]/60 text-sm font-semibold">
              {filteredRankings.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-[#AFAFAF] text-xs font-bold">
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
                          ? 'bg-[#EEF2FF]/60 border-l-4 border-l-[#4F46E5] font-extrabold'
                          : 'hover:bg-[#FFFFFF]'
                      }`}
                    >
                      {/* Rank Number & Icon */}
                      <td className="py-4 px-6">
                        <div className="flex items-center gap-2">
                          {student.rank === 1 ? (
                            <span className="w-7 h-7 rounded-lg bg-[#4F46E5] text-white flex items-center justify-center font-black text-xs elevation-1">
                              🥇
                            </span>
                          ) : student.rank === 2 ? (
                            <span className="w-7 h-7 rounded-lg bg-[#E2E8F0] text-[#3C3C3C] flex items-center justify-center font-black text-xs elevation-1">
                              🥈
                            </span>
                          ) : student.rank === 3 ? (
                            <span className="w-7 h-7 rounded-lg bg-[#FFC800] text-white flex items-center justify-center font-black text-xs elevation-1">
                              🥉
                            </span>
                          ) : (
                            <span className="w-7 h-7 rounded-lg bg-[#E5E5E5] text-[#777777] flex items-center justify-center font-extrabold text-xs">
                              #{student.rank}
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Student Info */}
                      <td className="py-4 px-6">
                        <div className="flex items-center gap-3">
                          <div
                            className={`w-9 h-9 rounded-[1.25rem] flex items-center justify-center font-black text-xs text-white ${
                              isCurrent ? 'bg-[#4F46E5]' : 'bg-[#3C3C3C]'
                            }`}
                          >
                            {student.username[0]?.toUpperCase()}
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-extrabold text-[#3C3C3C]">{student.username}</span>
                              {isCurrent && (
                                <span className="text-[10px] font-black uppercase bg-[#4F46E5] text-white px-2 py-0.5 rounded-full">
                                  You
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-[#AFAFAF] font-medium">{student.email}</p>
                          </div>
                        </div>
                      </td>

                      {/* Total XP */}
                      <td className="py-4 px-6 font-black text-[#4F46E5]">
                        {student.total_xp} XP
                      </td>

                      {/* Quizzes Taken */}
                      <td className="py-4 px-6 text-[#3C3C3C]">
                        <div className="flex items-center gap-1.5">
                          <Brain size={15} className="text-[#AFAFAF]" />
                          <span>{student.quizzes_taken}</span>
                        </div>
                      </td>

                      {/* Accuracy */}
                      <td className="py-4 px-6">
                        <div className="flex items-center gap-2">
                          <div className="w-16 bg-[#E5E5E5] h-2 rounded-full overflow-hidden">
                            <div
                              className="bg-[#58CC02] h-full rounded-full"
                              style={{ width: `${Math.min(100, student.avg_accuracy)}%` }}
                            />
                          </div>
                          <span className="text-xs font-black text-[#3C3C3C]">{student.avg_accuracy}%</span>
                        </div>
                      </td>

                      {/* Documents Uploaded */}
                      <td className="py-4 px-6 text-[#3C3C3C]">
                        <div className="flex items-center gap-1.5">
                          <FileText size={15} className="text-[#AFAFAF]" />
                          <span>{student.docs_uploaded}</span>
                        </div>
                      </td>

                      {/* Badges List */}
                      <td className="py-4 px-6 text-right">
                        <div className="flex items-center justify-end gap-1.5 flex-wrap">
                          {student.badges.map((b, i) => (
                            <span
                              key={i}
                              className="text-[10px] font-extrabold bg-[#EEF2FF] text-[#4F46E5] px-2 py-0.5 rounded-md border border-[#4F46E5]/30"
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
