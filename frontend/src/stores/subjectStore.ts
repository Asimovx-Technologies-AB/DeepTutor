import { create } from 'zustand'
import { persist } from 'zustand/middleware'

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
}

// Default Catalog of Subjects
export const INITIAL_SUBJECTS: Subject[] = [
  {
    id: '6',
    name: 'Machine Learning',
    description: 'Supervised learning, regression, classification, neural networks & AI algorithms',
    illustration: '/assets/illustrations/cs_code.png',
    category: 'Computer Science',
    totalTopics: 6,
    isEnrolled: true,
    lastStudiedAt: new Date(Date.now() - 3600 * 1000 * 2).toISOString(), // 2 hours ago
  },
  {
    id: '3',
    name: 'Mathematics',
    description: 'Algebra, calculus, linear algebra, statistics & discrete math',
    illustration: '/assets/illustrations/math_fx.png',
    category: 'STEM',
    totalTopics: 6,
    isEnrolled: true,
    lastStudiedAt: new Date(Date.now() - 3600 * 1000 * 24).toISOString(), // 1 day ago
  },
  {
    id: '1',
    name: 'Physics',
    description: 'Mechanics, thermodynamics, electromagnetism & quantum physics',
    illustration: '/assets/illustrations/physics_atom.png',
    category: 'STEM',
    totalTopics: 6,
    isEnrolled: true,
    lastStudiedAt: new Date(Date.now() - 3600 * 1000 * 48).toISOString(), // 2 days ago
  },
  {
    id: '2',
    name: 'Biology',
    description: 'Cell biology, genetics, ecology, physiology & evolutionary biology',
    illustration: '/assets/illustrations/biology_dna.png',
    category: 'Science',
    totalTopics: 5,
    isEnrolled: true,
    lastStudiedAt: null,
  },
  {
    id: '4',
    name: 'Geography',
    description: 'Physical geography, climate science, maps & world geopolitical regions',
    illustration: '/assets/illustrations/geography_globe.png',
    category: 'Social Studies',
    totalTopics: 5,
    isEnrolled: false,
    lastStudiedAt: null,
  },
  {
    id: '5',
    name: 'History',
    description: 'Ancient civilizations, world revolutions, modern conflicts & historiography',
    illustration: '/assets/illustrations/stack_of_books.png',
    category: 'Humanities',
    totalTopics: 5,
    isEnrolled: false,
    lastStudiedAt: null,
  },
  {
    id: '7',
    name: 'Chemistry',
    description: 'Organic chemistry, molecular structures, chemical reactions & lab safety',
    illustration: '/assets/illustrations/chemistry_flask.png',
    category: 'Science',
    totalTopics: 5,
    isEnrolled: false,
    lastStudiedAt: null,
  },
  {
    id: '8',
    name: 'Literature',
    description: 'Classic literature analysis, poetry, storytelling & critical reading',
    illustration: '/assets/illustrations/open_book.png',
    category: 'Humanities',
    totalTopics: 5,
    isEnrolled: false,
    lastStudiedAt: null,
  },
]

// Default Topics by Subject ID
export const INITIAL_TOPICS: Record<string, Topic[]> = {
  '6': [
    { id: 'ml-1', subjectId: '6', title: 'Introduction to Machine Learning', description: 'Core principles of ML, training sets, features, and model evaluation', order: 1, difficulty: 'easy', progress: 100, status: 'COMPLETED', lastStudiedAt: new Date(Date.now() - 86400000 * 3).toISOString(), estimatedDuration: '30 mins' },
    { id: 'ml-2', subjectId: '6', title: 'Linear Regression', description: 'Fitting lines to data, cost functions, and Mean Squared Error minimization', order: 2, difficulty: 'medium', progress: 100, status: 'COMPLETED', lastStudiedAt: new Date(Date.now() - 86400000 * 2).toISOString(), estimatedDuration: '45 mins' },
    { id: 'ml-3', subjectId: '6', title: 'Logistic Regression & Classification', description: 'Binary classification, sigmoid function, decision boundaries, and log loss', order: 3, difficulty: 'medium', progress: 80, status: 'IN_PROGRESS', lastStudiedAt: new Date(Date.now() - 3600000 * 2).toISOString(), estimatedDuration: '50 mins' },
    { id: 'ml-4', subjectId: '6', title: 'Decision Trees & Random Forests', description: 'Tree splitting metrics (Gini impurity, Entropy), pruning, and ensemble learning', order: 4, difficulty: 'medium', progress: 60, status: 'IN_PROGRESS', lastStudiedAt: new Date(Date.now() - 86400000 * 5).toISOString(), estimatedDuration: '60 mins' },
    { id: 'ml-5', subjectId: '6', title: 'Gradient Descent Optimization', description: 'Learning rates, momentum, stochastic gradient descent (SGD), and Adam optimizer', order: 5, difficulty: 'hard', progress: 40, status: 'REVIEW', lastStudiedAt: new Date(Date.now() - 86400000 * 1).toISOString(), estimatedDuration: '55 mins' },
    { id: 'ml-6', subjectId: '6', title: 'Neural Networks & Deep Learning', description: 'Perceptrons, activation functions, backpropagation, and multi-layer networks', order: 6, difficulty: 'hard', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '75 mins' },
  ],
  '3': [
    { id: 'math-1', subjectId: '3', title: 'Calculus: Derivatives & Rates of Change', description: 'Limits, derivative rules, velocity, and tangent line slopes', order: 1, difficulty: 'easy', progress: 100, status: 'COMPLETED', lastStudiedAt: new Date(Date.now() - 86400000 * 4).toISOString(), estimatedDuration: '40 mins' },
    { id: 'math-2', subjectId: '3', title: 'Integrals & Fundamental Theorem', description: 'Definite/indefinite integrals, area under curves, and substitution method', order: 2, difficulty: 'medium', progress: 100, status: 'COMPLETED', lastStudiedAt: new Date(Date.now() - 86400000 * 3).toISOString(), estimatedDuration: '50 mins' },
    { id: 'math-3', subjectId: '3', title: 'Linear Algebra: Matrices & Vectors', description: 'Vector spaces, matrix multiplication, determinants, and linear transformations', order: 3, difficulty: 'medium', progress: 75, status: 'IN_PROGRESS', lastStudiedAt: new Date(Date.now() - 86400000 * 1).toISOString(), estimatedDuration: '55 mins' },
    { id: 'math-4', subjectId: '3', title: 'Eigenvalues & Eigenvectors', description: 'Characteristic equations, diagonalization, and principal components concept', order: 4, difficulty: 'hard', progress: 40, status: 'IN_PROGRESS', lastStudiedAt: new Date(Date.now() - 86400000 * 6).toISOString(), estimatedDuration: '65 mins' },
    { id: 'math-5', subjectId: '3', title: 'Probability Distributions & Bayes Theorem', description: 'Random variables, Gaussian distribution, conditional probability, and prior/posterior', order: 5, difficulty: 'medium', progress: 30, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '45 mins' },
    { id: 'math-6', subjectId: '3', title: 'Differential Equations', description: 'First-order separable equations, linear DEs, and modeling real-world growth', order: 6, difficulty: 'hard', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '70 mins' },
  ],
  '1': [
    { id: 'phys-1', subjectId: '1', title: 'Newton\'s Laws of Motion', description: 'Forces, acceleration, momentum, and friction in classical mechanics', order: 1, difficulty: 'easy', progress: 100, status: 'COMPLETED', lastStudiedAt: new Date(Date.now() - 86400000 * 5).toISOString(), estimatedDuration: '35 mins' },
    { id: 'phys-2', subjectId: '1', title: 'Work, Energy & Power', description: 'Kinetic energy, potential energy fields, conservation of mechanical energy', order: 2, difficulty: 'medium', progress: 90, status: 'COMPLETED', lastStudiedAt: new Date(Date.now() - 86400000 * 2).toISOString(), estimatedDuration: '40 mins' },
    { id: 'phys-3', subjectId: '1', title: 'Thermodynamics & Heat Transfer', description: 'Laws of thermodynamics, entropy, heat engines, and thermal equilibrium', order: 3, difficulty: 'medium', progress: 60, status: 'IN_PROGRESS', lastStudiedAt: new Date(Date.now() - 3600000 * 6).toISOString(), estimatedDuration: '50 mins' },
    { id: 'phys-4', subjectId: '1', title: 'Electromagnetism & Maxwell\'s Equations', description: 'Electric fields, magnetic induction, Lorentz force, and electromagnetic waves', order: 4, difficulty: 'hard', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '65 mins' },
    { id: 'phys-5', subjectId: '1', title: 'Wave Optics & Interference', description: 'Superposition, diffraction patterns, Young\'s double-slit experiment, and Doppler effect', order: 5, difficulty: 'medium', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '45 mins' },
    { id: 'phys-6', subjectId: '1', title: 'Special Relativity & Quantum Physics', description: 'Time dilation, E=mc², wave-particle duality, and the Uncertainty Principle', order: 6, difficulty: 'hard', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '70 mins' },
  ],
  '2': [
    { id: 'bio-1', subjectId: '2', title: 'Cellular Structure & Organelles', description: 'Plasma membrane, mitochondria, nucleus, and cellular transport mechanisms', order: 1, difficulty: 'easy', progress: 20, status: 'IN_PROGRESS', lastStudiedAt: new Date(Date.now() - 86400000 * 7).toISOString(), estimatedDuration: '35 mins' },
    { id: 'bio-2', subjectId: '2', title: 'DNA Replication & Protein Synthesis', description: 'Double helix structure, transcription, translation, and codon decoding', order: 2, difficulty: 'medium', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '50 mins' },
    { id: 'bio-3', subjectId: '2', title: 'Genetics & Mendelian Inheritance', description: 'Alleles, Punnett squares, dominant/recessive traits, and genetic mutations', order: 3, difficulty: 'medium', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '45 mins' },
    { id: 'bio-4', subjectId: '2', title: 'Photosynthesis & Cellular Respiration', description: 'Calvin cycle, ATP generation, Krebs cycle, and electron transport chain', order: 4, difficulty: 'medium', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '55 mins' },
    { id: 'bio-5', subjectId: '2', title: 'Ecology & Ecosystem Dynamics', description: 'Trophic levels, energy pyramids, biodiversity, and biogeochemical cycles', order: 5, difficulty: 'easy', progress: 0, status: 'NOT_STARTED', lastStudiedAt: null, estimatedDuration: '40 mins' },
  ],
}

interface SubjectState {
  subjects: Subject[]
  topics: Record<string, Topic[]>
  
  // Actions
  enrollSubject: (subjectId: string) => void
  unenrollSubject: (subjectId: string) => void
  updateTopicProgress: (subjectId: string, topicId: string, progress: number) => void
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
    { name: 'deep-tutor-subjects' }
  )
)
