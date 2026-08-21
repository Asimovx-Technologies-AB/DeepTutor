import { useEffect, useRef } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from './stores/authStore'
import { useChatStore } from './stores/chatStore'
import { chatApi } from './services/api'
import { lazy, Suspense } from 'react'
import Layout from './components/Layout'
import MouseSpotlight from './components/MouseSpotlight'
import ServerWarmupNotice from './components/ServerWarmupNotice'

// Directly import core primary pages for 0ms instant snappy navigation
import DashboardPage from './pages/DashboardPage'
import ChatPage from './pages/ChatPage'
import SubjectsPage from './pages/SubjectsPage'
import StudentRecordsPage from './pages/StudentRecordsPage'
import StudyPlanPage from './pages/StudyPlanPage'
import SubjectWorkspacePage from './pages/SubjectWorkspacePage'
import SubjectChatPage from './pages/SubjectChatPage'
import TopicsPage from './pages/TopicsPage'
import QuizPage from './pages/QuizPage'
import QuizResultPage from './pages/QuizResultPage'
import FlashcardsPage from './pages/FlashcardsPage'

// Code-split auxiliary public & auth pages
const LandingPage = lazy(() => import('./pages/LandingPage'))
const LoginPage = lazy(() => import('./pages/LoginPage'))
const RegisterPage = lazy(() => import('./pages/RegisterPage'))

function PageFallback() {
  return (
    <div className="flex items-center justify-center min-h-[50vh] w-full">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-3 border-indigo-600 border-t-transparent rounded-full animate-spin" />
        <span className="text-xs font-semibold text-slate-400">Loading...</span>
      </div>
    </div>
  )
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 60 * 1000,         // 1 minute instant cached navigation
      gcTime: 10 * 60 * 1000,       // 10 minutes garbage collection
      refetchOnWindowFocus: false,  // Avoid repeated network calls on tab switch
    },
  },
})

/** Pre-fetches sessions and ensures data is scoped to the current user only.
 * - On login/user-switch: clears old sessions immediately then fetches fresh ones
 * - On logout: wipes all cached session data
 */
function GlobalSessionLoader() {
  const user = useAuthStore((s) => s.user)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const setSessions = useChatStore((s) => s.setSessions)
  const setActiveSession = useChatStore((s) => s.setActiveSession)
  const prevUserIdRef = useRef<string | null>(null)

  useEffect(() => {
    const currentUserId = user?.id ?? null

    // Logout: clear everything immediately
    if (!isAuthenticated) {
      setSessions([])
      setActiveSession(null)
      prevUserIdRef.current = null
      queryClient.clear() // wipe all React Query caches
      return
    }

    // User switched (different account): clear old data before loading new
    if (prevUserIdRef.current !== null && prevUserIdRef.current !== currentUserId) {
      setSessions([])
      setActiveSession(null)
      queryClient.clear()
    }
    prevUserIdRef.current = currentUserId

    // Fetch this user's sessions in background
    chatApi.sessions('learn')
      .then((res) => setSessions(res.data || []))
      .catch(() => {/* page-level queries will retry */ })
  }, [isAuthenticated, user?.id])

  return null
}

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  return isAuthenticated ? <>{children}</> : <Navigate to="/" replace />
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  return !isAuthenticated ? <>{children}</> : <Navigate to="/dashboard" replace />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ServerWarmupNotice />
        <GlobalSessionLoader />
        <Routes>
          {/* Public Hero Landing Page */}
          <Route path="/" element={<Suspense fallback={<PageFallback />}><LandingPage /></Suspense>} />
          <Route path="/hero" element={<Suspense fallback={<PageFallback />}><LandingPage /></Suspense>} />

          {/* Auth */}
          <Route path="/login" element={<Suspense fallback={<PageFallback />}><PublicRoute><LoginPage /></PublicRoute></Suspense>} />
          <Route path="/register" element={<Suspense fallback={<PageFallback />}><PublicRoute><RegisterPage /></PublicRoute></Suspense>} />

          {/* Authenticated Application Shell (Persistent Layout - Never Unmounts) */}
          <Route element={<PrivateRoute><Layout /></PrivateRoute>}>
            {/* Root-level routes */}
            <Route path="dashboard" element={<DashboardPage />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="chat/:sessionId" element={<ChatPage />} />
            <Route path="subjects" element={<SubjectsPage />} />
            <Route path="subjects/:subjectId" element={<SubjectWorkspacePage />} />
            <Route path="subjects/:subjectId/chat" element={<SubjectChatPage />} />
            <Route path="subjects/:subjectId/chat/:topicId" element={<SubjectChatPage />} />
            <Route path="subjects/:subjectId/topics" element={<TopicsPage />} />
            <Route path="topics" element={<TopicsPage />} />
            <Route path="records" element={<StudentRecordsPage />} />
            <Route path="student-records" element={<StudentRecordsPage />} />
            <Route path="study-plan" element={<StudyPlanPage />} />
            <Route path="quiz" element={<QuizPage />} />
            <Route path="quiz/:topicId" element={<QuizPage />} />
            <Route path="quiz/:topicId/result" element={<QuizResultPage />} />
            <Route path="flashcards/:topicId" element={<FlashcardsPage />} />

            {/* Nested /app/* prefix routes for complete backward compatibility */}
            <Route path="app">
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="subjects" element={<SubjectsPage />} />
              <Route path="subjects/:subjectId" element={<SubjectWorkspacePage />} />
              <Route path="subjects/:subjectId/chat" element={<SubjectChatPage />} />
              <Route path="subjects/:subjectId/chat/:topicId" element={<SubjectChatPage />} />
              <Route path="subjects/:subjectId/topics" element={<TopicsPage />} />
              <Route path="topics" element={<TopicsPage />} />
              <Route path="records" element={<StudentRecordsPage />} />
              <Route path="student-records" element={<StudentRecordsPage />} />
              <Route path="study-plan" element={<StudyPlanPage />} />
              <Route path="chat" element={<ChatPage />} />
              <Route path="chat/:sessionId" element={<ChatPage />} />
              <Route path="leaderboard" element={<Navigate to="/dashboard" replace />} />
              <Route path="quiz" element={<QuizPage />} />
              <Route path="quiz/:topicId" element={<QuizPage />} />
              <Route path="quiz/:topicId/result" element={<QuizResultPage />} />
              <Route path="flashcards/:topicId" element={<FlashcardsPage />} />
            </Route>

            {/* Aliases */}
            <Route path="exam-prep" element={<Navigate to="/dashboard" replace />} />
            <Route path="notes" element={<Navigate to="/dashboard" replace />} />
            <Route path="progress" element={<Navigate to="/dashboard" replace />} />
            <Route path="leaderboard" element={<Navigate to="/dashboard" replace />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

