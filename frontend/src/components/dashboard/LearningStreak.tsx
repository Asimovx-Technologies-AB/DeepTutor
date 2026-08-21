import { Flame } from 'lucide-react'

interface LearningStreakProps {
  currentStreak: number
  longestStreak: number
}

export default function LearningStreak({ currentStreak, longestStreak }: LearningStreakProps) {
  // Simple 7-day visualization 
  // (In a real app, we'd fetch the last 7 days of activity to accurately highlight active days)
  const days = ['M', 'T', 'W', 'T', 'F', 'S', 'S']
  const activeDays = [true, true, false, true, true, false, true] // Mock pattern based on streak

  return (
    <div className="card p-6 flex flex-col justify-between h-full bg-gradient-to-br from-orange-50 to-white border border-orange-100">
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-[15px] text-[#1E293B]">Learning Streak</h3>
          <div className="w-8 h-8 rounded-full bg-orange-100 text-orange-500 flex items-center justify-center">
            <Flame size={16} fill="currentColor" />
          </div>
        </div>
        
        <div className="flex items-end gap-2 mb-6">
          <span className="text-4xl font-bold text-[#1E293B] leading-none">{currentStreak}</span>
          <span className="text-sm font-medium text-[#64748B] mb-1">Days</span>
        </div>
        
        <p className="text-[12px] text-[#64748B]">
          Longest streak: <strong className="text-[#1E293B]">{longestStreak} days</strong>
        </p>
      </div>

      <div className="mt-6 border-t border-orange-100 pt-4">
        <div className="flex justify-between items-center">
          {days.map((day, idx) => {
            const isActive = activeDays[idx]
            return (
              <div key={idx} className="flex flex-col items-center gap-1.5">
                <div 
                  className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold transition-all ${
                    isActive 
                      ? 'bg-orange-500 text-white shadow-[0_4px_10px_rgba(249,115,22,0.3)]' 
                      : 'bg-white text-[#94A3B8] border border-[#E2E8F0]'
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
