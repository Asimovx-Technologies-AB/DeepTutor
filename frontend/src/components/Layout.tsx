import { useState } from 'react'
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
  Bot
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useChatStore } from '../stores/chatStore'

const NAV_ITEMS = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard', badge: null },
  { to: '/study-plan', icon: Calendar, label: 'Study Plan', badge: 'AI' },
  { to: '/chat', icon: MessageSquare, label: 'AI Tutor', badge: 'Live' },
  { to: '/progress', icon: BarChart3, label: 'Progress', badge: null },
]

export default function Layout() {
  const { user, logout } = useAuthStore()
  const sessions = useChatStore((s) => s.sessions)
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="flex h-screen bg-[#f8fafc] overflow-hidden font-sans text-slate-800">
      {/* Mobile backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-40 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* ─── LEFT SIDEBAR NAV ─── */}
      <aside
        className={`fixed lg:static inset-y-0 left-0 z-50 w-64 bg-white border-r border-slate-200/80 flex flex-col justify-between transition-transform duration-300 ${mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
          }`}
      >
        {/* Top Header / Logo */}
        <div className="p-5 flex items-center justify-between border-b border-slate-100">
          <div
            className="flex items-center gap-3 cursor-pointer group"
            onClick={() => navigate('/dashboard')}
          >
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-indigo-600 via-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/20 group-hover:scale-105 transition-transform">
              <GraduationCap size={20} className="text-white" />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-black text-base text-slate-900 tracking-tight">DeepTutor</span>
                <span className="text-[9px] font-black uppercase tracking-wider bg-indigo-50 text-indigo-600 px-1.5 py-0.5 rounded-md border border-indigo-100">
                  AI
                </span>
              </div>
              <p className="text-[10px] text-slate-400 font-medium">GraphRAG Study Engine</p>
            </div>
          </div>

          <button
            onClick={() => setMobileOpen(false)}
            className="lg:hidden text-slate-400 hover:text-slate-600 p-1"
          >
            <X size={18} />
          </button>
        </div>

        {/* Middle Navigation Items */}
        <div className="flex-1 px-3.5 py-5 overflow-y-auto space-y-6">
          <div>
            <p className="px-3 text-[10px] font-extrabold text-slate-400 uppercase tracking-widest mb-2.5">
              Navigation
            </p>
            <nav className="space-y-1">
              {NAV_ITEMS.map(({ to, icon: Icon, label, badge }) => {
                const isActive = location.pathname.startsWith(to)
                return (
                  <NavLink
                    key={to}
                    to={to}
                    onClick={() => setMobileOpen(false)}
                    className={`flex items-center justify-between px-3.5 py-2.5 rounded-2xl text-xs font-bold transition-all group ${isActive
                        ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/20'
                        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/80'
                      }`}
                  >
                    <div className="flex items-center gap-3">
                      <Icon
                        size={17}
                        className={isActive ? 'text-white' : 'text-slate-400 group-hover:text-indigo-600 transition-colors'}
                      />
                      <span>{label}</span>
                    </div>

                    {badge ? (
                      <span
                        className={`text-[9px] font-extrabold px-1.5 py-0.5 rounded-full ${isActive
                            ? 'bg-white/20 text-white'
                            : 'bg-emerald-50 text-emerald-600 border border-emerald-100'
                          }`}
                      >
                        {badge}
                      </span>
                    ) : isActive ? (
                      <ChevronRight size={14} className="text-white/70" />
                    ) : null}
                  </NavLink>
                )
              })}
            </nav>
          </div>

          {/* Quick Action Widget in Sidebar */}
          <div className="p-3.5 bg-gradient-to-br from-indigo-50/80 via-slate-50 to-violet-50/80 border border-indigo-100/80 rounded-2xl space-y-2.5">
            <div className="flex items-center gap-2">
              <Zap size={14} className="text-indigo-600" />
              <span className="text-xs font-bold text-slate-800">Quick Tutor Chat</span>
            </div>
            <p className="text-[11px] text-slate-500 leading-tight">
              Have a study question? Ask Ollama AI tutor directly.
            </p>
            <button
              onClick={() => {
                setMobileOpen(false)
                navigate('/chat')
              }}
              className="w-full btn-primary py-2 text-xs flex items-center justify-center gap-1.5 shadow-sm"
            >
              <Bot size={13} /> Start New Chat
            </button>
          </div>
        </div>

        {/* Bottom User Profile Section */}
        <div className="p-3.5 border-t border-slate-100 bg-slate-50/50">
          <div className="flex items-center justify-between p-2 rounded-2xl bg-white border border-slate-200/60 shadow-sm">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white flex items-center justify-center font-black text-xs shadow-inner flex-shrink-0">
                {user?.username?.[0]?.toUpperCase() ?? 'U'}
              </div>
              <div className="min-w-0">
                <p className="text-xs font-bold text-slate-800 truncate">{user?.username}</p>
                <p className="text-[10px] text-slate-400 truncate">{user?.email}</p>
              </div>
            </div>

            <button
              onClick={handleLogout}
              className="text-slate-400 hover:text-rose-600 transition-colors p-1.5 rounded-xl hover:bg-rose-50 flex-shrink-0"
              title="Logout"
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </aside>

      {/* ─── MAIN CONTENT CONTAINER ─── */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Mobile top navbar toggle */}
        <div className="lg:hidden p-4 bg-white border-b border-slate-200 flex items-center justify-between">
          <button
            onClick={() => setMobileOpen(true)}
            className="p-2 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50"
          >
            <Menu size={18} />
          </button>
          <div className="flex items-center gap-2" onClick={() => navigate('/dashboard')}>
            <GraduationCap size={18} className="text-indigo-600" />
            <span className="font-black text-sm">Adhyapika AI</span>
          </div>
          <div className="w-8 h-8 rounded-full bg-indigo-50 flex items-center justify-center font-bold text-xs text-indigo-600">
            {user?.username?.[0]?.toUpperCase() ?? 'U'}
          </div>
        </div>

        {/* Page Outlet */}
        <main className="flex-1 overflow-y-auto bg-[#f8fafc]">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
