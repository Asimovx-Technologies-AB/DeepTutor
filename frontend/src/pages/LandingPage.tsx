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
    <div className="min-h-screen bg-[#FAF8F3] text-[#20201D] font-sans relative">
      {/* ─── HEADER ─── */}
      <header className="sticky top-0 z-40 bg-[#FAF8F3]/90 backdrop-blur-md border-b border-[#E7E1D8]">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 sm:h-20 flex items-center justify-between">
          <div
            className="flex items-center gap-2 sm:gap-3 cursor-pointer group"
            onClick={() => navigate('/')}
          >
            <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-xl sm:rounded-2xl bg-[#FFF0E4] border border-[#F28A45]/30 flex items-center justify-center text-[#F28A45] shadow-2xs transition-transform active:scale-95 flex-shrink-0">
              <GraduationCap className="w-4 h-4 sm:w-5 sm:h-5" />
            </div>
            <div className="flex items-center gap-1.5 sm:gap-2">
              <span className="font-black text-base sm:text-xl text-[#20201D] tracking-tight">DeepTutor</span>
              <span className="text-[9px] sm:text-[10px] font-black uppercase tracking-wider bg-[#FFF0E4] text-[#F28A45] px-1.5 sm:px-2 py-0.5 rounded-full border border-[#F28A45]/20">
                AI
              </span>
            </div>
          </div>

          <nav className="hidden md:flex items-center gap-8 text-sm font-bold text-[#6F6B63]">
            <a href="#showcase" className="hover:text-[#F28A45] transition-colors">Previews</a>
            <a href="#features" className="hover:text-[#F28A45] transition-colors">Features</a>
            <a href="#how-it-works" className="hover:text-[#F28A45] transition-colors">How It Works</a>
          </nav>

          <div className="flex items-center gap-2 sm:gap-3">
            {isAuthenticated ? (
              <button
                onClick={() => navigate('/dashboard')}
                className="btn-primary py-2 sm:py-2.5 px-4 sm:px-6 text-xs sm:text-sm font-black flex items-center gap-1.5 sm:gap-2 shadow-2xs cursor-pointer whitespace-nowrap"
              >
                <span>Dashboard</span> <ArrowRight className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
              </button>
            ) : (
              <>
                <button
                  onClick={() => navigate('/login')}
                  className="text-xs sm:text-sm font-bold text-[#6F6B63] hover:text-[#20201D] px-2.5 sm:px-4 py-1.5 sm:py-2 rounded-full transition-colors whitespace-nowrap cursor-pointer"
                >
                  Sign In
                </button>
                <button
                  onClick={() => navigate('/register')}
                  className="btn-primary py-1.5 sm:py-2.5 px-3.5 sm:px-6 text-xs sm:text-sm font-black shadow-2xs cursor-pointer whitespace-nowrap"
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
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-[#FFF0E4] border border-[#F28A45]/30 text-[#F28A45] text-xs font-black tracking-wide">
          <Sparkles size={14} className="text-[#F28A45]" />
          Simplified Learning Engine
        </div>

        <h1 className="text-5xl md:text-6xl lg:text-7xl font-black tracking-tight text-[#20201D] leading-[1.1]">
          Your Personal <br />
          <span className="text-[#F28A45]">AI Study System</span>
        </h1>

        <p className="text-lg md:text-xl text-[#6F6B63] font-medium leading-relaxed max-w-2xl mx-auto">
          DeepTutor turns your textbook PDFs into day-by-day study roadmaps, AI tutoring sessions, interactive flashcards, and real-time progress analytics.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-4 pt-2">
          <button
            onClick={() => navigate(isAuthenticated ? '/dashboard' : '/register')}
            className="btn-primary py-4 px-8 text-base font-black flex items-center gap-3 shadow-xs cursor-pointer"
          >
            <Brain size={20} />
            {isAuthenticated ? 'Open Dashboard' : 'Get Started Free'}
          </button>

          <a
            href="#showcase"
            className="bg-white text-[#20201D] hover:bg-[#FFF9F2] border border-[#E7E1D8] py-4 px-8 rounded-full text-base font-black transition-all active:scale-95"
          >
            View Previews
          </a>
        </div>

        {/* Hero Image Mockup (Dashboard Screenshot) */}
        <div className="mt-14 relative rounded-3xl p-3 bg-white border border-[#E7E1D8] shadow-xs">
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[#E7E1D8] bg-[#FAF8F3] rounded-t-2xl">
            <div className="w-3 h-3 rounded-full bg-[#E7E1D8]" />
            <div className="w-3 h-3 rounded-full bg-[#E7E1D8]" />
            <div className="w-3 h-3 rounded-full bg-[#E7E1D8]" />
            <span className="text-xs font-bold text-[#6F6B63] ml-2">DeepTutor AI — Dashboard View</span>
          </div>

          <div className="rounded-b-2xl overflow-hidden bg-[#FAF8F3]">
            <img
              src="/images/dashboard_screenshot.png"
              alt="DeepTutor AI Dashboard"
              className="w-full h-auto object-cover rounded-b-2xl"
            />
          </div>
        </div>
      </section>

      {/* ─── APP SHOWCASE SECTION ─── */}
      <section id="showcase" className="py-20 px-6 max-w-5xl mx-auto border-t border-[#E7E1D8]">
        <div className="text-center max-w-2xl mx-auto space-y-3 mb-10">
          <span className="text-xs font-black text-[#F28A45] uppercase tracking-wider bg-[#FFF0E4] border border-[#F28A45]/20 px-3.5 py-1 rounded-full">
            Application Screenshots
          </span>
          <h2 className="text-4xl font-black text-[#20201D]">Explore the System</h2>
          <p className="text-[#6F6B63] text-base font-medium">
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
                className={`flex items-center gap-2.5 px-6 py-3 rounded-full text-xs font-black transition-all active:scale-95 cursor-pointer ${
                  isActive
                    ? 'bg-[#F28A45] text-white shadow-2xs'
                    : 'bg-white text-[#6F6B63] border border-[#E7E1D8] hover:bg-[#FFF9F2] hover:text-[#20201D]'
                }`}
              >
                <Icon size={16} />
                <span>{item.title}</span>
              </button>
            )
          })}
        </div>

        {/* Active Showcase Frame */}
        <div className="bg-white rounded-3xl p-6 md:p-8 border border-[#E7E1D8] shadow-2xs space-y-6">
          <div className="max-w-3xl space-y-3">
            <span className="text-xs font-black text-[#F28A45] uppercase tracking-wider bg-[#FFF0E4] border border-[#F28A45]/20 px-3 py-1 rounded-full">
              {activeShowcase.badge}
            </span>
            <h3 className="text-3xl font-black text-[#20201D]">{activeShowcase.title}</h3>
            <p className="text-[#6F6B63] text-base font-medium leading-relaxed">{activeShowcase.subtitle}</p>

            <div className="grid md:grid-cols-3 gap-3 pt-2">
              {activeShowcase.highlights.map((h, i) => (
                <div key={i} className="flex items-start gap-2.5 text-xs font-bold text-[#20201D] bg-[#FFF9F2] p-3 rounded-2xl border border-[#E7E1D8]">
                  <CheckCircle2 size={16} className="text-[#4F8A68] flex-shrink-0 mt-0.5" />
                  <span>{h}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl overflow-hidden border border-[#E7E1D8] bg-[#FAF8F3]">
            <img
              src={activeShowcase.image}
              alt={activeShowcase.title}
              className="w-full h-auto object-cover rounded-2xl"
            />
          </div>
        </div>
      </section>

      {/* ─── HOW IT WORKS ─── */}
      <section id="how-it-works" className="py-20 px-6 max-w-5xl mx-auto border-t border-[#E7E1D8]">
        <div className="text-center max-w-2xl mx-auto space-y-3 mb-14">
          <span className="text-xs font-black text-[#F28A45] uppercase tracking-wider bg-[#FFF0E4] border border-[#F28A45]/20 px-3.5 py-1 rounded-full">
            3-Step Process
          </span>
          <h2 className="text-4xl font-black text-[#20201D]">How It Works</h2>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          <div className="bg-white p-8 rounded-3xl border border-[#E7E1D8] shadow-2xs space-y-4">
            <div className="w-10 h-10 rounded-full bg-[#FFF0E4] text-[#F28A45] border border-[#F28A45]/30 font-black text-sm flex items-center justify-center">
              01
            </div>
            <h3 className="text-xl font-black text-[#20201D]">Upload PDF Materials</h3>
            <p className="text-[#6F6B63] text-sm font-medium leading-relaxed">
              Upload textbook chapters or course materials into DeepTutor to start indexing.
            </p>
          </div>

          <div className="bg-white p-8 rounded-3xl border border-[#E7E1D8] shadow-2xs space-y-4">
            <div className="w-10 h-10 rounded-full bg-[#FFF0E4] text-[#F28A45] border border-[#F28A45]/30 font-black text-sm flex items-center justify-center">
              02
            </div>
            <h3 className="text-xl font-black text-[#20201D]">Generate Study Roadmap</h3>
            <p className="text-[#6F6B63] text-sm font-medium leading-relaxed">
              Set your target finish date to automatically generate a day-by-day study schedule.
            </p>
          </div>

          <div className="bg-white p-8 rounded-3xl border border-[#E7E1D8] shadow-2xs space-y-4">
            <div className="w-10 h-10 rounded-full bg-[#FFF0E4] text-[#F28A45] border border-[#F28A45]/30 font-black text-sm flex items-center justify-center">
              03
            </div>
            <h3 className="text-xl font-black text-[#20201D]">Study & Track Mastery</h3>
            <p className="text-[#6F6B63] text-sm font-medium leading-relaxed">
              Ask AI tutor questions, review flashcards, take quizzes, and track your activity streak.
            </p>
          </div>
        </div>
      </section>

      {/* ─── FOOTER ─── */}
      <footer className="py-16 border-t border-[#E7E1D8] bg-white">
        <div className="max-w-5xl mx-auto px-6 text-center space-y-6">
          <div className="flex items-center justify-center gap-3">
            <div className="w-9 h-9 rounded-2xl bg-[#FFF0E4] border border-[#F28A45]/30 flex items-center justify-center text-[#F28A45]">
              <GraduationCap size={20} />
            </div>
            <span className="font-black text-2xl text-[#20201D]">DeepTutor AI</span>
          </div>

          <p className="text-[#6F6B63] text-sm max-w-md mx-auto font-medium">
            Personalized AI study roadmaps, GraphRAG tutoring, and learning analytics.
          </p>

          <button
            onClick={() => navigate(isAuthenticated ? '/dashboard' : '/register')}
            className="btn-primary py-3.5 px-8 text-sm font-black shadow-2xs cursor-pointer"
          >
            Start Learning Free Today
          </button>

          <p className="text-xs text-[#969188] font-bold pt-6">
            © {new Date().getFullYear()} DeepTutor AI. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  )
}
