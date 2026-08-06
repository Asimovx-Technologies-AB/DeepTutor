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
    <div className="min-h-screen bg-[#ffffff] text-[#111111] font-sans selection:bg-[#111111] selection:text-white relative">
      {/* ─── EASLO MINIMAL HEADER ─── */}
      <header className="sticky top-0 z-40 bg-white/90 backdrop-blur-md border-b border-[#e5e7eb]">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 sm:h-20 flex items-center justify-between">
          <div
            className="flex items-center gap-2 sm:gap-3 cursor-pointer group"
            onClick={() => navigate('/')}
          >
            <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-xl sm:rounded-2xl bg-[#111111] flex items-center justify-center text-white shadow-sm transition-transform active:scale-95 flex-shrink-0">
              <GraduationCap className="w-4 h-4 sm:w-5 sm:h-5" />
            </div>
            <div className="flex items-center gap-1.5 sm:gap-2">
              <span className="font-black text-base sm:text-xl text-[#111111] tracking-tight">DeepTutor</span>
              <span className="text-[9px] sm:text-[10px] font-extrabold uppercase tracking-wider bg-[#f4f4f5] text-[#18181b] px-1.5 sm:px-2 py-0.5 rounded-full border border-[#e4e4e7]">
                AI
              </span>
            </div>
          </div>

          <nav className="hidden md:flex items-center gap-8 text-sm font-semibold text-[#52525b]">
            <a href="#showcase" className="hover:text-[#111111] transition-colors">Previews</a>
            <a href="#features" className="hover:text-[#111111] transition-colors">Features</a>
            <a href="#how-it-works" className="hover:text-[#111111] transition-colors">How It Works</a>
          </nav>

          <div className="flex items-center gap-2 sm:gap-3">
            {isAuthenticated ? (
              <button
                onClick={() => navigate('/dashboard')}
                className="bg-[#111111] text-white hover:bg-[#27272a] py-2 sm:py-2.5 px-4 sm:px-6 rounded-full text-xs sm:text-sm font-bold flex items-center gap-1.5 sm:gap-2 transition-all active:scale-95 whitespace-nowrap"
              >
                <span>Dashboard</span> <ArrowRight className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
              </button>
            ) : (
              <>
                <button
                  onClick={() => navigate('/login')}
                  className="text-xs sm:text-sm font-bold text-[#52525b] hover:text-[#111111] px-2.5 sm:px-4 py-1.5 sm:py-2 rounded-full transition-colors whitespace-nowrap"
                >
                  Sign In
                </button>
                <button
                  onClick={() => navigate('/register')}
                  className="bg-[#111111] text-white hover:bg-[#27272a] py-1.5 sm:py-2.5 px-3.5 sm:px-6 rounded-full text-xs sm:text-sm font-bold shadow-sm transition-all active:scale-95 whitespace-nowrap"
                >
                  Get Started
                </button>
              </>
            )}
          </div>
        </div>
      </header>

      {/* ─── HERO SECTION (Easlo Tone) ─── */}
      <section className="pt-20 pb-16 px-6 max-w-5xl mx-auto text-center space-y-7">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-[#f4f4f5] border border-[#e4e4e7] text-[#18181b] text-xs font-semibold tracking-wide">
          <Sparkles size={14} className="text-[#18181b]" />
          Simplified Learning Engine
        </div>

        <h1 className="text-5xl md:text-6xl lg:text-7xl font-black tracking-tight text-[#111111] leading-[1.1]">
          Your Personal <br />
          <span className="text-[#111111]">AI Study System</span>
        </h1>

        <p className="text-lg md:text-xl text-[#52525b] font-medium leading-relaxed max-w-2xl mx-auto">
          DeepTutor turns your textbook PDFs into day-by-day study roadmaps, AI tutoring sessions, interactive flashcards, and real-time progress analytics.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-4 pt-2">
          <button
            onClick={() => navigate(isAuthenticated ? '/dashboard' : '/register')}
            className="bg-[#111111] text-white hover:bg-[#27272a] py-4 px-8 rounded-full text-base font-bold flex items-center gap-3 shadow-md transition-all active:scale-95"
          >
            <Brain size={20} />
            {isAuthenticated ? 'Open Dashboard' : 'Get Started Free'}
          </button>

          <a
            href="#showcase"
            className="bg-white text-[#111111] hover:bg-[#f4f4f5] border border-[#e4e4e7] py-4 px-8 rounded-full text-base font-bold transition-all active:scale-95"
          >
            View Previews
          </a>
        </div>

        {/* Hero Image Mockup (Dashboard Screenshot) */}
        <div className="mt-14 relative rounded-3xl p-3 bg-white border border-[#e5e7eb] shadow-xl">
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[#f4f4f5] bg-[#fafafa] rounded-t-2xl">
            <div className="w-3 h-3 rounded-full bg-[#e4e4e7]" />
            <div className="w-3 h-3 rounded-full bg-[#e4e4e7]" />
            <div className="w-3 h-3 rounded-full bg-[#e4e4e7]" />
            <span className="text-xs font-semibold text-[#71717a] ml-2">DeepTutor AI — Dashboard View</span>
          </div>

          <div className="rounded-b-2xl overflow-hidden bg-[#fafafa]">
            <img
              src="/images/dashboard_screenshot.png"
              alt="DeepTutor AI Dashboard"
              className="w-full h-auto object-cover rounded-b-2xl"
            />
          </div>
        </div>
      </section>

      {/* ─── APP SHOWCASE SECTION (Easlo Tone Tabs & Screenshot) ─── */}
      <section id="showcase" className="py-20 px-6 max-w-5xl mx-auto border-t border-[#e5e7eb]">
        <div className="text-center max-w-2xl mx-auto space-y-3 mb-10">
          <span className="text-xs font-bold text-[#18181b] uppercase tracking-wider bg-[#f4f4f5] border border-[#e4e4e7] px-3.5 py-1 rounded-full">
            Application Screenshots
          </span>
          <h2 className="text-4xl font-black text-[#111111]">Explore the System</h2>
          <p className="text-[#52525b] text-base font-medium">
            Screenshots from your AI Study Dashboard, Day-by-Day Roadmaps, and Progress Analytics.
          </p>
        </div>

        {/* Interactive Tab Selectors (Click ONLY hover effect) */}
        <div className="flex flex-wrap items-center justify-center gap-3 mb-10">
          {PRODUCT_SHOWCASES.map((item) => {
            const Icon = item.icon
            const isActive = activeTab === item.id
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`flex items-center gap-2.5 px-6 py-3 rounded-full text-xs font-bold transition-all active:scale-95 ${
                  isActive
                    ? 'bg-[#111111] text-white border border-[#111111] shadow-sm'
                    : 'bg-white text-[#52525b] border border-[#e4e4e7] hover:bg-[#f4f4f5] hover:text-[#111111]'
                }`}
              >
                <Icon size={16} />
                <span>{item.title}</span>
              </button>
            )
          })}
        </div>

        {/* Active Showcase Frame */}
        <div className="bg-white rounded-3xl p-6 md:p-8 border border-[#e5e7eb] shadow-lg space-y-6">
          <div className="max-w-3xl space-y-3">
            <span className="text-xs font-bold text-[#18181b] uppercase tracking-wider bg-[#f4f4f5] border border-[#e4e4e7] px-3 py-1 rounded-full">
              {activeShowcase.badge}
            </span>
            <h3 className="text-3xl font-black text-[#111111]">{activeShowcase.title}</h3>
            <p className="text-[#52525b] text-base font-medium leading-relaxed">{activeShowcase.subtitle}</p>

            <div className="grid md:grid-cols-3 gap-3 pt-2">
              {activeShowcase.highlights.map((h, i) => (
                <div key={i} className="flex items-start gap-2.5 text-xs font-semibold text-[#27272a] bg-[#fafafa] p-3 rounded-2xl border border-[#f4f4f5]">
                  <CheckCircle2 size={16} className="text-[#111111] flex-shrink-0 mt-0.5" />
                  <span>{h}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl overflow-hidden border border-[#e5e7eb] bg-[#fafafa]">
            <img
              src={activeShowcase.image}
              alt={activeShowcase.title}
              className="w-full h-auto object-cover rounded-2xl"
            />
          </div>
        </div>
      </section>

      {/* ─── HOW IT WORKS (Minimal Cards) ─── */}
      <section id="how-it-works" className="py-20 px-6 max-w-5xl mx-auto border-t border-[#e5e7eb]">
        <div className="text-center max-w-2xl mx-auto space-y-3 mb-14">
          <span className="text-xs font-bold text-[#18181b] uppercase tracking-wider bg-[#f4f4f5] border border-[#e4e4e7] px-3.5 py-1 rounded-full">
            3-Step Process
          </span>
          <h2 className="text-4xl font-black text-[#111111]">How It Works</h2>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          <div className="bg-white p-8 rounded-3xl border border-[#e5e7eb] shadow-sm space-y-4">
            <div className="w-10 h-10 rounded-full bg-[#111111] text-white font-extrabold text-sm flex items-center justify-center">
              01
            </div>
            <h3 className="text-xl font-black text-[#111111]">Upload PDF Materials</h3>
            <p className="text-[#52525b] text-sm font-medium leading-relaxed">
              Upload textbook chapters or course materials into DeepTutor to start indexing.
            </p>
          </div>

          <div className="bg-white p-8 rounded-3xl border border-[#e5e7eb] shadow-sm space-y-4">
            <div className="w-10 h-10 rounded-full bg-[#111111] text-white font-extrabold text-sm flex items-center justify-center">
              02
            </div>
            <h3 className="text-xl font-black text-[#111111]">Generate Study Roadmap</h3>
            <p className="text-[#52525b] text-sm font-medium leading-relaxed">
              Set your target finish date to automatically generate a day-by-day study schedule.
            </p>
          </div>

          <div className="bg-white p-8 rounded-3xl border border-[#e5e7eb] shadow-sm space-y-4">
            <div className="w-10 h-10 rounded-full bg-[#111111] text-white font-extrabold text-sm flex items-center justify-center">
              03
            </div>
            <h3 className="text-xl font-black text-[#111111]">Study & Track Mastery</h3>
            <p className="text-[#52525b] text-sm font-medium leading-relaxed">
              Ask AI tutor questions, review flashcards, take quizzes, and track your activity streak.
            </p>
          </div>
        </div>
      </section>

      {/* ─── EASLO MINIMAL FOOTER ─── */}
      <footer className="py-16 border-t border-[#e5e7eb] bg-white">
        <div className="max-w-5xl mx-auto px-6 text-center space-y-6">
          <div className="flex items-center justify-center gap-3">
            <div className="w-9 h-9 rounded-2xl bg-[#111111] flex items-center justify-center text-white">
              <GraduationCap size={20} />
            </div>
            <span className="font-black text-2xl text-[#111111]">DeepTutor AI</span>
          </div>

          <p className="text-[#71717a] text-sm max-w-md mx-auto font-medium">
            Personalized AI study roadmaps, GraphRAG tutoring, and learning analytics.
          </p>

          <button
            onClick={() => navigate(isAuthenticated ? '/dashboard' : '/register')}
            className="bg-[#111111] text-white hover:bg-[#27272a] py-3.5 px-8 rounded-full text-sm font-bold transition-all active:scale-95"
          >
            Start Learning Free Today
          </button>

          <p className="text-xs text-[#a1a1aa] font-semibold pt-6">
            © {new Date().getFullYear()} DeepTutor AI. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  )
}
