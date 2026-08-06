import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Send, Paperclip, Plus, MessageSquare,
  Sparkles, BookOpen, Brain, GraduationCap,
  CheckCircle, AlertCircle, Loader2, Trophy, Trash2,
  Mic, MicOff, Search, Share2, Download,
  ChevronDown, LogOut, Network,
  Clock, ArrowRight, Menu, X, Zap, Cpu
} from 'lucide-react'
import { useChatStore } from '../stores/chatStore'
import { useAuthStore } from '../stores/authStore'
import { chatApi } from '../services/api'
import ChatMessage from '../components/ChatMessage'
import GraphContextPanel from '../components/GraphContextPanel'
import GamifiedQuizGame from '../components/GamifiedQuizGame'
import FlashcardsOverlay from '../components/FlashcardsOverlay'
import McpDrawer from '../components/McpDrawer'
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
  const [showMcpDrawer, setShowMcpDrawer] = useState(false)
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
  const eventSourceRef = useRef<EventSource | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

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

  // Load session messages when sessionId changes
  useEffect(() => {
    if (!sessionId) return
    chatApi.messages(sessionId).then((res) => {
      const msgs: ExtendedMessage[] = res.data.map((m: any) => ({
        ...m,
        sources: m.metadata?.sources ?? [],
        graph_context: m.metadata?.graph_context ?? null,
      }))
      setExtMessages(msgs)
      setMessages(res.data)
      const session = sessions.find((s) => s.id === sessionId)
      if (session) setActiveSession(session)
    })
  }, [sessionId])

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

  const handleDeleteSession = async (e: React.MouseEvent, sId: string) => {
    e.stopPropagation()
    if (!confirm('Are you sure you want to delete this chat session?')) return
    try {
      await chatApi.deleteSession(sId)
      removeSession(sId)
      if (activeSession?.id === sId) {
        const remaining = sessions.filter((s) => s.id !== sId)
        if (remaining.length > 0) {
          navigate(`/chat/${remaining[0].id}`)
        } else {
          navigate('/chat')
        }
      }
    } catch (err) {
      console.error('Failed to delete session:', err)
    }
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = `${Math.min(e.target.scrollHeight, 180)}px`
  }

  const handleSend = useCallback(async (text?: string) => {
    let content = (text ?? input).trim()
    if (!content || isStreaming) return

    let currentSessionId = activeSession?.id
    if (!currentSessionId) {
      try {
        const res = await chatApi.createSession('', content.slice(0, 30) || 'New Chat')
        await refetchSessions()
        currentSessionId = res.data.id
        setActiveSession(res.data)
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

    if (eventSourceRef.current) eventSourceRef.current.close()

    const url = `/api/chat/sessions/${currentSessionId}/message/stream?content=${encodeURIComponent(content)}&token=${token}`
    const es = new EventSource(url)
    eventSourceRef.current = es

    let accContent = ''
    let accSources: Source[] = []
    let accGraph: GraphContextData = { entities: [], relationships: [] }

    es.onmessage = (event) => {
      try {
        const evt = JSON.parse(event.data)
        if (evt.type === 'token') {
          accContent += evt.data
          appendStreamToken(evt.data)
        } else if (evt.type === 'sources') {
          accSources = evt.data
          setLiveSources(evt.data)
        } else if (evt.type === 'graph_context') {
          accGraph = evt.data
          setLiveGraphContext(evt.data)
        } else if (evt.type === 'done') {
          es.close()
          const assistantMsg: ExtendedMessage = {
            id: Date.now().toString() + '_ai',
            role: 'assistant',
            content: accContent,
            created_at: new Date().toISOString(),
            sources: accSources,
            graph_context: accGraph,
          }
          setExtMessages((prev) => [...prev, assistantMsg])
          clearStreamingContent()
          setStreaming(false)
        }
      } catch { /* ignore */ }
    }

    es.onerror = () => {
      es.close()
      const fallback: ExtendedMessage = {
        id: Date.now().toString() + '_fallback',
        role: 'assistant',
        content: accContent || '⚠️ **Backend not connected.** Start the FastAPI backend to use DeepTutor GraphRAG:\n```bash\ncd backend\nuvicorn app.main:app --reload\n```',
        created_at: new Date().toISOString(),
      }
      setExtMessages((prev) => [...prev, fallback])
      clearStreamingContent()
      setStreaming(false)
    }
  }, [input, isStreaming, activeSession, token, navigate, refetchSessions, setActiveSession, addMessage, appendStreamToken, clearStreamingContent, setStreaming])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadingFile(true)

    try {
      let targetSessionId = activeSession?.id
      if (!targetSessionId) {
        const newSess = await chatApi.createSession('', file.name.slice(0, 30))
        targetSessionId = newSess.data.id
        setActiveSession(newSess.data)
        navigate(`/chat/${newSess.data.id}`)
      }

      const topicId = activeSession?.topic_id || 'general'
      const formData = new FormData()
      formData.append('file', file)
      formData.append('topic_id', topicId)

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
        throw new Error(data.detail ?? 'Upload failed')
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
    <div className="flex flex-col md:flex-row h-screen w-full bg-[#f8fafc] overflow-hidden text-slate-800 font-sans">
      
      {/* ─── MOBILE BACKDROP OVERLAYS ────────────────────────────────────────── */}
      <AnimatePresence>
        {(mobileLeftOpen || mobileRightOpen) && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => { setMobileLeftOpen(false); setMobileRightOpen(false); }}
            className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-40 md:hidden"
          />
        )}
      </AnimatePresence>

      {/* ─── LEFT SIDEBAR (RESPONSIVE DRAWER ON MOBILE, FIXED ON DESKTOP) ─────── */}
      <aside
        className={`fixed md:static inset-y-0 left-0 z-50 w-72 bg-[#f4f4f8] border-r border-slate-200/90 text-slate-800 flex flex-col justify-between p-4 select-none shadow-xl md:shadow-none transition-transform duration-300 ${
          mobileLeftOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        }`}
      >
        <div className="flex flex-col h-full overflow-hidden">
          
          {/* DeepTutor Brand Header (Easlo Hero Style) */}
          <div className="flex items-center justify-between px-2 py-2 mb-4 border-b border-slate-200/80 pb-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-[#111111] flex items-center justify-center text-white shadow-sm">
                <GraduationCap size={22} />
              </div>
              <div>
                <span className="font-black text-slate-900 text-lg tracking-tight">DeepTutor</span>
                <span className="text-[10px] font-extrabold uppercase tracking-wider bg-[#f4f4f5] text-[#18181b] px-2 py-0.5 rounded-full border border-[#e4e4e7] ml-2">AI</span>
              </div>
            </div>
            <button
              onClick={() => setMobileLeftOpen(false)}
              className="md:hidden text-slate-400 hover:text-slate-700 p-1.5 rounded-xl hover:bg-slate-200/60"
            >
              <X size={18} />
            </button>
          </div>

          {/* New Chat Button (Easlo Obsidian Black) */}
          <button
            onClick={() => {
              navigate('/chat')
              setActiveSession(null)
              setExtMessages([])
              setMobileLeftOpen(false)
            }}
            className="w-full bg-[#111111] hover:bg-[#27272a] text-white font-bold text-sm py-3 px-4 rounded-2xl flex items-center justify-center gap-2 shadow-sm transition-all active:scale-[0.98] mb-4"
          >
            <Plus size={18} />
            <span>New Chat</span>
          </button>

          {/* Search Box */}
          <div className="relative mb-4">
            <Search size={15} className="absolute left-3.5 top-3.5 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search chat history..."
              className="w-full bg-white border border-slate-200 rounded-xl pl-10 pr-8 py-2.5 text-xs font-semibold text-slate-900 placeholder-slate-400 outline-none focus:border-[#111111] focus:ring-2 focus:ring-slate-200 transition-all shadow-sm"
            />
            <span className="absolute right-3 top-3 text-[10px] font-bold text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">⌘</span>
          </div>

          {/* Chat Sessions History */}
          <div className="flex-1 overflow-y-auto space-y-4 pr-1 text-xs">
            {groupedSessions.today.length > 0 && (
              <div>
                <p className="px-2 text-[11px] font-extrabold text-slate-400 uppercase tracking-wider mb-2">Today</p>
                <div className="space-y-1">
                  {groupedSessions.today.map((s) => (
                    <SessionItem
                      key={s.id}
                      session={s}
                      activeId={activeSession?.id}
                      onSelect={() => { navigate(`/chat/${s.id}`); setMobileLeftOpen(false); }}
                      onDelete={(e) => handleDeleteSession(e, s.id)}
                    />
                  ))}
                </div>
              </div>
            )}

            {groupedSessions.yesterday.length > 0 && (
              <div>
                <p className="px-2 text-[11px] font-extrabold text-slate-400 uppercase tracking-wider mb-2">Yesterday</p>
                <div className="space-y-1">
                  {groupedSessions.yesterday.map((s) => (
                    <SessionItem
                      key={s.id}
                      session={s}
                      activeId={activeSession?.id}
                      onSelect={() => { navigate(`/chat/${s.id}`); setMobileLeftOpen(false); }}
                      onDelete={(e) => handleDeleteSession(e, s.id)}
                    />
                  ))}
                </div>
              </div>
            )}

            {groupedSessions.lastWeek.length > 0 && (
              <div>
                <p className="px-2 text-[11px] font-extrabold text-slate-400 uppercase tracking-wider mb-2">7 Days</p>
                <div className="space-y-1">
                  {groupedSessions.lastWeek.map((s) => (
                    <SessionItem
                      key={s.id}
                      session={s}
                      activeId={activeSession?.id}
                      onSelect={() => { navigate(`/chat/${s.id}`); setMobileLeftOpen(false); }}
                      onDelete={(e) => handleDeleteSession(e, s.id)}
                    />
                  ))}
                </div>
              </div>
            )}

            {groupedSessions.older.length > 0 && (
              <div>
                <p className="px-2 text-[11px] font-extrabold text-slate-400 uppercase tracking-wider mb-2">Older</p>
                <div className="space-y-1">
                  {groupedSessions.older.map((s) => (
                    <SessionItem
                      key={s.id}
                      session={s}
                      activeId={activeSession?.id}
                      onSelect={() => { navigate(`/chat/${s.id}`); setMobileLeftOpen(false); }}
                      onDelete={(e) => handleDeleteSession(e, s.id)}
                    />
                  ))}
                </div>
              </div>
            )}

            {sessions.length === 0 && (
              <p className="px-2 text-xs text-slate-400 italic">No chat history yet</p>
            )}
          </div>
        </div>
      </aside>

      {/* ─── MAIN CHAT WORKSPACE AREA ───────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col bg-white overflow-hidden relative">
        
        {/* Hidden File Input */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.txt,.md"
          className="hidden"
          onChange={handleFileUpload}
        />

        {/* Top Header Bar (Easlo Style Header) */}
        <header className="h-16 border-b border-slate-200/80 flex items-center justify-between px-4 sm:px-6 flex-shrink-0 bg-white/80 backdrop-blur-md">
          
          <div className="flex items-center gap-3">
            {/* Mobile Left Drawer Trigger */}
            <button
              onClick={() => setMobileLeftOpen(true)}
              className="md:hidden p-2 text-slate-600 hover:text-slate-900 rounded-xl hover:bg-slate-100 transition-colors"
              title="Open Chat History"
            >
              <Menu size={20} />
            </button>

            {/* Model Switcher Pill */}
            <div className="flex items-center gap-2 px-3 py-1.5 sm:px-3.5 sm:py-2 rounded-2xl border border-slate-200 bg-slate-50 hover:bg-slate-100 cursor-pointer transition-all">
              <div className="w-5 h-5 sm:w-6 sm:h-6 rounded-xl bg-[#111111] text-white flex items-center justify-center shadow-sm">
                <Sparkles size={13} />
              </div>
              <span className="text-xs font-extrabold text-slate-900 truncate max-w-[140px] sm:max-w-none">{selectedModel}</span>
              <ChevronDown size={14} className="text-slate-400 flex-shrink-0" />
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Mobile Right Drawer Trigger */}
            <button
              onClick={() => setMobileRightOpen(true)}
              className="lg:hidden flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 border border-slate-200 text-slate-800 text-xs font-extrabold hover:bg-slate-200 transition-colors"
              title="Study Tools & Graph"
            >
              <Zap size={14} />
              <span>Tools</span>
            </button>
          </div>
        </header>

        {/* Upload Status Notification */}
        {uploadStatuses.length > 0 && (
          <div className="px-4 sm:px-6 py-2 border-b border-slate-200 bg-slate-50">
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
          
          {/* HERO STATE (Easlo Clean Monochrome Tone) */}
          {allMessages.length === 0 && (
            <div className="flex-1 flex flex-col items-center justify-center px-4 sm:px-6 py-8 sm:py-10 max-w-3xl mx-auto w-full text-center">
              
              {/* Easlo Sleek Icon Graphic */}
              <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-3xl bg-[#111111] text-white flex items-center justify-center shadow-xl mb-4 sm:mb-6">
                <Sparkles className="w-8 h-8 sm:w-10 sm:h-10 text-white" />
              </div>

              {/* Personal Greeting & Headline */}
              <p className="text-slate-500 font-extrabold text-sm sm:text-base mb-1 tracking-wide">
                Hello, {user?.username ?? 'Learner'}
              </p>
              <h1 className="text-2xl sm:text-4xl font-black text-[#111111] tracking-tight mb-6 sm:mb-8">
                How can I assist you today?
              </h1>

              {/* Clean Multi-Tool Input Container */}
              <div className="w-full bg-[#f8fafc] border border-slate-200/90 rounded-3xl p-3.5 sm:p-5 shadow-sm focus-within:border-[#111111] focus-within:ring-2 focus-within:ring-slate-200 transition-all text-left">
                
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  rows={2}
                  className="w-full bg-transparent resize-none outline-none text-slate-900 font-medium text-sm sm:text-base placeholder-slate-400 leading-relaxed px-1"
                  placeholder="Ask your AI Tutor anything..."
                />

                {/* Sub Action Toolbar */}
                <div className="flex items-center justify-between gap-2 mt-3 sm:mt-4 pt-3 border-t border-slate-200/80">
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploadingFile}
                    className="flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-1.5 sm:py-2 rounded-xl bg-white border border-slate-200 hover:bg-slate-100 text-slate-700 text-xs font-bold transition-all shadow-sm disabled:opacity-40"
                  >
                    {uploadingFile ? <Loader2 size={14} className="animate-spin text-slate-800" /> : <Paperclip size={14} className="text-slate-800" />}
                    <span>{uploadingFile ? 'Uploading...' : 'Attach PDF'}</span>
                  </button>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={toggleVoiceInput}
                      className={`p-2.5 sm:p-3 rounded-full text-white transition-all shadow-md ${
                        isListening
                          ? 'bg-rose-600 animate-bounce ring-4 ring-rose-200'
                          : 'bg-[#111111] hover:bg-[#27272a]'
                      }`}
                      title={isListening ? 'Stop Recording' : 'Voice Input'}
                    >
                      {isListening ? <MicOff size={16} /> : <Mic size={16} />}
                    </button>

                    <button
                      onClick={() => handleSend()}
                      disabled={!input.trim()}
                      className="p-2.5 sm:p-3 rounded-full bg-[#111111] hover:bg-[#27272a] text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-md"
                    >
                      <Send size={15} />
                    </button>
                  </div>
                </div>

              </div>

              {/* Starter Action Cards */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 sm:gap-4 w-full mt-6 sm:mt-8">
                
                <SuggestionCard
                  icon={<Clock className="w-5 h-5 sm:w-6 sm:h-6 text-[#111111]" />}
                  title="Synthesize Notes"
                  description="Turn my uploaded PDF notes into 5 key bullet points for quick review."
                  onClick={() => handleSend("Turn my uploaded PDF notes into 5 key bullet points for quick review.")}
                />

                <SuggestionCard
                  icon={<Trophy className="w-5 h-5 sm:w-6 sm:h-6 text-amber-500" />}
                  title="Practice Quiz"
                  description="Generate a 5-question multiple choice practice quiz from my material."
                  onClick={() => handleSend("Generate a 5-question multiple choice practice quiz from my material.")}
                />

                <SuggestionCard
                  icon={<Brain className="w-5 h-5 sm:w-6 sm:h-6 text-[#111111]" />}
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
                />
              ))}

              {isStreaming && !streamingContent && (
                <div className="flex gap-3 sm:gap-4">
                  <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-2xl bg-[#111111] flex items-center justify-center text-white flex-shrink-0 shadow-md">
                    <Sparkles size={16} />
                  </div>
                  <div className="bg-slate-50 border border-slate-200 rounded-2xl px-4 sm:px-5 py-3 sm:py-4">
                    <div className="flex items-center gap-2">
                      <span className="flex gap-1">
                        <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
                      </span>
                      <span className="text-xs font-bold text-slate-500">Searching GraphRAG knowledge base...</span>
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
          <div className="p-3 sm:p-4 border-t border-slate-200/80 bg-white">
            <div className="max-w-4xl mx-auto bg-slate-50 border border-slate-200 rounded-2xl p-3 sm:p-3.5 focus-within:border-[#111111] focus-within:ring-2 focus-within:ring-slate-200 transition-all">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                rows={1}
                className="w-full bg-transparent resize-none outline-none text-slate-900 font-medium text-sm sm:text-base placeholder-slate-400"
                placeholder="Ask follow-up question..."
                style={{ minHeight: '28px', maxHeight: '160px' }}
              />
              <div className="flex items-center justify-between mt-2.5 pt-2 border-t border-slate-200">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="flex items-center gap-1.5 text-xs font-bold text-slate-800 hover:text-black bg-white px-2.5 py-1.5 rounded-xl border border-slate-200 shadow-sm transition-colors"
                  >
                    <Paperclip size={13} />
                    <span>Attach PDF</span>
                  </button>
                  <button
                    onClick={toggleVoiceInput}
                    className={`p-2 rounded-xl transition-colors ${
                      isListening ? 'text-rose-600 bg-rose-50 animate-pulse' : 'text-slate-500 hover:text-slate-900 hover:bg-slate-200/60'
                    }`}
                    title="Voice input"
                  >
                    <Mic size={16} />
                  </button>
                </div>
                <button
                  onClick={() => handleSend()}
                  disabled={!input.trim() || isStreaming}
                  className="p-2.5 rounded-xl bg-[#111111] hover:bg-[#27272a] text-white disabled:opacity-30 transition-all shadow-md"
                >
                  <Send size={15} />
                </button>
              </div>
            </div>
          </div>
        )}

      </main>

      {/* ─── RIGHT SIDEBAR (Easlo Minimal Tone) ────────────────────────────────── */}
      <aside
        className={`fixed lg:static inset-y-0 right-0 z-50 w-80 bg-white border-l border-slate-200/80 p-5 flex flex-col justify-between overflow-y-auto shadow-2xl lg:shadow-sm transition-transform duration-300 ${
          mobileRightOpen ? 'translate-x-0' : 'translate-x-full lg:translate-x-0'
        }`}
      >
        <div className="space-y-4">
          <div className="flex items-center justify-between mb-1 pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2.5">
              <Sparkles size={18} className="text-[#111111]" />
              <h3 className="text-xs font-extrabold uppercase text-slate-400 tracking-wider">
                Study Tools & Graph
              </h3>
            </div>
            <button
              onClick={() => setMobileRightOpen(false)}
              className="lg:hidden text-slate-400 hover:text-slate-700 p-1.5 rounded-xl hover:bg-slate-100"
            >
              <X size={18} />
            </button>
          </div>

          {/* 1. Flashcards Card */}
          <motion.div
            whileHover={{ scale: 1.02 }}
            onClick={() => { setShowFlashcards(true); setMobileRightOpen(false); }}
            className="p-4 sm:p-5 rounded-3xl bg-slate-50/80 border border-slate-200/80 hover:border-slate-400 shadow-sm hover:shadow-md transition-all cursor-pointer group relative overflow-hidden"
          >
            <div className="w-11 h-11 sm:w-12 sm:h-12 rounded-2xl bg-[#111111] text-white flex items-center justify-center mb-3 shadow-md group-hover:scale-110 transition-transform">
              <BookOpen size={22} />
            </div>
            <h4 className="text-base font-extrabold text-slate-900 group-hover:text-black transition-colors">
              Flashcards Deck
            </h4>
            <p className="text-xs text-slate-600 mt-1.5 leading-relaxed font-medium">
              Review AI study cards generated strictly from your uploaded PDF text.
            </p>
            <div className="mt-4 flex items-center gap-1.5 text-xs font-extrabold text-[#111111] group-hover:translate-x-1 transition-transform">
              <span>Study Flashcards</span> <ArrowRight size={14} />
            </div>
          </motion.div>

          {/* 2. Play Quiz Card */}
          <motion.div
            whileHover={{ scale: 1.02 }}
            onClick={() => { setShowQuizGame(true); setMobileRightOpen(false); }}
            className="p-4 sm:p-5 rounded-3xl bg-amber-50/60 border border-amber-200/80 shadow-sm hover:shadow-md transition-all cursor-pointer group relative overflow-hidden"
          >
            <div className="w-11 h-11 sm:w-12 sm:h-12 rounded-2xl bg-[#111111] text-white flex items-center justify-center mb-3 shadow-md group-hover:scale-110 transition-transform">
              <Trophy size={22} className="text-amber-400" />
            </div>
            <h4 className="text-base font-extrabold text-slate-900 group-hover:text-[#111111] transition-colors">
              Play Gamified Quiz
            </h4>
            <p className="text-xs text-slate-600 mt-1.5 leading-relaxed font-medium">
              Test your understanding with PDF-based quizzes, score XP & master topics.
            </p>
            <div className="mt-4 flex items-center gap-1.5 text-xs font-extrabold text-[#111111] group-hover:translate-x-1 transition-transform">
              <span>Start Quiz Game</span> <ArrowRight size={14} />
            </div>
          </motion.div>

          {/* 3. Knowledge Graph Card */}
          <motion.div
            whileHover={{ scale: 1.02 }}
            onClick={() => { setShowGraphPanel(true); setMobileRightOpen(false); }}
            className="p-4 sm:p-5 rounded-3xl bg-slate-50/80 border border-slate-200/80 hover:border-slate-400 shadow-sm hover:shadow-md transition-all cursor-pointer group relative overflow-hidden"
          >
            <div className="w-11 h-11 sm:w-12 sm:h-12 rounded-2xl bg-[#111111] text-white flex items-center justify-center mb-3 shadow-md group-hover:scale-110 transition-transform">
              <Network size={22} />
            </div>
            <div className="flex items-center justify-between">
              <h4 className="text-base font-extrabold text-slate-900 group-hover:text-black transition-colors">
                Knowledge Graph
              </h4>
              {liveGraphContext.entities.length > 0 && (
                <span className="text-[10px] font-extrabold bg-slate-200 text-slate-800 px-2 py-0.5 rounded-full">
                  {liveGraphContext.entities.length} Nodes
                </span>
              )}
            </div>
            <p className="text-xs text-slate-600 mt-1.5 leading-relaxed font-medium">
              Explore 3D visual entity maps and document relationship connections.
            </p>
            <div className="mt-4 flex items-center gap-1.5 text-xs font-extrabold text-[#111111] group-hover:translate-x-1 transition-transform">
              <span>Explore 3D Graph</span> <ArrowRight size={14} />
            </div>
          </motion.div>

          {/* 4. MCP Tools Card */}
          <motion.div
            whileHover={{ scale: 1.02 }}
            onClick={() => { setShowMcpDrawer(true); setMobileRightOpen(false); }}
            className="p-4 sm:p-5 rounded-3xl bg-emerald-50/60 border border-emerald-200/80 shadow-sm hover:shadow-md transition-all cursor-pointer group relative overflow-hidden"
          >
            <div className="w-11 h-11 sm:w-12 sm:h-12 rounded-2xl bg-[#111111] text-white flex items-center justify-center mb-3 shadow-md group-hover:scale-110 transition-transform">
              <Cpu size={22} className="text-emerald-400" />
            </div>
            <h4 className="text-base font-extrabold text-slate-900 group-hover:text-black transition-colors">
              MCP Tool Extensions
            </h4>
            <p className="text-xs text-slate-600 mt-1.5 leading-relaxed font-medium">
              Manage external Model Context Protocol sandboxes & math solvers.
            </p>
            <div className="mt-4 flex items-center gap-1.5 text-xs font-extrabold text-[#111111] group-hover:translate-x-1 transition-transform">
              <span>Configure MCP Tools</span> <ArrowRight size={14} />
            </div>
          </motion.div>
        </div>

        <div className="pt-4 border-t border-slate-100 text-center">
          <p className="text-xs font-bold text-slate-400">
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

      <McpDrawer
        isOpen={showMcpDrawer}
        onClose={() => setShowMcpDrawer(false)}
      />

      {activeSession && (
        <>
          <GamifiedQuizGame
            sessionId={activeSession.id}
            isOpen={showQuizGame}
            onClose={() => setShowQuizGame(false)}
          />
          <FlashcardsOverlay
            sessionId={activeSession.id}
            isOpen={showFlashcards}
            onClose={() => setShowFlashcards(false)}
          />
        </>
      )}

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
          ? 'bg-[#111111] text-white font-bold shadow-sm'
          : 'text-slate-700 hover:bg-slate-200/60 hover:text-slate-900 font-medium'
      }`}
    >
      <div className="flex items-center gap-2.5 min-w-0 pr-1">
        <MessageSquare size={15} className={isActive ? 'text-white' : 'text-slate-400'} />
        <span className="truncate text-xs">{session.session_title}</span>
      </div>
      <button
        onClick={onDelete}
        className={`opacity-0 group-hover:opacity-100 p-1 rounded-lg transition-all ${
          isActive ? 'text-slate-300 hover:text-rose-400 hover:bg-slate-800' : 'text-slate-400 hover:text-rose-600 hover:bg-slate-200/80'
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
      className="p-4 sm:p-5 rounded-3xl bg-[#f8fafc] border border-slate-200/80 hover:border-slate-400 hover:bg-slate-100/50 transition-all cursor-pointer text-left group shadow-sm hover:shadow-md"
    >
      <div className="mb-2 sm:mb-3">{icon}</div>
      <h3 className="font-extrabold text-sm sm:text-base text-slate-900 group-hover:text-black mb-1">{title}</h3>
      <p className="text-xs text-slate-500 leading-relaxed font-medium">{description}</p>
    </div>
  )
}
