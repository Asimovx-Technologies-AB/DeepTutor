import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { BookOpen, ChevronRight, Sparkles, Search } from 'lucide-react'
import { subjectsApi } from '../services/api'
import { useState } from 'react'

const GRADIENTS = [
  'from-indigo-500 to-violet-600',
  'from-violet-500 to-pink-600',
  'from-cyan-500 to-blue-600',
  'from-emerald-500 to-cyan-600',
  'from-orange-500 to-red-600',
  'from-rose-500 to-pink-600',
  'from-yellow-500 to-orange-600',
  'from-teal-500 to-emerald-600',
]

const MOCK_SUBJECTS = [
  { id: '1', name: 'Physics', description: 'Mechanics, thermodynamics, electromagnetism & modern physics', icon: '⚛️', topic_count: 12 },
  { id: '2', name: 'Biology', description: 'Cell biology, genetics, ecology & human physiology', icon: '🧬', topic_count: 15 },
  { id: '3', name: 'Mathematics', description: 'Algebra, calculus, statistics & discrete math', icon: '📐', topic_count: 18 },
  { id: '4', name: 'Geography', description: 'Physical geography, climate, maps & world regions', icon: '🌍', topic_count: 10 },
  { id: '5', name: 'History', description: 'Ancient civilizations, world wars & modern history', icon: '📜', topic_count: 14 },
  { id: '6', name: 'Computer Science', description: 'Algorithms, data structures, AI & systems programming', icon: '💻', topic_count: 20 },
  { id: '7', name: 'Chemistry', description: 'Organic chemistry, reactions, periodic table & lab safety', icon: '🧪', topic_count: 13 },
  { id: '8', name: 'Literature', description: 'Classic literature, poetry, analysis & creative writing', icon: '📚', topic_count: 9 },
]

export default function SubjectsPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')

  const { data: subjects, isLoading } = useQuery({
    queryKey: ['subjects'],
    queryFn: () => subjectsApi.list().then((r) => r.data),
  })

  const displaySubjects = (subjects ?? MOCK_SUBJECTS).filter((s: any) =>
    s.name.toLowerCase().includes(search.toLowerCase()) ||
    s.description?.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
        <div className="flex items-center gap-2 mb-1">
          <Sparkles size={16} className="text-indigo-400" />
          <span className="text-xs font-semibold text-indigo-400 uppercase tracking-widest">Learning Library</span>
        </div>
        <h1 className="text-3xl font-bold text-white mb-2">Browse Subjects</h1>
        <p className="text-slate-400 text-sm">
          Choose a subject to explore topics and start an AI tutoring session
        </p>
      </motion.div>

      {/* Search */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }} className="mb-6">
        <div className="relative max-w-md">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input-base pl-9"
            placeholder="Search subjects..."
          />
        </div>
      </motion.div>

      {/* Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="skeleton h-48 rounded-2xl" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {displaySubjects.map((subject: any, i: number) => (
            <motion.button
              key={subject.id}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06 }}
              onClick={() => navigate(`/subjects/${subject.id}/topics`)}
              className="glass-card p-6 text-left group relative overflow-hidden"
            >
              {/* Gradient background blur */}
              <div className={`absolute -top-8 -right-8 w-24 h-24 rounded-full bg-gradient-to-br ${GRADIENTS[i % GRADIENTS.length]} opacity-10 blur-xl group-hover:opacity-20 transition-opacity`} />

              <div className="relative">
                <div className={`w-12 h-12 rounded-2xl bg-gradient-to-br ${GRADIENTS[i % GRADIENTS.length]} flex items-center justify-center text-2xl mb-4 shadow-lg`}>
                  {subject.icon}
                </div>

                <h3 className="font-bold text-white text-lg mb-1 group-hover:text-indigo-300 transition-colors">
                  {subject.name}
                </h3>
                <p className="text-slate-500 text-xs leading-relaxed mb-4 line-clamp-2">
                  {subject.description}
                </p>

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <BookOpen size={12} className="text-slate-600" />
                    <span className="text-xs text-slate-500 font-medium">
                      {subject.topic_count} topics
                    </span>
                  </div>
                  <div className="w-7 h-7 rounded-full bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center group-hover:bg-indigo-500/20 group-hover:border-indigo-500/40 transition-all">
                    <ChevronRight size={13} className="text-indigo-400 group-hover:translate-x-0.5 transition-transform" />
                  </div>
                </div>
              </div>
            </motion.button>
          ))}
        </div>
      )}

      {displaySubjects.length === 0 && !isLoading && (
        <div className="text-center py-20">
          <div className="text-4xl mb-3">🔍</div>
          <p className="text-slate-400 font-semibold">No subjects found</p>
          <p className="text-slate-600 text-sm mt-1">Try a different search term</p>
        </div>
      )}
    </div>
  )
}
