import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Brain,
  GraduationCap,
  Sparkles,
  Calendar,
  BarChart3,
  ArrowRight,
  CheckCircle2,
  LayoutDashboard
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'

const PRODUCT_SHOWCASES = [
  {
    id: 'dashboard',
    title: 'AI Study Dashboard',
    subtitle: 'All your study tools, AI tutor sessions, and daily checklists in one clean, unified workspace.',
    badge: 'Central Workspace',
    icon: LayoutDashboard,
    image: '/images/dashboard_screenshot.png',
    highlights: [
      'Instant Ask AI prompt bar for quick concept explanations',
      'Interactive Daily Study Goal checklist with completion tracking',
      'Quick-access cards for Recent Sessions, Flashcards, and Quizzes'
    ]
  },
  {
    id: 'roadmap',
    title: 'AI Study Roadmap & Schedule',
    subtitle: 'Upload your document & target completion date to generate a personalized day-by-day study schedule.',
    badge: 'Adaptive Planning',
    icon: Calendar,
    image: '/images/study_roadmap_screenshot.png',
    highlights: [
      'Day-by-day topic breakdown with estimated study hours',
      'Actionable daily tasks (e.g. Read chapter, take 5-question AI Quiz)',
      'Key concepts tags & progress completion indicator'
    ]
  },
  {
    id: 'analytics',
    title: 'Learning Analytics & Progress',
    subtitle: 'Track your real-time learning journey, quiz accuracy, activity streak, and topic mastery.',
    badge: 'Real-time Metrics',
    icon: BarChart3,
    image: '/images/progress_analytics_screenshot.png',
    highlights: [
      'Weekly learning activity curve & average quiz scores',
      'GitHub-style 5-week learning activity heat calendar',
      'Topic mastery level badges from Beginner to Expert'
    ]
  }
]

export default function LandingPage() {
  const navigate = useNavigate()
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const [activeTab, setActiveTab] = useState('dashboard')

  const activeShowcase = PRODUCT_SHOWCASES.find((s) => s.id === activeTab) || PRODUCT_SHOWCASES[0]

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 font-sans relative">
      {/* ─── HEADER ─── */}
      <header className="sticky top-0 z-40 bg-white/90 backdrop-blur-md border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 sm:h-20 flex items-center justify-between">
          <div
            className="flex items-center gap-2.5 sm:gap-3 cursor-pointer group"
            onClick={() => navigate('/')}
          >
            <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-2xl bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600 shadow-xs transition-transform active:scale-95 flex-shrink-0">
              <GraduationCap className="w-5 h-5" />
            </div>
            <div className="flex items-center gap-2">
              <span className="font-black text-lg sm:text-xl text-slate-800 tracking-tight">IndieTutor</span>
              <span className="text-[10px] font-black uppercase tracking-wider bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded-full border border-indigo-200">
                AI
              </span>
            </div>
          </div>

          <nav className="hidden md:flex items-center gap-8 text-sm font-bold text-slate-500">
            <a href="#showcase" className="hover:text-indigo-600 transition-colors">Previews</a>
            <a href="#features" className="hover:text-indigo-600 transition-colors">Features</a>
            <a href="#how-it-works" className="hover:text-indigo-600 transition-colors">How It Works</a>
          </nav>

          <div className="flex items-center gap-2 sm:gap-3">
            {isAuthenticated ? (
              <button
                onClick={() => navigate('/dashboard')}
                className="btn-primary py-2.5 px-5 text-xs sm:text-sm font-black flex items-center gap-2 shadow-md shadow-indigo-600/25 cursor-pointer whitespace-nowrap"
              >
                <span>Dashboard</span> <ArrowRight className="w-4 h-4" />
              </button>
            ) : (
              <>
                <button
                  onClick={() => navigate('/login')}
                  className="text-xs sm:text-sm font-bold text-slate-600 hover:text-slate-900 px-3 sm:px-4 py-2 rounded-xl transition-colors whitespace-nowrap cursor-pointer"
                >
                  Sign In
                </button>
                <button
                  onClick={() => navigate('/register')}
                  className="btn-primary py-2 sm:py-2.5 px-4 sm:px-6 text-xs sm:text-sm font-black shadow-md shadow-indigo-600/25 cursor-pointer whitespace-nowrap"
                >
                  Get Started
                </button>
              </>
            )}
          </div>
        </div>
      </header>

      {/* ─── HERO SECTION ─── */}
      <section className="pt-20 pb-16 px-6 max-w-5xl mx-auto text-center space-y-7">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-600 text-xs font-black tracking-wide shadow-xs">
          <Sparkles size={14} className="text-indigo-600" />
          AI Exam-Prep Engine
        </div>

        <h1 className="text-5xl md:text-6xl lg:text-7xl font-black tracking-tight text-slate-800 leading-[1.1]">
          Your learning. <br />
          <span className="text-indigo-600">Your pace. Your tutor.</span>
        </h1>

        <p className="text-lg md:text-xl text-slate-500 font-medium leading-relaxed max-w-2xl mx-auto">
          IndieTutor helps you understand difficult topics, practice what you've learned, and build your own path to exam mastery.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-4 pt-2">
          <button
            onClick={() => navigate(isAuthenticated ? '/dashboard' : '/register')}
            className="btn-primary py-4 px-8 text-base font-black flex items-center gap-3 shadow-lg shadow-indigo-600/30 cursor-pointer"
          >
            <Brain size={20} />
            {isAuthenticated ? 'Open Dashboard' : 'Start Learning'}
          </button>

          <a
            href="#showcase"
            className="bg-white text-slate-800 hover:bg-slate-50 border border-slate-200 py-4 px-8 rounded-2xl text-base font-black transition-all active:scale-95 shadow-xs"
          >
            Explore How It Works
          </a>
        </div>

        {/* Hero Image Mockup (Dashboard Screenshot) */}
        <div className="mt-14 relative rounded-3xl p-3 bg-white border border-slate-200 shadow-xl">
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-slate-200 bg-slate-50 rounded-t-2xl">
            <div className="w-3 h-3 rounded-full bg-slate-300" />
            <div className="w-3 h-3 rounded-full bg-slate-300" />
            <div className="w-3 h-3 rounded-full bg-slate-300" />
            <span className="text-xs font-bold text-slate-500 ml-2">IndieTutor — Dashboard View</span>
          </div>

          <div className="rounded-b-2xl overflow-hidden bg-slate-50">
            <img
              src="/images/dashboard_screenshot.png"
              alt="IndieTutor Dashboard"
              className="w-full h-auto object-cover rounded-b-2xl"
            />
          </div>
        </div>
      </section>

      {/* ─── APP SHOWCASE SECTION ─── */}
      <section id="showcase" className="py-20 px-6 max-w-5xl mx-auto border-t border-slate-200">
        <div className="text-center max-w-2xl mx-auto space-y-3 mb-10">
          <span className="text-xs font-black text-indigo-600 uppercase tracking-wider bg-indigo-50 border border-indigo-200 px-3.5 py-1 rounded-full">
            Application Screenshots
          </span>
          <h2 className="text-4xl font-black text-slate-800">Explore How It Works</h2>
          <p className="text-slate-500 text-base font-medium">
            Screenshots from your AI Study Dashboard, Day-by-Day Roadmaps, and Progress Analytics.
          </p>
        </div>

        {/* Interactive Tab Selectors */}
        <div className="flex flex-wrap items-center justify-center gap-3 mb-10">
          {PRODUCT_SHOWCASES.map((item) => {
            const Icon = item.icon
            const isActive = activeTab === item.id
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`flex items-center gap-2.5 px-6 py-3 rounded-2xl text-xs font-black transition-all active:scale-95 cursor-pointer ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                    : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50 hover:text-slate-900 shadow-xs'
                }`}
              >
                <Icon size={16} />
                <span>{item.title}</span>
              </button>
            )
          })}
        </div>

        {/* Active Showcase Frame */}
        <div className="bg-white rounded-3xl p-6 md:p-8 border border-slate-200 shadow-sm space-y-6">
          <div className="max-w-3xl space-y-3">
            <span className="text-xs font-black text-indigo-600 uppercase tracking-wider bg-indigo-50 border border-indigo-200 px-3 py-1 rounded-full">
              {activeShowcase.badge}
            </span>
            <h3 className="text-3xl font-black text-slate-800">{activeShowcase.title}</h3>
            <p className="text-slate-500 text-base font-medium leading-relaxed">{activeShowcase.subtitle}</p>

            <div className="grid md:grid-cols-3 gap-3 pt-2">
              {activeShowcase.highlights.map((h, i) => (
                <div key={i} className="flex items-start gap-2.5 text-xs font-bold text-slate-800 bg-slate-50 p-3 rounded-2xl border border-slate-200">
                  <CheckCircle2 size={16} className="text-emerald-500 flex-shrink-0 mt-0.5" />
                  <span>{h}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl overflow-hidden border border-slate-200 bg-slate-50">
            <img
              src={activeShowcase.image}
              alt={activeShowcase.title}
              className="w-full h-auto object-cover rounded-2xl"
            />
          </div>
        </div>
      </section>

      {/* ─── FOOTER ─── */}
      <footer className="py-16 border-t border-slate-200 bg-white">
        <div className="max-w-5xl mx-auto px-6 text-center space-y-6">
          <div className="flex items-center justify-center gap-3">
            <div className="w-9 h-9 rounded-2xl bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600 shadow-xs">
              <GraduationCap size={20} />
            </div>
            <span className="font-black text-2xl text-slate-800">IndieTutor</span>
          </div>

          <p className="text-slate-500 text-sm max-w-md mx-auto font-medium">
            Personalized AI study roadmaps, GraphRAG tutoring, and learning analytics.
          </p>

          <button
            onClick={() => navigate(isAuthenticated ? '/dashboard' : '/register')}
            className="btn-primary py-3.5 px-8 text-sm font-black shadow-md shadow-indigo-600/25 cursor-pointer"
          >
            Start Learning
          </button>

          <p className="text-xs text-slate-400 font-bold pt-6">
            © {new Date().getFullYear()} IndieTutor. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  )
}
