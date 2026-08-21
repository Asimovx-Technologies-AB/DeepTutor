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
  Award,
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
    <div className="flex h-screen bg-[#FAF8F3] overflow-hidden text-[#20201D] font-sans antialiased">
      {/* Profile Modal */}
      <ProfileModal isOpen={isProfileOpen} onClose={() => setIsProfileOpen(false)} />
      {/* Upgrade Modal */}
      <UpgradeModal isOpen={isUpgradeOpen} onClose={() => setIsUpgradeOpen(false)} />
      {/* Confirm Delete Modal */}
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


      {/* ─── LEFT SIDEBAR NAVIGATION ─── */}
      <aside
        className={`fixed lg:static inset-y-0 left-0 z-50 w-72 bg-white border-r border-[#E7E1D8] flex flex-col justify-between shadow-2xl lg:shadow-none transition-transform duration-300 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        {/* Top Header Logo */}
        <div className="p-6 border-b border-[#E7E1D8]/60 flex items-center justify-between">
          <div className="flex items-center gap-3 cursor-pointer" onClick={() => navigate('/dashboard')}>
            <div className="w-9 h-9 rounded-xl bg-[#FFF0E4] border border-[#F28A45]/30 flex items-center justify-center p-1.5 shadow-2xs">
              <div className="grid grid-cols-2 gap-1 w-full h-full">
                <div className="bg-[#F28A45] rounded-xs" />
                <div className="bg-[#4F8A68] rounded-xs" />
                <div className="bg-[#D99A32] rounded-xs" />
                <div className="bg-[#A99BCB] rounded-xs" />
              </div>
            </div>
            <div>
              <span className="font-extrabold text-lg text-[#20201D] tracking-tight block leading-none">
                DeepTutor
              </span>
              <span className="text-[10px] text-[#F28A45] font-extrabold uppercase tracking-widest mt-0.5 block">
                AI Learning Platform
              </span>
            </div>
          </div>
          <button
            onClick={() => setMobileOpen(false)}
            className="lg:hidden text-[#969188] hover:text-[#20201D] p-1.5 rounded-xl hover:bg-[#F4EFE7]"
          >
            <X size={18} />
          </button>
        </div>

        {/* Middle Navigation Items */}
        <div className="flex-1 px-4 py-5 overflow-y-auto space-y-6">
          <div>
            <nav className="space-y-1.5">
              {NAV_ITEMS.map(({ to, icon: Icon, label, badge }) => {
                const isActive = location.pathname.startsWith(to)
                const isChat = to === '/chat'
                const isSubject = to === '/subjects'
                const learnSessions = sessions.filter(
                  (s) => !s.topic_id?.startsWith('sslc-') &&
                         !s.topic_id?.startsWith('math-') &&
                         !s.topic_id?.startsWith('phys-') &&
                         !s.topic_id?.startsWith('chem-')
                )

                return (
                  <div key={to} className="space-y-1.5">
                    <NavLink
                      to={to}
                      onClick={() => setMobileOpen(false)}
                      className={`flex items-center justify-between px-4 py-3 rounded-2xl text-[15px] leading-[22px] transition-all group ${
                        isActive
                          ? 'bg-[#FFF0E4] text-[#F28A45] font-semibold shadow-xs'
                          : 'text-[#6F6B63] font-medium hover:text-[#20201D] hover:bg-[#F4EFE7]'
                      }`}
                    >
                      <div className="flex items-center gap-3.5">
                        <Icon
                          size={20}
                          className={isActive ? 'text-[#F28A45]' : 'text-[#969188] group-hover:text-[#20201D] transition-colors'}
                        />
                        <span>{label}</span>
                      </div>

                      {badge ? (
                        <span
                          className={`text-[11px] font-extrabold px-2 py-0.5 rounded-full ${
                            isActive
                              ? 'bg-[#F28A45] text-white'
                              : 'bg-[#F4EFE7] text-[#6F6B63] border border-[#E7E1D8]'
                          }`}
                        >
                          {badge}
                        </span>
                      ) : isActive ? (
                        <ChevronRight size={16} className="text-[#F28A45]" />
                      ) : null}
                    </NavLink>

                    {/* Learn History Sub-panel (Only for custom uploaded documents) */}
                    {isChat && isActive && (
                      <div className="ml-3 pl-3 border-l-2 border-[#F28A45]/30 space-y-3 pt-2 pb-1">
                        {/* New Chat Button */}
                        <button
                          onClick={() => {
                            setActiveSession(null)
                            navigate('/chat')
                            setMobileOpen(false)
                          }}
                          className="w-full btn-primary font-bold text-xs py-2.5 px-3 rounded-xl flex items-center justify-center gap-2 shadow-2xs transition-all active:scale-[0.98] cursor-pointer"
                        >
                          <Plus size={15} />
                          <span>New Document Chat</span>
                        </button>

                        {/* History Header & List */}
                        <div className="space-y-1">
                          <p className="px-2 text-[10px] font-black text-[#969188] uppercase tracking-wider">
                            Document Chat History
                          </p>

                          {learnSessions.length === 0 ? (
                            <p className="px-2 py-1 text-xs text-[#969188] italic">No document chats yet</p>
                          ) : (
                            learnSessions.slice(0, 6).map((s) => {
                              const isSelected = activeSession?.id === s.id
                              return (
                                <div
                                  key={s.id}
                                  onClick={() => {
                                    navigate(`/chat/${s.id}`)
                                    setMobileOpen(false)
                                  }}
                                  className={`group flex items-center justify-between px-2.5 py-2 rounded-xl text-xs cursor-pointer transition-all ${
                                    isSelected
                                      ? 'bg-white text-[#F28A45] font-black border border-[#F28A45]/30 shadow-2xs'
                                      : 'text-[#6F6B63] hover:text-[#20201D] hover:bg-[#F4EFE7] font-semibold'
                                  }`}
                                >
                                  <div className="flex items-center gap-2 min-w-0 pr-1">
                                    <FileText size={13} className={isSelected ? 'text-[#F28A45]' : 'text-[#969188]'} />
                                    <span className="truncate">{s.session_title || 'Untitled Session'}</span>
                                  </div>
                                  <button
                                    onClick={(e) => handleDeleteSession(e, s.id)}
                                    className="opacity-0 group-hover:opacity-100 text-[#969188] hover:text-[#C85C52] p-1 rounded transition-opacity"
                                    title="Delete chat"
                                  >
                                    <Trash2 size={12} />
                                  </button>
                                </div>
                              )
                            })
                          )}
                        </div>
                      </div>
                    )}

                    {/* My Subjects Sub-panel (Direct AI Tutor shortcuts) */}
                    {isSubject && isActive && (
                      <div className="ml-3 pl-3 border-l-2 border-[#D97706]/30 space-y-2 pt-2 pb-1">
                        <p className="px-2 text-[10px] font-black text-[#969188] uppercase tracking-wider">
                          Class 10 AI Tutors
                        </p>
                        <div className="space-y-1">
                          <button
                            onClick={() => {
                              navigate('/subjects/sslc-math/chat')
                              setMobileOpen(false)
                            }}
                            className={`w-full text-left px-2.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
                              location.pathname.includes('/sslc-math')
                                ? 'bg-white text-[#D97706] border border-[#D97706]/30 shadow-2xs'
                                : 'text-[#6F6B63] hover:text-[#20201D] hover:bg-[#F4EFE7]'
                            }`}
                          >
                            <span>📐</span>
                            <span className="truncate">Mathematics Tutor</span>
                          </button>

                          <button
                            onClick={() => {
                              navigate('/subjects/sslc-physics/chat')
                              setMobileOpen(false)
                            }}
                            className={`w-full text-left px-2.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
                              location.pathname.includes('/sslc-physics')
                                ? 'bg-white text-[#0284C7] border border-[#0284C7]/30 shadow-2xs'
                                : 'text-[#6F6B63] hover:text-[#20201D] hover:bg-[#F4EFE7]'
                            }`}
                          >
                            <span>⚡</span>
                            <span className="truncate">Physics Tutor</span>
                          </button>

                          <button
                            onClick={() => {
                              navigate('/subjects/sslc-chemistry/chat')
                              setMobileOpen(false)
                            }}
                            className={`w-full text-left px-2.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
                              location.pathname.includes('/sslc-chemistry')
                                ? 'bg-white text-[#059669] border border-[#059669]/30 shadow-2xs'
                                : 'text-[#6F6B63] hover:text-[#20201D] hover:bg-[#F4EFE7]'
                            }`}
                          >
                            <span>🧪</span>
                            <span className="truncate">Chemistry Tutor</span>
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </nav>
          </div>
        </div>

        {/* Sidebar Footer User Profile */}
        <div className="p-4 border-t border-[#E7E1D8]/60 bg-[#FAF8F3]">
          <div className="flex items-center justify-between">
            <div
              onClick={() => setIsProfileOpen(true)}
              className="flex items-center gap-3 cursor-pointer hover:opacity-80 transition-opacity min-w-0"
              title="View & Edit Profile"
            >
              <div className="w-9 h-9 rounded-full bg-[#20201D] text-white flex items-center justify-center font-extrabold text-xs flex-shrink-0 shadow-2xs">
                {user?.username?.[0]?.toUpperCase() ?? 'A'}
              </div>
              <div className="min-w-0">
                <p className="text-xs font-extrabold text-[#20201D] truncate">{user?.username || 'Adwaid'}</p>
                <p className="text-[11px] text-[#969188] truncate">{user?.email || 'adwaid08@gmail.com'}</p>
              </div>
            </div>

            <button
              onClick={handleLogout}
              className="text-[#969188] hover:text-[#C85C52] transition-colors p-1.5 rounded-xl hover:bg-[#FBE7E4] flex-shrink-0 cursor-pointer"
              title="Logout"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      {/* ─── MAIN CONTENT CONTAINER ─── */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Mobile top navbar toggle */}
        <div className="md:hidden p-4 bg-white border-b border-[#E7E1D8] flex items-center justify-between sticky top-0 z-30 elevation-1">
          <button
            onClick={() => setMobileOpen(true)}
            className="p-2 rounded-xl border border-[#E7E1D8] text-[#20201D] hover:bg-[#F4EFE7]"
          >
            <Menu size={18} />
          </button>
          <div className="flex items-center gap-2 cursor-pointer" onClick={() => navigate('/dashboard')}>
            <span className="font-black text-base text-[#20201D]">DeepTutor</span>
          </div>
          <div className="flex items-center gap-2">
            <span className={`w-2.5 h-2.5 rounded-full ${isOnline ? 'bg-[#4F8A68]' : 'bg-[#C85C52] animate-ping'}`} title={isOnline ? 'API Connected' : 'API Offline'} />
            <button
              onClick={handleLogout}
              className="w-8 h-8 rounded-full bg-[#F28A45] text-white flex items-center justify-center font-extrabold text-xs shadow-xs"
            >
              {user?.username?.[0]?.toUpperCase() ?? 'A'}
            </button>
          </div>
        </div>

        {/* Network Warning Banner */}
        {!isOnline && (
          <div className="bg-[#FFF3D8] text-[#D99A32] border-b border-[#E7E1D8] px-4 py-2 text-xs font-bold flex items-center justify-between">
            <div className="flex items-center gap-2">
              <WifiOff size={14} />
              <span>Network Warning: Backend server offline. Start http://localhost:8000.</span>
            </div>
            <button
              onClick={() => window.location.reload()}
              className="bg-[#D99A32] text-white px-2.5 py-1 rounded-lg text-[11px] font-extrabold"
            >
              Retry
            </button>
          </div>
        )}

        {/* Page Outlet */}
        <main className="flex-1 overflow-y-auto bg-[#FAF8F3] pb-16 lg:pb-0">
          <Outlet />
        </main>

        {/* ─── MOBILE BOTTOM QUICK NAVIGATION BAR ─── */}
        <nav className="lg:hidden fixed bottom-0 left-0 right-0 bg-[#FAF8F3]/95 backdrop-blur-md border-t border-[#E7E1D8] py-2 px-3 flex items-center justify-around z-40 shadow-lg">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => {
            const isActive = location.pathname.startsWith(to)
            return (
              <NavLink
                key={to}
                to={to}
                className={`flex flex-col items-center gap-1 py-1 px-3 rounded-xl transition-all ${isActive ? 'text-[#F28A45] font-extrabold scale-105' : 'text-[#969188] font-semibold hover:text-[#20201D]'
                  }`}
              >
                <Icon size={18} />
                <span className="text-[10px]">{label}</span>
              </NavLink>
            )
          })}
        </nav>
      </div>
    </div>
  )
}

