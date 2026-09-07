import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Mail, Lock, ArrowRight, Eye, EyeOff, Sparkles, GraduationCap, Globe, CheckCircle2, ShieldCheck } from 'lucide-react'
import { authApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'
import { clearAllUserData } from '../stores/authStore'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const { login } = useAuthStore()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await authApi.login(email, password)
      const { access_token, user } = res.data
      clearAllUserData()
      login(user, access_token)
      navigate('/dashboard')
    } catch (err: any) {
      if (!err.response || err.code === 'ERR_NETWORK' || err.response?.status >= 500) {
        setError('Network Error: Unable to connect to backend server. Please verify backend is running on port 8000.')
        return
      }
      setError(err.response?.data?.detail ?? 'Login failed. Please check your credentials and try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleLogin = () => {
    clearAllUserData()
    login(
      { id: 'google-user', username: 'Google Scholar', email: 'scholar.student@deeptutor.ai', role: 'student' },
      'demo-google-token'
    )
    navigate('/dashboard')
  }

  return (
    <div className="min-h-screen bg-[#FCF9F8] text-[#1B1C1C] font-serif flex items-center justify-center p-4 sm:p-8">
      {/* ─── Outer Archival Container Frame ─── */}
      <div className="w-full max-w-5xl bg-white rounded-3xl border border-[#E5E2D9] shadow-sm overflow-hidden flex flex-col lg:flex-row min-h-[620px]">
        
        {/* ─── LEFT COLUMN: Atmospheric Academic Banner ─── */}
        <div className="lg:w-5/12 bg-[#F6F3F0] border-b lg:border-b-0 lg:border-r border-[#E5E2D9] p-8 sm:p-10 flex flex-col justify-between relative overflow-hidden">
          {/* Subtle archival watermark pattern */}
          <div className="space-y-6 relative z-10">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-[#1B1C1C] text-white flex items-center justify-center font-bold text-sm shadow-xs">
                <GraduationCap size={18} />
              </div>
              <span className="font-serif font-bold text-lg text-[#1B1C1C] tracking-tight">DeepTutor</span>
            </div>

            <div className="pt-4 space-y-3">
              <span className="text-[11px] font-sans font-bold uppercase tracking-widest text-[#8C6212] bg-[#FDF6E9] border border-[#EBD5A2] px-2.5 py-1 rounded-full">
                Scholarly Inquiry
              </span>
              <h2 className="text-2xl sm:text-3xl font-bold text-[#1B1C1C] leading-snug font-serif italic">
                “Mastery is the consequence of continuous, grounded inquiry.”
              </h2>
              <p className="text-xs text-[#66645E] font-sans leading-relaxed">
                Connect directly with your course textbooks, structured lecture streams, and interactive study decks.
              </p>
            </div>
          </div>

          {/* Academic Disciplines & Math Card Preview */}
          <div className="space-y-4 pt-8 relative z-10 font-sans">
            <div className="flex flex-wrap gap-1.5 text-[11px]">
              <span className="px-2.5 py-1 rounded-md bg-white border border-[#E0DDD2] text-[#4A4843] font-medium">Computer Science</span>
              <span className="px-2.5 py-1 rounded-md bg-white border border-[#E0DDD2] text-[#4A4843] font-medium">Applied Physics</span>
              <span className="px-2.5 py-1 rounded-md bg-white border border-[#E0DDD2] text-[#4A4843] font-medium">Mathematics</span>
            </div>

            {/* Formula Preview Badge */}
            <div className="p-3.5 rounded-xl bg-white border border-[#E5E2D9] shadow-xs text-xs space-y-1">
              <div className="flex items-center justify-between text-[#7C7A74] text-[10px] font-mono">
                <span>FOUNDATIONAL MECHANICS</span>
                <span className="text-[#2E7D32] flex items-center gap-1"><ShieldCheck size={11} /> Grounded</span>
              </div>
              <div className="font-mono text-[#1B1C1C] font-bold text-center py-1">
                ∇ × E = -∂B/∂t
              </div>
            </div>
          </div>
        </div>

        {/* ─── RIGHT COLUMN: Sign In Form ─── */}
        <div className="lg:w-7/12 p-8 sm:p-12 flex flex-col justify-center bg-white">
          <div className="max-w-md w-full mx-auto space-y-6">
            <div className="space-y-1 text-left">
              <h1 className="text-2xl sm:text-3xl font-bold text-[#1B1C1C] font-serif">
                Return to Your Studies
              </h1>
              <p className="text-xs text-[#7C7A74] font-sans">
                Sign in to access your course materials, lecture streams, and flashcard decks.
              </p>
            </div>

            {/* Demo Hint Banner */}
            <div className="p-3 rounded-xl bg-[#FAF9F5] border border-[#ECE9DF] flex items-center gap-2.5 text-xs font-sans text-[#55534E]">
              <Sparkles size={14} className="text-[#996515] shrink-0" />
              <span>
                <strong>Quick Access:</strong> Enter any credentials or use Google Demo Sign-In.
              </span>
            </div>

            {error && (
              <div className="p-3 rounded-xl bg-[#FDF0EE] border border-[#E89E94] text-xs font-sans text-[#7D2218]">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4 font-sans text-xs">
              <div className="space-y-1.5 text-left">
                <label className="font-semibold text-[#4A4843]">Email Address</label>
                <div className="relative">
                  <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#8C8980]" />
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="student@university.edu"
                    className="w-full pl-10 pr-3 py-2.5 rounded-xl border border-[#DCD9CE] bg-[#FCF9F8] focus:bg-white focus:outline-none focus:border-[#1B1C1C] text-xs text-[#1B1C1C] transition-all"
                  />
                </div>
              </div>

              <div className="space-y-1.5 text-left">
                <div className="flex items-center justify-between">
                  <label className="font-semibold text-[#4A4843]">Password</label>
                  <a href="#forgot" onClick={(e) => { e.preventDefault(); alert("Please enter any test credentials in demo mode."); }} className="text-[11px] text-[#8C6212] hover:underline">
                    Forgot password?
                  </a>
                </div>
                <div className="relative">
                  <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#8C8980]" />
                  <input
                    type={showPass ? 'text' : 'password'}
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full pl-10 pr-10 py-2.5 rounded-xl border border-[#DCD9CE] bg-[#FCF9F8] focus:bg-white focus:outline-none focus:border-[#1B1C1C] text-xs text-[#1B1C1C] transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass(!showPass)}
                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-[#8C8980] hover:text-[#1B1C1C]"
                  >
                    {showPass ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 px-4 rounded-xl bg-[#1B1C1C] hover:bg-[#33322E] text-[#FCF9F8] font-semibold text-xs transition cursor-pointer shadow-xs flex items-center justify-center gap-2"
              >
                <span>{loading ? 'Authenticating...' : 'Sign In to DeepTutor'}</span>
                <ArrowRight size={14} />
              </button>
            </form>

            <div className="relative flex items-center justify-center my-4">
              <div className="border-t border-[#EFECE6] w-full" />
              <span className="bg-white px-3 text-[11px] text-[#8C8980] font-sans uppercase tracking-wider shrink-0">
                or continue with
              </span>
              <div className="border-t border-[#EFECE6] w-full" />
            </div>

            <button
              onClick={handleGoogleLogin}
              className="w-full py-2.5 px-4 rounded-xl border border-[#DCD9CE] bg-white hover:bg-[#FAF9F5] text-[#1B1C1C] text-xs font-semibold font-sans transition cursor-pointer flex items-center justify-center gap-2.5 shadow-xs"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
              </svg>
              <span>Continue with Google Scholar Demo</span>
            </button>

            <p className="text-center text-xs font-sans text-[#7C7A74] pt-2">
              New to DeepTutor?{' '}
              <Link to="/register" className="font-semibold text-[#1B1C1C] hover:underline">
                Create your academic workspace
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
