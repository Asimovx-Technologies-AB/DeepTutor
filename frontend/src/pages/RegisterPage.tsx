import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Mail, Lock, User, ArrowRight, Eye, EyeOff, Sparkles, Brain, Globe, Send } from 'lucide-react'
import { authApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'
import { TextInput } from '../components/ui/TextInput'
import { Button } from '../components/ui/Button'

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
      { id: 'google-user', username: 'Google Learner', email: 'google.student@indietutor.ai', role: 'student' },
      'demo-google-token'
    )
    navigate('/dashboard')
  }

  return (
    <div className="min-h-screen bg-transparent flex items-center justify-center p-4 sm:p-8 font-sans relative">
      
      {/* Outer Card Frame */}
      <div className="w-full max-w-5xl bg-black/5 rounded-[36px] border border-border/60 shadow-sm p-6 sm:p-10 flex flex-col justify-between min-h-[640px] relative overflow-hidden backdrop-blur-3xl">
        
        {/* Top Header Navigation */}
        <header className="flex items-center justify-between z-10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-[1.5rem] bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600 shadow-sm">
              <Brain size={22} />
            </div>
            <div>
              <span className="font-black text-slate-800 text-xl tracking-tight">IndieTutor</span>
              <span className="block text-[10px] font-black text-indigo-600 uppercase tracking-widest">AI Learning Engine</span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button aria-label="Language" className="w-10 h-10 rounded-full border border-slate-200 bg-white text-slate-500 hover:text-indigo-600 hover:border-indigo-200 flex items-center justify-center transition-all shadow-sm cursor-pointer">
              <Globe size={18} />
            </button>
            <button aria-label="Contact" className="w-10 h-10 rounded-full bg-slate-900 text-white hover:bg-slate-800 flex items-center justify-center transition-all shadow-sm cursor-pointer">
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
                <rect x="20" y="100" width="45" height="70" rx="6" fill="#FFFFFF" stroke="currentColor" className="text-slate-800" strokeWidth="2.5" />
                <path d="M32 135L42 120" stroke="currentColor" className="text-slate-800" strokeWidth="2.5" strokeLinecap="round" />
                <rect x="70" y="70" width="55" height="100" rx="6" fill="#EEF2FF" stroke="#4F46E5" strokeWidth="2.5" />
                <rect x="150" y="90" width="50" height="80" rx="6" fill="#FFFFFF" stroke="currentColor" className="text-slate-800" strokeWidth="2.5" />
                <rect x="180" y="45" width="35" height="125" rx="6" fill="#EEF2FF" stroke="#4F46E5" strokeWidth="2.5" />
                <circle cx="82" cy="40" r="12" fill="currentColor" className="text-slate-800" />
                <path d="M72 58C72 52 92 52 92 58L95 82H69L72 58Z" fill="currentColor" className="text-slate-800" />
                <path d="M69 82L62 105L85 105L88 82" fill="currentColor" className="text-slate-800" />
                <path d="M92 72L108 62" stroke="#4F46E5" strokeWidth="4" strokeLinecap="round" />
              </svg>
            </div>
          </div>

          {/* Center Sign Up Card */}
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.4 }}
            className="w-full max-w-md bg-white rounded-[2rem] p-8 sm:p-10 border border-slate-200 shadow-md relative"
          >
            <div className="text-left mb-6">
              <h1 className="text-2xl sm:text-3xl font-black text-slate-800 tracking-tight mb-1.5 leading-tight">
                Let's<br />Start Learning
              </h1>
              <p className="text-xs font-semibold text-slate-400">
                Create your account to continue
              </p>
            </div>

            {/* Demo Hint */}
            <div className="mb-5 p-3 rounded-[1.5rem] bg-indigo-50 border border-indigo-200 flex items-center gap-2.5">
              <Sparkles size={16} className="text-indigo-600 flex-shrink-0" />
              <p className="text-xs text-slate-700 font-medium">
                <span className="font-bold text-indigo-600">Demo Mode:</span> Fill in any details to create your profile.
              </p>
            </div>

            {error && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                className="mb-4 p-3 rounded-[1.5rem] bg-rose-50 border border-rose-200 text-rose-600 text-xs font-bold"
              >
                {error}
              </motion.div>
            )}

            <form onSubmit={handleSubmit} autoComplete="off" className="space-y-4">
              
              <TextInput
                id="reg-username"
                name="new-username"
                type="text"
                autoComplete="off"
                value={form.username}
                onChange={(e) => set('username', e.target.value)}
                placeholder="Your Name"
                leftIcon={<User size={18} />}
                required
              />

              <TextInput
                id="reg-email"
                name="new-email"
                type="email"
                autoComplete="off"
                value={form.email}
                onChange={(e) => set('email', e.target.value)}
                placeholder="Your Email"
                leftIcon={<Mail size={18} />}
                required
              />

              <TextInput
                id="reg-password"
                name="new-user-password"
                type={showPass ? 'text' : 'password'}
                autoComplete="new-password"
                value={form.password}
                onChange={(e) => set('password', e.target.value)}
                placeholder="Your Password"
                leftIcon={<Lock size={18} />}
                rightIcon={
                  <button
                    type="button"
                    aria-label="Toggle password visibility"
                    onClick={() => setShowPass(!showPass)}
                    className="hover:text-slate-800 text-slate-400 transition-colors cursor-pointer"
                  >
                    {showPass ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                }
                required
              />

              <TextInput
                id="reg-confirm"
                name="new-confirm-password"
                type="password"
                autoComplete="new-password"
                value={form.confirm}
                onChange={(e) => set('confirm', e.target.value)}
                placeholder="Confirm Password"
                leftIcon={<Lock size={18} />}
                required
              />

              {/* Primary Action Button */}
              <Button
                type="submit"
                id="register-submit"
                variant="primary"
                className="w-full mt-2 bg-indigo-600 hover:bg-indigo-700 text-white"
                isLoading={loading}
                rightIcon={<ArrowRight size={18} />}
              >
                Sign Up
              </Button>
            </form>

            {/* Google OAuth Button */}
            <div className="mt-4">
              <Button
                type="button"
                variant="ghost"
                className="w-full border border-slate-200 bg-white hover:bg-slate-50 text-slate-700"
                onClick={handleGoogleSignup}
                leftIcon={
                  <svg width="18" height="18" viewBox="0 0 24 24">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
                  </svg>
                }
              >
                Google
              </Button>
            </div>

            {/* Switch to Login */}
            <p className="text-center text-xs font-semibold text-slate-500 mt-5">
              Already have an account?{' '}
              <Link to="/login" className="text-indigo-600 hover:text-indigo-700 font-black transition-colors">
                Login
              </Link>
            </p>

          </motion.div>
        </div>

        {/* Footer info */}
        <footer className="flex items-center justify-between text-xs text-slate-400 font-semibold z-10 pt-2 border-t border-slate-200/60">
          <div className="flex items-center gap-1.5 text-slate-500">
            <Brain size={16} className="text-indigo-600" />
            <span>Powered by IndieTutor AI Engine</span>
          </div>
          <span>© 2026 IndieTutor Inc.</span>
        </footer>

      </div>
    </div>
  )
}
