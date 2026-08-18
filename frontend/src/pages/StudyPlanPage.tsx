import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
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
  X
} from 'lucide-react'
import { studyPlanApi, documentsApi, default as api } from '../services/api'
import { useAuthStore } from '../stores/authStore'
import { useChatStore } from '../stores/chatStore'
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
  const [upgradeModalInfo, setUpgradeModalInfo] = useState<{ open: boolean; fileName?: string; sizeMb?: number }>({ open: false })
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Generator form state
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [selectedSessionId, setSelectedSessionId] = useState<string>('')
  const [targetDate, setTargetDate] = useState<string>(() => {
    const d = new Date()
    d.setDate(d.getDate() + 10)
    return d.toISOString().split('T')[0]
  })
  const [hoursPerDay, setHoursPerDay] = useState<number>(2.0)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)

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
      notes: `### 📌 ${dayItem.topic}\n\nGenerating comprehensive AI Study Notes from document context...`,
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
              notes: `### ⚠️ Could Not Generate Notes\n\n**Error:** ${errMsg}\n\nPlease try again. If the problem persists, check that the backend is running and your PDF is uploaded for this topic.`,
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

      // If user uploaded a new file directly in the Study Plan generator
      if (selectedFile) {
        topicId = `plan_${Date.now()}`
        await documentsApi.upload(topicId, selectedFile)
      } else if (selectedSessionId) {
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
      })

      queryClient.invalidateQueries({ queryKey: ['study-plans'] })
      queryClient.invalidateQueries({ queryKey: ['progress-summary'] })
      setActivePlanId(res.data.id)
      setShowCreateModal(false)
      setSelectedFile(null)
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
    <div className="p-6 max-w-7xl mx-auto space-y-8 bg-[#FAF8F3]">
      {/* ─── HEADER ─── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Calendar size={18} className="text-[#F28A45]" />
            <span className="text-xs font-black text-[#F28A45] uppercase tracking-widest bg-[#FFF0E4] px-2.5 py-0.5 rounded-full border border-[#F28A45]/20">
              AI Study Plan Engine
            </span>
          </div>
          <h1 className="text-3xl font-black text-[#20201D] tracking-tight">Study Roadmap</h1>
          <p className="text-[#6F6B63] text-sm mt-0.5 font-medium">
            Upload document material + set target completion date to generate a personalized day-by-day study plan.
          </p>
        </div>

        <button
          onClick={() => setShowCreateModal(true)}
          className="btn-primary flex items-center gap-2 py-2.5 px-5 text-xs shadow-xs self-start md:self-auto cursor-pointer"
        >
          <Plus size={16} /> Create New Study Plan
        </button>
      </div>

      {isLoading ? (
        <div className="p-12 text-center">
          <RefreshCw size={28} className="animate-spin text-[#F28A45] mx-auto mb-3" />
          <p className="text-xs font-bold text-[#6F6B63]">Loading study plans...</p>
        </div>
      ) : plans.length === 0 ? (
        /* ─── EMPTY STATE ─── */
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="glass-card p-12 text-center border border-[#E7E1D8] max-w-xl mx-auto space-y-5"
        >
          <div className="w-24 h-24 mx-auto select-none pointer-events-none mb-2">
            <img src="/assets/illustrations/mountain_goal.png" alt="Study Plan" className="w-full h-full object-contain" />
          </div>
          <div>
            <h2 className="text-xl font-black text-[#20201D]">No Active Study Plans</h2>
            <p className="text-xs text-[#6F6B63] mt-2 max-w-md mx-auto leading-relaxed font-medium">
              Analyze your PDF documents against your target completion date. Ollama AI will calculate your days remaining and build a custom daily schedule.
            </p>
          </div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="btn-primary flex items-center gap-2 mx-auto py-2.5 px-6 text-xs shadow-xs cursor-pointer"
          >
            <Sparkles size={15} /> Analyze Material & Generate Plan
          </button>
        </motion.div>
      ) : (
        /* ─── ACTIVE STUDY PLAN DASHBOARD ─── */
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Left: Saved Plans Sidebar */}
          <div className="space-y-3">
            <h3 className="text-xs font-black text-[#969188] uppercase tracking-wider px-1">
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
                    className={`w-full text-left p-3.5 rounded-2xl border transition-all cursor-pointer flex flex-col gap-2 ${
                      isSel
                        ? 'bg-[#FFF0E4] text-[#F28A45] border-[#F28A45]/40 shadow-xs'
                        : 'bg-white text-[#20201D] border-[#E7E1D8] hover:border-[#F28A45]/40 hover:bg-[#FFF9F2]'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className={`text-[10px] font-black uppercase px-2 py-0.5 rounded-md ${
                        isSel ? 'bg-[#F28A45] text-white' : 'bg-[#F4EFE7] text-[#6F6B63]'
                      }`}>
                        Target: {p.target_date}
                      </span>
                      <span className={`text-xs font-black ${isSel ? 'text-[#F28A45]' : 'text-[#6F6B63]'}`}>
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
                  className={`p-4 rounded-2xl border flex items-center justify-between text-xs font-extrabold shadow-2xs ${
                    quizVerificationMessage.passed
                      ? 'bg-[#E3F0E5] text-[#35654B] border-[#4F8A68]/40'
                      : 'bg-[#FFF0E4] text-[#C85C52] border-[#F28A45]/40'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <Sparkles size={16} className={quizVerificationMessage.passed ? 'text-[#4F8A68]' : 'text-[#F28A45]'} />
                    <span>{quizVerificationMessage.message}</span>
                  </div>
                  <button
                    onClick={() => setQuizVerificationMessage(null)}
                    className="p-1 text-[#969188] hover:text-[#20201D] cursor-pointer"
                  >
                    <X size={16} />
                  </button>
                </motion.div>
              )}

              {/* Plan Overview Card */}
              <div className="glass-card p-6 border border-[#E7E1D8] bg-gradient-to-r from-[#FFF9F2] via-white to-[#FFF0E4] space-y-4 shadow-xs">
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
                              ? 'bg-[#FBE7E4] text-[#C85C52] border-[#C85C52]/30 animate-pulse'
                              : 'bg-[#FFF0E4] text-[#F28A45] border-[#F28A45]/20'
                          }`}
                        >
                          {isOverdue ? `⚠️ Target Overdue: ${currentPlan.target_date}` : `Target Finish Date: ${currentPlan.target_date}`}
                        </span>
                      )
                    })()}
                    <h2 className="text-xl font-black text-[#20201D] mt-2">{currentPlan.title}</h2>
                  </div>

                  <button
                    onClick={() => deletePlanMutation.mutate(currentPlan.id)}
                    className="p-2 text-[#969188] hover:text-[#C85C52] hover:bg-[#FBE7E4] rounded-xl transition-colors self-start sm:self-auto"
                    title="Delete Study Plan"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>

                {/* Progress bar */}
                <div className="space-y-1.5 pt-2">
                  <div className="flex items-center justify-between text-xs font-extrabold text-[#6F6B63]">
                    <span>Overall Study Completion</span>
                    <span className="text-[#4F8A68]">
                      {completedCount} of {currentPlan.total_days} Days Completed ({completionPct}%)
                    </span>
                  </div>
                  <div className="w-full bg-[#F4EFE7] rounded-full h-2 overflow-hidden">
                    <motion.div
                      className="bg-[#4F8A68] h-full rounded-full"
                      animate={{ width: `${completionPct}%` }}
                      transition={{ duration: 0.5 }}
                    />
                  </div>
                </div>
              </div>

              {/* Day-by-Day Timeline Schedule */}
              <div className="space-y-4">
                <h3 className="text-sm font-black text-[#20201D] flex items-center gap-2">
                  <Clock size={16} className="text-[#F28A45]" />
                  Day-by-Day Study Schedule ({currentPlan.schedule?.length ?? 0} Days)
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
                              <span className="text-xs font-black text-[#F28A45] bg-[#FFF0E4] border border-[#F28A45]/30 px-3 py-1 rounded-xl uppercase tracking-wider shadow-2xs">
                                {dayItem.phase}
                              </span>
                              <div className="flex-1 h-[1px] bg-[#E7E1D8]" />
                            </div>
                          </div>
                        )}

                        <motion.div
                          initial={{ opacity: 0, y: 6 }}
                          animate={{ opacity: 1, y: 0 }}
                          className={`p-5 rounded-2xl border transition-all ${
                            isDone
                              ? 'bg-[#E3F0E5]/50 border-[#4F8A68]/30 shadow-2xs'
                              : 'bg-white border-[#E7E1D8] shadow-2xs hover:border-[#F28A45]/40'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div className="flex items-start gap-3.5">
                              {/* Status Indicator (completed via quiz only) */}
                              <div
                                className={`w-7 h-7 rounded-xl border flex items-center justify-center mt-0.5 flex-shrink-0 ${
                                  isDone
                                    ? 'bg-[#4F8A68] border-[#4F8A68] text-white shadow-2xs'
                                    : 'bg-[#FAF8F3] border-[#E7E1D8] text-transparent'
                                }`}
                                title={isDone ? '✅ Passed Day Quiz (≥70%)' : 'Pass the Day Quiz to complete'}
                              >
                                <CheckCircle2 size={18} />
                              </div>

                              <div>
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="text-xs font-black text-[#F28A45] bg-[#FFF0E4] px-2 py-0.5 rounded-md border border-[#F28A45]/20">
                                    Day {dayItem.day}
                                  </span>
                                  {dayItem.phase && (
                                    <span className="text-[10px] font-bold text-[#4F8A68] bg-[#E3F0E5] px-2 py-0.5 rounded-md border border-[#4F8A68]/20">
                                      {dayItem.phase.split(':')[0]}
                                    </span>
                                  )}
                                  <span className="text-[11px] font-semibold text-[#969188] flex items-center gap-1">
                                    <Clock size={11} /> {dayItem.estimated_hours} hrs
                                  </span>
                                </div>

                                <h4 className={`text-sm font-extrabold mt-1.5 ${isDone ? 'line-through text-[#969188]' : 'text-[#20201D]'}`}>
                                  {dayItem.topic}
                                </h4>

                                <p className="text-xs text-[#6F6B63] mt-1 leading-relaxed font-medium">
                                  {dayItem.focus}
                                </p>

                                {/* Recommended Action */}
                                {dayItem.recommended_action && (
                                  <div className="mt-3 p-2.5 bg-[#FFF9F2] border border-[#E7E1D8] rounded-xl text-xs text-[#20201D] flex items-center gap-2">
                                    <Brain size={13} className="text-[#F28A45] flex-shrink-0" />
                                    <span><strong className="text-[#F28A45]">Action:</strong> {dayItem.recommended_action}</span>
                                  </div>
                                )}

                                {/* Key Concepts Pills */}
                                {dayItem.key_concepts && dayItem.key_concepts.length > 0 && (
                                  <div className="flex flex-wrap gap-1.5 mt-3">
                                    {dayItem.key_concepts.map((concept, idx) => (
                                      <span
                                        key={idx}
                                        className="text-[10px] font-bold bg-[#E3F0E5] text-[#35654B] border border-[#4F8A68]/20 px-2 py-0.5 rounded-lg"
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
                                    className="btn-primary py-2 px-3.5 text-xs font-bold flex items-center gap-1.5 transition-all cursor-pointer shadow-2xs active:scale-95"
                                  >
                                    <BookOpen size={14} /> View AI Study Notes
                                  </button>

                                  <button
                                    type="button"
                                    onClick={() => {
                                      const conceptsStr = dayItem.key_concepts?.length
                                        ? ` (Key Concepts: ${dayItem.key_concepts.join(', ')})`
                                        : ''
                                      setDayQuizModal({ dayNum: dayItem.day, topic: dayItem.topic + conceptsStr })
                                    }}
                                    className={`py-2 px-3.5 text-xs font-extrabold rounded-xl border flex items-center gap-1.5 transition-all cursor-pointer shadow-2xs active:scale-95 ${
                                      isDone
                                        ? 'bg-[#E3F0E5] text-[#35654B] border-[#4F8A68]/30 hover:bg-[#d5e8d8]'
                                        : 'bg-[#FFF0E4] text-[#F28A45] border-[#F28A45]/40 hover:bg-[#ffe3ce]'
                                    }`}
                                  >
                                    <Target size={14} />
                                    {isDone ? '✓ Retake Day Quiz (Passed)' : '🎯 Take Day Quiz (Pass ≥ 70%)'}
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
          <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-lg bg-white rounded-3xl p-7 shadow-2xl border border-slate-100 relative overflow-hidden"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-2xl bg-indigo-50 flex items-center justify-center text-indigo-600 border border-indigo-100">
                  <Sparkles size={20} />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-900">Generate AI Study Plan</h3>
                  <p className="text-xs text-slate-500">Analyze PDF context & calculate date schedule</p>
                </div>
              </div>

              <form onSubmit={handleGeneratePlan} className="space-y-4">
                {/* PDF File Upload */}
                <div>
                  <label className="text-xs font-bold text-slate-400 uppercase tracking-wider block mb-1.5">
                    1. Upload PDF Document (or Select Existing Session)
                  </label>
                  
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf,.png,.jpg,.jpeg,.webp,.bmp,.docx,.doc,.csv,.xlsx,.xls,.pptx,.ppt,.html,.json,.txt,.md"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0]
                      if (file) {
                        setSelectedFile(file)
                        setSelectedSessionId('')
                      }
                    }}
                  />

                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className={`flex-1 p-3 border rounded-2xl text-xs font-semibold flex items-center justify-center gap-2 transition-all cursor-pointer ${
                        selectedFile
                          ? 'bg-indigo-50 border-indigo-400 text-indigo-900'
                          : 'bg-slate-50 border-slate-200 text-slate-600 hover:bg-slate-100'
                      }`}
                    >
                      <UploadCloud size={16} className="text-indigo-600" />
                      <span className="truncate">{selectedFile ? selectedFile.name : 'Upload Document PDF'}</span>
                    </button>

                    {sessions.length > 0 && (
                      <select
                        value={selectedSessionId}
                        onChange={(e) => {
                          setSelectedSessionId(e.target.value)
                          setSelectedFile(null)
                        }}
                        className="bg-slate-50 border border-slate-200 text-xs font-semibold text-slate-700 rounded-2xl px-3 py-2.5 focus:outline-none"
                      >
                        <option value="">Or pick chat session...</option>
                        {sessions.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.session_title}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                </div>

                {/* Target Date Picker */}
                <div>
                  <label className="text-xs font-bold text-slate-400 uppercase tracking-wider block mb-1.5">
                    2. Target Completion / Exam Date
                  </label>
                  <input
                    type="date"
                    required
                    value={targetDate}
                    onChange={(e) => setTargetDate(e.target.value)}
                    min={new Date().toISOString().split('T')[0]}
                    className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-2.5 text-xs text-slate-800 font-bold focus:outline-none focus:border-indigo-500"
                  />
                  <p className="text-[10px] text-slate-400 mt-1">
                    AI will automatically calculate days remaining until this date to construct your schedule.
                  </p>
                </div>

                {/* Hours Per Day */}
                <div>
                  <label className="text-xs font-bold text-slate-400 uppercase tracking-wider block mb-1.5">
                    3. Daily Study Time Available
                  </label>
                  <div className="flex gap-2">
                    {[1.0, 2.0, 3.0, 4.0].map((hrs) => (
                      <button
                        key={hrs}
                        type="button"
                        onClick={() => setHoursPerDay(hrs)}
                        className={`flex-1 py-2 rounded-xl text-xs font-bold border transition-all cursor-pointer ${
                          hoursPerDay === hrs
                            ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm'
                            : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'
                        }`}
                      >
                        {hrs} hr{hrs > 1 ? 's' : ''}/day
                      </button>
                    ))}
                  </div>
                </div>

                {/* Buttons */}
                <div className="flex justify-end gap-3 pt-3 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => setShowCreateModal(false)}
                    className="btn-ghost py-2.5 px-4 text-xs text-slate-600"
                  >
                    Cancel
                  </button>

                  <button
                    type="submit"
                    disabled={generating}
                    className="btn-primary py-2.5 px-6 text-xs flex items-center gap-2 shadow-lg shadow-indigo-500/20"
                  >
                    {generating ? (
                      <>
                        <RefreshCw size={15} className="animate-spin" /> Analyzing & Planning...
                      </>
                    ) : (
                      <>
                        <Sparkles size={15} /> Generate Schedule
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
              className="w-full max-w-2xl bg-white rounded-3xl p-7 shadow-2xl border border-slate-200 relative overflow-hidden flex flex-col max-h-[85vh]"
            >
              {/* Header */}
              <div className="flex items-center justify-between border-b border-slate-100 pb-4 mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-2xl bg-[#111111] text-white flex items-center justify-center font-black">
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
                    className="p-2 rounded-xl text-slate-500 hover:text-[#F28A45] hover:bg-[#FFF0E4] transition-colors disabled:opacity-40"
                    title="Regenerate Full Study Brief"
                  >
                    <Sparkles size={18} />
                  </button>

                  <button
                    onClick={() => speakNotes(activeNotesModal.notes)}
                    className="p-2 rounded-xl text-slate-500 hover:bg-slate-100 transition-colors"
                    title="Audio Reader"
                  >
                    <Volume2 size={18} className={isSpeaking ? 'text-indigo-600 animate-pulse' : ''} />
                  </button>

                  <button
                    onClick={() => copyNotes(activeNotesModal.notes)}
                    className="p-2 rounded-xl text-slate-500 hover:bg-slate-100 transition-colors"
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
                    className="p-2 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
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
                  <div className="markdown-content text-slate-800 leading-relaxed text-sm">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {activeNotesModal.notes}
                    </ReactMarkdown>
                  </div>
                )}
              </div>

              <div className="border-t border-slate-100 pt-4 mt-4 flex items-center justify-between">
                <span className="text-xs text-slate-400 font-medium">✨ Derived from your uploaded PDF text</span>
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
                  className="btn-primary flex items-center gap-2 px-6 py-2.5 text-xs shadow-xs cursor-pointer"
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
