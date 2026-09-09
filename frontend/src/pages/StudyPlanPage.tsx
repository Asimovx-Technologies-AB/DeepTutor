import { useState, useRef, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import MermaidDiagram from '../components/MermaidDiagram'
import {
  Calendar,
  Sparkles,
  Clock,
  CheckCircle2,
  BookOpen,
  FileText,
  RefreshCw,
  Plus,
  Trash2,
  ChevronRight,
  Brain,
  Target,
  UploadCloud,
  CheckSquare,
  AlertCircle,
  Volume2,
  Copy,
  Check,
  X,
  Search,
  Layers,
  ArrowRight
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
  const [materialSourceMode, setMaterialSourceMode] = useState<'upload' | 'library' | 'session'>('library')
  const [selectedDocumentId, setSelectedDocumentId] = useState<string>('')
  const [selectedSessionId, setSelectedSessionId] = useState<string>('')
  const [modalDocSearchQuery, setModalDocSearchQuery] = useState<string>('')
  const [targetDate, setTargetDate] = useState<string>(() => {
    const d = new Date()
    d.setDate(d.getDate() + 10)
    return d.toISOString().split('T')[0]
  })
  const [hoursPerDay, setHoursPerDay] = useState<number>(2.0)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)

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

  // Fetch my study plans with 60s stale cache
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
    // 1. Check if the study_notes is already a full structured brief (has markdown headers and substantive text)
    const isFullNote =
      dayItem.study_notes &&
      dayItem.study_notes.trim().length > 150 &&
      (dayItem.study_notes.includes('##') || dayItem.study_notes.includes('#'))

    // 2. Zero-token instant open: if already a full structured note and not force-regenerating, open immediately!
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
      notes: `### ${dayItem.topic}\n\nGenerating comprehensive AI Study Notes from document context...`,
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
        // Save to React Query client-side cache so reopening uses 0 tokens & 0ms latency
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
              notes: `### Could Not Generate Notes\n\n**Error:** ${errMsg}\n\nPlease try again. If the problem persists, check that the backend is running and your PDF is uploaded for this topic.`,
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
        topicId = `plan_${Date.now()}`
        await documentsApi.upload(topicId, selectedFile)
      } else if (materialSourceMode === 'library' && selectedDocumentId) {
        const doc = userDocuments.find((d: any) => d.id === selectedDocumentId)
        if (doc) {
          topicId = doc.topic_id || doc.id || 'general'
          sessionId = doc.topic_id || doc.id
        }
      } else if (materialSourceMode === 'session' && selectedSessionId) {
        sessionId = selectedSessionId
        const session = sessions.find((s) => s.id === selectedSessionId)
        topicId = session?.topic_id || selectedSessionId || 'general'
      }

      // Generate Study Plan
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
      alert(err.response?.data?.detail || 'Failed to generate study plan. Make sure Ollama is running.')
    } finally {
      setGenerating(false)
    }
  }

  const completedCount = currentPlan?.completed_days?.length ?? 0
  const totalScheduleDays = currentPlan?.schedule?.length ?? 1
  const completionPct = Math.round((completedCount / totalScheduleDays) * 100)

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8 bg-transparent">
      {/* ─── HEADER ─── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Calendar size={18} className="text-[#4F46E5]" />
            <span className="text-xs font-black text-[#4F46E5] uppercase tracking-widest bg-[#EEF2FF] px-2.5 py-0.5 rounded-full border border-[#4F46E5]/20">
              {t.studyPlan.engineLabel}
            </span>
          </div>
          <h1 className="text-3xl font-black text-[#3C3C3C] tracking-tight">{t.studyPlan.title}</h1>
          <p className="text-[#777777] text-sm mt-0.5 font-medium">
            {t.studyPlan.subtitle}
          </p>
        </div>

        <button
          onClick={() => setShowCreateModal(true)}
          className="btn-primary flex items-center gap-2 py-2.5 px-5 text-xs elevation-2 self-start md:self-auto cursor-pointer"
        >
          <Plus size={16} /> {t.studyPlan.createNew}
        </button>
      </div>

      {isLoading ? (
        <div className="p-12 text-center">
          <RefreshCw size={28} className="animate-spin text-[#4F46E5] mx-auto mb-3" />
          <p className="text-xs font-bold text-[#777777]">Loading study plans...</p>
        </div>
      ) : plans.length === 0 ? (
        /* ─── EMPTY STATE ─── */
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="glass-card p-12 text-center border border-[#E2E8F0] max-w-xl mx-auto space-y-5"
        >
          <motion.div animate={{ y: [0, -10, 0] }} transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }} className="w-24 h-24 mx-auto select-none pointer-events-none mb-2">
            <img src="/assets/illustrations/mountain_goal.png" alt="Study Plan" className="w-full h-full object-contain" style={{ filter: 'hue-rotate(200deg) saturate(1.2)' }} />
          </motion.div>
          <div>
            <h2 className="text-xl font-black text-[#3C3C3C]">Nothing here yet.</h2>
            <p className="text-xs text-[#777777] mt-2 max-w-md mx-auto leading-relaxed font-medium">
              Start a learning path and your progress will appear here.
            </p>
          </div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="btn-primary flex items-center gap-2 mx-auto py-2.5 px-6 text-xs elevation-2 cursor-pointer"
          >
            <Sparkles size={15} /> Start Learning
          </button>
        </motion.div>
      ) : (
        /* ─── ACTIVE STUDY PLAN DASHBOARD ─── */
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Left: Saved Plans Sidebar */}
          <div className="space-y-3">
            <h3 className="text-xs font-black text-[#AFAFAF] uppercase tracking-wider px-1">
              Your Saved Plans ({plans.length})
            </h3>
            <div className="space-y-2">
              {plans.map((p) => {
                const isSel = (currentPlan?.id ?? plans[0]?.id) === p.id
                const pct = Math.round(((p.completed_days?.length ?? 0) / (p.schedule?.length || 1)) * 100)

                return (
                  <button
                    key={p.id}
                    onClick={() => setActivePlanId(p.id)}
                    className={`w-full text-left p-3.5 rounded-[1.5rem] border transition-all cursor-pointer flex flex-col gap-2 hover:scale-[1.02] active:scale-[0.98] ${
                      isSel
                        ? 'bg-[#EEF2FF] text-[#4F46E5] border-[#4F46E5]/40 elevation-2'
                        : 'bg-white text-[#3C3C3C] border-[#E2E8F0] hover:border-[#4F46E5]/40 hover:bg-[#FFFFFF]'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className={`text-[10px] font-black uppercase px-2 py-0.5 rounded-md ${
                        isSel ? 'bg-[#4F46E5] text-white' : 'bg-[#E5E5E5] text-[#777777]'
                      }`}>
                        Target: {p.target_date}
                      </span>
                      <span className={`text-xs font-black ${isSel ? 'text-[#4F46E5]' : 'text-[#777777]'}`}>
                        {pct}%
                      </span>
                    </div>

                    <p className="text-xs font-extrabold truncate leading-snug">{p.title}</p>

                    <div className="flex items-center justify-between text-[10px] font-semibold opacity-80 mt-1">
                      <span>{p.total_days} Days Schedule</span>
                      <span>{p.hours_per_day} hrs/day</span>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Right: Detailed Plan Timeline */}
          {currentPlan && (
            <div className="lg:col-span-3 space-y-6">
              {/* Quiz Verification Result Banner */}
              {quizVerificationMessage && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`p-4 rounded-[1.5rem] border flex items-center justify-between text-xs font-extrabold elevation-1 ${
                    quizVerificationMessage.passed
                      ? 'bg-[#D7FFB8] text-[#46A302] border-[#58CC02]/40'
                      : 'bg-[#EEF2FF] text-[#FF4B4B] border-[#4F46E5]/40'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <Sparkles size={16} className={quizVerificationMessage.passed ? 'text-[#58CC02]' : 'text-[#4F46E5]'} />
                    <span>{quizVerificationMessage.message}</span>
                  </div>
                  <button
                    onClick={() => setQuizVerificationMessage(null)}
                    className="p-1 text-[#AFAFAF] hover:text-[#3C3C3C] cursor-pointer"
                  >
                    <X size={16} />
                  </button>
                </motion.div>
              )}

              {/* Plan Overview Card */}
              <div className="glass-card p-6 border border-[#E2E8F0] bg-gradient-to-r from-[#FFFFFF] via-white to-[#EEF2FF] space-y-4 elevation-2">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    {(() => {
                      const isOverdue =
                        currentPlan.target_date &&
                        new Date(currentPlan.target_date).getTime() < new Date().setHours(0, 0, 0, 0) &&
                        completionPct < 100
                      return (
                        <span
                          className={`text-[10px] font-black uppercase tracking-widest px-2.5 py-0.5 rounded-md border ${
                            isOverdue
                              ? 'bg-[#FFD1D1] text-[#FF4B4B] border-[#FF4B4B]/30 animate-pulse'
                              : 'bg-[#EEF2FF] text-[#4F46E5] border-[#4F46E5]/20'
                          }`}
                        >
                          {isOverdue ? `Target Overdue: ${currentPlan.target_date}` : `Target Finish Date: ${currentPlan.target_date}`}
                        </span>
                      )
                    })()}
                    <h2 className="text-xl font-black text-[#3C3C3C] mt-2">{currentPlan.title}</h2>
                  </div>

                  <button
                    onClick={() => deletePlanMutation.mutate(currentPlan.id)}
                    className="p-2 text-[#AFAFAF] hover:text-[#FF4B4B] hover:bg-[#FFD1D1] rounded-[1.25rem] transition-colors self-start sm:self-auto"
                    title="Delete Study Plan"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>

                {/* Progress bar */}
                <div className="space-y-1.5 pt-2">
                  <div className="flex items-center justify-between text-xs font-extrabold text-[#777777]">
                    <span>{uiLanguage === 'sv' ? 'Total studieframgång' : 'Overall Study Completion'}</span>
                    <span className="text-[#58CC02]">
                      {completedCount} {uiLanguage === 'sv' ? 'av' : 'of'} {currentPlan.total_days} {uiLanguage === 'sv' ? 'dagar slutförda' : 'Days Completed'} ({completionPct}%)
                    </span>
                  </div>
                  <div className="w-full bg-[#E5E5E5] rounded-full h-2 overflow-hidden">
                    <motion.div
                      className="bg-[#58CC02] h-full rounded-full"
                      animate={{ width: `${completionPct}%` }}
                      transition={{ duration: 0.5 }}
                    />
                  </div>
                </div>
              </div>

              {/* Day-by-Day Timeline Schedule */}
              <div className="space-y-4">
                <h3 className="text-sm font-black text-[#3C3C3C] flex items-center gap-2">
                  <Clock size={16} className="text-[#4F46E5]" />
                  {uiLanguage === 'sv' ? `Dag-för-dag studieplanering (${currentPlan.schedule?.length ?? 0} dagar)` : `Day-by-Day Study Schedule (${currentPlan.schedule?.length ?? 0} Days)`}
                </h3>

                <div className="space-y-3">
                  {currentPlan.schedule?.map((dayItem, idx) => {
                    const isDone = currentPlan.completed_days?.includes(dayItem.day)
                    const prevPhase = idx > 0 ? currentPlan.schedule[idx - 1].phase : null
                    const isNewPhase = dayItem.phase && dayItem.phase !== prevPhase

                    return (
                      <div key={dayItem.day} className="space-y-3">
                        {isNewPhase && (
                          <div className="pt-3 pb-1">
                            <div className="flex items-center gap-2.5">
                              <span className="text-xs font-black text-[#4F46E5] bg-[#EEF2FF] border border-[#4F46E5]/30 px-3 py-1 rounded-[1.25rem] uppercase tracking-wider elevation-1">
                                {dayItem.phase}
                              </span>
                              <div className="flex-1 h-[1px] bg-[#E2E8F0]" />
                            </div>
                          </div>
                        )}

                        <motion.div
                          initial={{ opacity: 0, y: 6 }}
                          animate={{ opacity: 1, y: 0 }}
                          className={`p-5 rounded-[1.5rem] border transition-all ${
                            isDone
                              ? 'bg-[#D7FFB8]/50 border-[#58CC02]/30 elevation-1'
                              : 'bg-white border-[#E2E8F0] elevation-1 hover:border-[#4F46E5]/40'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div className="flex items-start gap-3.5">
                              {/* Status Indicator (completed via quiz only) */}
                              <div
                                className={`w-7 h-7 rounded-[1.25rem] border flex items-center justify-center mt-0.5 flex-shrink-0 ${
                                  isDone
                                    ? 'bg-[#58CC02] border-[#58CC02] text-white elevation-1'
                                    : 'bg-[#F7F7F7] border-[#E2E8F0] text-transparent'
                                }`}
                                title={isDone ? (uiLanguage === 'sv' ? 'Klarade Dags-Quiz (≥70%)' : 'Passed Day Quiz (≥70%)') : (uiLanguage === 'sv' ? 'Gör Dags-Quiz för att slutföra' : 'Pass the Day Quiz to complete')}
                              >
                                <CheckCircle2 size={18} />
                              </div>

                              <div>
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="text-xs font-black text-[#4F46E5] bg-[#EEF2FF] px-2 py-0.5 rounded-md border border-[#4F46E5]/20">
                                    {uiLanguage === 'sv' ? 'Dag' : 'Day'} {dayItem.day}
                                  </span>
                                  {dayItem.phase && (
                                    <span className="text-[10px] font-bold text-[#58CC02] bg-[#D7FFB8] px-2 py-0.5 rounded-md border border-[#58CC02]/20">
                                      {dayItem.phase.split(':')[0]}
                                    </span>
                                  )}
                                  <span className="text-[11px] font-semibold text-[#AFAFAF] flex items-center gap-1">
                                    <Clock size={11} /> {dayItem.estimated_hours} {uiLanguage === 'sv' ? 'tim' : 'hrs'}
                                  </span>
                                </div>

                                <h4 className={`text-sm font-extrabold mt-1.5 ${isDone ? 'line-through text-[#AFAFAF]' : 'text-[#3C3C3C]'}`}>
                                  {dayItem.topic}
                                </h4>

                                <p className="text-xs text-[#777777] mt-1 leading-relaxed font-medium">
                                  {dayItem.focus}
                                </p>

                                {/* Recommended Action */}
                                {dayItem.recommended_action && (
                                  <div className="mt-3 p-2.5 bg-[#FFFFFF] border border-[#E2E8F0] rounded-[1.25rem] text-xs text-[#3C3C3C] flex items-center gap-2">
                                    <Brain size={13} className="text-[#4F46E5] flex-shrink-0" />
                                    <span><strong className="text-[#4F46E5]">{uiLanguage === 'sv' ? 'Åtgärd:' : 'Action:'}</strong> {dayItem.recommended_action}</span>
                                  </div>
                                )}

                                {/* Key Concepts Pills */}
                                {dayItem.key_concepts && dayItem.key_concepts.length > 0 && (
                                  <div className="flex flex-wrap gap-1.5 mt-3">
                                    {dayItem.key_concepts.map((concept, idx) => (
                                      <span
                                        key={idx}
                                        className="text-[10px] font-bold bg-[#D7FFB8] text-[#46A302] border border-[#58CC02]/20 px-2 py-0.5 rounded-lg"
                                      >
                                        {concept}
                                      </span>
                                    ))}
                                  </div>
                                )}

                                {/* Action Buttons: Notes & Day Mastery Quiz */}
                                <div className="pt-3 flex flex-wrap items-center gap-2.5">
                                  <button
                                    type="button"
                                    onClick={() => handleOpenStudyNotes(dayItem)}
                                    className="btn-primary py-2 px-3.5 text-xs font-bold flex items-center gap-1.5 transition-all cursor-pointer elevation-1 active:scale-95"
                                  >
                                    <BookOpen size={14} /> {uiLanguage === 'sv' ? 'Visa AI-Studieanteckningar' : 'View AI Study Notes'}
                                  </button>

                                  <button
                                    type="button"
                                    onClick={() => {
                                      const conceptsStr = dayItem.key_concepts?.length
                                        ? ` (Key Concepts: ${dayItem.key_concepts.join(', ')})`
                                        : ''
                                      setDayQuizModal({ dayNum: dayItem.day, topic: dayItem.topic + conceptsStr })
                                    }}
                                    className={`py-2 px-3.5 text-xs font-extrabold rounded-[1.25rem] border flex items-center gap-1.5 transition-all cursor-pointer elevation-1 active:scale-95 ${
                                      isDone
                                        ? 'bg-[#D7FFB8] text-[#46A302] border-[#58CC02]/30 hover:bg-[#d5e8d8]'
                                        : 'bg-[#EEF2FF] text-[#4F46E5] border-[#4F46E5]/40 hover:bg-[#E0E7FF]'
                                    }`}
                                  >
                                    <Target size={14} />
                                    {isDone ? (uiLanguage === 'sv' ? 'Gör om Dags-Quiz (Klar)' : 'Retake Day Quiz (Passed)') : (uiLanguage === 'sv' ? 'Gör Dags-Quiz (Klar ≥ 70%)' : 'Take Day Quiz (Pass ≥ 70%)')}
                                  </button>
                                </div>
                              </div>
                            </div>
                          </div>
                        </motion.div>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ─── CREATE / GENERATE STUDY PLAN MODAL ─── */}
      <AnimatePresence>
        {showCreateModal && (
          <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-md flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 15 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 15 }}
              transition={{ duration: 0.2 }}
              className="w-full max-w-2xl bg-white rounded-[2.5rem] p-6 sm:p-9 shadow-2xl border border-slate-200/90 relative overflow-hidden my-auto"
            >
              {/* Modal Header */}
              <div className="flex items-start justify-between gap-4 mb-6 pb-4 border-b border-slate-100">
                <div className="flex items-center gap-3.5">
                  <div className="w-12 h-12 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shadow-2xs">
                    <Sparkles size={24} />
                  </div>
                  <div>
                    <h3 className="text-xl font-black text-slate-900 font-sans tracking-tight">Generate AI Study Plan</h3>
                    <p className="text-xs text-slate-500 font-medium mt-0.5">
                      Personalized day-by-day revision roadmap grounded in your study material
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="p-2 rounded-full text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition cursor-pointer"
                >
                  <X size={18} />
                </button>
              </div>

              <form onSubmit={handleGeneratePlan} className="space-y-6">
                {/* ─── Step 1: Select Study Material ─── */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs font-bold text-slate-700 uppercase tracking-wider block">
                      1. Choose Study Material
                    </label>
                    <span className="text-xs font-medium text-indigo-600">
                      {materialSourceMode === 'library' && uniqueUserDocuments.length > 0 && `${uniqueUserDocuments.length} available in library`}
                    </span>
                  </div>

                  {/* Segmented Control */}
                  <div className="flex p-1.5 bg-slate-100 rounded-2xl mb-3.5 gap-1.5 border border-slate-200/60">
                    <button
                      type="button"
                      onClick={() => {
                        setMaterialSourceMode('library')
                        setSelectedFile(null)
                        setSelectedSessionId('')
                      }}
                      className={`flex-1 py-2 px-3 rounded-xl text-xs font-bold transition-all cursor-pointer flex items-center justify-center gap-2 ${
                        materialSourceMode === 'library'
                          ? 'bg-white text-indigo-700 shadow-xs border border-slate-200/60'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      <Layers size={14} className={materialSourceMode === 'library' ? 'text-indigo-600' : 'text-slate-400'} />
                      <span>From Library ({uniqueUserDocuments.length})</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        setMaterialSourceMode('upload')
                        setSelectedDocumentId('')
                        setSelectedSessionId('')
                      }}
                      className={`flex-1 py-2 px-3 rounded-xl text-xs font-bold transition-all cursor-pointer flex items-center justify-center gap-2 ${
                        materialSourceMode === 'upload'
                          ? 'bg-white text-indigo-700 shadow-xs border border-slate-200/60'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      <UploadCloud size={14} className={materialSourceMode === 'upload' ? 'text-indigo-600' : 'text-slate-400'} />
                      <span>Upload New File</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        setMaterialSourceMode('session')
                        setSelectedFile(null)
                        setSelectedDocumentId('')
                      }}
                      className={`flex-1 py-2 px-3 rounded-xl text-xs font-bold transition-all cursor-pointer flex items-center justify-center gap-2 ${
                        materialSourceMode === 'session'
                          ? 'bg-white text-indigo-700 shadow-xs border border-slate-200/60'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      <BookOpen size={14} className={materialSourceMode === 'session' ? 'text-indigo-600' : 'text-slate-400'} />
                      <span>Chat Room ({sessions.length})</span>
                    </button>
                  </div>

                  {/* Mode A: Select from Library */}
                  {materialSourceMode === 'library' && (
                    <div className="space-y-3">
                      {uniqueUserDocuments.length > 4 && (
                        <div className="relative">
                          <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                          <input
                            type="text"
                            value={modalDocSearchQuery}
                            onChange={(e) => setModalDocSearchQuery(e.target.value)}
                            placeholder="Search your library materials..."
                            className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-800 focus:outline-none focus:border-indigo-400 focus:bg-white"
                          />
                        </div>
                      )}

                      {uniqueUserDocuments.length === 0 ? (
                        <div className="p-8 rounded-3xl bg-slate-50 border-2 border-dashed border-slate-200 text-center">
                          <BookOpen size={28} className="text-slate-400 mx-auto mb-2 opacity-60" />
                          <p className="text-sm font-bold text-slate-700 mb-1">No previously uploaded materials found</p>
                          <p className="text-xs text-slate-400 mb-3">Upload your first PDF textbook or chapter notes to get started.</p>
                          <button
                            type="button"
                            onClick={() => setMaterialSourceMode('upload')}
                            className="px-4 py-2 rounded-xl bg-indigo-600 text-white text-xs font-bold hover:bg-indigo-700 transition cursor-pointer"
                          >
                            Upload Study PDF Now →
                          </button>
                        </div>
                      ) : (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 max-h-56 overflow-y-auto pr-1">
                          {filteredModalDocuments.map((doc: any) => {
                            const isSelected = selectedDocumentId === doc.id
                            return (
                              <div
                                key={doc.id}
                                onClick={() => setSelectedDocumentId(doc.id)}
                                className={`p-3.5 rounded-2xl border-2 transition-all cursor-pointer flex items-center justify-between gap-3 text-left ${
                                  isSelected
                                    ? 'bg-indigo-50/90 border-indigo-500 text-indigo-950 shadow-sm'
                                    : 'bg-slate-50/70 border-slate-200/80 text-slate-700 hover:bg-white hover:border-slate-300'
                                }`}
                              >
                                <div className="flex items-center gap-3 min-w-0">
                                  <div
                                    className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 border ${
                                      isSelected
                                        ? 'bg-indigo-600 text-white border-indigo-600'
                                        : 'bg-white text-indigo-600 border-slate-200'
                                    }`}
                                  >
                                    <FileText size={16} />
                                  </div>
                                  <div className="min-w-0">
                                    <h4 className="text-xs font-bold truncate text-slate-900 max-w-[170px]" title={doc.file_name}>
                                      {doc.file_name}
                                    </h4>
                                    <div className="flex items-center gap-1.5 mt-0.5">
                                      <span className="text-[10px] font-semibold text-indigo-700 bg-indigo-100/70 px-1.5 py-0.2 rounded-md">
                                        {doc.detected_subject || 'General Study'}
                                      </span>
                                      {doc.key_topics?.length > 0 && (
                                        <span className="text-[10px] text-slate-400 truncate">
                                          • {doc.key_topics.length} topics
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                </div>

                                <div className="shrink-0">
                                  {isSelected ? (
                                    <div className="w-5 h-5 rounded-full bg-indigo-600 text-white flex items-center justify-center shadow-xs">
                                      <Check size={12} strokeWidth={3} />
                                    </div>
                                  ) : (
                                    <div className="w-5 h-5 rounded-full border-2 border-slate-300" />
                                  )}
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Mode B: Upload New File */}
                  {materialSourceMode === 'upload' && (
                    <div>
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".pdf,.png,.jpg,.jpeg,.webp,.bmp,.docx,.doc,.csv,.xlsx,.xls,.pptx,.ppt,.html,.json,.txt,.md"
                        className="hidden"
                        onChange={(e) => {
                          const file = e.target.files?.[0]
                          if (file) {
                            setSelectedFile(file)
                          }
                        }}
                      />
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className={`w-full p-6 border-2 border-dashed rounded-3xl text-xs font-semibold flex flex-col items-center justify-center gap-2.5 transition-all cursor-pointer ${
                          selectedFile
                            ? 'bg-indigo-50/80 border-indigo-400 text-indigo-950'
                            : 'bg-slate-50 border-slate-200 hover:bg-slate-100/80 hover:border-slate-300 text-slate-600'
                        }`}
                      >
                        <div className="w-12 h-12 rounded-2xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center">
                          <UploadCloud size={24} />
                        </div>
                        <div className="text-center">
                          <span className="font-bold text-sm text-slate-900 block truncate max-w-xs">
                            {selectedFile ? selectedFile.name : 'Click to select study PDF / Document'}
                          </span>
                          <span className="text-[11px] text-slate-400 font-normal">
                            Supports PDF, DOCX, Markdown, Lecture Slides, and Images
                          </span>
                        </div>
                      </button>
                    </div>
                  )}

                  {/* Mode C: Pick Chat Room */}
                  {materialSourceMode === 'session' && (
                    <div>
                      {sessions.length === 0 ? (
                        <div className="p-6 rounded-2xl bg-slate-50 border border-slate-200 text-center text-xs text-slate-400">
                          No active chat notebooks found.
                        </div>
                      ) : (
                        <select
                          value={selectedSessionId}
                          onChange={(e) => setSelectedSessionId(e.target.value)}
                          className="w-full bg-slate-50 hover:bg-slate-100/80 focus:bg-white border border-slate-200 text-xs font-semibold text-slate-900 rounded-2xl px-4 py-3.5 focus:outline-none focus:border-indigo-500"
                        >
                          <option value="">Choose an active chat notebook...</option>
                          {sessions.map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.session_title || `Chat Notebook #${s.id.slice(-4)}`}
                            </option>
                          ))}
                        </select>
                      )}
                    </div>
                  )}
                </div>

                {/* ─── Step 2 & 3: Target Date & Daily Study Time Grid ─── */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 pt-1">
                  {/* Target Date Picker */}
                  <div>
                    <label className="text-xs font-bold text-slate-700 uppercase tracking-wider block mb-2">
                      2. Target Completion Date
                    </label>
                    <input
                      type="date"
                      required
                      value={targetDate}
                      onChange={(e) => setTargetDate(e.target.value)}
                      min={new Date().toISOString().split('T')[0]}
                      className="w-full bg-slate-50 hover:bg-slate-100/80 focus:bg-white border border-slate-200 rounded-2xl px-4 py-3 text-sm text-slate-900 font-bold focus:outline-none focus:border-indigo-500 transition-all shadow-2xs"
                    />
                    <p className="text-[11px] text-slate-400 mt-1.5 font-medium">
                      Remaining days are automatically calculated for your schedule.
                    </p>
                  </div>

                  {/* Daily Study Time */}
                  <div>
                    <label className="text-xs font-bold text-slate-700 uppercase tracking-wider block mb-2">
                      3. Daily Study Time
                    </label>
                    <div className="grid grid-cols-4 gap-1.5">
                      {[1.0, 2.0, 3.0, 4.0].map((hrs) => (
                        <button
                          key={hrs}
                          type="button"
                          onClick={() => setHoursPerDay(hrs)}
                          className={`py-3 rounded-2xl text-xs font-bold border transition-all cursor-pointer flex flex-col items-center justify-center ${
                            hoursPerDay === hrs
                              ? 'bg-indigo-600 text-white border-indigo-600 shadow-md shadow-indigo-200 scale-[1.02]'
                              : 'bg-slate-50 hover:bg-slate-100 text-slate-700 border-slate-200/80'
                          }`}
                        >
                          <span className="text-sm font-black">{hrs}h</span>
                          <span className="text-[9px] opacity-80 uppercase font-semibold">/day</span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* ─── Footer Action Buttons ─── */}
                <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => setShowCreateModal(false)}
                    className="py-3 px-5 rounded-2xl text-xs font-bold text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition cursor-pointer"
                  >
                    Cancel
                  </button>

                  <button
                    type="submit"
                    disabled={
                      generating ||
                      (materialSourceMode === 'library' && !selectedDocumentId && uniqueUserDocuments.length > 0) ||
                      (materialSourceMode === 'upload' && !selectedFile)
                    }
                    className="py-3 px-7 rounded-2xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold flex items-center gap-2 shadow-lg shadow-indigo-500/25 transition-all cursor-pointer disabled:opacity-50"
                  >
                    {generating ? (
                      <>
                        <RefreshCw size={15} className="animate-spin" />
                        <span>Building Your Schedule...</span>
                      </>
                    ) : (
                      <>
                        <Sparkles size={15} />
                        <span>Generate Schedule</span>
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
          <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="w-full max-w-2xl bg-white rounded-[2rem] p-7 shadow-2xl border border-border relative overflow-hidden flex flex-col max-h-[85vh]"
            >
              {/* Header */}
              <div className="flex items-center justify-between border-b border-slate-100 pb-4 mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-[1.5rem] bg-[#111111] text-white flex items-center justify-center font-black">
                    {activeNotesModal.dayNum}
                  </div>
                  <div>
                    <span className="text-[10px] font-black uppercase text-indigo-600 tracking-wider bg-indigo-50 border border-indigo-100 px-2 py-0.5 rounded-full">
                      Day {activeNotesModal.dayNum} AI Study Notes
                    </span>
                    <h3 className="text-lg font-black text-slate-900 leading-snug">
                      {activeNotesModal.topic}
                    </h3>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      const dayItem = currentPlan?.schedule.find((s) => s.day === activeNotesModal.dayNum)
                      if (dayItem) handleOpenStudyNotes(dayItem, true)
                    }}
                    disabled={activeNotesModal.loading}
                    className="p-2 rounded-[1.25rem] text-slate-500 hover:text-[#1CB0F6] hover:bg-[#DDF4FF] transition-colors disabled:opacity-40"
                    title="Regenerate Full Study Brief"
                  >
                    <Sparkles size={18} />
                  </button>

                  <button
                    onClick={() => speakNotes(activeNotesModal.notes)}
                    className="p-2 rounded-[1.25rem] text-slate-500 hover:bg-black/10 transition-colors"
                    title="Audio Reader"
                  >
                    <Volume2 size={18} className={isSpeaking ? 'text-indigo-600 animate-pulse' : ''} />
                  </button>

                  <button
                    onClick={() => copyNotes(activeNotesModal.notes)}
                    className="p-2 rounded-[1.25rem] text-slate-500 hover:bg-black/10 transition-colors"
                    title="Copy Notes"
                  >
                    {copied ? <Check size={18} className="text-emerald-600" /> : <Copy size={18} />}
                  </button>

                  <button
                    onClick={() => {
                      if (isSpeaking) window.speechSynthesis.cancel()
                      setIsSpeaking(false)
                      setActiveNotesModal(null)
                    }}
                    className="p-2 rounded-[1.25rem] text-slate-400 hover:text-slate-700 hover:bg-black/10 transition-colors"
                  >
                    <X size={20} />
                  </button>
                </div>
              </div>

              {/* Notes Body Content */}
              <div className="flex-1 overflow-y-auto pr-2 space-y-4">
                {activeNotesModal.loading ? (
                  <div className="py-12 text-center space-y-3">
                    <RefreshCw size={24} className="animate-spin text-indigo-600 mx-auto" />
                    <p className="text-xs font-bold text-slate-500">Generating AI Study Notes from PDF...</p>
                  </div>
                ) : (
                  <div className="prose prose-sm max-w-none text-slate-800 space-y-3">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm, remarkMath]}
                      rehypePlugins={[rehypeKatex]}
                      components={{
                        h1: ({ children }) => (
                          <h1 className="text-xl font-black text-slate-900 mt-6 mb-3 pb-2 border-b border-slate-200">
                            {children}
                          </h1>
                        ),
                        h2: ({ children }) => (
                          <h2 className="text-base font-bold text-slate-900 mt-6 mb-2.5 flex items-center gap-2">
                            {children}
                          </h2>
                        ),
                        h3: ({ children }) => (
                          <h3 className="text-sm font-bold text-slate-800 mt-4 mb-2">
                            {children}
                          </h3>
                        ),
                        p: ({ children }) => (
                          <p className="text-xs sm:text-sm text-slate-700 leading-relaxed mb-3 font-normal">
                            {children}
                          </p>
                        ),
                        ul: ({ children }) => (
                          <ul className="list-disc pl-5 space-y-1.5 text-xs sm:text-sm text-slate-700 mb-3">
                            {children}
                          </ul>
                        ),
                        ol: ({ children }) => (
                          <ol className="list-decimal pl-5 space-y-1.5 text-xs sm:text-sm text-slate-700 mb-3">
                            {children}
                          </ol>
                        ),
                        li: ({ children }) => (
                          <li className="leading-relaxed">
                            {children}
                          </li>
                        ),
                        blockquote: ({ children }) => (
                          <blockquote className="border-l-4 border-indigo-500 pl-4 py-2 my-3 bg-indigo-50/60 rounded-r-xl text-xs sm:text-sm text-slate-800 italic">
                            {children}
                          </blockquote>
                        ),
                        table: ({ children }) => (
                          <div className="overflow-x-auto my-4 rounded-xl border border-slate-200 shadow-2xs">
                            <table className="w-full text-xs border-collapse">{children}</table>
                          </div>
                        ),
                        th: ({ children }) => (
                          <th className="border-b border-slate-200 bg-slate-100/80 p-2.5 font-bold text-left text-slate-800">
                            {children}
                          </th>
                        ),
                        td: ({ children }) => (
                          <td className="border-b border-slate-100 p-2.5 text-left text-slate-700">
                            {children}
                          </td>
                        ),
                        code({ className, children, ...props }: any) {
                          const match = /language-(\w+)/.exec(className || '')
                          const isMermaid = match && match[1] === 'mermaid'
                          const isInline = !match

                          if (isMermaid) {
                            return <MermaidDiagram chart={String(children).replace(/\n$/, '')} />
                          }
                          if (isInline) {
                            return (
                              <code className="bg-slate-100 text-indigo-700 px-1.5 py-0.5 rounded-md text-xs font-mono font-semibold border border-slate-200">
                                {children}
                              </code>
                            )
                          }
                          return (
                            <pre className="bg-slate-900 text-slate-100 p-4 rounded-2xl overflow-x-auto text-xs font-mono my-3 shadow-inner">
                              <code>{children}</code>
                            </pre>
                          )
                        },
                      }}
                    >
                      {(() => {
                        const raw = activeNotesModal.notes || ''
                        // Inline math delimiter normalization
                        let cleaned = raw.replace(/(?<!\$)\$\$\s*([^\$\n]+?)\s*\$\$(?!\$)/g, (_m: string, p1: string) => `$${p1.trim()}$`)
                        cleaned = cleaned.replace(/([^\n])\s*\$\$\s*\n/g, '$1\n\n$$\n')
                        cleaned = cleaned.replace(/\n\s*\$\$\s*([^\n])/g, '\n$$\n\n$1')
                        cleaned = cleaned.replace(/\n(Supervised Learning|Unsupervised Learning|Reinforcement Learning|Semi-Supervised Learning):\s*/g, '\n- **$1**: ')
                        return cleaned
                      })()}
                    </ReactMarkdown>
                  </div>
                )}
              </div>

              <div className="border-t border-slate-100 pt-4 mt-4 flex items-center justify-between">
                <span className="text-xs text-slate-400 font-medium">Derived from your uploaded PDF text</span>
                <button
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
                  className="btn-primary flex items-center gap-2 px-6 py-2.5 text-xs elevation-2 cursor-pointer"
                >
                  Done Reading — Take Day Quiz <Target size={14} />
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {dayQuizModal && (
        <GamifiedQuizGame
          isOpen={!!dayQuizModal}
          onClose={() => setDayQuizModal(null)}
          initialTopic={dayQuizModal.topic}
          onQuizComplete={handleDayQuizComplete}
        />
      )}

      <UpgradeModal
        isOpen={upgradeModalInfo.open}
        exceededFileName={upgradeModalInfo.fileName}
        exceededFileSizeMb={upgradeModalInfo.sizeMb}
        onClose={() => setUpgradeModalInfo({ open: false })}
      />
    </div>
  )
}
