import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Bell, X, ChevronRight, Settings, Check, Volume2 } from 'lucide-react'
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
  const [showSettings, setShowSettings] = useState(false)
  const [remindersEnabled, setRemindersEnabled] = useState(true)
  const [streakAlertsEnabled, setStreakAlertsEnabled] = useState(true)

  // Fetch real progress & study plan summaries
  const { data: progress } = useQuery({
    queryKey: ['progress-summary'],
    queryFn: () => progressApi.summary().then((r) => r.data),
    staleTime: 120_000,
  })

  const { data: plans } = useQuery({
    queryKey: ['study-plans'],
    queryFn: () => studyPlanApi.myPlans().then((r: any) => r.data),
    staleTime: 120_000,
  })

  const activePlan = plans?.[0]
  const currentStreak = progress?.streak_days ?? 1
  const totalXp = progress?.total_xp ?? 150

  // Dynamic Study Plan Deadline Analysis (Strictly Overdue & Deadline Only)
  let planNotification: NotificationItem | null = null

  if (activePlan) {
    const todayDate = new Date()
    todayDate.setHours(0, 0, 0, 0)

    let daysRemaining = 0
    if (activePlan.target_date) {
      const targetDate = new Date(activePlan.target_date)
      targetDate.setHours(0, 0, 0, 0)
      const diffMs = targetDate.getTime() - todayDate.getTime()
      daysRemaining = Math.ceil(diffMs / (1000 * 60 * 60 * 24))
    }

    const completedDaysCount = activePlan.completed_days?.length ?? 0
    const totalDaysCount = activePlan.schedule?.length ?? 5
    const planTitle = activePlan.title || 'Study Plan'

    if (daysRemaining === 0) {
      planNotification = {
        id: 'plan-target-today',
        type: 'plan',
        title: `🎯 Today's Goal: ${planTitle}`,
        message: `Today is your target completion date for '${planTitle}'. Finish your remaining topics to complete your goal!`,
        timeAgo: 'Just now',
        actionText: 'Continue Learning',
        actionPath: '/study-plan',
        unread: true,
      }
    } else if (daysRemaining < 0) {
      planNotification = {
        id: 'plan-catchup',
        type: 'plan',
        title: `⏰ Catch Up Plan: ${planTitle}`,
        message: `You have unfinished topics in '${planTitle}'. Resume learning anytime at your own pace!`,
        timeAgo: 'Reminder',
        actionText: 'Open Study Plan',
        actionPath: '/study-plan',
        unread: true,
      }
    }


  }

  const rawNotifications: NotificationItem[] = [
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
    ...(planNotification ? [planNotification] : []),
  ]



  const notifications = rawNotifications.filter((n) => {
    if (n.type === 'streak' && !streakAlertsEnabled) return false
    if (n.type === 'plan' && !remindersEnabled) return false
    return true
  })

  const unreadCount = notifications.filter((n) => n.unread).length

  return (
    <div className="relative inline-block text-left">
      {/* Notification Bell Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-10 h-10 rounded-full bg-white/80 backdrop-blur-md border border-white hover:bg-white text-text-primary flex items-center justify-center relative elevation-1 transition-colors cursor-pointer"
        title="Notifications & Study Reminders"
      >
        <Bell size={18} />
        {unreadCount > 0 && (
          <span className="absolute top-2 right-2 w-2.5 h-2.5 rounded-full bg-brand-primary ring-2 ring-white animate-pulse" />
        )}
      </button>

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
              className="absolute right-0 mt-3 w-80 sm:w-96 card z-50 overflow-hidden font-sans text-text-primary"
            >
              {/* Dropdown Header */}
              <div className="bg-transparent p-4 border-b border-border flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Bell size={16} className="text-brand-primary" />
                  <h3 className="text-sm font-semibold text-text-primary">Study Reminders</h3>
                  {unreadCount > 0 && (
                    <span className="text-[10px] font-bold bg-brand-primary text-white px-2 py-0.5 rounded-full">
                      {unreadCount} new
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setShowSettings(!showSettings)}
                    className={`p-1.5 rounded-lg transition-colors cursor-pointer ${
                      showSettings ? 'bg-brand-primary-soft text-brand-primary' : 'text-text-muted hover:text-text-primary'
                    }`}
                    title="Notification Settings"
                  >
                    <Settings size={15} />
                  </button>
                  <button
                    onClick={() => setIsOpen(false)}
                    className="text-text-muted hover:text-text-primary p-1 rounded-lg transition-colors cursor-pointer"
                  >
                    <X size={16} />
                  </button>
                </div>
              </div>

              {/* Notification Settings Toggle Panel */}
              {showSettings && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="bg-white/50 border-b border-border p-4 space-y-3"
                >
                  <h4 className="text-xs font-semibold text-text-primary uppercase tracking-wider">
                    Notification Preferences
                  </h4>
                  <div className="space-y-2 text-xs">
                    <label className="flex items-center justify-between cursor-pointer">
                      <span className="font-medium text-text-secondary">Daily Study Plan Reminders</span>
                      <input
                        type="checkbox"
                        checked={remindersEnabled}
                        onChange={(e) => setRemindersEnabled(e.target.checked)}
                        className="rounded text-brand-primary focus:ring-0 cursor-pointer"
                      />
                    </label>
                    <label className="flex items-center justify-between cursor-pointer">
                      <span className="font-medium text-text-secondary">Learning Streak Alerts</span>
                      <input
                        type="checkbox"
                        checked={streakAlertsEnabled}
                        onChange={(e) => setStreakAlertsEnabled(e.target.checked)}
                        className="rounded text-brand-primary focus:ring-0 cursor-pointer"
                      />
                    </label>
                  </div>
                </motion.div>
              )}

              {/* Notifications List */}
              <div className="max-h-96 overflow-y-auto divide-y divide-border/60 p-2 space-y-1">
                {notifications.length === 0 ? (
                  <div className="p-6 text-center text-xs font-medium text-text-muted">
                    No active study notifications.
                  </div>
                ) : (
                  notifications.map((item) => (
                    <div
                      key={item.id}
                      className={`p-3.5 rounded-[1.5rem] transition-colors ${
                        item.unread ? 'bg-brand-primary-soft/40 border border-brand-primary/20' : 'hover:bg-bg-secondary'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div
                          className={`w-9 h-9 rounded-[1.25rem] flex items-center justify-center flex-shrink-0 p-1.5 elevation-1 border ${
                            item.type === 'streak'
                              ? 'bg-[#DDF4FF] border-[#1CB0F6]/30'
                              : item.type === 'plan'
                              ? 'bg-[#D7FFB8] border-[#58CC02]/30'
                              : 'bg-[#FFF0B3] border-[#FFC800]/30'
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
                            <h4 className="text-xs font-semibold text-text-primary truncate">{item.title}</h4>
                            <span className="text-[10px] text-text-muted">{item.timeAgo}</span>
                          </div>
                          <p className="text-xs text-text-secondary leading-relaxed mt-1">{item.message}</p>

                          {item.actionText && item.actionPath && (
                            <button
                              onClick={() => {
                                setIsOpen(false)
                                navigate(item.actionPath!)
                              }}
                              className="mt-2 text-xs font-semibold text-brand-primary hover:underline flex items-center gap-1 cursor-pointer"
                            >
                              <span>{item.actionText}</span>
                              <ChevronRight size={13} />
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>

              {/* Dropdown Footer */}
              <div className="bg-transparent p-3 text-center border-t border-border">
                <button
                  onClick={() => {
                    setIsOpen(false)
                    navigate('/study-plan')
                  }}
                  className="text-xs font-semibold text-brand-primary hover:underline cursor-pointer"
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
