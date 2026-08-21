import React, { useState, useEffect } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import {
  GraduationCap,
  Sparkles,
  BookOpen,
  FileText,
  Brain,
  Zap,
  Table,
  Trophy,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
  RefreshCw,
  Clock,
  ArrowRight,
  Send,
  HelpCircle,
  Flame,
  Layers
} from 'lucide-react'
import { useSubjectStore } from '../stores/subjectStore'
import { notesApi, quizApi } from '../services/api'
import ChatMessage from '../components/ChatMessage'

import UploadZone from '../components/examprep/UploadZone'
import LoadingState from '../components/examprep/LoadingState'
import TabSwitcher, { type TabKey } from '../components/examprep/TabSwitcher'
import OutputCard from '../components/examprep/OutputCard'
import { triggerConfettiBurst, triggerQuizSuccessConfetti } from '../components/examprep/ConfettiBurst'
import ExamToast, { type ToastMessage } from '../components/examprep/ExamToast'
import {
  fadeInUp,
  scaleIn,
  staggerContainer,
  staggerItem,
  cardHover,
  buttonPress,
  accordionVariants
} from '../utils/animations'

interface NoteResult {
  id?: string
  title: string
  content_markdown: string
  high_yield_topics: string[]
  key_formulas: string[]
  exam_tips: string[]
  solved_questions: Array<{
    year_or_type: string
    question: string
    step_by_step_solution: string
    key_concept: string
  }>
}

interface QuizQuestion {
  id: number
  question: string
  options: string[]
  correct_index: number
  explanation: string
  concept_tag?: string
}

export default function ExamPrepPage() {
  const shouldReduceMotion = useReducedMotion()
  const { subjects, getTopics } = useSubjectStore()

  // Step 1: Input State
  const [inputMode, setInputMode] = useState<'curriculum' | 'custom'>('curriculum')
  const [selectedSubjectId, setSelectedSubjectId] = useState('sslc-math')
  const [selectedTopicId, setSelectedTopicId] = useState('math-10-1')
  
  // Custom Files
  const [customFile, setCustomFile] = useState<File | null>(null)
  const [pyqFile, setPyqFile] = useState<File | null>(null)
  const [customPrompt, setCustomPrompt] = useState('')

  // Step 2 & 3 State
  const [isGenerating, setIsGenerating] = useState(false)
  const [activeTab, setActiveTab] = useState<TabKey>('smart_notes')
  const [generatedNote, setGeneratedNote] = useState<NoteResult | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // Interactive Quiz State
  const [quizQuestions, setQuizQuestions] = useState<QuizQuestion[]>([])
  const [userQuizAnswers, setUserQuizAnswers] = useState<Record<number, number>>({})
  const [quizSubmitted, setQuizSubmitted] = useState(false)
  const [copiedFormula, setCopiedFormula] = useState<string | null>(null)
  const [expandedQuestionIdx, setExpandedQuestionIdx] = useState<number | null>(0)

  // Toasts
  const [toasts, setToasts] = useState<ToastMessage[]>([])

  const addToast = (type: 'success' | 'error' | 'info', title: string, message: string) => {
    const id = Date.now().toString()
    setToasts((prev) => [...prev, { id, type, title, message }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 3800)
  }

  const dismissToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }

  const topics = getTopics(selectedSubjectId) || []
  const activeSubject = subjects.find(s => s.id === selectedSubjectId) || subjects[0]
  const activeTopic = topics.find(t => t.id === selectedTopicId) || topics[0]

  useEffect(() => {
    if (topics.length > 0 && !topics.find(t => t.id === selectedTopicId)) {
      setSelectedTopicId(topics[0].id)
    }
  }, [selectedSubjectId, topics, selectedTopicId])

  // Handle Note & Resource Generation
  const handleGenerateResources = async () => {
    setIsGenerating(true)
    setErrorMsg(null)
    setQuizSubmitted(false)
    setUserQuizAnswers({})

    try {
      let subjectName = activeSubject?.name || 'Class 10'
      let topicTitle = activeTopic?.title || 'General Exam Prep'
      let topicIdParam = selectedTopicId

      if (inputMode === 'custom') {
        if (!customFile) {
          setErrorMsg('Please upload a textbook or syllabus PDF file.')
          addToast('error', 'Missing Material', 'Please upload a PDF file to begin analysis.')
          setIsGenerating(false)
          return
        }
        subjectName = 'Custom Subject'
        topicTitle = customFile.name.replace(/\.[^/.]+$/, '')
        topicIdParam = 'custom-upload'
      }

      // 1. Generate 5-Minute Smart Notes & Exam Resources
      const res = await notesApi.generate({
        materialFile: inputMode === 'custom' ? customFile : null,
        pyqFiles: inputMode === 'custom' && pyqFile ? [pyqFile] : [],
        topicId: topicIdParam,
        subject: subjectName,
        noteType: 'high_yield_master',
        customInstructions: customPrompt,
        existingDocId: inputMode === 'custom' ? topicTitle : ''
      })

      setGeneratedNote(res.data)

      // 2. Fetch / Generate Interactive Practice Quiz
      try {
        const quizRes = await quizApi.generate({
          topic_id: topicIdParam,
          num_questions: 5,
          difficulty: 'medium',
          focus_topic: topicTitle
        })
        if (quizRes.data && Array.isArray(quizRes.data.questions)) {
          const normalized = quizRes.data.questions.map((q: any, i: number) => {
            const qText = q.question_text || q.question || q.prompt || `Practice Question ${i + 1}`
            let correctIdx = 0
            if (typeof q.correct_index === 'number') {
              correctIdx = q.correct_index
            } else if (typeof q.correct_answer === 'string') {
              const letter = q.correct_answer.trim().toUpperCase()
              if (letter.includes('B')) correctIdx = 1
              else if (letter.includes('C')) correctIdx = 2
              else if (letter.includes('D')) correctIdx = 3
              else correctIdx = 0
            }
            return {
              id: q.id || i + 1,
              question: qText,
              options: Array.isArray(q.options) ? q.options : [],
              correct_index: correctIdx,
              explanation: q.explanation || ''
            }
          })
          setQuizQuestions(normalized)
        }
      } catch {
        // Fallback demo quiz
        setQuizQuestions([
          {
            id: 1,
            question: `What is the core principle tested in ${topicTitle}?`,
            options: [
              'Fundamental definition and governing laws',
              'Unrelated arbitrary formula',
              'Random guess calculation',
              'Historical footnote only'
            ],
            correct_index: 0,
            explanation: 'Exam questions always test foundational definitions and standard formula applications first.'
          },
          {
            id: 2,
            question: 'What is the most common mistake students make during the exam?',
            options: [
              'Writing with a blue pen',
              'Forgetting standard units and skipping step-by-step working',
              'Solving the paper too neatly',
              'Reading the question twice'
            ],
            correct_index: 1,
            explanation: 'Examiners award partial marks for Given, Formula, and Working. Forgetting units loses easy marks!'
          }
        ])
      }

      // Success Trigger
      triggerConfettiBurst()
      addToast('success', 'Exam Kit Ready!', 'DeepTutor synthesized your 5-minute notes, cheat sheet & quiz.')
    } catch (err: any) {
      console.error('Generation failed:', err)
      const errDetail = err?.response?.data?.detail || 'Failed to generate exam resources. Please try again.'
      setErrorMsg(errDetail)
      addToast('error', 'Generation Error', errDetail)
    } finally {
      setIsGenerating(false)
    }
  }

  const handleCopyFormula = (formula: string) => {
    navigator.clipboard.writeText(formula)
    setCopiedFormula(formula)
    addToast('info', 'Copied!', `Formula copied to clipboard: ${formula}`)
    setTimeout(() => setCopiedFormula(null), 2000)
  }

  const calculateQuizScore = () => {
    let score = 0
    quizQuestions.forEach((q, idx) => {
      if (userQuizAnswers[idx] === q.correct_index) score++
    })
    return score
  }

  const handleQuizSubmit = () => {
    setQuizSubmitted(true)
    const score = calculateQuizScore()
    if (score >= Math.ceil(quizQuestions.length * 0.6)) {
      triggerQuizSuccessConfetti()
      addToast('success', 'Great Job!', `You scored ${score}/${quizQuestions.length} on your practice quiz!`)
    } else {
      addToast('info', 'Quiz Completed', `Score: ${score}/${quizQuestions.length}. Review the explanations below!`)
    }
  }

  return (
    <div className="min-h-screen bg-[#FAF8F3] text-[#20201D] font-sans pb-20">
      
      {/* ─── TOAST NOTIFICATIONS ─── */}
      <ExamToast toasts={toasts} onDismiss={dismissToast} />

      {/* ─── HEADER ─── */}
      <div className="bg-white border-b border-[#E7E1D8] px-4 sm:px-8 py-6 shadow-2xs">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#FFF0E4] border border-[#F28A45]/30 text-[#F28A45] text-xs font-black uppercase tracking-wider">
              <Sparkles size={13} />
              Exam Preparation Hub
            </div>
            <h1 className="text-2xl sm:text-3xl font-black text-[#20201D] tracking-tight">
              3-Step Exam Readiness Engine
            </h1>
            <p className="text-xs sm:text-sm text-[#6F6B63] font-medium">
              Upload syllabus & past papers $\rightarrow$ DeepTutor analyzes $\rightarrow$ Get instant notes, cheat sheets & quizzes.
            </p>
          </div>

          <motion.button
            onClick={handleGenerateResources}
            disabled={isGenerating}
            whileTap={shouldReduceMotion ? undefined : buttonPress.tap}
            whileHover={shouldReduceMotion ? undefined : buttonPress.hover}
            className="btn-primary py-3 px-6 rounded-2xl font-black text-sm flex items-center justify-center gap-2 elevation-1 cursor-pointer disabled:opacity-50"
          >
            {isGenerating ? (
              <>
                <RefreshCw size={16} className="animate-spin text-white" />
                <span>DeepTutor Analyzing...</span>
              </>
            ) : (
              <>
                <Zap size={16} />
                <span>Generate Exam Resources</span>
              </>
            )}
          </motion.button>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 sm:px-8 py-8 space-y-8">

        {/* ─── 3-STEP PROGRESS HEADER ─── */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <motion.div
            whileHover={shouldReduceMotion ? undefined : { y: -2 }}
            className="p-4 rounded-2xl bg-[#F0F7FF] border border-[#BAE0FF] flex items-center gap-3.5 shadow-2xs"
          >
            <div className="w-10 h-10 rounded-xl bg-[#0284C7] text-white flex items-center justify-center font-black text-sm flex-shrink-0">
              1
            </div>
            <div>
              <h4 className="text-xs font-black text-[#0369A1] uppercase tracking-wider">Step 1: Upload Material</h4>
              <p className="text-xs text-[#64748B] font-medium">Textbook PDF, PYQ papers & notes</p>
            </div>
          </motion.div>

          <motion.div
            whileHover={shouldReduceMotion ? undefined : { y: -2 }}
            className="p-4 rounded-2xl bg-[#FFF7ED] border border-[#FED7AA] flex items-center gap-3.5 shadow-2xs"
          >
            <div className="w-10 h-10 rounded-xl bg-[#F97316] text-white flex items-center justify-center font-black text-sm flex-shrink-0">
              2
            </div>
            <div>
              <h4 className="text-xs font-black text-[#C2410C] uppercase tracking-wider">Step 2: DeepTutor AI</h4>
              <p className="text-xs text-[#64748B] font-medium">Extracts concepts & repeated questions</p>
            </div>
          </motion.div>

          <motion.div
            whileHover={shouldReduceMotion ? undefined : { y: -2 }}
            className="p-4 rounded-2xl bg-[#ECFDF5] border border-[#A7F3D0] flex items-center gap-3.5 shadow-2xs"
          >
            <div className="w-10 h-10 rounded-xl bg-[#10B981] text-white flex items-center justify-center font-black text-sm flex-shrink-0">
              3
            </div>
            <div>
              <h4 className="text-xs font-black text-[#047857] uppercase tracking-wider">Step 3: Exam Resources</h4>
              <p className="text-xs text-[#64748B] font-medium">Notes, cheat sheet, Q&A & quiz</p>
            </div>
          </motion.div>
        </div>

        {/* ─── STEP 1: MATERIAL SELECTION / UPLOAD CONTAINER ─── */}
        <div className="bg-white rounded-3xl border border-[#E7E1D8] p-6 sm:p-8 shadow-xs space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-[#E7E1D8]">
            <div className="flex items-center gap-2.5">
              <span className="w-7 h-7 rounded-lg bg-[#0284C7] text-white font-black text-xs flex items-center justify-center">
                1
              </span>
              <h2 className="text-lg font-black text-[#20201D]">Select or Upload Your Study Material</h2>
            </div>

            {/* Input Mode Toggle */}
            <div className="flex items-center p-1 rounded-xl bg-[#FAF8F3] border border-[#E7E1D8] gap-1">
              <motion.button
                onClick={() => setInputMode('curriculum')}
                whileTap={shouldReduceMotion ? undefined : { scale: 0.96 }}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  inputMode === 'curriculum'
                    ? 'bg-white text-[#20201D] shadow-2xs'
                    : 'text-[#6F6B63] hover:text-[#20201D]'
                }`}
              >
                📚 Official Curriculum
              </motion.button>
              <motion.button
                onClick={() => setInputMode('custom')}
                whileTap={shouldReduceMotion ? undefined : { scale: 0.96 }}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  inputMode === 'custom'
                    ? 'bg-white text-[#20201D] shadow-2xs'
                    : 'text-[#6F6B63] hover:text-[#20201D]'
                }`}
              >
                📄 Upload PDF & PYQs
              </motion.button>
            </div>
          </div>

          {inputMode === 'curriculum' ? (
            /* Curriculum Mode: Select Subject & Chapter */
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-xs font-bold text-[#6F6B63] uppercase tracking-wider mb-2">
                  Choose Subject
                </label>
                <div className="grid grid-cols-3 gap-2.5">
                  {subjects.map((s) => (
                    <motion.button
                      key={s.id}
                      onClick={() => setSelectedSubjectId(s.id)}
                      whileHover={shouldReduceMotion ? undefined : { y: -2 }}
                      whileTap={shouldReduceMotion ? undefined : { scale: 0.97 }}
                      className={`p-3 rounded-2xl border text-center transition-all cursor-pointer flex flex-col items-center gap-1.5 ${
                        selectedSubjectId === s.id
                          ? 'border-[#F28A45] bg-[#FFF0E4] text-[#F28A45] font-black shadow-2xs'
                          : 'border-[#E7E1D8] bg-white text-[#6F6B63] hover:bg-[#FAF8F3] font-bold'
                      }`}
                    >
                      <span className="text-xl">
                        {s.id.includes('math') ? '🧮' : s.id.includes('phys') ? '⚡' : s.id.includes('chem') ? '🧪' : '📖'}
                      </span>
                      <span className="text-xs truncate w-full">{s.name}</span>
                    </motion.button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-[#6F6B63] uppercase tracking-wider mb-2">
                  Choose Chapter / Topic
                </label>
                <select
                  value={selectedTopicId}
                  onChange={(e) => setSelectedTopicId(e.target.value)}
                  className="w-full p-3.5 rounded-2xl border border-[#E7E1D8] bg-[#FAF8F3] text-xs sm:text-sm font-bold text-[#20201D] focus:border-[#F28A45] outline-none shadow-2xs"
                >
                  {topics.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.title}
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-[#969188] font-medium mt-2">
                  Connected to official Kerala SCERT Class 10 Textbook Index.
                </p>
              </div>
            </div>
          ) : (
            /* Custom Upload Mode with UploadZone Components */
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <UploadZone
                label="Upload Textbook / Notes PDF"
                sublabel="Drag & drop PDF, Word, or text lecture materials"
                icon="book"
                selectedFile={customFile}
                onFileSelect={setCustomFile}
                onError={(msg) => addToast('error', 'Upload Error', msg)}
              />

              <UploadZone
                label="Attach Past Question Papers (PYQ)"
                sublabel="Optional: Attach past exam papers for trend analysis"
                icon="pyq"
                selectedFile={pyqFile}
                onFileSelect={setPyqFile}
                onError={(msg) => addToast('error', 'Upload Error', msg)}
              />
            </div>
          )}

          {/* Optional Custom Instructions */}
          <div>
            <label className="block text-xs font-bold text-[#6F6B63] uppercase tracking-wider mb-2">
              Custom Exam Focus (Optional)
            </label>
            <input
              type="text"
              value={customPrompt}
              onChange={(e) => setCustomPrompt(e.target.value)}
              placeholder="e.g. Focus on 4-mark numericals, proof of theorems, or specific treaties..."
              className="w-full p-3.5 rounded-2xl border border-[#E7E1D8] bg-[#FAF8F3] text-xs sm:text-sm font-medium text-[#20201D] focus:border-[#F28A45] outline-none shadow-2xs placeholder-[#969188]"
            />
          </div>
        </div>

        {/* ─── STEP 2: WHAT DEEPTUTOR DOES (ACTIVE GENERATOR ACTION BAR) ─── */}
        <div className="bg-gradient-to-r from-[#FFF7ED] via-[#FFF0E4] to-[#F0F7FF] rounded-3xl border-2 border-[#FED7AA] p-6 sm:p-8 shadow-sm space-y-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-start gap-3.5">
              <div className="w-10 h-10 rounded-2xl bg-[#F97316] text-white flex items-center justify-center font-black text-sm flex-shrink-0 shadow-xs">
                2
              </div>
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-black uppercase tracking-wider text-[#C2410C]">
                    DeepTutor AI Processing Engine
                  </span>
                  <span className="px-2 py-0.5 rounded-full bg-white text-[#EA580C] text-[10px] font-black border border-[#FED7AA]">
                    Ready
                  </span>
                </div>
                <h3 className="text-lg sm:text-xl font-black text-[#20201D]">
                  Transform Study Material into Exam-Ready Kit
                </h3>
                <p className="text-xs sm:text-sm text-[#6F6B63] font-medium max-w-xl">
                  DeepTutor reads your uploaded notes/curriculum, identifies recurring exam patterns, and synthesizes 5-minute cheat notes, formula tables & practice questions.
                </p>
              </div>
            </div>

            {/* Main Action Generate Button */}
            <motion.button
              onClick={handleGenerateResources}
              disabled={isGenerating}
              whileTap={shouldReduceMotion ? undefined : buttonPress.tap}
              whileHover={shouldReduceMotion ? undefined : buttonPress.hover}
              className="btn-primary py-4 px-8 rounded-2xl font-black text-sm sm:text-base flex items-center justify-center gap-3 shadow-md hover:shadow-lg transition-all cursor-pointer disabled:opacity-50 flex-shrink-0"
            >
              {isGenerating ? (
                <>
                  <RefreshCw size={20} className="animate-spin text-white" />
                  <span>DeepTutor Analyzing...</span>
                </>
              ) : (
                <>
                  <Zap size={20} className="text-white animate-bounce" />
                  <span>Generate All Exam Resources</span>
                </>
              )}
            </motion.button>
          </div>

          {/* Quick Target Resource Selectors */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 border-t border-[#FED7AA]/60">
            <motion.button
              onClick={() => {
                setActiveTab('smart_notes')
                if (!generatedNote) handleGenerateResources()
              }}
              whileHover={shouldReduceMotion ? undefined : { y: -2 }}
              whileTap={shouldReduceMotion ? undefined : { scale: 0.97 }}
              className="p-3 rounded-2xl bg-white border border-[#FED7AA] hover:border-[#F28A45] hover:bg-[#FFF0E4] transition-all text-left flex flex-col gap-1 cursor-pointer group shadow-2xs"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-black text-[#9A3412]">⚡ Smart Notes</span>
                <ArrowRight size={13} className="text-[#9A3412] opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
              <p className="text-[10px] text-[#64748B] font-medium leading-tight">5-min topic breakdown</p>
            </motion.button>

            <motion.button
              onClick={() => {
                setActiveTab('cheat_sheet')
                if (!generatedNote) handleGenerateResources()
              }}
              whileHover={shouldReduceMotion ? undefined : { y: -2 }}
              whileTap={shouldReduceMotion ? undefined : { scale: 0.97 }}
              className="p-3 rounded-2xl bg-white border border-[#FED7AA] hover:border-[#F28A45] hover:bg-[#FFF0E4] transition-all text-left flex flex-col gap-1 cursor-pointer group shadow-2xs"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-black text-[#9A3412]">📐 Cheat Sheet</span>
                <ArrowRight size={13} className="text-[#9A3412] opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
              <p className="text-[10px] text-[#64748B] font-medium leading-tight">Formulas & key facts</p>
            </motion.button>

            <motion.button
              onClick={() => {
                setActiveTab('important_qa')
                if (!generatedNote) handleGenerateResources()
              }}
              whileHover={shouldReduceMotion ? undefined : { y: -2 }}
              whileTap={shouldReduceMotion ? undefined : { scale: 0.97 }}
              className="p-3 rounded-2xl bg-white border border-[#FED7AA] hover:border-[#F28A45] hover:bg-[#FFF0E4] transition-all text-left flex flex-col gap-1 cursor-pointer group shadow-2xs"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-black text-[#9A3412]">❓ Important Q&A</span>
                <ArrowRight size={13} className="text-[#9A3412] opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
              <p className="text-[10px] text-[#64748B] font-medium leading-tight">Solved from past papers</p>
            </motion.button>

            <motion.button
              onClick={() => {
                setActiveTab('practice_quiz')
                if (!generatedNote) handleGenerateResources()
              }}
              whileHover={shouldReduceMotion ? undefined : { y: -2 }}
              whileTap={shouldReduceMotion ? undefined : { scale: 0.97 }}
              className="p-3 rounded-2xl bg-white border border-[#FED7AA] hover:border-[#F28A45] hover:bg-[#FFF0E4] transition-all text-left flex flex-col gap-1 cursor-pointer group shadow-2xs"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-black text-[#9A3412]">🏆 Practice Quiz</span>
                <ArrowRight size={13} className="text-[#9A3412] opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
              <p className="text-[10px] text-[#64748B] font-medium leading-tight">Instant self-test</p>
            </motion.button>
          </div>
        </div>

        {/* ─── ERROR ALERT ─── */}
        {errorMsg && (
          <motion.div
            variants={fadeInUp}
            initial="initial"
            animate="animate"
            className="p-4 rounded-2xl bg-[#FBE7E4] border border-[#C85C52]/30 text-[#C85C52] text-xs font-bold flex items-center gap-2"
          >
            <AlertCircle size={16} />
            <span>{errorMsg}</span>
          </motion.div>
        )}

        {/* ─── STEP 3: OUTPUT TABS & RESOURCES ─── */}
        <div className="bg-white rounded-3xl border border-[#E7E1D8] p-6 sm:p-8 shadow-xs space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#E7E1D8]">
            <div className="flex items-center gap-2.5">
              <span className="w-7 h-7 rounded-lg bg-[#10B981] text-white font-black text-xs flex items-center justify-center">
                3
              </span>
              <h2 className="text-lg font-black text-[#20201D]">
                {generatedNote ? generatedNote.title : 'Exam-Ready Resources'}
              </h2>
            </div>

            {/* Composable Animated TabSwitcher with layoutId */}
            <TabSwitcher activeTab={activeTab} onSelectTab={setActiveTab} />
          </div>

          {/* ─── TAB CONTENT DISPLAY ─── */}
          {isGenerating ? (
            <LoadingState />
          ) : !generatedNote ? (
            <div className="py-16 flex flex-col items-center justify-center text-center space-y-4 text-[#969188]">
              <div className="w-16 h-16 rounded-3xl bg-[#FAF8F3] border border-[#E7E1D8] flex items-center justify-center text-2xl shadow-2xs">
                🚀
              </div>
              <div className="max-w-md space-y-1">
                <h3 className="text-base font-bold text-[#20201D]">Ready to Prepare for Your Exam?</h3>
                <p className="text-xs text-[#6F6B63]">
                  Select your subject or upload your PDF material above, then click <strong>"Generate Exam Resources"</strong>.
                </p>
              </div>
              <motion.button
                onClick={handleGenerateResources}
                disabled={isGenerating}
                whileTap={shouldReduceMotion ? undefined : buttonPress.tap}
                whileHover={shouldReduceMotion ? undefined : buttonPress.hover}
                className="btn-primary py-3 px-7 rounded-2xl font-black text-xs sm:text-sm flex items-center gap-2 shadow-xs cursor-pointer active:scale-95 transition-all mt-2"
              >
                <Zap size={16} />
                <span>⚡ Click Here to Generate Exam Resources</span>
              </motion.button>
            </div>
          ) : (
            <AnimatePresence mode="wait">
              {/* TAB 1: 5-MINUTE SMART NOTES */}
              {activeTab === 'smart_notes' && (
                <motion.div
                  key="smart_notes"
                  variants={shouldReduceMotion ? undefined : staggerContainer}
                  initial="initial"
                  animate="animate"
                  exit="exit"
                  className="space-y-6"
                >
                  {/* High-Yield Topics Badges */}
                  {generatedNote.high_yield_topics?.length > 0 && (
                    <motion.div
                      variants={staggerItem}
                      className="flex flex-wrap items-center gap-2 p-3.5 rounded-2xl bg-[#FFF0E4] border border-[#F28A45]/20"
                    >
                      <span className="text-xs font-black uppercase text-[#F28A45] flex items-center gap-1 mr-1">
                        <Sparkles size={13} /> High-Yield Topics:
                      </span>
                      {generatedNote.high_yield_topics.map((t, idx) => (
                        <span
                          key={idx}
                          className="px-2.5 py-1 rounded-lg bg-white border border-[#F28A45]/30 text-xs font-bold text-[#20201D]"
                        >
                          {t}
                        </span>
                      ))}
                    </motion.div>
                  )}

                  {/* Markdown Notes Render */}
                  <motion.div variants={staggerItem} className="prose prose-sm max-w-none text-[#20201D]">
                    <ChatMessage
                      role="assistant"
                      content={generatedNote.content_markdown}
                    />
                  </motion.div>
                </motion.div>
              )}

              {/* TAB 2: CHEAT SHEET (FORMULAS & FACTS TABLE) */}
              {activeTab === 'cheat_sheet' && (
                <motion.div
                  key="cheat_sheet"
                  variants={shouldReduceMotion ? undefined : staggerContainer}
                  initial="initial"
                  animate="animate"
                  exit="exit"
                  className="space-y-6"
                >
                  <div className="space-y-3">
                    <h3 className="text-base font-black text-[#20201D] flex items-center gap-2">
                      <Table size={18} className="text-[#F28A45]" />
                      <span>Must-Know Formulas, Dates & Key Facts</span>
                    </h3>
                    <p className="text-xs text-[#6F6B63]">
                      Click any formula or term to copy it to your clipboard.
                    </p>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {generatedNote.key_formulas?.map((formula, idx) => (
                        <motion.div
                          key={idx}
                          variants={staggerItem}
                          whileHover={shouldReduceMotion ? undefined : { y: -3, boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.06)' }}
                          whileTap={shouldReduceMotion ? undefined : { scale: 0.98 }}
                          onClick={() => handleCopyFormula(formula)}
                          className="p-4 rounded-2xl bg-[#FAF8F3] border border-[#E7E1D8] hover:border-[#F28A45] transition-colors cursor-pointer flex items-center justify-between group shadow-2xs"
                        >
                          <span className="text-xs font-bold text-[#20201D] font-mono">
                            {formula}
                          </span>
                          <button
                            className="p-1.5 rounded-lg bg-white text-[#6F6B63] group-hover:text-[#F28A45] shadow-2xs transition-colors"
                            title="Copy to clipboard"
                          >
                            {copiedFormula === formula ? (
                              <Check size={14} className="text-[#10B981]" />
                            ) : (
                              <Copy size={14} />
                            )}
                          </button>
                        </motion.div>
                      ))}
                    </div>
                  </div>

                  {/* Examiner Tips OutputCard */}
                  {generatedNote.exam_tips?.length > 0 && (
                    <OutputCard
                      title="Top Examiner Tips to Avoid Losing Marks"
                      badge="High-Yield"
                      icon={<CheckCircle2 size={16} />}
                      collapsible={true}
                      defaultExpanded={true}
                    >
                      <ul className="space-y-2 text-xs text-[#065F46] font-medium">
                        {generatedNote.exam_tips.map((tip, idx) => (
                          <li key={idx} className="flex items-start gap-2 bg-[#ECFDF5] p-2.5 rounded-xl border border-[#A7F3D0]">
                            <span>•</span>
                            <span>{tip}</span>
                          </li>
                        ))}
                      </ul>
                    </OutputCard>
                  )}
                </motion.div>
              )}

              {/* TAB 3: IMPORTANT Q&A LIST */}
              {activeTab === 'important_qa' && (
                <motion.div
                  key="important_qa"
                  variants={shouldReduceMotion ? undefined : staggerContainer}
                  initial="initial"
                  animate="animate"
                  exit="exit"
                  className="space-y-4"
                >
                  <div className="space-y-1">
                    <h3 className="text-base font-black text-[#20201D] flex items-center gap-2">
                      <FileText size={18} className="text-[#F28A45]" />
                      <span>5 High-Yield Exam Practice Questions & Solutions</span>
                    </h3>
                    <p className="text-xs text-[#6F6B63]">
                      Categorized by marks weightage with step-by-step breakdown.
                    </p>
                  </div>

                  <div className="space-y-3">
                    {generatedNote.solved_questions?.map((sq, idx) => {
                      const isExpanded = expandedQuestionIdx === idx
                      return (
                        <OutputCard
                          key={idx}
                          title={sq.question}
                          badge={sq.year_or_type}
                          icon={<FileText size={15} />}
                          collapsible={true}
                          defaultExpanded={idx === 0}
                        >
                          <div className="space-y-3">
                            <div className="p-3.5 rounded-xl bg-[#FAF8F3] border border-[#E7E1D8] space-y-2">
                              <p className="text-xs font-black uppercase text-[#F28A45]">
                                Step-by-Step Model Solution:
                              </p>
                              <div className="text-xs text-[#20201D] whitespace-pre-line leading-relaxed font-medium">
                                {sq.step_by_step_solution}
                              </div>
                            </div>

                            <div className="flex items-center gap-2 text-[11px] text-[#6F6B63]">
                              <span className="font-bold">Core Concept:</span>
                              <span className="px-2 py-0.5 rounded-md bg-[#FAF8F3] border border-[#E7E1D8] text-[#20201D] font-medium">
                                {sq.key_concept}
                              </span>
                            </div>
                          </div>
                        </OutputCard>
                      )
                    })}
                  </div>
                </motion.div>
              )}

              {/* TAB 4: INTERACTIVE PRACTICE QUIZ */}
              {activeTab === 'practice_quiz' && (
                <motion.div
                  key="practice_quiz"
                  variants={shouldReduceMotion ? undefined : staggerContainer}
                  initial="initial"
                  animate="animate"
                  exit="exit"
                  className="space-y-6"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-base font-black text-[#20201D] flex items-center gap-2">
                        <Trophy size={18} className="text-[#F28A45]" />
                        <span>Interactive Self-Test Quiz</span>
                      </h3>
                      <p className="text-xs text-[#6F6B63]">
                        Test your understanding before stepping into the exam hall.
                      </p>
                    </div>

                    {quizSubmitted && (
                      <motion.div
                        variants={scaleIn}
                        initial="initial"
                        animate="animate"
                        className="px-4 py-2 rounded-2xl bg-[#ECFDF5] border border-[#A7F3D0] text-[#065F46] font-black text-sm shadow-xs"
                      >
                        Score: {calculateQuizScore()} / {quizQuestions.length}
                      </motion.div>
                    )}
                  </div>

                  <div className="space-y-4">
                    {quizQuestions.map((q, qIdx) => {
                      const selectedOpt = userQuizAnswers[qIdx]
                      return (
                        <OutputCard
                          key={q.id || qIdx}
                          title={`${qIdx + 1}. ${(q as any).question_text || q.question || 'Practice Question'}`}
                          badge={`Q${qIdx + 1}`}
                          icon={<Trophy size={14} />}
                        >
                          <div className="space-y-3">
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                              {q.options.map((opt, optIdx) => {
                                const isSelected = selectedOpt === optIdx
                                const isCorrect = q.correct_index === optIdx
                                let btnStyle = 'border-[#E7E1D8] bg-white text-[#20201D] hover:bg-[#F4EFE7]'

                                if (quizSubmitted) {
                                  if (isCorrect) btnStyle = 'border-[#10B981] bg-[#ECFDF5] text-[#065F46] font-bold shadow-xs'
                                  else if (isSelected && !isCorrect) btnStyle = 'border-[#C85C52] bg-[#FBE7E4] text-[#C85C52]'
                                } else if (isSelected) {
                                  btnStyle = 'border-[#F28A45] bg-[#FFF0E4] text-[#F28A45] font-bold shadow-2xs'
                                }

                                return (
                                  <motion.button
                                    key={optIdx}
                                    onClick={() => {
                                      if (!quizSubmitted) {
                                        setUserQuizAnswers(prev => ({ ...prev, [qIdx]: optIdx }))
                                      }
                                    }}
                                    disabled={quizSubmitted}
                                    whileTap={shouldReduceMotion || quizSubmitted ? undefined : { scale: 0.98 }}
                                    className={`p-3 rounded-xl border text-left text-xs font-medium transition-all cursor-pointer ${btnStyle}`}
                                  >
                                    {opt}
                                  </motion.button>
                                )
                              })}
                            </div>

                            {quizSubmitted && q.explanation && (
                              <motion.p
                                variants={fadeInUp}
                                initial="initial"
                                animate="animate"
                                className="text-[11px] text-[#065F46] bg-[#ECFDF5] p-3 rounded-xl border border-[#A7F3D0] mt-2 leading-relaxed"
                              >
                                💡 <strong>Explanation:</strong> {q.explanation}
                              </motion.p>
                            )}
                          </div>
                        </OutputCard>
                      )
                    })}
                  </div>

                  <div className="pt-2 flex justify-end">
                    {!quizSubmitted ? (
                      <motion.button
                        onClick={handleQuizSubmit}
                        disabled={Object.keys(userQuizAnswers).length === 0}
                        whileTap={shouldReduceMotion ? undefined : buttonPress.tap}
                        whileHover={shouldReduceMotion ? undefined : buttonPress.hover}
                        className="btn-primary py-2.5 px-6 rounded-xl font-bold text-xs flex items-center gap-2 cursor-pointer disabled:opacity-40 shadow-xs"
                      >
                        <CheckCircle2 size={15} />
                        <span>Submit Quiz & Check Score</span>
                      </motion.button>
                    ) : (
                      <motion.button
                        onClick={() => {
                          setQuizSubmitted(false)
                          setUserQuizAnswers({})
                        }}
                        whileTap={shouldReduceMotion ? undefined : buttonPress.tap}
                        whileHover={shouldReduceMotion ? undefined : buttonPress.hover}
                        className="p-2.5 px-6 rounded-xl border border-[#E7E1D8] bg-white hover:bg-[#FAF8F3] font-bold text-xs text-[#20201D] flex items-center gap-2 cursor-pointer shadow-2xs"
                      >
                        <RefreshCw size={14} />
                        <span>Retake Quiz</span>
                      </motion.button>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          )}
        </div>

      </div>
    </div>
  )
}
