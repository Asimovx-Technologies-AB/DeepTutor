import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
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

// ─── Upload Status Badge ────────────────────────────────────────────────────────
function UploadStatus({ docId, onDone }: { docId: string; onDone: (stats: any) => void }) {
  const [status, setStatus] = useState<any>({ status: 'indexing', progress: 0 })

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/documents/${docId}/status`, {
          headers: { Authorization: `Bearer ${useAuthStore.getState().token}` },
        })
        const data = await res.json()
        setStatus(data)
        if (data.status === 'done' || data.status === 'error') {
          clearInterval(interval)
          if (data.status === 'done') onDone(data.stats)
        }
      } catch { clearInterval(interval) }
    }, 2000)
    return () => clearInterval(interval)
  }, [docId])

  const isDone = status.status === 'done'
  const isError = status.status === 'error'

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className={`flex items-center gap-2.5 text-xs sm:text-sm px-3.5 sm:px-4 py-2.5 sm:py-3 rounded-2xl border font-semibold ${
        isDone ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-700' :
        isError ? 'bg-red-500/10 border-red-500/20 text-red-600' :
        'bg-slate-100 border-slate-200 text-slate-800'
      }`}
    >
      {isDone ? <CheckCircle size={16} /> :
       isError ? <AlertCircle size={16} /> :
       <Loader2 size={16} className="animate-spin" />}
      <span>
        {isDone
          ? `✅ GraphRAG indexed — ${status.stats?.entities_extracted ?? 0} entities, ${status.stats?.graph_nodes ?? 0} graph nodes`
          : isError
          ? `❌ Indexing failed: ${status.error}`
          : `🧠 GraphRAG indexing... ${status.progress ?? 0}% (${status.stage ?? 'processing'})`
        }
      </span>
    </motion.div>
  )
}

// ─── Main Component ─────────────────────────────────────────────────────────────
export default function ChatPage() {
  const { sessionId } = useParams<{ sessionId?: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const { user, token, logout } = useAuthStore()

  const {
    sessions, activeSession, isStreaming, streamingContent,
    setSessions, setActiveSession, setMessages, addMessage, removeSession,
    setStreaming, appendStreamToken, clearStreamingContent,
  } = useChatStore()

  const [input, setInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [uploadingFile, setUploadingFile] = useState(false)
  const [uploadStatuses, setUploadStatuses] = useState<string[]>([])
  const [showGraphPanel, setShowGraphPanel] = useState(false)
  const [showQuizGame, setShowQuizGame] = useState(false)
  const [showFlashcards, setShowFlashcards] = useState(false)
  const [upgradeModalInfo, setUpgradeModalInfo] = useState<{ open: boolean; fileName?: string; sizeMb?: number }>({ open: false })
  const [liveGraphContext, setLiveGraphContext] = useState<GraphContextData>({ entities: [], relationships: [] })
  const [liveSources, setLiveSources] = useState<Source[]>([])
  const [extMessages, setExtMessages] = useState<ExtendedMessage[]>([])
  const [selectedModel, setSelectedModel] = useState('DeepTutor AI (Llama 3.1)')

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

  // Fetch sessions
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
    staleTime: 0,
  })

  const handleSend = useCallback(async (text?: string) => {
    let content = (text ?? input).trim()
    if (!content || isStreaming) return

    let currentSessionId: string = activeSession?.id || ''
    const isKnownSession = sessions.some((s) => s.id === currentSessionId)
    if (!currentSessionId || !isKnownSession) {
      try {
        const res = await chatApi.createSession('', content.slice(0, 30) || 'New Chat')
        currentSessionId = res.data.id
        skipNextFetchRef.current = currentSessionId
        setActiveSession(res.data)
        await refetchSessions()
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
        const fallback: ExtendedMessage = {
          id: Date.now().toString() + '_fallback',
          role: 'assistant',
          content: accContent || `⚠️ **Error communicating with AI backend:** ${err?.message || 'Server error'}. Please verify that FastAPI backend is running on http://localhost:8000.`,
          created_at: new Date().toISOString(),
        }
        setExtMessages((prev) => [...prev, fallback])
        clearStreamingContent()
        setStreaming(false)
      },
    })
  }, [input, isStreaming, activeSession, token, navigate, refetchSessions, setActiveSession, addMessage, appendStreamToken, clearStreamingContent, setStreaming])

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

  // Group sessions by date
  const groupedSessions = useMemo(() => {
    const filtered = sessions.filter((s) =>
      s.session_title.toLowerCase().includes(searchQuery.toLowerCase())
    )

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

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [extMessages, streamingContent])

  const handleDeleteSession = async (e?: React.MouseEvent, sId?: string) => {
    if (e) e.stopPropagation()
    const targetId = sId || activeSession?.id
    if (!targetId) return
    if (!confirm('Are you sure you want to delete this chat session? All messages, documents, and study materials for this session will be permanently removed.')) return
    try {
      await chatApi.deleteSession(targetId)
      removeSession(targetId)
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
      alert('Failed to delete session from database. Please try again.')
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

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    const fileSizeMb = file.size / (1024 * 1024)
    const isPremium = Boolean(user?.is_premium)
    const maxLimitMb = isPremium ? 100 : 10

    if (fileSizeMb > maxLimitMb && !isPremium) {
      setUpgradeModalInfo({ open: true, fileName: file.name, sizeMb: fileSizeMb })
      if (fileInputRef.current) fileInputRef.current.value = ''
      return
    }

    setUploadingFile(true)

    try {
      let targetSessionId: string = activeSession?.id || ''
      const isKnownSession = sessions.some((s) => s.id === targetSessionId)
      if (!targetSessionId || !isKnownSession) {
        const newSess = await chatApi.createSession('', file.name.slice(0, 30))
        targetSessionId = newSess.data.id
        skipNextFetchRef.current = targetSessionId
        setActiveSession(newSess.data)
        await refetchSessions()
        navigate(`/chat/${newSess.data.id}`)
      }

      const topicId = targetSessionId || 'general'
      const formData = new FormData()
      formData.append('file', file)
      formData.append('topic_id', topicId)
      formData.append('section_id', topicId)

      const res = await fetch('/api/documents/upload', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      })
      const data = await res.json()

      if (res.ok) {
        setUploadStatuses((prev) => [...prev, data.id])
        const infoMsg: ExtendedMessage = {
          id: Date.now().toString(),
          role: 'assistant',
          content: `📄 **${file.name}** uploaded successfully!\n\n🧠 **GraphRAG indexing started** — Extracting entities and knowledge graph nodes from your PDF. You can start asking questions right away.`,
          created_at: new Date().toISOString(),
        }
        setExtMessages((prev) => [...prev, infoMsg])
      } else {
        if (res.status === 401) {
          logout()
          navigate('/login')
          throw new Error('Your login session expired. Please log in again.')
        }
        const detailMsg = typeof data.detail === 'object' ? data.detail?.message : data.detail
        if (data.detail?.requires_premium) {
          setUpgradeModalInfo({ open: true, fileName: file.name, sizeMb: fileSizeMb })
        }
        throw new Error(detailMsg ?? 'Upload failed')
      }
    } catch (err: any) {
      const errMsg: ExtendedMessage = {
        id: Date.now().toString(),
        role: 'assistant',
        content: `❌ Upload failed: ${err.message}`,
        created_at: new Date().toISOString(),
      }
      setExtMessages((prev) => [...prev, errMsg])
    } finally {
      setUploadingFile(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const streamingMsg: ExtendedMessage | null =
    isStreaming && streamingContent
      ? { id: 'streaming', role: 'assistant', content: streamingContent, created_at: '' }
      : null

  const allMessages = streamingMsg ? [...extMessages, streamingMsg] : extMessages

  return (
    <div className="flex flex-col md:flex-row h-screen w-full bg-[#FAF8F3] overflow-hidden text-[#20201D] font-sans">
      
      {/* ─── MOBILE BACKDROP OVERLAYS ────────────────────────────────────────── */}
      <AnimatePresence>
        {(mobileLeftOpen || mobileRightOpen) && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => { setMobileLeftOpen(false); setMobileRightOpen(false); }}
            className="fixed inset-0 bg-[#20201D]/40 backdrop-blur-sm z-40 md:hidden"
          />
        )}
      </AnimatePresence>

      {/* ─── MOBILE LEFT DRAWER (CHAT HISTORY) ─── */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-72 bg-white border-r border-[#E7E1D8] p-4 flex flex-col justify-between shadow-2xl transition-transform duration-300 md:hidden ${
          mobileLeftOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-[#E7E1D8]">
            <div className="flex items-center gap-2">
              <MessageSquare size={18} className="text-[#F28A45]" />
              <h3 className="text-xs font-extrabold uppercase text-[#6F6B63] tracking-wider">
                Chat History
              </h3>
            </div>
            <button
              onClick={() => setMobileLeftOpen(false)}
              className="text-[#969188] hover:text-[#20201D] p-1.5 rounded-xl hover:bg-[#F4EFE7]"
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
            className="w-full btn-primary font-bold text-xs py-2.5 px-3 rounded-xl flex items-center justify-center gap-2 shadow-2xs cursor-pointer"
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
                  className={`group flex items-center justify-between px-3 py-2.5 rounded-xl text-xs cursor-pointer transition-all ${
                    isSelected
                      ? 'bg-[#FFF0E4] text-[#F28A45] font-extrabold border border-[#F28A45]/30 shadow-2xs'
                      : 'text-[#6F6B63] hover:text-[#20201D] hover:bg-[#F4EFE7] font-medium'
                  }`}
                >
                  <span className="truncate pr-2">{s.session_title || 'Untitled Chat'}</span>
                  <button
                    onClick={(e) => handleDeleteSession(e, s.id)}
                    className="text-[#969188] hover:text-[#C85C52] hover:bg-[#FBE7E4] p-1.5 rounded-lg transition-colors"
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
      <main className="flex-1 flex flex-col bg-[#FAF8F3] overflow-hidden relative">

        {/* Hidden File Input */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.webp,.bmp,.docx,.doc,.csv,.xlsx,.xls,.pptx,.ppt,.html,.json,.txt,.md"
          className="hidden"
          onChange={handleFileUpload}
        />

        {/* Top Header Bar */}
        <header className="h-16 border-b border-[#E7E1D8] flex items-center justify-between px-4 sm:px-6 flex-shrink-0 bg-[#FAF8F3]/80 backdrop-blur-md">
          
          <div className="flex items-center gap-3">
            {/* Mobile Left Drawer Trigger */}
            <button
              onClick={() => setMobileLeftOpen(true)}
              className="md:hidden p-2 text-[#20201D] hover:bg-[#F4EFE7] rounded-xl transition-colors"
              title="Open Chat History"
            >
              <Menu size={20} />
            </button>

            {/* Model Switcher Pill */}
            <div className="flex items-center gap-2 px-3 py-1.5 sm:px-3.5 sm:py-2 rounded-2xl border border-[#E7E1D8] bg-white hover:bg-[#FFF0E4] hover:border-[#F28A45]/40 cursor-pointer transition-all shadow-2xs">
              <div className="w-5 h-5 sm:w-6 sm:h-6 rounded-xl bg-[#FFF0E4] text-[#F28A45] flex items-center justify-center border border-[#F28A45]/30">
                <Sparkles size={13} />
              </div>
              <span className="text-xs font-black text-[#20201D] truncate max-w-[140px] sm:max-w-none">{selectedModel}</span>
              <ChevronDown size={14} className="text-[#969188] flex-shrink-0" />
            </div>
          </div>

          <div className="flex items-center gap-2">
            {activeSession && (
              <button
                onClick={(e) => handleDeleteSession(e, activeSession.id)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white hover:bg-[#FBE7E4] border border-[#E7E1D8] hover:border-[#C85C52]/40 text-[#6F6B63] hover:text-[#C85C52] text-xs font-bold transition-all shadow-2xs cursor-pointer active:scale-95"
                title="Delete this chat session & database records"
              >
                <Trash2 size={13} className="text-[#C85C52]" />
                <span className="hidden sm:inline">Delete Section</span>
              </button>
            )}

            {/* Mobile Right Drawer Trigger */}
            <button
              onClick={() => setMobileRightOpen(true)}
              className="lg:hidden flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#FFF0E4] border border-[#F28A45]/30 text-[#F28A45] text-xs font-extrabold hover:bg-[#DF7635] hover:text-white transition-colors"
              title="Study Tools & Graph"
            >
              <Zap size={14} />
              <span>Tools</span>
            </button>
          </div>
        </header>

        {/* Upload Status Notification */}
        {uploadStatuses.length > 0 && (
          <div className="px-4 sm:px-6 py-2 border-b border-[#E7E1D8] bg-[#FFF9F2]">
            <AnimatePresence>
              {uploadStatuses.map((docId) => (
                <UploadStatus
                  key={docId}
                  docId={docId}
                  onDone={() => setUploadStatuses((prev) => prev.filter((id) => id !== docId))}
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
              
              {/* Warm Icon Graphic */}
              <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-3xl bg-[#FFF0E4] border border-[#F28A45]/30 text-[#F28A45] flex items-center justify-center shadow-md mb-4 sm:mb-6">
                <Sparkles className="w-8 h-8 sm:w-10 sm:h-10 text-[#F28A45]" />
              </div>

              {/* Personal Greeting & Headline */}
              <p className="text-[#6F6B63] font-extrabold text-sm sm:text-base mb-1 tracking-wide">
                Hello, {user?.username ?? 'Learner'}
              </p>
              <h1 className="text-2xl sm:text-4xl font-black text-[#20201D] tracking-tight mb-6 sm:mb-8">
                How can I assist you today?
              </h1>

              {/* Clean Multi-Tool Input Container */}
              <div className="w-full bg-white border border-[#E7E1D8] rounded-3xl p-3.5 sm:p-5 shadow-xs focus-within:border-[#F28A45] focus-within:ring-2 focus-within:ring-[#F28A45]/20 transition-all text-left">
                
                {/* 3 Quick Study Tool Action Buttons */}
                <div className="flex flex-wrap items-center gap-2 mb-3 pb-3 border-b border-[#E7E1D8]">
                  <span className="text-[11px] font-black uppercase text-[#6F6B63] tracking-wider mr-1 flex items-center gap-1">
                    <Sparkles size={13} className="text-[#F28A45]" /> Tools:
                  </span>
                  
                  <button
                    type="button"
                    onClick={() => {
                      const topic = input.trim() || 'the main topic in my study material'
                      handleSend(`Summarize ${topic} into 5-7 clear, high-yield bullet points for quick revision.`)
                    }}
                    disabled={isStreaming}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#FAF8F3] hover:bg-[#FFF0E4] border border-[#E7E1D8] hover:border-[#F28A45]/40 text-[#20201D] hover:text-[#F28A45] text-xs font-bold transition-all shadow-2xs cursor-pointer active:scale-95 disabled:opacity-40"
                    title="Generate 5-7 key bullet points"
                  >
                    <ListChecks size={13} className="text-[#F28A45]" />
                    <span>Bullet Points</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      const topic = input.trim() || 'this subject'
                      handleSend(`What are the most important exam-critical points, core formulas, and common misconceptions about ${topic}?`)
                    }}
                    disabled={isStreaming}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#FAF8F3] hover:bg-[#FFF3D8] border border-[#E7E1D8] hover:border-[#D99A32]/40 text-[#20201D] hover:text-[#D99A32] text-xs font-bold transition-all shadow-2xs cursor-pointer active:scale-95 disabled:opacity-40"
                    title="Highlight key exam-critical formulas & concepts"
                  >
                    <Star size={13} className="text-[#D99A32]" />
                    <span>Important Points</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      const topic = input.trim() || 'the central concept'
                      handleSend(`Explain ${topic} using a simple, intuitive real-world analogy and visual mental model.`)
                    }}
                    disabled={isStreaming}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#FAF8F3] hover:bg-[#E3F0E5] border border-[#E7E1D8] hover:border-[#4F8A68]/40 text-[#20201D] hover:text-[#4F8A68] text-xs font-bold transition-all shadow-2xs cursor-pointer active:scale-95 disabled:opacity-40"
                    title="Explain with a simple real-world analogy"
                  >
                    <Lightbulb size={13} className="text-[#4F8A68]" />
                    <span>Simple Analogy</span>
                  </button>
                </div>

                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  rows={2}
                  className="w-full bg-transparent resize-none outline-none text-[#20201D] font-medium text-sm sm:text-base placeholder-[#969188] leading-relaxed px-1"
                  placeholder="Ask your AI Tutor anything..."
                />

                {/* Sub Action Toolbar */}
                <div className="flex items-center justify-between gap-2 mt-3 sm:mt-4 pt-3 border-t border-[#E7E1D8]">
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploadingFile}
                    className="flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-1.5 sm:py-2 rounded-xl bg-[#FAF8F3] hover:bg-[#FFF0E4] border border-[#E7E1D8] hover:border-[#F28A45]/30 text-[#20201D] text-xs font-bold transition-all shadow-2xs disabled:opacity-40 cursor-pointer"
                  >
                    {uploadingFile ? <Loader2 size={14} className="animate-spin text-[#F28A45]" /> : <Paperclip size={14} className="text-[#F28A45]" />}
                    <span>{uploadingFile ? 'Uploading...' : 'Attach PDF'}</span>
                  </button>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={toggleVoiceInput}
                      className={`p-2.5 sm:p-3 rounded-full text-white transition-all shadow-xs cursor-pointer ${
                        isListening
                          ? 'bg-[#C85C52] animate-bounce ring-4 ring-[#FBE7E4]'
                          : 'bg-[#F28A45] hover:bg-[#DF7635]'
                      }`}
                      title={isListening ? 'Stop Recording' : 'Voice Input'}
                    >
                      {isListening ? <MicOff size={16} /> : <Mic size={16} />}
                    </button>

                    <button
                      onClick={() => handleSend()}
                      disabled={!input.trim()}
                      className="p-2.5 sm:p-3 rounded-full bg-[#F28A45] hover:bg-[#DF7635] text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-xs cursor-pointer"
                    >
                      <Send size={15} />
                    </button>
                  </div>
                </div>

              </div>

              {/* Starter Action Cards */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 sm:gap-4 w-full mt-6 sm:mt-8">
                
                <SuggestionCard
                  icon={<div className="w-10 h-10 rounded-2xl bg-[#FFF0E4] text-[#F28A45] flex items-center justify-center border border-[#F28A45]/20"><Clock className="w-5 h-5" /></div>}
                  title="Synthesize Notes"
                  description="Turn my uploaded PDF notes into 5 key bullet points for quick review."
                  onClick={() => handleSend("Turn my uploaded PDF notes into 5 key bullet points for quick review.")}
                />

                <SuggestionCard
                  icon={<div className="w-10 h-10 rounded-2xl bg-[#FFF3D8] text-[#D99A32] flex items-center justify-center border border-[#D99A32]/20"><Trophy className="w-5 h-5" /></div>}
                  title="Practice Quiz"
                  description="Generate a 5-question multiple choice practice quiz from my material."
                  onClick={() => handleSend("Generate a 5-question multiple choice practice quiz from my material.")}
                />

                <SuggestionCard
                  icon={<div className="w-10 h-10 rounded-2xl bg-[#E3F0E5] text-[#4F8A68] flex items-center justify-center border border-[#4F8A68]/20"><Brain className="w-5 h-5" /></div>}
                  title="Concept Explanation"
                  description="Explain complex topics step-by-step with clear real-world examples."
                  onClick={() => handleSend("Explain quantum mechanics step-by-step with clear real-world examples.")}
                />

              </div>

            </div>
          )}

          {/* ACTIVE CHAT THREAD */}
          {allMessages.length > 0 && (
            <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4 sm:space-y-6 max-w-4xl mx-auto w-full">
              {allMessages.map((msg) => (
                <ChatMessage
                  key={msg.id}
                  role={msg.role}
                  content={msg.content}
                  isStreaming={msg.id === 'streaming'}
                  sources={msg.id === 'streaming' ? liveSources : msg.sources}
                  grounding={msg.grounding}
                />
              ))}

              {isStreaming && !streamingContent && (
                <div className="flex gap-3 sm:gap-4">
                  <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-2xl bg-[#FFF0E4] text-[#F28A45] border border-[#F28A45]/30 flex items-center justify-center flex-shrink-0 shadow-xs">
                    <Sparkles size={16} />
                  </div>
                  <div className="bg-white border border-[#E7E1D8] rounded-2xl px-4 sm:px-5 py-3 sm:py-4">
                    <div className="flex items-center gap-2">
                      <span className="flex gap-1">
                        <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
                      </span>
                      <span className="text-xs font-bold text-[#6F6B63]">Searching GraphRAG knowledge base...</span>
                    </div>
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          )}

        </div>

        {/* Input Bar (Sticky at bottom when chat messages exist) */}
        {allMessages.length > 0 && (
          <div className="p-3 sm:p-4 border-t border-[#E7E1D8] bg-white">
            <div className="max-w-4xl mx-auto bg-[#FAF8F3] border border-[#E7E1D8] rounded-2xl p-3 sm:p-3.5 focus-within:border-[#F28A45] focus-within:ring-2 focus-within:ring-[#F28A45]/20 transition-all">
              
              {/* Quick Study Tool Pill Buttons */}
              <div className="flex flex-wrap items-center gap-1.5 mb-2.5 pb-2 border-b border-[#E7E1D8]">
                <button
                  type="button"
                  onClick={() => {
                    const topic = input.trim() || 'the previous topic'
                    handleSend(`Summarize ${topic} into 5-7 clear, high-yield bullet points for quick revision.`)
                  }}
                  disabled={isStreaming}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-white hover:bg-[#FFF0E4] border border-[#E7E1D8] hover:border-[#F28A45]/40 text-[#20201D] hover:text-[#F28A45] text-[11px] font-bold transition-all shadow-2xs cursor-pointer active:scale-95 disabled:opacity-40"
                  title="Generate bullet points"
                >
                  <ListChecks size={12} className="text-[#F28A45]" />
                  <span>Bullet Points</span>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    const topic = input.trim() || 'this topic'
                    handleSend(`What are the most important exam-critical points, core formulas, and common misconceptions for ${topic}?`)
                  }}
                  disabled={isStreaming}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-white hover:bg-[#FFF3D8] border border-[#E7E1D8] hover:border-[#D99A32]/40 text-[#20201D] hover:text-[#D99A32] text-[11px] font-bold transition-all shadow-2xs cursor-pointer active:scale-95 disabled:opacity-40"
                  title="Important exam points"
                >
                  <Star size={12} className="text-[#D99A32]" />
                  <span>Important Points</span>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    const topic = input.trim() || 'this concept'
                    handleSend(`Explain ${topic} with a simple real-world analogy and visual mental model.`)
                  }}
                  disabled={isStreaming}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-white hover:bg-[#E3F0E5] border border-[#E7E1D8] hover:border-[#4F8A68]/40 text-[#20201D] hover:text-[#4F8A68] text-[11px] font-bold transition-all shadow-2xs cursor-pointer active:scale-95 disabled:opacity-40"
                  title="Simple analogy"
                >
                  <Lightbulb size={12} className="text-[#4F8A68]" />
                  <span>Simple Analogy</span>
                </button>
              </div>

              <textarea
                ref={textareaRef}
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                rows={1}
                className="w-full bg-transparent resize-none outline-none text-[#20201D] font-medium text-sm sm:text-base placeholder-[#969188]"
                placeholder="Ask follow-up question..."
                style={{ minHeight: '28px', maxHeight: '160px' }}
              />
              <div className="flex items-center justify-between mt-2.5 pt-2 border-t border-[#E7E1D8]">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="flex items-center gap-1.5 text-xs font-bold text-[#20201D] bg-white hover:bg-[#FFF0E4] px-2.5 py-1.5 rounded-xl border border-[#E7E1D8] hover:border-[#F28A45]/30 shadow-2xs transition-colors cursor-pointer"
                  >
                    <Paperclip size={13} className="text-[#F28A45]" />
                    <span>Attach PDF</span>
                  </button>
                  <button
                    onClick={toggleVoiceInput}
                    className={`p-2 rounded-xl transition-colors cursor-pointer ${
                      isListening ? 'text-[#C85C52] bg-[#FBE7E4] animate-pulse' : 'text-[#6F6B63] hover:text-[#20201D] hover:bg-[#F4EFE7]'
                    }`}
                    title="Voice input"
                  >
                    <Mic size={16} />
                  </button>
                </div>
                <button
                  onClick={() => handleSend()}
                  disabled={!input.trim() || isStreaming}
                  className="p-2.5 rounded-xl bg-[#F28A45] hover:bg-[#DF7635] text-white disabled:opacity-30 transition-all shadow-xs cursor-pointer"
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
        className={`fixed lg:static inset-y-0 right-0 z-50 w-80 bg-[#FAF8F3] border-l border-[#E7E1D8] p-5 flex flex-col justify-between overflow-y-auto shadow-2xl lg:shadow-none transition-transform duration-300 ${
          mobileRightOpen ? 'translate-x-0' : 'translate-x-full lg:translate-x-0'
        }`}
      >
        <div className="space-y-4">
          <div className="flex items-center justify-between mb-1 pb-3 border-b border-[#E7E1D8]">
            <div className="flex items-center gap-2.5">
              <Sparkles size={18} className="text-[#F28A45]" />
              <h3 className="text-xs font-extrabold uppercase text-[#6F6B63] tracking-wider">
                Study Tools & Graph
              </h3>
            </div>
            <button
              onClick={() => setMobileRightOpen(false)}
              className="lg:hidden text-[#969188] hover:text-[#20201D] p-1.5 rounded-xl hover:bg-[#F4EFE7]"
            >
              <X size={18} />
            </button>
          </div>

          {/* 1. Flashcards Card */}
          <motion.div
            whileHover={{ scale: 1.02 }}
            onClick={() => { setShowFlashcards(true); setMobileRightOpen(false); }}
            className="p-4 sm:p-5 rounded-3xl bg-white border border-[#E7E1D8] hover:border-[#F28A45] shadow-2xs hover:shadow-xs transition-all cursor-pointer group relative overflow-hidden"
          >
            <div className="w-11 h-11 sm:w-12 sm:h-12 rounded-2xl bg-[#FFF0E4] border border-[#F28A45]/30 flex items-center justify-center mb-3 shadow-2xs p-2 group-hover:scale-105 transition-transform">
              <img src="/assets/illustrations/stack_of_books.png" alt="Flashcards" className="w-full h-full object-contain" />
            </div>
            <h4 className="text-base font-extrabold text-[#20201D] group-hover:text-[#F28A45] transition-colors">
              Flashcards Deck
            </h4>
            <p className="text-xs text-[#6F6B63] mt-1.5 leading-relaxed font-medium">
              Review AI study cards generated strictly from your uploaded PDF text.
            </p>
            <div className="mt-4 flex items-center gap-1.5 text-xs font-extrabold text-[#F28A45] group-hover:translate-x-1 transition-transform">
              <span>Study Flashcards</span> <ArrowRight size={14} />
            </div>
          </motion.div>

          {/* 2. Play Quiz Card */}
          <motion.div
            whileHover={{ scale: 1.02 }}
            onClick={() => { setShowQuizGame(true); setMobileRightOpen(false); }}
            className="p-4 sm:p-5 rounded-3xl bg-[#FFF9F2] border border-[#F28A45]/30 shadow-2xs hover:shadow-xs transition-all cursor-pointer group relative overflow-hidden"
          >
            <div className="w-11 h-11 sm:w-12 sm:h-12 rounded-2xl bg-[#FFF3D8] border border-[#D99A32]/30 flex items-center justify-center mb-3 shadow-2xs p-2 group-hover:scale-105 transition-transform">
              <img src="/assets/illustrations/gold_medal.png" alt="Quiz" className="w-full h-full object-contain" />
            </div>
            <h4 className="text-base font-extrabold text-[#20201D] group-hover:text-[#F28A45] transition-colors">
              Play Gamified Quiz
            </h4>
            <p className="text-xs text-[#6F6B63] mt-1.5 leading-relaxed font-medium">
              Test your understanding with PDF-based quizzes, score XP & master topics.
            </p>
            <div className="mt-4 flex items-center gap-1.5 text-xs font-extrabold text-[#F28A45] group-hover:translate-x-1 transition-transform">
              <span>Start Quiz Game</span> <ArrowRight size={14} />
            </div>
          </motion.div>

          {/* 3. Knowledge Graph Card */}
          <motion.div
            whileHover={{ scale: 1.02 }}
            onClick={() => { setShowGraphPanel(true); setMobileRightOpen(false); }}
            className="p-4 sm:p-5 rounded-3xl bg-white border border-[#E7E1D8] hover:border-[#4F8A68] shadow-2xs hover:shadow-xs transition-all cursor-pointer group relative overflow-hidden"
          >
            <div className="w-11 h-11 sm:w-12 sm:h-12 rounded-2xl bg-[#E3F0E5] border border-[#4F8A68]/30 flex items-center justify-center mb-3 shadow-2xs p-2 group-hover:scale-105 transition-transform">
              <img src="/assets/illustrations/cs_code.png" alt="Knowledge Graph" className="w-full h-full object-contain" />
            </div>
            <div className="flex items-center justify-between">
              <h4 className="text-base font-extrabold text-[#20201D] group-hover:text-[#4F8A68] transition-colors">
                Knowledge Graph
              </h4>
              {liveGraphContext.entities.length > 0 && (
                <span className="text-[10px] font-extrabold bg-[#E3F0E5] text-[#35654B] px-2 py-0.5 rounded-full border border-[#4F8A68]/30">
                  {liveGraphContext.entities.length} Nodes
                </span>
              )}
            </div>
            <p className="text-xs text-[#6F6B63] mt-1.5 leading-relaxed font-medium">
              Explore 3D visual entity maps and document relationship connections.
            </p>
            <div className="mt-4 flex items-center gap-1.5 text-xs font-extrabold text-[#4F8A68] group-hover:translate-x-1 transition-transform">
              <span>Explore 3D Graph</span> <ArrowRight size={14} />
            </div>
          </motion.div>
        </div>

        <div className="pt-4 border-t border-[#E7E1D8] text-center">
          <p className="text-xs font-bold text-[#969188]">
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
      onClick={onSelect}
      className={`group w-full flex items-center justify-between px-3 py-2.5 rounded-xl transition-all cursor-pointer ${
        isActive
          ? 'bg-[#FFF0E4] text-[#F28A45] font-extrabold shadow-2xs border border-[#F28A45]/30'
          : 'text-[#6F6B63] hover:bg-[#F4EFE7] hover:text-[#20201D] font-medium'
      }`}
    >
      <div className="flex items-center gap-2.5 min-w-0 pr-1">
        <MessageSquare size={15} className={isActive ? 'text-[#F28A45]' : 'text-[#969188]'} />
        <span className="truncate text-xs">{session.session_title}</span>
      </div>
      <button
        onClick={onDelete}
        className={`opacity-0 group-hover:opacity-100 p-1 rounded-lg transition-all ${
          isActive ? 'text-[#F28A45] hover:text-[#C85C52] hover:bg-[#FFF0E4]' : 'text-[#969188] hover:text-[#C85C52] hover:bg-[#FBE7E4]'
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
      onClick={onClick}
      className="p-4 sm:p-5 rounded-3xl bg-white border border-[#E7E1D8] hover:border-[#F28A45]/40 hover:bg-[#FFF9F2] transition-all cursor-pointer text-left group shadow-2xs hover:shadow-xs"
    >
      <div className="mb-2 sm:mb-3">{icon}</div>
      <h3 className="font-extrabold text-sm sm:text-base text-[#20201D] group-hover:text-[#F28A45] mb-1">{title}</h3>
      <p className="text-xs text-[#6F6B63] leading-relaxed font-medium">{description}</p>
    </div>
  )
}

