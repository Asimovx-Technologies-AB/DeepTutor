import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { ArrowLeft, MessageSquare, BookOpen, ChevronRight, Trophy, FileText } from 'lucide-react'
import { subjectsApi } from '../services/api'
import { chatApi } from '../services/api'

const MOCK_TOPICS = [
  { id: 't1', title: 'Newton\'s Laws of Motion', description: 'Forces, acceleration, and momentum — the foundation of classical mechanics', difficulty_level: 'easy', order_index: 1 },
  { id: 't2', title: 'Thermodynamics', description: 'Heat, energy transfer, entropy, and the laws governing thermal systems', difficulty_level: 'medium', order_index: 2 },
  { id: 't3', title: 'Electromagnetism', description: 'Electric fields, magnetic forces, Maxwell\'s equations, and electromagnetic waves', difficulty_level: 'hard', order_index: 3 },
  { id: 't4', title: 'Wave Mechanics', description: 'Oscillations, wave propagation, interference, and the Doppler effect', difficulty_level: 'medium', order_index: 4 },
  { id: 't5', title: 'Quantum Physics', description: 'Wave-particle duality, Schrödinger equation, and quantum tunneling', difficulty_level: 'hard', order_index: 5 },
  { id: 't6', title: 'Special Relativity', description: 'Time dilation, length contraction, mass-energy equivalence', difficulty_level: 'hard', order_index: 6 },
]

const DIFF_LABELS: Record<string, string> = {
  easy: 'Beginner', medium: 'Intermediate', hard: 'Advanced'
}

export default function TopicsPage() {
  const { subjectId } = useParams<{ subjectId: string }>()
  const navigate = useNavigate()

  const { data: topics, isLoading } = useQuery({
    queryKey: ['topics', subjectId],
    queryFn: () => subjectsApi.topics(subjectId!).then((r) => r.data),
  })

  const displayTopics: any[] = topics ?? MOCK_TOPICS

  const startChat = async (topic: any) => {
    try {
      const res = await chatApi.createSession(topic.id, `Chat: ${topic.title}`)
      navigate(`/chat/${res.data.id}`)
    } catch {
      navigate('/chat')
    }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto bg-[#F7F7F7]">
      {/* Back */}
      <motion.button
        initial={{ opacity: 0, x: -8 }}
        animate={{ opacity: 1, x: 0 }}
        onClick={() => navigate('/subjects')}
        className="flex items-center gap-2 text-[#777777] hover:text-[#1CB0F6] transition-colors mb-6 text-sm font-bold cursor-pointer"
      >
        <ArrowLeft size={16} /> Back to Subjects
      </motion.button>

      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
        <h1 className="text-3xl font-black text-[#3C3C3C] mb-2">Topics</h1>
        <p className="text-[#777777] text-sm font-medium">Select a topic to start an AI tutoring session or take a quiz</p>
      </motion.div>

      {/* Topics list */}
      {isLoading ? (
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => <div key={i} className="skeleton h-28 rounded-[1.5rem]" />)}
        </div>
      ) : (
        <div className="space-y-3">
          {displayTopics.map((topic: any, i: number) => (
            <motion.div
              key={topic.id}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.07 }}
              className="glass-card p-5 flex items-center gap-4 group border border-[#E2E8F0] elevation-1 hover:border-[#1CB0F6]/40"
            >
              {/* Order number */}
              <div className="w-10 h-10 rounded-[1.25rem] bg-[#DDF4FF] border border-[#1CB0F6]/30 flex items-center justify-center text-sm font-black text-[#1CB0F6] flex-shrink-0">
                {topic.order_index ?? i + 1}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="font-extrabold text-[#3C3C3C] text-sm group-hover:text-[#1CB0F6] transition-colors">
                    {topic.title}
                  </h3>
                  <span className={`badge badge-${topic.difficulty_level}`}>
                    {DIFF_LABELS[topic.difficulty_level] ?? topic.difficulty_level}
                  </span>
                </div>
                <p className="text-[#777777] text-xs line-clamp-1 font-medium">{topic.description}</p>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={() => navigate(`/flashcards/${topic.id}`)}
                  className="btn-ghost flex items-center gap-1.5 text-xs px-3 py-2 cursor-pointer"
                >
                  <BookOpen size={13} className="text-[#1CB0F6]" /> Flashcards
                </button>
                <button
                  onClick={() => navigate(`/quiz/${topic.id}`)}
                  className="btn-ghost flex items-center gap-1.5 text-xs px-3 py-2 cursor-pointer"
                >
                  <Trophy size={13} className="text-[#FFC800]" /> Quiz
                </button>
                <button
                  onClick={() => startChat(topic)}
                  className="btn-primary flex items-center gap-1.5 text-xs px-3 py-2 cursor-pointer elevation-1"
                >
                  <MessageSquare size={13} /> Chat
                </button>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  )
}
