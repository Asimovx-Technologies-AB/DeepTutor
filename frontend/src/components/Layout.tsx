import { useState, useEffect } from 'react'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Calendar,
  MessageSquare,
  BarChart3,
  LogOut,
  GraduationCap,
  ChevronRight,
  Menu,
  X,
  Zap,
  Bot,
  Sparkles,
  Trophy,
  Wifi,
  WifiOff
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useChatStore } from '../stores/chatStore'
import { healthApi } from '../services/api'

const NAV_ITEMS = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard', badge: null },
  { to: '/study-plan', icon: Calendar, label: 'Study Plan', badge: 'AI' },
  { to: '/chat', icon: MessageSquare, label: 'AI Tutor', badge: 'Live' },
  { to: '/leaderboard', icon: Trophy, label: 'Leaderboard', badge: 'TOP' },
  { to: '/progress', icon: BarChart3, label: 'Progress', badge: null },
]

export default function Layout() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [isOnline, setIsOnline] = useState<boolean>(true)

  // Periodic Network Connection Health Check
  useEffect(() => {
    const checkBackend = async () => {
      try {
        await healthApi.check()
        setIsOnline(true)
      } catch {
        setIsOnline(false)
      }
    }
    checkBackend()
    const timer = setInterval(checkBackend, 15000)
    return () => clearInterval(timer)
  }, [])

  const handleLogout = () => {
    logout()
    navigate('/')
  }

  return (
    <div className="flex h-screen bg-[#f8fafc] overflow-hidden font-sans text-slate-800 flex-col lg:flex-row">
      {/* Mobile backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-40 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* ─── LEFT SIDEBAR NAV ─── */}
      <aside
        className={`fixed lg:static inset-y-0 left-0 z-50 w-80 bg-white border-r border-slate-200/80 flex flex-col justify-between transition-transform duration-300 ${mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
          }`}
      >
        {/* Top Header / Logo */}
        <div className="p-6 flex items-center justify-between border-b border-slate-100">
          <div
            className="flex items-center gap-3.5 cursor-pointer group"
            onClick={() => navigate('/dashboard')}
          >
            <div className="w-12 h-12 rounded-2xl bg-[#111111] flex items-center justify-center text-white shadow-sm transition-transform active:scale-95">
              <GraduationCap size={24} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-black text-lg text-slate-900 tracking-tight">DeepTutor</span>
                <span className="text-[10px] font-extrabold uppercase tracking-wider bg-[#f4f4f5] text-[#18181b] px-2 py-0.5 rounded-full border border-[#e4e4e7]">
                  AI
                </span>
              </div>
              <p className="text-xs text-slate-400 font-semibold mt-0.5">GraphRAG Study Engine</p>
            </div>
          </div>

          <button
            onClick={() => setMobileOpen(false)}
            className="lg:hidden text-slate-400 hover:text-slate-600 p-1.5 rounded-xl hover:bg-slate-100"
          >
            <X size={20} />
          </button>
        </div>

        {/* Middle Navigation Items */}
        <div className="flex-1 px-4 py-6 overflow-y-auto space-y-7">
          <div>
            <p className="px-3.5 text-xs font-extrabold text-slate-400 uppercase tracking-widest mb-3">
              Navigation
            </p>
            <nav className="space-y-1.5">
              {NAV_ITEMS.map(({ to, icon: Icon, label, badge }) => {
                const isActive = location.pathname.startsWith(to)
                return (
                  <NavLink
                    key={to}
                    to={to}
                    onClick={() => setMobileOpen(false)}
                    className={`flex items-center justify-between px-4 py-3 rounded-2xl text-sm font-extrabold transition-all group ${isActive
                      ? 'bg-[#111111] text-white shadow-sm'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-[#f4f4f5]'
                      }`}
                  >
                    <div className="flex items-center gap-3.5">
                      <Icon
                        size={20}
                        className={isActive ? 'text-white' : 'text-slate-400 group-hover:text-slate-900 transition-colors'}
                      />
                      <span>{label}</span>
                    </div>

                    {badge ? (
                      <span
                        className={`text-xs font-extrabold px-2 py-0.5 rounded-full ${isActive
                          ? 'bg-white/20 text-white'
                          : 'bg-[#f4f4f5] text-[#18181b] border border-[#e4e4e7]'
                          }`}
                      >
                        {badge}
                      </span>
                    ) : isActive ? (
                      <ChevronRight size={16} className="text-white/80" />
                    ) : null}
                  </NavLink>
                )
              })}
            </nav>
          </div>

          {/* Quick Action Widget & Network Monitor */}
          <div className="p-4 bg-[#fafafa] border border-[#e4e4e7] rounded-2xl space-y-3 shadow-sm">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Zap size={16} className="text-[#111111]" />
                <span className="text-sm font-extrabold text-slate-900">Network & API</span>
              </div>
              <span className={`flex items-center gap-1 text-[10px] font-extrabold px-2 py-0.5 rounded-full ${isOnline ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-rose-50 text-rose-700 border border-rose-200 animate-pulse'
                }`}>
                {isOnline ? <Wifi size={10} /> : <WifiOff size={10} />}
                {isOnline ? 'ONLINE' : 'OFFLINE'}
              </span>
            </div>
            <p className="text-xs text-slate-500 leading-relaxed font-medium">
              {isOnline ? 'Connected to local FastAPI backend & Ollama engine.' : 'Backend disconnected. Verify http://localhost:8000 is running.'}
            </p>
            <button
              onClick={() => {
                useChatStore.getState().setActiveSession(null)
                useChatStore.getState().setMessages([])
                setMobileOpen(false)
                navigate('/chat')
              }}
              className="w-full btn-primary py-2.5 text-xs font-extrabold flex items-center justify-center gap-2 shadow-sm active:scale-95"
            >
              <Bot size={15} /> Start New Chat
            </button>
          </div>
        </div>

        {/* Bottom User Profile Section */}
        <div className="p-4 border-t border-slate-100 bg-[#fafafa]">
          <div className="flex items-center justify-between p-2.5 rounded-2xl bg-white border border-[#e4e4e7] shadow-sm">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-10 h-10 rounded-xl bg-[#111111] text-white flex items-center justify-center font-black text-sm shadow-sm flex-shrink-0">
                {user?.username?.[0]?.toUpperCase() ?? 'U'}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-extrabold text-slate-800 truncate">{user?.username}</p>
                <p className="text-xs text-slate-400 truncate">{user?.email}</p>
              </div>
            </div>

            <button
              onClick={handleLogout}
              className="text-slate-400 hover:text-rose-600 transition-colors p-2 rounded-xl hover:bg-rose-50 flex-shrink-0"
              title="Logout"
            >
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </aside>

      {/* ─── MAIN CONTENT CONTAINER ─── */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Mobile top navbar toggle */}
        <div className="lg:hidden p-4 bg-white border-b border-slate-200 flex items-center justify-between sticky top-0 z-30 shadow-sm">
          <button
            onClick={() => setMobileOpen(true)}
            className="p-2 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50"
          >
            <Menu size={18} />
          </button>
          <div className="flex items-center gap-2 cursor-pointer" onClick={() => navigate('/dashboard')}>
            <GraduationCap size={20} className="text-indigo-600" />
            <span className="font-black text-base text-slate-900">DeepTutor AI</span>
          </div>
          <div className="flex items-center gap-2">
            <span className={`w-2.5 h-2.5 rounded-full ${isOnline ? 'bg-emerald-500' : 'bg-rose-500 animate-ping'}`} title={isOnline ? 'API Connected' : 'API Offline'} />
            <button
              onClick={() => {
                if (window.confirm(`Logged in as "${user?.username || user?.email}". Would you like to log out and switch accounts?`)) {
                  handleLogout()
                }
              }}
              className="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center font-extrabold text-xs shadow-sm hover:opacity-90 active:scale-95 cursor-pointer"
              title={`Logged in as ${user?.username} (${user?.email}). Click to Logout / Switch Account`}
            >
              {user?.username?.[0]?.toUpperCase() ?? 'U'}
            </button>
          </div>
        </div>

        {/* Offline Alert Banner if Backend standard call fails */}
        {!isOnline && (
          <div className="bg-amber-500 text-white px-4 py-2 text-xs font-bold flex items-center justify-between shadow-inner">
            <div className="flex items-center gap-2">
              <WifiOff size={14} />
              <span>Network Warning: Unable to reach backend server. Make sure FastAPI server (`start.bat`) is running on port 8000.</span>
            </div>
            <button
              onClick={() => window.location.reload()}
              className="bg-white/20 hover:bg-white/30 text-white px-2.5 py-1 rounded-lg text-[11px] font-extrabold"
            >
              Retry
            </button>
          </div>
        )}

        {/* Page Outlet */}
        <main className="flex-1 overflow-y-auto bg-[#f8fafc] pb-16 lg:pb-0">
          <Outlet />
        </main>

        {/* ─── MOBILE BOTTOM QUICK NAVIGATION BAR ─── */}
        <nav className="lg:hidden fixed bottom-0 left-0 right-0 bg-white/95 backdrop-blur-md border-t border-slate-200 py-2 px-3 flex items-center justify-around z-40 shadow-lg">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => {
            const isActive = location.pathname.startsWith(to)
            return (
              <NavLink
                key={to}
                to={to}
                className={`flex flex-col items-center gap-1 py-1 px-3 rounded-xl transition-all ${isActive ? 'text-indigo-600 font-extrabold scale-105' : 'text-slate-400 font-semibold hover:text-slate-600'
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
