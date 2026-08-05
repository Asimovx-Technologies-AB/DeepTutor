import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { GraduationCap, Mail, Lock, User, ArrowRight, Eye, EyeOff, Sparkles } from 'lucide-react'
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
      // Demo bypass: if backend is offline, auto-login with mock data
      if (!err.response || err.code === 'ERR_NETWORK' || err.response?.status >= 500) {
        login(
          { id: 'demo-user', username: form.username || 'Learner', email: form.email, role: 'student' },
          'demo-token'
        )
        navigate('/dashboard')
        return
      }
      setError(err.response?.data?.detail ?? 'Registration failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-mesh flex items-center justify-center p-4 relative overflow-hidden">
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/3 right-1/4 w-96 h-96 bg-violet-600/10 rounded-full blur-3xl animate-float" />
        <div className="absolute bottom-1/3 left-1/4 w-80 h-80 bg-cyan-600/8 rounded-full blur-3xl animate-float" style={{ animationDelay: '2s' }} />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 24, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
        className="w-full max-w-md"
      >
        <div className="glass-strong rounded-2xl p-8 shadow-2xl">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-500 to-cyan-500 mb-4 shadow-xl glow-accent animate-float">
              <GraduationCap size={28} className="text-white" />
            </div>
            <h1 className="text-2xl font-bold text-white mb-1">Create Account</h1>
            <p className="text-slate-400 text-sm">Start your AI-powered learning journey</p>
          </div>

          {/* Demo hint */}
          <div className="mb-6 p-3 rounded-xl bg-violet-500/10 border border-violet-500/20 flex items-start gap-2">
            <Sparkles size={14} className="text-violet-400 mt-0.5 flex-shrink-0" />
            <p className="text-xs text-violet-300">
              <span className="font-semibold">Demo Mode:</span> Works without a backend — just fill in any details to explore the app
            </p>
          </div>

          {error && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              className="mb-4 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm"
            >
              {error}
            </motion.div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Username</label>
              <div className="relative">
                <User size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                <input id="reg-username" type="text" value={form.username} onChange={(e) => set('username', e.target.value)}
                  className="input-base pl-9" placeholder="your_name" required />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Email</label>
              <div className="relative">
                <Mail size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                <input id="reg-email" type="email" value={form.email} onChange={(e) => set('email', e.target.value)}
                  className="input-base pl-9" placeholder="you@example.com" required />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Password</label>
              <div className="relative">
                <Lock size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                <input id="reg-password" type={showPass ? 'text' : 'password'} value={form.password}
                  onChange={(e) => set('password', e.target.value)} className="input-base pl-9 pr-10" placeholder="••••••••" required />
                <button type="button" onClick={() => setShowPass(!showPass)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors">
                  {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Confirm Password</label>
              <div className="relative">
                <Lock size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                <input id="reg-confirm" type="password" value={form.confirm} onChange={(e) => set('confirm', e.target.value)}
                  className="input-base pl-9" placeholder="••••••••" required />
              </div>
            </div>

            <button type="submit" id="register-submit" disabled={loading}
              className="btn-primary w-full flex items-center justify-center gap-2 mt-2"
              style={{ background: 'linear-gradient(135deg, #7c3aed, #06b6d4)' }}>
              {loading ? (
                <span className="flex gap-1">
                  <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
                </span>
              ) : (<>Create Account <ArrowRight size={16} /></>)}
            </button>
          </form>

          <p className="text-center text-sm text-slate-500 mt-6">
            Already have an account?{' '}
            <Link to="/login" className="text-indigo-400 hover:text-indigo-300 font-semibold transition-colors">Sign in</Link>
          </p>
        </div>
      </motion.div>
    </div>
  )
}
