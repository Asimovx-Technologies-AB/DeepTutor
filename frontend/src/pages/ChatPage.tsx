import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Send, Paperclip, Plus, MessageSquare,
  Bot, Sparkles, BookOpen, Brain, X, Network,
  CheckCircle, AlertCircle, Loader2, FileText, Trophy
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
    setSessions, setActiveSession, setMessages, addMessage,
    setStreaming, appendStreamToken, clearStreamingContent, commitStreamedMessage,
  } = useChatStore()

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
      <aside className="w-56 flex-shrink-0 glass border-r border-[rgba(99,102,241,0.12)] flex flex-col overflow-hidden">
        <div className="p-3 border-b border-[rgba(99,102,241,0.12)]">
          <button onClick={() => setShowNewSession(true)}
            className="btn-primary w-full flex items-center justify-center gap-2 text-xs py-2">
            <Plus size={14} /> New Chat
          </button>
        </div>

        <AnimatePresence>
          {showNewSession && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
              <div className="p-3 border-b border-[rgba(99,102,241,0.12)] space-y-2">
                <input type="text" value={newSessionTitle} onChange={(e) => setNewSessionTitle(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && createNewSession()}
                  className="input-base text-xs py-2" placeholder="Session title..." autoFocus />
                <div className="flex gap-2">
                  <button onClick={createNewSession} className="btn-primary flex-1 py-1.5 text-xs">Create</button>
                  <button onClick={() => setShowNewSession(false)} className="btn-ghost py-1.5 text-xs px-2">
                    <X size={13} />
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          <p className="text-[10px] font-semibold text-slate-600 uppercase tracking-widest px-2 py-1">Recent Chats</p>
          {sessions.length === 0 && <p className="text-xs text-slate-600 px-2 py-3">No sessions yet</p>}
          {sessions.map((session) => (
            <button key={session.id} onClick={() => navigate(`/chat/${session.id}`)}
              className={`w-full text-left p-2.5 rounded-xl text-xs transition-all ${
                activeSession?.id === session.id
                  ? 'bg-indigo-500/15 text-indigo-300 border border-indigo-500/20'
                  : 'text-slate-400 hover:bg-white/5 hover:text-slate-300'
              }`}>
              <div className="flex items-center gap-2">
                <MessageSquare size={12} className="flex-shrink-0" />
                <span className="truncate font-medium">{session.session_title}</span>
              </div>
            </button>
          ))}
        </div>
      </aside>

      {/* Main chat area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Chat header */}
        <div className="flex-shrink-0 px-5 py-3 glass border-b border-[rgba(99,102,241,0.12)] flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center animate-pulse-glow">
            <Bot size={15} className="text-white" />
          </div>
          <div className="flex-1">
            <p className="font-semibold text-slate-200 text-sm">{activeSession?.session_title ?? 'AI Tutor'}</p>
            <div className="flex items-center gap-2">
              <div className={`w-1.5 h-1.5 rounded-full ${isStreaming ? 'bg-indigo-400 animate-pulse' : 'bg-emerald-400'}`} />
              <span className="text-[11px] text-slate-500">
                {isStreaming ? 'Thinking with GraphRAG...' : 'GraphRAG + Local LLM'}
              </span>
            </div>
          </div>

          {/* Study Actions */}
          {activeSession && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowFlashcards(true)}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-xl border border-[rgba(99,102,241,0.15)] text-slate-500 hover:text-indigo-500 hover:border-indigo-200 transition-all bg-white/40"
                title="Review Flashcards generated from documents"
              >
                <BookOpen size={13} className="text-indigo-500" />
                <span className="hidden md:inline">Flashcards</span>
              </button>

              <button
                onClick={() => setShowQuizGame(true)}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-xl border border-[rgba(99,102,241,0.15)] text-slate-500 hover:text-yellow-600 hover:border-yellow-200 transition-all bg-white/40"
                title="Play Quiz game generated from documents"
              >
                <Trophy size={13} className="text-yellow-500" />
                <span className="hidden md:inline">Play Quiz</span>
              </button>
            </div>
          )}

          {/* Graph toggle button */}
          <button
            onClick={() => setShowGraphPanel(!showGraphPanel)}
            className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-xl border transition-all ${
              showGraphPanel
                ? 'bg-indigo-500/20 border-indigo-500/30 text-indigo-300'
                : 'border-[rgba(99,102,241,0.15)] text-slate-500 hover:text-slate-300 hover:border-[rgba(99,102,241,0.3)]'
            }`}
          >
            <Network size={13} />
            <span className="hidden sm:inline">Knowledge Graph</span>
            {liveGraphContext.entities.length > 0 && (
              <span className="w-4 h-4 rounded-full bg-indigo-500 text-white text-[9px] flex items-center justify-center font-bold">
                {liveGraphContext.entities.length}
              </span>
            )}
          </button>
        </div>

        {/* Upload status bars */}
        {uploadStatuses.length > 0 && (
          <div className="px-4 py-2 space-y-1.5 border-b border-[rgba(99,102,241,0.1)]">
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
          <div className="flex-1 overflow-y-auto p-5 space-y-6">
            {allMessages.length === 0 && !activeSession && (
              <div className="flex flex-col items-center justify-center h-full text-center max-w-lg mx-auto">
                <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-indigo-500/20 to-violet-500/20 border border-indigo-500/20 flex items-center justify-center mb-5 animate-float">
                  <Brain size={36} className="text-indigo-400" />
                </div>
                <h2 className="text-2xl font-bold text-white mb-2">GraphRAG AI Tutor</h2>
                <p className="text-slate-400 text-sm mb-3 leading-relaxed">
                  Powered by a <span className="text-indigo-400 font-semibold">local knowledge graph</span> + vector search + Ollama LLM.
                  Upload PDFs to build a knowledge graph, then ask questions with graph-aware context.
                </p>
                <div className="glass-card p-3 mb-5 text-xs text-slate-400 space-y-1 text-left w-full">
                  <p className="font-semibold text-indigo-400 mb-1.5">How GraphRAG works:</p>
                  <p>1. 📄 Upload a PDF → chunks extracted</p>
                  <p>2. 🧠 LLM extracts entities & relationships → knowledge graph built</p>
                  <p>3. 🔍 Your question → vector + graph search → rich context</p>
                  <p>4. 💬 Ollama LLM answers with graph-aware context + citations</p>
                </div>
                <p className="text-xs text-slate-600">👆 Create a new chat session to begin →</p>
              </div>
            )}

            {allMessages.length === 0 && activeSession && (
              <div className="flex flex-col items-center justify-center h-full text-center max-w-lg mx-auto">
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500/20 to-violet-500/20 border border-indigo-500/20 flex items-center justify-center mb-4 animate-float">
                  <MessageSquare size={28} className="text-indigo-400" />
                </div>
                <p className="text-slate-300 font-semibold mb-1">Start the conversation</p>
                <p className="text-slate-500 text-sm mb-4">Upload a PDF first for GraphRAG, or ask any question directly</p>
                <div className="grid grid-cols-2 gap-2 w-full">
                  {WELCOME_PROMPTS.map((prompt) => (
                    <button key={prompt} onClick={() => handleSend(prompt)}
                      className="glass-card p-3 text-left text-xs text-slate-400 hover:text-slate-200 transition-colors">
                      <BookOpen size={11} className="text-indigo-400 mb-1.5" />
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
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center flex-shrink-0">
                  <Bot size={14} className="text-white" />
                </div>
                <div className="glass border border-[rgba(99,102,241,0.15)] rounded-2xl rounded-tl-sm px-4 py-3">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="flex gap-1.5">
                      <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
                    </span>
                    <span className="text-[11px] text-slate-600">Searching knowledge graph...</span>
                  </div>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

        </div>

        {/* Input area */}
        <div className="flex-shrink-0 p-4">
          <div className="glass border border-[rgba(99,102,241,0.2)] rounded-2xl p-3 focus-within:border-[rgba(99,102,241,0.4)] transition-colors">
            <textarea
              ref={textareaRef}
              id="chat-input"
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              disabled={isStreaming || !activeSession}
              rows={1}
              className="w-full bg-transparent resize-none outline-none text-slate-200 text-sm placeholder-slate-600 leading-relaxed"
              placeholder={
                activeSession
                  ? 'Ask anything — GraphRAG will search your documents and knowledge graph...'
                  : 'Create a chat session first →'
              }
              style={{ minHeight: '24px', maxHeight: '160px' }}
            />
            <div className="flex items-center justify-between mt-2 pt-2 border-t border-[rgba(99,102,241,0.1)]">
              <div className="flex items-center gap-2">
                <input ref={fileInputRef} type="file" accept=".pdf,.txt,.md"
                  className="hidden" onChange={handleFileUpload} id="file-upload" />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={!activeSession || uploadingFile}
                  className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border border-[rgba(99,102,241,0.2)] text-slate-500 hover:text-slate-300 hover:border-[rgba(99,102,241,0.4)] transition-all disabled:opacity-40"
                  title="Upload PDF for GraphRAG indexing"
                >
                  {uploadingFile ? (
                    <Loader2 size={13} className="animate-spin text-indigo-400" />
                  ) : (
                    <FileText size={13} />
                  )}
                  <span>Upload for GraphRAG</span>
                </button>
              </div>

              <div className="flex items-center gap-2">
                {isStreaming && liveSources.length > 0 && (
                  <span className="text-[11px] text-indigo-400 flex items-center gap-1">
                    <Sparkles size={11} /> {liveSources.length} sources found
                  </span>
                )}
                <button
                  onClick={() => handleSend()}
                  disabled={!input.trim() || isStreaming || !activeSession}
                  id="send-message"
                  className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white shadow-lg transition-all hover:shadow-indigo-500/30 disabled:opacity-40 disabled:cursor-not-allowed hover:scale-105 active:scale-95"
                >
                  {isStreaming
                    ? <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    : <Send size={14} />}
                </button>
              </div>
            </div>
          </div>
          <p className="text-center text-[11px] text-slate-700 mt-2">
            🧠 GraphRAG · 📊 Knowledge Graph · 🦙 Ollama Local LLM · 🔍 Vector Search
          </p>
        </div>
      </div>

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
