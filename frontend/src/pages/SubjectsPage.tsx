import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { BookOpen, ChevronRight, Sparkles, Search, Plus, Check, Clock, Play } from 'lucide-react'
import { useSubjectStore } from '../stores/subjectStore'

export default function SubjectsPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [activeTab, setActiveTab] = useState<'MY_SUBJECTS' | 'ALL' | 'IN_PROGRESS' | 'COMPLETED' | 'NOT_STARTED'>('MY_SUBJECTS')

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
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-8 bg-[#F7F7F7] text-[#3C3C3C] font-sans">
      {/* ─── 1. HEADER ─── */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="space-y-2">
        <div className="flex items-center gap-2">
          <Sparkles size={16} className="text-[#1CB0F6]" />
          <span className="text-xs font-black text-[#1CB0F6] uppercase tracking-widest bg-[#DDF4FF] px-2.5 py-0.5 rounded-full border border-[#1CB0F6]/20">
            Personalized Workspace
          </span>
        </div>
        <h1 className="text-3xl font-black text-[#3C3C3C] tracking-tight">My Subjects & Learning Hub</h1>
        <p className="text-[#777777] text-sm font-medium">
          Track your progress across enrolled subjects, continue active lessons, or explore new topics.
        </p>
      </motion.div>

      {/* ─── 2. SEARCH & TAB FILTERS BAR ─── */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        {/* Tab Filters */}
        <div className="flex items-center gap-1.5 bg-white border border-[#E2E8F0] p-1.5 rounded-[1.5rem] elevation-1 overflow-x-auto">
          {[
            { key: 'MY_SUBJECTS', label: 'My Subjects' },
            { key: 'ALL', label: 'All Catalog' },
            { key: 'IN_PROGRESS', label: 'In Progress' },
            { key: 'COMPLETED', label: 'Completed' },
            { key: 'NOT_STARTED', label: 'Not Started' },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as any)}
              className={`px-3.5 py-2 rounded-[1.25rem] text-xs font-extrabold transition-all whitespace-nowrap cursor-pointer ${
                activeTab === tab.key
                  ? 'bg-[#1CB0F6] text-white elevation-1'
                  : 'text-[#777777] hover:text-[#3C3C3C] hover:bg-[#F7F7F7]'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Search Input */}
        <div className="relative w-full md:w-72">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#AFAFAF]" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 text-xs font-bold rounded-[1.5rem] bg-white border border-[#E2E8F0] text-[#3C3C3C] placeholder-[#AFAFAF] focus:outline-none focus:border-[#1CB0F6] focus:ring-2 focus:ring-[#1CB0F6]/20 elevation-1"
            placeholder="Search subjects or topics..."
          />
        </div>
      </div>

      {/* ─── 3. SUBJECT CARDS GRID ─── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
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
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05 }}
              onClick={() => navigate(`/subjects/${subject.id}`)}
              className="glass-card p-6 text-left group relative border border-[#E2E8F0] elevation-1 hover:border-[#1CB0F6]/50 cursor-pointer rounded-[2rem] bg-white flex flex-col justify-between space-y-5 transition-all hover:elevation-4 hover:scale-[1.02] active:scale-[0.98]"
            >
              <div className="space-y-4">
                {/* Header Row: Illustration & Category Badge */}
                <div className="flex items-center justify-between">
                  <div className="w-12 h-12 rounded-[1.5rem] bg-[#DDF4FF] border border-[#1CB0F6]/30 flex items-center justify-center p-2 elevation-1">
                    <img src={subject.illustration} alt={subject.name} className="w-full h-full object-contain" />
                  </div>

                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-black uppercase tracking-wider bg-[#DDF4FF] text-[#1CB0F6] px-2.5 py-0.5 rounded-full border border-[#1CB0F6]/20">
                      {subject.category}
                    </span>

                    {status === 'COMPLETED' && (
                      <span className="text-[10px] font-bold bg-[#D7FFB8] text-[#46A302] px-2 py-0.5 rounded-full border border-[#58CC02]/30">
                        Done 🎉
                      </span>
                    )}
                  </div>
                </div>

                {/* Title & Description */}
                <div>
                  <h3 className="font-black text-[#3C3C3C] text-lg group-hover:text-[#1CB0F6] transition-colors">
                    {subject.name}
                  </h3>
                  <p className="text-[#777777] text-xs leading-relaxed line-clamp-2 font-medium mt-1">
                    {subject.description}
                  </p>
                </div>

                {/* Currently Learning Highlight */}
                {currentTopic && status !== 'COMPLETED' && (
                  <div className="bg-[#FFFFFF] border border-[#1CB0F6]/20 rounded-[1.5rem] p-3 text-xs space-y-1">
                    <span className="text-[10px] font-black text-[#1CB0F6] uppercase tracking-wider">Currently Learning</span>
                    <p className="font-bold text-[#3C3C3C] truncate">{currentTopic.title}</p>
                  </div>
                )}
              </div>

              {/* Progress & Bottom Actions */}
              <div className="space-y-3 pt-3 border-t border-[#E2E8F0]/60">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs font-bold">
                    <span className="text-[#777777]">
                      {completedCount} / {subjectTopics.length} topics completed
                    </span>
                    <span className="text-[#3C3C3C] font-black">{progressVal}%</span>
                  </div>
                  <div className="w-full bg-[#E5E5E5] rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-[#1CB0F6] h-full rounded-full transition-all duration-300"
                      style={{ width: `${progressVal}%` }}
                    />
                  </div>
                </div>

                <div className="flex items-center justify-between pt-1">
                  {!subject.isEnrolled ? (
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        enrollSubject(subject.id)
                      }}
                      className="btn-primary text-xs py-2 px-3 rounded-[1.25rem] flex items-center gap-1.5 cursor-pointer elevation-1"
                    >
                      <Plus size={14} /> Add Subject
                    </button>
                  ) : (
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        navigate(`/subjects/${subject.id}`)
                      }}
                      className="btn-primary text-xs font-extrabold py-2 px-4 rounded-[1.25rem] flex items-center gap-1.5 cursor-pointer elevation-1"
                    >
                      <span>{status === 'COMPLETED' ? 'Review Workspace' : 'Continue'}</span>
                      <ChevronRight size={14} />
                    </button>
                  )}

                  <span className="text-[11px] font-semibold text-[#AFAFAF] flex items-center gap-1">
                    <Clock size={12} />
                    {subject.lastStudiedAt
                      ? `Active ${Math.round((Date.now() - new Date(subject.lastStudiedAt).getTime()) / 3600000)}h ago`
                      : 'Not started'}
                  </span>
                </div>
              </div>
            </motion.div>
          )
        })}
      </div>

      {/* Empty State */}
      {filteredSubjects.length === 0 && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col items-center justify-center py-20 px-4 text-center">
          <div className="w-32 h-32 mb-4 pointer-events-none">
            <img src="/assets/illustrations/empty_state.jpg" alt="Empty State" className="w-full h-full object-contain mix-blend-multiply" />
          </div>
          <h3 className="text-xl font-bold text-[#3C3C3C] tracking-tight mb-2">No subjects found</h3>
          <p className="text-sm text-[#777777] font-medium max-w-sm mx-auto mb-8">
            Try adjusting your search filter or explore the full catalog to find new subjects to master.
          </p>
          <button
            onClick={() => {
              setSearch('')
              setActiveTab('ALL')
            }}
            className="btn-primary text-sm font-medium py-2.5 px-6 rounded-lg cursor-pointer flex items-center gap-2"
          >
            Explore Catalog <ChevronRight size={16} />
          </button>
        </motion.div>
      )}
    </div>
  )
}
