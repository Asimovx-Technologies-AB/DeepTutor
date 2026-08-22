import { Flame } from 'lucide-react'
import { useLanguageStore } from '../../stores/languageStore'

interface LearningStreakProps {
  currentStreak: number
  longestStreak: number
}

export default function LearningStreak({ currentStreak, longestStreak }: LearningStreakProps) {
  const { uiLanguage } = useLanguageStore()
  const days = uiLanguage === 'sv' ? ['M', 'T', 'O', 'T', 'F', 'L', 'S'] : ['M', 'T', 'W', 'T', 'F', 'S', 'S']
  const activeDays = [true, true, false, true, true, false, true] // Mock pattern based on streak

  return (
    <div className="card p-6 flex flex-col justify-between h-full bg-gradient-to-br from-[#EFF6FF] to-white border border-[#E2E8F0]">
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-[15px] text-text-primary">
            {uiLanguage === 'sv' ? 'Studiesvit' : 'Learning Streak'}
          </h3>
          <div className="w-8 h-8 rounded-full bg-info-soft text-info flex items-center justify-center border border-info/20">
            <Flame size={16} fill="currentColor" />
          </div>
        </div>
        
        <div className="flex items-end gap-2 mb-6">
          <span className="text-4xl font-bold text-text-primary leading-none">{currentStreak}</span>
          <span className="text-sm font-medium text-text-secondary mb-1">
            {uiLanguage === 'sv' ? 'Dagar' : 'Days'}
          </span>
        </div>
        
        <p className="text-[12px] text-text-secondary">
          {uiLanguage === 'sv' ? 'Längsta svit:' : 'Longest streak:'} <strong className="text-text-primary">{longestStreak} {uiLanguage === 'sv' ? 'dagar' : 'days'}</strong>
        </p>
      </div>

      <div className="mt-6 border-t border-[#E2E8F0] pt-4">
        <div className="flex justify-between items-center">
          {days.map((day, idx) => {
            const isActive = activeDays[idx]
            return (
              <div key={idx} className="flex flex-col items-center gap-1.5">
                <div 
                  className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold transition-all ${
                    isActive 
                      ? 'bg-info text-white shadow-sm shadow-info/30' 
                      : 'bg-white text-text-muted border border-[#E2E8F0]'
                  }`}
                >
                  {day}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
