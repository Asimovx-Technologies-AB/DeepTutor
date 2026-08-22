import { BookOpen, CheckCircle, Clock, Flame, Trophy, Play } from 'lucide-react'
import { useLanguageStore } from '../../stores/languageStore'

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
  const { uiLanguage } = useLanguageStore()
  if (!stats) return null

  const statItems = [
    { 
      label: uiLanguage === 'sv' ? 'Pågående' : 'In Progress', 
      value: stats.courses_in_progress, 
      icon: <Play size={18} className="text-info" />,
      color: 'bg-info-soft text-info'
    },
    { 
      label: uiLanguage === 'sv' ? 'Slutförda' : 'Completed', 
      value: stats.courses_completed, 
      icon: <CheckCircle size={18} className="text-success" />,
      color: 'bg-success-soft text-success'
    },
    { 
      label: uiLanguage === 'sv' ? 'Studiestimmar' : 'Learning Hours', 
      value: (stats.total_learning_hours || 0).toFixed(1), 
      icon: <Clock size={18} className="text-brand-primary" />,
      color: 'bg-brand-primary-soft text-brand-primary'
    },
    { 
      label: uiLanguage === 'sv' ? 'Nuvarande svit' : 'Current Streak', 
      value: `${stats.current_streak} ${uiLanguage === 'sv' ? 'dagar' : 'days'}`, 
      icon: <Flame size={18} className="text-brand-primary" />,
      color: 'bg-brand-primary-soft text-brand-primary'
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
            <p className="text-[11px] text-text-secondary font-medium">{item.label}</p>
            <p className="text-lg font-semibold text-text-primary leading-tight mt-0.5">{item.value}</p>
          </div>
        </div>
      ))}
    </div>
  )
}
