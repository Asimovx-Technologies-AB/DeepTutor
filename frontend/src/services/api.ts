import axios from 'axios'
import { useAuthStore } from '../stores/authStore'

export const getApiBaseUrl = (): string => {
  const envUrl = import.meta.env.VITE_API_BASE_URL
  if (envUrl) {
    const trimmed = envUrl.replace(/\/+$/, '')
    return trimmed.endsWith('/api') ? trimmed : `${trimmed}/api`
  }
  if (import.meta.env.DEV) {
    return '/api'
  }
  return 'https://deeptutor-api-udv2.onrender.com/api'
}

const api = axios.create({
  baseURL: getApiBaseUrl(),
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

// ─── Health & Connection ──────────────────────────────────────
export const healthApi = {
  check: () => api.get('/health'),
}

// ─── Auth ─────────────────────────────────────────────────────
export const authApi = {
  login: (email: string, password: string) =>
    api.post('/auth/login', { email, password }),
  register: (data: { username: string; email: string; password: string }) =>
    api.post('/auth/register', data),
  me: () => api.get('/auth/me'),
  upgradePremium: (isPremium: boolean = true) =>
    api.post('/auth/upgrade-premium', { is_premium: isPremium }),
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
  sessions: (scope?: string) => api.get('/chat/sessions', { params: scope ? { scope } : {} }),
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
  language = 'english',
  onToken,
  onSources,
  onGraphContext,
  onGrounding,
  onDone,
  onError,
  signal,
}: {
  sessionId: string
  content: string
  token: string
  language?: string
  onToken: (token: string) => void
  onSources: (sources: any[]) => void
  onGraphContext: (graph: any) => void
  onGrounding?: (grounding: any) => void
  onDone: () => void
  onError: (err: any) => void
  signal?: AbortSignal
}) => {
  const baseUrl = getApiBaseUrl()
  const url = `${baseUrl}/chat/sessions/${sessionId}/message/stream?content=${encodeURIComponent(content)}&language=${encodeURIComponent(language)}`
  const headers: Record<string, string> = { Accept: 'text/event-stream' }
  if (token) headers.Authorization = `Bearer ${token}`

  let res: Response | null = null
  let attempts = 0
  const maxAttempts = 2

  while (attempts < maxAttempts) {
    try {
      attempts++
      res = await fetch(url, { headers, signal })
      if (res.ok) break
      if (attempts < maxAttempts && (res.status === 502 || res.status === 503 || res.status === 504)) {
        await new Promise((r) => setTimeout(r, 1200))
        continue
      }
      throw new Error(`HTTP ${res.status}: ${res.statusText}`)
    } catch (fetchErr: any) {
      if (signal?.aborted || fetchErr?.name === 'AbortError') return
      if (attempts < maxAttempts) {
        await new Promise((r) => setTimeout(r, 1500))
        continue
      }
      onError(fetchErr)
      return
    }
  }

  try {
    if (!res || !res.ok) {
      throw new Error(res ? `HTTP ${res.status}: ${res.statusText}` : 'Connection failed')
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
          } else if (evt.type === 'grounding' && onGrounding) {
            onGrounding(evt.data)
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
    if (signal?.aborted || err?.name === 'AbortError') return
    onError(err)
  }
}

// SSE streaming — legacy EventSource
export const streamMessage = (sessionId: string, content: string, token: string): EventSource => {
  const baseUrl = getApiBaseUrl()
  const urlWithToken = `${baseUrl}/chat/sessions/${sessionId}/message/stream?content=${encodeURIComponent(content)}&token=${token}`
  return new EventSource(urlWithToken)
}

// Fallback non-streaming message
export const sendMessage = (sessionId: string, content: string, language: string = 'english') =>
  api.post(`/chat/sessions/${sessionId}/message`, { content, language })


// ─── Quiz ─────────────────────────────────────────────────────
export const quizApi = {
  list: (topicId: string) => api.get(`/quiz/topic/${topicId}`),
  get: (id: string) => api.get(`/quiz/${id}`),
  generate: (data: {
    topic_id?: string
    note_id?: string
    note_content?: string
    difficulty?: string
    session_id?: string
    focus_topic?: string
    custom_topic?: string
    num_questions?: number
    language?: string
  }) => api.post('/quiz/generate', data),
  submit: (quizId: string, answers: Record<string, string>) =>
    api.post(`/quiz/${quizId}/submit`, { answers }),
  attempts: (quizId: string) => api.get(`/quiz/${quizId}/attempts`),
  myAttempts: () => api.get('/quiz/my-attempts'),
  suggestions: (params: { session_id?: string; topic_id?: string }) =>
    api.get('/quiz/suggestions', { params }),
}

// ─── Flashcards ───────────────────────────────────────────────
export const flashcardsApi = {
  generate: (data: {
    session_id?: string
    topic_id?: string
    focus_topic?: string
    custom_topic?: string
    num_cards?: number
    language?: string
  }) => api.post('/flashcards/generate', data),
  byTopic: (topicId: string) => api.get(`/flashcards/topic/${topicId}`),
  bySession: (sessionId: string) => api.get(`/flashcards/session/${sessionId}`),
  review: (topicId: string, cardId: string, mastered: boolean) =>
    api.post(`/flashcards/${topicId}/cards/${cardId}/review`, { mastered }),
}

// ─── Progress ─────────────────────────────────────────────────
export const progressApi = {
  summary: () => api.get('/progress/summary'),
  weekly: () => api.get('/progress/weekly'),
  recentQuizzes: () => api.get('/progress/recent-quizzes'),
  calendar: () => api.get('/progress/calendar'),
  topics: () => api.get('/progress/topics'),
  streaks: () => api.get('/progress/streaks'),
  analysis: () => api.get('/progress/analysis'),
  studentRecord: () => api.get('/progress/student-record'),
}

// ─── Smart Notes & PYQ Generator ──────────────────────────────
export const notesApi = {
  list: () => api.get('/notes'),
  get: (id: string) => api.get(`/notes/${id}`),
  delete: (id: string) => api.delete(`/notes/${id}`),
  generate: (data: {
    materialFile?: File | null
    pyqFiles?: File[]
    topicId?: string
    subject?: string
    noteType?: string
    customInstructions?: string
    existingDocId?: string
  }) => {
    const form = new FormData()
    if (data.materialFile) {
      form.append('material_file', data.materialFile)
    }
    if (data.pyqFiles && data.pyqFiles.length > 0) {
      data.pyqFiles.forEach((file) => {
        form.append('pyq_files', file)
      })
    }
    if (data.topicId) form.append('topic_id', data.topicId)
    if (data.subject) form.append('subject', data.subject)
    if (data.noteType) form.append('note_type', data.noteType)
    if (data.customInstructions) form.append('custom_instructions', data.customInstructions)
    if (data.existingDocId) form.append('existing_doc_id', data.existingDocId)

    return api.post('/notes/generate', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}


// ─── Dashboard ─────────────────────────────────────────────────
export const dashboardApi = {
  stats: () => api.get('/dashboard/stats'),
  activity: (limit?: number) => api.get('/dashboard/activity', { params: { limit } }),
  continue: () => api.get('/dashboard/continue'),
  recordActivity: (data: { activity_type: string; title: string; subject_id?: string; topic_id?: string }) =>
    api.post('/dashboard/activity/record', data),
  updateProgress: (data: { subject_id: string; topic_id: string; progress_percentage: number }) =>
    api.post('/dashboard/progress/update', data),
  goals: () => api.get('/dashboard/goals'),
}

// ─── Documents ────────────────────────────────────────────────
export const documentsApi = {
  upload: (topicId: string, file: File, sectionId?: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('topic_id', topicId)
    if (sectionId) form.append('section_id', sectionId)
    return api.post('/documents/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  list: (topicId?: string) =>
    api.get('/documents', { params: { topic_id: topicId } }),
  status: (docId: string) => api.get(`/documents/${docId}/status`),
  graph: (topicId: string) => api.get(`/documents/topic/${topicId}/graph`),
  explainConcept: (concept: string, topicId?: string) =>
    api.post('/documents/concept-explain', { concept, topic_id: topicId }),
  delete: (docId: string) => api.delete(`/documents/${docId}`),
  deleteSection: (sectionId: string) => api.delete(`/documents/section/${sectionId}`),
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
  generate: (data: { topic_id?: string; session_id?: string; target_date: string; hours_per_day?: number; language?: string }) =>
    api.post('/study-plan/generate', data),
  toggleDay: (planId: string, dayNumber: number) =>
    api.post(`/study-plan/${planId}/toggle-day`, { day_number: dayNumber }),
  verifyQuiz: (planId: string, dayNumber: number, scorePercentage: number) =>
    api.post(`/study-plan/${planId}/verify-quiz`, { day_number: dayNumber, score_percentage: scorePercentage }),
  delete: (planId: string) => api.delete(`/study-plan/${planId}`),
}

// ─── Leaderboard ──────────────────────────────────────────────
export const leaderboardApi = {
  getRankings: () => api.get('/leaderboard'),
}

// ─── AI Study Room & GraphRAG Platform API ────────────────────
export const studyApi = {
  upload: (file: File, subject?: string, sessionId?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (subject) form.append('subject', subject)
    if (sessionId) form.append('session_id', sessionId)
    return api.post('/study/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  sendMessage: (payload: {
    message: string
    session_id: string
    user_id?: string
    subject?: string
    difficulty?: string
    history?: any[]
  }) => api.post('/study/agent/message', payload),
  getCoreIdea: (payload: {
    session_id: string
    topic_id: string
    topic_title: string
    topic_summary?: string
  }) => api.post('/study/topic/core-idea', payload),
  askDoubt: (payload: {
    session_id: string
    topic_id: string
    topic_title: string
    question: string
    history?: any[]
  }) => api.post('/study/topic/doubt', payload),
  getExam: (payload: {
    session_id: string
    topic_id: string
    topic_title: string
  }) => api.post('/study/topic/exam', payload),
  evaluateExam: (payload: {
    session_id: string
    topic_id: string
    questions: any[]
    answers: Record<string, string>
  }) => api.post('/study/topic/evaluate', payload),
  exportNotesMd: (payload: { markdown: string; title?: string }) =>
    api.post('/study/export/notes-md', payload, { responseType: 'blob' }),
  listSessions: () => api.get('/study/sessions'),
  createSession: (payload?: { subject?: string; title?: string }) =>
    api.post('/study/sessions/new', payload || {}),
  getSession: (sessionId: string) => api.get(`/study/sessions/${sessionId}`),
  deleteSession: (sessionId: string) => api.delete(`/study/sessions/${sessionId}`),
  getMemory: (userId: string) => api.get(`/study/memory/${userId}`),
  addMemoryFact: (userId: string, factData: any) =>
    api.post(`/study/memory/${userId}/fact`, factData),
  clearMemory: (userId: string) => api.delete(`/study/memory/${userId}`),
}

export const streamTeacherLecture = async ({
  sessionId,
  topicId,
  topicTitle,
  onPhaseStart,
  onToken,
  onPhaseEnd,
  onDone,
  onError,
  signal,
}: {
  sessionId: string
  topicId: string
  topicTitle: string
  onPhaseStart?: (phase: string) => void
  onToken: (token: string) => void
  onPhaseEnd?: (phase: string) => void
  onDone: () => void
  onError: (err: any) => void
  signal?: AbortSignal
}) => {
  const baseUrl = getApiBaseUrl()
  const url = `${baseUrl}/study/topic/teach/stream?session_id=${encodeURIComponent(sessionId)}&topic_id=${encodeURIComponent(topicId)}&topic_title=${encodeURIComponent(topicTitle)}`

  try {
    const res = await fetch(url, {
      headers: { Accept: 'text/event-stream' },
      signal,
    })

    if (!res.ok || !res.body) {
      throw new Error(`HTTP ${res.status}: ${res.statusText}`)
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

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
          if (evt.type === 'phase_start' && onPhaseStart) {
            onPhaseStart(evt.phase)
          } else if (evt.type === 'token') {
            onToken(evt.token)
          } else if (evt.type === 'phase_end' && onPhaseEnd) {
            onPhaseEnd(evt.phase)
          } else if (evt.type === 'done') {
            onDone()
            return
          }
        } catch {
          // ignore partial parse error
        }
      }
    }
    onDone()
  } catch (err: any) {
    if (signal?.aborted || err?.name === 'AbortError') return
    onError(err)
  }
}

export default api


