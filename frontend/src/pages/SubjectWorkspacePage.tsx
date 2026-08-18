import { useParams, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ArrowLeft, BookOpen, ChevronRight, Trophy, MessageSquare,
  Sparkles, CheckCircle2, Play, RotateCcw, Clock, Award, Plus, Check
} from 'lucide-react'
import { useSubjectStore, type TopicStatus, type SubjectStatus } from '../stores/subjectStore'
import { chatApi } from '../services/api'

const DIFF_LABELS: Record<string, string> = {
  easy: 'Beginner',
  medium: 'Intermediate',
  hard: 'Advanced',
}

export default function SubjectWorkspacePage() {
  const { subjectId } = useParams<{ subjectId: string }>()
  const navigate = useNavigate()

  const {
    getSubject,
    getTopics,
    getSubjectProgress,
    getSubjectStatus,
    getCurrentTopic,
    enrollSubject,
    recordActivity,
  } = useSubjectStore()

  const subject = getSubject(subjectId || '')
  const topics = getTopics(subjectId || '')
  const overallProgress = getSubjectProgress(subjectId || '')
  const subjectStatus = getSubjectStatus(subjectId || '')
  const currentTopic = getCurrentTopic(subjectId || '')

  if (!subject) {
    return (
      <div className="p-8 max-w-4xl mx-auto text-center space-y-4">
        <div className="text-4xl">📚</div>
        <h2 className="text-xl font-bold text-[#20201D]">Subject Not Found</h2>
        <p className="text-sm text-[#6F6B63]">The subject you are looking for does not exist or has been removed.</p>
        <button
          onClick={() => navigate('/subjects')}
          className="btn-primary py-2 px-5 text-xs font-bold rounded-2xl cursor-pointer"
        >
          Back to Subjects
        </button>
      </div>
    )
  }

  const completedTopicsCount = topics.filter((t) => t.status === 'COMPLETED').length

  const handleStartTopicChat = (topic: any) => {
    recordActivity(subject.id, topic.id)
    navigate(`/subjects/${subject.id}/chat/${topic.id}`, {
      state: {
        initialPrompt: `Hi Deepy! I'd like to study ${topic.title} in ${subject.name}. Can you give me an overview and key concepts?`,
        subjectId: subject.id,
        subjectName: subject.name,
        topicId: topic.id,
        topicName: topic.title,
      },
    })
  }

  return (
    <div className="p-6 sm:p-8 max-w-6xl mx-auto space-y-8 bg-[#FAF8F3] text-[#20201D] font-sans">
      {/* Back Button */}
      <motion.button
        initial={{ opacity: 0, x: -8 }}
        animate={{ opacity: 1, x: 0 }}
        onClick={() => navigate('/subjects')}
        className="flex items-center gap-2 text-[#6F6B63] hover:text-[#F28A45] transition-colors text-xs font-extrabold cursor-pointer"
      >
        <ArrowLeft size={16} /> Back to My Subjects
      </motion.button>

      {/* ─── 1. SUBJECT HEADER BANNER ─── */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-white border border-[#E7E1D8] rounded-3xl p-6 sm:p-8 shadow-2xs space-y-6 relative overflow-hidden"
      >
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-2xl bg-[#FFF0E4] border border-[#F28A45]/30 flex items-center justify-center p-2.5 shadow-2xs flex-shrink-0">
              <img src={subject.illustration} alt={subject.name} className="w-full h-full object-contain" />
            </div>

            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[11px] font-black uppercase tracking-wider bg-[#FFF0E4] text-[#F28A45] px-2.5 py-0.5 rounded-full border border-[#F28A45]/20">
                  {subject.category}
                </span>

                {subjectStatus === 'COMPLETED' && (
                  <span className="text-[11px] font-bold bg-[#E3F0E5] text-[#35654B] px-2.5 py-0.5 rounded-full border border-[#4F8A68]/30">
                    Completed 🎉
                  </span>
                )}
                {subjectStatus === 'IN_PROGRESS' && (
                  <span className="text-[11px] font-bold bg-[#FFF3D8] text-[#D99A32] px-2.5 py-0.5 rounded-full border border-[#D99A32]/30">
                    In Progress
                  </span>
                )}
                {subjectStatus === 'INACTIVE' && (
                  <span className="text-[11px] font-bold bg-[#FBE7E4] text-[#C85C52] px-2.5 py-0.5 rounded-full border border-[#C85C52]/30">
                    Inactive
                  </span>
                )}
              </div>

              <h1 className="text-2xl sm:text-3xl font-black text-[#20201D] tracking-tight">{subject.name}</h1>
              <p className="text-[#6F6B63] text-xs font-medium leading-relaxed mt-1 max-w-xl">
                {subject.description}
              </p>
            </div>
          </div>

          {/* Enrollment Button */}
          {!subject.isEnrolled ? (
            <button
              onClick={() => enrollSubject(subject.id)}
              className="btn-primary text-xs font-bold py-2.5 px-5 rounded-2xl flex items-center gap-2 shadow-2xs cursor-pointer whitespace-nowrap"
            >
              <Plus size={15} /> Add to My Subjects
            </button>
          ) : (
            <div className="flex items-center gap-2 bg-[#E3F0E5] text-[#35654B] border border-[#4F8A68]/30 px-3.5 py-2 rounded-2xl text-xs font-bold">
              <Check size={15} /> Enrolled
            </div>
          )}
        </div>

        {/* Overall Progress Bar */}
        <div className="space-y-2 pt-2 border-t border-[#E7E1D8]/60">
          <div className="flex items-center justify-between text-xs font-bold">
            <span className="text-[#6F6B63]">
              Overall Progress ({completedTopicsCount} of {topics.length} topics completed)
            </span>
            <span className="text-[#20201D] font-black">{overallProgress}%</span>
          </div>
          <div className="w-full bg-[#F4EFE7] rounded-full h-2.5 overflow-hidden">
            <motion.div
              className="bg-[#F28A45] h-full rounded-full"
              animate={{ width: `${overallProgress}%` }}
              transition={{ duration: 0.5 }}
            />
          </div>
        </div>
      </motion.div>

      {/* ─── 2. CURRENTLY LEARNING HIGHLIGHT CARD ─── */}
      {currentTopic && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-gradient-to-r from-[#FFF5EB] via-[#FFF9F2] to-[#FFF5EB] border border-[#F28A45]/40 rounded-3xl p-6 shadow-2xs space-y-4 relative overflow-hidden"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles size={16} className="text-[#F28A45]" />
              <h3 className="text-xs font-black text-[#20201D] uppercase tracking-wider">Currently Learning</h3>
            </div>
            <span className="text-xs font-bold text-[#F28A45]">{currentTopic.progress}% complete</span>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <h4 className="text-lg font-black text-[#20201D]">{currentTopic.title}</h4>
              <p className="text-xs text-[#6F6B63] font-medium leading-relaxed">{currentTopic.description}</p>
            </div>

            <button
              onClick={() => handleStartTopicChat(currentTopic)}
              className="btn-primary text-xs font-black py-3 px-6 rounded-2xl flex items-center justify-center gap-2 shadow-md cursor-pointer whitespace-nowrap self-start sm:self-auto"
            >
              <span>Continue learning</span>
              <ChevronRight size={16} />
            </button>
          </div>
        </motion.div>
      )}

      {/* ─── 3. ORDERED TOPICS LIST ─── */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-black text-[#20201D]">All Topics ({topics.length})</h2>
          <span className="text-xs font-bold text-[#6F6B63]">Ordered by curriculum sequence</span>
        </div>

        <div className="space-y-3">
          {topics.map((topic, index) => {
            const isCompleted = topic.status === 'COMPLETED'
            const isInProgress = topic.status === 'IN_PROGRESS' || topic.status === 'REVIEW'

            return (
              <motion.div
                key={topic.id}
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.05 }}
                className={`bg-white border rounded-3xl p-5 shadow-2xs transition-all flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 ${
                  isInProgress ? 'border-[#F28A45]/40 shadow-xs' : 'border-[#E7E1D8] hover:border-[#F28A45]/30'
                }`}
              >
                <div className="flex items-start gap-4 min-w-0 flex-1">
                  {/* Topic Order Index Badge */}
                  <div
                    className={`w-10 h-10 rounded-2xl border flex items-center justify-center text-xs font-black flex-shrink-0 shadow-2xs ${
                      isCompleted
                        ? 'bg-[#E3F0E5] border-[#4F8A68]/40 text-[#35654B]'
                        : isInProgress
                        ? 'bg-[#FFF0E4] border-[#F28A45]/40 text-[#F28A45]'
                        : 'bg-[#FAF8F3] border-[#E7E1D8] text-[#969188]'
                    }`}
                  >
                    {isCompleted ? '✓' : topic.order}
                  </div>

                  <div className="space-y-1.5 min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h4 className="font-extrabold text-[#20201D] text-sm">{topic.title}</h4>
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                        topic.difficulty === 'easy' ? 'bg-[#E3F0E5] border-[#4F8A68]/30 text-[#35654B]' :
                        topic.difficulty === 'medium' ? 'bg-[#FFF3D8] border-[#D99A32]/30 text-[#D99A32]' :
                        'bg-[#FBE7E4] border-[#C85C52]/30 text-[#C85C52]'
                      }`}>
                        {DIFF_LABELS[topic.difficulty] ?? topic.difficulty}
                      </span>

                      {/* Status Tag */}
                      {isCompleted && (
                        <span className="text-[10px] font-black bg-[#E3F0E5] text-[#35654B] px-2 py-0.5 rounded-full">
                          Completed
                        </span>
                      )}
                      {isInProgress && (
                        <span className="text-[10px] font-black bg-[#FFF0E4] text-[#F28A45] px-2 py-0.5 rounded-full">
                          {topic.status === 'REVIEW' ? 'Review Needed' : 'In Progress'}
                        </span>
                      )}
                    </div>

                    <p className="text-[#6F6B63] text-xs leading-relaxed line-clamp-1 font-medium">{topic.description}</p>

                    {/* Topic Progress Bar */}
                    <div className="flex items-center gap-3 pt-1 max-w-md">
                      <div className="flex-1 bg-[#F4EFE7] rounded-full h-1.5 overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            isCompleted ? 'bg-[#4F8A68]' : 'bg-[#F28A45]'
                          }`}
                          style={{ width: `${topic.progress}%` }}
                        />
                      </div>
                      <span className="text-[11px] font-black text-[#20201D]">{topic.progress}%</span>
                    </div>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 flex-shrink-0 self-end sm:self-center">
                  <button
                    onClick={() => {
                      recordActivity(subject.id, topic.id)
                      navigate(`/flashcards/${topic.id}`)
                    }}
                    className="btn-orange-outline text-xs py-2 px-3 rounded-xl flex items-center gap-1.5 cursor-pointer"
                    title="Study Flashcards"
                  >
                    <BookOpen size={13} />
                    <span>Flashcards</span>
                  </button>

                  <button
                    onClick={() => {
                      recordActivity(subject.id, topic.id)
                      navigate(`/quiz/${topic.id}`)
                    }}
                    className="btn-orange-outline text-xs py-2 px-3 rounded-xl flex items-center gap-1.5 cursor-pointer text-[#D99A32] border-[#D99A32]/40 hover:bg-[#FFF8EB]"
                    title="Take Topic Quiz"
                  >
                    <Trophy size={13} />
                    <span>Quiz</span>
                  </button>

                  <button
                    onClick={() => handleStartTopicChat(topic)}
                    className="btn-primary text-xs font-bold py-2 px-3.5 rounded-xl flex items-center gap-1.5 shadow-2xs cursor-pointer"
                  >
                    <MessageSquare size={13} />
                    <span>Chat</span>
                  </button>
                </div>
              </motion.div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
