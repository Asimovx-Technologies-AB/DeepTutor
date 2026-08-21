import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Send, Sparkles, BookOpen, Brain,
  ArrowLeft, RefreshCw, Trophy, HelpCircle,
  Layers, CheckCircle2, ChevronRight, Plus, RotateCcw
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useSubjectStore } from '../stores/subjectStore'
import { chatApi, streamChatMessage } from '../services/api'
import ChatMessage from '../components/ChatMessage'
import type { Source } from '../components/SourceCard'

interface ExtendedMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
  sources?: Source[]
  graph_context?: any
}

// Subject-specific theme and prompts
const SUBJECT_CONFIGS: Record<string, {
  color: string
  accentBg: string
  borderColor: string
  title: string
  icon: string
  starters: string[]
}> = {
  'sslc-math': {
    color: '#D97706',
    accentBg: '#FFFBEB',
    borderColor: '#FDE68A',
    title: 'Class 10 Mathematics AI Tutor',
    icon: '📐',
    starters: [
      'Give me 5 minute cheatcode for Arithmetic Sequences.',
      'How to solve second degree equations by completing the square?',
      'What are the angle properties of cyclic quadrilaterals in circles?',
      'How do I calculate probability using geometric area method?',
    ],
  },
  'sslc-physics': {
    color: '#0284C7',
    accentBg: '#F0F9FF',
    borderColor: '#BAE6FD',
    title: 'Class 10 Physics AI Tutor',
    icon: '⚡',
    starters: [
      'Give me 5 minute cheatcode for Wave Motion & Light Refraction.',
      'Explain how convex lenses form images at different object distances.',
      'Why does light disperse into a spectrum when passing through a glass prism?',
      'Explain the Right-Hand Thumb Rule for magnetic fields around a conductor.',
    ],
  },
  'sslc-chemistry': {
    color: '#059669',
    accentBg: '#ECFDF5',
    borderColor: '#A7F3D0',
    title: 'Class 10 Chemistry AI Tutor',
    icon: '🧪',
    starters: [
      'Give me 5 minute cheatcode for Nomenclature of Organic Compounds.',
      'How do I write IUPAC names for branched alkanes and alkenes?',
      'Explain the subshell electron configuration (s, p, d, f) with examples.',
      'What are Boyle’s Law and Charles’s Law? Explain with mole concept.',
    ],
  },
}

export default function SubjectChatPage() {
  const { subjectId, topicId: routeTopicId } = useParams<{ subjectId: string; topicId?: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuthStore((s) => s.user)
  const subjects = useSubjectStore((s) => s.subjects)
  const getTopics = useSubjectStore((s) => s.getTopics)
  const recordActivity = useSubjectStore((s) => s.recordActivity)

  const activeSubjectId = subjectId || 'sslc-math'
  const subject = subjects.find((s) => s.id === activeSubjectId) || subjects[0]
  const topics = getTopics(activeSubjectId)
  const config = SUBJECT_CONFIGS[activeSubjectId] || SUBJECT_CONFIGS['sslc-math']

  const [selectedTopicId, setSelectedTopicId] = useState<string>(routeTopicId || '')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ExtendedMessage[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [loadingSession, setLoadingSession] = useState(true)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const selectedTopic = topics.find((t) => t.id === selectedTopicId)

  // Initialize or fetch stored session & messages for this subject from database
  useEffect(() => {
    let isMounted = true

    async function initSession() {
      setLoadingSession(true)
      const targetTopic = selectedTopicId || activeSubjectId
      const sessionTitle = selectedTopic ? `${subject.name}: ${selectedTopic.title}` : `${subject.name} Chat`
      
      try {
        // 1. Fetch user's existing sessions from database
        const res = await chatApi.sessions()
        const allSessions = res.data || []
        
        // Find existing session for this exact subject/topic
        const existingSession = allSessions.find(
          (s: any) => s.topic_id === targetTopic
        )

        let activeSid = ''

        if (existingSession) {
          activeSid = existingSession.id
          if (isMounted) {
            setSessionId(activeSid)
          }
          // 2. Load stored chat history from database
          const msgRes = await chatApi.messages(activeSid)
          const loadedMsgs: ExtendedMessage[] = (msgRes.data || []).map((m: any) => ({
            ...m,
            sources: m.metadata?.sources ?? [],
            graph_context: m.metadata?.graph_context ?? null,
          }))
          if (isMounted) {
            setMessages(loadedMsgs)
          }
        } else {
          // 3. Create a new persistent session in database
          const newSessRes = await chatApi.createSession(targetTopic, sessionTitle)
          activeSid = newSessRes.data.id
          if (isMounted) {
            setSessionId(activeSid)
            setMessages([])
          }
        }

        // If navigated with an initial prompt in state and session is fresh/empty
        const state = location.state as any
        if (state?.initialPrompt && isMounted) {
          sendMessage(state.initialPrompt, activeSid)
          navigate(location.pathname, { replace: true, state: {} })
        }
      } catch (err) {
        console.error('Failed to initialize subject chat session from database', err)
      } finally {
        if (isMounted) setLoadingSession(false)
      }
    }

    initSession()
    return () => { isMounted = false }
  }, [activeSubjectId, selectedTopicId])

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming])

  // Send message and persist to database
  const sendMessage = useCallback(async (contentToSend?: string, overrideSessionId?: string) => {
    const text = (contentToSend || input).trim()
    const activeSid = overrideSessionId || sessionId
    if (!text || !activeSid || isStreaming) return

    if (!contentToSend) setInput('')

    const userMessage: ExtendedMessage = {
      id: `usr_${Date.now()}`,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    }

    const assistantMsgId = `asst_${Date.now()}`
    const placeholderAssistant: ExtendedMessage = {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
      sources: [],
    }

    setMessages((prev) => [...prev, userMessage, placeholderAssistant])
    setIsStreaming(true)

    if (selectedTopicId) {
      recordActivity(activeSubjectId, selectedTopicId)
    }

    const token = useAuthStore.getState().token || localStorage.getItem('access_token') || ''

    await streamChatMessage({
      sessionId: activeSid,
      content: text,
      token,
      signal: abortControllerRef.current?.signal,
      onGraphContext: () => {},
      onSources: (sources) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantMsgId ? { ...m, sources } : m))
        )
      },
      onToken: (tokenChunk) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantMsgId ? { ...m, content: m.content + tokenChunk } : m))
        )
      },
      onDone: () => {
        setIsStreaming(false)
        abortControllerRef.current = null
      },
      onError: (err) => {
        setIsStreaming(false)
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, content: m.content + `\n\n*(Error connecting to AI: ${err})*` }
              : m
          )
        )
      },
    })
  }, [input, sessionId, isStreaming, selectedTopicId, activeSubjectId, recordActivity])

  // Reset/Clear conversation for this chapter in DB
  const handleResetChat = async () => {
    if (!sessionId || isStreaming) return
    const confirmed = window.confirm('Start a new conversation for this chapter? Previous messages will be cleared.')
    if (!confirmed) return

    try {
      await chatApi.deleteSession(sessionId)
      const targetTopic = selectedTopicId || activeSubjectId
      const sessionTitle = selectedTopic ? `${subject.name}: ${selectedTopic.title}` : `${subject.name} Chat`
      const newSess = await chatApi.createSession(targetTopic, sessionTitle)
      setSessionId(newSess.data.id)
      setMessages([])
    } catch (err) {
      console.error('Failed to reset session:', err)
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-68px)] bg-[#FAF8F3] text-[#20201D] font-sans">
      {/* ─── Top Subject Navigation & Chapter Bar ─── */}
      <header className="bg-white border-b border-[#E7E1D8] px-4 sm:px-8 py-3.5 flex flex-col gap-3 shadow-2xs">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate(`/subjects/${activeSubjectId}`)}
              className="p-2 rounded-xl hover:bg-[#F2ECE4] text-[#6F6B63] hover:text-[#20201D] transition-colors cursor-pointer"
              title="Back to Subject Workspace"
            >
              <ArrowLeft size={18} />
            </button>

            <div className="flex items-center gap-2.5">
              <span className="text-2xl">{config.icon}</span>
              <div>
                <h1 className="text-base sm:text-lg font-bold text-[#20201D] leading-tight">
                  {subject.name} AI Tutor
                </h1>
                <p className="text-xs text-[#6F6B63]">
                  Connected to Official Kerala SCERT Class 10 Textbook (Pinecone Cloud)
                </p>
              </div>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="flex items-center gap-2">
            {messages.length > 0 && (
              <button
                onClick={handleResetChat}
                disabled={isStreaming}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-[#E7E1D8] hover:border-[#F28A45] text-xs font-bold text-[#6F6B63] hover:text-[#F28A45] transition-colors cursor-pointer bg-white"
                title="Start a new chat for this chapter"
              >
                <RotateCcw size={13} />
                <span className="hidden sm:inline">New Chat</span>
              </button>
            )}

            {selectedTopicId && (
              <>
                <button
                  onClick={() => navigate(`/quiz/${selectedTopicId}`)}
                  className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-[#E7E1D8] hover:border-[#F28A45] text-xs font-bold text-[#6F6B63] hover:text-[#F28A45] transition-colors cursor-pointer bg-white"
                >
                  <Trophy size={14} /> Practice Quiz
                </button>
                <button
                  onClick={() => navigate(`/flashcards/${selectedTopicId}`)}
                  className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-[#E7E1D8] hover:border-[#F28A45] text-xs font-bold text-[#6F6B63] hover:text-[#F28A45] transition-colors cursor-pointer bg-white"
                >
                  <Layers size={14} /> Flashcards
                </button>
              </>
            )}
          </div>
        </div>

        {/* ─── Chapter Selector Chips ─── */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
          <button
            onClick={() => setSelectedTopicId('')}
            className={`px-3 py-1 rounded-full text-xs font-bold whitespace-nowrap transition-all cursor-pointer ${
              selectedTopicId === ''
                ? 'bg-[#20201D] text-white shadow-xs'
                : 'bg-[#F2ECE4] text-[#6F6B63] hover:bg-[#E7E1D8]'
            }`}
          >
            📖 All Chapters
          </button>
          {topics.map((t) => {
            const isSelected = selectedTopicId === t.id
            return (
              <button
                key={t.id}
                onClick={() => setSelectedTopicId(t.id)}
                className={`px-3 py-1 rounded-full text-xs font-bold whitespace-nowrap transition-all cursor-pointer flex items-center gap-1.5 ${
                  isSelected
                    ? 'bg-[#F28A45] text-white shadow-xs'
                    : 'bg-[#F2ECE4] text-[#6F6B63] hover:bg-[#E7E1D8]'
                }`}
              >
                {t.title}
              </button>
            )
          })}
        </div>
      </header>

      {/* ─── Main Chat Area ─── */}
      <main className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6 max-w-4xl w-full mx-auto">
        {loadingSession ? (
          <div className="h-full flex flex-col items-center justify-center py-20 space-y-4">
            <div className="w-10 h-10 border-3 border-[#F28A45] border-t-transparent rounded-full animate-spin" />
            <p className="text-xs font-bold text-[#969188] animate-pulse">Loading AI Textbook Tutor...</p>
          </div>
        ) : messages.length === 0 ? (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, ease: 'easeOut' }}
            className="h-full flex flex-col items-center justify-center text-center py-10 space-y-6"
          >
            {/* Animated Floating Emblem */}
            <motion.div
              animate={{ y: [0, -8, 0] }}
              transition={{ repeat: Infinity, duration: 3.5, ease: 'easeInOut' }}
              className="relative"
            >
              <div
                className="w-20 h-20 rounded-3xl flex items-center justify-center text-4xl shadow-md border"
                style={{ backgroundColor: config.accentBg, borderColor: config.borderColor }}
              >
                {config.icon}
              </div>
              <div
                className="absolute -bottom-1 -right-1 w-7 h-7 rounded-full bg-white border flex items-center justify-center shadow-xs text-xs font-bold"
                style={{ borderColor: config.borderColor, color: config.color }}
              >
                10th
              </div>
            </motion.div>

            <div className="max-w-md space-y-2">
              <h2 className="text-2xl font-black text-[#20201D] tracking-tight">
                {selectedTopic ? selectedTopic.title : `${subject.name} AI Tutor`}
              </h2>
              <p className="text-sm text-[#6F6B63] leading-relaxed">
                {selectedTopic
                  ? selectedTopic.description
                  : 'Ask any question from official textbook chapters. I will explain concepts, provide step-by-step examples, solved calculations, and exam model answers.'}
              </p>
            </div>

            {/* Prompt Starters */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-xl text-left pt-2">
              {config.starters.map((starter, idx) => (
                <motion.button
                  key={idx}
                  whileHover={{ scale: 1.02, y: -2 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => sendMessage(starter)}
                  className="p-4 rounded-2xl bg-white border border-[#E7E1D8] hover:border-[#F28A45] hover:shadow-xs transition-all cursor-pointer flex items-start gap-3 group text-left"
                >
                  <div className="w-7 h-7 rounded-xl bg-[#FFF0E4] flex items-center justify-center flex-shrink-0 mt-0.5 group-hover:scale-110 transition-transform">
                    <Sparkles size={14} className="text-[#F28A45]" />
                  </div>
                  <span className="text-xs font-bold text-[#20201D] group-hover:text-[#F28A45] transition-colors leading-relaxed">
                    {starter}
                  </span>
                </motion.button>
              ))}
            </div>
          </motion.div>
        ) : (
          <div className="space-y-4 pb-4">
            <AnimatePresence initial={false}>
              {messages.map((m) => (
                <motion.div
                  key={m.id}
                  initial={{ opacity: 0, y: 10, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ duration: 0.25, ease: 'easeOut' }}
                >
                  <ChatMessage
                    role={m.role}
                    content={m.content}
                    sources={m.sources}
                    isStreaming={isStreaming && m.id === messages[messages.length - 1]?.id}
                  />
                </motion.div>
              ))}
            </AnimatePresence>
            <div ref={messagesEndRef} />
          </div>
        )}
      </main>

      {/* ─── Bottom Chat Input (Clean & Aesthetic Floating Capsule) ─── */}
      <footer className="p-4 max-w-4xl w-full mx-auto">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            sendMessage()
          }}
          className="relative bg-white border border-[#E7E1D8] focus-within:border-[#F28A45] focus-within:ring-3 focus-within:ring-[#F28A45]/15 rounded-3xl p-2 pl-5 shadow-xs transition-all flex items-center gap-3"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={`Ask a question or topic from ${selectedTopic ? selectedTopic.title : subject.name}...`}
            className="flex-1 bg-transparent text-sm sm:text-base text-[#20201D] font-medium placeholder-[#9E9B95] focus:outline-none"
            disabled={isStreaming || loadingSession}
          />

          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            type="submit"
            disabled={!input.trim() || isStreaming || loadingSession}
            className="p-3.5 bg-[#F28A45] hover:bg-[#D97706] disabled:opacity-30 disabled:cursor-not-allowed text-white rounded-2xl transition-all cursor-pointer flex-shrink-0 shadow-xs flex items-center justify-center"
            title="Send Message"
          >
            <Send size={16} />
          </motion.button>
        </form>
      </footer>
    </div>
  )
}
