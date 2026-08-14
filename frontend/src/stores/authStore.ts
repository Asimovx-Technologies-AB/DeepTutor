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
        // Also wipe the chat store persisted data so the next user
        // doesn't see a previous user's sessions on first render
        try { localStorage.removeItem('deep-tutor-chat') } catch {}
        set({ user: null, token: null, isAuthenticated: false })
      },
      updateUser: (fields) =>
        set((state) => ({
          user: state.user ? { ...state.user, ...fields } : null,
        })),
    }),
    { name: 'deep-tutor-auth' }
  )
)
