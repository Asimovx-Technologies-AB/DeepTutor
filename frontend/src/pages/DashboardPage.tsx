import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, ChevronDown, MoreHorizontal, BookOpen, Sparkles, Target, ArrowRight } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useSubjectStore } from '../stores/subjectStore'
import { useLanguageStore } from '../stores/languageStore'
import { useTranslation } from '../utils/translations'

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

  const { uiLanguage } = useLanguageStore()
  const t = useTranslation(uiLanguage)

  const [isProfileOpen, setIsProfileOpen] = useState(false)

  // Fetch Dynamic Data with snappy in-memory caching (background revalidation)
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: async () => {
      const res = await dashboardApi.stats()
      return res.data
    },
    staleTime: 60_000,
  })

  const { data: recentActivity, isLoading: activityLoading } = useQuery({
    queryKey: ['dashboard-activity'],
    queryFn: async () => {
      const res = await dashboardApi.activity(8)
      return res.data
    },
    staleTime: 60_000,
  })

  const { data: continueData, isLoading: continueLoading } = useQuery({
    queryKey: ['dashboard-continue'],
    queryFn: async () => {
      const res = await dashboardApi.continue()
      return res.data
    },
    staleTime: 60_000,
  })

  const { getSubject, getTopics } = useSubjectStore()

  // Resolve continue learning meta
  let continueSubject = null
  let continueTopic = null
  let resolvedTopicTitle = 'Active Document Topic'
  if (continueData) {
    continueSubject = getSubject(continueData.subject_id)
    continueTopic = getTopics(continueData.subject_id)?.find(t => t.id === continueData.topic_id)
    resolvedTopicTitle = continueData.topic_title || continueTopic?.title || continueData.topic_id || 'Document Study'
  }

  return (
    <PageContainer maxWidth="full">

      <ProfileModal isOpen={isProfileOpen} onClose={() => setIsProfileOpen(false)} />

      {/* TOP HEADER: "Dashboard overview" + Top Right Nav */}
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-xl font-bold text-slate-800 tracking-tight">{t.dashboard.welcome}</h1>
        <div className="flex items-center gap-4">
          <NotificationPopup />

          <div
            onClick={() => setIsProfileOpen(true)}
            className="flex items-center gap-3 bg-white rounded-full py-1.5 px-2 pr-4 cursor-pointer shadow-xs border border-slate-200 hover:shadow-sm transition-all"
          >
            <div className="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center text-white font-bold text-xs shadow-2xs">
              {user?.username?.[0]?.toUpperCase() ?? 'U'}
            </div>
            <div className="flex flex-col text-left">
              <span className="text-[13px] font-bold text-slate-800 leading-none">{user?.username || 'Learner'}</span>
              <span className="text-[10px] text-slate-400 mt-0.5 leading-none">{user?.email || 'student@indietutor.ai'}</span>
            </div>
            <ChevronDown size={14} className="text-slate-400 ml-1" />
          </div>
        </div>
      </div>

      {/* MAIN LAYOUT GRID */}
      <div className="flex flex-col gap-8 flex-1">

        {/* ROW 1: Hero & Courses */}
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-8">

          {/* Left Hero */}
          <div className="xl:col-span-6 flex flex-col justify-center">
            <div className="flex items-start gap-4 mb-4">
              {/* Mascot Badge */}
              <div className="w-16 h-16 rounded-2xl bg-indigo-50 border border-indigo-200 flex items-center justify-center text-3xl shadow-xs flex-shrink-0">
                🚀
              </div>
              <div>
                <h2 className="text-3xl sm:text-4xl font-black leading-tight tracking-tight text-slate-800">
                  {t.dashboard.welcome}, {user?.username || 'Learner'}! 👋
                </h2>
                <p className="text-slate-500 text-sm mt-1.5 font-medium">
                  {t.dashboard.subtitle}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3 mt-2">
              <button
                onClick={() => navigate('/chat')}
                className="btn-primary px-6 py-2.5 text-xs sm:text-sm font-bold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl shadow-xs hover:shadow-md transition-all flex items-center gap-2"
              >
                <Sparkles size={16} />
                {t.dashboard.startChat}
              </button>
              <button
                onClick={() => navigate('/subjects')}
                className="px-5 py-2.5 text-xs sm:text-sm font-bold bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 rounded-xl transition-colors"
              >
                {t.dashboard.mySubjects}
              </button>
            </div>
          </div>

          {/* Right Horizontal Stats Row (6 Columns) */}
          <div className="xl:col-span-6 flex flex-col justify-center h-full">
            <LearningStatsRow stats={stats} />
          </div>
        </div>

        {/* ROW 2: Bottom Section */}
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-8 flex-1">

          {/* Left & Middle combined (8 Columns) */}
          <div className="xl:col-span-8 flex flex-col gap-8">

            {/* Middle Row (Cards) */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 h-auto">
              {continueData ? (
                <div className="col-span-1 h-auto min-h-[140px]">
                  <ContinueLearningCard
                    subjectId={continueData.subject_id || 'general'}
                    topicId={continueData.topic_id || 'history'}
                    topicTitle={resolvedTopicTitle}
                    progress={continueData.progress_percentage ?? 0}
                    lastStudied={continueData.last_studied_at}
                    continuePath={continueData.continue_path}
                  />
                </div>
              ) : (
                <div className="col-span-1 p-6 rounded-3xl flex flex-col justify-center items-center gap-2.5 bg-indigo-50/40 border border-dashed border-indigo-200/80 text-center min-h-[140px]">
                  <span className="text-2xl">📚</span>
                  <p className="text-xs font-bold text-slate-800">
                    {uiLanguage === 'sv' ? 'Redo att börja lära dig?' : 'Ready to Start Learning?'}
                  </p>
                  <p className="text-[11px] text-slate-500 font-medium max-w-xs">
                    {uiLanguage === 'sv' ? 'Ladda upp ditt eget kursmaterial. AI identifierar ämnet och viktiga områden.' : 'Upload your own study material. AI will identify the subject and key topics.'}
                  </p>
                  <button 
                    onClick={() => navigate('/chat')} 
                    className="mt-1 px-4 py-1.5 text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl shadow-2xs transition-all"
                  >
                    {uiLanguage === 'sv' ? 'Starta AI-session' : 'Start AI Session'}
                  </button>
                </div>
              )}

              <div className="col-span-1 h-auto min-h-[140px]">
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
          <div className="xl:col-span-4 rounded-3xl bg-white border border-slate-200/80 p-6 xl:p-8 flex flex-col justify-between shadow-xs">
            <div>
              <div className="flex items-center justify-between mb-6">
                <h3 className="font-black text-lg text-slate-800 tracking-tight">
                  {uiLanguage === 'sv' ? 'Prestandarapport' : 'Performance Report'}
                </h3>
                <MoreHorizontal className="text-slate-400 cursor-pointer" size={20} />
              </div>

              <div className="flex flex-col items-center mb-6 text-center">
                <div className="w-20 h-20 rounded-full border-2 border-indigo-100 p-1 mb-3 relative shadow-xs bg-indigo-50/50 flex items-center justify-center">
                  <div className="w-full h-full bg-indigo-600 rounded-full flex items-center justify-center text-3xl text-white font-black shadow-2xs">
                    {user?.username?.[0]?.toUpperCase() ?? 'U'}
                  </div>
                </div>
                <h4 className="text-base font-black text-slate-800">{user?.username || 'Learner'}</h4>
                <p className="text-slate-500 text-xs font-medium">{user?.email}</p>
              </div>

              <div className="grid grid-cols-3 gap-2 border-t border-b border-slate-100 py-4 mb-6">
                <div className="flex flex-col items-center p-2 rounded-2xl bg-slate-50/70 border border-slate-100">
                  <div className="w-8 h-8 rounded-xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center text-sm mb-1.5 shadow-2xs">📚</div>
                  <p className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                    {uiLanguage === 'sv' ? 'KURSER' : 'COURSES'}
                  </p>
                  <p className="text-sm font-black text-slate-800 mt-0.5">{stats?.courses_in_progress ?? stats?.courses_completed ?? 0}</p>
                </div>
                <div className="flex flex-col items-center p-2 rounded-2xl bg-slate-50/70 border border-slate-100">
                  <div className="w-8 h-8 rounded-xl bg-amber-50 border border-amber-100 text-amber-600 flex items-center justify-center text-sm mb-1.5 shadow-2xs">✨</div>
                  <p className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                    {uiLanguage === 'sv' ? 'LEKTIONER' : 'LESSONS'}
                  </p>
                  <p className="text-sm font-black text-slate-800 mt-0.5">{stats?.lessons_completed || 0}</p>
                </div>
                <div className="flex flex-col items-center p-2 rounded-2xl bg-slate-50/70 border border-slate-100">
                  <div className="w-8 h-8 rounded-xl bg-emerald-50 border border-emerald-100 text-emerald-600 flex items-center justify-center text-sm mb-1.5 shadow-2xs">🏆</div>
                  <p className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                    {uiLanguage === 'sv' ? 'SVIT' : 'STREAK'}
                  </p>
                  <p className="text-sm font-black text-slate-800 mt-0.5">{stats?.longest_streak || 0}d</p>
                </div>
              </div>
            </div>

            <div>
              <h3 className="font-bold text-xs text-slate-700 uppercase tracking-wider mb-2.5">
                {uiLanguage === 'sv' ? 'Rekommenderat studiefokus' : 'Recommended Study Focus'}
              </h3>
              <div 
                onClick={() => navigate('/chat')}
                className="bg-indigo-50/70 border border-indigo-200/80 rounded-2xl p-3.5 flex items-center gap-3 cursor-pointer hover:bg-indigo-100/70 hover:border-indigo-300 transition-all shadow-2xs group"
              >
                <div className="w-9 h-9 bg-indigo-600 text-white rounded-xl flex items-center justify-center text-base flex-shrink-0 shadow-2xs group-hover:scale-105 transition-transform">
                  🎯
                </div>
                <div className="min-w-0 flex-1">
                  <h4 className="text-xs font-bold text-slate-800 truncate">
                    {stats?.latest_doc ? (uiLanguage === 'sv' ? `Repetera ${stats.latest_doc}` : `Review ${stats.latest_doc}`) : (uiLanguage === 'sv' ? 'Daglig examensövning' : 'Daily Kerala SCERT Exam Practice')}
                  </h4>
                  <p className="text-[11px] text-indigo-600 font-semibold mt-0.5 flex items-center gap-1">
                    <span>{uiLanguage === 'sv' ? 'Fråga AI-Handledare' : 'Ask AI Tutor'}</span>
                    <ArrowRight size={12} />
                  </p>
                </div>
              </div>
            </div>
          </div>

        </div>

