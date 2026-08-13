import { useEffect, useRef } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from './stores/authStore'
import { useChatStore } from './stores/chatStore'
import { chatApi } from './services/api'
import { lazy, Suspense } from 'react'
import Layout from './components/Layout'
import MouseSpotlight from './components/MouseSpotlight'

// Lazy-loaded pages for fast code splitting
const LandingPage = lazy(() => import('./pages/LandingPage'))
const LoginPage = lazy(() => import('./pages/LoginPage'))
const RegisterPage = lazy(() => import('./pages/RegisterPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const StudyPlanPage = lazy(() => import('./pages/StudyPlanPage'))
const ChatPage = lazy(() => import('./pages/ChatPage'))
const QuizPage = lazy(() => import('./pages/QuizPage'))
const QuizResultPage = lazy(() => import('./pages/QuizResultPage'))
const ProgressPage = lazy(() => import('./pages/ProgressPage'))
const FlashcardsPage = lazy(() => import('./pages/FlashcardsPage'))
const LeaderboardPage = lazy(() => import('./pages/LeaderboardPage'))
const SubjectsPage = lazy(() => import('./pages/SubjectsPage'))
const TopicsPage = lazy(() => import('./pages/TopicsPage'))
const SubjectWorkspacePage = lazy(() => import('./pages/SubjectWorkspacePage'))

function PageFallback() {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="w-8 h-8 border-3 border-[#F28A45] border-t-transparent rounded-full animate-spin" />
    </div>
  )
}


const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
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

    // Fetch this user's sessions
    chatApi.sessions()
      .then((res) => setSessions(res.data))
      .catch(() => {/* page-level queries will retry */})
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
        <GlobalSessionLoader />
        <Suspense fallback={<PageFallback />}>
          <Routes>
            {/* Public Hero Landing Page */}
            <Route path="/" element={<LandingPage />} />
            <Route path="/hero" element={<LandingPage />} />

            {/* Auth */}
            <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />
            <Route path="/register" element={<PublicRoute><RegisterPage /></PublicRoute>} />

            {/* Protected Application Routes */}
            <Route path="/app" element={<PrivateRoute><Layout /></PrivateRoute>}>
              <Route index element={<Navigate to="/app/dashboard" replace />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="subjects" element={<SubjectsPage />} />
              <Route path="subjects/:subjectId" element={<SubjectWorkspacePage />} />
              <Route path="subjects/:subjectId/topics" element={<TopicsPage />} />
              <Route path="topics" element={<TopicsPage />} />
              <Route path="study-plan" element={<StudyPlanPage />} />
              <Route path="chat/:sessionId?" element={<ChatPage />} />
              <Route path="leaderboard" element={<LeaderboardPage />} />
              <Route path="quiz/:topicId" element={<QuizPage />} />
              <Route path="quiz/:topicId/result" element={<QuizResultPage />} />
              <Route path="flashcards/:topicId" element={<FlashcardsPage />} />
              <Route path="progress" element={<ProgressPage />} />
            </Route>

            {/* Root-level redirects for convenience */}
            <Route path="/dashboard" element={<PrivateRoute><Layout /></PrivateRoute>}>
              <Route index element={<DashboardPage />} />
            </Route>
            <Route path="/subjects" element={<PrivateRoute><Layout /></PrivateRoute>}>
              <Route index element={<SubjectsPage />} />
            </Route>
            <Route path="/subjects/:subjectId" element={<PrivateRoute><Layout /></PrivateRoute>}>
              <Route index element={<SubjectWorkspacePage />} />
            </Route>
            <Route path="/subjects/:subjectId/topics" element={<PrivateRoute><Layout /></PrivateRoute>}>
              <Route index element={<TopicsPage />} />
            </Route>
            <Route path="/topics" element={<PrivateRoute><Layout /></PrivateRoute>}>
              <Route index element={<TopicsPage />} />
            </Route>
            <Route path="/study-plan" element={<PrivateRoute><Layout /></PrivateRoute>}>
              <Route index element={<StudyPlanPage />} />
            </Route>
            <Route path="/chat/:sessionId?" element={<PrivateRoute><Layout /></PrivateRoute>}>
              <Route index element={<ChatPage />} />
            </Route>
            <Route path="/leaderboard" element={<PrivateRoute><Layout /></PrivateRoute>}>
              <Route index element={<LeaderboardPage />} />
            </Route>
            <Route path="/progress" element={<PrivateRoute><Layout /></PrivateRoute>}>
              <Route index element={<ProgressPage />} />
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>

      </BrowserRouter>
    </QueryClientProvider>
  )
}

