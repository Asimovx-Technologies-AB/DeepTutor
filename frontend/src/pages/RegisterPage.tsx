import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Mail, Lock, User, ArrowRight, Eye, EyeOff, Sparkles, GraduationCap, CheckCircle2, ShieldCheck } from 'lucide-react'
import { authApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'
import { clearAllUserData } from '../stores/authStore'

export default function RegisterPage() {
  const [form, setForm] = useState({ username: '', email: '', password: '', confirm: '' })
  const [showPass, setShowPass] = useState(false)
  const [agreeHonor, setAgreeHonor] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const { login } = useAuthStore()
  const navigate = useNavigate()

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  // Compute simple password strength
  const passLength = form.password.length
  const passStrength = passLength === 0 ? 0 : passLength < 6 ? 1 : passLength < 10 ? 2 : 3

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (form.password !== form.confirm) {
      setError('Passwords do not match. Please verify and re-enter.')
      return
    }
    if (!agreeHonor) {
      setError('Please accept the Academic Integrity pledge to continue.')
      return
    }
    setError('')
    setLoading(true)
    try {
      const res = await authApi.register({
        username: form.username,
        email: form.email,
        password: form.password,
      })
      const { access_token, user } = res.data
      clearAllUserData()
      login(user, access_token)
      navigate('/dashboard')
    } catch (err: any) {
      if (!err.response || err.code === 'ERR_NETWORK' || err.response?.status >= 500) {
        setError('Network Error: Unable to reach backend server. Please verify backend is running on port 8000.')
        return
      }
      setError(err.response?.data?.detail ?? 'Registration failed. Please check your information.')
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleSignup = () => {
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
      <div className="w-full max-w-5xl bg-white rounded-3xl border border-[#E5E2D9] shadow-sm overflow-hidden flex flex-col lg:flex-row min-h-[660px]">
        
        {/* ─── LEFT COLUMN: Atmospheric Academic Features Banner ─── */}
        <div className="lg:w-5/12 bg-[#F6F3F0] border-b lg:border-b-0 lg:border-r border-[#E5E2D9] p-8 sm:p-10 flex flex-col justify-between relative overflow-hidden">
          <div className="space-y-6 relative z-10">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-[#1B1C1C] text-white flex items-center justify-center font-bold text-sm shadow-xs">
                <GraduationCap size={18} />
              </div>
              <span className="font-serif font-bold text-lg text-[#1B1C1C] tracking-tight">DeepTutor</span>
            </div>

            <div className="pt-2 space-y-3">
              <span className="text-[11px] font-sans font-bold uppercase tracking-widest text-[#536257] bg-[#EDF3EE] border border-[#B8CCBB] px-2.5 py-1 rounded-full">
                Academic Integrity
              </span>
              <h2 className="text-2xl sm:text-3xl font-bold text-[#1B1C1C] leading-snug font-serif italic">
                “Your intellect deserves rigorous tools, not synthetic shortcuts.”
              </h2>
              <p className="text-xs text-[#66645E] font-sans leading-relaxed">
                Step into an AI learning sanctuary built strictly for serious STEM inquiry, first-principles table computation, and grounded concept mastery.
              </p>
            </div>
          </div>

          {/* Academic Features Checklist */}
          <div className="space-y-3 pt-6 relative z-10 font-sans text-xs">
            <div className="flex items-start gap-2.5 text-[#4A4843]">
              <CheckCircle2 size={15} className="text-[#2E7D32] shrink-0 mt-0.5" />
              <span>Grounded strictly in your course syllabus</span>
            </div>
            <div className="flex items-start gap-2.5 text-[#4A4843]">
              <CheckCircle2 size={15} className="text-[#2E7D32] shrink-0 mt-0.5" />
              <span>STEM table solver with zero omitted rows</span>
            </div>
            <div className="flex items-start gap-2.5 text-[#4A4843]">
              <CheckCircle2 size={15} className="text-[#2E7D32] shrink-0 mt-0.5" />
              <span>PyMuPDF diagram and circuit schematic grounding</span>
            </div>
            <div className="flex items-start gap-2.5 text-[#4A4843]">
              <CheckCircle2 size={15} className="text-[#2E7D32] shrink-0 mt-0.5" />
              <span>Claude-style minimalist study decks & quizzes</span>
            </div>

            <div className="mt-4 p-3 rounded-xl bg-white border border-[#E5E2D9] text-[11px] text-[#7C7A74] flex items-center gap-2">
              <ShieldCheck size={14} className="text-[#8C6212]" />
              <span>Used by researchers and scholars across STEM fields.</span>
            </div>
          </div>
        </div>

        {/* ─── RIGHT COLUMN: Registration Form ─── */}
        <div className="lg:w-7/12 p-8 sm:p-12 flex flex-col justify-center bg-white">
          <div className="max-w-md w-full mx-auto space-y-6">
            <div className="space-y-1 text-left">
              <h1 className="text-2xl sm:text-3xl font-bold text-[#1B1C1C] font-serif">
                Create Your Academic Workspace
              </h1>
              <p className="text-xs text-[#7C7A74] font-sans">
                Begin studying with your actual textbooks, lecture streams, and practice quizzes.
              </p>
            </div>

            {error && (
              <div className="p-3 rounded-xl bg-[#FDF0EE] border border-[#E89E94] text-xs font-sans text-[#7D2218]">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-3.5 font-sans text-xs">
              <div className="space-y-1 text-left">
                <label className="font-semibold text-[#4A4843]">Full Name</label>
                <div className="relative">
                  <User size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#8C8980]" />
                  <input
                    type="text"
                    required
                    value={form.username}
                    onChange={(e) => set('username', e.target.value)}
                    placeholder="Ada Lovelace"
                    className="w-full pl-10 pr-3 py-2 rounded-xl border border-[#DCD9CE] bg-[#FCF9F8] focus:bg-white focus:outline-none focus:border-[#1B1C1C] text-xs text-[#1B1C1C] transition-all"
                  />
                </div>
              </div>

              <div className="space-y-1 text-left">
                <label className="font-semibold text-[#4A4843]">Academic Email Address</label>
                <div className="relative">
                  <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#8C8980]" />
                  <input
                    type="email"
                    required
                    value={form.email}
                    onChange={(e) => set('email', e.target.value)}
                    placeholder="student@university.edu"
                    className="w-full pl-10 pr-3 py-2 rounded-xl border border-[#DCD9CE] bg-[#FCF9F8] focus:bg-white focus:outline-none focus:border-[#1B1C1C] text-xs text-[#1B1C1C] transition-all"
                  />
                </div>
              </div>

              <div className="space-y-1 text-left">
                <label className="font-semibold text-[#4A4843]">Password</label>
                <div className="relative">
                  <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#8C8980]" />
                  <input
                    type={showPass ? 'text' : 'password'}
                    required
                    value={form.password}
                    onChange={(e) => set('password', e.target.value)}
                    placeholder="Minimum 6 characters"
                    className="w-full pl-10 pr-10 py-2 rounded-xl border border-[#DCD9CE] bg-[#FCF9F8] focus:bg-white focus:outline-none focus:border-[#1B1C1C] text-xs text-[#1B1C1C] transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass(!showPass)}
                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-[#8C8980] hover:text-[#1B1C1C]"
                  >
                    {showPass ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
                {/* Subtle Password Strength Indicator */}
                {form.password && (
                  <div className="flex items-center gap-1.5 pt-1">
                    <div className={`h-1 flex-1 rounded-full ${passStrength >= 1 ? 'bg-amber-400' : 'bg-slate-200'}`} />
                    <div className={`h-1 flex-1 rounded-full ${passStrength >= 2 ? 'bg-[#86C995]' : 'bg-slate-200'}`} />
                    <div className={`h-1 flex-1 rounded-full ${passStrength >= 3 ? 'bg-[#2E7D32]' : 'bg-slate-200'}`} />
                    <span className="text-[10px] text-[#7C7A74] pl-1">
                      {passStrength === 1 ? 'Weak' : passStrength === 2 ? 'Medium' : 'Strong'}
                    </span>
                  </div>
                )}
              </div>

              <div className="space-y-1 text-left">
                <label className="font-semibold text-[#4A4843]">Confirm Password</label>
                <div className="relative">
                  <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#8C8980]" />
                  <input
                    type={showPass ? 'text' : 'password'}
                    required
                    value={form.confirm}
                    onChange={(e) => set('confirm', e.target.value)}
                    placeholder="Re-enter password"
                    className="w-full pl-10 pr-3 py-2 rounded-xl border border-[#DCD9CE] bg-[#FCF9F8] focus:bg-white focus:outline-none focus:border-[#1B1C1C] text-xs text-[#1B1C1C] transition-all"
                  />
                </div>
              </div>

              {/* Honor Code Pledge */}
              <div className="flex items-center gap-2 pt-1 text-left">
                <input
                  type="checkbox"
                  id="honor-code"
                  checked={agreeHonor}
                  onChange={(e) => setAgreeHonor(e.target.checked)}
                  className="rounded border-[#DCD9CE] text-[#1B1C1C] focus:ring-0 cursor-pointer"
                />
                <label htmlFor="honor-code" className="text-[11px] text-[#66645E] cursor-pointer">
                  I commit to academic integrity and using DeepTutor for grounded mastery.
                </label>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 px-4 rounded-xl bg-[#1B1C1C] hover:bg-[#33322E] text-[#FCF9F8] font-semibold text-xs transition cursor-pointer shadow-xs flex items-center justify-center gap-2 mt-2"
              >
                <span>{loading ? 'Creating Workspace...' : 'Create Academic Workspace'}</span>
                <ArrowRight size={14} />
              </button>
            </form>

            <div className="relative flex items-center justify-center my-3">
              <div className="border-t border-[#EFECE6] w-full" />
              <span className="bg-white px-3 text-[11px] text-[#8C8980] font-sans uppercase tracking-wider shrink-0">
                or continue with
              </span>
              <div className="border-t border-[#EFECE6] w-full" />
            </div>

            <button
              onClick={handleGoogleSignup}
              className="w-full py-2.5 px-4 rounded-xl border border-[#DCD9CE] bg-white hover:bg-[#FAF9F5] text-[#1B1C1C] text-xs font-semibold font-sans transition cursor-pointer flex items-center justify-center gap-2.5 shadow-xs"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
              </svg>
              <span>Sign up with Google Scholar Demo</span>
            </button>

            <p className="text-center text-xs font-sans text-[#7C7A74] pt-1">
              Already have an academic account?{' '}
              <Link to="/login" className="font-semibold text-[#1B1C1C] hover:underline">
                Sign in
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
