import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { X, MessageSquare, Plus, ArrowRight, Clock, BookOpen, Layers, Sparkles } from 'lucide-react'
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
  onSessionCreated?: (sessionId: string) => void
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
  onSessionCreated,
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

      onSessionCreated?.(newSessionId)
      onClose()
      navigate(`/chat/${newSessionId}`)
    } catch (err) {
      console.error('Failed to create new session with material:', err)
      // Fallback: navigate with timestamp session ID
      const fallbackId = `session_${Date.now()}`
      onSessionCreated?.(fallbackId)
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
          className="fixed inset-0 bg-black/40 backdrop-blur-sm"
        />

        {/* Modal Window */}
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 12 }}
          transition={{ duration: 0.18, ease: 'easeOut' }}
          className="relative w-full max-w-lg bg-white rounded-2xl shadow-xl border border-zinc-200 overflow-hidden z-10"
        >
          {/* Header */}
          <div className="p-6 border-b border-zinc-100 flex items-start justify-between gap-4">
            <div className="space-y-1 min-w-0">
              <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-zinc-100 border border-zinc-200/80 text-[11px] font-semibold text-zinc-700 uppercase tracking-wider">
                <Sparkles size={12} className="text-zinc-800" />
                <span>Select Study Session</span>
              </div>
              <h3 className="text-xl font-bold text-zinc-900 tracking-tight truncate capitalize pt-1">
                {cleanName}
              </h3>
              <p className="text-xs text-zinc-500 font-medium">
                {document.detected_subject || 'General Study'} · {document.file_type?.toUpperCase()}
              </p>
            </div>

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-800 hover:bg-zinc-100 transition-colors shrink-0"
              aria-label="Close"
            >
              <X size={18} />
            </button>
          </div>

          <div className="p-6 space-y-5">
            {/* Quick Actions: Start New Room */}
            <button
              onClick={handleCreateNewSession}
              disabled={isCreating}
              className="w-full group flex items-center justify-between p-4 rounded-xl bg-white hover:bg-zinc-50 border-2 border-zinc-900 text-zinc-900 transition-all shadow-sm cursor-pointer disabled:opacity-50"
            >
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-zinc-100 border border-zinc-300 text-zinc-900 flex items-center justify-center transition-colors">
                  <Plus size={18} className="stroke-[2.5]" />
                </div>
                <div className="text-left">
                  <div className="font-bold text-sm text-zinc-900">Start New Study Room</div>
                  <div className="text-xs text-zinc-500 font-normal">
                    Create a fresh chat workspace with this material
                  </div>
                </div>
              </div>
              <ArrowRight size={18} className="text-zinc-600 group-hover:text-zinc-900 group-hover:translate-x-0.5 transition-all" />
            </button>

            {/* Existing Linked Sessions */}
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
                  <Layers size={13} className="text-zinc-700" />
                  <span>Existing Study Rooms ({sessions.length})</span>
                </div>
              </div>

              {sessions.length > 0 ? (
                <div className="space-y-2 max-h-52 overflow-y-auto pr-1">
                  {sessions.map((sess) => (
                    <button
                      key={sess.id}
                      onClick={() => handleOpenSession(sess.id)}
                      className="w-full flex items-center justify-between p-3.5 rounded-xl bg-white hover:bg-zinc-50 border border-zinc-200 hover:border-zinc-400 transition-all text-left group cursor-pointer"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-8 h-8 rounded-lg bg-zinc-100 group-hover:bg-zinc-200 text-zinc-700 flex items-center justify-center transition-colors shrink-0">
                          <MessageSquare size={15} />
                        </div>
                        <div className="min-w-0">
                          <div className="font-semibold text-sm text-zinc-900 group-hover:text-black transition-colors truncate">
                            {sess.title || 'Study Room'}
                          </div>
                          <div className="flex items-center gap-1.5 text-[11px] text-zinc-400 mt-0.5">
                            <Clock size={11} />
                            <span>{formatDate(sess.created_at)}</span>
                          </div>
                        </div>
                      </div>
                      <ArrowRight size={16} className="text-zinc-300 group-hover:text-zinc-900 group-hover:translate-x-0.5 transition-all shrink-0 ml-2" />
                    </button>
                  ))}
                </div>
              ) : (
                <div className="p-4 rounded-xl bg-zinc-50 border border-dashed border-zinc-200 text-center text-xs text-zinc-400">
                  No previous sessions linked yet. Click above to start your first study room!
                </div>
              )}
            </div>

            {/* Extracted Key Topics */}
            {document.key_topics && document.key_topics.length > 0 && (
              <div className="space-y-2 pt-1 border-t border-zinc-100">
                <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
                  <BookOpen size={13} className="text-zinc-700" />
                  <span>Key Concepts in Material</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {document.key_topics.slice(0, 6).map((topic) => (
                    <span
                      key={topic}
                      className="px-2.5 py-1 rounded-lg bg-zinc-100 border border-zinc-200 text-[11px] font-medium text-zinc-800"
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

