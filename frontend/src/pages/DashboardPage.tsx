import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  MessageSquare, Star, BookOpen, CalendarCheck,
  Flame, ArrowRight, Brain, Zap, Clock, Send,
  Trophy, CheckCircle2, Sparkles, X, Lightbulb, Code2,
  HelpCircle, Compass, LineChart, Hash, ChevronRight,
  Target, Layers, Dna, Atom, Globe, Book, Check, Award,
  Bell, User, MoreHorizontal
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useSubjectStore } from '../stores/subjectStore'
import { progressApi, chatApi } from '../services/api'

import NotificationPopup from '../components/NotificationPopup'
import ProfileModal from '../components/ProfileModal'

export default function DashboardPage() {
  const { user } = useAuthStore()
  const navigate = useNavigate()

  const {
    getSubject,
    getSubjectProgress,
    getCurrentTopic,
    getTopics,
    getRecommendation,
  } = useSubjectStore()

  const recommendation = getRecommendation()

  // Profile Modal State
  const [isProfileOpen, setIsProfileOpen] = useState(false)

  // Quick Chat input state
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

  const handleQuickAsk = (e?: React.FormEvent, customText?: string) => {
    if (e) e.preventDefault()
    const textToSend = customText || quickPrompt
    if (!textToSend.trim()) return
    navigate('/chat', { state: { initialPrompt: textToSend } })
  }

  const completedGoalsCount = goals.filter(g => g.completed).length
  const goalPct = Math.round((completedGoalsCount / goals.length) * 100)

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-8 bg-[#FAF8F3] text-[#20201D] font-sans">
      
      {/* User View/Edit Profile Modal */}
      <ProfileModal isOpen={isProfileOpen} onClose={() => setIsProfileOpen(false)} />

      {/* ─── 1. TOP HEADER & HEADER ACTIONS ─── */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#E7E1D8]/60 pb-5"
      >
        <div>
          <h1 className="text-[28px] sm:text-[32px] leading-[36px] sm:leading-[40px] tracking-[-0.6px] font-bold text-[#20201D] flex items-center gap-2">
            <span>{timeGreeting}, <span className="text-[#F28A45] font-bold">{user?.username || 'adwaid'}</span></span>
            <span className="text-2xl animate-bounce">👋</span>
          </h1>
          <p className="text-[#6F6B63] text-sm leading-[22px] font-normal mt-1">
            Let's continue your learning journey.
          </p>
        </div>

        {/* Top Right Header Action Items matching reference image */}
        <div className="flex items-center gap-3 self-start sm:self-auto">
          {/* Ask Your Tutor Button */}
          <button
            onClick={() => navigate('/chat')}
            className="btn-primary font-semibold text-sm py-2.5 px-4 rounded-full flex items-center gap-2 shadow-2xs transition-all active:scale-[0.98] cursor-pointer"
          >
            <Sparkles size={16} />
            <span>Ask your tutor</span>
          </button>

          {/* Dynamic Notification Bell & Study Plan Reminders Dropdown */}
          <NotificationPopup />

          {/* User Profile Avatar Pill (Triggers Profile Modal) */}
          <div
            onClick={() => setIsProfileOpen(true)}
            className="flex items-center gap-2 bg-white border border-[#E7E1D8] p-1 pr-3 rounded-full shadow-2xs cursor-pointer hover:bg-[#FFF9F2] transition-colors"
            title="View & Edit Profile"
          >
            <div className="w-8 h-8 rounded-full bg-[#20201D] text-white flex items-center justify-center font-bold text-xs">
              {user?.username?.[0]?.toUpperCase() ?? 'A'}
            </div>
            <ChevronRight size={14} className="text-[#969188]" />
          </div>
        </div>
      </motion.div>

      {/* ─── 2. MAIN 2-COLUMN DASHBOARD GRID (CENTRAL LEARNING + RIGHT INSIGHTS PANEL) ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        
        {/* ─── CENTRAL COLUMN (Lg: col-span-8) ─── */}
        <div className="lg:col-span-8 space-y-8">
          
          {/* ASK YOUR TUTOR HERO LEARNING CARD (EDITORIAL BORDERLESS COMPOSITION) */}
          <div className="bg-[#FFF9F2] border border-[#E7E1D8] rounded-3xl p-6 sm:p-8 shadow-2xs relative overflow-hidden space-y-6">
            
            {/* Header Content with Left Desk Lamp & Right Plant Editorial Layout */}
            <div className="relative flex flex-col items-center text-center space-y-3 px-4 sm:px-16 pt-2">
              
              {/* Left Decorative Illustration: Desk Lamp & Books (Borderless & Transparent) */}
              <div className="hidden sm:block absolute left-2 top-0 w-24 sm:w-32 h-24 sm:h-32 pointer-events-none select-none">
                <img src="/assets/illustrations/desk_lamp.png" alt="Desk Lamp" className="w-full h-full object-contain" />
              </div>

              {/* Right Decorative Illustration: Potted Plant (Borderless & Transparent) */}
              <div className="hidden sm:block absolute right-2 top-0 w-24 sm:w-32 h-24 sm:h-32 pointer-events-none select-none">
                <img src="/assets/illustrations/plant.png" alt="Plant" className="w-full h-full object-contain" />
              </div>

              {/* Floating Sparkle Accents */}
              <span className="absolute top-1 left-28 text-[#D99A32] text-xs opacity-70 animate-pulse">✨</span>
              <span className="absolute bottom-1 right-28 text-[#F28A45] text-xs opacity-70 animate-pulse">✨</span>

              <h2 className="text-[24px] sm:text-[28px] leading-[32px] sm:leading-[36px] tracking-[-0.5px] font-bold text-[#20201D] max-w-md">
                What would you like to <span className="text-[#F28A45] font-bold">understand</span> today?
              </h2>

              <p className="text-sm leading-[22px] font-normal text-[#6F6B63] max-w-sm">
                Ask anything. I'll explain it in the way you learn best.
              </p>
            </div>

            {/* Question Input Field (Visually Dominant & High Contrast) */}
            <form onSubmit={(e) => handleQuickAsk(e)} className="relative w-full max-w-2xl mx-auto pt-1 z-10">
              <div className="bg-white border border-[#E7E1D8] rounded-full p-2 flex items-center justify-between gap-3 shadow-2xs focus-within:border-[#F28A45] focus-within:ring-2 focus-within:ring-[#F28A45]/20 transition-all">
                <div className="flex items-center gap-2 flex-1 pl-4">
                  <Sparkles size={16} className="text-[#F28A45] flex-shrink-0" />
                  <input
                    type="text"
                    value={quickPrompt}
                    onChange={(e) => setQuickPrompt(e.target.value)}
                    placeholder="Ask your tutor anything..."
                    className="w-full bg-transparent outline-none text-[#20201D] font-normal text-[15px] leading-[24px] placeholder-[#969188]"
                  />
                </div>
                <button
                  type="submit"
                  disabled={!quickPrompt.trim()}
                  className="w-10 h-10 rounded-full bg-[#F28A45] hover:bg-[#DF7635] text-white flex items-center justify-center shadow-2xs disabled:opacity-40 transition-all cursor-pointer flex-shrink-0"
                  title="Submit prompt"
                >
                  <ArrowRight size={18} className="text-white" />
                </button>
              </div>
            </form>

            {/* Quick Actions Chips */}
            <div className="flex flex-wrap items-center justify-center gap-2 pt-1">
              <motion.button
                whileHover={{ y: -2 }}
                onClick={() => handleQuickAsk(undefined, "Explain the core concept of Machine Learning")}
                className="flex items-center gap-1.5 bg-white hover:bg-[#FFF0E4] border border-[#E7E1D8] hover:border-[#F28A45]/40 text-[#20201D] px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all shadow-2xs cursor-pointer"
              >
                <img src="/assets/illustrations/lightbulb.png" alt="Lightbulb" className="w-4 h-4 object-contain" />
                <span>Explain a concept</span>
              </motion.button>

              <motion.button
                whileHover={{ y: -2 }}
                onClick={() => handleQuickAsk(undefined, "Can you give me a real-world example of Linear Regression")}
                className="flex items-center gap-1.5 bg-white hover:bg-[#E3F0E5] border border-[#E7E1D8] hover:border-[#4F8A68]/40 text-[#20201D] px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all shadow-2xs cursor-pointer"
              >
                <img src="/assets/illustrations/cs_code.png" alt="Code" className="w-4 h-4 object-contain" />
                <span>Give me an example</span>
              </motion.button>

              <motion.button
                whileHover={{ y: -2 }}
                onClick={() => handleQuickAsk(undefined, "Quiz me with 3 questions on Neural Networks")}
                className="flex items-center gap-1.5 bg-white hover:bg-[#F0ECF7] border border-[#E7E1D8] hover:border-[#A99BCB]/40 text-[#20201D] px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all shadow-2xs cursor-pointer"
              >
                <img src="/assets/illustrations/checklist_clipboard.png" alt="Quiz" className="w-4 h-4 object-contain" />
                <span>Quiz me</span>
              </motion.button>

              <motion.button
                whileHover={{ y: -2 }}
                onClick={() => handleQuickAsk(undefined, "Help me study and summarize my uploaded document")}
                className="flex items-center gap-1.5 bg-white hover:bg-[#FFF0E4] border border-[#E7E1D8] hover:border-[#F28A45]/40 text-[#20201D] px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all shadow-2xs cursor-pointer"
              >
                <img src="/assets/illustrations/open_book.png" alt="Study" className="w-4 h-4 object-contain" />
                <span>Help me study</span>
              </motion.button>
            </div>
          </div>

          {/* CONTINUE LEARNING SECTION */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-[20px] leading-[28px] tracking-[-0.2px] font-bold text-[#20201D]">Continue learning</h2>
              <button
                onClick={() => navigate('/chat')}
                className="text-xs font-bold text-[#F28A45] hover:text-[#DF7635] flex items-center gap-1 transition-colors cursor-pointer"
              >
                <span>View all</span> <ArrowRight size={13} />
              </button>
            </div>

            <div className="bg-white border border-[#E7E1D8] rounded-3xl p-6 shadow-2xs flex flex-col md:flex-row items-center justify-between gap-6 hover:border-[#F28A45]/40 transition-all relative overflow-hidden">
              
              {/* Left Concept Graphic Thumbnail */}
              <div className="w-full md:w-36 h-28 rounded-2xl bg-[#4F8A68] border border-[#35654B]/30 flex items-center justify-center text-white flex-shrink-0 relative overflow-hidden p-3 shadow-2xs">
                <div className="absolute inset-0 bg-gradient-to-br from-[#4F8A68] to-[#35654B] opacity-90" />
                <div className="relative z-10 flex flex-col items-center justify-center text-center">
                  <Brain size={32} className="text-[#E3F0E5] mb-1" />
                  <span className="text-[10px] font-black uppercase tracking-wider text-[#E3F0E5]">ML Concept</span>
                </div>
                <span className="absolute bottom-2 right-2 bg-black/40 backdrop-blur-xs text-white text-[10px] font-extrabold px-2 py-0.5 rounded-md">
                  68%
                </span>
              </div>

              {/* Middle Course Information */}
              <div className="space-y-2 flex-1 min-w-0 z-10">
                <p className="text-[11px] font-bold text-[#6F6B63]">Introduction to Machine Learning</p>
                <h3 className="text-xl font-black text-[#20201D] truncate">Supervised Learning</h3>
                <p className="text-xs text-[#969188] font-bold">Linear Regression</p>
                
                {/* Progress Bar & Percentage */}
                <div className="flex items-center gap-3 pt-1">
                  <div className="flex-1 bg-[#F4EFE7] rounded-full h-1.5 overflow-hidden">
                    <div className="bg-[#F28A45] h-full rounded-full w-[68%]" />
                  </div>
                  <span className="text-xs font-black text-[#20201D]">68%</span>
                </div>

                <p className="text-xs text-[#6F6B63] font-semibold leading-relaxed line-clamp-1 pt-1">
                  You were learning how a model learns the relationship between inputs and outputs.
                </p>

                <div className="pt-2">
                  <button
                    onClick={() => navigate(lastSession ? `/chat/${lastSession.id}` : '/chat', { state: lastSession ? {} : { initialPrompt: 'Continue Supervised Learning lesson on Linear Regression' } })}
                    className="btn-primary text-xs font-black py-2.5 px-5 rounded-2xl flex items-center gap-2 shadow-2xs cursor-pointer whitespace-nowrap"
                  >
                    <span>Continue learning</span>
                    <ArrowRight size={14} />
                  </button>
                </div>
              </div>

              {/* Right Friendly AI Robot Working on Laptop (Borderless Illustration) */}
              <div className="w-28 sm:w-36 h-28 sm:h-36 flex-shrink-0 relative select-none pointer-events-none">
                <img src="/assets/illustrations/ai_tutor_laptop.png" alt="AI Robot Laptop" className="w-full h-full object-contain filter drop-shadow-xs" />
              </div>

              {/* Top Right Context Menu (...) */}
              <button className="absolute top-5 right-5 text-[#969188] hover:text-[#20201D] transition-colors p-1 cursor-pointer">
                <MoreHorizontal size={18} />
              </button>

            </div>
          </div>

          {/* YOUR SUBJECTS SECTION (DYNAMIC SINGLE SOURCE OF TRUTH) */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-black text-[#20201D]">Your subjects</h2>
              <button
                onClick={() => navigate('/subjects')}
                className="text-xs font-black text-[#F28A45] hover:text-[#DF7635] flex items-center gap-1 transition-colors cursor-pointer"
              >
                <span>View all</span> <ChevronRight size={14} />
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {['6', '3', '1'].map((subjectId) => {
                const subject = getSubject(subjectId)
                if (!subject) return null
                const progressVal = getSubjectProgress(subjectId)
                const subjectTopics = getTopics(subjectId)
                const completedCount = subjectTopics.filter((t) => t.status === 'COMPLETED').length
                const currentTopic = getCurrentTopic(subjectId)

                return (
                  <div
                    key={subject.id}
                    onClick={() => navigate(`/subjects/${subject.id}`)}
                    className="bg-white border border-[#E7E1D8] hover:border-[#F28A45]/50 rounded-3xl p-5 shadow-2xs transition-all cursor-pointer group flex flex-col justify-between space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2.5">
                        <div className="w-8 h-8 rounded-xl bg-[#FFF0E4] border border-[#F28A45]/30 flex items-center justify-center p-1.5">
                          <img src={subject.illustration} alt={subject.name} className="w-full h-full object-contain" />
                        </div>
                        <h4 className="text-xs font-black text-[#20201D] group-hover:text-[#F28A45] transition-colors">
                          {subject.name}
                        </h4>
                      </div>
                    </div>

                    {currentTopic && (
                      <p className="text-[11px] font-semibold text-[#6F6B63] truncate">
                        Next: <span className="text-[#20201D] font-bold">{currentTopic.title}</span>
                      </p>
                    )}

                    <div className="space-y-1.5 pt-1">
                      <div className="w-full bg-[#F4EFE7] rounded-full h-1.5 overflow-hidden">
                        <div
                          className="bg-[#F28A45] h-full rounded-full transition-all duration-300"
                          style={{ width: `${progressVal}%` }}
                        />
                      </div>
                      <div className="flex items-center justify-between text-[11px] font-bold text-[#969188]">
                        <span>{completedCount} / {subjectTopics.length} topics completed</span>
                        <span className="text-[#20201D] font-black">{progressVal}%</span>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* TUTOR REMEMBERS SECTION (EDITORIAL BORDERLESS PLANT ILLUSTRATION) */}
          <div className="bg-[#FFF9F2] border border-[#F28A45]/30 rounded-3xl p-5 shadow-2xs flex flex-col sm:flex-row items-center justify-between gap-4 relative overflow-hidden">
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 flex-shrink-0 select-none">
                <img src="/assets/illustrations/plant.png" alt="Plant" className="w-full h-full object-contain filter drop-shadow-xs" />
              </div>
              <div>
                <h4 className="text-xs font-black text-[#20201D]">Your tutor remembers</h4>
                <p className="text-xs text-[#6F6B63] font-semibold leading-relaxed mt-0.5">
                  You already understand linear regression well, but classification is still a bit unclear. Let's strengthen it! 💪
                </p>
              </div>
            </div>
            <button
              onClick={() => navigate('/chat', { state: { initialPrompt: 'Review Classification concepts and reinforce understanding.' } })}
              className="btn-orange-outline text-xs whitespace-nowrap self-stretch sm:self-auto cursor-pointer"
            >
              Review Classification &rarr;
            </button>
          </div>

        </div>

        {/* ─── RIGHT INSIGHTS PANEL (Lg: col-span-4, ~300-330px) ─── */}
        <div className="lg:col-span-4 space-y-6">
          
          {/* 1. YOUR STUDY GOAL CARD */}
          <div className="bg-white border border-[#E7E1D8] rounded-3xl p-6 shadow-2xs space-y-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <img src="/assets/illustrations/target_arrow.png" alt="Target Goal" className="w-5 h-5 object-contain" />
                <h3 className="font-extrabold text-[#20201D] text-xs">Your study goal</h3>
              </div>
              <button onClick={() => navigate('/study-plan')} className="text-xs font-bold text-[#4F8A68] hover:underline cursor-pointer">
                Change
              </button>
            </div>

            <div className="space-y-2">
              <p className="text-xs font-black text-[#20201D]">Study 5 days this week</p>
              
              {/* 7 Day Indicators M T W T F S S */}
              <div className="flex items-center justify-between pt-1">
                {['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((day, idx) => (
                  <div key={idx} className="flex flex-col items-center gap-1">
                    <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-black ${
                      idx < 5 ? 'bg-[#4F8A68] text-white' : 'border border-[#E7E1D8] text-[#969188]'
                    }`}>
                      {idx < 5 ? '✓' : ''}
                    </div>
                    <span className="text-[10px] font-extrabold text-[#969188]">{day}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Weekly Goal Progress bar */}
            <div className="space-y-1.5 pt-2">
              <div className="flex items-center justify-between text-xs font-bold">
                <span className="text-[#6F6B63]">Progress</span>
                <span className="text-[#20201D] font-black">80%</span>
              </div>
              <div className="w-full bg-[#F4EFE7] rounded-full h-2 overflow-hidden">
                <motion.div
                  className="bg-[#4F8A68] h-full rounded-full"
                  animate={{ width: `80%` }}
                  transition={{ duration: 0.4 }}
                />
              </div>
            </div>
          </div>

          {/* 2. TUTOR SUGGESTS CARD (MATCHING REFERENCE IMAGE 3) */}
          <div className="bg-[#FFF9F2] border border-[#F28A45]/30 rounded-3xl p-6 shadow-2xs space-y-4 relative overflow-hidden">
            <div className="flex items-center gap-2">
              <img src="/assets/illustrations/lightbulb.png" alt="Lightbulb" className="w-5 h-5 object-contain" />
              <h3 className="font-extrabold text-[#20201D] text-xs">Tutor suggests</h3>
            </div>

            <div className="flex items-start justify-between gap-3">
              <p className="text-xs text-[#6F6B63] leading-relaxed font-semibold flex-1">
                Review gradient descent before moving on to neural networks. It will strengthen your foundation.
              </p>
              
              {/* Friendly AI Robot Reading Book (Borderless Graphic) */}
              <div className="w-20 h-20 flex-shrink-0 relative select-none pointer-events-none -mt-4">
                <img src="/assets/illustrations/ai_tutor_thinking.png" alt="AI Reading" className="w-full h-full object-contain filter drop-shadow-xs" />
                <span className="absolute top-0 right-0 text-[#F28A45] text-[10px] animate-pulse">✨</span>
              </div>
            </div>

            <button
              onClick={() => navigate('/chat', { state: { initialPrompt: 'Review Gradient Descent before moving on to neural networks.' } })}
              className="btn-orange-outline w-full text-xs font-bold py-2.5 px-4 rounded-2xl flex items-center justify-center gap-2 shadow-2xs cursor-pointer"
            >
              <span>Start suggested lesson &rarr;</span>
            </button>
          </div>

          {/* 3. YOUR LEARNING AT A GLANCE CARD (WITH DONUT CHART GRAPHIC) */}
          <div className="bg-white border border-[#E7E1D8] rounded-3xl p-6 shadow-2xs space-y-4">
            <div className="flex items-center gap-2 border-b border-[#E7E1D8] pb-3">
              <LineChart size={16} className="text-[#F28A45]" />
              <h3 className="font-extrabold text-[#20201D] text-xs">Your learning at a glance</h3>
            </div>

            <div className="flex items-center justify-between gap-4">
              <div className="space-y-3 text-xs font-semibold flex-1">
                <div className="flex items-center justify-between">
                  <span className="text-[#6F6B63]">Sessions completed</span>
                  <span className="text-[#4F8A68] font-black">{progress?.total_sessions ?? 0}</span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-[#6F6B63]">Active subjects</span>
                  <span className="text-[#20201D] font-black">{getSubject('6')?.isEnrolled ? 3 : 1}</span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-[#6F6B63]">Topics mastered</span>
                  <span className="text-[#20201D] font-black">{progress?.topics_studied ?? 0}</span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-[#6F6B63]">Current streak</span>
                  <span className="text-[#F28A45] font-black">{progress?.streak_days ?? 0} {progress?.streak_days === 1 ? 'day' : 'days'}</span>
                </div>
              </div>

              {/* Analytics Donut Graphic */}
              <div className="w-20 h-20 flex-shrink-0 select-none pointer-events-none">
                <img src="/assets/illustrations/donut_80_percent.png" alt="Donut Chart" className="w-full h-full object-contain filter drop-shadow-xs" />
              </div>
            </div>
          </div>

        </div>

      </div>

    </div>
  )
}

