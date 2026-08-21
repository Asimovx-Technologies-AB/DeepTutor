import { useState, useEffect, useCallback } from 'react'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'

import {
  Home,
  BookOpen,
  CalendarCheck,
  Trophy,
  TrendingUp,
  Layers,
  LogOut,
  ChevronRight,
  Menu,
  X,
  Zap,
  Bot,
  Sparkles,
  Wifi,
  WifiOff,
  Crown,
  Plus,
  FileText,
  Trash2,
  GraduationCap,
  Award
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useChatStore } from '../stores/chatStore'
import { healthApi, chatApi } from '../services/api'
import ProfileModal from './ProfileModal'
import UpgradeModal from './UpgradeModal'
import ConfirmModal from './ConfirmModal'


const NAV_ITEMS = [
  { to: '/dashboard', icon: Home, label: 'Home', badge: null },
  { to: '/chat', icon: BookOpen, label: 'Learn', badge: 'Live' },
  { to: '/exam-prep', icon: GraduationCap, label: 'Exam Prep', badge: '3-Step' },
  { to: '/subjects', icon: Layers, label: 'My Subjects', badge: null },
  { to: '/records', icon: Award, label: 'Student Records', badge: 'Live' },
  { to: '/study-plan', icon: CalendarCheck, label: 'Study Plan', badge: 'AI' },
]

export default function Layout() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [isOnline, setIsOnline] = useState<boolean>(true)
  const [isProfileOpen, setIsProfileOpen] = useState(false)
  const [isUpgradeOpen, setIsUpgradeOpen] = useState(false)
  const [confirmDeleteSid, setConfirmDeleteSid] = useState<string | null>(null)

  const sessions = useChatStore((s) => s.sessions)
  const activeSession = useChatStore((s) => s.activeSession)
  const setActiveSession = useChatStore((s) => s.setActiveSession)
  const setSessions = useChatStore((s) => s.setSessions)
  const removeSession = useChatStore((s) => s.removeSession)

  useEffect(() => {
    let isMounted = true
    const checkBackend = () => {
      healthApi
        .check()
        .then(() => { if (isMounted) setIsOnline(true) })
        .catch(() => { if (isMounted) setIsOnline(false) })
    }
    checkBackend()
    const interval = setInterval(checkBackend, 60000)
    return () => {
      isMounted = false
      clearInterval(interval)
    }
  }, [])

  const handleLogout = useCallback(() => {
    logout()
    navigate('/login')
  }, [logout, navigate])

  const handleDeleteSession = useCallback((e: React.MouseEvent, sid: string) => {
    e.stopPropagation()
    setConfirmDeleteSid(sid)
  }, [])

  const executeDeleteSession = useCallback(async () => {
    const sid = confirmDeleteSid
    if (!sid) return
    setConfirmDeleteSid(null)
    try {
      await chatApi.deleteSession(sid)
      removeSession(sid)
      if (activeSession?.id === sid) {
        setActiveSession(null)
        navigate('/chat')
      }
    } catch (err) {
      console.error('Failed to delete session:', err)
    }
  }, [confirmDeleteSid, activeSession?.id, removeSession, setActiveSession, navigate])

  return (
    <div className="flex h-screen bg-bg-primary overflow-hidden text-text-primary font-sans antialiased">
      {/* Modals */}
      <ProfileModal isOpen={isProfileOpen} onClose={() => setIsProfileOpen(false)} />
      <UpgradeModal isOpen={isUpgradeOpen} onClose={() => setIsUpgradeOpen(false)} />
      <ConfirmModal
        isOpen={Boolean(confirmDeleteSid)}
        title="Delete Chat Session?"
        message="Are you sure you want to delete this chat session? All messages, documents, and data will be permanently removed from the database."
        confirmText="Delete Session"
        cancelText="Cancel"
        variant="danger"
        onConfirm={executeDeleteSession}
        onCancel={() => setConfirmDeleteSid(null)}
      />

      {/* ─── DESKTOP SIDEBAR ─── */}
      <aside className="hidden lg:flex w-[104px] flex-shrink-0 flex-col p-4 z-20">
        <div className="flex-1 rounded-3xl bg-white/80 backdrop-blur-xl border border-white/60 elevation-1 flex flex-col items-center py-8 justify-between relative">

          {/* Top Logo */}
          <div className="flex items-center justify-center cursor-pointer mb-8" onClick={() => navigate('/dashboard')}>
            <div className="w-12 h-12 rounded-2xl bg-brand-primary text-white flex items-center justify-center elevation-2">
              <GraduationCap size={24} />
            </div>
          </div>

          {/* Navigation Items */}
          <nav className="flex-1 flex flex-col items-center gap-6 overflow-y-auto no-scrollbar w-full">
            {NAV_ITEMS.map(({ to, icon: Icon, label }) => {
              const isActive = location.pathname.startsWith(to)
              return (
                <NavLink
                  key={to}
                  to={to}
                  title={label}
                  className={`flex items-center justify-center w-12 h-12 rounded-2xl transition-all group ${isActive
                    ? 'bg-white elevation-1 text-brand-primary'
                    : 'text-text-muted hover:text-brand-primary hover:bg-white/50'
                    }`}
                >
                  <Icon
                    size={22}
                    className={isActive ? 'text-brand-primary' : 'text-text-muted group-hover:text-brand-primary transition-colors'}
                  />
                </NavLink>
              )
            })}
          </nav>

          {/* Footer User Profile */}
          <div className="pt-6 border-t border-border w-full flex flex-col items-center gap-4">
            <div
              onClick={() => setIsProfileOpen(true)}
              className="w-10 h-10 rounded-full bg-brand-primary text-white flex items-center justify-center font-bold text-sm cursor-pointer elevation-1 hover:opacity-90 transition-opacity"
              title="View & Edit Profile"
            >
              {user?.username?.charAt(0).toUpperCase() || 'U'}
            </div>
            <button
              onClick={() => logout()}
              className="text-text-muted hover:text-error transition-colors p-2 rounded-full hover:bg-error-soft cursor-pointer"
              title="Logout"
            >
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </aside>

      {/* ─── MOBILE SIDEBAR (Drawer) ─── */}
      <div className={`fixed inset-0 bg-black/20 backdrop-blur-sm z-40 lg:hidden transition-opacity ${mobileOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'}`} onClick={() => setMobileOpen(false)} />
      <aside className={`fixed inset-y-0 left-0 z-50 w-64 bg-white border-r border-border transform transition-transform duration-300 lg:hidden flex flex-col ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="p-6 flex items-center justify-between border-b border-border">
          <div className="flex items-center gap-3 text-brand-primary">
            <GraduationCap size={24} />
            <span className="font-bold text-lg">Indie-Tutor</span>
          </div>
          <button onClick={() => setMobileOpen(false)} className="p-2 text-text-muted hover:bg-bg-secondary rounded-lg">
            <X size={20} />
          </button>
        </div>
        <nav className="flex-1 p-4 flex flex-col gap-2 overflow-y-auto">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => {
            const isActive = location.pathname.startsWith(to)
            return (
              <NavLink
                key={to}
                to={to}
                onClick={() => setMobileOpen(false)}
                className={`flex items-center gap-3 px-4 py-3 rounded-xl font-medium transition-colors ${isActive ? 'bg-bg-secondary text-brand-primary' : 'text-text-secondary hover:bg-bg-primary hover:text-brand-primary'
                  }`}
              >
                <Icon size={20} className={isActive ? 'text-brand-primary' : 'text-text-muted'} />
                {label}
              </NavLink>
            )
          })}
        </nav>
      </aside>

      {/* ─── MAIN CONTENT CONTAINER ─── */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden relative">
        {/* Mobile Top Navbar */}
        <div className="lg:hidden px-4 h-16 bg-white border-b border-border flex items-center justify-between sticky top-0 z-30 elevation-1 shrink-0">
          <button
            onClick={() => setMobileOpen(true)}
            className="p-2 rounded-lg border border-border text-text-primary hover:bg-bg-secondary"
          >
            <Menu size={20} />
          </button>
          <div className="flex items-center gap-2 cursor-pointer font-bold text-brand-primary text-lg" onClick={() => navigate('/dashboard')}>
            Indie-Tutor
          </div>
          <div className="flex items-center gap-3">
            <span className={`w-2.5 h-2.5 rounded-full ${isOnline ? 'bg-success' : 'bg-error animate-ping'}`} title={isOnline ? 'API Connected' : 'API Offline'} />
            <button
              onClick={() => setIsProfileOpen(true)}
              className="w-8 h-8 rounded-full bg-brand-primary text-white flex items-center justify-center font-bold text-sm elevation-1"
            >
              {user?.username?.[0]?.toUpperCase() ?? 'U'}
            </button>
          </div>
        </div>

        {/* Network Warning Banner */}
        {!isOnline && (
          <div className="bg-warning-soft text-warning border-b border-warning/20 px-4 py-3 text-sm font-semibold flex items-center justify-between shrink-0">
            <div className="flex items-center gap-2">
              <WifiOff size={16} />
              <span>Backend server offline. Please check your connection.</span>
            </div>
            <button onClick={() => window.location.reload()} className="bg-warning text-white px-3 py-1.5 rounded-lg text-xs font-bold">
              Retry
            </button>
          </div>
        )}

        {/* Page Outlet */}
        <main className="flex-1 overflow-y-auto pb-20 lg:pb-0">
          <Outlet />
        </main>

        {/* Mobile Bottom Navigation (Optional/Fallback) */}
        <nav className="lg:hidden absolute bottom-0 left-0 right-0 bg-white/90 backdrop-blur-md border-t border-border px-4 py-2 flex items-center justify-around z-40 elevation-2 pb-safe">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => {
            const isActive = location.pathname.startsWith(to)
            return (
              <NavLink
                key={to}
                to={to}
                className={`flex flex-col items-center gap-1 py-1 px-3 rounded-xl transition-all ${isActive ? 'text-brand-primary scale-105' : 'text-text-muted hover:text-text-primary'
                  }`}
              >
                <Icon size={20} strokeWidth={isActive ? 2.5 : 2} />
                <span className={`text-[10px] font-medium ${isActive ? 'font-bold' : ''}`}>{label}</span>
              </NavLink>
            )
          })}
        </nav>
      </div>
    </div>
  )
}

