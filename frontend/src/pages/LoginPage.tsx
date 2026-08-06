import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { GraduationCap, Mail, Lock, ArrowRight, Eye, EyeOff, Sparkles, Brain } from 'lucide-react'
import { authApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'

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
      login(user, access_token)
      navigate('/dashboard')
    } catch (err: any) {
      // Demo bypass: if backend is offline, auto-login with mock data
      if (!err.response || err.code === 'ERR_NETWORK' || err.response?.status >= 500) {
        const username = email.split('@')[0] || 'Learner'
        login(
          { id: 'demo-user', username, email, role: 'student' },
          'demo-token'
        )
        navigate('/dashboard')
        return
      }
      setError(err.response?.data?.detail ?? 'Login failed. Please try again.')
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
        {/* Card */}
        <div className="bg-white rounded-3xl p-8 border border-[#e5e7eb] shadow-xl">
          {/* Header */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-[#111111] text-white mb-4 shadow-sm">
              <GraduationCap size={30} />
            </div>
            <h1 className="text-2xl font-black text-[#111111] mb-1">Welcome back</h1>
            <p className="text-slate-500 text-sm font-medium">Sign in to continue your learning journey</p>
          </div>

          {/* Demo hint */}
          <div className="mb-6 p-3.5 rounded-2xl bg-[#f4f4f5] border border-[#e4e4e7] flex items-start gap-2.5">
            <Sparkles size={15} className="text-[#111111] mt-0.5 flex-shrink-0" />
            <p className="text-xs text-[#18181b] font-medium">
              <span className="font-bold">Demo Mode:</span> Use any email & password to enter the system.
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
            {/* Email */}
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">
                Email
              </label>
              <div className="relative">
                <Mail size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                <input
                  id="login-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="input-base pl-9"
                  placeholder="you@example.com"
                  required
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">
                Password
              </label>
              <div className="relative">
                <Lock size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                <input
                  id="login-password"
                  type={showPass ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="input-base pl-9 pr-10"
                  placeholder="••••••••"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                >
                  {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              id="login-submit"
              disabled={loading}
              className="btn-primary w-full flex items-center justify-center gap-2 mt-2"
            >
              {loading ? (
                <span className="flex gap-1">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </span>
              ) : (
                <>
                  Sign In <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>

          <p className="text-center text-sm text-slate-500 mt-6">
            Don't have an account?{' '}
            <Link to="/register" className="text-indigo-400 hover:text-indigo-300 font-semibold transition-colors">
              Create one
            </Link>
          </p>
        </div>

        {/* Footer brand */}
        <div className="text-center mt-6 flex items-center justify-center gap-2 text-slate-600">
          <Brain size={14} />
          <span className="text-xs">Powered by Local AI • Privacy First</span>
        </div>
      </motion.div>
    </div>
  )
}
