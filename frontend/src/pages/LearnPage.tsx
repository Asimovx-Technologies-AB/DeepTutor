import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'

import {
  BookOpen, Sparkles, Send, Mic, MicOff, Volume2, VolumeX,
  Layers, GraduationCap, CheckCircle2, AlertCircle, ChevronDown,
  ChevronRight, ArrowRight, Download, Printer, Copy, Check,
  Trash2, Plus, FileText, UploadCloud, RefreshCw, PanelLeft,
  PanelRight, Maximize2, Minimize2, Split, HelpCircle, Award,
  Brain, FileSpreadsheet, Eye, Play, Pause, X
} from 'lucide-react'

import { studyApi, streamTeacherLecture } from '../services/api'
import { exportNotesToPdf } from '../utils/pdfExport'
import { useAuthStore } from '../stores/authStore'
import confetti from 'canvas-confetti'

// ─── Interfaces ─────────────────────────────────────────────────────────────

interface StudySessionMeta {
  id: string
  subject: string
  title: string
  document_name?: string
  status: string
  topic_count: number
  message_count: number
  created_at: string
  last_active: string
}

interface CurriculumTopic {
  id: string
  title: string
  summary: string
  difficulty: string
  key_concepts: string[]
  estimated_study_time: string
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  thought_process?: string
  sources?: Array<{ chunk_id: string; page: number; source_type: string; snippet?: string }>
  quiz_data?: any
  format?: string
  created_at?: string
}

interface CoreIdeaData {
  topic_id: string
  topic_title: string
  big_picture: string
  core_principle: string
  key_takeaways: string[]
  common_pitfalls: string[]
}

interface ExamQuestion {
  id: string
  type: 'written' | 'mcq' | 'fill_in_the_blank'
  question: string
  options?: string[]
  rubric_criteria?: string
  sample_model_answer?: string
  correct_answer?: string
  explanation?: string
}

interface ExamEvaluation {
  topic_id: string
  total_questions: number
  score: number
  percentage: number
  mastery_badge: string
  mastery_level: string
  evaluations: Array<{
    id: string
    type: string
    question: string
    student_answer: string
    sample_model_answer?: string
    correct_answer?: string
    score_percentage: number
    is_correct: boolean
    feedback: string
    explanation?: string
  }>
}

type ActiveTab = 'chat' | 'normal' | 'teacher' | 'exam' | 'artifact'

export default function LearnPage() {
  const { sessionId: routeSessionId } = useParams<{ sessionId?: string }>()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)

  // ─── State: Workspaces & Sessions ───
  const [sessions, setSessions] = useState<StudySessionMeta[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string>(routeSessionId || '')
  const [activeSubject, setActiveSubject] = useState<string>('Machine Learning & AI')
  const [documentName, setDocumentName] = useState<string>('')
  const [docStatus, setDocStatus] = useState<string>('text_ready')

  // Panels
  const [workspaceOpen, setWorkspaceOpen] = useState(false)
  const [studyMapOpen, setStudyMapOpen] = useState(true)
  const [artifactViewerOpen, setArtifactViewerOpen] = useState(false)
  const [artifactDockSide, setArtifactDockSide] = useState<'right' | 'left'>('right')
  const [artifactExpanded, setArtifactExpanded] = useState(false)
  const [artifactTab, setArtifactTab] = useState<'preview' | 'raw'>('preview')
  const [copiedArtifact, setCopiedArtifact] = useState(false)

  // Active Mode Tab
  const [activeTab, setActiveTab] = useState<ActiveTab>('chat')

  // Curriculum Topics
  const [topics, setTopics] = useState<CurriculumTopic[]>([])
  const [activeTopic, setActiveTopic] = useState<CurriculumTopic | null>(null)

  // Grounded Chat
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [inputQuery, setInputQuery] = useState('')
  const [isAgentThinking, setIsAgentThinking] = useState(false)
  const [expandedThoughtIds, setExpandedThoughtIds] = useState<Record<string, boolean>>({})

  // Voice Tutor
  const [speakingMsgId, setSpeakingMsgId] = useState<string | null>(null)
  const [isListeningVoice, setIsListeningVoice] = useState(false)

  // Normal Mode 4-Step Cards
  const [coreIdeaData, setCoreIdeaData] = useState<CoreIdeaData | null>(null)
  const [coreIdeaStep, setCoreIdeaStep] = useState(0)
  const [isLoadingCoreIdea, setIsLoadingCoreIdea] = useState(false)
  const [topicDoubtInput, setTopicDoubtInput] = useState('')
  const [topicDoubtAnswer, setTopicDoubtAnswer] = useState<string | null>(null)
  const [isLoadingDoubt, setIsLoadingDoubt] = useState(false)

  // Teacher Mode
  const [teacherLectureText, setTeacherLectureText] = useState('')
  const [currentLecturePhase, setCurrentLecturePhase] = useState('Introduction')
  const [isTeacherStreaming, setIsTeacherStreaming] = useState(false)
  const teacherAbortControllerRef = useRef<AbortController | null>(null)

  // Mixed Exam Engine
  const [examQuestions, setExamQuestions] = useState<ExamQuestion[]>([])
  const [examAnswers, setExamAnswers] = useState<Record<string, string>>({})
  const [isLoadingExam, setIsLoadingExam] = useState(false)
  const [examEvaluation, setExamEvaluation] = useState<ExamEvaluation | null>(null)
  const [isSubmittingExam, setIsSubmittingExam] = useState(false)

  // Upload modal & drag drop
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadSubject, setUploadSubject] = useState('Machine Learning')

  // Student Profile
  const [studentMemory, setStudentMemory] = useState<any>(null)

  // Current Generated Markdown for Artifact Viewer
  const [currentArtifactMarkdown, setCurrentArtifactMarkdown] = useState<string>(
    `# DeepTutor Master Study Notes\n\nWelcome to your AI Study Room. Upload your course documents, textbook chapters, or lecture slides to generate real-time grounded notes, KaTeX formula breakdowns, and curriculum maps.\n\n## Core Mechanics\n- **Sub-2ms FTS5 BM25 Retrieval**: Every query is constrained to your uploaded material.\n- **Two-Agent Architecture**: Planner prepares search queries; Executor verifies factual grounding.\n- **Zero Hallucination Guarantee**: Strict academic integrity and formula preservation.`
  )

  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, isAgentThinking])

  // ─── 1. Load Sessions on Mount ───
  const fetchSessions = useCallback(async () => {
    try {
      const res = await studyApi.listSessions()
      const list = res.data || []
      setSessions(list)
      if (list.length > 0 && !activeSessionId) {
        const first = list[0]
        setActiveSessionId(first.id)
        setActiveSubject(first.subject || 'General Study')
        setDocumentName(first.document_name || '')
      } else if (list.length === 0 && !activeSessionId) {
        studyApi.createSession({ subject: 'General Study', title: 'Default Study Room' }).then((r) => {
          if (r.data && r.data.id) {
            setActiveSessionId(r.data.id)
            setSessions([r.data])
          }
        }).catch(() => {})
      }
    } catch (err) {
      console.error('Failed to load study sessions:', err)
    }
  }, [activeSessionId])

  useEffect(() => {
    fetchSessions()
  }, [fetchSessions])

  // ─── 2. Load Session Details & SQLite Data ───
  const loadSessionDetails = useCallback(async (sid: string) => {
    if (!sid) return
    try {
      const res = await studyApi.getSession(sid)
      const data = res.data
      if (data.meta) {
        setActiveSubject(data.meta.subject || 'General Study')
        setDocumentName(data.meta.document_name || '')
        setDocStatus(data.meta.status || 'text_ready')
      }
      setMessages(data.messages || [])
      setTopics(data.topics || [])
      if (data.topics && data.topics.length > 0) {
        setActiveTopic(data.topics[0])
      }
    } catch (err) {
      console.error('Failed to load session details:', err)
    }
  }, [])

  useEffect(() => {
    if (activeSessionId) {
      loadSessionDetails(activeSessionId)
    }
  }, [activeSessionId, loadSessionDetails])

  // ─── 3. Load Student Memory Profile ───
  useEffect(() => {
    const uid = user?.id || 'default-user'
    studyApi.getMemory(uid).then((res) => {
      setStudentMemory(res.data)
    }).catch(() => {})
  }, [user?.id])

  // ─── 4. Document Ingestion Handler ───
  const handleFileUpload = async (file: File) => {
    setIsUploading(true)
    setUploadProgress(15)
    setUploadError(null)

    try {
      const interval = setInterval(() => {
        setUploadProgress((p) => (p < 85 ? p + 12 : p))
      }, 400)

      const res = await studyApi.upload(file, uploadSubject, activeSessionId || undefined)
      clearInterval(interval)
      setUploadProgress(100)

      const data = res.data
      setActiveSessionId(data.session_id)
      setDocumentName(data.filename)
      setDocStatus(data.status)
      if (data.topics && data.topics.length > 0) {
        setTopics(data.topics)
        setActiveTopic(data.topics[0])
      }

      // Add system confirmation message in chat
      setMessages((prev) => [
        ...prev,
        {
          id: `sys-${Date.now()}`,
          role: 'assistant',
          text: `I have analyzed **${data.filename}** and indexed ${data.chunk_count} semantic segments into your session database. The Curriculum Study Map with ${data.topics?.length || 0} progressive topics is ready. How would you like to begin?`,
          thought_process: 'Fast-path digital text and VLM OCR indexing complete. Sub-2ms FTS5 BM25 retrieval active. Guardrail classification passed.',
          format: 'conceptual'
        }
      ])

      fetchSessions()
      setIsUploading(false)
    } catch (err: any) {
      setIsUploading(false)
      const msg = err.response?.data?.detail || err.message || 'Upload failed'
      setUploadError(msg)
    }
  }

  // ─── 5. Send Chat Message (Planner -> Executor) ───
  const handleSendMessage = async (customQuery?: string) => {
    const q = customQuery || inputQuery
    if (!q.trim() || isAgentThinking) return

    let currentSid = activeSessionId
    if (!currentSid) {
      try {
        const createRes = await studyApi.createSession({ subject: activeSubject, title: 'Default Study Room' })
        currentSid = createRes.data.id
        setActiveSessionId(currentSid)
        fetchSessions()
      } catch {
        currentSid = `session_${Date.now()}`
        setActiveSessionId(currentSid)
      }
    }

    const userMsg: ChatMessage = {
      id: `usr-${Date.now()}`,
      role: 'user',
      text: q.trim(),
      created_at: new Date().toISOString()
    }
    setMessages((prev) => [...prev, userMsg])
    setInputQuery('')
    setIsAgentThinking(true)

    try {
      const res = await studyApi.sendMessage({
        message: q.trim(),
        session_id: currentSid,
        user_id: user?.id || 'default-user',
        subject: activeSubject,
        difficulty: activeTopic?.difficulty || 'Intermediate'
      })

      const assistantMsg: ChatMessage = {
        id: res.data.id || `ast-${Date.now()}`,
        role: 'assistant',
        text: res.data.text,
        thought_process: res.data.thought_process,
        sources: res.data.sources,
        quiz_data: res.data.quiz_data,
        format: res.data.format,
        created_at: new Date().toISOString()
      }

      setMessages((prev) => [...prev, assistantMsg])
      // Update Artifact Viewer content with the latest substantial explanation
      if (res.data.text.length > 250) {
        setCurrentArtifactMarkdown(
          `# ${activeSubject} — Study Notes\n\n**Topic Focus**: ${activeTopic?.title || 'Course Material'}\n\n${res.data.text}`
        )
      }
    } catch (err) {
      console.error('Chat failed:', err)
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: 'assistant',
          text: 'I encountered an issue verifying the context chunks for this question. Please ensure your study material is uploaded and try again.',
          thought_process: 'FTS5 retrieval or executor exception encountered.'
        }
      ])
    } finally {
      setIsAgentThinking(false)
    }
  }

  // ─── 6. Speech Synthesis & Microphone Input ───
  const handleToggleVoice = (msgId: string, text: string) => {
    if (!('speechSynthesis' in window)) return

    if (speakingMsgId === msgId) {
      window.speechSynthesis.cancel()
      setSpeakingMsgId(null)
      return
    }

    window.speechSynthesis.cancel()
    const cleanText = text.replace(/[$#*`_]/g, '').slice(0, 500)
    const utterance = new SpeechSynthesisUtterance(cleanText)
    utterance.rate = 1.05
    utterance.pitch = 1.0
    utterance.onend = () => setSpeakingMsgId(null)
    utterance.onerror = () => setSpeakingMsgId(null)

    setSpeakingMsgId(msgId)
    window.speechSynthesis.speak(utterance)
  }

  const handleToggleMic = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRecognition) {
      alert('Speech-to-text is not supported in this browser. Please use Chrome or Edge.')
      return
    }

    if (isListeningVoice) {
      setIsListeningVoice(false)
      return
    }

    const recognition = new SpeechRecognition()
    recognition.lang = 'en-US'
    recognition.interimResults = false
    recognition.onstart = () => setIsListeningVoice(true)
    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript
      setInputQuery(transcript)
      setIsListeningVoice(false)
    }
    recognition.onerror = () => setIsListeningVoice(false)
    recognition.onend = () => setIsListeningVoice(false)
    recognition.start()
  }

  // ─── 7. Normal Mode Loader ───
  const fetchCoreIdea = async (topic: CurriculumTopic) => {
    if (!activeSessionId) return
    setIsLoadingCoreIdea(true)
    setCoreIdeaStep(0)
    setTopicDoubtAnswer(null)
    try {
      const res = await studyApi.getCoreIdea({
        session_id: activeSessionId,
        topic_id: topic.id,
        topic_title: topic.title,
        topic_summary: topic.summary
      })
      setCoreIdeaData(res.data)
      setCurrentArtifactMarkdown(
        `# Core Idea: ${topic.title}\n\n## 1. The Big Picture\n${res.data.big_picture}\n\n## 2. Core Principle\n${res.data.core_principle}\n\n## 3. Key Takeaways\n${res.data.key_takeaways?.map((t: string) => `- ${t}`).join('\n')}\n\n## 4. Common Pitfalls\n${res.data.common_pitfalls?.map((p: string) => `- ${p}`).join('\n')}`
      )
    } catch (err) {
      console.error('Failed to load core idea:', err)
    } finally {
      setIsLoadingCoreIdea(false)
    }
  }

  const handleAskTopicDoubt = async () => {
    if (!topicDoubtInput.trim() || !activeTopic || !activeSessionId || isLoadingDoubt) return
    setIsLoadingDoubt(true)
    try {
      const res = await studyApi.askDoubt({
        session_id: activeSessionId,
        topic_id: activeTopic.id,
        topic_title: activeTopic.title,
        question: topicDoubtInput.trim()
      })
      setTopicDoubtAnswer(res.data.answer)
      setTopicDoubtInput('')
    } catch (err) {
      console.error('Topic doubt failed:', err)
    } finally {
      setIsLoadingDoubt(false)
    }
  }

  // ─── 8. Teacher Mode SSE Stream ───
  const handleStartTeacherLecture = () => {
    if (!activeTopic || !activeSessionId || isTeacherStreaming) return
    setTeacherLectureText('')
    setIsTeacherStreaming(true)
    setCurrentLecturePhase('Phase 1: Introduction & Intuition')

    const controller = new AbortController()
    teacherAbortControllerRef.current = controller

    streamTeacherLecture({
      sessionId: activeSessionId,
      topicId: activeTopic.id,
      topicTitle: activeTopic.title,
      onPhaseStart: (phase) => setCurrentLecturePhase(phase),
      onToken: (token) => {
        setTeacherLectureText((prev) => prev + token)
      },
      onPhaseEnd: () => {},
      onDone: () => {
        setIsTeacherStreaming(false)
        setCurrentArtifactMarkdown(
          `# University Masterclass: ${activeTopic.title}\n\n${teacherLectureText}`
        )
      },
      onError: (err) => {
        console.error('Lecture stream error:', err)
        setIsTeacherStreaming(false)
      },
      signal: controller.signal
    })
  }

  const handleStopTeacherLecture = () => {
    if (teacherAbortControllerRef.current) {
      teacherAbortControllerRef.current.abort()
      setIsTeacherStreaming(false)
    }
  }

  // ─── 9. Topic Mastery Exam Engine ───
  const handleFetchExam = async (topic: CurriculumTopic) => {
    if (!activeSessionId) return
    setIsLoadingExam(true)
    setExamAnswers({})
    setExamEvaluation(null)
    try {
      const res = await studyApi.getExam({
        session_id: activeSessionId,
        topic_id: topic.id,
        topic_title: topic.title
      })
      setExamQuestions(res.data.questions || [])
    } catch (err) {
      console.error('Failed to load exam:', err)
    } finally {
      setIsLoadingExam(false)
    }
  }

  const handleSubmitExam = async () => {
    if (!activeTopic || !activeSessionId || isSubmittingExam) return
    setIsSubmittingExam(true)
    try {
      const res = await studyApi.evaluateExam({
        session_id: activeSessionId,
        topic_id: activeTopic.id,
        questions: examQuestions,
        answers: examAnswers
      })
      setExamEvaluation(res.data)
      if (res.data.percentage >= 80) {
        confetti({ particleCount: 80, spread: 70, origin: { y: 0.6 } })
      }
    } catch (err) {
      console.error('Exam evaluation failed:', err)
    } finally {
      setIsSubmittingExam(false)
    }
  }

  // Auto-load mode data on tab or topic switch
  useEffect(() => {
    if (activeTab === 'normal' && activeTopic) {
      fetchCoreIdea(activeTopic)
    } else if (activeTab === 'exam' && activeTopic && examQuestions.length === 0) {
      handleFetchExam(activeTopic)
    }
  }, [activeTab, activeTopic?.id])

  // ─── Session Switching ───
  const handleSelectSession = (sid: string) => {
    setActiveSessionId(sid)
    const target = sessions.find((s) => s.id === sid)
    if (target) {
      setActiveSubject(target.subject || 'General Study')
      setDocumentName(target.document_name || '')
      setDocStatus(target.status || 'text_ready')
    }
    setWorkspaceOpen(false)
  }

  const handleCreateNewSession = async () => {
    try {
      const res = await studyApi.createSession({
        subject: 'General Study',
        title: 'New Study Workspace'
      })
      const newSid = res.data.id
      setActiveSessionId(newSid)
      fetchSessions()
      setMessages([])
      setTopics([])
      setActiveTopic(null)
      setWorkspaceOpen(false)
    } catch (err) {
      console.error('Create session failed:', err)
    }
  }

  const handleDeleteSession = async (sid: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Are you sure you want to permanently delete this study session and its database?')) return
    try {
      await studyApi.deleteSession(sid)
      setSessions((prev) => prev.filter((s) => s.id !== sid))
      if (activeSessionId === sid) {
        const remaining = sessions.filter((s) => s.id !== sid)
        if (remaining.length > 0) {
          handleSelectSession(remaining[0].id)
        } else {
          setActiveSessionId('')
          setMessages([])
          setTopics([])
        }
      }
    } catch (err) {
      console.error('Delete session failed:', err)
    }
  }

  // ─── Markdown / PDF Export ───
  const handleExportMarkdown = async () => {
    try {
      const res = await studyApi.exportNotesMd({
        markdown: currentArtifactMarkdown,
        title: `${activeSubject}_${activeTopic?.title || 'notes'}`
      })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `${activeSubject.toLowerCase().replace(/\s+/g, '_')}_notes.md`)
      document.body.appendChild(link)
      link.click()
      link.remove()
    } catch (err) {
      console.error('Export markdown failed:', err)
    }
  }

  const handleExportPdf = () => {
    exportNotesToPdf(
      activeTopic?.title ? `${activeTopic.title} — Study Notes` : `${activeSubject} Master Notes`,
      currentArtifactMarkdown,
      activeSubject
    )
  }

  const handleCopyArtifact = () => {
    navigator.clipboard.writeText(currentArtifactMarkdown)
    setCopiedArtifact(true)
    setTimeout(() => setCopiedArtifact(false), 2000)
  }

  // Render KaTeX Math safely
  const customMarkdownComponents = useMemo(() => ({
    // Enforce standalone block KaTeX highlighting
    div: ({ node, className, children, ...props }: any) => {
      if (className?.includes('math-display')) {
        return (
          <div className="my-4 p-4 rounded-2xl bg-indigo-50/80 border border-indigo-200/80 text-indigo-950 font-mono text-center shadow-xs overflow-x-auto">
            {children}
          </div>
        )
      }
      return <div className={className} {...props}>{children}</div>
    },
    table: ({ node, ...props }: any) => (
      <div className="overflow-x-auto my-4 rounded-xl border border-slate-200 shadow-xs">
        <table className="w-full text-sm text-left border-collapse" {...props} />
      </div>
    ),
    th: ({ node, ...props }: any) => (
      <th className="bg-slate-100/90 text-slate-800 font-bold px-4 py-2.5 border-b border-slate-200" {...props} />
    ),
    td: ({ node, ...props }: any) => (
      <td className="px-4 py-2 border-b border-slate-100 text-slate-700" {...props} />
    ),
  }), [])

  return (
    <div className="flex h-screen w-full bg-[#FAF8F3] text-slate-800 font-sans overflow-hidden">

      {/* ─── 1. COLLAPSIBLE LEFT WORKSPACE DRAWER ─── */}
      <AnimatePresence>
        {workspaceOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/30 backdrop-blur-xs flex"
            onClick={() => setWorkspaceOpen(false)}
          >
            <motion.aside
              initial={{ x: -320 }}
              animate={{ x: 0 }}
              exit={{ x: -320 }}
              transition={{ type: 'spring', damping: 25, stiffness: 280 }}
              className="w-80 h-full bg-white/95 backdrop-blur-2xl border-r border-slate-200/80 shadow-2xl p-5 flex flex-col justify-between"
              onClick={(e) => e.stopPropagation()}
            >
              <div>
                {/* Header */}
                <div className="flex items-center justify-between pb-4 border-b border-slate-100">
                  <div className="flex items-center gap-2.5">
                    <div className="w-9 h-9 rounded-2xl bg-indigo-600 text-white flex items-center justify-center shadow-md">
                      <Layers size={18} />
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-slate-900 leading-tight">Course Workspaces</h3>
                      <p className="text-[11px] text-slate-400 font-medium">Session-Isolated SQLite DBs</p>
                    </div>
                  </div>
                  <button
                    onClick={() => setWorkspaceOpen(false)}
                    className="p-1.5 rounded-xl hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition"
                  >
                    <X size={16} />
                  </button>
                </div>

                {/* New Session Button */}
                <button
                  onClick={handleCreateNewSession}
                  className="w-full mt-4 flex items-center justify-center gap-2 py-2.5 px-4 rounded-2xl bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-bold text-xs transition border border-indigo-200/70"
                >
                  <Plus size={15} />
                  New Course Workspace
                </button>

                {/* Document Upload Area */}
                <div className="mt-4 p-4 rounded-2xl bg-slate-50 border border-dashed border-slate-200 text-center">
                  <UploadCloud size={24} className="mx-auto text-indigo-500 mb-2" />
                  <p className="text-xs font-bold text-slate-700">Upload Study Material</p>
                  <p className="text-[10px] text-slate-400 mb-3">PDF, Scanned Docs, Word, PPTX</p>

                  <input
                    type="text"
                    value={uploadSubject}
                    onChange={(e) => setUploadSubject(e.target.value)}
                    placeholder="Course / Subject name"
                    className="w-full text-xs px-2.5 py-1.5 rounded-xl bg-white border border-slate-200 mb-2 focus:outline-indigo-600"
                  />

                  <label className="inline-block py-1.5 px-4 rounded-xl bg-indigo-600 text-white font-bold text-xs cursor-pointer hover:bg-indigo-700 transition shadow-xs">
                    Choose File
                    <input
                      type="file"
                      accept=".pdf,.docx,.doc,.pptx,.ppt,.png,.jpg,.jpeg,.txt"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0]
                        if (file) handleFileUpload(file)
                      }}
                    />
                  </label>

                  {isUploading && (
                    <div className="mt-3">
                      <div className="flex items-center justify-between text-[10px] font-bold text-indigo-700 mb-1">
                        <span>Parallel OCR & Indexing...</span>
                        <span>{uploadProgress}%</span>
                      </div>
                      <div className="w-full h-1.5 bg-indigo-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-indigo-600 transition-all duration-300"
                          style={{ width: `${uploadProgress}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {uploadError && (
                    <p className="mt-2 text-[10px] text-red-600 font-semibold">{uploadError}</p>
                  )}
                </div>

                {/* Active Sessions List */}
                <div className="mt-4 max-h-[38vh] overflow-y-auto space-y-2 pr-1">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400 px-1">
                    Your Active Courses ({sessions.length})
                  </span>
                  {sessions.map((s) => {
                    const isActive = s.id === activeSessionId
                    return (
                      <div
                        key={s.id}
                        onClick={() => handleSelectSession(s.id)}
                        className={`group relative p-3 rounded-2xl cursor-pointer transition border ${
                          isActive
                            ? 'bg-indigo-600 text-white border-indigo-600 shadow-md'
                            : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200/80 shadow-xs'
                        }`}
                      >
                        <div className="flex items-start justify-between">
                          <div className="pr-4 overflow-hidden">
                            <h4 className={`text-xs font-bold truncate ${isActive ? 'text-white' : 'text-slate-900'}`}>
                              {s.title}
                            </h4>
                            <p className={`text-[10px] truncate mt-0.5 ${isActive ? 'text-indigo-100' : 'text-slate-400'}`}>
                              {s.document_name || s.subject}
                            </p>
                          </div>
                          <button
                            onClick={(e) => handleDeleteSession(s.id, e)}
                            className={`opacity-0 group-hover:opacity-100 p-1 rounded-lg transition ${
                              isActive ? 'hover:bg-indigo-700 text-indigo-200' : 'hover:bg-slate-100 text-slate-400 hover:text-red-600'
                            }`}
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                        <div className="mt-2 flex items-center gap-3 text-[9px] font-semibold opacity-85">
                          <span>{s.topic_count} Topics</span>
                          <span>·</span>
                          <span>{s.message_count} Turns</span>
                          <span>·</span>
                          <span>Sub-2ms FTS5</span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Episodic Student Profile Snippet */}
              {studentMemory && (
                <div className="pt-3 border-t border-slate-100">
                  <div className="flex items-center gap-2 mb-1.5">
                    <Brain size={14} className="text-indigo-600" />
                    <span className="text-[11px] font-bold text-slate-700">Episodic Profile</span>
                  </div>
                  <p className="text-[10px] text-slate-500 line-clamp-2">
                    {studentMemory.weaknesses?.length > 0
                      ? `Focus Area: ${studentMemory.weaknesses[studentMemory.weaknesses.length - 1]}`
                      : 'Active learning style: Step-by-Step with KaTeX formulas.'}
                  </p>
                </div>
              )}
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ─── 2. MAIN CENTER STUDY ROOM WORKSPACE ─── */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">

        {/* ─── Top Header & Controls ─── */}
        <header className="h-16 flex-shrink-0 px-6 bg-white/80 backdrop-blur-xl border-b border-slate-200/70 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setWorkspaceOpen(true)}
              className="p-2 rounded-2xl bg-slate-100 hover:bg-slate-200 text-slate-600 transition flex items-center gap-1.5 text-xs font-bold"
              title="Open Workspaces"
            >
              <PanelLeft size={16} />
              <span className="hidden sm:inline">Courses</span>
            </button>

            <div className="h-4 w-[1px] bg-slate-200" />

            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-black text-slate-900 leading-tight truncate max-w-xs md:max-w-md">
                  {documentName ? documentName : activeSubject}
                </h2>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200/80">
                  {docStatus === 'fully_processed' ? 'Fully Grounded (Tables & Figs)' : 'Sub-2ms FTS5 Active'}
                </span>
              </div>
              {activeTopic && (
                <p className="text-[11px] text-indigo-600 font-semibold truncate flex items-center gap-1">
                  <span>Topic:</span>
                  <span className="underline decoration-indigo-200">{activeTopic.title}</span>
                  <span className="text-slate-300">|</span>
                  <span className="text-slate-400 font-normal">{activeTopic.difficulty}</span>
                </p>
              )}
            </div>
          </div>

          {/* Mode Switcher Tabs */}
          <div className="flex items-center gap-1 p-1 bg-slate-100/90 rounded-2xl border border-slate-200/60 shadow-xs">
            <button
              onClick={() => setActiveTab('chat')}
              className={`px-3 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-1.5 ${
                activeTab === 'chat'
                  ? 'bg-white text-indigo-600 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <BookOpen size={14} />
              <span className="hidden md:inline">Tutor Chat</span>
            </button>

            <button
              onClick={() => setActiveTab('normal')}
              className={`px-3 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-1.5 ${
                activeTab === 'normal'
                  ? 'bg-white text-indigo-600 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Sparkles size={14} />
              <span className="hidden md:inline">Normal Mode</span>
            </button>

            <button
              onClick={() => setActiveTab('teacher')}
              className={`px-3 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-1.5 ${
                activeTab === 'teacher'
                  ? 'bg-white text-indigo-600 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <GraduationCap size={14} />
              <span className="hidden md:inline">Teacher Mode</span>
            </button>

            <button
              onClick={() => setActiveTab('exam')}
              className={`px-3 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-1.5 ${
                activeTab === 'exam'
                  ? 'bg-white text-indigo-600 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Award size={14} />
              <span className="hidden md:inline">Topic Exam</span>
            </button>
          </div>

          {/* Right Action Controls */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setArtifactViewerOpen(!artifactViewerOpen)}
              className={`p-2 rounded-2xl border transition text-xs font-bold flex items-center gap-1.5 ${
                artifactViewerOpen
                  ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm'
                  : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200 shadow-xs'
              }`}
              title="Claude-Style Artifact Viewer"
            >
              <Split size={15} />
              <span className="hidden lg:inline">Artifact</span>
            </button>

            <button
              onClick={() => setStudyMapOpen(!studyMapOpen)}
              className={`p-2 rounded-2xl border transition text-xs font-bold flex items-center gap-1.5 ${
                studyMapOpen
                  ? 'bg-indigo-50 text-indigo-700 border-indigo-200'
                  : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200'
              }`}
              title="Curriculum Study Map"
            >
              <PanelRight size={15} />
              <span className="hidden xl:inline">Curriculum</span>
            </button>
          </div>
        </header>

        {/* ─── Mode Content Area ─── */}
        <div className="flex-1 flex overflow-hidden">

          {/* Left Docked Artifact Viewer (if configured to dock left) */}
          {artifactViewerOpen && artifactDockSide === 'left' && (
            <div className={`${artifactExpanded ? 'w-3/5' : 'w-[480px]'} h-full border-r border-slate-200 bg-white shadow-xl transition-all duration-300 z-10 flex flex-col`}>
              {renderArtifactPanel()}
            </div>
          )}

          {/* ─── Central Active Workspace View ─── */}
          <main className="flex-1 flex flex-col h-full overflow-hidden relative">

            {/* TAB 1: GROUNDED TUTOR CHAT */}
            {activeTab === 'chat' && (
              <div className="flex-1 flex flex-col h-full overflow-hidden">
                {/* Message Scroll Container */}
                <div className="flex-1 overflow-y-auto p-6 space-y-5">
                  {messages.length === 0 ? (
                    <div className="flex flex-col items-center justify-center min-h-[50vh] text-center max-w-md mx-auto">
                      <div className="w-16 h-16 rounded-3xl bg-indigo-100 text-indigo-600 flex items-center justify-center mb-4 shadow-sm">
                        <BookOpen size={28} />
                      </div>
                      <h3 className="text-lg font-black text-slate-900">Your AI Study Room is Ready</h3>
                      <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
                        Ask questions about your uploaded course material. Answers are strictly verified against local FTS5 SQLite chunks with KaTeX mathematical typography.
                      </p>
                      <div className="mt-6 flex flex-wrap gap-2 justify-center">
                        {[
                          'Explain the fundamental principle',
                          'Compare key mechanisms with a markdown table',
                          'Quiz me on the core formulas',
                          'Summarize this topic as study notes'
                        ].map((prompt, idx) => (
                          <button
                            key={idx}
                            onClick={() => handleSendMessage(prompt)}
                            className="text-xs font-semibold px-3 py-1.5 rounded-xl bg-white hover:bg-indigo-50 border border-slate-200 hover:border-indigo-200 text-slate-700 hover:text-indigo-700 transition shadow-xs"
                          >
                            {prompt} →
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : (
                    messages.map((msg) => {
                      const isUser = msg.role === 'user'
                      const isThoughtExpanded = expandedThoughtIds[msg.id] ?? false
                      return (
                        <div
                          key={msg.id}
                          className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
                        >
                          {/* Role Header */}
                          <div className="flex items-center gap-2 mb-1 px-1 text-[11px] font-bold text-slate-400">
                            <span>{isUser ? 'You' : 'DeepTutor Academic Agent'}</span>
                            {!isUser && (
                              <button
                                onClick={() => handleToggleVoice(msg.id, msg.text)}
                                className={`p-1 rounded-md transition ${
                                  speakingMsgId === msg.id ? 'text-indigo-600 bg-indigo-50' : 'hover:text-slate-700'
                                }`}
                                title="Read Aloud"
                              >
                                {speakingMsgId === msg.id ? <VolumeX size={13} /> : <Volume2 size={13} />}
                              </button>
                            )}
                          </div>

                          {/* Message Bubble Card */}
                          <div
                            className={`max-w-2xl p-4.5 rounded-3xl text-sm leading-relaxed shadow-xs ${
                              isUser
                                ? 'bg-indigo-600 text-white rounded-br-xs'
                                : 'bg-white text-slate-800 border border-slate-200/80 rounded-bl-xs'
                            }`}
                          >
                            {/* Expandable Chain-of-Thought Pass */}
                            {!isUser && msg.thought_process && (
                              <div className="mb-3 rounded-2xl bg-slate-50/90 border border-slate-200/70 overflow-hidden">
                                <button
                                  onClick={() =>
                                    setExpandedThoughtIds((p) => ({ ...p, [msg.id]: !isThoughtExpanded }))
                                  }
                                  className="w-full flex items-center justify-between px-3 py-2 text-[11px] font-bold text-slate-500 hover:text-indigo-600 transition"
                                >
                                  <span className="flex items-center gap-1.5">
                                    <Brain size={13} className="text-indigo-500" />
                                    DeepTutor Grounding Pass & Reasoning
                                  </span>
                                  {isThoughtExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                                </button>
                                {isThoughtExpanded && (
                                  <div className="px-3 pb-2.5 pt-1 text-xs text-slate-600 font-mono border-t border-slate-100 bg-white/70">
                                    {msg.thought_process}
                                  </div>
                                )}
                              </div>
                            )}

                            {/* Markdown Rendered Content */}
                            <div className="prose prose-sm max-w-none text-inherit prose-headings:font-black prose-headings:text-inherit prose-p:my-1 prose-ul:my-1 prose-li:my-0.5">
                              <ReactMarkdown
                                remarkPlugins={[remarkGfm, remarkMath]}
                                rehypePlugins={[rehypeKatex]}
                                components={customMarkdownComponents}
                              >
                                {msg.text}
                              </ReactMarkdown>
                            </div>

                            {/* Grounding Source Citation Badges */}
                            {!isUser && msg.sources && msg.sources.length > 0 && (
                              <div className="mt-3 pt-2.5 border-t border-slate-100 flex flex-wrap items-center gap-1.5">
                                <span className="text-[10px] font-bold text-slate-400">Grounding Chunks:</span>
                                {msg.sources.map((src, idx) => (
                                  <span
                                    key={idx}
                                    className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200"
                                    title={src.snippet}
                                  >
                                    Page {src.page} · {src.source_type}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      )
                    })
                  )}

                  {/* Agent Thinking Skeleton */}
                  {isAgentThinking && (
                    <div className="flex items-center gap-3 p-4 rounded-3xl bg-white border border-slate-200/80 max-w-xs shadow-xs animate-pulse">
                      <div className="w-8 h-8 rounded-2xl bg-indigo-100 text-indigo-600 flex items-center justify-center">
                        <Sparkles size={16} className="animate-spin" />
                      </div>
                      <div>
                        <p className="text-xs font-bold text-slate-800">Planning & Grounding...</p>
                        <p className="text-[10px] text-slate-400">QueryAnalyzerAgent → FTS5 BM25</p>
                      </div>
                    </div>
                  )}

                  <div ref={messagesEndRef} />
                </div>

                {/* Question Input Bar */}
                <div className="p-4 bg-white/80 backdrop-blur-xl border-t border-slate-200/70">
                  <div className="max-w-3xl mx-auto flex items-center gap-2 p-1.5 rounded-2xl bg-slate-50 border border-slate-200/90 shadow-xs focus-within:border-indigo-500 focus-within:bg-white transition">
                    <button
                      onClick={handleToggleMic}
                      className={`p-2 rounded-xl transition ${
                        isListeningVoice ? 'bg-red-500 text-white animate-pulse' : 'text-slate-400 hover:text-slate-700'
                      }`}
                      title="Speech-to-Text Microphone"
                    >
                      {isListeningVoice ? <MicOff size={18} /> : <Mic size={18} />}
                    </button>

                    <input
                      type="text"
                      value={inputQuery}
                      onChange={(e) => setInputQuery(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault()
                          handleSendMessage()
                        }
                      }}
                      placeholder={`Ask questions about ${activeTopic?.title || 'your uploaded course notes'}...`}
                      className="flex-1 bg-transparent text-xs sm:text-sm text-slate-800 placeholder-slate-400 focus:outline-hidden px-2"
                    />

                    <button
                      onClick={() => handleSendMessage()}
                      disabled={!inputQuery.trim() || isAgentThinking}
                      className="py-2 px-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-bold text-xs transition flex items-center gap-1 shadow-xs"
                    >
                      <Send size={14} />
                      <span className="hidden sm:inline">Ask</span>
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 2: NORMAL MODE (4-STEP CORE IDEA) */}
            {activeTab === 'normal' && (
              <div className="flex-1 overflow-y-auto p-6">
                <div className="max-w-3xl mx-auto space-y-6">
                  {/* Topic Title Header */}
                  <div className="p-6 rounded-3xl bg-white border border-slate-200/80 shadow-xs flex items-center justify-between">
                    <div>
                      <span className="text-[10px] font-black uppercase tracking-widest text-indigo-600">
                        Normal Mode · 4-Phase Core Idea Distillation
                      </span>
                      <h2 className="text-xl font-black text-slate-900 mt-1">
                        {activeTopic?.title || 'Select a Topic'}
                      </h2>
                      <p className="text-xs text-slate-500 mt-1">{activeTopic?.summary}</p>
                    </div>

                    <button
                      onClick={() => activeTopic && fetchCoreIdea(activeTopic)}
                      disabled={isLoadingCoreIdea}
                      className="p-2.5 rounded-2xl bg-indigo-50 hover:bg-indigo-100 text-indigo-700 transition"
                      title="Refresh Core Idea"
                    >
                      <RefreshCw size={16} className={isLoadingCoreIdea ? 'animate-spin' : ''} />
                    </button>
                  </div>

                  {isLoadingCoreIdea ? (
                    <div className="p-12 text-center">
                      <div className="w-10 h-10 border-3 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                      <p className="text-xs font-bold text-slate-500">Distilling 4-Phase Core Mechanics...</p>
                    </div>
                  ) : coreIdeaData ? (
                    <div className="space-y-4">
                      {/* Step Indicator Tabs */}
                      <div className="grid grid-cols-4 gap-2">
                        {['1. The Big Picture', '2. Core Principle', '3. Key Takeaways', '4. Common Pitfalls'].map((title, idx) => (
                          <button
                            key={idx}
                            onClick={() => setCoreIdeaStep(idx)}
                            className={`p-3 rounded-2xl text-xs font-bold transition text-left border ${
                              coreIdeaStep === idx
                                ? 'bg-indigo-600 text-white border-indigo-600 shadow-md'
                                : 'bg-white hover:bg-slate-50 text-slate-600 border-slate-200'
                            }`}
                          >
                            <span className="block text-[10px] opacity-75">Phase {idx + 1}</span>
                            <span className="truncate block mt-0.5">{title.split('. ')[1]}</span>
                          </button>
                        ))}
                      </div>

                      {/* Active Card Body */}
                      <motion.div
                        key={coreIdeaStep}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="p-6 rounded-3xl bg-white border border-slate-200/90 shadow-sm"
                      >
                        {coreIdeaStep === 0 && (
                          <div>
                            <span className="text-[11px] font-black uppercase text-indigo-600">Fundamental Intuition</span>
                            <h3 className="text-base font-black text-slate-900 mt-1 mb-3">The Big Picture</h3>
                            <div className="prose prose-sm text-slate-700 leading-relaxed">
                              <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                                {coreIdeaData.big_picture}
                              </ReactMarkdown>
                            </div>
                          </div>
                        )}

                        {coreIdeaStep === 1 && (
                          <div>
                            <span className="text-[11px] font-black uppercase text-indigo-600">Governing Mechanics & Math</span>
                            <h3 className="text-base font-black text-slate-900 mt-1 mb-3">Core Principle & Formulas</h3>
                            <div className="prose prose-sm text-slate-700 leading-relaxed">
                              <ReactMarkdown
                                remarkPlugins={[remarkGfm, remarkMath]}
                                rehypePlugins={[rehypeKatex]}
                                components={customMarkdownComponents}
                              >
                                {coreIdeaData.core_principle}
                              </ReactMarkdown>
                            </div>
                          </div>
                        )}

                        {coreIdeaStep === 2 && (
                          <div>
                            <span className="text-[11px] font-black uppercase text-emerald-600">High-Yield Revision</span>
                            <h3 className="text-base font-black text-slate-900 mt-1 mb-3">Key Takeaways</h3>
                            <ul className="space-y-2.5">
                              {coreIdeaData.key_takeaways?.map((item, i) => (
                                <li key={i} className="flex items-start gap-2.5 text-sm text-slate-700">
                                  <CheckCircle2 size={16} className="text-emerald-500 flex-shrink-0 mt-0.5" />
                                  <span>{item}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {coreIdeaStep === 3 && (
                          <div>
                            <span className="text-[11px] font-black uppercase text-amber-600">Exam Traps & Misconceptions</span>
                            <h3 className="text-base font-black text-slate-900 mt-1 mb-3">Common Pitfalls</h3>
                            <ul className="space-y-2.5">
                              {coreIdeaData.common_pitfalls?.map((item, i) => (
                                <li key={i} className="flex items-start gap-2.5 text-sm text-slate-700">
                                  <AlertCircle size={16} className="text-amber-500 flex-shrink-0 mt-0.5" />
                                  <span>{item}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Navigation stepper buttons */}
                        <div className="mt-6 pt-4 border-t border-slate-100 flex items-center justify-between">
                          <button
                            onClick={() => setCoreIdeaStep((s) => Math.max(0, s - 1))}
                            disabled={coreIdeaStep === 0}
                            className="py-1.5 px-4 rounded-xl border border-slate-200 text-xs font-bold text-slate-600 hover:bg-slate-50 disabled:opacity-40"
                          >
                            ← Previous
                          </button>
                          <span className="text-xs font-bold text-slate-400">Step {coreIdeaStep + 1} of 4</span>
                          <button
                            onClick={() => setCoreIdeaStep((s) => Math.min(3, s + 1))}
                            disabled={coreIdeaStep === 3}
                            className="py-1.5 px-4 rounded-xl bg-indigo-600 text-white text-xs font-bold hover:bg-indigo-700 disabled:opacity-40"
                          >
                            Next Step →
                          </button>
                        </div>
                      </motion.div>

                      {/* Embedded Topic Doubt Resolution Chat */}
                      <div className="p-5 rounded-3xl bg-white border border-slate-200 shadow-xs">
                        <h4 className="text-xs font-bold text-slate-900 flex items-center gap-1.5">
                          <HelpCircle size={15} className="text-indigo-600" />
                          Have a Specific Doubt on this Topic?
                        </h4>
                        <div className="mt-3 flex items-center gap-2">
                          <input
                            type="text"
                            value={topicDoubtInput}
                            onChange={(e) => setTopicDoubtInput(e.target.value)}
                            placeholder="Ask a clarifying question..."
                            className="flex-1 text-xs px-3.5 py-2.5 rounded-xl bg-slate-50 border border-slate-200 focus:outline-indigo-600"
                            onKeyDown={(e) => e.key === 'Enter' && handleAskTopicDoubt()}
                          />
                          <button
                            onClick={handleAskTopicDoubt}
                            disabled={!topicDoubtInput.trim() || isLoadingDoubt}
                            className="py-2.5 px-4 rounded-xl bg-indigo-600 text-white text-xs font-bold hover:bg-indigo-700 disabled:opacity-50"
                          >
                            {isLoadingDoubt ? 'Solving...' : 'Resolve'}
                          </button>
                        </div>

                        {topicDoubtAnswer && (
                          <div className="mt-4 p-4 rounded-2xl bg-indigo-50/70 border border-indigo-100 text-xs text-slate-800 leading-relaxed">
                            <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                              {topicDoubtAnswer}
                            </ReactMarkdown>
                          </div>
                        )}
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            )}

            {/* TAB 3: TEACHER MODE (SSE STREAMED LECTURE) */}
            {activeTab === 'teacher' && (
              <div className="flex-1 overflow-y-auto p-6">
                <div className="max-w-3xl mx-auto space-y-6">
                  {/* Lecture Header */}
                  <div className="p-6 rounded-3xl bg-white border border-slate-200/80 shadow-xs flex items-center justify-between">
                    <div>
                      <span className="text-[10px] font-black uppercase tracking-widest text-indigo-600">
                        Teacher Mode · Immersive Live Masterclass
                      </span>
                      <h2 className="text-xl font-black text-slate-900 mt-1">
                        {activeTopic?.title || 'Select a Topic'}
                      </h2>
                      <div className="flex items-center gap-2 mt-2">
                        <span className="text-xs font-bold px-3 py-1 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
                          {currentLecturePhase}
                        </span>
                        {isTeacherStreaming && (
                          <span className="flex items-center gap-1.5 text-xs text-emerald-600 font-bold">
                            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
                            Live SSE Streaming
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      {isTeacherStreaming ? (
                        <button
                          onClick={handleStopTeacherLecture}
                          className="py-2 px-4 rounded-2xl bg-red-50 hover:bg-red-100 text-red-600 text-xs font-bold transition flex items-center gap-1.5 border border-red-200"
                        >
                          <Pause size={14} /> Stop
                        </button>
                      ) : (
                        <button
                          onClick={handleStartTeacherLecture}
                          className="py-2.5 px-5 rounded-2xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold transition flex items-center gap-1.5 shadow-md"
                        >
                          <Play size={14} /> Start Lecture
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Streamed Lecture Canvas */}
                  <div className="p-8 rounded-3xl bg-white border border-slate-200/90 shadow-xs min-h-[50vh]">
                    {teacherLectureText ? (
                      <div className="prose prose-sm max-w-none text-slate-800 leading-relaxed font-sans">
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm, remarkMath]}
                          rehypePlugins={[rehypeKatex]}
                          components={customMarkdownComponents}
                        >
                          {teacherLectureText}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <div className="text-center py-16">
                        <GraduationCap size={40} className="mx-auto text-indigo-400 mb-3" />
                        <h4 className="text-sm font-bold text-slate-700">Live University Lecture Stream</h4>
                        <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                          Click 'Start Lecture' to begin real-time streaming of first-principles intuition, deep mechanics, worked derivations, and exam traps.
                        </p>
                      </div>
                    )}

                    {/* Seamless Exam Handoff Button */}
                    {!isTeacherStreaming && teacherLectureText.length > 300 && (
                      <div className="mt-8 pt-6 border-t border-slate-100 flex items-center justify-between">
                        <p className="text-xs font-bold text-slate-500">Mastered this masterclass?</p>
                        <button
                          onClick={() => {
                            setActiveTab('exam')
                            if (activeTopic) handleFetchExam(activeTopic)
                          }}
                          className="py-2.5 px-5 rounded-2xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-black transition flex items-center gap-2 shadow-sm"
                        >
                          Take Topic Mastery Exam →
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* TAB 4: TOPIC MASTERY EXAM ENGINE */}
            {activeTab === 'exam' && (
              <div className="flex-1 overflow-y-auto p-6">
                <div className="max-w-3xl mx-auto space-y-6">
                  {/* Exam Header */}
                  <div className="p-6 rounded-3xl bg-white border border-slate-200/80 shadow-xs flex items-center justify-between">
                    <div>
                      <span className="text-[10px] font-black uppercase tracking-widest text-indigo-600">
                        Exam Engine · Written, MCQ & Fill-in-the-Blank
                      </span>
                      <h2 className="text-xl font-black text-slate-900 mt-1">
                        {activeTopic?.title || 'Mastery Exam'}
                      </h2>
                      <p className="text-xs text-slate-500 mt-1">
                        Automated rubric evaluation and grading for {activeTopic?.title}.
                      </p>
                    </div>

                    <button
                      onClick={() => activeTopic && handleFetchExam(activeTopic)}
                      disabled={isLoadingExam}
                      className="py-2 px-4 rounded-2xl bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-bold transition flex items-center gap-1.5"
                    >
                      <RefreshCw size={13} className={isLoadingExam ? 'animate-spin' : ''} />
                      Retake Exam
                    </button>
                  </div>

                  {isLoadingExam ? (
                    <div className="p-12 text-center">
                      <div className="w-10 h-10 border-3 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                      <p className="text-xs font-bold text-slate-500">Generating Mixed Exam Questions...</p>
                    </div>
                  ) : examEvaluation ? (
                    /* Evaluation Report View */
                    <div className="space-y-6">
                      <div className="p-6 rounded-3xl bg-white border border-slate-200 shadow-sm flex items-center justify-between">
                        <div>
                          <span className="text-[10px] font-black uppercase text-slate-400">Score Earned</span>
                          <div className="text-3xl font-black text-slate-900 mt-0.5">
                            {examEvaluation.percentage}%
                          </div>
                          <p className="text-xs text-slate-500 mt-0.5">
                            {examEvaluation.score} of {examEvaluation.total_questions} Questions Earned
                          </p>
                        </div>
                        <div className="text-right">
                          <span className="text-base font-black px-4 py-2 rounded-2xl bg-indigo-50 text-indigo-700 border border-indigo-200 inline-block shadow-xs">
                            {examEvaluation.mastery_badge}
                          </span>
                        </div>
                      </div>

                      {/* Question Review Cards */}
                      <div className="space-y-4">
                        {examEvaluation.evaluations.map((ev, idx) => (
                          <div
                            key={ev.id}
                            className={`p-5 rounded-3xl bg-white border shadow-xs ${
                              ev.is_correct ? 'border-emerald-200' : 'border-amber-200'
                            }`}
                          >
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-xs font-bold text-slate-500">
                                Question {idx + 1} ({ev.type.toUpperCase()})
                              </span>
                              <span className={`text-xs font-black px-2.5 py-0.5 rounded-full ${
                                ev.is_correct ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
                              }`}>
                                {ev.score_percentage}%
                              </span>
                            </div>
                            <h4 className="text-sm font-bold text-slate-900 mb-2">{ev.question}</h4>
                            <div className="p-3 rounded-xl bg-slate-50 text-xs text-slate-700 mb-2">
                              <span className="font-bold">Your Answer: </span>
                              {ev.student_answer || '<Empty>'}
                            </div>
                            {ev.sample_model_answer && (
                              <div className="p-3 rounded-xl bg-indigo-50/60 text-xs text-indigo-900 mb-2">
                                <span className="font-bold">Model Answer: </span>
                                {ev.sample_model_answer}
                              </div>
                            )}
                            <p className="text-xs text-slate-600">
                              <span className="font-bold">Feedback: </span>
                              {ev.feedback}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    /* Question Answering Form */
                    <div className="space-y-5">
                      {examQuestions.map((q, idx) => (
                        <div key={q.id} className="p-6 rounded-3xl bg-white border border-slate-200/90 shadow-xs">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-[10px] font-black uppercase tracking-wider text-indigo-600">
                              Question {idx + 1} · {q.type === 'written' ? 'Written Synthesis' : q.type === 'mcq' ? 'Multiple Choice' : 'Fill in the Blank'}
                            </span>
                          </div>
                          <h3 className="text-sm font-bold text-slate-900 mb-4">{q.question}</h3>

                          {/* Written */}
                          {q.type === 'written' && (
                            <textarea
                              rows={3}
                              value={examAnswers[q.id] || ''}
                              onChange={(e) => setExamAnswers({ ...examAnswers, [q.id]: e.target.value })}
                              placeholder="Write your academic explanation..."
                              className="w-full text-xs p-3.5 rounded-2xl bg-slate-50 border border-slate-200 focus:outline-indigo-600 focus:bg-white"
                            />
                          )}

                          {/* MCQ */}
                          {q.type === 'mcq' && q.options && (
                            <div className="space-y-2">
                              {q.options.map((opt, oIdx) => {
                                const isSelected = examAnswers[q.id] === opt
                                return (
                                  <button
                                    key={oIdx}
                                    onClick={() => setExamAnswers({ ...examAnswers, [q.id]: opt })}
                                    className={`w-full text-left p-3 rounded-2xl text-xs font-semibold transition border ${
                                      isSelected
                                        ? 'bg-indigo-600 text-white border-indigo-600 shadow-xs'
                                        : 'bg-slate-50 hover:bg-slate-100 text-slate-700 border-slate-200'
                                    }`}
                                  >
                                    {opt}
                                  </button>
                                )
                              })}
                            </div>
                          )}

                          {/* Fill-in-the-Blank */}
                          {q.type === 'fill_in_the_blank' && (
                            <input
                              type="text"
                              value={examAnswers[q.id] || ''}
                              onChange={(e) => setExamAnswers({ ...examAnswers, [q.id]: e.target.value })}
                              placeholder="Type exact term or formula..."
                              className="w-full text-xs p-3 rounded-2xl bg-slate-50 border border-slate-200 focus:outline-indigo-600"
                            />
                          )}
                        </div>
                      ))}

                      {examQuestions.length > 0 && (
                        <button
                          onClick={handleSubmitExam}
                          disabled={isSubmittingExam}
                          className="w-full py-3.5 rounded-2xl bg-indigo-600 hover:bg-indigo-700 text-white font-black text-sm transition shadow-md disabled:opacity-50"
                        >
                          {isSubmittingExam ? 'Grading Submission via Rubrics...' : 'Submit Exam for Automated Grading'}
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </main>

          {/* Right Docked Artifact Viewer (Default) */}
          {artifactViewerOpen && artifactDockSide === 'right' && (
            <div className={`${artifactExpanded ? 'w-3/5' : 'w-[480px]'} h-full border-l border-slate-200 bg-white shadow-xl transition-all duration-300 z-10 flex flex-col`}>
              {renderArtifactPanel()}
            </div>
          )}
        </div>
      </div>

      {/* ─── 3. COLLAPSIBLE RIGHT CURRICULUM STUDY MAP ─── */}
      <AnimatePresence>
        {studyMapOpen && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 320, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            className="h-full border-l border-slate-200/80 bg-white/80 backdrop-blur-xl flex flex-col justify-between overflow-hidden flex-shrink-0"
          >
            <div className="p-4 flex flex-col h-full overflow-hidden">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <BookOpen size={16} className="text-indigo-600" />
                  <h3 className="text-xs font-black text-slate-900 uppercase tracking-wider">Curriculum Roadmap</h3>
                </div>
                <button
                  onClick={() => setStudyMapOpen(false)}
                  className="p-1 rounded-lg text-slate-400 hover:text-slate-700"
                >
                  <X size={14} />
                </button>
              </div>

              {/* Topic Stepper List */}
              <div className="mt-3 flex-1 overflow-y-auto space-y-2 pr-1">
                {topics.length === 0 ? (
                  <div className="py-12 text-center text-xs text-slate-400">
                    Upload a syllabus or textbook to generate your progressive curriculum roadmap.
                  </div>
                ) : (
                  topics.map((t, idx) => {
                    const isSelected = activeTopic?.id === t.id
                    return (
                      <div
                        key={t.id}
                        onClick={() => {
                          setActiveTopic(t)
                          if (activeTab === 'normal') fetchCoreIdea(t)
                          if (activeTab === 'exam') handleFetchExam(t)
                        }}
                        className={`p-3 rounded-2xl cursor-pointer transition border text-left ${
                          isSelected
                            ? 'bg-indigo-50/90 border-indigo-300 text-indigo-950 shadow-xs'
                            : 'bg-white hover:bg-slate-50 border-slate-200/80 text-slate-700'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-[10px] font-black text-slate-400">Topic {idx + 1}</span>
                          <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full ${
                            t.difficulty === 'Beginner'
                              ? 'bg-emerald-50 text-emerald-700'
                              : t.difficulty === 'Intermediate'
                              ? 'bg-amber-50 text-amber-700'
                              : 'bg-purple-50 text-purple-700'
                          }`}>
                            {t.difficulty}
                          </span>
                        </div>
                        <h4 className="text-xs font-bold line-clamp-1">{t.title}</h4>
                        <p className="text-[10px] text-slate-500 line-clamp-2 mt-0.5">{t.summary}</p>
                        <div className="mt-2 text-[9px] font-semibold text-slate-400 flex items-center justify-between">
                          <span>Est: {t.estimated_study_time}</span>
                          <span className="text-indigo-600 font-bold">Select →</span>
                        </div>
                      </div>
                    )
                  })
                )}
              </div>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

    </div>
  )

  // ─── Helper: Claude-Style Artifact Panel Render ───
  function renderArtifactPanel() {
    return (
      <div className="flex flex-col h-full overflow-hidden">
        {/* Artifact Top Bar */}
        <div className="p-3.5 px-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText size={16} className="text-indigo-600" />
            <span className="text-xs font-black text-slate-900">Claude-Style Artifact Viewer</span>
          </div>

          <div className="flex items-center gap-1.5">
            {/* Dock toggle */}
            <button
              onClick={() => setArtifactDockSide((d) => (d === 'right' ? 'left' : 'right'))}
              className="p-1.5 rounded-xl hover:bg-slate-200 text-slate-500 text-xs"
              title="Toggle Dock Side"
            >
              <Split size={14} />
            </button>

            {/* Expand width */}
            <button
              onClick={() => setArtifactExpanded(!artifactExpanded)}
              className="p-1.5 rounded-xl hover:bg-slate-200 text-slate-500"
              title={artifactExpanded ? 'Collapse' : 'Expand'}
            >
              {artifactExpanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            </button>

            {/* Close */}
            <button
              onClick={() => setArtifactViewerOpen(false)}
              className="p-1.5 rounded-xl hover:bg-slate-200 text-slate-500"
            >
              <X size={15} />
            </button>
          </div>
        </div>

        {/* Tab switcher: Preview vs Raw Markdown */}
        <div className="px-4 py-2 bg-white border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-1 p-0.5 bg-slate-100 rounded-xl text-xs">
            <button
              onClick={() => setArtifactTab('preview')}
              className={`px-3 py-1 rounded-lg font-bold transition ${
                artifactTab === 'preview' ? 'bg-white text-indigo-600 shadow-xs' : 'text-slate-600'
              }`}
            >
              Preview
            </button>
            <button
              onClick={() => setArtifactTab('raw')}
              className={`px-3 py-1 rounded-lg font-bold transition ${
                artifactTab === 'raw' ? 'bg-white text-indigo-600 shadow-xs' : 'text-slate-600'
              }`}
            >
              Raw Source
            </button>
          </div>

          {/* Export Utilities */}
          <div className="flex items-center gap-1.5">
            <button
              onClick={handleCopyArtifact}
              className="p-1.5 rounded-xl hover:bg-slate-100 text-slate-600 flex items-center gap-1 text-[11px] font-bold"
              title="Copy Markdown"
            >
              {copiedArtifact ? <Check size={13} className="text-emerald-600" /> : <Copy size={13} />}
              <span>{copiedArtifact ? 'Copied' : 'Copy'}</span>
            </button>
            <button
              onClick={handleExportMarkdown}
              className="p-1.5 rounded-xl hover:bg-slate-100 text-slate-600 flex items-center gap-1 text-[11px] font-bold"
              title="Download .md"
            >
              <Download size={13} />
              <span>.md</span>
            </button>
            <button
              onClick={handleExportPdf}
              className="py-1 px-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white flex items-center gap-1 text-[11px] font-bold shadow-xs"
              title="Publication-Grade PDF"
            >
              <Printer size={13} />
              <span>PDF</span>
            </button>
          </div>
        </div>

        {/* Artifact Content Canvas */}
        <div className="flex-1 overflow-y-auto p-6 bg-white">
          {artifactTab === 'preview' ? (
            <div className="prose prose-sm max-w-none text-slate-800 leading-relaxed font-sans">
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkMath]}
                rehypePlugins={[rehypeKatex]}
                components={customMarkdownComponents}
              >
                {currentArtifactMarkdown}
              </ReactMarkdown>
            </div>
          ) : (
            <textarea
              value={currentArtifactMarkdown}
              onChange={(e) => setCurrentArtifactMarkdown(e.target.value)}
              className="w-full h-full font-mono text-xs text-slate-700 bg-slate-50 p-4 rounded-2xl border border-slate-200 focus:outline-hidden"
            />
          )}
        </div>
      </div>
    )
  }
}
