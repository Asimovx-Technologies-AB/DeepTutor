import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Send, Paperclip, Plus, MessageSquare,
  Bot, Sparkles, BookOpen, Brain, X, Network,
  CheckCircle, AlertCircle, Loader2, FileText, Trophy, Trash2,
  Mic, MicOff
} from 'lucide-react'
import { useChatStore } from '../stores/chatStore'
import { useAuthStore } from '../stores/authStore'
import { chatApi, documentsApi } from '../services/api'
import ChatMessage from '../components/ChatMessage'
import GraphContextPanel from '../components/GraphContextPanel'
import GamifiedQuizGame from '../components/GamifiedQuizGame'
import FlashcardsOverlay from '../components/FlashcardsOverlay'
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

const WELCOME_PROMPTS = [
  'Explain the concept of entropy in simple terms',
  'What are Newton\'s three laws of motion?',
  'How does machine learning work?',
  'Explain quantum entanglement',
]

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
      className={`flex items-center gap-2 text-xs px-3 py-2 rounded-xl border ${
        isDone ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' :
        isError ? 'bg-red-500/10 border-red-500/20 text-red-400' :
        'bg-indigo-500/10 border-indigo-500/20 text-indigo-300'
      }`}
    >
      {isDone ? <CheckCircle size={13} /> :
       isError ? <AlertCircle size={13} /> :
       <Loader2 size={13} className="animate-spin" />}
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
  const { token } = useAuthStore()

  const {
    sessions, activeSession, messages, isStreaming, streamingContent,
    setSessions, setActiveSession, setMessages, addMessage, removeSession,
    setStreaming, appendStreamToken, clearStreamingContent, commitStreamedMessage,
  } = useChatStore()

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

  const [input, setInput] = useState('')
  const [newSessionTitle, setNewSessionTitle] = useState('')
  const [showNewSession, setShowNewSession] = useState(false)
  const [uploadingFile, setUploadingFile] = useState(false)
  const [uploadStatuses, setUploadStatuses] = useState<string[]>([])
  const [showGraphPanel, setShowGraphPanel] = useState(false)
  const [showQuizGame, setShowQuizGame] = useState(false)
  const [showFlashcards, setShowFlashcards] = useState(false)
  const [liveGraphContext, setLiveGraphContext] = useState<GraphContextData>({ entities: [], relationships: [] })
  const [liveSources, setLiveSources] = useState<Source[]>([])
  const [extMessages, setExtMessages] = useState<ExtendedMessage[]>([])

  // Voice Input (Speech-to-Text) State
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

      recognition.onstart = () => {
        setIsListening(true)
      }

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

      recognition.onerror = (event: any) => {
        console.error('Speech recognition error:', event.error)
        setIsListening(false)
      }

      recognition.onend = () => {
        setIsListening(false)
      }

      recognitionRef.current = recognition
      recognition.start()
    } catch (e) {
      console.error(e)
      setIsListening(false)
    }
  }

  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Fetch sessions — always fresh on mount so history appears immediately after login
  const { refetch: refetchSessions } = useQuery({
    queryKey: ['chat-sessions'],
    queryFn: async () => {
      const res = await chatApi.sessions()
      setSessions(res.data)
      // If we're on a specific session URL, restore active session from fresh data
      if (sessionId) {
        const found = res.data.find((s: any) => s.id === sessionId)
        if (found) setActiveSession(found)
      }
      return res.data
    },
    staleTime: 0, // Always re-fetch on mount so login → history is immediate
  })

  // Load session messages whenever sessionId changes
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
      // Restore active session from already-populated store (handles cached case)
      const session = sessions.find((s) => s.id === sessionId)
      if (session) setActiveSession(session)
    })
  }, [sessionId])

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [extMessages, streamingContent])

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`
  }

  const handleSend = useCallback(async (text?: string) => {
    const content = (text ?? input).trim()
    if (!content || isStreaming || !activeSession) return

    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'

    // Add user message
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

    // Close previous EventSource
    if (eventSourceRef.current) eventSourceRef.current.close()

    const url = `/api/chat/sessions/${activeSession.id}/message/stream?content=${encodeURIComponent(content)}&token=${token}`
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
          // Show graph panel when we have graph context
          if (showGraphPanel) setShowGraphPanel(true)

        } else if (evt.type === 'graph_context') {
          accGraph = evt.data
          setLiveGraphContext(evt.data)
          if (evt.data.entities?.length > 0) setShowGraphPanel(true)

        } else if (evt.type === 'done') {
          es.close()
          // Commit the streaming message to extMessages
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
      } catch { /* ignore parse errors */ }
    }

    es.onerror = () => {
      es.close()
      // Fallback message
      const fallback: ExtendedMessage = {
        id: Date.now().toString() + '_fallback',
        role: 'assistant',
        content: accContent || '⚠️ **Backend not connected.** Start the FastAPI backend to use GraphRAG:\n```bash\ncd backend\npip install -r requirements.txt\nuvicorn app.main:app --reload\n```',
        created_at: new Date().toISOString(),
      }
      setExtMessages((prev) => [...prev, fallback])
      clearStreamingContent()
      setStreaming(false)
    }
  }, [input, isStreaming, activeSession, token, showGraphPanel])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const createNewSession = async () => {
    const title = newSessionTitle.trim() || 'New Chat Session'
    try {
      const res = await chatApi.createSession('', title)
      await refetchSessions()
      navigate(`/chat/${res.data.id}`)
      setActiveSession(res.data)
      setExtMessages([])
      setShowNewSession(false)
      setNewSessionTitle('')
    } catch { /* noop */ }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !activeSession) return
    setUploadingFile(true)

    try {
      const topicId = activeSession.topic_id || 'general'
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
        // Add status tracker
        setUploadStatuses((prev) => [...prev, data.id])
        // Add info message in chat
        const infoMsg: ExtendedMessage = {
          id: Date.now().toString(),
          role: 'assistant',
          content: `📄 **${file.name}** uploaded successfully!\n\n🧠 **GraphRAG indexing started** — I'm extracting entities and building the knowledge graph from your document. This may take 1-3 minutes depending on the document size.\n\nYou can start asking questions right away — I'll use whatever has been indexed so far.`,
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

  // Build the streaming message overlay
  const streamingMsg: ExtendedMessage | null =
    isStreaming && streamingContent
      ? { id: 'streaming', role: 'assistant', content: streamingContent, created_at: '' }
      : null

  const allMessages = streamingMsg ? [...extMessages, streamingMsg] : extMessages

  return (
    <div className="flex h-full overflow-hidden">
      {/* Sessions sidebar */}
      <aside className="w-64 flex-shrink-0 glass border-r border-[rgba(99,102,241,0.12)] flex flex-col overflow-hidden">
        <div className="p-4 border-b border-[rgba(99,102,241,0.12)]">
          <button onClick={() => setShowNewSession(true)}
            className="btn-primary w-full flex items-center justify-center gap-2 text-sm font-bold py-2.5 shadow-md hover:scale-[1.02]">
            <Plus size={16} /> New Chat
          </button>
        </div>

        <AnimatePresence>
          {showNewSession && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
              <div className="p-3 border-b border-[rgba(99,102,241,0.12)] space-y-2">
                <input type="text" value={newSessionTitle} onChange={(e) => setNewSessionTitle(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && createNewSession()}
                  className="input-base text-sm py-2.5" placeholder="Session title..." autoFocus />
                <div className="flex gap-2">
                  <button onClick={createNewSession} className="btn-primary flex-1 py-2 text-xs font-bold">Create</button>
                  <button onClick={() => setShowNewSession(false)} className="btn-ghost py-2 text-xs px-3">
                    <X size={15} />
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
          <p className="text-xs font-extrabold text-slate-500 uppercase tracking-widest px-2 py-1">Recent Chats</p>
          {sessions.length === 0 && <p className="text-xs font-semibold text-slate-500 px-2 py-3">No sessions yet</p>}
          {sessions.map((session) => (
            <div
              key={session.id}
              onClick={() => navigate(`/chat/${session.id}`)}
              className={`group w-full flex items-center justify-between p-3 rounded-2xl text-sm transition-all cursor-pointer ${
                activeSession?.id === session.id
                  ? 'bg-indigo-600 text-white font-bold shadow-md shadow-indigo-600/20'
                  : 'text-slate-700 hover:bg-indigo-50/80 hover:text-indigo-600 font-semibold'
              }`}
            >
              <div className="flex items-center gap-2.5 min-w-0 pr-1">
                <MessageSquare size={16} className="flex-shrink-0" />
                <span className="truncate">{session.session_title}</span>
              </div>

              <button
                onClick={(e) => handleDeleteSession(e, session.id)}
                className="opacity-0 group-hover:opacity-100 p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-xl transition-all flex-shrink-0"
                title="Delete session"
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      </aside>

      {/* Main chat area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Chat header */}
        <div className="flex-shrink-0 px-6 py-3.5 glass border-b border-[rgba(99,102,241,0.12)] flex items-center gap-4">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center animate-pulse-glow shadow-md">
            <Bot size={18} className="text-white" />
          </div>
          <div className="flex-1">
            <p className="font-extrabold text-slate-900 text-base">{activeSession?.session_title ?? 'AI Tutor'}</p>
            <div className="flex items-center gap-2 mt-0.5">
              <div className={`w-2 h-2 rounded-full ${isStreaming ? 'bg-indigo-500 animate-pulse' : 'bg-emerald-500'}`} />
              <span className="text-xs font-semibold text-slate-500">
                {isStreaming ? 'Thinking with GraphRAG...' : 'GraphRAG + Local LLM'}
              </span>
            </div>
          </div>
        </div>

        {/* Upload status bars */}
        {uploadStatuses.length > 0 && (
          <div className="px-5 py-2.5 space-y-2 border-b border-[rgba(99,102,241,0.1)]">
            <AnimatePresence>
              {uploadStatuses.map((docId) => (
                <UploadStatus
                  key={docId}
                  docId={docId}
                  onDone={(stats) => {
                    setUploadStatuses((prev) => prev.filter((id) => id !== docId))
                  }}
                />
              ))}
            </AnimatePresence>
          </div>
        )}

        {/* Content area: messages + optional graph panel */}
        <div className="flex-1 flex overflow-hidden">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {allMessages.length === 0 && !activeSession && (
              <div className="flex flex-col items-center justify-center h-full text-center max-w-xl mx-auto">
                <div className="w-24 h-24 rounded-3xl bg-gradient-to-br from-indigo-500/20 to-violet-500/20 border border-indigo-500/30 flex items-center justify-center mb-6 animate-float shadow-xl shadow-indigo-500/10">
                  <Brain size={42} className="text-indigo-600" />
                </div>
                <h2 className="text-3xl font-black text-slate-900 mb-3">GraphRAG AI Tutor</h2>
                <p className="text-slate-600 text-base mb-4 leading-relaxed font-medium">
                  Powered by a <span className="text-indigo-600 font-bold">local knowledge graph</span> + vector search + Ollama LLM.
                  Upload PDFs to build a knowledge graph, then ask questions with graph-aware context.
                </p>
                <div className="glass-card p-4 mb-6 text-sm text-slate-700 space-y-2 text-left w-full border border-indigo-100 shadow-sm">
                  <p className="font-extrabold text-indigo-700 mb-2">How GraphRAG works:</p>
                  <p>1. 📄 Upload a PDF → chunks extracted</p>
                  <p>2. 🧠 LLM extracts entities & relationships → knowledge graph built</p>
                  <p>3. 🔍 Your question → vector + graph search → rich context</p>
                  <p>4. 💬 Ollama LLM answers with graph-aware context + citations</p>
                </div>
                <p className="text-sm font-bold text-slate-500">👈 Create a new chat session to begin</p>
              </div>
            )}

            {allMessages.length === 0 && activeSession && (
              <div className="flex flex-col items-center justify-center h-full text-center max-w-xl mx-auto">
                <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-indigo-500/20 to-violet-500/20 border border-indigo-500/30 flex items-center justify-center mb-5 animate-float shadow-lg">
                  <MessageSquare size={34} className="text-indigo-600" />
                </div>
                <p className="text-slate-900 font-black text-xl mb-1">Start the conversation</p>
                <p className="text-slate-500 text-base mb-6">Upload a PDF first for GraphRAG, or ask any question directly</p>
                <div className="grid grid-cols-2 gap-3 w-full">
                  {WELCOME_PROMPTS.map((prompt) => (
                    <button key={prompt} onClick={() => handleSend(prompt)}
                      className="glass-card p-4 text-left text-sm font-bold text-slate-700 hover:text-indigo-600 hover:border-indigo-200 hover:scale-[1.02] transition-all shadow-sm">
                      <BookOpen size={14} className="text-indigo-500 mb-2" />
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            )}

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
              <div className="flex gap-4">
                <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center flex-shrink-0 shadow-md">
                  <Bot size={18} className="text-white" />
                </div>
                <div className="glass border border-[rgba(99,102,241,0.2)] rounded-3xl rounded-tl-sm px-5 py-4">
                  <div className="flex items-center gap-2.5">
                    <span className="flex gap-1.5">
                      <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
                    </span>
                    <span className="text-xs font-bold text-slate-600">Searching knowledge graph...</span>
                  </div>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

        </div>

        {/* Input area */}
        <div className="flex-shrink-0 p-5">
          <div className="glass border border-slate-200 rounded-3xl p-4 focus-within:border-indigo-400 focus-within:ring-4 focus-within:ring-indigo-100 transition-all shadow-md">
            <textarea
              ref={textareaRef}
              id="chat-input"
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              disabled={isStreaming || !activeSession}
              rows={1}
              className="w-full bg-transparent resize-none outline-none text-slate-900 font-medium text-base placeholder-slate-400 leading-relaxed"
              placeholder={
                activeSession
                  ? 'Ask anything — GraphRAG will search your documents and knowledge graph...'
                  : 'Create a chat session first →'
              }
              style={{ minHeight: '30px', maxHeight: '180px' }}
            />
            <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-100">
              <div className="flex items-center gap-2">
                <input ref={fileInputRef} type="file" accept=".pdf,.txt,.md"
                  className="hidden" onChange={handleFileUpload} id="file-upload" />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={!activeSession || uploadingFile}
                  className="flex items-center gap-2 text-xs font-extrabold px-3.5 py-2 rounded-xl border border-slate-200 text-slate-700 bg-slate-50 hover:bg-indigo-50 hover:text-indigo-600 hover:border-indigo-200 transition-all disabled:opacity-40"
                  title="Upload PDF for GraphRAG indexing"
                >
                  {uploadingFile ? (
                    <Loader2 size={15} className="animate-spin text-indigo-600" />
                  ) : (
                    <FileText size={15} />
                  )}
                  <span>Upload for GraphRAG</span>
                </button>
              </div>

              <div className="flex items-center gap-3">
                {isListening && (
                  <span className="text-xs font-bold text-rose-600 bg-rose-50 border border-rose-200 px-3 py-1.5 rounded-xl flex items-center gap-2 animate-pulse">
                    <Mic size={14} className="animate-bounce" /> Listening... Speak now
                  </span>
                )}
                {isStreaming && liveSources.length > 0 && (
                  <span className="text-xs font-bold text-indigo-600 flex items-center gap-1">
                    <Sparkles size={13} /> {liveSources.length} sources found
                  </span>
                )}

                {/* Voice Input Microphone Button */}
                <button
                  type="button"
                  onClick={toggleVoiceInput}
                  disabled={isStreaming || !activeSession}
                  className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all shadow-sm ${
                    isListening
                      ? 'bg-rose-600 text-white animate-pulse ring-4 ring-rose-200 shadow-rose-500/30 scale-105'
                      : 'bg-slate-100 text-slate-700 hover:bg-indigo-50 hover:text-indigo-600 border border-slate-200 hover:border-indigo-200'
                  } disabled:opacity-40 disabled:cursor-not-allowed`}
                  title={isListening ? 'Stop Recording' : 'Voice Input (Click & Speak)'}
                >
                  {isListening ? <MicOff size={18} /> : <Mic size={18} />}
                </button>

                <button
                  onClick={() => handleSend()}
                  disabled={!input.trim() || isStreaming || !activeSession}
                  id="send-message"
                  className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-600 to-violet-600 flex items-center justify-center text-white shadow-lg transition-all hover:shadow-indigo-500/30 disabled:opacity-40 disabled:cursor-not-allowed hover:scale-105 active:scale-95"
                >
                  {isStreaming
                    ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    : <Send size={16} />}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ─── RIGHT ACTION SIDEBAR (BIG FEATURE CARDS) ─── */}
      <aside className="w-80 flex-shrink-0 bg-white border-l border-slate-200/80 p-5 flex flex-col justify-between overflow-y-auto hidden lg:flex shadow-sm">
        <div className="space-y-4">
          <div className="flex items-center gap-2 mb-1 pb-3 border-b border-slate-100">
            <Sparkles size={16} className="text-indigo-600" />
            <h3 className="text-xs font-black uppercase text-slate-400 tracking-wider">
              Study Tools & Graph
            </h3>
          </div>

          {/* 1. Flashcards Card */}
          <motion.div
            whileHover={{ scale: 1.02 }}
            onClick={() => setShowFlashcards(true)}
            className="p-5 rounded-2xl bg-gradient-to-br from-indigo-50/80 via-indigo-50/30 to-white border border-indigo-100 shadow-sm hover:shadow-md transition-all cursor-pointer group relative overflow-hidden"
          >
            <div className="w-12 h-12 rounded-2xl bg-[#111111] text-white flex items-center justify-center mb-3 shadow-md group-hover:scale-110 transition-transform">
              <BookOpen size={22} />
            </div>
            <h4 className="text-base font-black text-slate-900 group-hover:text-indigo-600 transition-colors">
              Flashcards Deck
            </h4>
            <p className="text-xs text-slate-600 mt-1 leading-relaxed font-medium">
              Review AI study cards generated strictly from your uploaded PDF text.
            </p>
            <div className="mt-4 flex items-center gap-1.5 text-xs font-extrabold text-[#111111] group-hover:translate-x-1 transition-transform">
              <span>Study Flashcards</span> →
            </div>
          </motion.div>

          {/* 2. Play Quiz Card */}
          <motion.div
            whileHover={{ scale: 1.02 }}
            onClick={() => setShowQuizGame(true)}
            className="p-5 rounded-2xl bg-gradient-to-br from-amber-50/80 via-amber-50/30 to-white border border-amber-200/80 shadow-sm hover:shadow-md transition-all cursor-pointer group relative overflow-hidden"
          >
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-amber-500 to-amber-600 text-white flex items-center justify-center mb-3 shadow-md group-hover:scale-110 transition-transform">
              <Trophy size={22} />
            </div>
            <h4 className="text-base font-black text-slate-900 group-hover:text-amber-600 transition-colors">
              Play Gamified Quiz
            </h4>
            <p className="text-xs text-slate-600 mt-1 leading-relaxed font-medium">
              Test your understanding with PDF-based quizzes, score XP & master topics.
            </p>
            <div className="mt-4 flex items-center gap-1.5 text-xs font-extrabold text-amber-700 group-hover:translate-x-1 transition-transform">
              <span>Start Quiz Game</span> →
            </div>
          </motion.div>

          {/* 3. Knowledge Graph Card */}
          <motion.div
            whileHover={{ scale: 1.02 }}
            onClick={() => setShowGraphPanel(true)}
            className="p-5 rounded-2xl bg-gradient-to-br from-violet-50/80 via-violet-50/30 to-white border border-violet-100 shadow-sm hover:shadow-md transition-all cursor-pointer group relative overflow-hidden"
          >
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-violet-600 to-indigo-600 text-white flex items-center justify-center mb-3 shadow-md group-hover:scale-110 transition-transform">
              <Network size={22} />
            </div>
            <div className="flex items-center justify-between">
              <h4 className="text-base font-black text-slate-900 group-hover:text-violet-600 transition-colors">
                Knowledge Graph
              </h4>
              {liveGraphContext.entities.length > 0 && (
                <span className="text-[10px] font-extrabold bg-violet-100 text-violet-700 px-2 py-0.5 rounded-full">
                  {liveGraphContext.entities.length} Nodes
                </span>
              )}
            </div>
            <p className="text-xs text-slate-600 mt-1 leading-relaxed font-medium">
              Explore 3D visual entity maps and document relationship connections.
            </p>
            <div className="mt-4 flex items-center gap-1.5 text-xs font-extrabold text-violet-700 group-hover:translate-x-1 transition-transform">
              <span>Explore 3D Graph</span> →
            </div>
          </motion.div>
        </div>

        <div className="pt-4 border-t border-slate-100 text-center">
          <p className="text-[11px] font-bold text-slate-400">
            🧠 GraphRAG + Ollama AI Tutor
          </p>
        </div>
      </aside>

      {/* Knowledge Graph Overlay */}
      <GraphContextPanel
        entities={liveGraphContext.entities}
        relationships={liveGraphContext.relationships}
        isOpen={showGraphPanel}
        onClose={() => setShowGraphPanel(false)}
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
