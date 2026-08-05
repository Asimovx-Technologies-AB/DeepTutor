import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Brain,
  GraduationCap,
  Sparkles,
  Zap,
  BookOpen,
  Calendar,
  BarChart3,
  ArrowRight,
  CheckCircle2,
  LayoutDashboard,
  ShieldCheck,
  Star,
  Layers,
  ChevronRight
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'

const PRODUCT_SHOWCASES = [
  {
    id: 'dashboard',
    title: 'AI Study Dashboard',
    subtitle: 'All your study tools, stats, and AI tutor sessions in one clean, unified workspace.',
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
    subtitle: 'Upload your document & target exam completion date to generate a personalized day-by-day study schedule.',
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
    <div className="min-h-screen bg-[#f8fafc] text-slate-900 font-sans selection:bg-indigo-500 selection:text-white relative">
      {/* ─── Soft Subtle Top Gradient Flare ─── */}
      <div className="absolute top-0 inset-x-0 h-96 bg-gradient-to-b from-indigo-50/80 via-indigo-50/20 to-transparent pointer-events-none" />

      {/* ─── NAVBAR (Easlo Clean Style) ─── */}
      <header className="sticky top-0 z-40 backdrop-blur-md bg-white/90 border-b border-slate-200/80">
        <div className="max-w-6xl mx-auto px-6 h-20 flex items-center justify-between">
          <div
            className="flex items-center gap-3 cursor-pointer group"
            onClick={() => navigate('/')}
          >
            <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-600 flex items-center justify-center shadow-md shadow-indigo-500/20 group-hover:scale-105 transition-transform">
              <GraduationCap size={22} className="text-white" />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-black text-xl text-slate-900 tracking-tight">DeepTutor</span>
                <span className="text-[10px] font-black uppercase tracking-wider bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded-md border border-indigo-100">
                  AI
                </span>
              </div>
              <p className="text-xs text-slate-400 font-medium">GraphRAG Study Engine</p>
            </div>
          </div>

          <nav className="hidden md:flex items-center gap-8 text-sm font-extrabold text-slate-600">
            <a href="#showcase" className="hover:text-indigo-600 transition-colors">Previews</a>
            <a href="#features" className="hover:text-indigo-600 transition-colors">Features</a>
            <a href="#how-it-works" className="hover:text-indigo-600 transition-colors">How It Works</a>
          </nav>

          <div className="flex items-center gap-4">
            {isAuthenticated ? (
              <button
                onClick={() => navigate('/dashboard')}
                className="btn-primary py-2.5 px-6 text-sm font-bold flex items-center gap-2 shadow-md shadow-indigo-500/20 hover:scale-105"
              >
                Go to Dashboard <ArrowRight size={16} />
              </button>
            ) : (
              <>
                <button
                  onClick={() => navigate('/login')}
                  className="text-sm font-extrabold text-slate-600 hover:text-slate-900 px-4 py-2 rounded-xl transition-colors"
                >
                  Sign In
                </button>
                <button
                  onClick={() => navigate('/register')}
                  className="btn-primary py-2.5 px-6 text-sm font-bold shadow-md shadow-indigo-500/20 hover:scale-105"
                >
                  Get Started Free
                </button>
              </>
            )}
          </div>
        </div>
      </header>

      {/* ─── HERO SECTION (Easlo Minimalist Style) ─── */}
      <section className="pt-20 pb-20 px-6 max-w-5xl mx-auto text-center space-y-7 relative">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-indigo-50 border border-indigo-100 text-indigo-600 text-xs font-extrabold tracking-wide shadow-sm"
        >
          <Sparkles size={14} className="text-indigo-500" />
          Simplifying Study & Learning with AI
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="text-5xl md:text-6xl lg:text-7xl font-black tracking-tight text-slate-900 leading-[1.1]"
        >
          Your All-in-One Personal{' '}
          <span className="bg-gradient-to-r from-indigo-600 via-violet-600 to-indigo-800 bg-clip-text text-transparent">
            AI Study System
          </span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="text-lg md:text-xl text-slate-600 font-medium leading-relaxed max-w-3xl mx-auto"
        >
          DeepTutor helps you turn textbook PDFs into day-by-day study roadmaps, AI tutoring sessions, interactive flashcards, and real-time mastery tracking.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="flex flex-wrap items-center justify-center gap-4 pt-3"
        >
          <button
            onClick={() => navigate(isAuthenticated ? '/dashboard' : '/register')}
            className="btn-primary py-4 px-9 text-base font-extrabold flex items-center gap-3 shadow-lg shadow-indigo-500/25 hover:scale-105"
          >
            <Brain size={20} />
            {isAuthenticated ? 'Open Dashboard' : 'Get Started Free'}
          </button>

          <a
            href="#showcase"
            className="btn-ghost py-4 px-8 text-base font-bold text-slate-700 bg-white border-slate-200 hover:bg-slate-50 shadow-sm"
          >
            View App Previews
          </a>
        </motion.div>

        {/* Hero Browser Mockup Frame (Displaying user's actual Dashboard screenshot) */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="mt-14 relative rounded-3xl p-3 bg-white border border-slate-200/90 shadow-2xl shadow-slate-300/50 group hover:scale-[1.006] transition-transform"
        >
          {/* Browser dots header */}
          <div className="flex items-center gap-2 px-4 py-2 border-b border-slate-100 bg-slate-50/80 rounded-t-2xl">
            <div className="w-3 h-3 rounded-full bg-rose-400/80" />
            <div className="w-3 h-3 rounded-full bg-amber-400/80" />
            <div className="w-3 h-3 rounded-full bg-emerald-400/80" />
            <span className="text-xs font-semibold text-slate-400 ml-2">DeepTutor AI Workspace — Dashboard</span>
          </div>

          <div className="rounded-b-2xl overflow-hidden bg-slate-50">
            <img
              src="/images/dashboard_screenshot.png"
              alt="DeepTutor AI Dashboard"
              className="w-full h-auto object-cover rounded-b-2xl"
            />
          </div>
        </motion.div>
      </section>

      {/* ─── APP SHOWCASE SECTION (Minimal Easlo Cards) ─── */}
      <section id="showcase" className="py-20 px-6 max-w-6xl mx-auto border-t border-slate-200/80">
        <div className="text-center max-w-2xl mx-auto space-y-3 mb-12">
          <span className="text-xs font-extrabold text-indigo-600 uppercase tracking-widest bg-indigo-50 border border-indigo-100 px-3 py-1 rounded-full">
            Application Screenshots
          </span>
          <h2 className="text-4xl font-black text-slate-900">Explore the Platform</h2>
          <p className="text-slate-600 text-base font-medium">
            Real interface previews of your AI Study Dashboard, Day-by-Day Roadmaps, and Progress Analytics.
          </p>
        </div>

        {/* Tab Buttons */}
        <div className="flex flex-wrap items-center justify-center gap-3 mb-10">
          {PRODUCT_SHOWCASES.map((item) => {
            const Icon = item.icon
            const isActive = activeTab === item.id
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`flex items-center gap-2.5 px-6 py-3.5 rounded-2xl text-sm font-extrabold transition-all ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/20 scale-105'
                    : 'bg-white text-slate-600 border border-slate-200 hover:text-slate-900 hover:bg-slate-50'
                }`}
              >
                <Icon size={18} />
                <span>{item.title}</span>
              </button>
            )
          })}
        </div>

        {/* Active Showcase Card */}
        <div className="bg-white rounded-3xl p-8 border border-slate-200/90 shadow-xl space-y-8">
          <div className="max-w-3xl space-y-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-black text-indigo-600 uppercase tracking-wider bg-indigo-50 border border-indigo-100 px-3 py-1 rounded-lg">
                {activeShowcase.badge}
              </span>
            </div>
            <h3 className="text-3xl font-black text-slate-900">{activeShowcase.title}</h3>
            <p className="text-slate-600 text-base font-medium leading-relaxed">{activeShowcase.subtitle}</p>

            <div className="grid md:grid-cols-3 gap-3 pt-2">
              {activeShowcase.highlights.map((h, i) => (
                <div key={i} className="flex items-start gap-2 text-xs font-bold text-slate-700 bg-slate-50 p-3 rounded-xl border border-slate-100">
                  <CheckCircle2 size={16} className="text-indigo-600 flex-shrink-0 mt-0.5" />
                  <span>{h}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Screenshot Display Frame */}
          <div className="rounded-2xl overflow-hidden border border-slate-200 shadow-lg bg-slate-50 group">
            <img
              src={activeShowcase.image}
              alt={activeShowcase.title}
              className="w-full h-auto object-cover group-hover:scale-[1.01] transition-transform duration-500"
            />
          </div>
        </div>
      </section>

      {/* ─── HOW IT WORKS (Minimal Cards) ─── */}
      <section id="how-it-works" className="py-20 px-6 max-w-6xl mx-auto border-t border-slate-200/80">
        <div className="text-center max-w-2xl mx-auto space-y-3 mb-16">
          <span className="text-xs font-extrabold text-indigo-600 uppercase tracking-widest bg-indigo-50 border border-indigo-100 px-3 py-1 rounded-full">
            Simple 3-Step Process
          </span>
          <h2 className="text-4xl font-black text-slate-900">How It Works</h2>
        </div>

        <div className="grid md:grid-cols-3 gap-8">
          <div className="bg-white p-8 rounded-3xl border border-slate-200/80 shadow-sm hover:shadow-md transition-all space-y-4">
            <div className="w-12 h-12 rounded-2xl bg-indigo-50 border border-indigo-100 text-indigo-600 font-black text-lg flex items-center justify-center">
              01
            </div>
            <h3 className="text-xl font-extrabold text-slate-900">Upload PDF Materials</h3>
            <p className="text-slate-600 text-sm font-medium leading-relaxed">
              Upload textbook chapters or course materials into DeepTutor to start indexing.
            </p>
          </div>

          <div className="bg-white p-8 rounded-3xl border border-slate-200/80 shadow-sm hover:shadow-md transition-all space-y-4">
            <div className="w-12 h-12 rounded-2xl bg-violet-50 border border-violet-100 text-violet-600 font-black text-lg flex items-center justify-center">
              02
            </div>
            <h3 className="text-xl font-extrabold text-slate-900">Generate Study Roadmap</h3>
            <p className="text-slate-600 text-sm font-medium leading-relaxed">
              Set your target finish date to automatically generate a day-by-day study schedule.
            </p>
          </div>

          <div className="bg-white p-8 rounded-3xl border border-slate-200/80 shadow-sm hover:shadow-md transition-all space-y-4">
            <div className="w-12 h-12 rounded-2xl bg-emerald-50 border border-emerald-100 text-emerald-600 font-black text-lg flex items-center justify-center">
              03
            </div>
            <h3 className="text-xl font-extrabold text-slate-900">Study & Track Mastery</h3>
            <p className="text-slate-600 text-sm font-medium leading-relaxed">
              Ask AI tutor questions, review flashcards, take quizzes, and track your activity streak.
            </p>
          </div>
        </div>
      </section>

      {/* ─── MINIMAL FOOTER ─── */}
      <footer className="py-16 border-t border-slate-200/80 bg-white">
        <div className="max-w-6xl mx-auto px-6 text-center space-y-6">
          <div className="flex items-center justify-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-600 flex items-center justify-center shadow-md">
              <GraduationCap size={22} className="text-white" />
            </div>
            <span className="font-black text-2xl text-slate-900">DeepTutor AI</span>
          </div>

          <p className="text-slate-500 text-sm max-w-md mx-auto font-medium">
            Personalized AI study roadmaps, GraphRAG tutoring, and learning analytics.
          </p>

          <button
            onClick={() => navigate(isAuthenticated ? '/dashboard' : '/register')}
            className="btn-primary py-3.5 px-8 text-sm font-extrabold shadow-md hover:scale-105"
          >
            Start Learning Free Today
          </button>

          <p className="text-xs text-slate-400 font-semibold pt-6">
            © {new Date().getFullYear()} DeepTutor AI. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  )
}
