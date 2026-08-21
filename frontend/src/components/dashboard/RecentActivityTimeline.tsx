import { PlayCircle, CheckCircle, Award } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

interface Activity {
  id: string
  activity_type: string
  title: string
  subject_id: string | null
  topic_id: string | null
  timestamp: string
}

interface RecentActivityTimelineProps {
  activities: Activity[] | undefined
  isLoading: boolean
}

export default function RecentActivityTimeline({ activities, isLoading }: RecentActivityTimelineProps) {
  const navigate = useNavigate()

  // Format relative time (e.g. "2 hours ago")
  const getRelativeTime = (dateStr: string) => {
    const diff = Math.floor((new Date().getTime() - new Date(dateStr).getTime()) / 1000)
    if (diff < 60) return 'Just now'
    if (diff < 3600) return `${Math.floor(diff / 60)} minutes ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)} hours ago`
    return `${Math.floor(diff / 86400)} days ago`
  }

  const getIcon = (type: string) => {
    if (type.includes('start')) return <PlayCircle size={14} className="text-blue-500" />
    if (type.includes('complete')) return <CheckCircle size={14} className="text-green-500" />
    if (type.includes('quiz') || type.includes('goal')) return <Award size={14} className="text-orange-500" />
    return <div className="w-2 h-2 rounded-full bg-[#1E293B]" />
  }

  if (isLoading) {
    return (
      <div className="card p-6 flex-1 flex flex-col relative min-h-[250px] animate-pulse">
        <div className="h-6 w-32 bg-gray-200 rounded mb-6"></div>
        <div className="space-y-4">
          <div className="h-10 bg-gray-100 rounded w-full"></div>
          <div className="h-10 bg-gray-100 rounded w-3/4"></div>
          <div className="h-10 bg-gray-100 rounded w-5/6"></div>
        </div>
      </div>
    )
  }

  if (!activities || activities.length === 0) {
    return (
      <div className="card p-6 flex-1 flex flex-col items-center justify-center min-h-[250px] bg-slate-50 border border-dashed border-slate-200">
        <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center mb-3">
          <span className="text-2xl">🌱</span>
        </div>
        <h3 className="font-semibold text-[#1E293B] mb-1">No recent activity</h3>
        <p className="text-[12px] text-[#64748B] max-w-[200px] text-center mb-4">
          Start a course to see your learning progress here.
        </p>
        <button 
          onClick={() => navigate('/subjects')}
          className="btn-primary px-4 py-1.5 text-[12px]"
        >
          Explore Courses
        </button>
      </div>
    )
  }

  return (
    <div className="card p-6 flex-1 flex flex-col relative min-h-[250px]">
      <h3 className="font-semibold text-lg text-[#1E293B] mb-6">Recent Activity</h3>
      
      <div className="relative pl-3 space-y-6 flex-1 border-l-2 border-[#F1F5F9] ml-2">
        {activities.map((act) => (
          <div key={act.id} className="relative flex items-center">
            {/* Timeline dot */}
            <div className="absolute -left-[22px] w-6 h-6 rounded-full bg-white border-2 border-[#F1F5F9] flex items-center justify-center shadow-sm">
              {getIcon(act.activity_type)}
            </div>
            
            <div 
              className={`ml-4 p-3 rounded-xl bg-slate-50 border border-slate-100 flex-1 hover:shadow-sm transition-shadow cursor-pointer ${act.subject_id ? 'hover:border-slate-200' : ''}`}
              onClick={() => act.subject_id && navigate(`/subjects/${act.subject_id}/workspace`)}
            >
              <h4 className="text-[13px] font-medium text-[#1E293B]">{act.title}</h4>
              <p className="text-[11px] text-[#64748B] mt-0.5">{getRelativeTime(act.timestamp)}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
