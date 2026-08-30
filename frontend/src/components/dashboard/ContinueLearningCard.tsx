import { useNavigate } from 'react-router-dom'
import { PlayCircle, Clock } from 'lucide-react'
import { useLanguageStore } from '../../stores/languageStore'

interface ContinueLearningCardProps {
  subjectId: string
  topicId: string
  topicTitle: string
  progress: number
  lastStudied: string
  continuePath?: string
}

export default function ContinueLearningCard({ subjectId, topicId, topicTitle, progress, lastStudied, continuePath }: ContinueLearningCardProps) {
  const navigate = useNavigate()
  const { uiLanguage } = useLanguageStore()

  // Format relative time (e.g. "2 hours ago")
  const getRelativeTime = (dateStr: string) => {
    const diff = Math.floor((new Date().getTime() - new Date(dateStr).getTime()) / 1000)
    if (uiLanguage === 'sv') {
      if (diff < 60) return 'Alldeles nyss'
      if (diff < 3600) return `${Math.floor(diff / 60)} minuter sedan`
      if (diff < 86400) return `${Math.floor(diff / 3600)} timmar sedan`
      return `${Math.floor(diff / 86400)} dagar sedan`
    }
    if (diff < 60) return 'Just now'
    if (diff < 3600) return `${Math.floor(diff / 60)} minutes ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)} hours ago`
    return `${Math.floor(diff / 86400)} days ago`
  }

  return (
    <div 
      className="card p-6 flex flex-col justify-between gap-5 cursor-pointer relative overflow-hidden h-full group hover:shadow-[0_8px_30px_rgba(0,0,0,0.06)] transition-all bg-white"
      onClick={() => navigate(continuePath || (topicId ? `/subjects/${subjectId}/chat/${topicId}` : `/subjects/${subjectId}`))}
    >
      <div className="flex items-start justify-between z-10">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-[#EAF0F8] text-info flex items-center justify-center flex-shrink-0">
            <PlayCircle size={24} />
          </div>
          <div>
            <p className="text-[11px] text-text-secondary font-medium uppercase tracking-wider mb-0.5">
              {uiLanguage === 'sv' ? 'FORTSÄTT LÄRA' : 'CONTINUE LEARNING'}
            </p>
            <h3 className="font-semibold text-base text-text-primary line-clamp-1">{topicTitle}</h3>
          </div>
        </div>
      </div>
      
      <div className="mt-2 z-10">
        <div className="flex justify-between items-end mb-2">
          <span className="text-2xl font-bold text-text-primary">{progress}%</span>
          <div className="flex items-center text-[11px] text-text-secondary gap-1">
            <Clock size={12} />
            <span>{uiLanguage === 'sv' ? 'Aktiv' : 'Active'} {getRelativeTime(lastStudied)}</span>
          </div>
        </div>
        
        {/* Progress Bar */}
        <div className="w-full bg-[#F1F5F9] rounded-full h-2 overflow-hidden">
          <div 
            className="bg-brand-primary h-2 rounded-full transition-all duration-1000 ease-out" 
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
      
      {/* Decorative background element */}
      <div className="absolute -right-10 -bottom-10 w-40 h-40 bg-[#EAF0F8] rounded-full blur-3xl opacity-50 group-hover:opacity-80 transition-opacity pointer-events-none" />
    </div>
  )
}
