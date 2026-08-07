import axios from 'axios'
import { useAuthStore } from '../stores/authStore'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Handle 401 globally
api.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// ─── Auth ─────────────────────────────────────────────────────
export const authApi = {
  login: (email: string, password: string) =>
    api.post('/auth/login', { email, password }),
  register: (data: { username: string; email: string; password: string }) =>
    api.post('/auth/register', data),
  me: () => api.get('/auth/me'),
}

// ─── Subjects ─────────────────────────────────────────────────
export const subjectsApi = {
  list: () => api.get('/subjects'),
  get: (id: string) => api.get(`/subjects/${id}`),
  topics: (id: string) => api.get(`/subjects/${id}/topics`),
}

// ─── Topics ───────────────────────────────────────────────────
export const topicsApi = {
  get: (id: string) => api.get(`/topics/${id}`),
}

// ─── Chat ─────────────────────────────────────────────────────
export const chatApi = {
  sessions: () => api.get('/chat/sessions'),
  createSession: (topicId: string, title: string) =>
    api.post('/chat/sessions', { topic_id: topicId, session_title: title }),
  messages: (sessionId: string) =>
    api.get(`/chat/sessions/${sessionId}/messages`),
  deleteSession: (sessionId: string) =>
    api.delete(`/chat/sessions/${sessionId}`),
}

// SSE streaming — using fetch + ReadableStream for reliable header auth & proxy support
export const streamChatMessage = async ({
  sessionId,
  content,
  token,
  onToken,
  onSources,
  onGraphContext,
  onDone,
  onError,
  signal,
}: {
  sessionId: string
  content: string
  token: string
  onToken: (token: string) => void
  onSources: (sources: any[]) => void
  onGraphContext: (graph: any) => void
  onDone: () => void
  onError: (err: any) => void
  signal?: AbortSignal
}) => {
  try {
    const url = `/api/chat/sessions/${sessionId}/message/stream?content=${encodeURIComponent(content)}`
    const headers: Record<string, string> = { Accept: 'text/event-stream' }
    if (token) headers.Authorization = `Bearer ${token}`

    const res = await fetch(url, { headers, signal })

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${res.statusText}`)
    }

    if (!res.body) {
      throw new Error('ReadableStream not supported')
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    let isCompleted = false

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data: ')) continue
        const raw = trimmed.slice(6)
        try {
          const evt = JSON.parse(raw)
          if (evt.type === 'token') {
            onToken(evt.data)
          } else if (evt.type === 'sources') {
            onSources(evt.data)
          } else if (evt.type === 'graph_context') {
            onGraphContext(evt.data)
          } else if (evt.type === 'done') {
            isCompleted = true
            onDone()
            return
          }
        } catch {
          // ignore parsing error for partial frame
        }
      }
    }

    if (!isCompleted) {
      onDone()
    }
  } catch (err: any) {
    if (err.name === 'AbortError') return
    onError(err)
  }
}

// SSE streaming — legacy EventSource
export const streamMessage = (sessionId: string, content: string, token: string): EventSource => {
  const urlWithToken = `/api/chat/sessions/${sessionId}/message/stream?content=${encodeURIComponent(content)}&token=${token}`
  return new EventSource(urlWithToken)
}

// Fallback non-streaming message
export const sendMessage = (sessionId: string, content: string) =>
  api.post(`/chat/sessions/${sessionId}/message`, { content })


// ─── Quiz ─────────────────────────────────────────────────────
export const quizApi = {
  list: (topicId: string) => api.get(`/quiz/topic/${topicId}`),
  get: (id: string) => api.get(`/quiz/${id}`),
  generate: (data: {
    topic_id: string
    difficulty?: string
    session_id?: string
    focus_topic?: string
    num_questions?: number
  }) => api.post('/quiz/generate', data),
  submit: (quizId: string, answers: Record<string, string>) =>
    api.post(`/quiz/${quizId}/submit`, { answers }),
  attempts: (quizId: string) => api.get(`/quiz/${quizId}/attempts`),
  myAttempts: () => api.get('/quiz/my-attempts'),
}

// ─── Progress ─────────────────────────────────────────────────
export const progressApi = {
  summary: () => api.get('/progress/summary'),
  weekly: () => api.get('/progress/weekly'),
  recentQuizzes: () => api.get('/progress/recent-quizzes'),
  calendar: () => api.get('/progress/calendar'),
  topics: () => api.get('/progress/topics'),
  streaks: () => api.get('/progress/streaks'),
}

// ─── Documents ────────────────────────────────────────────────
export const documentsApi = {
  upload: (topicId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    form.append('topic_id', topicId)
    return api.post('/documents/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  list: (topicId?: string) =>
    api.get('/documents', { params: { topic_id: topicId } }),
  status: (docId: string) => api.get(`/documents/${docId}/status`),
  graph: (topicId: string) => api.get(`/documents/topic/${topicId}/graph`),
}

// ─── MCP Protocol API ──────────────────────────────────────────
export const mcpApi = {
  listServers: () => api.get('/mcp/servers'),
  addServer: (config: any) => api.post('/mcp/servers', config),
  toggleServer: (serverId: string, enabled: boolean) =>
    api.patch(`/mcp/servers/${serverId}/toggle`, { enabled }),
  deleteServer: (serverId: string) => api.delete(`/mcp/servers/${serverId}`),
  listTools: () => api.get('/mcp/tools'),
  executeTool: (toolName: string, args: any) =>
    api.post('/mcp/tools/execute', { tool_name: toolName, arguments: args }),
}

// ─── Study Plan ───────────────────────────────────────────────
export const studyPlanApi = {
  myPlans: () => api.get('/study-plan/my-plans'),
  get: (id: string) => api.get(`/study-plan/${id}`),
  generate: (data: { topic_id?: string; target_date: string; hours_per_day?: number }) =>
    api.post('/study-plan/generate', data),
  toggleDay: (planId: string, dayNumber: number) =>
    api.post(`/study-plan/${planId}/toggle-day`, { day_number: dayNumber }),
  delete: (planId: string) => api.delete(`/study-plan/${planId}`),
}

// ─── Leaderboard ──────────────────────────────────────────────
export const leaderboardApi = {
  getRankings: () => api.get('/leaderboard'),
}

export default api
