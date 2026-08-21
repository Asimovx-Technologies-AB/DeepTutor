import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { User, Mail, Sparkles, Check, Edit3, Save, X, LogOut, Award, Clock, BookOpen } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useQuery } from '@tanstack/react-query'
import { progressApi } from '../services/api'

interface ProfileModalProps {
  isOpen: boolean
  onClose: () => void
}

export default function ProfileModal({ isOpen, onClose }: ProfileModalProps) {
  const { user, updateUser, logout } = useAuthStore()

  const { data: progress } = useQuery({
    queryKey: ['progress-summary'],
    queryFn: () => progressApi.summary().then((r) => r.data),
  })

  // Editable Profile Form State
  const [isEditing, setIsEditing] = useState(false)
  const [username, setUsername] = useState(user?.username || 'adwaid')
  const [email, setEmail] = useState(user?.email || 'adwaidp08@gmail.com')
  const [learningStyle, setLearningStyle] = useState('Visual & Examples')
  const [dailyGoalHours, setDailyGoalHours] = useState('2 hours / day')
  const [savedSuccess, setSavedSuccess] = useState(false)

  if (!isOpen) return null

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim()) return

    updateUser({
      id: user?.id || '1',
      username,
      email,
      role: user?.role || 'student',
    })

    setSavedSuccess(true)
    setIsEditing(false)
    setTimeout(() => setSavedSuccess(false), 2500)
  }

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        {/* Backdrop overlay */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="fixed inset-0 bg-black/40 backdrop-blur-xs"
        />

        {/* Modal Window */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          className="relative w-full max-w-md card overflow-hidden font-sans text-text-primary z-10 max-h-[90vh] overflow-y-auto"
        >
          {/* Header Banner */}
          <div className="bg-transparent p-6 border-b border-border relative text-center">
            <button
              onClick={onClose}
              className="absolute top-4 right-4 text-text-muted hover:text-text-primary p-1 rounded-full hover:bg-black/5 transition-colors cursor-pointer"
            >
              <X size={18} />
            </button>

            {/* User Avatar Circle */}
            <div className="w-20 h-20 rounded-full bg-brand-primary text-white font-bold text-2xl flex items-center justify-center mx-auto elevation-2 border-4 ring-2 ring-brand-primary/20 border-white mb-3">
              {username[0]?.toUpperCase() ?? 'A'}
            </div>

            <h2 className="text-xl font-bold text-[#3C3C3C]">{username}</h2>
            <p className="text-xs text-[#777777] font-normal mt-0.5">{email}</p>

            {/* Level & XP Badges */}
            <div className="flex items-center justify-center gap-2 mt-3">
              <span className="text-[11px] font-bold bg-[#1CB0F6] text-white px-3 py-0.5 rounded-full elevation-1">
                Level {progress?.level ?? 1} Scholar
              </span>
              <span className="text-[11px] font-bold bg-[#D7FFB8] text-[#46A302] px-3 py-0.5 rounded-full border border-[#58CC02]/30">
                {progress?.total_xp ?? 150} Total XP
              </span>
            </div>
          </div>

          {/* Form / Content Section */}
          <div className="p-6 space-y-5">
            {savedSuccess && (
              <motion.div
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-success-soft border border-success/30 text-success text-xs font-bold p-3 rounded-[1.5rem] flex items-center gap-2"
              >
                <Check size={16} /> Profile changes saved successfully!
              </motion.div>
            )}

            {!isEditing ? (
              /* VIEW MODE */
              <div className="space-y-4 text-xs">
                <div className="bg-[#F7F7F7] border border-[#E2E8F0] rounded-[1.5rem] p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[#777777] font-medium flex items-center gap-2">
                      <User size={15} className="text-[#1CB0F6]" /> Username
                    </span>
                    <span className="font-bold text-[#3C3C3C]">{username}</span>
                  </div>

                  <div className="flex items-center justify-between border-t border-[#E2E8F0]/60 pt-2.5">
                    <span className="text-[#777777] font-medium flex items-center gap-2">
                      <Mail size={15} className="text-[#1CB0F6]" /> Email Address
                    </span>
                    <span className="font-bold text-[#3C3C3C] truncate max-w-[180px]">{email}</span>
                  </div>

                  <div className="flex items-center justify-between border-t border-[#E2E8F0]/60 pt-2.5">
                    <span className="text-[#777777] font-medium flex items-center gap-2">
                      <BookOpen size={15} className="text-[#58CC02]" /> Learning Style
                    </span>
                    <span className="font-bold text-[#3C3C3C]">{learningStyle}</span>
                  </div>

                  <div className="flex items-center justify-between border-t border-[#E2E8F0]/60 pt-2.5">
                    <span className="text-[#777777] font-medium flex items-center gap-2">
                      <Clock size={15} className="text-[#FFC800]" /> Daily Goal
                    </span>
                    <span className="font-bold text-[#3C3C3C]">{dailyGoalHours}</span>
                  </div>
                </div>

                <div className="flex items-center gap-3 pt-2">
                  <button
                    onClick={() => setIsEditing(true)}
                    className="flex-1 btn-primary py-2.5 text-xs flex items-center justify-center gap-2 cursor-pointer"
                  >
                    <Edit3 size={15} /> Edit Profile
                  </button>

                  <button
                    onClick={() => {
                      logout()
                      onClose()
                    }}
                    className="btn-ghost py-2.5 px-4 text-xs flex items-center gap-1.5 cursor-pointer text-error hover:bg-error-soft"
                  >
                    <LogOut size={15} /> Logout
                  </button>
                </div>
              </div>
            ) : (
              /* EDIT MODE */
              <form onSubmit={handleSave} className="space-y-4 text-xs">
                <div className="space-y-1">
                  <label className="font-bold text-text-primary">Username</label>
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="w-full input-field px-3.5 py-2.5 text-xs"
                    placeholder="Enter username..."
                  />
                </div>

                <div className="space-y-1">
                  <label className="font-bold text-text-primary">Email Address</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full input-field px-3.5 py-2.5 text-xs"
                    placeholder="Enter email address..."
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="font-bold text-[#3C3C3C]">Preferred Learning Style</label>
                  <div className="grid grid-cols-2 gap-2">
                    {['Visual & Examples', 'Step-by-Step', 'Concept Deep-Dive', 'Quiz-focused'].map((style) => (
                      <button
                        key={style}
                        type="button"
                        onClick={() => setLearningStyle(style)}
                        className={`p-2 rounded-[1.25rem] text-[11px] font-semibold border transition-all text-left ${
                          learningStyle === style
                            ? 'bg-[#DDF4FF] border-[#1CB0F6] text-[#1CB0F6]'
                            : 'bg-white border-[#E2E8F0] text-[#777777] hover:bg-[#F7F7F7]'
                        }`}
                      >
                        {style}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="font-bold text-[#3C3C3C]">Daily Study Time Goal</label>
                  <div className="grid grid-cols-3 gap-2">
                    {['1 hour / day', '2 hours / day', '3 hours / day'].map((goal) => (
                      <button
                        key={goal}
                        type="button"
                        onClick={() => setDailyGoalHours(goal)}
                        className={`p-2 rounded-[1.25rem] text-[11px] font-semibold border transition-all text-center ${
                          dailyGoalHours === goal
                            ? 'bg-[#D7FFB8] border-[#58CC02] text-[#46A302]'
                            : 'bg-white border-[#E2E8F0] text-[#777777] hover:bg-[#F7F7F7]'
                        }`}
                      >
                        {goal}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex items-center gap-3 pt-2">
                  <button
                    type="submit"
                    className="flex-1 btn-primary py-2.5 text-xs flex items-center justify-center gap-2 cursor-pointer"
                  >
                    <Save size={15} /> Save Changes
                  </button>

                  <button
                    type="button"
                    onClick={() => setIsEditing(false)}
                    className="btn-ghost py-2.5 px-4 text-xs cursor-pointer"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            )}
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  )
}
