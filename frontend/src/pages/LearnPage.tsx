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
  Brain, FileSpreadsheet, Eye, Play, Pause, X, ArrowUp,
  ThumbsUp, ThumbsDown
} from 'lucide-react'

import { studyApi, streamTeacherLecture } from '../services/api'
import { exportNotesToPdf } from '../utils/pdfExport'
import { useAuthStore } from '../stores/authStore'
import confetti from 'canvas-confetti'
import MermaidDiagram from '../components/MermaidDiagram'
import StudyNotesCard, { extractDocTitle } from '../components/StudyNotesCard'
import ConfirmModal from '../components/ConfirmModal'

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
  response_format?: string
  export_ready?: boolean
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
  const [expandedInlineNotes, setExpandedInlineNotes] = useState<Record<string, boolean>>({})

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

  // Voice Tutor & Reading System (Cognitive Minimalist TTS)
  const [speakingMsgId, setSpeakingMsgId] = useState<string | null>(null)
  const [speakingWordIndex, setSpeakingWordIndex] = useState<number | null>(null)
  const [isListeningVoice, setIsListeningVoice] = useState(false)
  const ttsIntervalRef = useRef<any>(null)

  // Floating Input Bar & Attachments
  const [attachedFile, setAttachedFile] = useState<{ name: string; sizeFormatted: string; rawFile?: File } | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const chatScrollRef = useRef<HTMLDivElement | null>(null)
  const [showScrollBottom, setShowScrollBottom] = useState(false)
  const [feedbackRatings, setFeedbackRatings] = useState<Record<string, 'good' | 'easier' | null>>({})

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
  const [uploadingFileMeta, setUploadingFileMeta] = useState<{ name: string; sizeFormatted: string } | null>(null)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadSubject, setUploadSubject] = useState('')

  // Student Profile
  const [studentMemory, setStudentMemory] = useState<any>(null)

  // Current Generated Markdown for Artifact Viewer
  const [currentArtifactMarkdown, setCurrentArtifactMarkdown] = useState<string>(
    `# DeepTutor Master Study Notes\n\nWelcome to your AI Study Room! Upload your course documents, textbook chapters, or lecture slides to generate comprehensive notes, formula breakdowns, and revision summaries.\n\n## What You Can Do Here\n- **Ask In-Depth Doubts**: Get clear, intuitive step-by-step explanations for tricky concepts.\n- **Solve Exercises & Tables**: Fill and solve textbook exercise tables and math problems.\n- **Prepare for Exams**: Generate revision notes and test your knowledge with interactive quizzes.`
  )

  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, isAgentThinking])

  const activeSessionIdRef = useRef(activeSessionId)
  useEffect(() => {
    activeSessionIdRef.current = activeSessionId
  }, [activeSessionId])

  // ─── 1. Load Sessions on Mount ───
  const fetchSessions = useCallback(async () => {
    try {
      const res = await studyApi.listSessions()
      const list = res.data || []
      setSessions(list)
      if (list.length > 0 && !activeSessionIdRef.current) {
        const first = list[0]
        setActiveSessionId(first.id)
        setActiveSubject(first.subject || 'General Study')
        setDocumentName(first.document_name || '')
      } else if (list.length === 0 && !activeSessionIdRef.current) {
        studyApi.createSession({ subject: 'General Study', title: 'Default Study Room' }).then((r) => {
          if (r.data && r.data.id) {
            setActiveSessionId(r.data.id)
            setSessions([r.data])
          }
        }).catch(() => { })
      }
    } catch (err) {
      console.error('Failed to load study sessions:', err)
    }
  }, [])

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

      // Prepare study notes in state, but do NOT auto-open viewer initially
      if (data.messages && data.messages.length > 0) {
        const latestNotes = [...data.messages].reverse().find((m: any) =>
          m.role === 'assistant' && (
            m.export_ready ||
            m.format === 'study_notes' ||
            m.response_format === 'study_notes' ||
            (Boolean(m.text) && m.text.startsWith('# ') && m.text.toLowerCase().includes('study notes'))
          )
        )
        if (latestNotes) {
          setCurrentArtifactMarkdown(latestNotes.text)
          setArtifactDockSide('right')
        }
        // No popup initially on session load; only pops up when clicking the note box
        setArtifactViewerOpen(false)
      } else {
        setArtifactViewerOpen(false)
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
    }).catch(() => { })
  }, [user?.id])

  // ─── 4. Document Ingestion Handler ───
  const handleFileUpload = async (file: File) => {
    const sizeStr = file.size < 1024 * 1024 
      ? `${(file.size / 1024).toFixed(1)} KB` 
      : `${(file.size / (1024 * 1024)).toFixed(2)} MB`
    setUploadingFileMeta({ name: file.name, sizeFormatted: sizeStr })
    setIsUploading(true)
    setUploadProgress(15)
    setUploadError(null)

    try {
      const interval = setInterval(() => {
        setUploadProgress((p) => (p < 85 ? p + 12 : p))
      }, 350)

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

      // Add student-friendly interactive welcome message in chat
      setMessages((prev) => [
        ...prev,
        {
          id: `sys-${Date.now()}`,
          role: 'assistant',
          text: `Welcome! I have prepared your study material for **${data.filename}**.\n\nYou can ask me to:\n- **Explain any concept or topic** with simple step-by-step intuition\n- **Solve exercises and fill tables** from any page in the book\n- **Generate quick revision notes, formulas, or practice quizzes**\n\nWhat would you like to explore first?`,
          thought_process: 'Study material loaded and ready for interactive learning.',
          format: 'conceptual'
        }
      ])

      fetchSessions()
      setTimeout(() => {
        setIsUploading(false)
        setUploadingFileMeta(null)
      }, 500)
    } catch (err: any) {
      setIsUploading(false)
      setUploadingFileMeta(null)
      const msg = err.response?.data?.detail || err.message || 'Upload failed'
      setUploadError(msg)
    }
  }

  // ─── 5. Send Chat Message (Planner -> Executor) ───
  const handleSendMessage = async (customQuery?: string) => {
    // If a file is attached without text, upload the file directly
    if (attachedFile?.rawFile && !customQuery && !inputQuery.trim()) {
      const fileToUpload = attachedFile.rawFile
      setAttachedFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      await handleFileUpload(fileToUpload)
      return
    }

    const q = customQuery || inputQuery
    if (!q.trim() || isAgentThinking) return

    // If a file is attached WITH text query, upload first then ask
    if (attachedFile?.rawFile) {
      const fileToUpload = attachedFile.rawFile
      setAttachedFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      await handleFileUpload(fileToUpload)
    }

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
        difficulty: activeTopic?.difficulty || 'Intermediate',
        history: messages.slice(-4).map((m) => ({ role: m.role, text: m.text }))
      })

      const isExport = res.data.export_ready ?? (
        res.data.response_format === 'study_notes' ||
        res.data.format === 'study_notes' ||
        (Boolean(res.data.text) && res.data.text.startsWith('# ') && res.data.text.toLowerCase().includes('study notes'))
      )

      const assistantMsg: ChatMessage = {
        id: res.data.id || `ast-${Date.now()}`,
        role: 'assistant',
        text: res.data.text,
        thought_process: res.data.thought_process,
        sources: res.data.sources,
        quiz_data: res.data.quiz_data,
        format: res.data.format,
        response_format: res.data.response_format || res.data.format,
        export_ready: isExport,
        created_at: new Date().toISOString()
      }

      // ── Push assistant reply into the chat ──
      setMessages((prev) => [...prev, assistantMsg])

      // Update Artifact Viewer content with the latest notes/explanation (do not auto-popup; user clicks on box to pop up)
      if (isExport) {
        setCurrentArtifactMarkdown(res.data.text)
        setArtifactDockSide('right')
        setArtifactViewerOpen(false)
      } else if (res.data.text && res.data.text.length > 250) {
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

  // ─── 6. Speech Synthesis (Word-by-Word Cognitive Highlight) & Microphone Input ───
  const handleToggleVoice = (msgId: string, text: string) => {
    if (!('speechSynthesis' in window)) return

    if (speakingMsgId === msgId) {
      window.speechSynthesis.cancel()
      if (ttsIntervalRef.current) clearInterval(ttsIntervalRef.current)
      setSpeakingMsgId(null)
      setSpeakingWordIndex(null)
      return
    }

    window.speechSynthesis.cancel()
    if (ttsIntervalRef.current) clearInterval(ttsIntervalRef.current)

    // Clean text for speech synthesis
    const cleanText = text
      .replace(/```[\s\S]*?```/g, 'Code block omitted.')
      .replace(/[#*`_~>\[\]\(\)]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 1500)

    const words = cleanText.split(/\s+/).filter(Boolean)
    const utterance = new SpeechSynthesisUtterance(cleanText)
    utterance.rate = 1.0
    utterance.pitch = 1.0

    let currentWordIdx = 0
    setSpeakingWordIndex(0)

    // Real-time word boundary synchronization
    utterance.onboundary = (event) => {
      if (event.name === 'word') {
        const charIndex = event.charIndex
        const substr = cleanText.slice(0, charIndex)
        const wordCount = substr.trim().split(/\s+/).filter(Boolean).length
        currentWordIdx = Math.min(wordCount, words.length - 1)
        setSpeakingWordIndex(currentWordIdx)
      }
    }

    // Fallback cadence timer if browser synthesis does not fire onboundary
    const wordsPerMinute = 150
    const msPerWord = (60 / wordsPerMinute) * 1000
    ttsIntervalRef.current = setInterval(() => {
      currentWordIdx++
      if (currentWordIdx < words.length) {
        setSpeakingWordIndex((prev) => (prev !== null ? Math.max(prev, currentWordIdx) : currentWordIdx))
      } else {
        if (ttsIntervalRef.current) clearInterval(ttsIntervalRef.current)
      }
    }, msPerWord)

    utterance.onend = () => {
      if (ttsIntervalRef.current) clearInterval(ttsIntervalRef.current)
      setSpeakingMsgId(null)
      setSpeakingWordIndex(null)
    }

    utterance.onerror = () => {
      if (ttsIntervalRef.current) clearInterval(ttsIntervalRef.current)
      setSpeakingMsgId(null)
      setSpeakingWordIndex(null)
    }

    setSpeakingMsgId(msgId)
    window.speechSynthesis.speak(utterance)
  }

  const handleChatScroll = () => {
    if (!chatScrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = chatScrollRef.current
    setShowScrollBottom(scrollHeight - scrollTop - clientHeight > 140)
  }

  const handleFileAttach = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const sizeKb = (file.size / 1024).toFixed(1)
    const sizeFormatted = file.size > 1024 * 1024 ? `${(file.size / (1024 * 1024)).toFixed(1)} MB` : `${sizeKb} KB`
    setAttachedFile({ name: file.name, sizeFormatted, rawFile: file })
  }

  const handleRemoveAttachedFile = () => {
    setAttachedFile(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
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
      onPhaseEnd: () => { },
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

  const [sessionToDelete, setSessionToDelete] = useState<{ id: string; title: string } | null>(null)
  const [isDeletingSession, setIsDeletingSession] = useState(false)

  const handleDeleteSession = (sid: string, title?: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    setSessionToDelete({ id: sid, title: title || 'this study workspace' })
  }

  const confirmDeleteSession = async () => {
    if (!sessionToDelete) return
    setIsDeletingSession(true)
    const sid = sessionToDelete.id
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
      setSessionToDelete(null)
    } catch (err) {
      console.error('Delete session failed:', err)
    } finally {
      setIsDeletingSession(false)
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
    pre: ({ node, children, ...props }: any) => {
      const child = React.Children.toArray(children)[0] as any
      const className = child?.props?.className || ''
      if (className.includes('language-mermaid')) {
        return <>{children}</>
      }
      return (
        <pre className="my-4 p-4 rounded-xl bg-slate-900 text-slate-100 font-mono text-xs overflow-x-auto border border-slate-800" {...props}>
          {children}
        </pre>
      )
    },
    code: ({ node, inline, className, children, ...props }: any) => {
      const match = /language-(\w+)/.exec(className || '')
      const lang = match ? match[1] : ''
      const codeString = String(children).replace(/\n$/, '')
      if (!inline && lang === 'mermaid') {
        return <MermaidDiagram chart={codeString} />
      }
      return <code className={className} {...props}>{children}</code>
    },
  }), [])

  return (
    <div className="flex h-screen w-full bg-[#F9FAFB] text-[#000000] font-serif antialiased overflow-hidden">

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
                    <div className="w-8 h-8 rounded-full bg-slate-900 text-white flex items-center justify-center shadow-xs">
                      <Layers size={16} />
                    </div>
                    <div>
                      <h3 className="text-xs font-bold text-slate-900 leading-tight">Course Workspaces</h3>
                      <p className="learn-caption text-slate-400 font-medium">Session-Isolated SQLite DBs</p>
                    </div>
                  </div>
                  <button
                    onClick={() => setWorkspaceOpen(false)}
                    className="p-1.5 rounded-full hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition cursor-pointer"
                  >
                    <X size={15} />
                  </button>
                </div>

                {/* New Session Button */}
                <button
                  onClick={handleCreateNewSession}
                  className="w-full mt-4 flex items-center justify-center gap-2 py-2.5 px-4 rounded-full bg-slate-900 hover:bg-slate-800 text-white font-medium text-xs transition shadow-xs cursor-pointer"
                >
                  <Plus size={14} />
                  New Course Workspace
                </button>

                {/* Document Upload Area */}
                <div className="mt-4 p-4 rounded-2xl bg-slate-50/70 border border-dashed border-slate-200 text-center">
                  <UploadCloud size={22} className="mx-auto text-slate-600 mb-2" />
                  <p className="text-xs font-bold text-slate-800">Upload Study Material</p>
                  <p className="learn-caption text-slate-400 mb-3">PDF, Scanned Docs, Word, PPTX</p>

                  <input
                    type="text"
                    value={uploadSubject}
                    onChange={(e) => setUploadSubject(e.target.value)}
                    placeholder="Course / Subject name"
                    className="w-full text-xs px-3 py-1.5 rounded-xl bg-white border border-slate-200 mb-2.5 text-slate-800 placeholder-slate-400 focus:outline-none focus:border-slate-400"
                  />

                  <label className="inline-block py-2 px-5 rounded-full bg-slate-900 text-white font-medium text-xs cursor-pointer hover:bg-slate-800 transition shadow-xs">
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
                      <div className="flex items-center justify-between learn-caption font-bold text-slate-700 mb-1">
                        <span>{uploadSubject} - Processing...</span>
                        <span>{uploadProgress}%</span>
                      </div>
                      <div className="w-full h-1.5 bg-slate-200 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-slate-900 transition-all duration-300"
                          style={{ width: `${uploadProgress}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {uploadError && (
                    <p className="mt-2 learn-caption text-red-600 font-semibold">{uploadError}</p>
                  )}
                </div>

                {/* Active Sessions List */}
                <div className="mt-4 max-h-[38vh] overflow-y-auto space-y-2 pr-1">
                  <span className="learn-caption font-bold uppercase tracking-wider text-slate-400 px-1">
                    Your Active Courses ({sessions.length})
                  </span>
                  {sessions.map((s) => {
                    const isActive = s.id === activeSessionId
                    return (
                      <div
                        key={s.id}
                        onClick={() => handleSelectSession(s.id)}
                        className={`group relative p-3.5 rounded-2xl cursor-pointer transition border ${isActive
                          ? 'bg-slate-100/90 border-slate-300/90 text-slate-900 shadow-xs font-semibold'
                          : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200/80 shadow-xs'
                          }`}
                      >
                        <div className="flex items-start justify-between">
                          <div className="pr-4 overflow-hidden">
                            <h4 className="text-xs font-bold truncate text-slate-900">
                              {s.title}
                            </h4>
                            <p className="learn-caption truncate mt-0.5 text-slate-500">
                              {s.document_name || s.subject}
                            </p>
                          </div>
                          <button
                            onClick={(e) => handleDeleteSession(s.id, s.title, e)}
                            className="opacity-0 group-hover:opacity-100 p-1 rounded-lg transition hover:bg-slate-200/70 text-slate-400 hover:text-red-600"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                        <div className="mt-2 flex items-center gap-3 learn-caption font-medium text-slate-400">
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
                    <Brain size={14} className="text-slate-700" />
                    <span className="learn-caption font-bold text-slate-800">Episodic Profile</span>
                  </div>
                  <p className="learn-caption text-slate-500 line-clamp-2">
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

        {/* ─── Mode Content Area ─── */}
        <div className="flex-1 flex overflow-hidden relative">

          {/* Left Docked Artifact Viewer (if configured to dock left) */}
          {artifactViewerOpen && artifactDockSide === 'left' && (
            <div className={`${artifactExpanded ? 'w-3/5' : 'w-[480px]'} h-full border-r border-slate-200 bg-white shadow-xl transition-all duration-300 z-30 flex flex-col`}>
              {renderArtifactPanel()}
            </div>
          )}

          {/* ─── Central Active Workspace View ─── */}
          <main className="flex-1 flex flex-col h-full overflow-hidden relative">

            {/* ─── Top Header & Controls (Floating Translucent Ambient Bar like Chatbox) ─── */}
            <header className="absolute top-0 inset-x-0 pt-3.5 pb-6 px-4 sm:px-6 bg-transparent flex items-center justify-between gap-3 flex-shrink-0 z-20 pointer-events-none floating-header-gradient">
              {/* Left Course / Document Pill */}
              <div className="flex items-center gap-2 pointer-events-auto shrink-0 max-w-[28%] sm:max-w-[30%]">
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/95 border border-slate-200/80 shadow-[0_2px_12px_rgba(0,0,0,0.04)] backdrop-blur-md min-w-0">
                  <button
                    onClick={() => setWorkspaceOpen(true)}
                    className="text-slate-500 hover:text-slate-900 transition flex items-center gap-1.5 text-xs font-medium cursor-pointer shrink-0"
                    title="Open Workspaces & Courses"
                  >
                    <PanelLeft size={14} />
                    <span className="hidden md:inline">Courses</span>
                  </button>

                  <div className="h-3.5 w-[1px] bg-slate-200 shrink-0" />

                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className="text-xs font-medium text-slate-700 font-sans truncate max-w-[120px] sm:max-w-[180px] md:max-w-[220px]" title={documentName ? documentName : activeSubject}>
                      {documentName ? documentName : activeSubject}
                    </span>
                  </div>
                </div>
              </div>

              {/* Mode Switcher Tabs (Individual Centered Floating Pills with Gap) */}
              <div className="absolute left-1/2 -translate-x-1/2 flex items-center gap-1.5 sm:gap-2 pointer-events-auto z-10">
                <button
                  onClick={() => setActiveTab('chat')}
                  className={`px-3.5 py-1.5 rounded-full text-xs font-medium transition-all flex items-center gap-1.5 cursor-pointer backdrop-blur-md ${activeTab === 'chat'
                    ? 'bg-white text-slate-900 font-bold border border-slate-300 shadow-sm'
                    : 'bg-white/85 text-slate-600 hover:text-slate-900 hover:bg-white border border-slate-200/80 shadow-2xs'
                    }`}
                >
                  <BookOpen size={13} className={activeTab === 'chat' ? 'text-slate-900' : 'text-slate-500'} />
                  <span className="hidden sm:inline">Tutor Chat</span>
                </button>

                <button
                  onClick={() => setActiveTab('normal')}
                  className={`px-3.5 py-1.5 rounded-full text-xs font-medium transition-all flex items-center gap-1.5 cursor-pointer backdrop-blur-md ${activeTab === 'normal'
                    ? 'bg-white text-slate-900 font-bold border border-slate-300 shadow-sm'
                    : 'bg-white/85 text-slate-600 hover:text-slate-900 hover:bg-white border border-slate-200/80 shadow-2xs'
                    }`}
                >
                  <Sparkles size={13} className={activeTab === 'normal' ? 'text-slate-900' : 'text-slate-500'} />
                  <span className="hidden sm:inline">Normal Mode</span>
                </button>

                <button
                  onClick={() => setActiveTab('teacher')}
                  className={`px-3.5 py-1.5 rounded-full text-xs font-medium transition-all flex items-center gap-1.5 cursor-pointer backdrop-blur-md ${activeTab === 'teacher'
                    ? 'bg-white text-slate-900 font-bold border border-slate-300 shadow-sm'
                    : 'bg-white/85 text-slate-600 hover:text-slate-900 hover:bg-white border border-slate-200/80 shadow-2xs'
                    }`}
                >
                  <GraduationCap size={13} className={activeTab === 'teacher' ? 'text-slate-900' : 'text-slate-500'} />
                  <span className="hidden sm:inline">Teacher Mode</span>
                </button>

                <button
                  onClick={() => setActiveTab('exam')}
                  className={`px-3.5 py-1.5 rounded-full text-xs font-medium transition-all flex items-center gap-1.5 cursor-pointer backdrop-blur-md ${activeTab === 'exam'
                    ? 'bg-white text-slate-900 font-bold border border-slate-300 shadow-sm'
                    : 'bg-white/85 text-slate-600 hover:text-slate-900 hover:bg-white border border-slate-200/80 shadow-2xs'
                    }`}
                >
                  <Award size={13} className={activeTab === 'exam' ? 'text-slate-900' : 'text-slate-500'} />
                  <span className="hidden sm:inline">Topic Exam</span>
                </button>
              </div>

              {/* Right Action Controls (Floating Pill) */}
              <div className="flex items-center gap-2 pointer-events-auto shrink-0">
                <button
                  onClick={() => setStudyMapOpen(!studyMapOpen)}
                  className={`px-3 py-1.5 rounded-full border transition text-xs font-semibold flex items-center gap-1.5 cursor-pointer shadow-[0_2px_12px_rgba(0,0,0,0.04)] backdrop-blur-md ${studyMapOpen
                    ? 'bg-slate-100 text-slate-900 border-slate-300'
                    : 'bg-white/95 text-slate-700 hover:text-slate-900 hover:bg-slate-50 border-slate-200/80'
                    }`}
                  title="Curriculum Study Map"
                >
                  <PanelRight size={14} />
                  <span className="hidden xl:inline">Curriculum</span>
                </button>
              </div>
            </header>

            {/* TAB 1: GROUNDED TUTOR CHAT (IndTutor Cognitive Minimalist Experience) */}
            {activeTab === 'chat' && (
              <div className="flex-1 flex flex-col h-full overflow-hidden relative bg-[#F9FAFB]">
                {/* Message Scroll Container */}
                <div
                  ref={chatScrollRef}
                  onScroll={handleChatScroll}
                  className="flex-1 overflow-y-auto px-4 sm:px-8 pt-24 sm:pt-28 pb-36"
                >
                  {messages.length === 0 && !isAgentThinking && !isUploading && (
                    <div className="flex flex-col items-center justify-center min-h-[50vh] text-center max-w-lg mx-auto pt-6">
                      <div className="w-14 h-14 rounded-2xl bg-white border border-slate-200 text-slate-800 flex items-center justify-center mb-4 shadow-sm">
                        <BookOpen size={24} className="text-slate-800" />
                      </div>
                      <h3 className="text-xl font-bold text-slate-900 font-serif tracking-tight">Your Academic Workspace is Ready</h3>
                      <p className="text-sm text-slate-500 mt-2 leading-relaxed font-serif">
                        Explore your course material with verified, citation-grounded tutoring. Mathematical formulations, structured tables, and downloadable study notes are ready on demand.
                      </p>
                    </div>
                  )}

                  {(messages.length > 0 || isAgentThinking || isUploading) && (
                    <div className="max-w-3xl mx-auto w-full flex flex-col gap-6 pt-2 sm:pt-4">
                      {messages.map((msg) => {
                        const isUser = msg.role === 'user'
                        const isThoughtExpanded = expandedThoughtIds[msg.id] ?? false
                        const isStudyNotes = !isUser && (
                          Boolean(msg.export_ready) ||
                          msg.response_format === 'study_notes' ||
                          msg.format === 'study_notes' ||
                          (Boolean(msg.text) && msg.text.startsWith('# ') && msg.text.toLowerCase().includes('study notes'))
                        )

                        return (
                          <motion.div
                            key={msg.id}
                            initial={{ opacity: 0, y: 5 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.25, ease: 'easeOut' }}
                            className={`flex flex-col ${isUser ? 'items-end' : 'items-start w-full'}`}
                          >
                            {/* ─── USER MESSAGE BUBBLE (Right-aligned, white card with tail) ─── */}
                            {isUser ? (
                              <div className="bg-[#FFFFFF] border-[1.5px] border-[#E5E7EB] rounded-[14px_14px_4px_14px] px-4 py-2.5 max-w-[80%] shadow-[0_2px_8px_rgba(27,35,64,0.04)] chat-reading text-[#000000] font-serif">
                                {msg.text}
                              </div>
                            ) : (
                              /* ─── AI MESSAGE (Full-width, sits directly on paper bg) ─── */
                              <div className="w-full max-w-3xl flex flex-col items-start text-left">
                                {/* Optional Thought Process Disclosure */}
                                {msg.thought_process && (
                                  <div className="mb-2.5 w-full rounded-xl bg-slate-50/90 border border-slate-200/70 overflow-hidden font-sans">
                                    <button
                                      onClick={() =>
                                        setExpandedThoughtIds((p) => ({ ...p, [msg.id]: !isThoughtExpanded }))
                                      }
                                      className="w-full flex items-center justify-between px-3 py-1.5 learn-caption font-semibold text-slate-500 hover:text-slate-800 transition cursor-pointer"
                                    >
                                      <span className="flex items-center gap-1.5">
                                        <Brain size={13} className="text-slate-600" />
                                        IndTutor Grounding Pass & Reasoning
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

                                {/* EQUALIZER INDICATOR (when reading aloud) */}
                                {speakingMsgId === msg.id && (
                                  <div className="flex items-center gap-2 mb-2 px-2 py-1 rounded-md bg-slate-100/90 border border-slate-200/60 w-fit">
                                    <div className="flex items-end gap-[3px] h-3.5 px-0.5">
                                      <span className="w-[2px] bg-[#334155] rounded-full animate-audio-bar-1" />
                                      <span className="w-[2px] bg-[#334155] rounded-full animate-audio-bar-2" />
                                      <span className="w-[2px] bg-[#334155] rounded-full animate-audio-bar-3" />
                                    </div>
                                    <span className="learn-caption font-semibold text-slate-600 font-sans">
                                      Reading aloud...
                                    </span>
                                    <button
                                      onClick={() => handleToggleVoice(msg.id, msg.text)}
                                      className="learn-caption text-slate-400 hover:text-slate-800 ml-1 underline cursor-pointer font-sans"
                                    >
                                      Stop
                                    </button>
                                  </div>
                                )}

                                {/* Message Content: Word-by-Word Highlight OR Study Notes OR Editorial Markdown */}
                                {speakingMsgId === msg.id ? (
                                  /* WORD-BY-WORD HIGHLIGHT MODE */
                                  <div className="markdown-content text-slate-900 leading-[1.85] flex flex-wrap gap-y-1 items-baseline w-full">
                                    {msg.text
                                      .replace(/```[\s\S]*?```/g, '')
                                      .replace(/[#*`_~>\[\]\(\)]/g, ' ')
                                      .split(/\s+/)
                                      .filter(Boolean)
                                      .map((word, wIdx) => {
                                        const isCurrent = wIdx === speakingWordIndex
                                        const isPast = speakingWordIndex !== null && wIdx < speakingWordIndex
                                        return (
                                          <span
                                            key={wIdx}
                                            className={`inline-block mr-1.5 transition-all duration-150 ${isCurrent
                                              ? 'bg-amber-300 text-slate-950 font-bold px-1.5 py-0.5 rounded-md ring-2 ring-amber-400/60 scale-105 shadow-xs'
                                              : isPast
                                                ? 'text-slate-900 font-medium'
                                                : 'text-slate-400 opacity-75'
                                              }`}
                                          >
                                            {word}
                                          </span>
                                        )
                                      })}
                                  </div>
                                ) : isStudyNotes ? (
                                  /* Study Notes Response (Matching Claude design) */
                                  <div className="w-full">
                                    <p className="text-sm leading-relaxed text-slate-700 mb-2.5 font-serif">
                                      I have prepared the structured study notes reference document for{' '}
                                      <strong className="text-slate-900 font-semibold">
                                        {extractDocTitle(msg.text) || `${activeSubject || 'Study'} notes`}
                                      </strong>
                                      . You can view the full formatted document in the Markdown viewer on the right or download the{' '}
                                      <code className="text-xs font-mono bg-slate-100 px-1 py-0.5 rounded text-slate-700">.md</code> file below.
                                    </p>

                                    <StudyNotesCard
                                      markdown={msg.text}
                                      title={extractDocTitle(msg.text) || `${activeSubject || 'Study'} notes`}
                                      className="mb-2"
                                      onOpenViewer={() => {
                                        setCurrentArtifactMarkdown(msg.text)
                                        setArtifactViewerOpen(true)
                                        setArtifactDockSide('right')
                                        setStudyMapOpen(false)
                                      }}
                                    />

                                    <button
                                      onClick={() => setExpandedInlineNotes((p) => ({ ...p, [msg.id]: !p[msg.id] }))}
                                      className="learn-caption font-semibold text-slate-400 hover:text-slate-700 transition flex items-center gap-1 mt-1 cursor-pointer font-sans"
                                    >
                                      {expandedInlineNotes[msg.id] ? (
                                        <>Collapse inline preview <ChevronDown size={12} /></>
                                      ) : (
                                        <>Preview full notes in chat <ChevronRight size={12} /></>
                                      )}
                                    </button>

                                    {expandedInlineNotes[msg.id] && (
                                      <div className="mt-3 pt-3 border-t border-slate-200/80 markdown-content">
                                        <ReactMarkdown
                                          remarkPlugins={[remarkGfm, remarkMath]}
                                          rehypePlugins={[rehypeKatex]}
                                          components={customMarkdownComponents}
                                        >
                                          {msg.text}
                                        </ReactMarkdown>
                                      </div>
                                    )}
                                  </div>
                                ) : (
                                  /* Standard Editorial Markdown Render */
                                  <div className="w-full markdown-content">
                                    <ReactMarkdown
                                      remarkPlugins={[remarkGfm, remarkMath]}
                                      rehypePlugins={[rehypeKatex]}
                                      components={customMarkdownComponents}
                                    >
                                      {msg.text}
                                    </ReactMarkdown>
                                  </div>
                                )}

                                {/* Action Footer: Listen + Feedback buttons */}
                                <div className="mt-3 flex items-center gap-2 chat-reading font-serif text-slate-400">
                                  <button
                                    onClick={() => handleToggleVoice(msg.id, msg.text)}
                                    className={`flex items-center gap-1 px-2 py-1 rounded hover:bg-slate-100 transition cursor-pointer ${speakingMsgId === msg.id ? 'text-indigo-600' : 'hover:text-slate-600'
                                      }`}
                                    title="Read aloud"
                                  >
                                    <Volume2 size={15} />
                                    <span>Listen</span>
                                  </button>

                                  <span className="text-slate-200">|</span>

                                  <button
                                    onClick={() =>
                                      setFeedbackRatings((p) => ({ ...p, [msg.id]: p[msg.id] === 'good' ? null : 'good' }))
                                    }
                                    className={`flex items-center gap-1 px-2 py-1 rounded hover:bg-slate-100 transition cursor-pointer ${feedbackRatings[msg.id] === 'good' ? 'text-emerald-700 bg-emerald-50' : 'hover:text-slate-600'
                                      }`}
                                    title="Mark as helpful"
                                  >
                                    <ThumbsUp size={15} />
                                    <span>Good</span>
                                  </button>

                                  <span className="text-slate-200">|</span>

                                  <button
                                    onClick={() => {
                                      setFeedbackRatings((p) => ({ ...p, [msg.id]: p[msg.id] === 'easier' ? null : 'easier' }))
                                      handleSendMessage('Please explain that more simply with an everyday analogy and clearer terms.')
                                    }}
                                    className={`flex items-center gap-1 px-2 py-1 rounded hover:bg-slate-100 transition cursor-pointer ${feedbackRatings[msg.id] === 'easier' ? 'text-amber-700 bg-amber-50' : 'hover:text-slate-600'
                                      }`}
                                    title="Simplify this explanation"
                                  >
                                    <ChevronDown size={15} />
                                    <span>Make it easier</span>
                                  </button>
                                </div>
                              </div>
                            )}
                          </motion.div>
                        )
                      })}

                      {/* ─── NATURAL TYPING / PRINTING INDICATOR ─── */}
                      {(isAgentThinking || isUploading) && (
                        <motion.div
                          initial={{ opacity: 0, y: 4 }}
                          animate={{ opacity: 1, y: 0 }}
                          className="flex items-center gap-2.5 py-2 px-1 text-slate-400"
                        >
                          <div className="flex items-center gap-1">
                            <span className="w-[5px] h-[5px] rounded-full bg-slate-500 animate-dot-1" />
                            <span className="w-[5px] h-[5px] rounded-full bg-slate-500 animate-dot-2" />
                            <span className="w-[5px] h-[5px] rounded-full bg-slate-500 animate-dot-3" />
                          </div>
                          <span className="text-xs italic font-serif text-slate-400">
                            {isUploading ? 'reading document...' : 'writing...'}
                          </span>
                        </motion.div>
                      )}
                    </div>
                  )}

                  {/* Spacer to push content above the floating input pill when scrolled to bottom */}
                  <div className="h-28 shrink-0" />
                  <div ref={messagesEndRef} />
                </div>

                {/* ─── SCROLL-TO-BOTTOM FLOATING BUTTON ─── */}
                <AnimatePresence>
                  {showScrollBottom && (
                    <motion.button
                      initial={{ opacity: 0, y: 6, scale: 0.9 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 6, scale: 0.9 }}
                      onClick={scrollToBottom}
                      className="absolute bottom-24 right-6 sm:right-10 w-7 h-7 rounded-full bg-white border border-slate-200 shadow-md flex items-center justify-center text-slate-500 hover:text-slate-800 hover:bg-slate-50 transition z-30 cursor-pointer"
                      title="Scroll to bottom"
                    >
                      <ChevronDown size={15} />
                    </motion.button>
                  )}
                </AnimatePresence>

                {/* ─── FLOATING TRANSLUCENT INPUT BAR ─── */}
                <div className="absolute bottom-0 inset-x-0 pt-6 pb-3 pointer-events-none z-20 floating-input-gradient">
                  <div className="max-w-3xl mx-auto px-4 pointer-events-auto">
                    {/* Animated File Attachment Pill */}
                    <AnimatePresence>
                      {attachedFile && (
                        <motion.div
                          initial={{ opacity: 0, y: -4, height: 0 }}
                          animate={{ opacity: 1, y: 0, height: 'auto' }}
                          exit={{ opacity: 0, y: -4, height: 0 }}
                          className="mb-2 inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white border border-slate-200 shadow-sm text-xs font-sans"
                        >
                          <FileText size={14} className="text-blue-600 shrink-0" />
                          <span className="font-semibold text-slate-800 truncate max-w-[200px]">
                            {attachedFile.name}
                          </span>
                          <span className="text-slate-400 learn-caption">{attachedFile.sizeFormatted}</span>
                          <button
                            onClick={handleRemoveAttachedFile}
                            className="p-0.5 hover:bg-slate-100 rounded-full text-slate-400 hover:text-slate-600 cursor-pointer"
                            title="Remove attachment"
                          >
                            <X size={12} />
                          </button>
                        </motion.div>
                      )}
                    </AnimatePresence>

                    {/* ChatInputForm Pill */}
                    <div className="rounded-full bg-white border border-slate-200 shadow-[0_4px_20px_rgba(0,0,0,0.07)] focus-within:ring-2 focus-within:ring-slate-800/10 focus-within:border-slate-800 transition-all px-2.5 py-1.5 sm:px-3.5 sm:py-2 flex items-center gap-2">
                      {/* ① [+] Attach Button */}
                      <button
                        onClick={() => fileInputRef.current?.click()}
                        className="w-7 h-7 rounded-full bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-600 transition shrink-0 cursor-pointer"
                        title="Attach notes or document"
                      >
                        <Plus size={15} />
                      </button>
                      <input
                        type="file"
                        ref={fileInputRef}
                        className="hidden"
                        onChange={handleFileAttach}
                        accept=".pdf,.txt,.md,.docx,.png,.jpg"
                      />

                      {/* ② Textarea with auto-resize and serif font */}
                      <textarea
                        ref={textareaRef}
                        rows={1}
                        value={inputQuery}
                        onChange={(e) => {
                          setInputQuery(e.target.value)
                          if (textareaRef.current) {
                            textareaRef.current.style.height = 'auto'
                            textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px'
                          }
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault()
                            handleSendMessage()
                            if (textareaRef.current) textareaRef.current.style.height = 'auto'
                          }
                        }}
                        placeholder={`Ask questions about ${activeTopic?.title || 'your uploaded course notes'}...`}
                        className="flex-1 bg-transparent border-0 border-none outline-none focus:outline-none focus-visible:outline-none focus:ring-0 focus-visible:ring-0 ring-0 chat-reading font-serif text-slate-900 placeholder-slate-400 resize-none max-h-[120px] py-1 px-1.5 shadow-none"
                        style={{ outline: 'none', boxShadow: 'none', border: 'none' }}
                      />

                      {/* ③ Mic / Send Button */}
                      {(inputQuery.trim() || attachedFile) ? (
                        <button
                          onClick={() => {
                            handleSendMessage()
                            if (textareaRef.current) textareaRef.current.style.height = 'auto'
                          }}
                          disabled={isAgentThinking || isUploading}
                          className="w-8 h-8 rounded-full bg-[#000000] hover:bg-slate-800 text-white flex items-center justify-center transition shrink-0 cursor-pointer shadow-xs disabled:opacity-40"
                          title={attachedFile ? "Upload and analyze document" : "Send message"}
                        >
                          <ArrowUp size={16} />
                        </button>
                      ) : (
                        <button
                          onClick={handleToggleMic}
                          className={`w-8 h-8 rounded-full flex items-center justify-center transition shrink-0 cursor-pointer ${isListeningVoice
                            ? 'bg-red-500 text-white animate-pulse'
                            : 'text-slate-400 hover:text-slate-700 hover:bg-slate-100'
                            }`}
                          title="Voice input"
                        >
                          <Mic size={17} />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 2: NORMAL MODE (4-STEP CORE IDEA) */}
            {activeTab === 'normal' && (
              <div className="flex-1 overflow-y-auto p-6 pt-28">
                <div className="max-w-3xl mx-auto space-y-6">
                  {/* Topic Title Header */}
                  <div className="p-6 rounded-3xl bg-white border border-slate-200/80 shadow-xs flex items-center justify-between">
                    <div>
                      <span className="learn-caption font-bold uppercase tracking-wider text-slate-500">
                        Normal Mode · 4-Phase Core Idea Distillation
                      </span>
                      <h2 className="text-xl font-black text-slate-900 mt-1 font-serif">
                        {activeTopic?.title || 'Select a Topic'}
                      </h2>
                      <p className="text-xs text-slate-500 mt-1">{activeTopic?.summary}</p>
                    </div>

                    <button
                      onClick={() => activeTopic && fetchCoreIdea(activeTopic)}
                      disabled={isLoadingCoreIdea}
                      className="p-2.5 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-700 transition cursor-pointer"
                      title="Refresh Core Idea"
                    >
                      <RefreshCw size={15} className={isLoadingCoreIdea ? 'animate-spin' : ''} />
                    </button>
                  </div>

                  {isLoadingCoreIdea ? (
                    <div className="p-12 text-center">
                      <div className="w-8 h-8 border-2 border-slate-800 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                      <p className="text-xs font-medium text-slate-500">Distilling 4-Phase Core Mechanics...</p>
                    </div>
                  ) : coreIdeaData ? (
                    <div className="space-y-4">
                      {/* Step Indicator Tabs */}
                      <div className="grid grid-cols-4 gap-2">
                        {['1. The Big Picture', '2. Core Principle', '3. Key Takeaways', '4. Common Pitfalls'].map((title, idx) => (
                          <button
                            key={idx}
                            onClick={() => setCoreIdeaStep(idx)}
                            className={`p-3 rounded-2xl text-xs font-medium transition text-left border cursor-pointer ${coreIdeaStep === idx
                              ? 'bg-slate-900 text-white border-slate-900 shadow-xs'
                              : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200/80'
                              }`}
                          >
                            <span className={`block learn-caption ${coreIdeaStep === idx ? 'text-slate-300' : 'text-slate-400'}`}>
                              Phase {idx + 1}
                            </span>
                            <span className="truncate block mt-0.5 font-semibold">{title.split('. ')[1]}</span>
                          </button>
                        ))}
                      </div>

                      {/* Active Card Body */}
                      <motion.div
                        key={coreIdeaStep}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="p-7 rounded-3xl bg-white border border-slate-200/90 shadow-xs"
                      >
                        {coreIdeaStep === 0 && (
                          <div>
                            <span className="learn-caption font-bold uppercase tracking-wider text-slate-400">Fundamental Intuition</span>
                            <h3 className="text-lg font-serif font-bold text-slate-900 mt-1 mb-3">The Big Picture</h3>
                            <div className="markdown-content text-slate-800 leading-relaxed font-serif">
                              <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                                {coreIdeaData.big_picture}
                              </ReactMarkdown>
                            </div>
                          </div>
                        )}

                        {coreIdeaStep === 1 && (
                          <div>
                            <span className="learn-caption font-bold uppercase tracking-wider text-slate-400">Governing Mechanics & Math</span>
                            <h3 className="text-lg font-serif font-bold text-slate-900 mt-1 mb-3">Core Principle & Formulas</h3>
                            <div className="markdown-content text-slate-800 leading-relaxed font-serif">
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
                            <span className="learn-caption font-bold uppercase tracking-wider text-emerald-600">High-Yield Revision</span>
                            <h3 className="text-lg font-serif font-bold text-slate-900 mt-1 mb-3">Key Takeaways</h3>
                            <ul className="space-y-3 font-serif">
                              {coreIdeaData.key_takeaways?.map((item, i) => (
                                <li key={i} className="flex items-start gap-2.5 text-sm text-slate-800">
                                  <CheckCircle2 size={16} className="text-emerald-600 flex-shrink-0 mt-0.5" />
                                  <span>{item}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {coreIdeaStep === 3 && (
                          <div>
                            <span className="learn-caption font-bold uppercase tracking-wider text-amber-600">Exam Traps & Misconceptions</span>
                            <h3 className="text-lg font-serif font-bold text-slate-900 mt-1 mb-3">Common Pitfalls</h3>
                            <ul className="space-y-3 font-serif">
                              {coreIdeaData.common_pitfalls?.map((item, i) => (
                                <li key={i} className="flex items-start gap-2.5 text-sm text-slate-800">
                                  <AlertCircle size={16} className="text-amber-500 flex-shrink-0 mt-0.5" />
                                  <span>{item}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Navigation stepper buttons */}
                        <div className="mt-8 pt-5 border-t border-slate-100 flex items-center justify-between">
                          <button
                            onClick={() => setCoreIdeaStep((s) => Math.max(0, s - 1))}
                            disabled={coreIdeaStep === 0}
                            className="py-2 px-5 rounded-full border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40 transition cursor-pointer"
                          >
                            ← Previous
                          </button>
                          <span className="text-xs font-medium text-slate-400">Step {coreIdeaStep + 1} of 4</span>
                          <button
                            onClick={() => setCoreIdeaStep((s) => Math.min(3, s + 1))}
                            disabled={coreIdeaStep === 3}
                            className="py-2 px-5 rounded-full bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 disabled:opacity-40 transition shadow-xs cursor-pointer"
                          >
                            Next Step →
                          </button>
                        </div>
                      </motion.div>

                      {/* Embedded Topic Doubt Resolution Chat */}
                      <div className="p-6 rounded-3xl bg-white border border-slate-200/90 shadow-xs">
                        <h4 className="text-xs font-bold text-slate-900 flex items-center gap-1.5">
                          <HelpCircle size={15} className="text-slate-700" />
                          Have a Specific Doubt on this Topic?
                        </h4>
                        <div className="mt-3 flex items-center gap-2">
                          <input
                            type="text"
                            value={topicDoubtInput}
                            onChange={(e) => setTopicDoubtInput(e.target.value)}
                            placeholder="Ask a clarifying question..."
                            className="flex-1 text-xs px-4 py-2.5 rounded-full bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:bg-white focus:border-slate-400"
                            onKeyDown={(e) => e.key === 'Enter' && handleAskTopicDoubt()}
                          />
                          <button
                            onClick={handleAskTopicDoubt}
                            disabled={!topicDoubtInput.trim() || isLoadingDoubt}
                            className="py-2.5 px-5 rounded-full bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 disabled:opacity-50 transition shadow-xs cursor-pointer"
                          >
                            {isLoadingDoubt ? 'Solving...' : 'Resolve'}
                          </button>
                        </div>

                        {topicDoubtAnswer && (
                          <div className="mt-4 p-5 rounded-2xl bg-slate-50/70 border border-slate-200 markdown-content text-sm text-slate-800 leading-relaxed font-serif">
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
              <div className="flex-1 overflow-y-auto p-6 pt-28">
                <div className="max-w-3xl mx-auto space-y-6">
                  {/* Lecture Header */}
                  <div className="p-6 rounded-3xl bg-white border border-slate-200/80 shadow-xs flex items-center justify-between">
                    <div>
                      <span className="learn-caption font-bold uppercase tracking-wider text-slate-500">
                        Teacher Mode · Immersive Live Masterclass
                      </span>
                      <h2 className="text-xl font-black text-slate-900 mt-1 font-serif">
                        {activeTopic?.title || 'Select a Topic'}
                      </h2>
                      <div className="flex items-center gap-2 mt-2">
                        <span className="text-xs font-semibold px-3 py-1 rounded-full bg-slate-100 text-slate-800 border border-slate-200">
                          {currentLecturePhase}
                        </span>
                        {isTeacherStreaming && (
                          <span className="flex items-center gap-1.5 text-xs text-emerald-600 font-semibold">
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
                          className="py-2 px-4 rounded-full bg-red-50 hover:bg-red-100 text-red-600 text-xs font-semibold transition flex items-center gap-1.5 border border-red-200 cursor-pointer"
                        >
                          <Pause size={14} /> Stop
                        </button>
                      ) : (
                        <button
                          onClick={handleStartTeacherLecture}
                          className="py-2.5 px-5 rounded-full bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold transition flex items-center gap-1.5 shadow-xs cursor-pointer"
                        >
                          <Play size={14} /> Start Lecture
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Streamed Lecture Canvas */}
                  <div className="p-8 rounded-3xl bg-white border border-slate-200/90 shadow-xs min-h-[50vh]">
                    {teacherLectureText ? (
                      <div className="markdown-content max-w-none text-slate-900 leading-relaxed font-serif">
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
                        <GraduationCap size={38} className="mx-auto text-slate-400 mb-3" />
                        <h4 className="text-sm font-bold text-slate-800">Live University Lecture Stream</h4>
                        <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto font-serif">
                          Click 'Start Lecture' to begin real-time streaming of first-principles intuition, deep mechanics, worked derivations, and exam traps.
                        </p>
                      </div>
                    )}

                    {/* Seamless Exam Handoff Button */}
                    {!isTeacherStreaming && teacherLectureText.length > 300 && (
                      <div className="mt-8 pt-6 border-t border-slate-100 flex items-center justify-between">
                        <p className="text-xs font-medium text-slate-500">Mastered this masterclass?</p>
                        <button
                          onClick={() => {
                            setActiveTab('exam')
                            if (activeTopic) handleFetchExam(activeTopic)
                          }}
                          className="py-2.5 px-5 rounded-full bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold transition flex items-center gap-2 shadow-xs cursor-pointer"
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
              <div className="flex-1 overflow-y-auto p-6 pt-28">
                <div className="max-w-3xl mx-auto space-y-6">
                  {/* Exam Header */}
                  <div className="p-6 rounded-3xl bg-white border border-slate-200/80 shadow-xs flex items-center justify-between">
                    <div>
                      <span className="learn-caption font-bold uppercase tracking-wider text-slate-500">
                        Exam Engine · Written, MCQ & Fill-in-the-Blank
                      </span>
                      <h2 className="text-xl font-black text-slate-900 mt-1 font-serif">
                        {activeTopic?.title || 'Mastery Exam'}
                      </h2>
                      <p className="text-xs text-slate-500 mt-1">
                        Automated rubric evaluation and grading for {activeTopic?.title}.
                      </p>
                    </div>

                    <button
                      onClick={() => activeTopic && handleFetchExam(activeTopic)}
                      disabled={isLoadingExam}
                      className="py-2 px-4 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-semibold transition flex items-center gap-1.5 cursor-pointer"
                    >
                      <RefreshCw size={13} className={isLoadingExam ? 'animate-spin' : ''} />
                      Retake Exam
                    </button>
                  </div>

                  {isLoadingExam ? (
                    <div className="p-12 text-center">
                      <div className="w-8 h-8 border-2 border-slate-800 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                      <p className="text-xs font-medium text-slate-500">Generating Mixed Exam Questions...</p>
                    </div>
                  ) : examEvaluation ? (
                    /* Evaluation Report View */
                    <div className="space-y-6">
                      <div className="p-6 rounded-3xl bg-white border border-slate-200 shadow-xs flex items-center justify-between">
                        <div>
                          <span className="learn-caption font-bold uppercase text-slate-400">Score Earned</span>
                          <div className="text-3xl font-black text-slate-900 mt-0.5">
                            {examEvaluation.percentage}%
                          </div>
                          <p className="text-xs text-slate-500 mt-0.5">
                            {examEvaluation.score} of {examEvaluation.total_questions} Questions Earned
                          </p>
                        </div>
                        <div className="text-right">
                          <span className="text-xs font-bold px-4 py-2 rounded-full bg-slate-100 text-slate-900 border border-slate-200 inline-block shadow-xs">
                            {examEvaluation.mastery_badge}
                          </span>
                        </div>
                      </div>

                      {/* Question Review Cards */}
                      <div className="space-y-4">
                        {examEvaluation.evaluations.map((ev, idx) => (
                          <div
                            key={ev.id}
                            className={`p-6 rounded-3xl bg-white border shadow-xs ${ev.is_correct ? 'border-emerald-200' : 'border-amber-200'
                              }`}
                          >
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-xs font-bold text-slate-500">
                                Question {idx + 1} ({ev.type.toUpperCase()})
                              </span>
                              <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${ev.is_correct ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' : 'bg-amber-50 text-amber-800 border border-amber-200'
                                }`}>
                                {ev.score_percentage}%
                              </span>
                            </div>
                            <h4 className="text-sm font-serif font-bold text-slate-900 mb-2">{ev.question}</h4>
                            <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-100 text-xs text-slate-700 mb-2 font-serif">
                              <span className="font-bold">Your Answer: </span>
                              {ev.student_answer || '<Empty>'}
                            </div>
                            {ev.sample_model_answer && (
                              <div className="p-3.5 rounded-xl bg-slate-50/80 border border-slate-200 text-xs text-slate-900 mb-2 font-serif">
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
                        <div key={q.id} className="p-7 rounded-3xl bg-white border border-slate-200/90 shadow-xs">
                          <div className="flex items-center justify-between mb-2">
                            <span className="learn-caption font-bold uppercase tracking-wider text-slate-400">
                              Question {idx + 1} · {q.type === 'written' ? 'Written Synthesis' : q.type === 'mcq' ? 'Multiple Choice' : 'Fill in the Blank'}
                            </span>
                          </div>
                          <h3 className="text-base font-serif font-bold text-slate-900 mb-4">{q.question}</h3>

                          {/* Written */}
                          {q.type === 'written' && (
                            <textarea
                              rows={3}
                              value={examAnswers[q.id] || ''}
                              onChange={(e) => setExamAnswers({ ...examAnswers, [q.id]: e.target.value })}
                              placeholder="Write your academic explanation..."
                              className="w-full text-sm p-4 rounded-2xl bg-slate-50/70 border border-slate-200 text-slate-900 font-serif focus:bg-white focus:outline-none focus:border-slate-400 leading-relaxed"
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
                                    className={`w-full text-left p-3.5 rounded-xl text-xs font-medium transition border cursor-pointer ${isSelected
                                      ? 'bg-slate-900 text-white border-slate-900 shadow-xs'
                                      : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200'
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
                              className="w-full text-xs px-4 py-2.5 rounded-full bg-slate-50/70 border border-slate-200 text-slate-900 focus:bg-white focus:outline-none focus:border-slate-400"
                            />
                          )}
                        </div>
                      ))}

                      {examQuestions.length > 0 && (
                        <button
                          onClick={handleSubmitExam}
                          disabled={isSubmittingExam}
                          className="w-full py-3.5 rounded-full bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs transition shadow-xs disabled:opacity-50 cursor-pointer"
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
                  <BookOpen size={15} className="text-slate-700" />
                  <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">FOCUS</h3>
                </div>
                <button
                  onClick={() => setStudyMapOpen(false)}
                  className="p-1 rounded-full text-slate-400 hover:text-slate-700 transition cursor-pointer"
                >
                  <X size={14} />
                </button>
              </div>

              {/* Topic Stepper List */}
              <div className="mt-3 flex-1 overflow-y-auto space-y-2 pr-1">
                {topics.length === 0 ? (
                  <div className="py-12 text-center text-xs text-slate-400 font-serif">
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
                        className={`p-3.5 rounded-2xl cursor-pointer transition border text-left ${isSelected
                          ? 'bg-slate-100/90 border-slate-300/90 text-slate-900 shadow-xs'
                          : 'bg-white hover:bg-slate-50 border-slate-200/80 text-slate-800 shadow-xs'
                          }`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="learn-caption font-bold text-slate-500">Topic {idx + 1}</span>
                          <span className={`text-[11px] ${isSelected ? 'text-slate-900 font-bold' : 'text-slate-500 font-medium'}`}>Select →</span>
                        </div>
                        <h4 className="text-xs font-bold line-clamp-1 text-slate-900">{t.title}</h4>
                        <p className="learn-caption line-clamp-2 mt-0.5 text-slate-500">{t.summary}</p>
                      </div>
                    )
                  })
                )}
              </div>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      {/* Delete Workspace Confirmation Modal */}
      <ConfirmModal
        isOpen={!!sessionToDelete}
        title="Delete Study Workspace?"
        itemName={sessionToDelete?.title}
        warningNote="Permanent Data Removal: All chat messages, generated notes, and database records for this session will be permanently deleted."
        isLoading={isDeletingSession}
        onConfirm={confirmDeleteSession}
        onCancel={() => setSessionToDelete(null)}
      />
    </div>
  )

  // ─── Helper: Claude-Style Artifact Panel Render ───
  function renderArtifactPanel() {
    return (
      <div className="flex flex-col h-full overflow-hidden">
        {/* Artifact Top Bar */}
        <div className="p-3 px-4 bg-white border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center gap-2 min-w-0">
            <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-mono learn-caption font-bold border border-slate-200/60">
              &lt;/&gt;
            </span>
            <span className="text-xs font-semibold text-slate-800 truncate">
              {extractDocTitle(currentArtifactMarkdown) || 'Study Notes'} · MD
            </span>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            {/* Dock toggle */}
            <button
              onClick={() => setArtifactDockSide((d) => (d === 'right' ? 'left' : 'right'))}
              className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 text-xs transition cursor-pointer"
              title={artifactDockSide === 'left' ? 'Dock to right' : 'Dock to left'}
            >
              <Split size={14} />
            </button>

            {/* Expand width */}
            <button
              onClick={() => setArtifactExpanded(!artifactExpanded)}
              className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 transition cursor-pointer"
              title={artifactExpanded ? 'Collapse width' : 'Expand width'}
            >
              {artifactExpanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            </button>

            {/* Close */}
            <button
              onClick={() => setArtifactViewerOpen(false)}
              className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 transition cursor-pointer"
              title="Close viewer"
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
              className={`px-3 py-1 rounded-lg font-bold transition ${artifactTab === 'preview' ? 'bg-white text-indigo-600 shadow-xs' : 'text-slate-600'
                }`}
            >
              Preview
            </button>
            <button
              onClick={() => setArtifactTab('raw')}
              className={`px-3 py-1 rounded-lg font-bold transition ${artifactTab === 'raw' ? 'bg-white text-indigo-600 shadow-xs' : 'text-slate-600'
                }`}
            >
              Raw Source
            </button>
          </div>

          {/* Export Utilities */}
          <div className="flex items-center gap-1.5">
            <button
              onClick={handleCopyArtifact}
              className="p-1.5 rounded-xl hover:bg-slate-100 text-slate-600 flex items-center gap-1 learn-caption font-bold"
              title="Copy Markdown"
            >
              {copiedArtifact ? <Check size={13} className="text-emerald-600" /> : <Copy size={13} />}
              <span>{copiedArtifact ? 'Copied' : 'Copy'}</span>
            </button>
            <button
              onClick={handleExportMarkdown}
              className="p-1.5 rounded-xl hover:bg-slate-100 text-slate-600 flex items-center gap-1 learn-caption font-bold"
              title="Download .md"
            >
              <Download size={13} />
              <span>.md</span>
            </button>
            <button
              onClick={handleExportPdf}
              className="py-1 px-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white flex items-center gap-1 learn-caption font-bold shadow-xs"
              title="Publication-Grade PDF"
            >
              <Printer size={13} />
              <span>PDF</span>
            </button>
          </div>
        </div>

        {/* Artifact Content Canvas */}
        <div className="flex-1 overflow-y-auto p-4 bg-white">
          {artifactTab === 'preview' ? (
            <div className="artifact-md-viewer prose prose-sm max-w-none font-serif leading-relaxed">
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
