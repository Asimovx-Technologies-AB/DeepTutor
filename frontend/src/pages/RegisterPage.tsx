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
    <div className="min-h-screen bg-[#fafafa] flex items-center justify-center p-4 relative overflow-hidden">
      <motion.div
        initial={{ opacity: 0, y: 24, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
        className="w-full max-w-md"
      >
        <div className="bg-white rounded-3xl p-8 border border-[#e5e7eb] shadow-xl">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-[#111111] text-white mb-4 shadow-sm">
              <GraduationCap size={30} />
            </div>
            <h1 className="text-2xl font-black text-[#111111] mb-1">Create Account</h1>
            <p className="text-slate-500 text-sm font-medium">Start your AI-powered learning journey</p>
          </div>

          {/* Demo hint */}
          <div className="mb-6 p-3.5 rounded-2xl bg-[#f4f4f5] border border-[#e4e4e7] flex items-start gap-2.5">
            <Sparkles size={15} className="text-[#111111] mt-0.5 flex-shrink-0" />
            <p className="text-xs text-[#18181b] font-medium">
              <span className="font-bold">Demo Mode:</span> Fill in any details to create an account and explore.
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
