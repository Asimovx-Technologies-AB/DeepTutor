import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { BookOpen, ChevronRight, Sparkles, Search, Plus, Check, Clock, Play } from 'lucide-react'
import { useSubjectStore } from '../stores/subjectStore'
import { useLanguageStore } from '../stores/languageStore'
import { useTranslation } from '../utils/translations'

export default function SubjectsPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [activeTab, setActiveTab] = useState<'MY_SUBJECTS' | 'ALL' | 'IN_PROGRESS' | 'COMPLETED' | 'NOT_STARTED'>('MY_SUBJECTS')

  const { uiLanguage } = useLanguageStore()
  const t = useTranslation(uiLanguage)

  const {
    subjects,
    getSubjectProgress,
    getSubjectStatus,
    getCurrentTopic,
    getTopics,
    enrollSubject,
  } = useSubjectStore()

  // Filter Logic
  const filteredSubjects = subjects.filter((subject) => {
    // Search match
    const matchesSearch =
      subject.name.toLowerCase().includes(search.toLowerCase()) ||
      subject.description.toLowerCase().includes(search.toLowerCase()) ||
      subject.category.toLowerCase().includes(search.toLowerCase())

    if (!matchesSearch) return false

    // Tab match
    const status = getSubjectStatus(subject.id)
    if (activeTab === 'MY_SUBJECTS') return subject.isEnrolled
    if (activeTab === 'IN_PROGRESS') return subject.isEnrolled && (status === 'IN_PROGRESS' || status === 'INACTIVE')
    if (activeTab === 'COMPLETED') return status === 'COMPLETED'
    if (activeTab === 'NOT_STARTED') return status === 'NOT_STARTED'
    return true // ALL
  })

  return (
    <div className="min-h-screen bg-[#F7F7F7] pb-12">
      {/* ─── 1. HERO BANNER ─── */}
      <div className="relative bg-white border-b border-[#E2E8F0] pt-8 pb-12 overflow-hidden shadow-sm">
        <div className="absolute right-0 top-0 w-1/3 h-full pointer-events-none opacity-40">
          <div className="w-full h-full bg-gradient-to-l from-[#4F46E5]/20 via-[#4F46E5]/5 to-transparent blur-3xl"></div>
        </div>
        
        <div className="max-w-7xl mx-auto px-6 sm:px-8 relative z-10">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="max-w-2xl">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-8 h-8 rounded-xl bg-[#EEF2FF] flex items-center justify-center text-[#4F46E5] border border-[#4F46E5]/20">
                <Sparkles size={16} />
              </div>
              <span className="text-xs font-black text-[#4F46E5] uppercase tracking-widest">
                {uiLanguage === 'sv' ? 'Läroplanshubb' : 'Curriculum Hub'}
              </span>
            </div>
            <h1 className="text-4xl sm:text-5xl font-black text-[#3C3C3C] tracking-tight mb-3 leading-[1.1]">
              {t.subjects.title}
            </h1>
            <p className="text-[#777777] text-sm sm:text-base font-medium max-w-md leading-relaxed">
              {t.subjects.subtitle}
            </p>
          </motion.div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 sm:px-8 mt-8 space-y-8">
        
        {/* ─── 2. FLOATING CONTROLS BAR ─── */}
        <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4 sticky top-4 z-20">
          {/* Tab Filters */}
          <div className="flex items-center gap-1.5 bg-white border border-[#E2E8F0] p-1.5 rounded-[1.5rem] shadow-sm overflow-x-auto">
            {[
              { key: 'MY_SUBJECTS', label: t.subjects.title },
              { key: 'ALL', label: uiLanguage === 'sv' ? 'Hela katalogen' : 'All Catalog' },
              { key: 'IN_PROGRESS', label: uiLanguage === 'sv' ? 'Pågående' : 'In Progress' },
              { key: 'COMPLETED', label: uiLanguage === 'sv' ? 'Slutförda' : 'Completed' },
            ].map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key as any)}
                className={`px-4 py-2.5 rounded-[1.25rem] text-xs font-extrabold transition-all whitespace-nowrap cursor-pointer ${
                  activeTab === tab.key
                    ? 'bg-[#4F46E5] text-white shadow-md shadow-[#4F46E5]/20 scale-100'
                    : 'text-[#777777] hover:text-[#3C3C3C] hover:bg-[#F7F7F7] active:scale-95'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Search Input */}
          <div className="relative w-full md:w-80 group">
            <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#AFAFAF] group-focus-within:text-[#4F46E5] transition-colors" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-12 pr-4 py-3.5 text-sm font-bold rounded-[1.5rem] bg-white border border-[#E2E8F0] text-[#3C3C3C] placeholder-[#AFAFAF] focus:outline-none focus:border-[#4F46E5] focus:ring-4 focus:ring-[#4F46E5]/10 shadow-sm transition-all"
              placeholder={uiLanguage === 'sv' ? 'Sök ämnen eller kapitel...' : 'Search subjects or topics...'}
            />
          </div>
        </div>

        {/* ─── 3. SUBJECT CARDS GRID ─── */}
        {filteredSubjects.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredSubjects.map((subject, index) => {
              const progressVal = getSubjectProgress(subject.id)
              const status = getSubjectStatus(subject.id)
              const currentTopic = getCurrentTopic(subject.id)
              const subjectTopics = getTopics(subject.id)
              const completedCount = subjectTopics.filter((t) => t.status === 'COMPLETED').length

              return (
                <motion.div
                  key={subject.id}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      navigate(`/subjects/${subject.id}`)
                    }
                  }}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.05 }}
                  onClick={() => navigate(`/subjects/${subject.id}`)}
                  className="group relative bg-white border border-[#E2E8F0] rounded-[2rem] p-6 flex flex-col justify-between shadow-sm hover:shadow-xl hover:shadow-[#4F46E5]/10 hover:border-[#4F46E5]/40 transition-all duration-300 cursor-pointer overflow-hidden min-h-[320px]"
                >
                  {/* Decorative glow on hover */}
                  <div className="absolute inset-0 bg-gradient-to-br from-[#4F46E5]/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

                  <div className="relative z-10 space-y-5">
                    {/* Header Row: Illustration & Category Badge */}
                    <div className="flex items-start justify-between">
                      <div className="w-14 h-14 rounded-[1.25rem] bg-info-soft border border-info/20 flex items-center justify-center p-2.5 shadow-sm group-hover:scale-110 transition-transform duration-300 text-3xl">
                        {subject.emoji || subject.illustration}
                      </div>

                      <div className="flex flex-col items-end gap-1.5">
                        <span className="text-[10px] font-black uppercase tracking-wider bg-[#F7F7F7] text-[#777777] px-2.5 py-1 rounded-full border border-[#E2E8F0]">
                          {subject.category}
                        </span>
                        {status === 'COMPLETED' && (
                          <span className="text-[10px] font-bold bg-[#D7FFB8] text-[#46A302] px-2 py-0.5 rounded-full border border-[#58CC02]/30 flex items-center gap-1">
                            <Check size={10} strokeWidth={3} /> {uiLanguage === 'sv' ? 'Klar' : 'Done'}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Title & Description */}
                    <div>
                      <h3 className="font-black text-[#3C3C3C] text-xl group-hover:text-[#4F46E5] transition-colors leading-tight">
                        {subject.name}
                      </h3>
                      <p className="text-[#777777] text-xs leading-relaxed line-clamp-2 font-medium mt-2">
                        {subject.description}
                      </p>
                    </div>

                    {/* Currently Learning Highlight */}
                    {currentTopic && status !== 'COMPLETED' && (
                      <div className="bg-[#FAF8F3] border border-[#E7E1D8] rounded-[1.25rem] p-3 text-xs space-y-1 group-hover:bg-white group-hover:border-[#4F46E5]/20 transition-colors">
                        <div className="flex items-center gap-1.5 mb-1">
                          <Play size={12} className="text-[#4F46E5] fill-[#4F46E5]" />
                          <span className="text-[10px] font-black text-[#4F46E5] uppercase tracking-wider">
                            {uiLanguage === 'sv' ? 'Nästa kapitel' : 'Up Next'}
                          </span>
                        </div>
                        <p className="font-bold text-[#3C3C3C] truncate pr-2">{currentTopic.title}</p>
                      </div>
                    )}
                  </div>

                  {/* Progress & Bottom Actions */}
                  <div className="relative z-10 mt-6 pt-5 border-t border-[#E2E8F0]/80">
                    <div className="flex items-end justify-between">
                      
                      <div className="flex-1 pr-4">
                        <div className="flex items-center justify-between text-[11px] font-bold mb-2">
                          <span className="text-[#777777]">
                            {completedCount} / {subjectTopics.length} {uiLanguage === 'sv' ? 'ämnesområden' : 'topics'}
                          </span>
                          <span className="text-[#4F46E5] font-black">{progressVal}%</span>
                        </div>
                        <div className="w-full bg-[#E5E5E5] rounded-full h-2.5 overflow-hidden border border-[#E2E8F0]">
                          <div
                            className="bg-gradient-to-r from-[#4F46E5] to-[#10B981] h-full rounded-full transition-all duration-700 ease-out"
                            style={{ width: `${progressVal}%` }}
                          />
                        </div>
                      </div>

                      <div className="flex-shrink-0">
                        {!subject.isEnrolled ? (
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              enrollSubject(subject.id)
                            }}
                            className="w-10 h-10 rounded-[1.25rem] bg-white border-2 border-[#E2E8F0] text-[#777777] hover:border-[#4F46E5] hover:text-[#4F46E5] flex items-center justify-center transition-colors cursor-pointer group-hover:bg-[#4F46E5] group-hover:border-[#4F46E5] group-hover:text-white"
                          >
                            <Plus size={18} strokeWidth={3} />
                          </button>
                        ) : (
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              navigate(`/subjects/${subject.id}`)
                            }}
                            className="w-10 h-10 rounded-[1.25rem] bg-[#4F46E5] text-white flex items-center justify-center shadow-md shadow-[#4F46E5]/20 transition-transform active:scale-95 cursor-pointer group-hover:scale-110"
                          >
                            <ChevronRight size={18} strokeWidth={3} />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </motion.div>
              )
            })}
          </div>
        ) : (
          <div className="text-center py-20">
            <div className="w-20 h-20 bg-white rounded-[2rem] border border-[#E2E8F0] flex items-center justify-center mx-auto mb-4 shadow-sm">
              <Search size={32} className="text-[#AFAFAF]" />
            </div>
            <h3 className="text-xl font-black text-[#3C3C3C] mb-2">
              {uiLanguage === 'sv' ? 'Inga ämnen hittades' : 'No subjects found'}
            </h3>
            <p className="text-[#777777] text-sm font-medium">
              {uiLanguage === 'sv' ? 'Försök med andra filter eller sökord.' : 'Try adjusting your filters or search query.'}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

function formatTimeAgo(date: Date) {
  const diff = Date.now() - date.getTime()
  const hours = Math.floor(diff / (1000 * 60 * 60))
  if (hours < 1) return 'Just now'
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}
