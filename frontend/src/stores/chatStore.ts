import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface ChatSession {
  id: string
  topic_id: string
  session_title: string
  started_at: string
}

interface ChatState {
  sessions: ChatSession[]
  activeSession: ChatSession | null
  messages: Message[]
  isStreaming: boolean
  streamingContent: string
  setSessions: (sessions: ChatSession[]) => void
  setActiveSession: (session: ChatSession | null) => void
  setMessages: (messages: Message[]) => void
  addMessage: (message: Message) => void
  removeSession: (sessionId: string) => void
  setStreaming: (streaming: boolean) => void
  appendStreamToken: (token: string) => void
  clearStreamingContent: () => void
  commitStreamedMessage: () => void
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      sessions: [],
      activeSession: null,
      // Messages are intentionally NOT persisted — always fetched fresh from server
      messages: [],
      isStreaming: false,
      streamingContent: '',
      setSessions: (sessions) => set({ sessions }),
      setActiveSession: (session) => set({ activeSession: session }),
      setMessages: (messages) => set({ messages }),
      addMessage: (message) =>
        set((state) => ({ messages: [...state.messages, message] })),
      removeSession: (sessionId) =>
        set((state) => {
          const updatedSessions = state.sessions.filter((s) => s.id !== sessionId)
          const isDeletingActive = state.activeSession?.id === sessionId
          return {
            sessions: updatedSessions,
            activeSession: isDeletingActive ? (updatedSessions[0] || null) : state.activeSession,
            messages: isDeletingActive ? [] : state.messages,
          }
        }),
      setStreaming: (streaming) => set({ isStreaming: streaming }),
      appendStreamToken: (token) =>
        set((state) => ({ streamingContent: state.streamingContent + token })),
      clearStreamingContent: () => set({ streamingContent: '' }),
      commitStreamedMessage: () => {
        const { streamingContent, messages } = get()
        if (!streamingContent) return
        const msg: Message = {
          id: Date.now().toString(),
          role: 'assistant',
          content: streamingContent,
          created_at: new Date().toISOString(),
        }
        set({ messages: [...messages, msg], streamingContent: '', isStreaming: false })
      },
    }),
    {
      name: 'deep-tutor-chat',
      // Only persist sessions + activeSession — messages are always loaded from server
      partialize: (state) => ({
        sessions: state.sessions,
        activeSession: state.activeSession,
      }),
    }
  )
)
