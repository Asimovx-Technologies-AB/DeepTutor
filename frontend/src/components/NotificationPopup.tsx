import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Bell, X, ChevronRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { studyPlanApi, progressApi } from '../services/api'

interface NotificationItem {
  id: string
  type: 'streak' | 'plan' | 'tip'
  title: string
  message: string
  timeAgo: string
  actionText?: string
  actionPath?: string
  unread: boolean
}

export default function NotificationPopup() {
  const navigate = useNavigate()
  const [isOpen, setIsOpen] = useState(false)
  const [showToast, setShowToast] = useState(true)

  // Fetch real progress & study plan summaries
  const { data: progress } = useQuery({
    queryKey: ['progress-summary'],
    queryFn: () => progressApi.summary().then((r) => r.data),
  })

  const { data: plans } = useQuery({
    queryKey: ['study-plans'],
    queryFn: () => studyPlanApi.myPlans().then((r: any) => r.data),
  })

  const activePlan = plans?.[0]
  const currentStreak = progress?.streak_days ?? 1
  const totalXp = progress?.total_xp ?? 150

  const notifications: NotificationItem[] = [
    {
      id: 'streak-1',
      type: 'streak',
      title: '🔥 Streak Active!',
      message: `You are on a ${currentStreak}-day learning streak (${totalXp} XP earned). Complete 1 lesson today to keep it going!`,
      timeAgo: 'Just now',
      actionText: 'Continue Streak',
      actionPath: '/chat',
      unread: true,
    },
    {
      id: 'plan-1',
      type: 'plan',
      title: '📅 Study Plan Reminder',
      message: activePlan
        ? `Target Date: ${activePlan.target_date}. Complete today's focus topic in your ${activePlan.title || 'custom plan'}.`
        : "Today's Focus: Supervised Learning (2 hrs). 4 topics remaining in your Machine Learning plan.",
      timeAgo: '10m ago',
      actionText: 'View Study Plan',
      actionPath: '/study-plan',
      unread: true,
    },
    {
      id: 'tip-1',
      type: 'tip',
      title: '💡 AI Tutor Suggestion',
      message: 'Review Gradient Descent formulas before moving on to Neural Networks.',
      timeAgo: '1h ago',
      actionText: 'Start Lesson',
      actionPath: '/chat',
      unread: false,
    },
  ]

  const unreadCount = notifications.filter((n) => n.unread).length

  // Auto-dismiss floating toast after 9s
  useEffect(() => {
    const timer = setTimeout(() => setShowToast(false), 9000)
    return () => clearTimeout(timer)
  }, [])

  return (
    <div className="relative inline-block text-left">
      {/* Notification Bell Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-10 h-10 rounded-full bg-white border border-[#E7E1D8] hover:bg-[#FFF9F2] text-[#20201D] flex items-center justify-center relative shadow-2xs transition-colors cursor-pointer"
        title="Notifications & Study Reminders"
      >
        <Bell size={18} />
        {unreadCount > 0 && (
          <span className="absolute top-2 right-2 w-2.5 h-2.5 rounded-full bg-[#F28A45] ring-2 ring-white animate-pulse" />
        )}
      </button>

      {/* Floating Toast Reminder Banner (Auto-dismisses) */}
      <AnimatePresence>
        {showToast && !isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.95 }}
            className="fixed top-20 right-6 z-50 max-w-sm bg-[#FFF9F2] border border-[#F28A45]/40 rounded-3xl p-4 shadow-xl flex items-start gap-3.5"
          >
            <div className="w-10 h-10 rounded-2xl bg-[#FFF0E4] border border-[#F28A45]/30 flex items-center justify-center flex-shrink-0 text-[#F28A45] shadow-2xs">
              <img src="/assets/illustrations/flame_streak.png" alt="Streak" className="w-6 h-6 object-contain" />
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-[#20201D]">🔥 {currentStreak}-Day Streak Active!</span>
                <button
                  onClick={() => setShowToast(false)}
                  className="text-[#969188] hover:text-[#20201D] p-0.5 cursor-pointer"
                >
                  <X size={14} />
                </button>
              </div>
              <p className="text-[12px] text-[#6F6B63] font-normal leading-relaxed mt-0.5">
                Complete today's Study Plan target to keep your streak alive!
              </p>
              <div className="flex items-center gap-3 mt-2">
                <button
                  onClick={() => {
                    setShowToast(false)
                    navigate('/study-plan')
                  }}
                  className="text-[11px] font-semibold text-[#F28A45] hover:underline flex items-center gap-1 cursor-pointer"
                >
                  <span>Study Plan</span> <ChevronRight size={12} />
                </button>
                <button
                  onClick={() => {
                    setShowToast(false)
                    navigate('/chat')
                  }}
                  className="text-[11px] font-semibold text-[#4F8A68] hover:underline flex items-center gap-1 cursor-pointer"
                >
                  <span>Start Lesson</span> <ChevronRight size={12} />
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Full Notifications Dropdown Popover */}
      <AnimatePresence>
        {isOpen && (
          <>
            {/* Backdrop click to close */}
            <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />

            <motion.div
              initial={{ opacity: 0, y: 8, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.98 }}
              transition={{ duration: 0.15 }}
              className="absolute right-0 mt-3 w-80 sm:w-96 bg-white border border-[#E7E1D8] rounded-3xl shadow-xl z-50 overflow-hidden font-sans text-[#20201D]"
            >
              {/* Dropdown Header */}
              <div className="bg-[#FFF9F2] p-4 border-b border-[#E7E1D8] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Bell size={16} className="text-[#F28A45]" />
                  <h3 className="text-sm font-bold text-[#20201D]">Study Reminders</h3>
                  {unreadCount > 0 && (
                    <span className="text-[10px] font-bold bg-[#F28A45] text-white px-2 py-0.5 rounded-full">
                      {unreadCount} new
                    </span>
                  )}
                </div>
                <button
                  onClick={() => setIsOpen(false)}
                  className="text-[#969188] hover:text-[#20201D] p-1 rounded-lg transition-colors cursor-pointer"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Notifications List */}
              <div className="max-h-96 overflow-y-auto divide-y divide-[#E7E1D8]/60 p-2 space-y-1">
                {notifications.map((item) => (
                  <div
                    key={item.id}
                    className={`p-3.5 rounded-2xl transition-colors ${
                      item.unread ? 'bg-[#FFF0E4]/40 border border-[#F28A45]/20' : 'hover:bg-[#FAF8F3]'
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div
                        className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 p-1.5 shadow-2xs border ${
                          item.type === 'streak'
                            ? 'bg-[#FFF0E4] border-[#F28A45]/30'
                            : item.type === 'plan'
                            ? 'bg-[#E3F0E5] border-[#4F8A68]/30'
                            : 'bg-[#FFF3D8] border-[#D99A32]/30'
                        }`}
                      >
                        {item.type === 'streak' && (
                          <img src="/assets/illustrations/flame_streak.png" alt="Streak" className="w-full h-full object-contain" />
                        )}
                        {item.type === 'plan' && (
                          <img src="/assets/illustrations/target_arrow.png" alt="Plan" className="w-full h-full object-contain" />
                        )}
                        {item.type === 'tip' && (
                          <img src="/assets/illustrations/lightbulb.png" alt="Tip" className="w-full h-full object-contain" />
                        )}
                      </div>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <h4 className="text-xs font-bold text-[#20201D] truncate">{item.title}</h4>
                          <span className="text-[10px] text-[#969188] font-normal">{item.timeAgo}</span>
                        </div>
                        <p className="text-xs text-[#6F6B63] font-normal leading-relaxed mt-1">{item.message}</p>

                        {item.actionText && item.actionPath && (
                          <button
                            onClick={() => {
                              setIsOpen(false)
                              navigate(item.actionPath!)
                            }}
                            className="mt-2 text-xs font-semibold text-[#F28A45] hover:underline flex items-center gap-1 cursor-pointer"
                          >
                            <span>{item.actionText}</span>
                            <ChevronRight size={13} />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Dropdown Footer */}
              <div className="bg-[#FAF8F3] p-3 text-center border-t border-[#E7E1D8]">
                <button
                  onClick={() => {
                    setIsOpen(false)
                    navigate('/study-plan')
                  }}
                  className="text-xs font-semibold text-[#4F8A68] hover:underline cursor-pointer"
                >
                  Manage Study Plan & Goal Schedule &rarr;
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}
