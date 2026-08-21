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

// SSLC (Class 10) Core Subjects Catalog
export const INITIAL_SUBJECTS: Subject[] = [
  {
    id: 'sslc-math',
    name: 'Class 10 Mathematics',
    description: 'Arithmetic sequences, circles, algebra of sequences, mathematics of chance, second degree equations, trigonometry & coordinates',
    illustration: '/assets/illustrations/math_fx.png',
    emoji: '📐',
    category: 'SSLC / 10th STEM',
    totalTopics: 7,
    isEnrolled: true,
    lastStudiedAt: new Date(Date.now() - 3600 * 1000 * 3).toISOString(),
  },
  {
    id: 'sslc-physics',
    name: 'Class 10 Physics',
    description: 'Wave motion & oscillations, refraction of light & lenses, dispersion of light & colours, magnetic effect of electric current',
    illustration: '/assets/illustrations/physics_atom.png',
    emoji: '⚛️',
    category: 'SSLC / 10th Science',
    totalTopics: 4,
    isEnrolled: true,
    lastStudiedAt: new Date(Date.now() - 3600 * 1000 * 12).toISOString(),
  },
  {
    id: 'sslc-chemistry',
    name: 'Class 10 Chemistry',
    description: 'Nomenclature of organic compounds & isomerism, reactions of organic compounds, periodic table & electron configuration, gas laws & mole concept',
    illustration: '/assets/illustrations/chemistry_flask.png',
    emoji: '🧪',
    category: 'SSLC / 10th Science',
    totalTopics: 4,
    isEnrolled: true,
    lastStudiedAt: null,
  },
]

// SSLC Class 10 Official Topics by Subject ID (Kerala SCERT English Medium)
export const INITIAL_TOPICS: Record<string, Topic[]> = {
  'sslc-math': [
    { id: 'math-10-1', subjectId: 'sslc-math', title: '1. Arithmetic Sequences', description: 'Number patterns, common difference, terms and positions, sequence calculations', order: 1, difficulty: 'easy', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '40 mins' },
    { id: 'math-10-2', subjectId: 'sslc-math', title: '2. Circles and Angles', description: 'Chord properties, central angles, angle subtended by arcs, cyclic quadrilaterals', order: 2, difficulty: 'medium', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '45 mins' },
    { id: 'math-10-3', subjectId: 'sslc-math', title: '3. Arithmetic Sequences & Algebra', description: 'Algebraic form of sequences, nth term formula xn = an + b, sum of first n terms', order: 3, difficulty: 'medium', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '50 mins' },
    { id: 'math-10-4', subjectId: 'sslc-math', title: '4. Mathematics of Chance', description: 'Probability as numbers, geometric probability, pairs and combinations', order: 4, difficulty: 'easy', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '35 mins' },
    { id: 'math-10-5', subjectId: 'sslc-math', title: '5. Second Degree Equations', description: 'Square completion method, quadratic equation solving, word problems', order: 5, difficulty: 'hard', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '55 mins' },
    { id: 'math-10-6', subjectId: 'sslc-math', title: '6. Trigonometry', description: 'Ratios of right triangles (sin, cos, tan), standard angle values, heights and distances', order: 6, difficulty: 'hard', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '60 mins' },
    { id: 'math-10-7', subjectId: 'sslc-math', title: '7. Coordinates', description: 'Coordinate axes, distance between points, rectangle/circle geometry on coordinate plane', order: 7, difficulty: 'medium', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '45 mins' },
  ],
  'sslc-physics': [
    { id: 'phys-10-1', subjectId: 'sslc-physics', title: '1. Wave Motion & Oscillations', description: 'Types of motion, oscillatory motion, transverse and longitudinal waves, wavelength and frequency', order: 1, difficulty: 'medium', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '45 mins' },
    { id: 'phys-10-2', subjectId: 'sslc-physics', title: '2. Refraction of Light & Lenses', description: 'Refraction laws, convex & concave lenses, ray diagrams, lens formula, power of lenses', order: 2, difficulty: 'hard', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '55 mins' },
    { id: 'phys-10-3', subjectId: 'sslc-physics', title: '3. Dispersion of Light & Colour', description: 'Refraction through prism, spectrum formation, recombination, rainbow formation, scattering of light', order: 3, difficulty: 'medium', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '50 mins' },
    { id: 'phys-10-4', subjectId: 'sslc-physics', title: '4. Magnetic Effect of Electric Current', description: 'Magnetic field around current-carrying conductors, solenoid, Right-Hand Thumb Rule, motor principle', order: 4, difficulty: 'hard', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '55 mins' },
  ],
  'sslc-chemistry': [
    { id: 'chem-10-1', subjectId: 'sslc-chemistry', title: '1. Nomenclature of Organic Compounds & Isomerism', description: 'Hydrocarbons (alkanes, alkenes, alkynes), IUPAC naming rules, chain/position/functional isomerism', order: 1, difficulty: 'hard', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '60 mins' },
    { id: 'chem-10-2', subjectId: 'sslc-chemistry', title: '2. Chemical Reactions of Organic Compounds', description: 'Substitution, addition, polymerization, combustion, and thermal cracking reactions', order: 2, difficulty: 'medium', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '50 mins' },
    { id: 'chem-10-3', subjectId: 'sslc-chemistry', title: '3. Periodic Table & Electron Configuration', description: 'Shells & subshells (s, p, d, f), Aufbau principle, block classification, periodic trends', order: 3, difficulty: 'hard', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '55 mins' },
    { id: 'chem-10-4', subjectId: 'sslc-chemistry', title: '4. Gas Laws and Mole Concept', description: 'Boyle’s law, Charles’s law, Avogadro’s law, mole calculations, molar volume (22.4 L at STP)', order: 4, difficulty: 'medium', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '50 mins' },
  ],
}

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
      topics: INITIAL_TOPICS,

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
    { name: 'indie-tutor-sslc-fresh-v3' }
  )
)
