import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface User {
  id: string
  username: string
  email: string
  role: string
  is_premium?: boolean
  plan?: string
  max_upload_size_mb?: number
}

/** All localStorage keys owned by user-scoped stores. Update here if store names change. */
const USER_STORE_KEYS = [
  'indietutor-chat-v2',       // chatStore
  'indie-tutor-document-library', // subjectStore
  // legacy key – remove after a few releases
  'indie-tutor-chat',
]

/** Wipe all cached user data from localStorage. Call before switching users. */
export function clearAllUserData() {
  USER_STORE_KEYS.forEach((key) => {
    try { localStorage.removeItem(key) } catch { /* ignore */ }
  })
}

interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  login: (user: User, token: string) => void
  logout: () => void
  updateUser: (user: Partial<User>) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      login: (user, token) =>
        set({ user, token, isAuthenticated: true }),
      logout: () => {
        // Wipe every user-scoped persisted store so the next user
        // always starts with a clean slate
        clearAllUserData()
        set({ user: null, token: null, isAuthenticated: false })
      },
      updateUser: (fields) =>
        set((state) => ({
          user: state.user ? { ...state.user, ...fields } : null,
        })),
    }),
    { name: 'indie-tutor-auth' }
  )
)
