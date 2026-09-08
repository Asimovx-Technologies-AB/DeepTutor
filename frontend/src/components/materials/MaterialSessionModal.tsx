import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { X, MessageSquare, Plus, ArrowRight, Sparkles, Clock, BookOpen, Layers } from 'lucide-react'
import { studyApi, documentsApi } from '../../services/api'

export interface LinkedSession {
  id: string
  title: string
  subject?: string
  created_at?: string
}

export interface StudyDocument {
  id: string
  topic_id: string
  file_name: string
  file_type: string
  indexed: boolean
  doc_hash?: string
  index_status?: string
  index_progress?: number
  key_topics?: string[]
  detected_subject?: string
  linked_sessions?: LinkedSession[]
  session_count?: number
}

interface MaterialSessionModalProps {
  document: StudyDocument | null
  isOpen: boolean
  onClose: () => void
}

function displayName(fileName: string) {
  return fileName.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').trim()
}

function formatDate(dateStr?: string) {
  if (!dateStr) return 'Recently'
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return 'Recently'
  }
}

export default function MaterialSessionModal({
  document,
  isOpen,
  onClose,
}: MaterialSessionModalProps) {
  const navigate = useNavigate()
  const [isCreating, setIsCreating] = useState(false)

  if (!isOpen || !document) return null

  const cleanName = displayName(document.file_name)
  const sessions = document.linked_sessions || (document.topic_id ? [{ id: document.topic_id, title: `${document.detected_subject || cleanName} Study Room` }] : [])

  const handleOpenSession = (sessionId: string) => {
    onClose()
    navigate(`/chat/${sessionId}`)
  }

  const handleCreateNewSession = async () => {
    setIsCreating(true)
    try {
      const subject = document.detected_subject || cleanName
      const title = `${cleanName} Study Room`
      
      const res = await studyApi.createSession({
        subject,
        title,
      })
      const newSessionId = res.data?.id || res.data?.session_id || `session_${Date.now()}`

      // Link material to the new session
      try {
        await documentsApi.linkToSession({
          session_id: newSessionId,
          doc_id: document.id,
          doc_hash: document.doc_hash,
          filename: document.file_name,
        })
      } catch (linkErr) {
        console.warn('Document link warning:', linkErr)
      }

      onClose()
      navigate(`/chat/${newSessionId}`)
    } catch (err) {
      console.error('Failed to create new session with material:', err)
      // Fallback: navigate with timestamp session ID
      const fallbackId = `session_${Date.now()}`
      onClose()
      navigate(`/chat/${fallbackId}`)
    } finally {
      setIsCreating(false)
    }
  }

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
        {/* Backdrop */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm"
        />

        {/* Modal Window */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 16 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 16 }}
          transition={{ type: 'spring', damping: 25, stiffness: 300 }}
          className="relative w-full max-w-lg bg-white rounded-3xl shadow-2xl border border-slate-100 overflow-hidden z-10"
        >
          {/* Header Banner */}
          <div className="bg-gradient-to-r from-indigo-600 via-indigo-700 to-purple-700 p-6 text-white relative">
            <button
              onClick={onClose}
              className="absolute top-5 right-5 w-8 h-8 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center transition-colors"
            >
              <X size={18} />
            </button>
            <div className="flex items-center gap-2 text-indigo-200 text-xs font-bold uppercase tracking-wider mb-2">
              <Sparkles size={14} className="text-amber-300" />
              <span>Select Study Session</span>
            </div>
            <h3 className="text-2xl font-black tracking-tight capitalize line-clamp-1">{cleanName}</h3>
            <p className="text-indigo-100/80 text-xs font-medium mt-1">
              {document.detected_subject || 'General Study'} · {document.file_type?.toUpperCase()}
            </p>
          </div>

          <div className="p-6 space-y-6">
            {/* Quick Actions: New Session Button */}
            <button
              onClick={handleCreateNewSession}
              disabled={isCreating}
              className="w-full group flex items-center justify-between p-4 rounded-2xl bg-indigo-50/80 hover:bg-indigo-600 border border-indigo-100 hover:border-indigo-600 text-indigo-950 hover:text-white transition-all shadow-sm hover:shadow-md cursor-pointer"
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-indigo-600 text-white group-hover:bg-white group-hover:text-indigo-600 flex items-center justify-center transition-colors shadow-sm">
                  <Plus size={20} className="stroke-[2.5]" />
                </div>
                <div className="text-left">
                  <div className="font-black text-sm group-hover:text-white">Start New Study Room</div>
                  <div className="text-[11px] text-indigo-700/80 group-hover:text-indigo-100 font-medium">
                    Create a fresh chat workspace with this material
                  </div>
                </div>
              </div>
              <ArrowRight size={18} className="text-indigo-400 group-hover:text-white group-hover:translate-x-1 transition-all" />
            </button>

            {/* Existing Linked Sessions */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2 text-xs font-black uppercase tracking-wider text-slate-500">
                  <Layers size={14} className="text-indigo-600" />
                  <span>Existing Study Rooms ({sessions.length})</span>
                </div>
              </div>

              {sessions.length > 0 ? (
                <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                  {sessions.map((sess) => (
                    <button
                      key={sess.id}
                      onClick={() => handleOpenSession(sess.id)}
                      className="w-full flex items-center justify-between p-3.5 rounded-2xl bg-slate-50 hover:bg-white border border-slate-200/80 hover:border-indigo-500/50 hover:shadow-sm transition-all text-left group cursor-pointer"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-8 h-8 rounded-xl bg-slate-200/60 group-hover:bg-indigo-100 text-slate-600 group-hover:text-indigo-600 flex items-center justify-center transition-colors shrink-0">
                          <MessageSquare size={16} />
                        </div>
                        <div className="min-w-0">
                          <div className="font-bold text-sm text-slate-800 group-hover:text-indigo-600 transition-colors truncate">
                            {sess.title || 'Study Room'}
                          </div>
                          <div className="flex items-center gap-2 text-[11px] text-slate-400 font-medium mt-0.5">
                            <Clock size={11} />
                            <span>{formatDate(sess.created_at)}</span>
                          </div>
                        </div>
                      </div>
                      <ArrowRight size={16} className="text-slate-300 group-hover:text-indigo-600 group-hover:translate-x-0.5 transition-all shrink-0 ml-2" />
                    </button>
                  ))}
                </div>
              ) : (
                <div className="p-4 rounded-2xl bg-slate-50 border border-dashed border-slate-200 text-center text-xs text-slate-400 font-medium">
                  No previous sessions linked yet. Click above to start your first study room!
                </div>
              )}
            </div>

            {/* Extracted Key Topics */}
            {document.key_topics && document.key_topics.length > 0 && (
              <div>
                <div className="flex items-center gap-1.5 text-xs font-black uppercase tracking-wider text-slate-500 mb-2">
                  <BookOpen size={13} className="text-purple-600" />
                  <span>Key Concepts in Material</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {document.key_topics.slice(0, 6).map((topic) => (
                    <span
                      key={topic}
                      className="px-2.5 py-1 rounded-xl bg-purple-50 border border-purple-100 text-[11px] font-bold text-purple-700"
                    >
                      {topic}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  )
}
