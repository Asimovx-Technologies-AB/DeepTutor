import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Mail, Lock, User, ArrowRight, Eye, EyeOff, Sparkles, Brain, Globe, Send } from 'lucide-react'
import { authApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'

export default function RegisterPage() {
  const [form, setForm] = useState({ username: '', email: '', password: '', confirm: '' })
  const [showPass, setShowPass] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const { login } = useAuthStore()
  const navigate = useNavigate()

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (form.password !== form.confirm) {
      setError('Passwords do not match')
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
      login(user, access_token)
      navigate('/dashboard')
    } catch (err: any) {
      if (!err.response || err.code === 'ERR_NETWORK' || err.response?.status >= 500) {
        setError('Network Error: Unable to reach FastAPI backend server. Please verify backend is running.')
        return
      }
      setError(err.response?.data?.detail ?? 'Registration failed.')
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleSignup = () => {
    login(
      { id: 'google-user', username: 'Google Learner', email: 'google.student@deeptutor.ai', role: 'student' },
      'demo-google-token'
    )
    navigate('/dashboard')
  }

  return (
    <div className="min-h-screen bg-[#F7F7F7] flex items-center justify-center p-4 sm:p-8 font-sans">
      
      {/* Outer Card Frame */}
      <div className="w-full max-w-5xl bg-[#E5E5E5] rounded-[36px] border border-[#E2E8F0] elevation-1 p-6 sm:p-10 flex flex-col justify-between min-h-[640px] relative overflow-hidden">
        
        {/* Top Header Navigation */}
        <header className="flex items-center justify-between z-10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-[1.5rem] bg-[#DDF4FF] border border-[#1CB0F6]/30 flex items-center justify-center text-[#1CB0F6] elevation-1">
              <Brain size={22} />
            </div>
            <div>
              <span className="font-black text-[#3C3C3C] text-xl tracking-tight">Indie-Tutor</span>
              <span className="block text-[10px] font-black text-[#1CB0F6] uppercase tracking-widest">AI Learning Engine</span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button className="w-10 h-10 rounded-full border border-[#E2E8F0] bg-white text-[#777777] hover:text-[#1CB0F6] hover:border-[#1CB0F6]/30 flex items-center justify-center transition-all elevation-1 cursor-pointer">
              <Globe size={18} />
            </button>
            <button className="w-10 h-10 rounded-full bg-[#3C3C3C] text-white hover:bg-black flex items-center justify-center transition-all elevation-1 cursor-pointer">
              <Send size={16} />
            </button>
          </div>
        </header>

        {/* Main Content Area */}
        <div className="flex-1 flex items-center justify-center my-6 relative z-10">
          
          {/* Decorative Side Illustration Element (Left) */}
          <div className="hidden lg:flex flex-col items-center justify-center absolute left-6 bottom-4 select-none opacity-90">
            <div className="relative">
              <svg width="220" height="180" viewBox="0 0 220 180" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="20" y="100" width="45" height="70" rx="6" fill="#FFFFFF" stroke="#3C3C3C" strokeWidth="2.5" />
                <path d="M32 135L42 120" stroke="#3C3C3C" strokeWidth="2.5" strokeLinecap="round" />
                <rect x="70" y="70" width="55" height="100" rx="6" fill="#DDF4FF" stroke="#1CB0F6" strokeWidth="2.5" />
                <rect x="150" y="90" width="50" height="80" rx="6" fill="#FFFFFF" stroke="#3C3C3C" strokeWidth="2.5" />
                <rect x="180" y="45" width="35" height="125" rx="6" fill="#DDF4FF" stroke="#1CB0F6" strokeWidth="2.5" />
                <circle cx="82" cy="40" r="12" fill="#3C3C3C" />
                <path d="M72 58C72 52 92 52 92 58L95 82H69L72 58Z" fill="#3C3C3C" />
                <path d="M69 82L62 105L85 105L88 82" fill="#3C3C3C" />
                <path d="M92 72L108 62" stroke="#1CB0F6" strokeWidth="4" strokeLinecap="round" />
              </svg>
            </div>
          </div>

          {/* Center Sign Up Card */}
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.4 }}
            className="w-full max-w-md bg-white rounded-[2rem] p-8 sm:p-10 border border-[#E2E8F0] elevation-2 relative"
          >
            <div className="text-left mb-6">
              <h1 className="text-2xl sm:text-3xl font-black text-[#3C3C3C] tracking-tight mb-1.5 leading-tight">
                Let's<br />Start Learning
              </h1>
              <p className="text-xs font-semibold text-[#AFAFAF]">
                Create your account to continue
              </p>
            </div>

            {/* Demo Hint */}
            <div className="mb-5 p-3 rounded-[1.5rem] bg-[#DDF4FF] border border-[#1CB0F6]/30 flex items-center gap-2.5">
              <Sparkles size={16} className="text-[#1CB0F6] flex-shrink-0" />
              <p className="text-xs text-[#3C3C3C] font-medium">
                <span className="font-bold text-[#1CB0F6]">Demo Mode:</span> Fill in any details to create your profile.
              </p>
            </div>

            {error && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                className="mb-4 p-3 rounded-[1.5rem] bg-[#FFD1D1] border border-[#FF4B4B]/30 text-[#FF4B4B] text-xs font-bold"
              >
                {error}
              </motion.div>
            )}

            <form onSubmit={handleSubmit} className="space-y-3">
              
              {/* Username */}
              <div className="relative">
                <User size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#AFAFAF]" />
                <input
                  id="reg-username"
                  type="text"
                  value={form.username}
                  onChange={(e) => set('username', e.target.value)}
                  className="w-full bg-[#F7F7F7] border border-[#E2E8F0] rounded-[1.5rem] pl-12 pr-4 py-3 text-sm font-semibold text-[#3C3C3C] placeholder-[#AFAFAF] outline-none focus:bg-white focus:border-[#1CB0F6] focus:ring-4 focus:ring-[#1CB0F6]/20 transition-all"
                  placeholder="Your Name"
                  required
                />
              </div>

              {/* Email */}
              <div className="relative">
                <Mail size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#AFAFAF]" />
                <input
                  id="reg-email"
                  type="email"
                  value={form.email}
                  onChange={(e) => set('email', e.target.value)}
                  className="w-full bg-[#F7F7F7] border border-[#E2E8F0] rounded-[1.5rem] pl-12 pr-4 py-3 text-sm font-semibold text-[#3C3C3C] placeholder-[#AFAFAF] outline-none focus:bg-white focus:border-[#1CB0F6] focus:ring-4 focus:ring-[#1CB0F6]/20 transition-all"
                  placeholder="Your Email"
                  required
                />
              </div>

              {/* Password */}
              <div className="relative">
                <Lock size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#AFAFAF]" />
                <input
                  id="reg-password"
                  type={showPass ? 'text' : 'password'}
                  value={form.password}
                  onChange={(e) => set('password', e.target.value)}
                  className="w-full bg-[#F7F7F7] border border-[#E2E8F0] rounded-[1.5rem] pl-12 pr-11 py-3 text-sm font-semibold text-[#3C3C3C] placeholder-[#AFAFAF] outline-none focus:bg-white focus:border-[#1CB0F6] focus:ring-4 focus:ring-[#1CB0F6]/20 transition-all"
                  placeholder="Your Password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-[#AFAFAF] hover:text-[#3C3C3C] transition-colors"
                >
                  {showPass ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>

              {/* Confirm Password */}
              <div className="relative">
                <Lock size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#AFAFAF]" />
                <input
                  id="reg-confirm"
                  type="password"
                  value={form.confirm}
                  onChange={(e) => set('confirm', e.target.value)}
                  className="w-full bg-[#F7F7F7] border border-[#E2E8F0] rounded-[1.5rem] pl-12 pr-4 py-3 text-sm font-semibold text-[#3C3C3C] placeholder-[#AFAFAF] outline-none focus:bg-white focus:border-[#1CB0F6] focus:ring-4 focus:ring-[#1CB0F6]/20 transition-all"
                  placeholder="Confirm Password"
                  required
                />
              </div>

              {/* Primary Action Button */}
              <button
                type="submit"
                id="register-submit"
                disabled={loading}
                className="btn-primary w-full py-3.5 px-4 text-base font-black elevation-2 flex items-center justify-center gap-2 mt-2 cursor-pointer disabled:opacity-50"
              >
                {loading ? (
                  <span className="flex gap-1">
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                  </span>
                ) : (
                  <>
                    Sign Up <ArrowRight size={18} />
                  </>
                )}
              </button>
            </form>

            {/* Google OAuth Button */}
            <div className="mt-3">
              <button
                type="button"
                onClick={handleGoogleSignup}
                className="w-full bg-white border border-[#E2E8F0] hover:bg-[#F7F7F7] text-[#3C3C3C] font-bold py-3 px-4 rounded-[1.5rem] text-sm flex items-center justify-center gap-2.5 transition-all elevation-1 cursor-pointer"
              >
                <svg width="18" height="18" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
                </svg>
                <span>Google</span>
              </button>
            </div>

            {/* Switch to Login */}
            <p className="text-center text-xs font-semibold text-[#777777] mt-4">
              Already have an account?{' '}
              <Link to="/login" className="text-[#1CB0F6] hover:text-[#1899D6] font-black transition-colors">
                Login
              </Link>
            </p>

          </motion.div>
        </div>

        {/* Footer info */}
        <footer className="flex items-center justify-between text-xs text-[#AFAFAF] font-semibold z-10 pt-2 border-t border-[#E2E8F0]">
          <div className="flex items-center gap-1.5 text-[#777777]">
            <Brain size={16} className="text-[#1CB0F6]" />
            <span>Powered by Local Indie-Tutor</span>
          </div>
          <span>© 2026 Indie-Tutor Inc.</span>
        </footer>

      </div>
    </div>
  )
}
