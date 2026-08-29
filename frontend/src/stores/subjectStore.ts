import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { dashboardApi } from '../services/api'

export type SubjectStatus = 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED' | 'INACTIVE'
export type TopicStatus = 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED' | 'REVIEW'

export interface Topic {
  id: string
  subjectId: string
  title: string
  description: string
  order: number
  difficulty: 'easy' | 'medium' | 'hard'
  progress: number // 0 to 100
  status: TopicStatus
  lastStudiedAt: string | null
  estimatedDuration: string
  lastQuizScore?: number
  lastQuizTotal?: number
  lastQuizPct?: number
  lastQuizDate?: string
}

export interface Subject {
  id: string
  name: string
  description: string
  illustration: string
  category: string
  totalTopics: number
  isEnrolled: boolean
  lastStudiedAt: string | null
  emoji: string
}

// Subjects and topics are created from the authenticated user's uploaded
// documents. Never seed a browser with content that the user does not own.
export const INITIAL_SUBJECTS: Subject[] = []


interface SubjectState {
  subjects: Subject[]
  topics: Record<string, Topic[]>
  
  // Actions
  enrollSubject: (subjectId: string) => void
  unenrollSubject: (subjectId: string) => void
  updateTopicProgress: (subjectId: string, topicId: string, progress: number) => void
  recordQuizResult: (subjectId: string, topicId: string, score: number, total: number, pct: number) => void
  recordActivity: (subjectId: string, topicId: string) => void
  
  // Getters & Calculations
  getSubject: (subjectId: string) => Subject | undefined
  getTopics: (subjectId: string) => Topic[]
  getSubjectProgress: (subjectId: string) => number
  getSubjectStatus: (subjectId: string) => SubjectStatus
  getCurrentTopic: (subjectId: string) => Topic | undefined
  getRecommendation: () => { subjectId: string; topicId: string; topicName: string; reason: string } | null
}

export const useSubjectStore = create<SubjectState>()(
  persist(
    (set, get) => ({
      subjects: INITIAL_SUBJECTS,
      topics: {},

      enrollSubject: (subjectId) => {
        set((state) => ({
          subjects: state.subjects.map((s) =>
            s.id === subjectId ? { ...s, isEnrolled: true, lastStudiedAt: new Date().toISOString() } : s
          ),
        }))
      },

      unenrollSubject: (subjectId) => {
        set((state) => ({
          subjects: state.subjects.map((s) => (s.id === subjectId ? { ...s, isEnrolled: false } : s)),
        }))
      },

      recordQuizResult: (subjectId, topicId, score, total, pct) => {
        const now = new Date().toISOString()
        set((state) => {
          const subjectTopics = state.topics[subjectId] || []
          const updatedTopics = subjectTopics.map((t) => {
            if (t.id === topicId) {
              const newProgress = Math.max(t.progress, pct)
              const newStatus: TopicStatus =
                newProgress >= 70 ? 'COMPLETED' : newProgress > 0 ? 'IN_PROGRESS' : 'NOT_STARTED'
              return {
                ...t,
                progress: newProgress,
                status: newStatus,
                lastQuizScore: score,
                lastQuizTotal: total,
                lastQuizPct: pct,
                lastQuizDate: now,
                lastStudiedAt: now,
              }
            }
            return t
          })

          const updatedSubjects = state.subjects.map((s) =>
            s.id === subjectId ? { ...s, lastStudiedAt: now } : s
          )

          return {
            topics: { ...state.topics, [subjectId]: updatedTopics },
            subjects: updatedSubjects,
          }
        })
      },

      updateTopicProgress: (subjectId, topicId, progressVal) => {
        set((state) => {
          const subjectTopics = state.topics[subjectId] || []
          const updatedTopics = subjectTopics.map((t) => {
            if (t.id === topicId) {
              const newProgress = Math.min(100, Math.max(0, progressVal))
              const newStatus: TopicStatus =
                newProgress >= 100 ? 'COMPLETED' : newProgress > 0 ? 'IN_PROGRESS' : 'NOT_STARTED'
              return {
                ...t,
                progress: newProgress,
                status: newStatus,
                lastStudiedAt: new Date().toISOString(),
              }
            }
            return t
          })

          const updatedSubjects = state.subjects.map((s) =>
            s.id === subjectId ? { ...s, lastStudiedAt: new Date().toISOString() } : s
          )
          
          // Fire-and-forget sync to backend
          dashboardApi.updateProgress({
            subject_id: subjectId,
            topic_id: topicId,
            progress_percentage: progressVal
          }).catch(console.error)

          return {
            topics: { ...state.topics, [subjectId]: updatedTopics },
            subjects: updatedSubjects,
          }
        })
      },

      recordActivity: (subjectId, topicId) => {
        const now = new Date().toISOString()
        set((state) => {
          const subjectTopics = state.topics[subjectId] || []
          const updatedTopics = subjectTopics.map((t) => {
            if (t.id === topicId) {
              const newProgress = t.progress === 0 ? 25 : t.progress
              const newStatus: TopicStatus =
                t.status === 'NOT_STARTED' ? 'IN_PROGRESS' : t.status
              return { ...t, progress: newProgress, status: newStatus, lastStudiedAt: now }
            }
            return t
          })

          const updatedSubjects = state.subjects.map((s) =>
            s.id === subjectId ? { ...s, isEnrolled: true, lastStudiedAt: now } : s
          )
          
          // Fire-and-forget record activity to backend
          dashboardApi.recordActivity({
            activity_type: 'topic_started',
            title: `Started studying topic`,
            subject_id: subjectId,
            topic_id: topicId
          }).catch(console.error)

          return {
            topics: { ...state.topics, [subjectId]: updatedTopics },
            subjects: updatedSubjects,
          }
        })
      },

      getSubject: (subjectId) => {
        return get().subjects.find((s) => s.id === subjectId)
      },

      getTopics: (subjectId) => {
        return get().topics[subjectId] || []
      },

      getSubjectProgress: (subjectId) => {
        const subjectTopics = get().topics[subjectId] || []
        if (!subjectTopics.length) return 0
        const sum = subjectTopics.reduce((acc, t) => acc + t.progress, 0)
        return Math.round(sum / subjectTopics.length)
      },

      getSubjectStatus: (subjectId) => {
        const subject = get().subjects.find((s) => s.id === subjectId)
        const progressVal = get().getSubjectProgress(subjectId)
        if (!subject) return 'NOT_STARTED'

        if (progressVal >= 100) return 'COMPLETED'
        if (progressVal > 0) {
          if (subject.lastStudiedAt) {
            const daysDiff = (Date.now() - new Date(subject.lastStudiedAt).getTime()) / (1000 * 3600 * 24)
            if (daysDiff > 21) return 'INACTIVE'
          }
          return 'IN_PROGRESS'
        }
        return 'NOT_STARTED'
      },

      getCurrentTopic: (subjectId) => {
        const subjectTopics = get().topics[subjectId] || []
        if (!subjectTopics.length) return undefined

        // 1. Topic currently in progress with highest recent activity
        const inProgress = subjectTopics
          .filter((t) => t.status === 'IN_PROGRESS' || t.status === 'REVIEW')
          .sort((a, b) => {
            const timeA = a.lastStudiedAt ? new Date(a.lastStudiedAt).getTime() : 0
            const timeB = b.lastStudiedAt ? new Date(b.lastStudiedAt).getTime() : 0
            return timeB - timeA
          })
        if (inProgress.length > 0) return inProgress[0]

        // 2. First incomplete topic
        const firstNotStarted = subjectTopics.find((t) => t.status === 'NOT_STARTED')
        if (firstNotStarted) return firstNotStarted

        // 3. Fallback to first topic
        return subjectTopics[0]
      },

      getRecommendation: () => {
        const enrolled = get().subjects.filter((s) => s.isEnrolled)
        for (const subj of enrolled) {
          const current = get().getCurrentTopic(subj.id)
          if (current && current.progress < 100) {
            return {
              subjectId: subj.id,
              topicId: current.id,
              topicName: current.title,
              reason: `Review ${current.title} to strengthen your foundation in ${subj.name}.`,
            }
          }
        }
        return null
      },
    }),
    {
      name: 'indie-tutor-document-library',
      version: 1,
      migrate: () => ({ subjects: [], topics: {} }),
    }
  )
)
