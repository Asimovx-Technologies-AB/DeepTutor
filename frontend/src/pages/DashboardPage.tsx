import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, Bell, User, ChevronDown, Sparkles, Trophy, Download, PlayCircle, MoreHorizontal } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useSubjectStore } from '../stores/subjectStore'

import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '../services/api'
import NotificationPopup from '../components/NotificationPopup'
import ProfileModal from '../components/ProfileModal'
import ContinueLearningCard from '../components/dashboard/ContinueLearningCard'
import LearningStatsRow from '../components/dashboard/LearningStatsRow'
import RecentActivityTimeline from '../components/dashboard/RecentActivityTimeline'
import LearningStreak from '../components/dashboard/LearningStreak'
import PageContainer from '../components/PageContainer'

export default function DashboardPage() {
  const { user } = useAuthStore()
  const navigate = useNavigate()

  const [isProfileOpen, setIsProfileOpen] = useState(false)

  // Fetch Dynamic Data
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: async () => {
      const res = await dashboardApi.stats()
      return res.data
    }
  })

  const { data: recentActivity, isLoading: activityLoading } = useQuery({
    queryKey: ['dashboard-activity'],
    queryFn: async () => {
      const res = await dashboardApi.activity(5)
      return res.data
    }
  })

  const { data: continueData, isLoading: continueLoading } = useQuery({
    queryKey: ['dashboard-continue'],
    queryFn: async () => {
      const res = await dashboardApi.continue()
      return res.data
    }
  })

  const { getSubject, getTopics } = useSubjectStore()

  // Resolve continue learning meta
  let continueSubject = null
  let continueTopic = null
  if (continueData) {
    continueSubject = getSubject(continueData.subject_id)
    continueTopic = getTopics(continueData.subject_id)?.find(t => t.id === continueData.topic_id)
  }

  return (
    <PageContainer maxWidth="2xl">

      <ProfileModal isOpen={isProfileOpen} onClose={() => setIsProfileOpen(false)} />

      {/* TOP HEADER: "Dashboard overview" + Top Right Nav */}
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-xl font-semibold text-[#1E293B]">Dashboard overview</h1>
        <div className="flex items-center gap-4">
          <button className="w-10 h-10 bg-white rounded-full flex items-center justify-center text-[#64748B] hover:text-[#1E293B] shadow-[0_4px_15px_rgba(0,0,0,0.02)] transition-colors">
            <Search size={18} />
          </button>
          <NotificationPopup />

          <div
            onClick={() => setIsProfileOpen(true)}
            className="flex items-center gap-3 bg-white rounded-full py-1.5 px-2 pr-4 cursor-pointer shadow-[0_4px_15px_rgba(0,0,0,0.02)] hover:shadow-[0_8px_25px_rgba(0,0,0,0.05)] transition-all"
          >
            <div className="w-8 h-8 rounded-full bg-[#1E293B] flex items-center justify-center text-white font-bold text-xs">
              {user?.username?.[0]?.toUpperCase() ?? 'M'}
            </div>
            <div className="flex flex-col">
              <span className="text-[13px] font-semibold text-[#1E293B] leading-none">{user?.username || 'Miquella strife'}</span>
              <span className="text-[10px] text-[#64748B] mt-0.5 leading-none">{user?.email || 'miquella@gmail.com'}</span>
            </div>
            <ChevronDown size={14} className="text-[#94A3B8] ml-2" />
          </div>
        </div>
      </div>

      {/* MAIN LAYOUT GRID */}
      <div className="flex flex-col gap-8 flex-1">

        {/* ROW 1: Hero & Courses */}
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-8">

          {/* Left Hero (4 Columns) */}
          <div className="xl:col-span-4 flex flex-col justify-center">
            {/* Hero Mascot Illustration */}
            <div className="w-24 h-24 mb-1 opacity-90 pointer-events-none">
              <img src="/assets/illustrations/hero_mascot.jpg" alt="Friendly Robot Mascot" className="w-full h-full object-contain mix-blend-multiply rounded-full" />
            </div>

            <h2 className="text-display leading-[1.1] mb-2 tracking-tight">
              Hi, {user?.username || 'Miquella'} 👋 <br className="hidden xl:block" />
              what do you want <br className="hidden xl:block" /> to learn today?
            </h2>
            <p className="text-[#64748B] text-[14px] mb-5 max-w-sm">
              Discover courses, track progress, and achieve your learning goals seamlessly.
            </p>
            <div>
              <button
                onClick={() => navigate('/subjects')}
                className="btn-primary px-6 py-2.5 text-[14px]"
              >
                Explore course
              </button>
            </div>
          </div>

          {/* Right Horizontal Stats Row (8 Columns) */}
          <div className="xl:col-span-8 flex flex-col justify-center h-full">
            <LearningStatsRow stats={stats} />
          </div>
        </div>

        {/* ROW 2: Bottom Section */}
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-8 flex-1">

          {/* Left & Middle combined (8 Columns) */}
          <div className="xl:col-span-8 flex flex-col gap-8">

            {/* Middle Row (Cards) */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 h-auto">
              {continueData && continueSubject && continueTopic ? (
                <div className="col-span-1 h-[140px] xl:h-[160px]">
                  <ContinueLearningCard
                    subjectId={continueData.subject_id}
                    topicId={continueData.topic_id}
                    topicTitle={continueTopic.title}
                    progress={continueData.progress_percentage}
                    lastStudied={continueData.last_studied_at}
                  />
                </div>
              ) : (
                <div className="col-span-1 card p-6 flex flex-col justify-center items-center gap-3 bg-slate-50 border border-dashed border-slate-200">
                  <span className="text-2xl">📚</span>
                  <p className="text-sm font-medium text-[#1E293B]">Ready to start learning?</p>
                  <button onClick={() => navigate('/subjects')} className="btn-primary px-4 py-1.5 text-xs">Explore Curriculum</button>
                </div>
              )}

              <div className="col-span-1 h-[140px] xl:h-[160px]">
                <LearningStreak
                  currentStreak={stats?.current_streak || 0}
                  longestStreak={stats?.longest_streak || 0}
                />
              </div>
            </div>

            {/* Today's Activity Timeline */}
            <RecentActivityTimeline activities={recentActivity} isLoading={activityLoading} />

          </div>

          {/* Right Sidebar: Performance report (4 Columns) */}
          <div className="xl:col-span-4 card p-6 xl:p-8 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-6 xl:mb-8">
                <h3 className="font-semibold text-lg xl:text-xl text-[#1E293B]">Performance report</h3>
                <MoreHorizontal className="text-[#94A3B8] cursor-pointer" size={20} />
              </div>

              <div className="flex flex-col items-center mb-6 xl:mb-8">
                <div className="w-20 h-20 xl:w-24 xl:h-24 rounded-full border-[3px] border-[#10B981] p-1 mb-4 relative shadow-[0_10px_30px_rgba(16,185,129,0.2)]">
                  <div className="w-full h-full bg-[#1E293B] rounded-full flex items-center justify-center text-3xl xl:text-4xl text-white font-bold">
                    {user?.username?.[0]?.toUpperCase() ?? 'M'}
                  </div>
                </div>
                <h4 className="text-base xl:text-lg font-semibold text-[#1E293B]">{user?.username || 'Miquella strife'}</h4>
                <p className="text-[#64748B] text-[12px] xl:text-[13px]">{user?.email}</p>
              </div>

              <div className="grid grid-cols-3 gap-3 xl:gap-4 border-t border-b border-[#F1F5F9] py-5 xl:py-6 mb-6 xl:mb-8">
                <div className="flex flex-col items-center gap-2">
                  <div className="w-9 h-9 xl:w-10 xl:h-10 rounded-xl bg-[#ECFDF5] text-[#10B981] flex items-center justify-center text-base xl:text-lg">📚</div>
                  <div className="text-center">
                    <p className="text-[10px] xl:text-[11px] text-[#64748B] font-medium">Courses</p>
                    <p className="text-[12px] xl:text-[13px] font-semibold text-[#1E293B]">{stats?.courses_completed || 0}</p>
                  </div>
                </div>
                <div className="flex flex-col items-center gap-2">
                  <div className="w-9 h-9 xl:w-10 xl:h-10 rounded-xl bg-[#F2E8FA] text-[#8B5CF6] flex items-center justify-center text-base xl:text-lg">✨</div>
                  <div className="text-center">
                    <p className="text-[10px] xl:text-[11px] text-[#64748B] font-medium">Lessons</p>
                    <p className="text-[12px] xl:text-[13px] font-semibold text-[#1E293B]">{stats?.lessons_completed || 0}</p>
                  </div>
                </div>
                <div className="flex flex-col items-center gap-2">
                  <div className="w-9 h-9 xl:w-10 xl:h-10 rounded-xl bg-[#FFFBEB] text-[#F59E0B] flex items-center justify-center text-base xl:text-lg">🏆</div>
                  <div className="text-center">
                    <p className="text-[10px] xl:text-[11px] text-[#64748B] font-medium">Top Streak</p>
                    <p className="text-[12px] xl:text-[13px] font-semibold text-[#1E293B]">{stats?.longest_streak || 0}d</p>
                  </div>
                </div>
              </div>
            </div>

            <div>
              <h3 className="font-semibold text-[14px] xl:text-[15px] text-[#1E293B] mb-3 xl:mb-4">Upcoming assignment</h3>
              <div className="bg-[#E3FDF5] rounded-2xl p-3 xl:p-4 flex items-center gap-3 xl:gap-4 cursor-pointer hover:bg-[#D1F9EA] transition-colors">
                <div className="w-9 h-9 xl:w-10 xl:h-10 bg-white rounded-full flex items-center justify-center text-base xl:text-lg flex-shrink-0 shadow-sm">
                  🐼
                </div>
                <div>
                  <h4 className="text-[12px] xl:text-[13px] font-semibold text-[#1E293B]">Create a cute red panda mascot</h4>
                  <p className="text-[10px] xl:text-[11px] text-[#64748B] mt-0.5 xl:mt-1">Due 12 august 2024 - 12:00 AM</p>
                </div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </PageContainer>
  )
}
