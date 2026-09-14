import { useState, useRef, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import MermaidDiagram from '../components/MermaidDiagram'
import InlineSVGDiagram from '../components/InlineSVGDiagram'
import {
  Calendar,
  Sparkles,
  Clock,
  CheckCircle2,
  Circle,
  BookOpen,
  RefreshCw,
  Plus,
  Trash2,
  Brain,
  Target,
  UploadCloud,
  X,
  Search,
  Layers,
  Volume2,
  VolumeX,
  Copy,
  Check,
  Download,
  AlertTriangle,
  Flame,
  Filter
} from 'lucide-react'
import { studyPlanApi, documentsApi, default as api } from '../services/api'
import { useAuthStore } from '../stores/authStore'
import { useChatStore } from '../stores/chatStore'
import { useLanguageStore } from '../stores/languageStore'
import { useTranslation } from '../utils/translations'
import { UpgradeModal } from '../components/UpgradeModal'
import GamifiedQuizGame from '../components/GamifiedQuizGame'

interface ScheduleDay {
  day: number
  phase?: string
  topic: string
  focus: string
  estimated_hours: number
  recommended_action: string
  key_concepts: string[]
  study_notes?: string
}

interface StudyPlan {
  id: string
  user_id: string
  topic_id: string
  session_id?: string
  title: string
  target_date: string
  total_days: number
  hours_per_day: number
  schedule: ScheduleDay[]
  completed_days: number[]
  created_at: string
}

export default function StudyPlanPage() {
  const { user } = useAuthStore()
  const sessions = useChatStore((s) => s.sessions)
  const queryClient = useQueryClient()

  const { uiLanguage, aiLanguage } = useLanguageStore()
  const t = useTranslation(uiLanguage)

  const [upgradeModalInfo, setUpgradeModalInfo] = useState<{ open: boolean; fileName?: string; sizeMb?: number }>({ open: false })
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Generator form state
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [materialSourceMode, setMaterialSourceMode] = useState<'library' | 'upload' | 'session'>('library')
  const [selectedDocumentId, setSelectedDocumentId] = useState<string>('')
  const [selectedSessionId, setSelectedSessionId] = useState<string>('')
  const [modalDocSearchQuery, setModalDocSearchQuery] = useState<string>('')
  const [targetDate, setTargetDate] = useState<string>(() => {
    const d = new Date()
    d.setDate(d.getDate() + 14)
    return d.toISOString().split('T')[0]
  })
  const [hoursPerDay, setHoursPerDay] = useState<number>(2.5)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)

  // Filter & Search state in timeline
  const [filterMode, setFilterMode] = useState<'all' | 'completed' | 'in_progress' | 'upcoming'>('all')
  const [searchMilestoneQuery, setSearchMilestoneQuery] = useState<string>('')

  // Study Notes Modal State
  const [activeNotesModal, setActiveNotesModal] = useState<{
    dayNum: number
    topic: string
    notes: string
    loading: boolean
  } | null>(null)
  const [copied, setCopied] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)

  // Day Mastery Quiz State
  const [dayQuizModal, setDayQuizModal] = useState<{ dayNum: number; topic: string } | null>(null)
  const [quizVerificationMessage, setQuizVerificationMessage] = useState<{
    passed: boolean
    message: string
    dayNum: number
  } | null>(null)

  // Loading / generating state
  const [generating, setGenerating] = useState(false)
  const [activePlanId, setActivePlanId] = useState<string | null>(null)

  // Fetch all user uploaded materials across library and sessions
  const { data: userDocuments = [] } = useQuery<any[]>({
    queryKey: ['user-documents'],
    queryFn: async () => {
      const res = await documentsApi.list()
      return res.data || []
    },
    staleTime: 30_000,
  })

  // Deduplicate materials by file_name and pick richest metadata
  const uniqueUserDocuments = useMemo(() => {
    const map = new Map<string, any>()
    for (const doc of userDocuments) {
      const key = (doc.file_name || doc.id || '').toLowerCase().trim()
      if (!key) continue
      if (!map.has(key)) {
        map.set(key, doc)
      } else {
        const existing = map.get(key)
        if ((doc.key_topics?.length || 0) > (existing.key_topics?.length || 0)) {
          map.set(key, doc)
        }
      }
    }
    return Array.from(map.values())
  }, [userDocuments])

  // Filter documents for the modal search
  const filteredModalDocuments = useMemo(() => {
    if (!modalDocSearchQuery.trim()) return uniqueUserDocuments
    const q = modalDocSearchQuery.toLowerCase()
    return uniqueUserDocuments.filter((doc) =>
      (doc.file_name && doc.file_name.toLowerCase().includes(q)) ||
      (doc.detected_subject && doc.detected_subject.toLowerCase().includes(q)) ||
      (doc.key_topics && doc.key_topics.some((kt: string) => String(kt).toLowerCase().includes(q)))
    )
  }, [uniqueUserDocuments, modalDocSearchQuery])

  // Fetch my study plans from PostgreSQL
  const { data: plans = [], isLoading } = useQuery<StudyPlan[]>({
    queryKey: ['study-plans'],
    queryFn: async () => {
      const res = await studyPlanApi.myPlans()
      return res.data || []
    },
    staleTime: 60_000,
  })

  // Selected plan to view
  const currentPlan = plans.find((p) => p.id === activePlanId) || plans[0] || null

  const handleDayQuizComplete = async (result: { score: number; total: number; percentage: number }) => {
    if (!currentPlan?.id || !dayQuizModal) return
    const dayNum = dayQuizModal.dayNum
    try {
      const res = await studyPlanApi.verifyQuiz(currentPlan.id, dayNum, result.percentage)
      if (res.data) {
        setQuizVerificationMessage({
          passed: res.data.passed,
          message: res.data.message,
          dayNum: dayNum,
        })
        queryClient.invalidateQueries({ queryKey: ['study-plans'] })
        queryClient.invalidateQueries({ queryKey: ['progress-summary'] })
        queryClient.invalidateQueries({ queryKey: ['progress-calendar'] })
      }
    } catch (err: any) {
      console.error('[StudyPlan] Failed to verify day quiz:', err)
    }
  }

  // Toggle day completed mutation
  const toggleDayMutation = useMutation({
    mutationFn: async ({ planId, dayNumber }: { planId: string; dayNumber: number }) => {
      const res = await studyPlanApi.toggleDay(planId, dayNumber)
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['study-plans'] })
      queryClient.invalidateQueries({ queryKey: ['progress-summary'] })
      queryClient.invalidateQueries({ queryKey: ['progress-calendar'] })
    },
  })

  const handleOpenStudyNotes = async (dayItem: ScheduleDay, forceRegenerate = false) => {
    const isFullNote =
      dayItem.study_notes &&
      dayItem.study_notes.trim().length > 150 &&
      (dayItem.study_notes.includes('##') || dayItem.study_notes.includes('#'))

    if (!forceRegenerate && isFullNote) {
      setActiveNotesModal({
        dayNum: dayItem.day,
        topic: dayItem.topic,
        notes: dayItem.study_notes!,
        loading: false,
      })
      return
    }

    setActiveNotesModal({
      dayNum: dayItem.day,
      topic: dayItem.topic,
      notes: `### ${dayItem.topic}\n\nGenerating comprehensive AI Study Notes grounded in course materials...`,
      loading: true,
    })

    try {
      const res = await api.post('/study-plan/day-notes', {
        plan_id: currentPlan?.id,
        day_number: dayItem.day,
        topic_id: currentPlan?.topic_id || 'general',
        day_topic: dayItem.topic,
        key_concepts: dayItem.key_concepts || [],
        force_regenerate: forceRegenerate,
      })
      if (res.data?.notes) {
        setActiveNotesModal({
          dayNum: dayItem.day,
          topic: dayItem.topic,
          notes: res.data.notes,
          loading: false,
        })
        queryClient.setQueryData(['study-plans'], (oldPlans: StudyPlan[] | undefined) => {
          if (!oldPlans) return oldPlans
          return oldPlans.map((p) => {
            if (p.id === currentPlan?.id) {
              const updatedSchedule = p.schedule.map((item) =>
                item.day === dayItem.day ? { ...item, study_notes: res.data.notes } : item
              )
              return { ...p, schedule: updatedSchedule }
            }
            return p
          })
        })
      } else {
        setActiveNotesModal((prev) => (prev ? { ...prev, loading: false } : null))
      }
    } catch (err: any) {
      console.error('[StudyNotes] Failed to generate notes:', err)
      const errMsg = err?.response?.data?.detail || err?.message || 'Unknown error'
      setActiveNotesModal((prev) =>
        prev
          ? {
              ...prev,
              loading: false,
              notes: `### Could Not Generate Notes\n\n**Error:** ${errMsg}\n\nPlease try again.`,
            }
          : null
      )
    }
  }

  const copyNotes = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const downloadMarkdown = (text: string, title: string) => {
    if (!text) return
    const blob = new Blob([text], { type: 'text/markdown;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const cleanFileName = (title || 'Study_Notes').replace(/[^a-zA-Z0-9_-]/g, '_')
    link.setAttribute('download', `${cleanFileName}.md`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  const speakNotes = (text: string) => {
    if (!('speechSynthesis' in window)) return
    if (isSpeaking) {
      window.speechSynthesis.cancel()
      setIsSpeaking(false)
      return
    }
    const cleanText = text.replace(/[#*`_~]/g, '')
    const utterance = new SpeechSynthesisUtterance(cleanText)
    utterance.rate = 0.95
    utterance.onend = () => setIsSpeaking(false)
    utterance.onerror = () => setIsSpeaking(false)
    setIsSpeaking(true)
    window.speechSynthesis.speak(utterance)
  }

  // Delete plan mutation
  const deletePlanMutation = useMutation({
    mutationFn: async (planId: string) => {
      await studyPlanApi.delete(planId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['study-plans'] })
      queryClient.invalidateQueries({ queryKey: ['progress-summary'] })
      setActivePlanId(null)
    },
  })

  // Generate new study plan
  const handleGeneratePlan = async (e: React.FormEvent) => {
    e.preventDefault()
    setGenerating(true)

    try {
      let topicId = 'general'
      let sessionId: string | undefined = undefined

      if (materialSourceMode === 'upload' && selectedFile) {
        // Upload the new file and retrieve real document_id & session_id
        const uploadRes = await documentsApi.upload(
          `plan_${Date.now()}`,
          selectedFile
        )
        const docId =
          uploadRes.data?.document_id ||
          uploadRes.data?.id ||
          uploadRes.data?.canonical?.metadata?.id
        if (docId) {
          topicId = docId
        }
        sessionId = uploadRes.data?.session_id
      } else if (materialSourceMode === 'library') {
        const docIdToUse = selectedDocumentId || uniqueUserDocuments[0]?.id
        const doc = userDocuments.find((d: any) => d.id === docIdToUse)
        if (doc) {
          topicId = doc.id || doc.topic_id || 'general'
          sessionId = doc.session_id || doc.topic_id
        }
      } else if (materialSourceMode === 'session' && selectedSessionId) {
        sessionId = selectedSessionId
        const session = sessions.find((s) => s.id === selectedSessionId)
        topicId = session?.topic_id || selectedSessionId || 'general'
      } else if (uniqueUserDocuments.length > 0) {
        // Automatically default to the first available document
        const firstDoc = uniqueUserDocuments[0]
        topicId = firstDoc.id || firstDoc.topic_id || 'general'
        sessionId = firstDoc.session_id
      }

      const res = await studyPlanApi.generate({
        topic_id: topicId,
        session_id: sessionId,
        target_date: targetDate,
        hours_per_day: hoursPerDay,
        language: aiLanguage,
      })

      queryClient.invalidateQueries({ queryKey: ['study-plans'] })
      queryClient.invalidateQueries({ queryKey: ['progress-summary'] })
      if (res.data?.id) {
        setActivePlanId(res.data.id)
      }
      setShowCreateModal(false)
      setSelectedFile(null)
      setSelectedDocumentId('')
      setSelectedSessionId('')
    } catch (err: any) {
      console.error(err)
      alert(err.response?.data?.detail || 'Failed to generate study plan. Please verify backend connection.')
    } finally {
      setGenerating(false)
    }
  }

  // Progress metrics calculation
  const completedCount = currentPlan?.completed_days?.length ?? 0
  const totalScheduleDays = currentPlan?.schedule?.length ?? 1
  const completionPct = Math.round((completedCount / totalScheduleDays) * 100)

  // Target countdown days
  const daysRemaining = useMemo(() => {
    if (!currentPlan?.target_date) return 0
    const target = new Date(currentPlan.target_date).getTime()
    const now = new Date().setHours(0, 0, 0, 0)
    return Math.ceil((target - now) / (1000 * 60 * 60 * 24))
  }, [currentPlan?.target_date])

  // Grounded document reference
  const groundedDoc = useMemo(() => {
    if (!currentPlan) return null
    return (
      userDocuments.find(
        (d: any) =>
          d.id === currentPlan.topic_id ||
          d.topic_id === currentPlan.topic_id ||
          d.session_id === currentPlan.session_id
      ) || null
    )
  }, [currentPlan, userDocuments])

  // Filtered milestone schedule
  const filteredSchedule = useMemo(() => {
    if (!currentPlan?.schedule) return []
    let items = currentPlan.schedule

    if (filterMode === 'completed') {
      items = items.filter((d) => currentPlan.completed_days?.includes(d.day))
    } else if (filterMode === 'in_progress') {
      const nextUncompletedDay = items.find((d) => !currentPlan.completed_days?.includes(d.day))?.day
      items = items.filter((d) => d.day === nextUncompletedDay)
    } else if (filterMode === 'upcoming') {
      const nextUncompletedDay = items.find((d) => !currentPlan.completed_days?.includes(d.day))?.day || 0
      items = items.filter((d) => !currentPlan.completed_days?.includes(d.day) && d.day > nextUncompletedDay)
    }

    if (searchMilestoneQuery.trim()) {
      const q = searchMilestoneQuery.toLowerCase()
      items = items.filter(
        (d) =>
          d.topic.toLowerCase().includes(q) ||
          d.focus.toLowerCase().includes(q) ||
          (d.key_concepts && d.key_concepts.some((c) => c.toLowerCase().includes(q)))
      )
    }

    return items
  }, [currentPlan, filterMode, searchMilestoneQuery])

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-[#1C1A17] p-4 sm:p-8 font-sans selection:bg-[#9E6B38]/20 selection:text-[#1C1A17]">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* ─── TOP HEADER BAR (Athenaeum Editorial Luxury) ─── */}
        <header className="flex flex-col md:flex-row md:items-center justify-between gap-6 pb-6 border-b border-stone-200/80">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold tracking-wider uppercase bg-[#9E6B38]/10 text-[#9E6B38] border border-[#9E6B38]/20">
                <Sparkles size={11} className="text-[#9E6B38]" />
                Scholia AI • Personalized Learning Roadmap
              </span>
            </div>
            <h1 className="text-3xl sm:text-4xl font-serif font-medium tracking-tight text-[#1C1A17]">
              {t.studyPlan.title}
            </h1>
            <p className="text-xs sm:text-sm text-[#5C564E] max-w-2xl font-normal leading-relaxed">
              {t.studyPlan.subtitle}
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowCreateModal(true)}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[#1C1A17] text-[#FAF8F5] text-xs font-semibold hover:bg-[#332F2A] active:scale-98 transition shadow-xs cursor-pointer"
            >
              <Plus size={15} />
              <span>{t.studyPlan.createNew}</span>
            </button>
          </div>
        </header>

        {isLoading ? (
          <div className="p-16 text-center space-y-3">
            <RefreshCw size={28} className="animate-spin text-[#9E6B38] mx-auto" />
            <p className="text-xs font-semibold text-[#5C564E]">Loading your academic study plans...</p>
          </div>
        ) : plans.length === 0 ? (
          /* ─── EMPTY STATE (Scholarly Paper Aesthetic) ─── */
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="p-12 sm:p-16 text-center border border-stone-200/90 rounded-2xl bg-white max-w-xl mx-auto space-y-6 shadow-xs"
          >
            <div className="w-16 h-16 rounded-2xl bg-[#9E6B38]/10 border border-[#9E6B38]/20 flex items-center justify-center text-[#9E6B38] mx-auto shadow-2xs">
              <Calendar size={30} />
            </div>
            <div className="space-y-2">
              <h2 className="text-xl font-serif font-medium text-[#1C1A17]">No Study Roadmap Active</h2>
              <p className="text-xs text-[#5C564E] max-w-md mx-auto leading-relaxed">
                Build a personalized day-by-day learning plan grounded in your textbook or lecture slides with Socratic daily checkpoints.
              </p>
            </div>
            <button
              onClick={() => setShowCreateModal(true)}
              className="inline-flex items-center gap-2 px-6 py-2.5 rounded-lg bg-[#1C1A17] text-[#FAF8F5] text-xs font-semibold hover:bg-[#332F2A] active:scale-98 transition shadow-xs cursor-pointer"
            >
              <Sparkles size={14} className="text-[#9E6B38]" /> Generate Study Roadmap
            </button>
          </motion.div>
        ) : (
          /* ─── ACTIVE STUDY PLAN DASHBOARD ─── */
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
            {/* Left Column: Saved Curricula & Syllabi */}
            <aside className="space-y-4">
              <div className="flex items-center justify-between px-1">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-[#8C8479]">
                  Saved Syllabi ({plans.length})
                </h3>
              </div>

              <div className="space-y-2.5">
                {plans.map((p) => {
                  const isSel = (currentPlan?.id ?? plans[0]?.id) === p.id
                  const pct = Math.round(((p.completed_days?.length ?? 0) / (p.schedule?.length || 1)) * 100)

                  return (
                    <button
                      key={p.id}
                      onClick={() => setActivePlanId(p.id)}
                      className={`w-full text-left p-4 rounded-xl border transition-all cursor-pointer flex flex-col gap-2.5 ${
                        isSel
                          ? 'bg-white text-[#1C1A17] border-[#1C1A17] shadow-sm'
                          : 'bg-white/60 text-[#5C564E] border-stone-200/80 hover:bg-white hover:border-stone-300'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className={`text-[10px] font-mono font-semibold uppercase px-2 py-0.5 rounded-md ${
                          isSel ? 'bg-[#1C1A17] text-[#FAF8F5]' : 'bg-stone-100 text-[#5C564E]'
                        }`}>
                          Target: {p.target_date}
                        </span>
                        <span className="text-xs font-mono font-bold text-[#9E6B38]">
                          {pct}%
                        </span>
                      </div>

                      <h4 className="text-xs font-semibold line-clamp-1 text-[#1C1A17]">
                        {p.title}
                      </h4>

                      <div className="flex items-center justify-between text-[11px] text-[#8C8479] font-mono">
                        <span>{p.total_days} Days Total</span>
                        <span>{p.hours_per_day} hrs/day</span>
                      </div>
                    </button>
                  )
                })}
              </div>

              {/* Spaced repetition micro-card */}
              <div className="p-4 rounded-xl bg-white/70 border border-stone-200/70 space-y-2">
                <div className="flex items-center gap-2 text-xs font-semibold text-[#1C1A17]">
                  <Brain size={14} className="text-[#9E6B38]" />
                  <span>Cognitive Pacing</span>
                </div>
                <p className="text-[11px] text-[#5C564E] leading-relaxed">
                  Your daily checkpoints verify retention at ≥70% using active recall spaced repetition.
                </p>
              </div>
            </aside>

            {/* Right Column: Active Plan Details & Roadmap */}
            {currentPlan && (
              <main className="lg:col-span-3 space-y-6">
                {/* Quiz Verification Banner */}
                {quizVerificationMessage && (
                  <motion.div
                    initial={{ opacity: 0, y: -8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={`p-4 rounded-xl border flex items-center justify-between text-xs font-medium ${
                      quizVerificationMessage.passed
                        ? 'bg-[#ECFDF5] text-[#065F46] border-[#A7F3D0]'
                        : 'bg-[#FFFBEB] text-[#92400E] border-[#FDE68A]'
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      <Sparkles size={16} className={quizVerificationMessage.passed ? 'text-[#059669]' : 'text-[#D97706]'} />
                      <span>{quizVerificationMessage.message}</span>
                    </div>
                    <button
                      onClick={() => setQuizVerificationMessage(null)}
                      className="p-1 text-stone-400 hover:text-stone-700 cursor-pointer"
                    >
                      <X size={15} />
                    </button>
                  </motion.div>
                )}

                {/* Plan Overview Card */}
                <section className="p-6 sm:p-7 rounded-2xl bg-white border border-stone-200/90 shadow-xs space-y-5">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        {/* Countdown / Overdue pill */}
                        {daysRemaining < 0 && completionPct < 100 ? (
                          <span className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200">
                            <AlertTriangle size={11} /> Overdue by {Math.abs(daysRemaining)} Days
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-[#9E6B38]/10 text-[#9E6B38] border border-[#9E6B38]/20">
                            <Clock size={11} />
                            {daysRemaining === 0 ? 'Target: Today' : `${daysRemaining} Days Remaining`}
                          </span>
                        )}

                        <span className="text-[10px] font-mono text-[#8C8479]">
                          Target Finish: {currentPlan.target_date}
                        </span>
                      </div>

                      <h2 className="text-xl sm:text-2xl font-serif font-medium text-[#1C1A17]">
                        {currentPlan.title}
                      </h2>
                      {groundedDoc && (
                        <div className="inline-flex items-center gap-1.5 text-xs text-[#5C564E] pt-0.5">
                          <BookOpen size={13} className="text-[#9E6B38]" />
                          <span>
                            Grounded in: <strong className="text-[#1C1A17]">{groundedDoc.file_name || groundedDoc.title}</strong>{' '}
                            {groundedDoc.page_count ? `(${groundedDoc.page_count} pages)` : ''}
                          </span>
                        </div>
                      )}
                    </div>

                    <button
                      onClick={() => {
                        if (confirm(`Delete study plan "${currentPlan.title}"?`)) {
                          deletePlanMutation.mutate(currentPlan.id)
                        }
                      }}
                      className="p-2 text-stone-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition self-start sm:self-auto cursor-pointer"
                      title="Delete Study Plan"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>

                  {/* High Precision Progress Bar */}
                  <div className="space-y-2 pt-2 border-t border-stone-100">
                    <div className="flex items-center justify-between text-xs text-[#5C564E]">
                      <span className="font-medium">Mastery Progress</span>
                      <span className="font-mono font-semibold text-[#1C1A17]">
                        {completedCount} of {currentPlan.total_days} Days Mastered ({completionPct}%)
                      </span>
                    </div>
                    <div className="w-full bg-stone-100 rounded-full h-2 overflow-hidden">
                      <motion.div
                        className="bg-[#9E6B38] h-full rounded-full"
                        initial={{ width: 0 }}
                        animate={{ width: `${completionPct}%` }}
                        transition={{ duration: 0.6, ease: 'easeOut' }}
                      />
                    </div>
                  </div>
                </section>

                {/* Filter and Search Toolbar */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
                  {/* Segmented Filter Pills */}
                  <div className="flex items-center gap-1.5 p-1 bg-stone-200/50 rounded-lg border border-stone-200/60 self-start sm:self-auto">
                    {(['all', 'completed', 'in_progress', 'upcoming'] as const).map((mode) => (
                      <button
                        key={mode}
                        onClick={() => setFilterMode(mode)}
                        className={`px-3 py-1 rounded-md text-xs font-medium transition cursor-pointer ${
                          filterMode === mode
                            ? 'bg-white text-[#1C1A17] shadow-2xs font-semibold'
                            : 'text-[#5C564E] hover:text-[#1C1A17]'
                        }`}
                      >
                        {mode === 'all' && `All (${currentPlan.schedule?.length || 0})`}
                        {mode === 'completed' && `Mastered (${completedCount})`}
                        {mode === 'in_progress' && `In Focus`}
                        {mode === 'upcoming' && `Upcoming`}
                      </button>
                    ))}
                  </div>

                  {/* Topic Search Input */}
                  <div className="relative w-full sm:w-64">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
                    <input
                      type="text"
                      value={searchMilestoneQuery}
                      onChange={(e) => setSearchMilestoneQuery(e.target.value)}
                      placeholder="Search topics or concepts..."
                      className="w-full pl-8 pr-3 py-1.5 text-xs bg-white border border-stone-200/80 rounded-lg text-[#1C1A17] placeholder:text-stone-400 focus:outline-none focus:border-[#1C1A17]"
                    />
                  </div>
                </div>

                {/* Day-by-Day Milestone Cards */}
                <div className="space-y-4">
                  {filteredSchedule.length === 0 ? (
                    <div className="p-10 text-center rounded-xl bg-white border border-stone-200/80 space-y-2">
                      <p className="text-xs font-semibold text-[#5C564E]">No milestones matching current filter.</p>
                      <button
                        onClick={() => {
                          setFilterMode('all')
                          setSearchMilestoneQuery('')
                        }}
                        className="text-xs text-[#9E6B38] underline cursor-pointer"
                      >
                        Reset filters
                      </button>
                    </div>
                  ) : (
                    filteredSchedule.map((dayItem, idx) => {
                      const isDone = currentPlan.completed_days?.includes(dayItem.day)
                      const prevPhase = idx > 0 ? filteredSchedule[idx - 1].phase : null
                      const isNewPhase = dayItem.phase && dayItem.phase !== prevPhase

                      return (
                        <div key={dayItem.day} className="space-y-3">
                          {/* Phase Header */}
                          {isNewPhase && (
                            <div className="pt-4 pb-1">
                              <div className="flex items-center gap-3">
                                <span className="text-[11px] font-serif font-semibold text-[#9E6B38] tracking-wider uppercase px-2 py-0.5 rounded bg-[#9E6B38]/8 border border-[#9E6B38]/15">
                                  {dayItem.phase}
                                </span>
                                <div className="flex-1 h-[1px] bg-stone-200" />
                              </div>
                            </div>
                          )}

                          {/* Milestone Card */}
                          <motion.div
                            initial={{ opacity: 0, y: 5 }}
                            animate={{ opacity: 1, y: 0 }}
                            className={`p-5 sm:p-6 rounded-xl border transition-all ${
                              isDone
                                ? 'bg-white/80 border-stone-200/80'
                                : 'bg-white border-stone-200 hover:border-stone-300 shadow-2xs'
                            }`}
                          >
                            <div className="flex items-start gap-4">
                              {/* Checkbox toggle */}
                              <button
                                type="button"
                                onClick={() =>
                                  toggleDayMutation.mutate({
                                    planId: currentPlan.id,
                                    dayNumber: dayItem.day,
                                  })
                                }
                                title={isDone ? 'Mark as incomplete' : 'Click to mark complete'}
                                className={`w-6 h-6 rounded-md border mt-0.5 flex items-center justify-center flex-shrink-0 transition-colors cursor-pointer ${
                                  isDone
                                    ? 'bg-[#059669] border-[#059669] text-white'
                                    : 'border-stone-300 hover:border-[#1C1A17] bg-stone-50 text-transparent'
                                }`}
                              >
                                <Check size={14} className={isDone ? 'opacity-100' : 'opacity-0'} />
                              </button>

                              {/* Content */}
                              <div className="flex-1 space-y-3">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <div className="flex items-center gap-2">
                                    <span className="text-[11px] font-mono font-bold px-2 py-0.5 rounded bg-stone-100 text-[#1C1A17] border border-stone-200">
                                      Day {dayItem.day < 10 ? `0${dayItem.day}` : dayItem.day}
                                    </span>
                                    <span className="text-[11px] font-mono text-[#8C8479] flex items-center gap-1">
                                      <Clock size={11} /> {dayItem.estimated_hours} hrs
                                    </span>
                                  </div>

                                  {isDone ? (
                                    <span className="text-[10px] font-bold uppercase tracking-wider text-[#059669] bg-[#ECFDF5] border border-[#A7F3D0] px-2 py-0.5 rounded-full">
                                      Mastered
                                    </span>
                                  ) : (
                                    <span className="text-[10px] font-bold uppercase tracking-wider text-[#8C8479] bg-stone-100 px-2 py-0.5 rounded-full">
                                      Pending
                                    </span>
                                  )}
                                </div>

                                <div>
                                  <h3 className={`text-base font-serif font-semibold text-[#1C1A17] ${isDone ? 'line-through text-[#8C8479]' : ''}`}>
                                    {dayItem.topic}
                                  </h3>
                                  <p className="text-xs text-[#5C564E] mt-1 font-normal leading-relaxed">
                                    {dayItem.focus}
                                  </p>
                                </div>

                                {/* Recommended Directive */}
                                {dayItem.recommended_action && (
                                  <div className="p-3 bg-[#FAF8F5] border border-stone-200/70 rounded-lg text-xs text-[#5C564E] flex items-start gap-2.5">
                                    <Brain size={14} className="text-[#9E6B38] flex-shrink-0 mt-0.5" />
                                    <span>
                                      <strong className="text-[#1C1A17]">Daily Directive: </strong>
                                      {dayItem.recommended_action}
                                    </span>
                                  </div>
                                )}

                                {/* Key Concepts Chips */}
                                {dayItem.key_concepts && dayItem.key_concepts.length > 0 && (
                                  <div className="flex flex-wrap gap-1.5 pt-1">
                                    {dayItem.key_concepts.map((concept, cIdx) => (
                                      <span
                                        key={cIdx}
                                        className="text-[10px] font-mono px-2 py-0.5 rounded bg-stone-100/80 text-[#5C564E] border border-stone-200/60"
                                      >
                                        {concept}
                                      </span>
                                    ))}
                                  </div>
                                )}

                                {/* Action Buttons */}
                                <div className="pt-2 flex flex-wrap items-center gap-2.5">
                                  <button
                                    type="button"
                                    onClick={() => handleOpenStudyNotes(dayItem)}
                                    className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium rounded-lg border border-stone-200 bg-white hover:bg-stone-50 text-[#1C1A17] active:scale-98 transition cursor-pointer shadow-2xs"
                                  >
                                    <BookOpen size={13} className="text-[#9E6B38]" />
                                    <span>View AI Study Notes</span>
                                  </button>

                                  <button
                                    type="button"
                                    onClick={() => {
                                      const conceptsStr = dayItem.key_concepts?.length
                                        ? ` (Key Concepts: ${dayItem.key_concepts.join(', ')})`
                                        : ''
                                      setDayQuizModal({ dayNum: dayItem.day, topic: dayItem.topic + conceptsStr })
                                    }}
                                    className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium rounded-lg border active:scale-98 transition cursor-pointer shadow-2xs ${
                                      isDone
                                        ? 'bg-[#ECFDF5] text-[#065F46] border-[#A7F3D0] hover:bg-[#D1FAE5]'
                                        : 'bg-[#1C1A17] text-[#FAF8F5] border-[#1C1A17] hover:bg-[#332F2A]'
                                    }`}
                                  >
                                    <Target size={13} />
                                    <span>{isDone ? 'Retake Quiz (Mastered)' : 'Take Day Mastery Quiz'}</span>
                                  </button>
                                </div>
                              </div>
                            </div>
                          </motion.div>
                        </div>
                      )
                    })
                  )}
                </div>
              </main>
            )}
          </div>
        )}
      </div>

      {/* ─── CREATE / GENERATE STUDY PLAN MODAL ─── */}
      <AnimatePresence>
        {showCreateModal && (
          <div className="fixed inset-0 z-50 bg-[#1C1A17]/50 backdrop-blur-xs flex items-center justify-center p-4 overflow-y-auto">
            <motion.div
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              className="w-full max-w-xl bg-white rounded-2xl p-6 sm:p-8 border border-stone-200 shadow-xl space-y-6"
            >
              <div className="flex items-start justify-between pb-4 border-b border-stone-100">
                <div className="space-y-1">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-[#9E6B38]">
                    AI Curriculum Architect
                  </span>
                  <h3 className="text-xl font-serif font-medium text-[#1C1A17]">Generate Study Roadmap</h3>
                  <p className="text-xs text-[#5C564E]">
                    Structured day-by-day learning roadmap grounded in your materials.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="p-1.5 rounded-lg text-stone-400 hover:text-[#1C1A17] hover:bg-stone-100 cursor-pointer"
                >
                  <X size={18} />
                </button>
              </div>

              <form onSubmit={handleGeneratePlan} className="space-y-5">
                {/* Step 1: Material Source Selector */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-wider text-[#8C8479]">
                    1. Study Material Source
                  </label>
                  <div className="grid grid-cols-3 gap-2 p-1 bg-stone-100 rounded-lg">
                    {(['library', 'upload', 'session'] as const).map((mode) => (
                      <button
                        key={mode}
                        type="button"
                        onClick={() => setMaterialSourceMode(mode)}
                        className={`py-1.5 px-2 text-xs font-medium rounded-md transition cursor-pointer ${
                          materialSourceMode === mode
                            ? 'bg-white text-[#1C1A17] shadow-2xs font-semibold'
                            : 'text-[#5C564E] hover:text-[#1C1A17]'
                        }`}
                      >
                        {mode === 'library' && 'From Library'}
                        {mode === 'upload' && 'Upload File'}
                        {mode === 'session' && 'Chat Room'}
                      </button>
                    ))}
                  </div>

                  {materialSourceMode === 'library' && (
                    <div className="space-y-2 pt-1">
                      {uniqueUserDocuments.length === 0 ? (
                        <p className="text-xs text-stone-400 italic">No library documents found. You can upload a file instead.</p>
                      ) : (
                        <div className="max-h-40 overflow-y-auto space-y-1.5 pr-1 border border-stone-200 rounded-lg p-2 bg-[#FAF8F5]">
                          {uniqueUserDocuments.map((doc) => (
                            <button
                              key={doc.id}
                              type="button"
                              onClick={() => setSelectedDocumentId(doc.id)}
                              className={`w-full text-left p-2 rounded text-xs transition cursor-pointer flex items-center justify-between ${
                                selectedDocumentId === doc.id
                                  ? 'bg-[#1C1A17] text-[#FAF8F5]'
                                  : 'hover:bg-stone-200/60 text-[#1C1A17]'
                              }`}
                            >
                              <span className="truncate">{doc.file_name || doc.title || 'Document'}</span>
                              <span className="text-[10px] opacity-70 ml-2 font-mono">
                                {doc.page_count ? `${doc.page_count}p` : ''}
                              </span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {materialSourceMode === 'upload' && (
                    <div className="pt-1">
                      <input
                        type="file"
                        ref={fileInputRef}
                        onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                        accept=".pdf,.txt,.docx"
                        className="w-full text-xs text-stone-600 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-stone-100 file:text-[#1C1A17] hover:file:bg-stone-200 cursor-pointer"
                      />
                    </div>
                  )}

                  {materialSourceMode === 'session' && (
                    <div className="pt-1">
                      <select
                        value={selectedSessionId}
                        onChange={(e) => setSelectedSessionId(e.target.value)}
                        className="w-full text-xs p-2.5 rounded-lg border border-stone-200 bg-white text-[#1C1A17] focus:outline-none focus:border-[#1C1A17]"
                      >
                        <option value="">Select a Chat Room Session</option>
                        {sessions.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.session_title || `Session ${s.id.slice(0, 8)}`}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>

                {/* Step 2: Target Date & Daily Hours */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold uppercase tracking-wider text-[#8C8479]">
                      2. Target Date
                    </label>
                    <input
                      type="date"
                      value={targetDate}
                      onChange={(e) => setTargetDate(e.target.value)}
                      className="w-full text-xs p-2.5 rounded-lg border border-stone-200 bg-white text-[#1C1A17] focus:outline-none focus:border-[#1C1A17]"
                      required
                    />
                  </div>

                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-[#8C8479]">
                      <span>3. Hours / Day</span>
                      <span className="text-[#1C1A17] font-mono">{hoursPerDay} hrs</span>
                    </div>
                    <input
                      type="range"
                      min="1.0"
                      max="6.0"
                      step="0.5"
                      value={hoursPerDay}
                      onChange={(e) => setHoursPerDay(parseFloat(e.target.value))}
                      className="w-full accent-[#1C1A17] cursor-pointer mt-2"
                    />
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="pt-3 border-t border-stone-100 flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setShowCreateModal(false)}
                    className="px-4 py-2 text-xs font-medium text-stone-600 hover:text-stone-900 cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={generating}
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[#1C1A17] text-[#FAF8F5] text-xs font-semibold hover:bg-[#332F2A] disabled:opacity-60 transition shadow-xs cursor-pointer"
                  >
                    {generating ? (
                      <>
                        <RefreshCw size={14} className="animate-spin text-[#9E6B38]" />
                        <span>Architecting Roadmap...</span>
                      </>
                    ) : (
                      <>
                        <Sparkles size={14} className="text-[#9E6B38]" />
                        <span>Generate Roadmap</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ─── AI STUDY NOTES MODAL ─── */}
      <AnimatePresence>
        {activeNotesModal && (
          <div className="fixed inset-0 z-50 bg-[#1C1A17]/60 backdrop-blur-xs flex items-center justify-center p-4 overflow-y-auto">
            <motion.div
              initial={{ opacity: 0, scale: 0.97 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.97 }}
              className="w-full max-w-3xl max-h-[85vh] bg-white rounded-2xl p-6 sm:p-8 border border-stone-200 shadow-2xl flex flex-col space-y-4"
            >
              {/* Modal Top Bar */}
              <div className="flex items-center justify-between pb-3 border-b border-stone-200">
                <div>
                  <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#9E6B38]">
                    Day {activeNotesModal.dayNum} Briefing
                  </span>
                  <h3 className="text-lg sm:text-xl font-serif font-semibold text-[#1C1A17]">
                    {activeNotesModal.topic}
                  </h3>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => copyNotes(activeNotesModal.notes)}
                    className="p-1.5 rounded-lg text-stone-500 hover:text-[#1C1A17] hover:bg-stone-100 cursor-pointer"
                    title="Copy to Clipboard"
                  >
                    {copied ? <Check size={16} className="text-emerald-600" /> : <Copy size={16} />}
                  </button>

                  <button
                    onClick={() => downloadMarkdown(activeNotesModal.notes, activeNotesModal.topic)}
                    className="p-1.5 rounded-lg text-stone-500 hover:text-[#1C1A17] hover:bg-stone-100 cursor-pointer"
                    title="Download as Markdown"
                  >
                    <Download size={16} />
                  </button>

                  <button
                    onClick={() => speakNotes(activeNotesModal.notes)}
                    className="p-1.5 rounded-lg text-stone-500 hover:text-[#1C1A17] hover:bg-stone-100 cursor-pointer"
                    title={isSpeaking ? 'Stop Read Aloud' : 'Read Aloud'}
                  >
                    {isSpeaking ? <VolumeX size={16} className="text-rose-600" /> : <Volume2 size={16} />}
                  </button>

                  <button
                    onClick={() => {
                      if (isSpeaking) window.speechSynthesis.cancel()
                      setIsSpeaking(false)
                      setActiveNotesModal(null)
                    }}
                    className="p-1.5 rounded-lg text-stone-400 hover:text-[#1C1A17] hover:bg-stone-100 cursor-pointer"
                  >
                    <X size={18} />
                  </button>
                </div>
              </div>

              {/* Notes Body Content with Markdown & KaTeX */}
              <div className="flex-1 overflow-y-auto pr-2 space-y-3">
                {activeNotesModal.loading ? (
                  <div className="py-16 text-center space-y-3">
                    <RefreshCw size={24} className="animate-spin text-[#9E6B38] mx-auto" />
                    <p className="text-xs font-semibold text-[#5C564E]">Synthesizing AI Study Notes...</p>
                  </div>
                ) : (
                  <div className="prose prose-sm max-w-none text-[#1C1A17]">
                    <ReactMarkdown
                      remarkPlugins={[remarkMath, remarkGfm]}
                      rehypePlugins={[rehypeKatex]}
                      components={{
                        h1: ({ children }) => (
                          <h1 className="text-xl font-serif font-semibold text-[#1C1A17] mt-4 mb-2 pb-1 border-b border-stone-200">
                            {children}
                          </h1>
                        ),
                        h2: ({ children }) => (
                          <h2 className="text-base font-serif font-semibold text-[#1C1A17] mt-5 mb-2 flex items-center gap-2">
                            {children}
                          </h2>
                        ),
                        h3: ({ children }) => (
                          <h3 className="text-sm font-semibold text-[#1C1A17] mt-3 mb-1">
                            {children}
                          </h3>
                        ),
                        p: ({ children }) => (
                          <p className="text-xs sm:text-sm text-[#5C564E] leading-relaxed mb-3">
                            {children}
                          </p>
                        ),
                        ul: ({ children }) => (
                          <ul className="list-disc pl-5 space-y-1 text-xs sm:text-sm text-[#5C564E] mb-3">
                            {children}
                          </ul>
                        ),
                        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                        blockquote: ({ children }) => (
                          <blockquote className="border-l-2 border-[#9E6B38] pl-3 py-1 my-2 bg-[#9E6B38]/5 text-xs text-[#1C1A17] italic">
                            {children}
                          </blockquote>
                        ),
                        code({ className, children }: any) {
                          const match = /language-(\w+)/.exec(className || '')
                          const isMermaid = match && match[1] === 'mermaid'
                          const isInline = !match
                          const codeStr = String(children).replace(/\n$/, '')

                          if (isMermaid) {
                            return <MermaidDiagram chart={codeStr} />
                          }
                          if ((match && match[1] === 'svg') || (codeStr.includes('<svg') && codeStr.includes('</svg>'))) {
                            return <InlineSVGDiagram svg={codeStr} />
                          }
                          if (isInline) {
                            return (
                              <code className="bg-stone-100 text-[#1C1A17] px-1.5 py-0.5 rounded text-xs font-mono font-semibold">
                                {children}
                              </code>
                            )
                          }
                          return (
                            <pre className="bg-[#1C1A17] text-[#FAF8F5] p-3.5 rounded-xl overflow-x-auto text-xs font-mono my-2">
                              <code>{children}</code>
                            </pre>
                          )
                        },
                      }}
                    >
                      {activeNotesModal.notes}
                    </ReactMarkdown>
                  </div>
                )}
              </div>

              {/* Bottom Trigger to Quiz */}
              <div className="pt-3 border-t border-stone-200 flex items-center justify-between">
                <span className="text-[11px] text-[#8C8479]">
                  Finished reading? Complete the check to verify mastery.
                </span>
                <button
                  type="button"
                  onClick={() => {
                    if (isSpeaking) window.speechSynthesis.cancel()
                    setIsSpeaking(false)
                    if (activeNotesModal) {
                      const dayNum = activeNotesModal.dayNum
                      const dayItem = currentPlan?.schedule.find((s) => s.day === dayNum)
                      const conceptsStr = dayItem?.key_concepts?.length
                        ? ` (Key Concepts: ${dayItem.key_concepts.join(', ')})`
                        : ''
                      const topic = activeNotesModal.topic + conceptsStr
                      setActiveNotesModal(null)
                      setDayQuizModal({ dayNum, topic })
                    }
                  }}
                  className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg bg-[#1C1A17] text-[#FAF8F5] hover:bg-[#332F2A] cursor-pointer shadow-xs"
                >
                  <span>Take Day Quiz</span>
                  <Target size={14} />
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ─── DAY MASTERY QUIZ MODAL ─── */}
      {dayQuizModal && (
        <GamifiedQuizGame
          isOpen={!!dayQuizModal}
          onClose={() => setDayQuizModal(null)}
          initialTopic={dayQuizModal.topic}
          onQuizComplete={handleDayQuizComplete}
        />
      )}

      {/* ─── UPGRADE MODAL ─── */}
      <UpgradeModal
        isOpen={upgradeModalInfo.open}
        exceededFileName={upgradeModalInfo.fileName}
        exceededFileSizeMb={upgradeModalInfo.sizeMb}
        onClose={() => setUpgradeModalInfo({ open: false })}
      />
    </div>
  )
}
