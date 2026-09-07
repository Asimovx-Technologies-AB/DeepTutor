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
        <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto text-slate-400">
          <BookOpen size={32} />
        </div>
        <h2 className="text-xl font-bold text-[#3C3C3C]">Subject Not Found</h2>
        <p className="text-sm text-[#777777]">The subject you are looking for does not exist or has been removed.</p>
        <button
          onClick={() => navigate('/subjects')}
          className="btn-primary py-2 px-5 text-xs font-bold rounded-[1.5rem] cursor-pointer"
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
    <div className="p-6 sm:p-8 max-w-6xl mx-auto space-y-8 bg-[#F7F7F7] text-[#3C3C3C] font-sans">
      {/* Back Button */}
      <motion.button
        initial={{ opacity: 0, x: -8 }}
        animate={{ opacity: 1, x: 0 }}
        onClick={() => navigate('/subjects')}
        className="flex items-center gap-2 text-[#777777] hover:text-[#4F46E5] transition-colors text-xs font-extrabold cursor-pointer"
      >
        <ArrowLeft size={16} /> Back to My Subjects
      </motion.button>

      {/* ─── 1. SUBJECT HEADER BANNER ─── */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-white border border-[#E2E8F0] rounded-[2rem] p-6 sm:p-8 elevation-1 space-y-6 relative overflow-hidden"
      >
        {/* Journey Anchor Illustration Background */}
        <div className="absolute right-0 top-0 bottom-0 w-1/3 opacity-80 pointer-events-none hidden md:block">
          <img src="/assets/illustrations/journey_anchor.jpg" alt="Journey Path" className="w-full h-full object-cover mix-blend-multiply opacity-50" />
          {/* Fade out mask to blend with white */}
          <div className="absolute inset-0 bg-gradient-to-r from-white to-transparent" />
        </div>

        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6 relative z-10">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-[1.5rem] bg-info-soft border border-info/30 flex items-center justify-center p-2.5 elevation-1 flex-shrink-0 text-3xl">
              {subject.emoji || subject.illustration}
            </div>

            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[11px] font-black uppercase tracking-wider bg-[#EEF2FF] text-[#4F46E5] px-2.5 py-0.5 rounded-full border border-[#4F46E5]/20">
                  {subject.category}
                </span>

                {subjectStatus === 'COMPLETED' && (
                  <span className="text-[11px] font-bold bg-[#D7FFB8] text-[#46A302] px-2.5 py-0.5 rounded-full border border-[#58CC02]/30">
                    Completed
                  </span>
                )}
                {subjectStatus === 'IN_PROGRESS' && (
                  <span className="text-[11px] font-bold bg-[#FFF0B3] text-[#FFC800] px-2.5 py-0.5 rounded-full border border-[#FFC800]/30">
                    In Progress
                  </span>
                )}
                {subjectStatus === 'INACTIVE' && (
                  <span className="text-[11px] font-bold bg-[#FFD1D1] text-[#FF4B4B] px-2.5 py-0.5 rounded-full border border-[#FF4B4B]/30">
                    Inactive
                  </span>
                )}
              </div>

              <h1 className="text-2xl sm:text-3xl font-black text-[#3C3C3C] tracking-tight">{subject.name}</h1>
              <p className="text-[#777777] text-xs font-medium leading-relaxed mt-1 max-w-xl">
                {subject.description}
              </p>
            </div>
          </div>

          {/* Enrollment Button */}
          {!subject.isEnrolled ? (
            <button
              onClick={() => enrollSubject(subject.id)}
              className="btn-primary text-xs font-bold py-2.5 px-5 rounded-[1.5rem] flex items-center gap-2 elevation-1 cursor-pointer whitespace-nowrap"
            >
              <Plus size={15} /> Add to My Subjects
            </button>
          ) : (
            <div className="flex items-center gap-2 bg-[#D7FFB8] text-[#46A302] border border-[#58CC02]/30 px-3.5 py-2 rounded-[1.5rem] text-xs font-bold">
              <Check size={15} /> Enrolled
            </div>
          )}
        </div>

        {/* Overall Progress Bar */}
        <div className="space-y-2 pt-2 border-t border-[#E2E8F0]/60">
          <div className="flex items-center justify-between text-xs font-bold">
            <span className="text-[#777777]">
              Overall Progress ({completedTopicsCount} of {topics.length} topics completed)
            </span>
            <span className="text-[#3C3C3C] font-black">{overallProgress}%</span>
          </div>
          <div className="w-full bg-[#E5E5E5] rounded-full h-2.5 overflow-hidden">
            <motion.div
              className="bg-[#4F46E5] h-full rounded-full"
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
          className="bg-gradient-to-r from-[#EEF2FF] via-[#FFFFFF] to-[#EEF2FF] border border-[#4F46E5]/40 rounded-[2rem] p-6 elevation-1 space-y-4 relative overflow-hidden"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles size={16} className="text-[#4F46E5]" />
              <h3 className="text-xs font-black text-[#3C3C3C] uppercase tracking-wider">Currently Learning</h3>
            </div>
            <span className="text-xs font-bold text-[#4F46E5]">{currentTopic.progress}% complete</span>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <h4 className="text-lg font-black text-[#3C3C3C]">{currentTopic.title}</h4>
              <p className="text-xs text-[#777777] font-medium leading-relaxed">{currentTopic.description}</p>
            </div>

            <button
              onClick={() => handleStartTopicChat(currentTopic)}
              className="btn-primary text-xs font-black py-3 px-6 rounded-[1.5rem] flex items-center justify-center gap-2 elevation-4 cursor-pointer whitespace-nowrap self-start sm:self-auto"
            >
              <span>Continue learning</span>
              <ChevronRight size={16} />
            </button>
          </div>
        </motion.div>
      )}

      {/* ─── 3. LEARNING JOURNEY MAP ─── */}
      <div className="space-y-4">
        <div className="flex items-center justify-between px-2">
          <h2 className="text-xl tracking-tight font-bold text-[#3C3C3C]">Learning Journey Map</h2>
          <span className="text-xs font-medium text-[#777777]">{completedTopicsCount} of {topics.length} modules completed</span>
        </div>

        <div className="relative pl-6">
          {/* Vertical Timeline Line */}
          <div className="absolute left-10 top-6 bottom-6 w-0.5 bg-[#E2E8F0] z-0" />

          <div className="space-y-6">
            {topics.map((topic, index) => {
              const isCompleted = topic.status === 'COMPLETED'
              const isInProgress = topic.status === 'IN_PROGRESS' || topic.status === 'REVIEW'

              return (
                <motion.div
                  key={topic.id}
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.05 }}
                  className="relative flex items-start gap-6 z-10"
                >
                  {/* Timeline Node */}
                  <div
                    className={`w-8 h-8 rounded-full border-2 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-1 elevation-3 transition-colors ${isCompleted
                        ? 'bg-[#58CC02] border-[#58CC02] text-white'
                        : isInProgress
                          ? 'bg-[#4F46E5] border-[#4F46E5] text-white'
                          : 'bg-white border-[#E2E8F0] text-[#AFAFAF]'
                      }`}
                  >
                    {isCompleted ? <Check size={14} /> : topic.order}
                  </div>

                  <div className={`flex-1 bg-white border rounded-[1.5rem] p-5 elevation-3 transition-all hover:elevation-4 ${isInProgress ? 'border-[#4F46E5]/40 ring-1 ring-[#4F46E5]/10' : 'border-[#E2E8F0] hover:border-[#CBD5E1]'
                    }`}>
                    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                      <div className="space-y-1.5 min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h4 className="font-extrabold text-[#3C3C3C] text-sm">{topic.title}</h4>
                          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${topic.difficulty === 'easy' ? 'bg-[#D7FFB8] border-[#58CC02]/30 text-[#46A302]' :
                              topic.difficulty === 'medium' ? 'bg-[#FFF0B3] border-[#FFC800]/30 text-[#FFC800]' :
                                'bg-[#FFD1D1] border-[#FF4B4B]/30 text-[#FF4B4B]'
                            }`}>
                            {DIFF_LABELS[topic.difficulty] ?? topic.difficulty}
                          </span>

                          {/* Status Tag */}
                          {isCompleted && (
                            <span className="text-[10px] font-black bg-[#D7FFB8] text-[#46A302] px-2 py-0.5 rounded-full">
                              Completed
                            </span>
                          )}
                          {isInProgress && (
                            <span className="text-[10px] font-black bg-[#EEF2FF] text-[#4F46E5] px-2 py-0.5 rounded-full">
                              {topic.status === 'REVIEW' ? 'Review Needed' : 'In Progress'}
                            </span>
                          )}

                          {/* Last Quiz Score Badge */}
                          {topic.lastQuizPct !== undefined && (
                            <span className={`text-[10px] font-black px-2.5 py-0.5 rounded-full border flex items-center gap-1 ${topic.lastQuizPct >= 70
                              ? 'bg-success-soft border-success/30 text-[#35654B]'
                              : 'bg-[#FFF3D8] border-[#D99A32]/30 text-[#B45309]'
                              }`}>
                              <Trophy size={11} className={topic.lastQuizPct >= 70 ? 'text-success' : 'text-[#D99A32]'} />
                              <span>Quiz: {topic.lastQuizPct}% ({topic.lastQuizScore}/{topic.lastQuizTotal})</span>
                            </span>
                          )}
                        </div>

                        <p className="text-[#777777] text-xs leading-relaxed line-clamp-1 font-medium">{topic.description}</p>

                        {/* Topic Progress Bar */}
                        <div className="flex items-center gap-3 pt-1 max-w-md">
                          <div className="flex-1 bg-[#E5E5E5] rounded-full h-1.5 overflow-hidden">
                            <div
                              className={`h-full rounded-full ${isCompleted ? 'bg-[#58CC02]' : 'bg-[#4F46E5]'
                                }`}
                              style={{ width: `${topic.progress}%` }}
                            />
                          </div>
                          <span className="text-[11px] font-black text-[#3C3C3C]">{topic.progress}%</span>
                        </div>
                      </div>
                    </div>

                    {/* Actions Row */}
                    <div className="flex items-center gap-2 mt-4 pt-4 border-t border-[#E2E8F0]/60">
                      <button
                        onClick={() => {
                          recordActivity(subject.id, topic.id)
                          navigate(`/flashcards/${topic.id}`)
                        }}
                        className="btn-ghost text-xs py-1.5 px-3 rounded-lg flex items-center gap-1.5 cursor-pointer"
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
                        className="btn-ghost text-xs py-1.5 px-3 rounded-lg flex items-center gap-1.5 cursor-pointer"
                        title="Take Topic Quiz"
                      >
                        <Trophy size={13} />
                        <span>Quiz</span>
                      </button>

                      <div className="flex-1" />

                      <button
                        onClick={() => handleStartTopicChat(topic)}
                        className="btn-primary text-xs font-medium py-2 px-4 rounded-lg flex items-center gap-1.5 cursor-pointer"
                      >
                        <MessageSquare size={13} />
                        <span>Chat</span>
                      </button>
                    </div>
                  </div>
                </motion.div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
