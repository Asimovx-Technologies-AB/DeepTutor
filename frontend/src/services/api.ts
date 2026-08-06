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

// SSE streaming — returns EventSource
export const streamMessage = (sessionId: string, content: string, token: string): EventSource => {
  const params = new URLSearchParams({ content })
  const url = `/api/chat/sessions/${sessionId}/message/stream?${params}`
  // We can't set headers on EventSource natively; use a workaround via URL param
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
  generate: (topicId: string, difficulty?: string) =>
    api.post('/quiz/generate', { topic_id: topicId, difficulty }),
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
  status: (topicId: string) => api.get(`/documents/status/${topicId}`),
  list: () => api.get('/documents'),
  delete: (docId: string) => api.delete(`/documents/${docId}`),
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
