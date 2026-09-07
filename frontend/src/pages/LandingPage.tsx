import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Brain,
  FileText,
  Table,
  Eye,
  Layers,
  Sparkles,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Check,
  Quote
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'

export default function LandingPage() {
  const navigate = useNavigate()
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

  // Interactive Live Demo State
  const [activeTab, setActiveTab] = useState<'tables' | 'vision' | 'flashcards' | 'intelligence'>('tables')
  const [isFlipped, setIsFlipped] = useState(false)
  const [selectedQuizOption, setSelectedQuizOption] = useState<string | null>(null)

  return (
    <div className="min-h-screen bg-[#FDFCF8] text-[#1A1A18] font-serif selection:bg-[#EBE7DF] selection:text-[#1A1A18]">
      
      {/* ─── 1. NAVBAR (Matching Figma Screenshot 1) ─── */}
      <header className="sticky top-0 z-50 bg-[#FDFCF8]/95 backdrop-blur-md border-b border-[#ECE9E1]">
        <div className="max-w-7xl mx-auto px-6 sm:px-12 h-20 flex items-center justify-between">
          {/* Logo */}
          <div
            className="cursor-pointer flex items-center gap-2"
            onClick={() => navigate('/')}
          >
            <span className="font-sans font-black text-sm tracking-[0.2em] text-[#1A1A18] uppercase">
              DEEPTUTOR
            </span>
          </div>

          {/* Right Navigation */}
          <div className="flex items-center gap-6 sm:gap-8 font-sans text-xs sm:text-sm font-medium text-[#55534E]">
            <a href="#scholarly-engine" className="hover:text-[#1A1A18] transition-colors hidden sm:inline">
              About
            </a>
            <a href="#features" className="hover:text-[#1A1A18] transition-colors hidden sm:inline">
              Pricing
            </a>
            {isAuthenticated ? (
              <button
                onClick={() => navigate('/dashboard')}
                className="bg-[#1A1A1A] hover:bg-[#2E2E2E] text-white px-5 py-2.5 rounded-xl font-medium transition cursor-pointer shadow-xs"
              >
                Dashboard
              </button>
            ) : (
              <>
                <button
                  onClick={() => navigate('/login')}
                  className="hover:text-[#1A1A18] transition-colors cursor-pointer"
                >
                  Sign In
                </button>
                <button
                  onClick={() => navigate('/register')}
                  className="bg-[#1A1A1A] hover:bg-[#2E2E2E] text-white px-5 py-2.5 rounded-xl font-medium transition cursor-pointer shadow-xs"
                >
                  Create Workspace
                </button>
              </>
            )}
          </div>
        </div>
      </header>

      {/* ─── 2. HERO SECTION (Matching Figma Screenshot 1) ─── */}
      <section className="pt-24 pb-20 px-6 max-w-5xl mx-auto text-center space-y-7">
        <h1 className="text-5xl sm:text-6xl md:text-[72px] font-normal tracking-tight text-[#1A1A18] leading-[1.10] font-serif max-w-4xl mx-auto">
          Master complex STEM concepts <br className="hidden sm:inline" />
          from your actual textbooks.
        </h1>

        <div className="text-3xl sm:text-4xl md:text-[44px] font-serif italic text-[#9A7B38] -mt-1">
          Not generic summaries.
        </div>

        <p className="text-base sm:text-lg text-[#55534E] font-sans max-w-2xl mx-auto leading-relaxed pt-2">
          DeepTutor reads your uploaded course materials, calculates multi-row STEM tables from
          first principles, extracts high-resolution diagram schematics, and generates interactive
          Claude-style study decks.
        </p>

        {/* Hero CTA Buttons */}
        <div className="flex flex-wrap items-center justify-center gap-4 pt-4 font-sans text-xs sm:text-sm">
          <button
            onClick={() => navigate(isAuthenticated ? '/dashboard' : '/register')}
            className="bg-[#1A1A1A] hover:bg-[#2E2E2E] text-white py-3.5 px-6 rounded-xl font-semibold flex items-center gap-2.5 shadow-sm cursor-pointer transition active:scale-95"
          >
            <Brain size={16} />
            <span>Open Study Room</span>
          </button>

          <a
            href="#scholarly-engine"
            className="bg-white hover:bg-[#F9F8F5] text-[#1A1A18] border border-[#DDD9CE] py-3.5 px-6 rounded-xl font-semibold transition shadow-xs"
          >
            Explore Live Showcase
          </a>
        </div>
      </section>

      {/* ─── 3. THE SCHOLARLY ENGINE (Matching Figma Screenshot 2) ─── */}
      <section id="scholarly-engine" className="py-20 px-6 sm:px-12 max-w-7xl mx-auto border-t border-[#ECE9E1]">
        {/* Section Top Eyebrow & Split Header */}
        <div className="mb-14 space-y-6">
          <div className="flex items-center gap-3">
            <span className="font-sans font-semibold text-[11px] tracking-[0.2em] text-[#9A7B38] uppercase">
              THE SCHOLARLY ENGINE
            </span>
            <div className="h-[1px] bg-[#E8E4D8] flex-1 max-w-[280px]" />
          </div>

          <div className="grid lg:grid-cols-12 gap-8 items-end justify-between">
            <div className="lg:col-span-7">
              <h2 className="text-3xl sm:text-4xl md:text-[42px] font-normal text-[#1A1A18] font-serif leading-[1.18] tracking-tight">
                Systematic rigor engineered for <br className="hidden sm:inline" />
                advanced academic curricula.
              </h2>
            </div>
            <div className="lg:col-span-5 flex lg:justify-end">
              <p className="text-xs sm:text-sm text-[#55534E] font-sans leading-relaxed max-w-md">
                DeepTutor doesn't guess. It extracts structure, reasons step-by-step from base papers,
                and maintains a strict record of truth.
              </p>
            </div>
          </div>
        </div>

        {/* 4-Card Grid (Exact Figma Screenshot 2) */}
        <div className="grid md:grid-cols-2 gap-6">
          {/* Card 1: Multimodal Document Intelligence */}
          <div className="p-8 rounded-3xl bg-white border border-[#EBE8E0] shadow-xs hover:border-[#D8D4C8] transition-all space-y-4 text-left">
            <div className="flex items-center justify-between">
              <div className="w-11 h-11 rounded-2xl bg-[#FAF9F5] border border-[#E8E5DC] flex items-center justify-center text-[#1A1A18]">
                <FileText size={20} />
              </div>
              <span className="text-[10px] font-sans font-bold tracking-wider uppercase px-2.5 py-1 rounded-md bg-[#FBF7EE] text-[#9A7B38] border border-[#EADBBD]">
                DOCUMENT PARSER
              </span>
            </div>

            <h3 className="text-xl sm:text-2xl font-serif text-[#1A1A18] font-normal pt-1">
              Multimodal Document Intelligence
            </h3>

            <p className="text-xs sm:text-sm text-[#55534E] font-sans leading-relaxed">
              DeepTutor reads rich textbook PDFs, technical manuscripts, and lecture slides. It parses
              embedded tables, structural figures, complex multi-line math equations, and handwritten
              notes in a single unified sequence.
            </p>
          </div>

          {/* Card 2: First-Principles STEM Tables */}
          <div className="p-8 rounded-3xl bg-white border border-[#EBE8E0] shadow-xs hover:border-[#D8D4C8] transition-all space-y-4 text-left">
            <div className="flex items-center justify-between">
              <div className="w-11 h-11 rounded-2xl bg-[#FAF9F5] border border-[#E8E5DC] flex items-center justify-center text-[#1A1A18]">
                <Table size={20} />
              </div>
              <span className="text-[10px] font-sans font-bold tracking-wider uppercase px-2.5 py-1 rounded-md bg-[#FBF7EE] text-[#9A7B38] border border-[#EADBBD]">
                CALCULATION ENGINE
              </span>
            </div>

            <h3 className="text-xl sm:text-2xl font-serif text-[#1A1A18] font-normal pt-1">
              First-Principles STEM Tables
            </h3>

            <p className="text-xs sm:text-sm text-[#55534E] font-sans leading-relaxed">
              Solve matrix arithmetic, thermodynamic state tables, and biochemical pathways row-by-row.
              Click any calculation cell to inspect the mathematical proof, raw formula, and grounding
              page citations.
            </p>
          </div>

          {/* Card 3: Diagram & Schematic Vision */}
          <div className="p-8 rounded-3xl bg-white border border-[#EBE8E0] shadow-xs hover:border-[#D8D4C8] transition-all space-y-4 text-left">
            <div className="flex items-center justify-between">
              <div className="w-11 h-11 rounded-2xl bg-[#FAF9F5] border border-[#E8E5DC] flex items-center justify-center text-[#1A1A18]">
                <Eye size={20} />
              </div>
              <span className="text-[10px] font-sans font-bold tracking-wider uppercase px-2.5 py-1 rounded-md bg-[#FBF7EE] text-[#9A7B38] border border-[#EADBBD]">
                COMPUTER VISION
              </span>
            </div>

            <h3 className="text-xl sm:text-2xl font-serif text-[#1A1A18] font-normal pt-1">
              Diagram & Schematic Vision
            </h3>

            <p className="text-xs sm:text-sm text-[#55534E] font-sans leading-relaxed">
              Upload structural diagrams, electric circuit schematics, or anatomical plates. DeepTutor
              instantly isolates sub-components, reconstructs the physical architecture, and builds an
              annotated interactive quiz view.
            </p>
          </div>

          {/* Card 4: Smart Progress Tracking */}
          <div className="p-8 rounded-3xl bg-white border border-[#EBE8E0] shadow-xs hover:border-[#D8D4C8] transition-all space-y-4 text-left">
            <div className="flex items-center justify-between">
              <div className="w-11 h-11 rounded-2xl bg-[#FAF9F5] border border-[#E8E5DC] flex items-center justify-center text-[#1A1A18]">
                <Layers size={20} />
              </div>
              <span className="text-[10px] font-sans font-bold tracking-wider uppercase px-2.5 py-1 rounded-md bg-[#FBF7EE] text-[#9A7B38] border border-[#EADBBD]">
                ANALYTICS
              </span>
            </div>

            <h3 className="text-xl sm:text-2xl font-serif text-[#1A1A18] font-normal pt-1">
              Smart Progress Tracking
            </h3>

            <p className="text-xs sm:text-sm text-[#55534E] font-sans leading-relaxed">
              Visualize your learning journey with intelligent dashboards. Track completion rates,
              identify weak areas, and get personalized study recommendations that adapt to your pace
              and performance.
            </p>
          </div>
        </div>
      </section>

      {/* ─── 4. TRUSTED AT LEADING ACADEMIC INSTITUTIONS (Exact Figma Screenshot 3 with proper spacing) ─── */}
      <section className="py-24 px-6 sm:px-12 max-w-7xl mx-auto border-t border-[#ECE9E1]">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl md:text-[42px] font-normal text-[#1A1A18] font-serif tracking-tight">
            Trusted at leading academic institutions
          </h2>
        </div>

        {/* 3 Testimonial Cards (Figma Matched & Clean Non-Overlapping Spacing) */}
        <div className="grid md:grid-cols-3 gap-6 sm:gap-8 items-stretch mb-24">
          {/* Testimonial 1 */}
          <div className="p-8 sm:p-9 rounded-[28px] bg-white border border-[#EBE8E0] shadow-xs flex flex-col justify-between space-y-8 text-left relative group hover:border-[#D8D4C8] transition-all">
            <div className="space-y-4">
              <span className="text-3xl font-serif text-[#C8BA9D] leading-none select-none block">
                ““
              </span>
              <p className="text-xs sm:text-sm text-[#3E3C37] font-serif leading-[1.75]">
                DeepTutor managed to parse my 800-page Organic Chemistry textbook without a single
                hallucination. The citations link directly to the specific page columns and reaction
                diagrams. It's like having a textbook author sitting right next to me.
              </p>
            </div>

            <div className="pt-3">
              <h4 className="font-serif font-bold text-sm text-[#1A1A18]">
                Dr. Marcus Vance
              </h4>
              <p className="text-xs text-[#7C7A74] font-sans mt-0.5">
                Professor of Chemistry, Stanford University
              </p>
            </div>
          </div>

          {/* Testimonial 2 */}
          <div className="p-8 sm:p-9 rounded-[28px] bg-white border border-[#EBE8E0] shadow-xs flex flex-col justify-between space-y-8 text-left relative group hover:border-[#D8D4C8] transition-all">
            <div className="space-y-4">
              <span className="text-3xl font-serif text-[#C8BA9D] leading-none select-none block">
                ““
              </span>
              <p className="text-xs sm:text-sm text-[#3E3C37] font-serif leading-[1.75]">
                The multi-row STEM table calculations are remarkably sound. Unlike standard LLMs
                that confidently invent arithmetic, DeepTutor reasons from first principles, computing each
                cell step-by-step with explicit mathematical proof.
              </p>
            </div>

            <div className="pt-3">
              <h4 className="font-serif font-bold text-sm text-[#1A1A18]">
                Elena Rostova
              </h4>
              <p className="text-xs text-[#7C7A74] font-sans mt-0.5">
                Ph.D. Candidate in Physics, MIT
              </p>
            </div>
          </div>

          {/* Testimonial 3 */}
          <div className="p-8 sm:p-9 rounded-[28px] bg-white border border-[#EBE8E0] shadow-xs flex flex-col justify-between space-y-8 text-left relative group hover:border-[#D8D4C8] transition-all">
            <div className="space-y-4">
              <span className="text-3xl font-serif text-[#C8BA9D] leading-none select-none block">
                ““
              </span>
              <p className="text-xs sm:text-sm text-[#3E3C37] font-serif leading-[1.75]">
                The interactive Claude-style study decks generated from my syllabi have completely
                restructured how I prepare my undergrads for exams. It bridges the gap between passive
                reading and rigorous active recall perfectly.
              </p>
            </div>

            <div className="pt-3">
              <h4 className="font-serif font-bold text-sm text-[#1A1A18]">
                Prof. Arthur Pendelton
              </h4>
              <p className="text-xs text-[#7C7A74] font-sans mt-0.5">
                Dept. of Mathematics, University of Cambridge
              </p>
            </div>
          </div>
        </div>

        {/* ─── 5. CALL TO ACTION SECTION (Exact Figma Screenshot 3) ─── */}
        <div className="text-center max-w-2xl mx-auto space-y-6 pt-6">
          <h2 className="text-3xl sm:text-4xl md:text-[42px] font-normal text-[#1A1A18] font-serif">
            Begin your scholarly journey.
          </h2>

          <p className="text-xs sm:text-sm text-[#55534E] font-sans max-w-xl mx-auto leading-relaxed">
            Upload your course materials and experience rigorous, grounded AI
            guidance designed exclusively for academic excellence.
          </p>

          <div className="pt-2">
            <button
              onClick={() => navigate(isAuthenticated ? '/dashboard' : '/register')}
              className="bg-[#1A1A1A] hover:bg-[#2E2E2E] text-white py-3.5 px-8 rounded-xl font-sans text-xs sm:text-sm font-semibold shadow-md transition active:scale-95 cursor-pointer"
            >
              Create Your Workspace — Free
            </button>
          </div>

          <p className="text-[11px] text-[#8C8980] font-sans">
            No credit card required. 14-day full access.
          </p>
        </div>
      </section>

      {/* ─── 6. FOOTER (Exact Figma Screenshot 4) ─── */}
      <footer className="pt-20 pb-12 px-6 sm:px-12 max-w-7xl mx-auto border-t border-[#ECE9E1] font-sans text-xs text-[#66645E]">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-10 pb-16">
          {/* Column 1: Brand & Bio */}
          <div className="md:col-span-2 space-y-4 text-left">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-[#1A1A1A] text-white flex items-center justify-center">
                <BookOpen size={13} />
              </div>
              <span className="font-bold text-[#1A1A18] text-sm">DeepTutor</span>
            </div>
            <p className="text-xs text-[#7C7A74] max-w-xs leading-relaxed">
              Premium multimodal STEM AI tutor that reasons directly from uploaded textbooks and verified
              materials. Designed for rigorous academic performance.
            </p>
          </div>

          {/* Column 2: PRODUCT */}
          <div className="space-y-3 text-left">
            <h4 className="font-bold text-[#1A1A18] text-[11px] tracking-wider uppercase">
              PRODUCT
            </h4>
            <ul className="space-y-2.5 text-[#55534E]">
              <li><a href="#scholarly-engine" className="hover:text-[#1A1A18] transition">Multimodal Engine</a></li>
              <li><a href="#scholarly-engine" className="hover:text-[#1A1A18] transition">STEM Table Solver</a></li>
              <li><a href="#scholarly-engine" className="hover:text-[#1A1A18] transition">Diagram Vision</a></li>
              <li><a href="#scholarly-engine" className="hover:text-[#1A1A18] transition">Study Decks</a></li>
            </ul>
          </div>

          {/* Column 3: ACADEMIC */}
          <div className="space-y-3 text-left">
            <h4 className="font-bold text-[#1A1A18] text-[11px] tracking-wider uppercase">
              ACADEMIC
            </h4>
            <ul className="space-y-2.5 text-[#55534E]">
              <li><a href="#" className="hover:text-[#1A1A18] transition">School Licensing</a></li>
              <li><a href="#" className="hover:text-[#1A1A18] transition">Research Grounding</a></li>
              <li><a href="#" className="hover:text-[#1A1A18] transition">Privacy Charter</a></li>
              <li><a href="#" className="hover:text-[#1A1A18] transition">System Status</a></li>
            </ul>
          </div>

          {/* Column 4: ENTERPRISE */}
          <div className="space-y-3 text-left">
            <h4 className="font-bold text-[#1A1A18] text-[11px] tracking-wider uppercase">
              ENTERPRISE
            </h4>
            <ul className="space-y-2.5 text-[#55534E]">
              <li><a href="#" className="hover:text-[#1A1A18] transition">Privacy & Trust</a></li>
              <li><a href="#" className="hover:text-[#1A1A18] transition">Custom Deployment</a></li>
              <li><a href="#" className="hover:text-[#1A1A18] transition">Case Studies</a></li>
              <li><a href="#" className="hover:text-[#1A1A18] transition">Contact Sales</a></li>
            </ul>
          </div>
        </div>

        {/* Bottom Legal Bar */}
        <div className="pt-8 border-t border-[#ECE9E1] flex flex-col sm:flex-row items-center justify-between gap-4 text-[11px] text-[#8C8980]">
          <p>© 2026 DeepTutor Technologies Inc. All scholarly rights reserved.</p>
          <div className="flex items-center gap-6">
            <a href="#" className="hover:text-[#1A1A18] transition">Terms of Service</a>
            <a href="#" className="hover:text-[#1A1A18] transition">Privacy Protocol</a>
            <a href="#" className="hover:text-[#1A1A18] transition">Cookie Preferences</a>
          </div>
        </div>
      </footer>
    </div>
  )
}
