import React from 'react'
import { motion } from 'framer-motion'
import {
  UploadCloud,
  FileText,
  BookOpen,
  Brain,
  Sparkles,
  Zap,
  Table,
  CheckCircle2,
  FileQuestion,
  Trophy,
  ArrowRight,
  ChevronDown
} from 'lucide-react'

interface Props {
  className?: string
  showHeading?: boolean
}

export default function ExamPrepArchitectureFlow({ className = '', showHeading = true }: Props) {
  return (
    <div className={`w-full ${className}`}>
      {showHeading && (
        <div className="text-center max-w-2xl mx-auto space-y-2 mb-10">
          <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-600 text-xs font-black uppercase tracking-wider">
            <Sparkles size={13} />
            Exam Prep Architecture
          </div>
          <h2 className="text-2xl sm:text-3xl md:text-4xl font-black text-slate-800 tracking-tight">
            How DeepTutor Works in 3 Simple Steps
          </h2>
          <p className="text-sm sm:text-base text-slate-500 font-medium">
            Turn your study material into exam-ready notes, formulas, and practice questions in seconds.
          </p>
        </div>
      )}

      {/* 3-Step Visual Container (Horizontal Flow) */}
      <div className="grid grid-cols-1 lg:grid-cols-11 gap-4 lg:gap-2 items-center">
        
        {/* ─── STEP 1: WHAT YOU UPLOAD (Clean Slate/Indigo) ─── */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4 }}
          className="lg:col-span-3 bg-white border-2 border-indigo-100 rounded-3xl p-5 sm:p-6 shadow-xs flex flex-col justify-between h-full"
        >
          <div>
            <div className="flex items-center justify-between mb-4">
              <span className="text-[11px] font-black uppercase tracking-wider bg-indigo-600 text-white px-2.5 py-1 rounded-full">
                Step 1
              </span>
              <div className="w-8 h-8 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center shadow-xs">
                <UploadCloud size={17} />
              </div>
            </div>

            <h3 className="text-lg font-black text-slate-800 mb-1">What You Upload</h3>
            <p className="text-xs text-indigo-600 font-bold mb-4">Drop your study material</p>

            <div className="space-y-2.5">
              {/* Box 1 */}
              <div className="bg-slate-50 p-3 rounded-2xl border border-slate-200 shadow-2xs flex items-start gap-2.5">
                <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <BookOpen size={14} />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-slate-800">Textbook / syllabus PDF</h4>
                  <p className="text-[11px] text-slate-500 font-medium leading-tight mt-0.5">
                    Official chapter materials
                  </p>
                </div>
              </div>

              {/* Box 2 */}
              <div className="bg-slate-50 p-3 rounded-2xl border border-slate-200 shadow-2xs flex items-start gap-2.5">
                <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <FileQuestion size={14} />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-slate-800">Question papers (PYQ)</h4>
                  <p className="text-[11px] text-slate-500 font-medium leading-tight mt-0.5">
                    Past papers & recurring questions
                  </p>
                </div>
              </div>

              {/* Box 3 */}
              <div className="bg-slate-50 p-3 rounded-2xl border border-slate-200 shadow-2xs flex items-start gap-2.5">
                <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <FileText size={14} />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-slate-800">Class notes or slides</h4>
                  <p className="text-[11px] text-slate-500 font-medium leading-tight mt-0.5">
                    Lecture notes and handouts
                  </p>
                </div>
              </div>
            </div>
          </div>
        </motion.div>

        {/* ─── ARROW 1 ─── */}
        <div className="lg:col-span-1 flex items-center justify-center py-2 lg:py-0">
          <div className="w-9 h-9 rounded-full bg-white border border-slate-200 shadow-xs flex items-center justify-center text-indigo-600">
            <ArrowRight size={18} className="hidden lg:block" />
            <ChevronDown size={18} className="block lg:hidden" />
          </div>
        </div>

        {/* ─── STEP 2: WHAT DEEPTUTOR DOES (Indigo) ─── */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, delay: 0.1 }}
          className="lg:col-span-3 bg-indigo-50/50 border-2 border-indigo-200 rounded-3xl p-5 sm:p-6 shadow-xs flex flex-col justify-between h-full"
        >
          <div>
            <div className="flex items-center justify-between mb-4">
              <span className="text-[11px] font-black uppercase tracking-wider bg-indigo-600 text-white px-2.5 py-1 rounded-full">
                Step 2
              </span>
              <div className="w-8 h-8 rounded-xl bg-white text-indigo-600 flex items-center justify-center shadow-xs">
                <Brain size={17} />
              </div>
            </div>

            <h3 className="text-lg font-black text-slate-800 mb-1">What DeepTutor Does</h3>
            <p className="text-xs text-indigo-600 font-bold mb-4">Understands & extracts</p>

            <div className="space-y-3">
              {/* Box 1 */}
              <div className="bg-white p-3.5 rounded-2xl border border-indigo-100 shadow-xs flex items-start gap-3">
                <div className="w-8 h-8 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Sparkles size={16} />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-slate-800">Reads Everything</h4>
                  <p className="text-[11px] text-slate-500 font-medium leading-relaxed mt-0.5">
                    Reads and understands everything you uploaded.
                  </p>
                </div>
              </div>

              {/* Box 2 */}
              <div className="bg-white p-3.5 rounded-2xl border border-indigo-100 shadow-xs flex items-start gap-3">
                <div className="w-8 h-8 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <CheckCircle2 size={16} />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-slate-800">Picks Important Topics</h4>
                  <p className="text-[11px] text-slate-500 font-medium leading-relaxed mt-0.5">
                    Picks out the high-yield topics and exam questions.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </motion.div>

        {/* ─── ARROW 2 ─── */}
        <div className="lg:col-span-1 flex items-center justify-center py-2 lg:py-0">
          <div className="w-9 h-9 rounded-full bg-white border border-slate-200 shadow-xs flex items-center justify-center text-emerald-600">
            <ArrowRight size={18} className="hidden lg:block" />
            <ChevronDown size={18} className="block lg:hidden" />
          </div>
        </div>

        {/* ─── STEP 3: WHAT YOU GET BACK (Fresh Emerald Green) ─── */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, delay: 0.2 }}
          className="lg:col-span-3 bg-emerald-50/50 border-2 border-emerald-200 rounded-3xl p-5 sm:p-6 shadow-xs flex flex-col justify-between h-full"
        >
          <div>
            <div className="flex items-center justify-between mb-4">
              <span className="text-[11px] font-black uppercase tracking-wider bg-emerald-600 text-white px-2.5 py-1 rounded-full">
                Step 3
              </span>
              <div className="w-8 h-8 rounded-xl bg-white text-emerald-600 flex items-center justify-center shadow-xs">
                <Trophy size={17} />
              </div>
            </div>

            <h3 className="text-lg font-black text-slate-800 mb-1">What You Get Back</h3>
            <p className="text-xs text-emerald-600 font-bold mb-4">Exam-ready resources</p>

            <div className="space-y-2">
              {/* Box 1 */}
              <div className="bg-white p-2.5 rounded-xl border border-emerald-100 shadow-2xs flex items-start gap-2.5">
                <div className="w-6 h-6 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Zap size={13} />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-slate-800">Smart notes</h4>
                  <p className="text-[11px] text-slate-500 font-medium leading-tight">
                    Short summary of each topic
                  </p>
                </div>
              </div>

              {/* Box 2 */}
              <div className="bg-white p-2.5 rounded-xl border border-emerald-100 shadow-2xs flex items-start gap-2.5">
                <div className="w-6 h-6 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Table size={13} />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-slate-800">Cheat sheet</h4>
                  <p className="text-[11px] text-slate-500 font-medium leading-tight">
                    Formulas & key facts
                  </p>
                </div>
              </div>

              {/* Box 3 */}
              <div className="bg-white p-2.5 rounded-xl border border-emerald-100 shadow-2xs flex items-start gap-2.5">
                <div className="w-6 h-6 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <FileText size={13} />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-slate-800">Important Q&A list</h4>
                  <p className="text-[11px] text-slate-500 font-medium leading-tight">
                    Solved from past papers
                  </p>
                </div>
              </div>

              {/* Box 4 */}
              <div className="bg-white p-2.5 rounded-xl border border-emerald-100 shadow-2xs flex items-start gap-2.5">
                <div className="w-6 h-6 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Trophy size={13} />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-slate-800">Practice quiz</h4>
                  <p className="text-[11px] text-slate-500 font-medium leading-tight">
                    Instant test before exam
                  </p>
                </div>
              </div>
            </div>
          </div>
        </motion.div>

      </div>
    </div>
  )
}
