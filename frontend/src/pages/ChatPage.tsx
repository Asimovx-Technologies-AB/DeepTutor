import { useEffect, useRef, useState, useCallback, useMemo, memo } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Send, Paperclip, Plus, MessageSquare,
  Sparkles, BookOpen, Brain, GraduationCap,
  CheckCircle, AlertCircle, Loader2, Trophy, Trash2,
  Mic, MicOff, Search, Share2, Download,
  ChevronDown, LogOut, Network,
  Clock, ArrowRight, Menu, X, Zap,
  ListChecks, Star, Lightbulb
} from 'lucide-react'
import { useChatStore } from '../stores/chatStore'
import { useAuthStore } from '../stores/authStore'
import { chatApi, documentsApi, streamChatMessage } from '../services/api'
import ChatMessage from '../components/ChatMessage'
import GraphContextPanel from '../components/GraphContextPanel'
import GamifiedQuizGame from '../components/GamifiedQuizGame'
import FlashcardsOverlay from '../components/FlashcardsOverlay'
import { UpgradeModal } from '../components/UpgradeModal'
import ConfirmModal from '../components/ConfirmModal'
import type { Source } from '../components/SourceCard'


// ─── Types ─────────────────────────────────────────────────────────────────────
interface GraphContextData {
  entities: any[]
  relationships: any[]
}

interface ExtendedMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
  sources?: Source[]
  graph_context?: GraphContextData
  grounding?: any
}

export interface ActiveUpload {
  docId: string
  fileName: string
  sizeMb?: number
}

// ─── Aesthetic Document Indexing Status Card ─────────────────────────────────────
// ─── Aesthetic Document Indexing Status Card with Continuous 1-100% Animation ────
function UploadStatusCard({
  upload,
  onDone,
  onError,
  onDismiss,
}: {
  upload: ActiveUpload
  onDone: (docId: string, stats: any) => void
  onError: (docId: string, error: string) => void
  onDismiss: (docId: string) => void
}) {
  const [status, setStatus] = useState<any>({ status: 'indexing', progress: 5, stage: 'parsing' })
  const [smoothProgress, setSmoothProgress] = useState(1)
  const statusRef = useRef(status)
  statusRef.current = status
  const smoothRef = useRef(1)
  const hasTriggeredDoneRef = useRef(false)

  // ─── Natural, Realistically Paced 1-100% Smooth Animation Loop ───
  useEffect(() => {
    let animFrame: number
    const tick = () => {
      const current = smoothRef.current
      const isDone = statusRef.current.status === 'done'
      const isError = statusRef.current.status === 'error'

      if (isError) {
        return // Freeze on error
      }

      if (isDone) {
        if (current < 100) {
          // Calm, satisfying glide to 100%
          const diff = 100 - current
          const step = Math.max(0.25, diff * 0.06)
          const next = Math.min(100, current + step)
          smoothRef.current = next
          setSmoothProgress(Math.round(next))
          animFrame = requestAnimationFrame(tick)
        } else {
          setSmoothProgress(100)
        }
        return
      }

      // In-progress: Target from backend status
      const backendTarget = typeof statusRef.current.progress === 'number' ? statusRef.current.progress : 10

      let next: number
      if (current < backendTarget) {
        // Smoothly catch up to backend stage with gentle damping
        const diff = backendTarget - current
        const step = Math.max(0.04, diff * 0.025)
        next = Math.min(backendTarget, current + step)
      } else {
        // Natural micro-creep while backend computes (approx 0.4% to 0.8% per second at 60fps)
        const ceiling = Math.min(94, backendTarget + 8)
        if (current < ceiling) {
          next = current + 0.008
        } else {
          next = current
        }
      }

      smoothRef.current = next
      setSmoothProgress(Math.round(next))

      animFrame = requestAnimationFrame(tick)
    }

    animFrame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(animFrame)
  }, [])

  // ─── Polling Backend Indexing Status ────────────────────────
  useEffect(() => {
    let doneTimer: any = null
    const interval = setInterval(async () => {
      try {
        const res = await documentsApi.status(upload.docId)
        const data = res.data
        setStatus(data)
        if (data.status === 'done') {
          clearInterval(interval)
          if (!hasTriggeredDoneRef.current) {
            hasTriggeredDoneRef.current = true
            onDone(upload.docId, data.stats)
          }
          doneTimer = setTimeout(() => {
            onDismiss(upload.docId)
          }, 4500)
        } else if (data.status === 'error') {
          clearInterval(interval)
          onError(upload.docId, data.error || 'Document processing encountered an error')
        }
      } catch {
        // network polling retry
      }
    }, 1200)

    return () => {
      clearInterval(interval)
      if (doneTimer) clearTimeout(doneTimer)
    }
  }, [upload.docId, onDone, onError, onDismiss])

  const isDone = status.status === 'done' || smoothProgress >= 100
  const isError = status.status === 'error'

  const stageInfo = useMemo(() => {
    if (isDone) {
      return {
        label: 'Knowledge Base Ready',
        step: 'Complete',
        badgeColor: 'bg-[#D7FFB8] text-[#58CC02] border-[#58CC02]/30',
        description: 'All chunks, vector embeddings & GraphRAG nodes indexed successfully',
      }
    }
    if (isError) {
      return {
        label: 'Processing Failed',
        step: 'Error',
        badgeColor: 'bg-[#FFD1D1] text-[#FF4B4B] border-[#FF4B4B]/30',
        description: status.error || 'Could not parse document. Please verify the file.',
      }
    }
    if (smoothProgress < 25) {
      return {
        label: 'Parsing Document Structure',
        step: 'Stage 1/4',
        badgeColor: 'bg-[#DDF4FF] text-[#1CB0F6] border-[#1CB0F6]/30',
        description: 'Extracting text, formulas & table layouts via Docling / PyMuPDF cascade...',
      }
    }
    if (smoothProgress < 55) {
      return {
        label: 'Semantic Chunking',
        step: 'Stage 2/4',
        badgeColor: 'bg-[#FFF0B3] text-[#FFC800] border-[#FFC800]/30',
        description: 'Building section tree & context-preserving semantic study chunks...',
      }
    }
    if (smoothProgress < 80) {
      return {
        label: 'Generating Vector Embeddings',
        step: 'Stage 3/4',
        badgeColor: 'bg-[#F0ECF7] text-[#8C76B2] border-[#8C76B2]/30',
        description: 'Indexing high-dimensional semantic embeddings into vector store...',
      }
    }
    return {
      label: 'Constructing GraphRAG',
      step: 'Stage 4/4',
      badgeColor: 'bg-[#D7FFB8] text-[#58CC02] border-[#58CC02]/30',
      description: 'Extracting key concepts & entity relationship triplets for deep reasoning...',
    }
  }, [isDone, isError, smoothProgress, status.error])

  return (
    <motion.div
      initial={{ opacity: 0, y: -8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -8, scale: 0.96 }}
      transition={{ duration: 0.35, ease: 'easeOut' }}
      className={`relative overflow-hidden rounded-[1.5rem] border p-4 sm:p-5 elevation-2 transition-all ${isDone
        ? 'bg-gradient-to-r from-[#F4FAF5] via-white to-[#F4FAF5] border-[#58CC02]/40'
        : isError
          ? 'bg-gradient-to-r from-[#FFF5F4] via-white to-[#FFF5F4] border-[#FF4B4B]/40'
          : 'bg-gradient-to-r from-[#FFFDF9] via-white to-[#FFFFFF] border-[#1CB0F6]/35'
        }`}
    >
      {/* Background glowing ambient light while processing */}
      {!isDone && !isError && (
        <div className="absolute top-0 right-0 -mt-8 -mr-8 w-44 h-44 bg-[#1CB0F6]/10 rounded-full blur-2xl pointer-events-none animate-pulse" />
      )}

      <div className="flex items-start justify-between gap-3 relative z-10">

        {/* Left Icon with animated spinner */}
        <div className="flex items-center gap-3.5 flex-1 min-w-0">
          <div className="relative flex-shrink-0">
            <div
              className={`w-12 h-12 rounded-[1.5rem] flex items-center justify-center border elevation-1 transition-transform ${isDone
                ? 'bg-[#D7FFB8] text-[#58CC02] border-[#58CC02]/30 scale-105'
                : isError
                  ? 'bg-[#FFD1D1] text-[#FF4B4B] border-[#FF4B4B]/30'
                  : 'bg-[#DDF4FF] text-[#1CB0F6] border-[#1CB0F6]/30'
                }`}
            >
              {isDone ? (
                <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', stiffness: 300, damping: 20 }}>
                  <CheckCircle size={24} className="text-[#58CC02]" />
                </motion.div>
              ) : isError ? (
                <AlertCircle size={22} className="text-[#FF4B4B]" />
              ) : (
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ repeat: Infinity, duration: 3.5, ease: 'linear' }}
                >
                  <Sparkles size={22} className="text-[#1CB0F6]" />
                </motion.div>
              )}
            </div>

            {/* Orbital ring while indexing */}
            {!isDone && !isError && (
              <div className="absolute -inset-1 rounded-[1.5rem] border-2 border-[#1CB0F6]/40 border-t-[#1CB0F6] animate-spin pointer-events-none" />
            )}
          </div>

          {/* Title & Live Stage */}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-extrabold text-sm text-[#3C3C3C] truncate max-w-[220px] sm:max-w-md">
                {upload.fileName}
              </span>
              {upload.sizeMb !== undefined && (
                <span className="text-[10px] font-bold text-[#777777] bg-[#E5E5E5] px-2 py-0.5 rounded-md border border-[#E2E8F0]">
                  {upload.sizeMb.toFixed(1)} MB
                </span>
              )}
              <span className={`text-[10px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded-full border ${stageInfo.badgeColor}`}>
                {stageInfo.step} • {stageInfo.label}
              </span>
            </div>

            <p className="text-xs text-[#777777] font-medium mt-1 truncate">
              {stageInfo.description}
            </p>
          </div>
        </div>

        {/* Right Percentage & Close Button */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <div className="text-right">
            <span className={`text-xl sm:text-2xl font-black tracking-tight ${isDone ? 'text-[#58CC02]' : isError ? 'text-[#FF4B4B]' : 'text-[#1CB0F6]'}`}>
              {smoothProgress}%
            </span>
          </div>

          <button
            onClick={() => onDismiss(upload.docId)}
            className="text-[#AFAFAF] hover:text-[#3C3C3C] p-1.5 rounded-[1.25rem] hover:bg-[#E5E5E5] transition-colors cursor-pointer"
            title="Dismiss notification"
          >
            <X size={16} />
          </button>
        </div>

      </div>

      {/* Animated Gradient Progress Bar with Shimmer */}
      <div className="mt-3.5 w-full bg-[#E5E5E5] h-2.5 rounded-full overflow-hidden p-0.5 border border-[#E2E8F0] relative">
        <motion.div
          className={`h-full rounded-full transition-all relative ${isDone
            ? 'bg-[#58CC02]'
            : isError
              ? 'bg-[#FF4B4B]'
              : 'bg-info'
            }`}
          style={{ width: `${smoothProgress}%`, transition: 'width 75ms ease-out' }}
        >
          {/* Shimmer sweep */}
          {!isDone && !isError && (
            <motion.div
              className="absolute inset-0 bg-gradient-to-r from-transparent via-white/50 to-transparent rounded-full"
              animate={{ x: ['-100%', '100%'] }}
              transition={{ repeat: Infinity, duration: 1.5, ease: 'easeInOut' }}
            />
          )}
        </motion.div>
      </div>

      {/* Done Stats Pill */}
      {
        isDone && status.stats && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-3 pt-2.5 border-t border-[#E2E8F0]/60 flex items-center justify-between text-xs font-bold text-[#58CC02]"
          >
            <div className="flex items-center gap-3 flex-wrap">
              <span>✨ {status.stats.chunks_indexed || 0} Chunks Indexed</span>
              <span>•</span>
              <span>🧠 {status.stats.entities_extracted || 0} Graph Entities</span>
              {status.stats.extracted_topics?.length > 0 && (
                <>
                  <span>•</span>
                  <span className="text-[#777777]">Topics: {status.stats.extracted_topics.slice(0, 3).join(', ')}</span>
                </>
              )}
            </div>
            <span className="text-[11px] font-extrabold uppercase bg-[#D7FFB8] px-2.5 py-0.5 rounded-full">
              Ready to study
            </span>
          </motion.div>
        )
      }

    </motion.div >
  )
}

// ─── Streaming Message Component (Isolated Subscription to prevent ChatPage re-render storm) ───
const StreamingMessageBubble = memo(function StreamingMessageBubble({ liveSources }: { liveSources: Source[] }) {
  const isStreaming = useChatStore((s) => s.isStreaming)
  const streamingContent = useChatStore((s) => s.streamingContent)

  if (!isStreaming) return null

  if (!streamingContent) {
    return (
      <div className="flex gap-3 sm:gap-4">
        <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-[1.5rem] bg-[#DDF4FF] text-[#1CB0F6] border border-[#1CB0F6]/30 flex items-center justify-center flex-shrink-0 elevation-2">
          <Sparkles size={16} />
        </div>
        <div className="bg-white border border-[#E2E8F0] rounded-[1.5rem] px-4 sm:px-5 py-3 sm:py-4 elevation-1">
          <div className="flex items-center gap-2">
            <span className="flex gap-1">
              <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
            </span>
            <span className="text-xs font-bold text-[#777777]">Searching GraphRAG knowledge base...</span>
          </div>
        </div>
      </div>
    )
  }

  return (
    <ChatMessage
      role="assistant"
      content={streamingContent}
      isStreaming={true}
      sources={liveSources}
    />
  )
})

// ─── Main Component ─────────────────────────────────────────────────────────────
export default function ChatPage() {
  const { sessionId } = useParams<{ sessionId?: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const { user, token, logout } = useAuthStore()

  // Selective Zustand subscriptions — does NOT subscribe to streamingContent directly!
  const sessions = useChatStore((s) => s.sessions)
  const activeSession = useChatStore((s) => s.activeSession)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const setSessions = useChatStore((s) => s.setSessions)
  const setActiveSession = useChatStore((s) => s.setActiveSession)
  const setMessages = useChatStore((s) => s.setMessages)
  const addMessage = useChatStore((s) => s.addMessage)
  const removeSession = useChatStore((s) => s.removeSession)
  const setStreaming = useChatStore((s) => s.setStreaming)
  const appendStreamToken = useChatStore((s) => s.appendStreamToken)
  const clearStreamingContent = useChatStore((s) => s.clearStreamingContent)

  const [input, setInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [uploadingFile, setUploadingFile] = useState(false)
  const [activeUploads, setActiveUploads] = useState<ActiveUpload[]>([])
  const [showGraphPanel, setShowGraphPanel] = useState(false)
  const [showQuizGame, setShowQuizGame] = useState(false)
  const [showFlashcards, setShowFlashcards] = useState(false)
  const [upgradeModalInfo, setUpgradeModalInfo] = useState<{ open: boolean; fileName?: string; sizeMb?: number }>({ open: false })
  const [confirmDeleteSessionId, setConfirmDeleteSessionId] = useState<string | null>(null)
  const [liveGraphContext, setLiveGraphContext] = useState<GraphContextData>({ entities: [], relationships: [] })

  const [liveSources, setLiveSources] = useState<Source[]>([])
  const [extMessages, setExtMessages] = useState<ExtendedMessage[]>([])
  const [selectedModel, setSelectedModel] = useState('Indie-Tutor (Llama 3.1)')

  // Mobile Drawers State
  const [mobileLeftOpen, setMobileLeftOpen] = useState(false)
  const [mobileRightOpen, setMobileRightOpen] = useState(false)

  // Voice Input State
  const [isListening, setIsListening] = useState(false)
  const recognitionRef = useRef<any>(null)

  const toggleVoiceInput = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRecognition) {
      alert('Voice input is not supported in this browser. Please use Chrome, Edge, or Brave.')
      return
    }

    if (isListening) {
      recognitionRef.current?.stop()
      setIsListening(false)
      return
    }

    try {
      const recognition = new SpeechRecognition()
      recognition.continuous = true
      recognition.interimResults = true
      recognition.lang = 'en-US'

      recognition.onstart = () => setIsListening(true)
      recognition.onresult = (event: any) => {
        let transcript = ''
        for (let i = event.resultIndex; i < event.results.length; i++) {
          transcript += event.results[i][0].transcript
        }
        if (transcript.trim()) {
          setInput((prev) => {
            const base = prev.trim()
            return base ? `${base} ${transcript}` : transcript
          })
        }
      }
      recognition.onerror = () => setIsListening(false)
      recognition.onend = () => setIsListening(false)

      recognitionRef.current = recognition
      recognition.start()
    } catch {
      setIsListening(false)
    }
  }

  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const skipNextFetchRef = useRef<string | null>(null)
  const messagesCacheRef = useRef<Map<string, ExtendedMessage[]>>(new Map())

  // Fetch knowledge graph for active session/topic
  const fetchKnowledgeGraph = useCallback(async () => {
    const topicId = activeSession?.topic_id || activeSession?.id || 'general'
    try {
      const res = await documentsApi.graph(topicId)
      const nodes = res.data?.graph?.nodes || []
      const edges = res.data?.graph?.edges || []
      if (nodes.length > 0 || edges.length > 0) {
        setLiveGraphContext({ entities: nodes, relationships: edges })
      }
    } catch (err) {
      console.error('Failed to load knowledge graph:', err)
    }
  }, [activeSession])

  useEffect(() => {
    if (showGraphPanel) {
      fetchKnowledgeGraph()
    }
  }, [showGraphPanel, fetchKnowledgeGraph])

  // Fetch sessions (cached for 30s for fast sidebar navigation)
  const { refetch: refetchSessions } = useQuery({
    queryKey: ['chat-sessions'],
    queryFn: async () => {
      const res = await chatApi.sessions()
      setSessions(res.data)
      if (sessionId) {
        const found = res.data.find((s: any) => s.id === sessionId)
        if (found) setActiveSession(found)
      }
      return res.data
    },
    staleTime: 30000,
  })

  const handleSend = useCallback(async (text?: string) => {
    let content = (text ?? input).trim()
    if (!content || isStreaming) return

    let currentSessionId: string = sessionId || activeSession?.id || ''
    if (!currentSessionId) {
      try {
        const res = await chatApi.createSession('', content.slice(0, 30) || 'New Chat')
        currentSessionId = res.data.id
        skipNextFetchRef.current = currentSessionId
        setActiveSession(res.data)
        refetchSessions()
        navigate(`/chat/${res.data.id}`)
      } catch (err) {
        console.error('Auto session creation failed', err)
        return
      }
    }

    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'

    const userMsg: ExtendedMessage = {
      id: Date.now().toString(),
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    }
    setExtMessages((prev) => [...prev, userMsg])
    addMessage(userMsg)

    setStreaming(true)
    clearStreamingContent()
    setLiveSources([])
    setLiveGraphContext({ entities: [], relationships: [] })

    if (abortControllerRef.current) abortControllerRef.current.abort()
    const controller = new AbortController()
    abortControllerRef.current = controller

    let accContent = ''
    let accSources: Source[] = []
    let accGraph: GraphContextData = { entities: [], relationships: [] }
    let accGrounding: any = null

    await streamChatMessage({
      sessionId: currentSessionId,
      content,
      token: token || '',
      signal: controller.signal,
      onToken: (t) => {
        accContent += t
        appendStreamToken(t)
      },
      onSources: (s) => {
        accSources = s
        setLiveSources(s)
      },
      onGraphContext: (g) => {
        accGraph = g
        setLiveGraphContext(g)
      },
      onGrounding: (gr) => {
        accGrounding = gr
      },
      onDone: () => {
        const assistantMsg: ExtendedMessage = {
          id: Date.now().toString() + '_ai',
          role: 'assistant',
          content: accContent,
          created_at: new Date().toISOString(),
          sources: accSources,
          graph_context: accGraph,
          grounding: accGrounding,
        }
        setExtMessages((prev) => [...prev, assistantMsg])
        clearStreamingContent()
        setStreaming(false)
      },
      onError: (err) => {
        console.error('Stream error:', err)
        const fallbackMsg = `⚠️ **Something went wrong.**\n\nYour tutor couldn't respond this time. Try again in a moment. (${err?.message || 'Server error'})`
        const fallback: ExtendedMessage = {
          id: Date.now().toString() + '_fallback',
          role: 'assistant',
          content: accContent || fallbackMsg,
          created_at: new Date().toISOString(),
        }
        setExtMessages((prev) => [...prev, fallback])
        clearStreamingContent()
        setStreaming(false)
      },
    })
  }, [sessionId, input, isStreaming, activeSession, token, navigate, refetchSessions, setActiveSession, addMessage, appendStreamToken, clearStreamingContent, setStreaming])

  // Load session messages when sessionId changes
  useEffect(() => {
    if (!sessionId) {
      setActiveSession(null)
      setExtMessages([])
      setMessages([])
      return
    }

    if (skipNextFetchRef.current === sessionId) {
      skipNextFetchRef.current = null
      return
    }

    const found = sessions.find((s) => s.id === sessionId)
    if (found) {
      setActiveSession(found)
    }

    // 0ms instant display from local memory cache
    const cached = messagesCacheRef.current.get(sessionId)
    if (cached && cached.length > 0) {
      setExtMessages(cached)
    }

    chatApi
      .messages(sessionId)
      .then((res) => {
        if (!found) {
          setActiveSession({
            id: sessionId,
            user_id: user?.id || '',
            topic_id: '',
            session_title: 'Chat Session',
            started_at: new Date().toISOString(),
          })
        }
        const msgs: ExtendedMessage[] = res.data.map((m: any) => ({
          ...m,
          sources: m.metadata?.sources ?? [],
          graph_context: m.metadata?.graph_context ?? null,
        }))
        messagesCacheRef.current.set(sessionId, msgs)
        setExtMessages(msgs)
        setMessages(res.data)
      })
      .catch((err) => {
        console.error('Failed to load session messages:', err)
        if (err.response?.status === 404 || err.response?.status === 401) {
          // Stale or deleted session ID — cleanly reset and navigate to clean chat
          setActiveSession(null)
          setExtMessages([])
          setMessages([])
          navigate('/chat', { replace: true })
        }
      })
  }, [sessionId, sessions, user?.id, navigate, setActiveSession, setMessages])

  // Automatically submit initial prompt if navigated from Dashboard Quick Ask
  useEffect(() => {
    const initialPrompt = (location.state as any)?.initialPrompt
    if (initialPrompt && typeof initialPrompt === 'string') {
      handleSend(initialPrompt)
      navigate(location.pathname, { replace: true, state: {} })
    }
  }, [location.state, handleSend, location.pathname, navigate])

  // Group sessions by date (Only show custom document learning sessions)
  const groupedSessions = useMemo(() => {
    const filtered = sessions.filter((s) => {
      const isSubjectSession = s.topic_id?.startsWith('sslc-') ||
        s.topic_id?.startsWith('math-') ||
        s.topic_id?.startsWith('phys-') ||
        s.topic_id?.startsWith('chem-')
      if (isSubjectSession) return false
      return s.session_title.toLowerCase().includes(searchQuery.toLowerCase())
    })

    const now = new Date()
    const today: any[] = []
    const yesterday: any[] = []
    const lastWeek: any[] = []
    const older: any[] = []

    filtered.forEach((s) => {
      const date = s.started_at ? new Date(s.started_at) : new Date()
      const diffTime = Math.abs(now.getTime() - date.getTime())
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24))

      if (diffDays <= 1) today.push(s)
      else if (diffDays === 2) yesterday.push(s)
      else if (diffDays <= 7) lastWeek.push(s)
      else older.push(s)
    })

    return { today, yesterday, lastWeek, older }
  }, [sessions, searchQuery])

  // 60FPS throttled auto-scroll without layout thrashing
  useEffect(() => {
    const el = bottomRef.current
    if (!el) return
    const raf = requestAnimationFrame(() => {
      el.scrollIntoView({ behavior: isStreaming ? 'auto' : 'smooth', block: 'end' })
    })
    return () => cancelAnimationFrame(raf)
  }, [extMessages, isStreaming])

  const handleDeleteSession = (e?: React.MouseEvent, sId?: string) => {
    if (e) e.stopPropagation()
    const targetId = sId || activeSession?.id
    if (!targetId) return
    setConfirmDeleteSessionId(targetId)
  }

  const executeDeleteSession = async () => {
    const targetId = confirmDeleteSessionId
    if (!targetId) return
    setConfirmDeleteSessionId(null)
    try {
      await chatApi.deleteSession(targetId)
      removeSession(targetId)
      messagesCacheRef.current.delete(targetId)
      if (activeSession?.id === targetId) {
        setActiveSession(null)
        setExtMessages([])
        setMessages([])
        const remaining = sessions.filter((s) => s.id !== targetId)
        if (remaining.length > 0) {
          navigate(`/chat/${remaining[0].id}`)
        } else {
          navigate('/chat')
        }
      }
      refetchSessions()
    } catch (err) {
      console.error('Failed to delete session:', err)
    }
  }


  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = `${Math.min(e.target.scrollHeight, 180)}px`
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleUploadDone = useCallback((docId: string, stats: any) => {
    setActiveUploads((prev) => {
      const upload = prev.find((u) => u.docId === docId)
      const fileName = upload?.fileName || 'Document'

      const successMsg: ExtendedMessage = {
        id: Date.now().toString(),
        role: 'assistant',
        content: `📄 **${fileName}** is fully processed and indexed!\n\n${stats?.chunks_indexed
          ? `📊 **Knowledge Breakdown:**\n- **Chunks Indexed:** ${stats.chunks_indexed}\n- **Graph Entities:** ${stats.entities_extracted || 0}\n`
          : ''
          }${stats?.extracted_topics?.length ? `- **Key Topics:** ${stats.extracted_topics.slice(0, 5).join(', ')}\n` : ''}\n💡 *You can now ask questions, generate practice quizzes, or study flashcards for this material.*`,
        created_at: new Date().toISOString(),
      }
      setExtMessages((existing) => [...existing, successMsg])
      return prev
    })
  }, [])

  const handleUploadError = useCallback((docId: string, error: string) => {
    setActiveUploads((prev) => {
      const upload = prev.find((u) => u.docId === docId)
      const fileName = upload?.fileName || 'Document'
      const errorMsg: ExtendedMessage = {
        id: Date.now().toString(),
        role: 'assistant',
        content: `❌ **Failed to process ${fileName}**: ${error}`,
        created_at: new Date().toISOString(),
      }
      setExtMessages((existing) => [...existing, errorMsg])
      return prev
    })
  }, [])

  const handleDismissUpload = useCallback((docId: string) => {
    setActiveUploads((prev) => prev.filter((u) => u.docId !== docId))
  }, [])

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    const fileSizeMb = file.size / (1024 * 1024)
    setUploadingFile(true)

    try {
      let targetSessionId: string = sessionId || activeSession?.id || ''
      if (!targetSessionId) {
        const newSess = await chatApi.createSession('', file.name.slice(0, 30))
        targetSessionId = newSess.data.id
        skipNextFetchRef.current = targetSessionId
        setActiveSession(newSess.data)
        refetchSessions()
        navigate(`/chat/${newSess.data.id}`)
      }

      const topicId = targetSessionId || 'general'
      const res = await documentsApi.upload(topicId, file, topicId)
      const data = res.data

      // Track aesthetic live progress card — do NOT post success message until indexing is done!
      setActiveUploads((prev) => [
        ...prev.filter((u) => u.docId !== data.id),
        { docId: data.id, fileName: file.name, sizeMb: fileSizeMb },
      ])
    } catch (err: any) {
      if (err.response?.status === 401) {
        logout()
        navigate('/login')
        return
      }
      const data = err.response?.data
      const detailMsg = typeof data?.detail === 'object' ? data?.detail?.message : data?.detail
      if (data?.detail?.requires_premium) {
        setUpgradeModalInfo({ open: true, fileName: file.name, sizeMb: fileSizeMb })
      }
      const errMsg: ExtendedMessage = {
        id: Date.now().toString(),
        role: 'assistant',
        content: `❌ Upload failed: ${detailMsg || err.message || 'Unknown error'}`,
        created_at: new Date().toISOString(),
      }
      setExtMessages((prev) => [...prev, errMsg])
    } finally {
      setUploadingFile(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const allMessages = extMessages

  return (
    <div className="flex flex-col md:flex-row h-screen w-full bg-white overflow-hidden text-[#20201D] font-sans">

      {/* ─── MOBILE BACKDROP OVERLAYS ────────────────────────────────────────── */}
      <AnimatePresence>
        {(mobileLeftOpen || mobileRightOpen) && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => { setMobileLeftOpen(false); setMobileRightOpen(false); }}
            className="fixed inset-0 bg-[#3C3C3C]/40 backdrop-blur-sm z-40 md:hidden"
          />
        )}
      </AnimatePresence>

      {/* ─── MOBILE LEFT DRAWER (CHAT HISTORY) ─── */}
      <aside
        className={`fixed xl:static inset-y-0 left-0 z-40 w-72 bg-white border-r border-border p-4 flex flex-col justify-between shadow-2xl xl:shadow-none transition-transform duration-300 ${mobileLeftOpen ? 'translate-x-0' : '-translate-x-full xl:translate-x-0'
          }`}
      >
        <div className="space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-[#E2E8F0]">
            <div className="flex items-center gap-2">
              <MessageSquare size={18} className="text-[#1CB0F6]" />
              <h3 className="text-xs font-extrabold uppercase text-[#777777] tracking-wider">
                Chat History
              </h3>
            </div>
            <button
              onClick={() => setMobileLeftOpen(false)}
              className="xl:hidden text-[#AFAFAF] hover:text-[#3C3C3C] p-1.5 rounded-[1.25rem] hover:bg-[#E5E5E5]"
            >
              <X size={18} />
            </button>
          </div>

          <button
            onClick={() => {
              setActiveSession(null)
              navigate('/chat')
              setMobileLeftOpen(false)
            }}
            className="w-full btn-primary font-bold text-xs py-2.5 px-3 rounded-[1.25rem] flex items-center justify-center gap-2 elevation-1 cursor-pointer"
          >
            <Plus size={15} />
            <span>New Chat</span>
          </button>

          <div className="space-y-1.5 max-h-[65vh] overflow-y-auto">
            {sessions.map((s) => {
              const isSelected = activeSession?.id === s.id
              return (
                <div
                  key={s.id}
                  onClick={() => {
                    navigate(`/chat/${s.id}`)
                    setMobileLeftOpen(false)
                  }}
                  className={`group flex items-center justify-between px-3 py-2.5 rounded-[1.25rem] text-xs cursor-pointer transition-all ${isSelected
                    ? 'bg-white text-[#20201D] font-extrabold border border-border shadow-sm'
                    : 'text-[#6F6B63] hover:text-[#20201D] hover:bg-white/50 font-medium border border-transparent'
                    }`}
                >
                  <span className="truncate pr-2">{s.session_title || 'Untitled Chat'}</span>
                  <button
                    onClick={(e) => handleDeleteSession(e, s.id)}
                    className="text-[#AFAFAF] hover:text-[#FF4B4B] hover:bg-[#FFD1D1] p-1.5 rounded-lg transition-colors"
                    title="Delete session"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      </aside>

      {/* ─── MAIN CHAT WORKSPACE AREA ───────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col bg-white overflow-hidden relative">

        {/* Hidden File Input */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.webp,.bmp,.docx,.doc,.csv,.xlsx,.xls,.pptx,.ppt,.html,.json,.txt,.md"
          className="hidden"
          onChange={handleFileUpload}
        />

        {/* Top Header Bar */}
        <header className="h-16 border-b border-border flex items-center justify-between px-4 sm:px-6 flex-shrink-0 bg-white/80 backdrop-blur-md">

          <div className="flex items-center gap-3">
            {/* Mobile Left Drawer Trigger */}
            <button
              onClick={() => setMobileLeftOpen(true)}
              className="xl:hidden p-2 text-[#3C3C3C] hover:bg-[#E5E5E5] rounded-[1.25rem] transition-colors"
              title="Open Chat History"
            >
              <Menu size={20} />
            </button>

            {/* Model Switcher Pill */}
            <div className="flex items-center gap-2 px-3 py-1.5 sm:px-3.5 sm:py-2 rounded-[1.5rem] border border-border bg-white hover:bg-gray-50 hover:border-[#20201D]/40 cursor-pointer transition-all shadow-sm">
              <div className="w-5 h-5 sm:w-6 sm:h-6 rounded-[1.25rem] bg-info-soft text-info flex items-center justify-center border border-info/20">
                <Sparkles size={13} />
              </div>
              <span className="text-xs font-black text-[#3C3C3C] truncate max-w-[140px] sm:max-w-none">{selectedModel}</span>
              <ChevronDown size={14} className="text-[#AFAFAF] flex-shrink-0" />
            </div>
          </div>

          <div className="flex items-center gap-2">
            {activeSession && (
              <button
                onClick={(e) => handleDeleteSession(e, activeSession.id)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-[1.25rem] bg-white hover:bg-[#FFD1D1] border border-[#E2E8F0] hover:border-[#FF4B4B]/40 text-[#777777] hover:text-[#FF4B4B] text-xs font-bold transition-all elevation-1 cursor-pointer active:scale-95"
                title="Delete this chat session & database records"
              >
                <Trash2 size={13} className="text-[#FF4B4B]" />
                <span className="hidden sm:inline">Delete Section</span>
              </button>
            )}

            {/* Mobile Right Drawer Trigger */}
            <button
              onClick={() => setMobileRightOpen(true)}
              className="lg:hidden flex items-center gap-1.5 px-3 py-1.5 rounded-[1.25rem] bg-[#DDF4FF] border border-[#1CB0F6]/30 text-[#1CB0F6] text-xs font-extrabold hover:bg-[#1899D6] hover:text-white transition-colors"
              title="Study Tools & Graph"
            >
              <Zap size={14} />
              <span>Tools</span>
            </button>
          </div>
        </header>

        {/* Aesthetic Document Processing Banner */}
        {activeUploads.length > 0 && (
          <div className="px-4 sm:px-6 py-3 border-b border-[#E2E8F0] bg-[#F7F7F7]/90 backdrop-blur-sm space-y-3">
            <AnimatePresence>
              {activeUploads.map((upload) => (
                <UploadStatusCard
                  key={upload.docId}
                  upload={upload}
                  onDone={handleUploadDone}
                  onError={handleUploadError}
                  onDismiss={handleDismissUpload}
                />
              ))}
            </AnimatePresence>
          </div>
        )}

        {/* Workspace Content Area */}
        <div className="flex-1 overflow-y-auto flex flex-col">

          {/* HERO STATE */}
          {allMessages.length === 0 && (
            <div className="flex-1 flex flex-col items-center justify-center px-4 sm:px-6 py-8 sm:py-10 max-w-3xl mx-auto w-full text-center">

              {/* AI Tutor Avatar Graphic */}
              <div className="relative w-36 h-36 sm:w-48 sm:h-48 mb-6 mx-auto pointer-events-none">
                <div className="absolute inset-0 bg-info/20 rounded-full blur-2xl scale-110 opacity-50"></div>
                <img src="/assets/illustrations/ai_tutor.jpg" alt="AI Tutor" className="w-full h-full object-contain mix-blend-multiply relative z-10" />
              </div>

              {/* Personal Greeting & Headline */}
              <p className="text-info font-extrabold text-xs sm:text-sm mb-2 tracking-widest uppercase">
                Welcome back, {user?.username ?? 'Learner'}!
              </p>
              <h1 className="text-3xl sm:text-5xl font-black text-text-primary tracking-tight mb-8 leading-tight">
                What are we<br />learning today?
              </h1>

              {/* Clean Multi-Tool Input Container */}
              <div className="w-full bg-white border border-border rounded-[2rem] p-3.5 sm:p-5 shadow-sm focus-within:border-info focus-within:ring-2 focus-within:ring-info/20 transition-all text-left">

                {/* 3 Quick Study Tool Action Buttons */}
                <div className="flex flex-wrap items-center gap-2 mb-3 pb-3 border-b border-[#E2E8F0]">
                  <span className="text-[11px] font-black uppercase text-[#777777] tracking-wider mr-1 flex items-center gap-1">
                    <Sparkles size={13} className="text-[#1CB0F6]" /> Tools:
                  </span>

                  <button
                    type="button"
                    onClick={() => {
                      const topic = input.trim() || 'this topic'
                      handleSend(`Give me 5 minute cheatcode for ${topic}`)
                    }}
                    disabled={isStreaming}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#FFF0E4] hover:bg-[#F28A45] border border-[#F28A45]/30 hover:border-[#F28A45] text-[#F28A45] hover:text-white text-xs font-black transition-all shadow-2xs cursor-pointer active:scale-95 disabled:opacity-40"
                    title="Generate 5-minute structured revision cheat sheet"
                  >
                    <Zap size={13} />
                    <span>⚡ 5-Min Cheatcode</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      const topic = input.trim() || 'the main topic in my study material'
                      handleSend(`Summarize ${topic} into 5-7 clear, high-yield bullet points for quick revision.`)
                    }}
                    disabled={isStreaming}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#F7F7F7] hover:bg-[#DDF4FF] border border-[#E2E8F0] hover:border-[#1CB0F6]/40 text-[#3C3C3C] hover:text-[#1CB0F6] text-xs font-bold transition-all elevation-1 cursor-pointer active:scale-95 disabled:opacity-40"
                    title="Generate 5-7 key bullet points"
                  >
                    <ListChecks size={13} className="text-[#1CB0F6]" />
                    <span>Bullet Points</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      const topic = input.trim() || 'this subject'
                      handleSend(`What are the most important exam-critical points, core formulas, and common misconceptions about ${topic}?`)
                    }}
                    disabled={isStreaming}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#F7F7F7] hover:bg-[#FFF0B3] border border-[#E2E8F0] hover:border-[#FFC800]/40 text-[#3C3C3C] hover:text-[#FFC800] text-xs font-bold transition-all elevation-1 cursor-pointer active:scale-95 disabled:opacity-40"
                    title="Highlight key exam-critical formulas & concepts"
                  >
                    <Star size={13} className="text-[#FFC800]" />
                    <span>Important Points</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      const topic = input.trim() || 'the central concept'
                      handleSend(`Explain ${topic} using a simple, intuitive real-world analogy and visual mental model.`)
                    }}
                    disabled={isStreaming}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#F7F7F7] hover:bg-[#D7FFB8] border border-[#E2E8F0] hover:border-[#58CC02]/40 text-[#3C3C3C] hover:text-[#58CC02] text-xs font-bold transition-all elevation-1 cursor-pointer active:scale-95 disabled:opacity-40"
                    title="Explain with a simple real-world analogy"
                  >
                    <Lightbulb size={13} className="text-[#58CC02]" />
                    <span>Simple Analogy</span>
                  </button>
                </div>

                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    selectedModel.includes('Vision')
                      ? 'Ask a question or describe an image/diagram...'
                      : 'Ask anything about your study material, or click ⚡ 5-Min Cheatcode...'
                  }
                  rows={2}
                  className="w-full bg-transparent resize-none outline-none text-[#20201D] font-medium text-sm sm:text-base placeholder-[#969188] leading-relaxed px-1"
                />

                {/* Sub Action Toolbar */}
                <div className="flex items-center justify-between gap-2 mt-3 sm:mt-4 pt-3 border-t border-[#E2E8F0]">
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploadingFile}
                    className="flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-1.5 sm:py-2 rounded-[1.25rem] bg-[#F7F7F7] hover:bg-[#DDF4FF] border border-[#E2E8F0] hover:border-[#1CB0F6]/30 text-[#3C3C3C] text-xs font-bold transition-all elevation-1 disabled:opacity-40 cursor-pointer"
                  >
                    {uploadingFile ? <Loader2 size={14} className="animate-spin text-[#1CB0F6]" /> : <Paperclip size={14} className="text-[#1CB0F6]" />}
                    <span>{uploadingFile ? 'Uploading...' : 'Attach PDF'}</span>
                  </button>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={toggleVoiceInput}
                      className={`p-2.5 sm:p-3 rounded-full text-white transition-all elevation-2 cursor-pointer ${isListening
                        ? 'bg-[#FF4B4B] animate-bounce ring-4 ring-[#FFD1D1]'
                        : 'bg-[#1CB0F6] hover:bg-[#1899D6]'
                        }`}
                      title={isListening ? 'Stop Recording' : 'Voice Input'}
                    >
                      {isListening ? <MicOff size={16} /> : <Mic size={16} />}
                    </button>

                    <button
                      onClick={() => handleSend()}
                      disabled={!input.trim()}
                      className="p-2.5 sm:p-3 rounded-full bg-[#1CB0F6] hover:bg-[#1899D6] text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all elevation-2 cursor-pointer"
                    >
                      <Send size={15} />
                    </button>
                  </div>
                </div>

              </div>

              {/* Starter Action Cards */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 sm:gap-4 w-full mt-6 sm:mt-8">

                <SuggestionCard
                  icon={<div className="w-10 h-10 rounded-2xl bg-[#FFF0E4] text-[#F28A45] flex items-center justify-center border border-[#F28A45]/20"><Zap className="w-5 h-5" /></div>}
                  title="5-Min Cheatcode"
                  description="Get a structured 6-section 5-minute revision cheat sheet with analogies, tables & visual flowchart."
                  onClick={() => handleSend("Give me 5 minute cheatcode for this topic.")}
                />

                <SuggestionCard
                  icon={<div className="w-10 h-10 rounded-2xl bg-[#FFF0E4] text-[#F28A45] flex items-center justify-center border border-[#F28A45]/20"><Clock className="w-5 h-5" /></div>}
                  title="Synthesize Notes"
                  description="Turn my uploaded PDF notes into 5 key bullet points for quick review."
                  onClick={() => handleSend("Turn my uploaded PDF notes into 5 key bullet points for quick review.")}
                />

                <SuggestionCard
                  icon={<div className="w-10 h-10 rounded-[1.5rem] bg-[#FFF0B3] text-[#FFC800] flex items-center justify-center border border-[#FFC800]/20"><Trophy className="w-5 h-5" /></div>}
                  title="Practice Quiz"
                  description="Generate a 5-question multiple choice practice quiz from my material."
                  onClick={() => handleSend("Generate a 5-question multiple choice practice quiz from my material.")}
                />

                <SuggestionCard
                  icon={<div className="w-10 h-10 rounded-[1.5rem] bg-[#D7FFB8] text-[#58CC02] flex items-center justify-center border border-[#58CC02]/20"><Brain className="w-5 h-5" /></div>}
                  title="Concept Explanation"
                  description="Explain complex topics step-by-step with clear real-world examples."
                  onClick={() => handleSend("Explain quantum mechanics step-by-step with clear real-world examples.")}
                />

              </div>

            </div>
          )}

          {/* ACTIVE CHAT THREAD */}
          {(extMessages.length > 0 || isStreaming) && (
            <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4 sm:space-y-6 max-w-4xl mx-auto w-full">
              {extMessages.map((msg) => (
                <ChatMessage
                  key={msg.id}
                  role={msg.role}
                  content={msg.content}
                  sources={msg.sources}
                  grounding={msg.grounding}
                />
              ))}

              <StreamingMessageBubble liveSources={liveSources} />

              <div ref={bottomRef} />
            </div>
          )}

        </div>

        {/* Input Bar (Sticky at bottom when chat messages exist) */}
        {allMessages.length > 0 && (
          <div className="p-3 sm:p-4 border-t border-border bg-white">
            <div className="max-w-4xl mx-auto bg-white border border-border rounded-[1.5rem] p-3 sm:p-3.5 focus-within:border-info focus-within:ring-2 focus-within:ring-info/20 transition-all shadow-sm">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                rows={1}
                className="w-full bg-transparent resize-none outline-none text-[#3C3C3C] font-medium text-sm sm:text-base placeholder-[#AFAFAF]"
                placeholder="Ask follow-up question..."
                style={{ minHeight: '28px', maxHeight: '160px' }}
              />
              <div className="flex items-center justify-between mt-2.5 pt-2 border-t border-[#E2E8F0]">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="flex items-center gap-1.5 text-xs font-bold text-[#3C3C3C] bg-white hover:bg-[#DDF4FF] px-2.5 py-1.5 rounded-[1.25rem] border border-[#E2E8F0] hover:border-[#1CB0F6]/30 elevation-1 transition-colors cursor-pointer"
                  >
                    <Paperclip size={13} className="text-[#1CB0F6]" />
                    <span>Attach PDF</span>
                  </button>
                  <button
                    onClick={toggleVoiceInput}
                    className={`p-2 rounded-[1.25rem] transition-colors cursor-pointer ${isListening ? 'text-[#FF4B4B] bg-[#FFD1D1] animate-pulse' : 'text-[#777777] hover:text-[#3C3C3C] hover:bg-[#E5E5E5]'
                      }`}
                    title="Voice input"
                  >
                    <Mic size={16} />
                  </button>
                </div>
                <button
                  onClick={() => handleSend()}
                  disabled={!input.trim() || isStreaming}
                  className="p-2.5 rounded-[1.25rem] bg-[#1CB0F6] hover:bg-[#1899D6] text-white disabled:opacity-30 transition-all elevation-2 cursor-pointer"
                >
                  <Send size={15} />
                </button>
              </div>
            </div>
          </div>
        )}

      </main>

      {/* ─── RIGHT SIDEBAR ────────────────────────────────────────────────── */}
      <aside
        className={`fixed lg:static inset-y-0 right-0 z-50 w-80 bg-[#F7F7F7] border-l border-[#E2E8F0] p-5 flex flex-col justify-between overflow-y-auto shadow-2xl lg:shadow-none transition-transform duration-300 ${mobileRightOpen ? 'translate-x-0' : 'translate-x-full lg:translate-x-0'
          }`}
      >
        <div className="space-y-4">
          <div className="flex items-center justify-between mb-4 pb-3 border-b border-[#E2E8F0]">
            <div className="flex items-center gap-2.5">
              <Sparkles size={18} className="text-[#1CB0F6]" />
              <h3 className="text-xs font-extrabold uppercase text-[#777777] tracking-wider">
                Study Tools & Graph
              </h3>
            </div>
            <button
              onClick={() => setMobileRightOpen(false)}
              className="lg:hidden text-[#AFAFAF] hover:text-[#3C3C3C] p-1.5 rounded-[1.25rem] hover:bg-[#E5E5E5]"
            >
              <X size={18} />
            </button>
          </div>

          {/* Study Tools Graphic */}
          <div className="w-full h-32 bg-white rounded-2xl mb-4 overflow-hidden border border-[#E2E8F0] shadow-sm flex items-center justify-center">
            <img src="/assets/illustrations/study_tools.jpg" alt="Study Tools" className="w-full h-full object-cover mix-blend-multiply" />
          </div>

          {/* 1. Flashcards Card */}
          <motion.div
            whileHover={{ scale: 1.02 }}
            onClick={() => { setShowFlashcards(true); setMobileRightOpen(false); }}
            className="p-5 rounded-2xl bg-surface border border-border hover:border-info shadow-sm hover:shadow-md transition-all cursor-pointer group relative overflow-hidden"
          >
            <div className="w-12 h-12 rounded-xl bg-info-soft border border-info/30 flex items-center justify-center mb-3 shadow-sm p-2 group-hover:scale-105 transition-transform">
              <img src="/assets/uimojis/uimoji_flashcards.jpg" alt="Flashcards" className="w-full h-full object-cover mix-blend-multiply rounded-lg" />
            </div>
            <h4 className="text-md font-bold text-text-primary group-hover:text-info transition-colors">
              Flashcards Deck
            </h4>
            <p className="text-sm text-text-secondary mt-2 leading-relaxed">
              Review AI study cards generated strictly from your uploaded PDF text.
            </p>
            <div className="mt-4 flex items-center gap-1.5 text-sm font-bold text-info group-hover:translate-x-1 transition-transform">
              <span>Study Flashcards</span> <ArrowRight size={16} />
            </div>
          </motion.div>

          {/* 2. Play Quiz Card */}
          <motion.div
            whileHover={{ scale: 1.02 }}
            onClick={() => { setShowQuizGame(true); setMobileRightOpen(false); }}
            className="p-5 rounded-2xl bg-surface border border-border hover:border-info shadow-sm hover:shadow-md transition-all cursor-pointer group relative overflow-hidden"
          >
            <div className="w-12 h-12 rounded-xl bg-info-soft border border-info/30 flex items-center justify-center mb-3 shadow-sm p-2 group-hover:scale-105 transition-transform">
              <img src="/assets/uimojis/uimoji_quiz.jpg" alt="Quiz" className="w-full h-full object-cover mix-blend-multiply rounded-lg" />
            </div>
            <h4 className="text-md font-bold text-text-primary group-hover:text-info transition-colors">
              Play Gamified Quiz
            </h4>
            <p className="text-sm text-text-secondary mt-2 leading-relaxed">
              Test your understanding with PDF-based quizzes, score XP & master topics.
            </p>
            <div className="mt-4 flex items-center gap-1.5 text-sm font-bold text-info group-hover:translate-x-1 transition-transform">
              <span>Start Quiz Game</span> <ArrowRight size={16} />
            </div>
          </motion.div>

          {/* 3. Knowledge Graph Card */}
          <motion.div
            whileHover={{ scale: 1.02 }}
            onClick={() => { setShowGraphPanel(true); setMobileRightOpen(false); }}
            className="p-5 rounded-2xl bg-surface border border-border hover:border-success shadow-sm hover:shadow-md transition-all cursor-pointer group relative overflow-hidden"
          >
            <div className="w-12 h-12 rounded-xl bg-success-soft border border-success/30 flex items-center justify-center mb-3 shadow-sm p-2 group-hover:scale-105 transition-transform">
              <img src="/assets/uimojis/uimoji_graph.jpg" alt="Knowledge Graph" className="w-full h-full object-cover mix-blend-multiply rounded-lg" />
            </div>
            <div className="flex items-center justify-between">
              <h4 className="text-md font-bold text-text-primary group-hover:text-success transition-colors">
                Knowledge Graph
              </h4>
              {liveGraphContext.entities.length > 0 && (
                <span className="text-xs font-bold bg-success-soft text-success px-2 py-0.5 rounded-full border border-success/30">
                  {liveGraphContext.entities.length} Nodes
                </span>
              )}
            </div>
            <p className="text-sm text-text-secondary mt-2 leading-relaxed">
              Explore 3D visual entity maps and document relationship connections.
            </p>
            <div className="mt-4 flex items-center gap-1.5 text-sm font-bold text-success group-hover:translate-x-1 transition-transform">
              <span>Explore 3D Graph</span> <ArrowRight size={16} />
            </div>
          </motion.div>
        </div>

        <div className="pt-4 border-t border-border text-center">
          <p className="text-xs font-semibold text-text-muted">
            🧠 GraphRAG + Ollama AI Tutor Engine
          </p>
        </div>
      </aside>

      {/* ─── MODALS & OVERLAYS ──────────────────────────────────────────────────── */}
      <GraphContextPanel
        entities={liveGraphContext.entities}
        relationships={liveGraphContext.relationships}
        isOpen={showGraphPanel}
        onClose={() => setShowGraphPanel(false)}
        onAskTutor={(concept) => {
          setInput(`Explain the core concept "${concept}" in detail with key formulas, intuitive examples, and exam applications.`)
          if (textareaRef.current) {
            textareaRef.current.focus()
          }
        }}
      />

      <GamifiedQuizGame
        sessionId={activeSession?.id}
        isOpen={showQuizGame}
        onClose={() => setShowQuizGame(false)}
      />
      <FlashcardsOverlay
        sessionId={activeSession?.id}
        isOpen={showFlashcards}
        onClose={() => setShowFlashcards(false)}
      />

      <UpgradeModal
        isOpen={upgradeModalInfo.open}
        exceededFileName={upgradeModalInfo.fileName}
        exceededFileSizeMb={upgradeModalInfo.sizeMb}
        onClose={() => setUpgradeModalInfo({ open: false })}
      />

      <ConfirmModal
        isOpen={Boolean(confirmDeleteSessionId)}
        title="Delete Chat Session?"
        message="Are you sure you want to delete this chat session? All messages, uploaded documents, and study materials for this session will be permanently removed."
        confirmText="Delete Session"
        cancelText="Cancel"
        variant="danger"
        onConfirm={executeDeleteSession}
        onCancel={() => setConfirmDeleteSessionId(null)}
      />
    </div>
  )
}


// ─── Sub-components ────────────────────────────────────────────────────────────

function SessionItem({ session, activeId, onSelect, onDelete }: {
  session: any;
  activeId?: string;
  onSelect: () => void;
  onDelete: (e: React.MouseEvent) => void;
}) {
  const isActive = activeId === session.id

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect()
        }
      }}
      className={`group w-full flex items-center justify-between px-3 py-2.5 rounded-[1.25rem] transition-all cursor-pointer ${isActive
        ? 'bg-[#DDF4FF] text-[#1CB0F6] font-extrabold elevation-1 border border-[#1CB0F6]/30'
        : 'text-[#777777] hover:bg-[#E5E5E5] hover:text-[#3C3C3C] font-medium'
        }`}
    >
      <div className="flex items-center gap-2.5 min-w-0 pr-1">
        <MessageSquare size={15} className={isActive ? 'text-[#1CB0F6]' : 'text-[#AFAFAF]'} />
        <span className="truncate text-xs">{session.session_title}</span>
      </div>
      <button
        aria-label="Delete session"
        onClick={onDelete}
        className={`opacity-0 group-hover:opacity-100 p-1 rounded-lg transition-all ${isActive ? 'text-[#1CB0F6] hover:text-[#FF4B4B] hover:bg-[#DDF4FF]' : 'text-[#AFAFAF] hover:text-[#FF4B4B] hover:bg-[#FFD1D1]'
          }`}
        title="Delete session"
      >
        <Trash2 size={14} />
      </button>
    </div>
  )
}

function SuggestionCard({ icon, title, description, onClick }: {
  icon: React.ReactNode;
  title: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick()
        }
      }}
      className="p-4 sm:p-5 rounded-[2rem] bg-white border border-border hover:border-info/30 hover:bg-info-soft transition-all cursor-pointer text-left group shadow-sm hover:shadow-md hover:-translate-y-0.5 active:scale-[0.98]"
    >
      <div className="mb-2 sm:mb-3">{icon}</div>
      <h3 className="font-extrabold text-sm sm:text-base text-[#20201D] group-hover:text-info mb-1 transition-colors">{title}</h3>
      <p className="text-xs text-[#6F6B63] leading-relaxed font-medium">{description}</p>
    </div>
  )
}

