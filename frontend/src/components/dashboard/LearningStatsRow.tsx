import { BookOpen, CheckCircle, Clock, Flame, Trophy, Play } from 'lucide-react'

interface LearningStatsRowProps {
  stats: {
    courses_completed: number
    courses_in_progress: number
    total_learning_hours: number
    lessons_completed: number
    current_streak: number
    longest_streak: number
  } | undefined
}

export default function LearningStatsRow({ stats }: LearningStatsRowProps) {
  if (!stats) return null

  const statItems = [
    { 
      label: 'In Progress', 
      value: stats.courses_in_progress, 
      icon: <Play size={18} className="text-blue-500" />,
      color: 'bg-blue-50 text-blue-700'
    },
    { 
      label: 'Completed', 
      value: stats.courses_completed, 
      icon: <CheckCircle size={18} className="text-green-500" />,
      color: 'bg-green-50 text-green-700'
    },
    { 
      label: 'Learning Hours', 
      value: stats.total_learning_hours.toFixed(1), 
      icon: <Clock size={18} className="text-purple-500" />,
      color: 'bg-purple-50 text-purple-700'
    },
    { 
      label: 'Current Streak', 
      value: `${stats.current_streak} days`, 
      icon: <Flame size={18} className="text-orange-500" />,
      color: 'bg-orange-50 text-orange-700'
    },
  ]

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {statItems.map((item, idx) => (
        <div key={idx} className="card p-4 flex items-center gap-4 hover:shadow-md transition-shadow">
          <div className={`w-10 h-10 rounded-xl ${item.color} flex items-center justify-center flex-shrink-0`}>
            {item.icon}
          </div>
          <div>
            <p className="text-[11px] text-[#64748B] font-medium">{item.label}</p>
            <p className="text-lg font-semibold text-[#1E293B] leading-tight mt-0.5">{item.value}</p>
          </div>
        </div>
      ))}
    </div>
  )
}
