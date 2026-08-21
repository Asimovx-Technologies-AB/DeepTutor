import { useNavigate } from 'react-router-dom'
import { PlayCircle, Clock } from 'lucide-react'

interface ContinueLearningCardProps {
  subjectId: string
  topicId: string
  topicTitle: string
  progress: number
  lastStudied: string
}

export default function ContinueLearningCard({ subjectId, topicId, topicTitle, progress, lastStudied }: ContinueLearningCardProps) {
  const navigate = useNavigate()

  // Format relative time (e.g. "2 hours ago")
  const getRelativeTime = (dateStr: string) => {
    const diff = Math.floor((new Date().getTime() - new Date(dateStr).getTime()) / 1000)
    if (diff < 60) return 'Just now'
    if (diff < 3600) return `${Math.floor(diff / 60)} minutes ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)} hours ago`
    return `${Math.floor(diff / 86400)} days ago`
  }

  return (
    <div 
      className="card p-6 flex flex-col justify-between gap-5 cursor-pointer relative overflow-hidden h-full group hover:shadow-[0_8px_30px_rgba(0,0,0,0.06)] transition-all bg-white"
      onClick={() => navigate(`/subjects/${subjectId}/workspace`)}
    >
      <div className="flex items-start justify-between z-10">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-[#EAF0F8] text-blue-500 flex items-center justify-center flex-shrink-0">
            <PlayCircle size={24} />
          </div>
          <div>
            <p className="text-[11px] text-[#64748B] font-medium uppercase tracking-wider mb-0.5">Continue Learning</p>
            <h3 className="font-semibold text-base text-[#1E293B] line-clamp-1">{topicTitle}</h3>
          </div>
        </div>
      </div>
      
      <div className="mt-2 z-10">
        <div className="flex justify-between items-end mb-2">
          <span className="text-2xl font-bold text-[#1E293B]">{progress}%</span>
          <div className="flex items-center text-[11px] text-[#64748B] gap-1">
            <Clock size={12} />
            <span>Active {getRelativeTime(lastStudied)}</span>
          </div>
        </div>
        
        {/* Progress Bar */}
        <div className="w-full bg-[#F1F5F9] rounded-full h-2 overflow-hidden">
          <div 
            className="bg-[#1E293B] h-2 rounded-full transition-all duration-1000 ease-out" 
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
      
      {/* Decorative background element */}
      <div className="absolute -right-10 -bottom-10 w-40 h-40 bg-[#EAF0F8] rounded-full blur-3xl opacity-50 group-hover:opacity-80 transition-opacity pointer-events-none" />
    </div>
  )
}
