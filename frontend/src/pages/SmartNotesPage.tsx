import { useState, useRef, useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import {
  FileText, Upload, Sparkles, Brain, CheckCircle2,
  Trash2, Download, Copy, Check, AlertTriangle, BookOpen,
  Search, RefreshCw, X, ArrowRight, Zap, Target,
  Hash, ChevronDown, ChevronUp, Layers, HelpCircle,
  FileCheck2, ShieldAlert, ArrowUpRight
} from 'lucide-react'
import { notesApi } from '../services/api'
import MermaidDiagram from '../components/MermaidDiagram'
import ConfirmModal from '../components/ConfirmModal'

const PRESET_SUBJECTS = [
  { id: 'math-10-1', subject: 'Mathematics', title: '1. Arithmetic Sequences', category: 'Math', icon: '🔢', color: '#F28A45' },
  { id: 'math-10-2', subject: 'Mathematics', title: '2. Circles and Angles', category: 'Math', icon: '⭕', color: '#F28A45' },
  { id: 'math-10-3', subject: 'Mathematics', title: '3. Mathematics of Chance', category: 'Math', icon: '🎲', color: '#F28A45' },
  { id: 'math-10-5', subject: 'Mathematics', title: '5. Second Degree Equations', category: 'Math', icon: '📐', color: '#F28A45' },
  { id: 'math-10-6', subject: 'Mathematics', title: '6. Trigonometry', category: 'Math', icon: '🔺', color: '#F28A45' },
  { id: 'phys-10-1', subject: 'Physics', title: '1. Current Electricity & Waves', category: 'Physics', icon: '⚡', color: '#3B82F6' },
  { id: 'phys-10-2', subject: 'Physics', title: '2. Refraction of Light & Lenses', category: 'Physics', icon: '🔍', color: '#3B82F6' },
  { id: 'phys-10-4', subject: 'Physics', title: '4. Magnetic Effect of Current', category: 'Physics', icon: '🧲', color: '#3B82F6' },
  { id: 'chem-10-1', subject: 'Chemistry', title: '1. Organic Chemistry Nomenclature', category: 'Chemistry', icon: '🧪', color: '#10B981' },
  { id: 'chem-10-3', subject: 'Chemistry', title: '3. Periodic Table & Config', category: 'Chemistry', icon: '⚛️', color: '#10B981' },
  { id: 'chem-10-4', subject: 'Chemistry', title: '4. Gas Laws & Mole Concept', category: 'Chemistry', icon: '🌡️', color: '#10B981' },
]

type OutputTab = 'cheat' | 'formulas' | 'questions'

export default function SmartNotesPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // ── Step 1 State: Chapter Selection ──
  const [selectedPreset, setSelectedPreset] = useState<string>('math-10-1')
  const [subjectFilter, setSubjectFilter] = useState<string>('All')

  // ── Step 2 State: Optional Uploads ──
  const [materialFile, setMaterialFile] = useState<File | null>(null)
  const [pyqFiles, setPyqFiles] = useState<File[]>([])

  // ── Step 3 State: Generation & Status ──
  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeNoteId, setActiveNoteId] = useState<string | null>(null)

  // ── Output Canvas State ──
  const [activeTab, setActiveTab] = useState<OutputTab>('cheat')
  const [expandedQuestions, setExpandedQuestions] = useState<Record<number, boolean>>({ 0: true, 1: true })
  const [copied, setCopied] = useState(false)
  const [copiedFormulaIdx, setCopiedFormulaIdx] = useState<number | null>(null)

  // ── Bottom History & Modal State ──
  const [isHistoryOpen, setIsHistoryOpen] = useState(false)
  const [searchHistory, setSearchHistory] = useState('')
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)

  const materialInputRef = useRef<HTMLInputElement>(null)
  const pyqInputRef = useRef<HTMLInputElement>(null)
  const resultsRef = useRef<HTMLDivElement>(null)

  // Fetch saved notes
  const { data: savedNotes = [] } = useQuery({
    queryKey: ['saved-study-notes'],
    queryFn: () => notesApi.list().then((r) => r.data),
    staleTime: 30_000,
  })

  // Selected or most recent note
  const activeNote = savedNotes.find((n: any) => n.id === activeNoteId) || savedNotes[0] || null

  const selectedPresetObj = PRESET_SUBJECTS.find((p) => p.id === selectedPreset)

  const filteredPresets = useMemo(() => {
    if (subjectFilter === 'All') return PRESET_SUBJECTS
    return PRESET_SUBJECTS.filter((p) => p.category === subjectFilter)
  }, [subjectFilter])

  const filteredSavedNotes = savedNotes.filter((n: any) =>
    n.title.toLowerCase().includes(searchHistory.toLowerCase()) ||
    n.subject.toLowerCase().includes(searchHistory.toLowerCase())
  )

  const handleMaterialChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setMaterialFile(e.target.files[0])
    }
  }

  const handlePyqChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const newFiles = Array.from(e.target.files)
      setPyqFiles((prev) => [...prev, ...newFiles])
    }
  }

  const removePyqFile = (index: number) => {
    setPyqFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const toggleQuestionExpand = (index: number) => {
    setExpandedQuestions((prev) => ({ ...prev, [index]: !prev[index] }))
  }

  const handleGenerate = async () => {
    setIsGenerating(true)
    setError(null)
    try {
      const matchPreset = PRESET_SUBJECTS.find((p) => p.id === selectedPreset)
      const res = await notesApi.generate({
        materialFile,
        pyqFiles,
        topicId: materialFile ? 'custom-upload' : (selectedPreset || 'math-10-1'),
        subject: materialFile ? 'Uploaded Material' : (matchPreset?.subject || 'Mathematics'),
        noteType: pyqFiles.length > 0 ? 'pyq_analysis' : 'high_yield_master',
      })

      await queryClient.invalidateQueries({ queryKey: ['saved-study-notes'] })
      await queryClient.invalidateQueries({ queryKey: ['student-record'] })
      setActiveNoteId(res.data.id)
      setActiveTab('cheat')

      // Scroll smoothly to output
      setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 100)
    } catch (err: any) {
      console.error('Failed to generate smart notes:', err)
      setError(err.response?.data?.detail || 'Failed to generate notes. Please try again.')
    } finally {
      setIsGenerating(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteConfirmId) return
    try {
      await notesApi.delete(deleteConfirmId)
      await queryClient.invalidateQueries({ queryKey: ['saved-study-notes'] })
      if (activeNoteId === deleteConfirmId) setActiveNoteId(null)
      setDeleteConfirmId(null)
    } catch (err) {
      console.error('Failed to delete note:', err)
    }
  }

  const handleCopyMarkdown = () => {
    if (activeNote?.content_markdown) {
      navigator.clipboard.writeText(activeNote.content_markdown)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleDownloadMarkdown = () => {
    if (!activeNote?.content_markdown) return
    const blob = new Blob([activeNote.content_markdown], { type: 'text/markdown;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${activeNote.title.replace(/[^a-zA-Z0-9_-]/g, '_')}.md`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-5xl mx-auto space-y-8 bg-[#FAF8F3] text-[#20201D] font-sans antialiased min-h-screen">
      
      <ConfirmModal
        isOpen={Boolean(deleteConfirmId)}
        title="Delete Saved Note?"
        message="Are you sure you want to remove this study note from your library?"
        confirmText="Delete"
        cancelText="Cancel"
        variant="danger"
        onConfirm={handleDelete}
        onCancel={() => setDeleteConfirmId(null)}
      />

      {/* ─── Header ─── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-[#E7E1D8]/80 print:hidden">
        <div className="flex items-center gap-3.5">
          <div className="w-11 h-11 rounded-2xl bg-gradient-to-tr from-[#F28A45] to-[#FF9F5A] text-white flex items-center justify-center shadow-xs">
            <Sparkles size={22} />
          </div>
          <div>
            <h1 className="text-xl sm:text-2xl font-black text-[#20201D] tracking-tight">
              Smart Notes
            </h1>
            <p className="text-xs text-[#6F6B63] font-medium">
              3-Step Revision Hub: Cheat Notes • Key Equations • Solved Exam Papers
            </p>
          </div>
        </div>

        {savedNotes.length > 0 && (
          <button
            onClick={() => setIsHistoryOpen(!isHistoryOpen)}
            className="px-3.5 py-2 rounded-xl text-xs font-bold bg-white hover:bg-[#F4EFE7] border border-[#E7E1D8] text-[#20201D] shadow-2xs flex items-center gap-2 transition-all cursor-pointer self-start sm:self-auto"
          >
            <BookOpen size={14} className="text-[#F28A45]" />
            <span>Saved Notes ({savedNotes.length})</span>
            {isHistoryOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        )}
      </div>

      {/* ─── 3-STEP LINEAR GENERATOR WIZARD ─── */}
      <div className="bg-white rounded-3xl p-6 sm:p-8 border border-[#E7E1D8] shadow-xs space-y-6 print:hidden">
        
        {/* Error Callout */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="p-3.5 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 text-xs font-bold flex items-start gap-2.5"
            >
              <AlertTriangle size={16} className="text-rose-600 flex-shrink-0 mt-0.5" />
              <span className="flex-1">{error}</span>
              <button onClick={() => setError(null)} className="text-rose-500 hover:text-rose-900 cursor-pointer">
                <X size={14} />
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── STEP 1: Select Chapter ── */}
        <div className="space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-[#20201D] text-white text-[11px] font-black flex items-center justify-center">
                1
              </span>
              <h2 className="text-sm font-black text-[#20201D] uppercase tracking-wider">
                Select Chapter
              </h2>
            </div>

            {/* Subject Filter Pills */}
            <div className="flex items-center gap-1 bg-[#FAF8F3] p-1 rounded-xl border border-[#E7E1D8]">
              {['All', 'Math', 'Physics', 'Chemistry'].map((cat) => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => setSubjectFilter(cat)}
                  className={`text-xs px-2.5 py-1 rounded-lg font-bold transition-all cursor-pointer ${
                    subjectFilter === cat
                      ? 'bg-[#20201D] text-white shadow-2xs'
                      : 'text-[#6F6B63] hover:text-[#20201D]'
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>

          {/* Chapter Selector Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 max-h-48 overflow-y-auto pr-1">
            {filteredPresets.map((p) => {
              const isSelected = selectedPreset === p.id
              return (
                <motion.button
                  key={p.id}
                  type="button"
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.99 }}
                  onClick={() => setSelectedPreset(p.id)}
                  className={`p-3 rounded-2xl text-left border transition-all cursor-pointer flex items-center justify-between gap-2 ${
                    isSelected
                      ? 'bg-[#FFF0E4] text-[#F28A45] border-[#F28A45]/50 font-bold shadow-2xs ring-2 ring-[#F28A45]/20'
                      : 'bg-[#FAF8F3] text-[#20201D] border-[#E7E1D8] hover:bg-[#F4EFE7] font-medium'
                  }`}
                >
                  <div className="flex items-center gap-2 truncate">
                    <span className="text-base">{p.icon}</span>
                    <div className="truncate">
                      <p className="text-xs font-black truncate">{p.title}</p>
                      <p className="text-[10px] text-[#6F6B63] font-normal">{p.subject}</p>
                    </div>
                  </div>
                  {isSelected && <CheckCircle2 size={16} className="text-[#F28A45] flex-shrink-0" />}
                </motion.button>
              )
            })}
          </div>
        </div>

        {/* ── STEP 2: Upload Notes or PYQ (Optional) ── */}
        <div className="space-y-3 pt-4 border-t border-[#E7E1D8]/70">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-[#FAF8F3] border border-[#E7E1D8] text-[#20201D] text-[11px] font-black flex items-center justify-center">
                2
              </span>
              <h2 className="text-sm font-black text-[#20201D] uppercase tracking-wider">
                Upload Custom Material <span className="text-[11px] font-normal text-[#6F6B63] lowercase tracking-normal">(optional)</span>
              </h2>
            </div>
            {(materialFile || pyqFiles.length > 0) && (
              <span className="text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200">
                ✓ {materialFile ? '1 PDF ' : ''}{pyqFiles.length > 0 ? `+ ${pyqFiles.length} PYQs` : ''} attached
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* Box A: Upload PDF/Notes */}
            <div
              onClick={() => materialInputRef.current?.click()}
              className={`p-4 rounded-2xl border-2 border-dashed transition-all cursor-pointer flex flex-col justify-between space-y-2 ${
                materialFile
                  ? 'border-emerald-400 bg-emerald-50/40 text-emerald-950'
                  : 'border-[#E7E1D8] bg-[#FAF8F3] hover:bg-[#F4EFE7] hover:border-[#F28A45]/40 text-[#20201D]'
              }`}
            >
              <input
                ref={materialInputRef}
                type="file"
                accept=".pdf,.docx,.txt"
                className="hidden"
                onChange={handleMaterialChange}
              />
              <div className="flex items-start justify-between gap-2">
                <div className="w-8 h-8 rounded-xl bg-white border border-[#E7E1D8] flex items-center justify-center text-[#F28A45]">
                  <Upload size={16} />
                </div>
                {materialFile && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      setMaterialFile(null)
                    }}
                    className="text-xs text-red-500 hover:text-red-700 font-bold p-1 cursor-pointer"
                  >
                    Remove
                  </button>
                )}
              </div>
              <div>
                <p className="text-xs font-black truncate">
                  {materialFile ? materialFile.name : 'Upload Chapter PDF / Notes'}
                </p>
                <p className="text-[10px] text-[#6F6B63] mt-0.5">
                  {materialFile ? 'Ready to synthesize with chapter' : 'Use your school notes or custom textbook'}
                </p>
              </div>
            </div>

            {/* Box B: Upload Previous Year Questions */}
            <div
              onClick={() => pyqInputRef.current?.click()}
              className={`p-4 rounded-2xl border-2 border-dashed transition-all cursor-pointer flex flex-col justify-between space-y-2 ${
                pyqFiles.length > 0
                  ? 'border-indigo-400 bg-indigo-50/40 text-indigo-950'
                  : 'border-[#E7E1D8] bg-[#FAF8F3] hover:bg-[#F4EFE7] hover:border-indigo-300 text-[#20201D]'
              }`}
            >
              <input
                ref={pyqInputRef}
                type="file"
                multiple
                accept=".pdf,.docx,.txt,.png,.jpg"
                className="hidden"
                onChange={handlePyqChange}
              />
              <div className="flex items-start justify-between gap-2">
                <div className="w-8 h-8 rounded-xl bg-white border border-[#E7E1D8] flex items-center justify-center text-indigo-600">
                  <FileCheck2 size={16} />
                </div>
                {pyqFiles.length > 0 && (
                  <span className="text-[10px] font-black uppercase px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-800 border border-indigo-200">
                    {pyqFiles.length} Papers
                  </span>
                )}
              </div>
              <div>
                <p className="text-xs font-black truncate">
                  {pyqFiles.length > 0 ? `${pyqFiles.length} Past Year Papers Attached` : 'Upload Previous Year Questions (PYQ)'}
                </p>
                <p className="text-[10px] text-[#6F6B63] mt-0.5">
                  {pyqFiles.length > 0 ? 'Will solve questions based on real papers' : 'Attach 2024, 2023 papers to generate solved papers'}
                </p>
              </div>
            </div>
          </div>

          {pyqFiles.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {pyqFiles.map((f, i) => (
                <span key={i} className="text-[10px] font-bold px-2 py-1 rounded-lg bg-[#FAF8F3] border border-[#E7E1D8] flex items-center gap-1.5 text-[#20201D]">
                  <span>📄 {f.name}</span>
                  <button
                    onClick={() => removePyqFile(i)}
                    className="text-red-500 hover:text-red-700 font-bold ml-1 cursor-pointer"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>

        {/* ── STEP 3: Generate CTA ── */}
        <div className="pt-4 border-t border-[#E7E1D8]/70">
          <motion.button
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.99 }}
            onClick={handleGenerate}
            disabled={isGenerating}
            className="w-full py-4 px-6 rounded-2xl bg-[#20201D] hover:bg-black text-white text-sm font-black flex items-center justify-center gap-2.5 shadow-md hover:shadow-lg transition-all cursor-pointer disabled:opacity-50"
          >
            {isGenerating ? (
              <>
                <RefreshCw size={18} className="animate-spin text-[#F28A45]" />
                <span>Synthesizing Smart Notes (Cheat Sheet + Formulas + Solved Qs)...</span>
              </>
            ) : (
              <>
                <Sparkles size={18} className="text-[#F28A45]" />
                <span>
                  {materialFile
                    ? `Generate Smart Notes from ${materialFile.name}`
                    : `Generate Smart Notes for ${selectedPresetObj?.title || 'Selected Chapter'}`}
                </span>
                <ArrowRight size={16} />
              </>
            )}
          </motion.button>
        </div>

      </div>

      {/* ─── OUTPUT CANVAS: 3 CLEAN TABS ─── */}
      <div ref={resultsRef} className="space-y-4">
        {activeNote ? (
          <motion.div
            key={activeNote.id}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className="bg-white rounded-3xl p-6 sm:p-8 border border-[#E7E1D8] shadow-sm space-y-6"
          >
            
            {/* Output Header */}
            <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 pb-4 border-b border-[#E7E1D8]/80">
              <div className="space-y-1.5">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="px-2.5 py-0.5 rounded-full bg-[#FFF0E4] text-[#F28A45] text-[11px] font-black uppercase tracking-wider border border-[#F28A45]/30">
                    {activeNote.subject}
                  </span>
                  {activeNote.pyq_doc_names?.length > 0 ? (
                    <span className="px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 text-[11px] font-bold border border-indigo-200 flex items-center gap-1">
                      <span>📝</span>
                      <span>PYQ Solved ({activeNote.pyq_doc_names.length} Papers)</span>
                    </span>
                  ) : (
                    <span className="px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-800 text-[11px] font-bold border border-emerald-200 flex items-center gap-1">
                      <span>📘</span>
                      <span>Standard High-Yield Note</span>
                    </span>
                  )}
                </div>
                <h2 className="text-xl sm:text-2xl font-black text-[#20201D] tracking-tight">
                  {activeNote.title}
                </h2>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={handleCopyMarkdown}
                  className="p-2.5 rounded-xl text-xs font-bold bg-[#FAF8F3] hover:bg-[#F4EFE7] border border-[#E7E1D8] text-[#6F6B63] hover:text-[#20201D] transition-all cursor-pointer"
                  title="Copy Full Markdown"
                >
                  {copied ? <Check size={16} className="text-emerald-600" /> : <Copy size={16} />}
                </button>
                <button
                  onClick={handleDownloadMarkdown}
                  className="p-2.5 rounded-xl text-xs font-bold bg-[#FAF8F3] hover:bg-[#F4EFE7] border border-[#E7E1D8] text-[#6F6B63] hover:text-[#20201D] transition-all cursor-pointer"
                  title="Download Note (.md)"
                >
                  <Download size={16} />
                </button>
                <button
                  onClick={() => {
                    const targetTopic = activeNote?.topic_id || 'math-10-1'
                    navigate(`/quiz/${targetTopic}`, {
                      state: {
                        noteId: activeNote?.id,
                        topicId: targetTopic,
                        focusTopic: activeNote?.title || activeNote?.subject || '',
                        title: activeNote?.title,
                        noteContent: activeNote?.content_markdown,
                        forceGenerate: true,
                      },
                    })
                  }}
                  className="py-2.5 px-4 rounded-xl text-xs font-black bg-[#20201D] hover:bg-black text-white flex items-center gap-1.5 shadow-2xs transition-all cursor-pointer"
                >
                  <Brain size={15} className="text-[#F28A45]" />
                  <span>Practice Quiz</span>
                </button>
              </div>
            </div>

            {/* ─── 3 PRIMARY TABS ─── */}
            <div className="flex items-center gap-1.5 bg-[#FAF8F3] p-1.5 rounded-2xl border border-[#E7E1D8]">
              {/* Tab 1: 5-Min Cheat Notes */}
              <button
                onClick={() => setActiveTab('cheat')}
                className={`relative flex-1 py-2.5 px-3 rounded-xl text-xs font-black transition-all cursor-pointer flex items-center justify-center gap-2 ${
                  activeTab === 'cheat' ? 'text-emerald-950' : 'text-[#6F6B63] hover:text-[#20201D]'
                }`}
              >
                {activeTab === 'cheat' && (
                  <motion.div
                    layoutId="active-note-tab"
                    className="absolute inset-0 bg-white rounded-xl shadow-xs border border-emerald-200"
                  />
                )}
                <span className="relative z-10 flex items-center gap-1.5">
                  <span className="text-sm">📋</span>
                  <span>5-Minute Cheat Notes</span>
                </span>
              </button>

              {/* Tab 2: Key Equations & Topics */}
              <button
                onClick={() => setActiveTab('formulas')}
                className={`relative flex-1 py-2.5 px-3 rounded-xl text-xs font-black transition-all cursor-pointer flex items-center justify-center gap-2 ${
                  activeTab === 'formulas' ? 'text-amber-950' : 'text-[#6F6B63] hover:text-[#20201D]'
                }`}
              >
                {activeTab === 'formulas' && (
                  <motion.div
                    layoutId="active-note-tab"
                    className="absolute inset-0 bg-white rounded-xl shadow-xs border border-amber-200"
                  />
                )}
                <span className="relative z-10 flex items-center gap-1.5">
                  <span className="text-sm">📐</span>
                  <span>Important Equations & Topics</span>
                  {activeNote.key_formulas?.length > 0 && (
                    <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-amber-100 text-amber-800 border border-amber-200 font-black">
                      {activeNote.key_formulas.length}
                    </span>
                  )}
                </span>
              </button>

              {/* Tab 3: Solved Questions Paper */}
              <button
                onClick={() => setActiveTab('questions')}
                className={`relative flex-1 py-2.5 px-3 rounded-xl text-xs font-black transition-all cursor-pointer flex items-center justify-center gap-2 ${
                  activeTab === 'questions' ? 'text-rose-950' : 'text-[#6F6B63] hover:text-[#20201D]'
                }`}
              >
                {activeTab === 'questions' && (
                  <motion.div
                    layoutId="active-note-tab"
                    className="absolute inset-0 bg-white rounded-xl shadow-xs border border-rose-200"
                  />
                )}
                <span className="relative z-10 flex items-center gap-1.5">
                  <span className="text-sm">📝</span>
                  <span>Solved Questions Paper</span>
                  {activeNote.solved_questions?.length > 0 && (
                    <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-rose-100 text-rose-800 border border-rose-200 font-black">
                      {activeNote.solved_questions.length} Qs
                    </span>
                  )}
                </span>
              </button>
            </div>

            {/* ─── TAB CONTENT PANELS ─── */}
            <AnimatePresence mode="wait">
              
              {/* TAB 1: 5-MIN CHEAT NOTES */}
              {activeTab === 'cheat' && (
                <motion.div
                  key="tab-cheat"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.2 }}
                  className="space-y-6"
                >
                  {/* High Yield Badges */}
                  {activeNote.high_yield_topics?.length > 0 && (
                    <div className="p-4 rounded-2xl bg-[#FAF8F3] border border-[#E7E1D8] space-y-2">
                      <span className="text-[11px] font-black uppercase text-[#6F6B63] tracking-wider block">
                        🎯 Key Concepts to Master:
                      </span>
                      <div className="flex flex-wrap gap-1.5">
                        {activeNote.high_yield_topics.map((t: string, i: number) => (
                          <span
                            key={i}
                            className="px-2.5 py-1 rounded-xl bg-white border border-[#E7E1D8] text-xs font-bold text-[#20201D] shadow-2xs"
                          >
                            {t}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Clean Markdown Study Content */}
                  <div className="prose prose-sm max-w-none text-[#20201D] space-y-4">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm, remarkMath]}
                      rehypePlugins={[rehypeKatex]}
                      components={{
                        code({ className, children }: any) {
                          const match = /language-(\w+)/.exec(className || '')
                          const isMermaid = match && match[1] === 'mermaid'
                          const isInline = !match

                          if (isMermaid) {
                            return <MermaidDiagram chart={String(children).replace(/\n$/, '')} />
                          }
                          if (isInline) {
                            return (
                              <code className="bg-[#FAF8F3] text-[#F28A45] px-1.5 py-0.5 rounded-md text-xs font-mono font-bold border border-[#E7E1D8]">
                                {children}
                              </code>
                            )
                          }
                          return (
                            <pre className="bg-[#20201D] text-white p-4 rounded-2xl overflow-x-auto text-xs font-mono">
                              <code>{children}</code>
                            </pre>
                          )
                        },
                        h1: ({ children }) => <h1 className="text-lg sm:text-xl font-black text-[#20201D] mt-6 mb-3 border-b pb-2 border-[#E7E1D8]">{children}</h1>,
                        h2: ({ children }) => <h2 className="text-base font-black text-[#20201D] mt-5 mb-2">{children}</h2>,
                        h3: ({ children }) => <h3 className="text-sm font-extrabold text-[#20201D] mt-4 mb-2">{children}</h3>,
                        p: ({ children }) => <p className="text-xs sm:text-sm text-[#20201D] leading-relaxed mb-3 font-normal">{children}</p>,
                        ul: ({ children }) => <ul className="list-disc pl-5 space-y-1 text-xs sm:text-sm text-[#20201D] mb-3">{children}</ul>,
                        ol: ({ children }) => <ol className="list-decimal pl-5 space-y-1 text-xs sm:text-sm text-[#20201D] mb-3">{children}</ol>,
                        blockquote: ({ children }) => (
                          <blockquote className="border-l-4 border-[#F28A45] pl-4 py-2 my-3 bg-[#FFF0E4]/40 rounded-r-2xl text-xs sm:text-sm text-[#20201D] font-medium">
                            {children}
                          </blockquote>
                        ),
                        table: ({ children }) => (
                          <div className="overflow-x-auto my-4 rounded-2xl border border-[#E7E1D8] shadow-2xs">
                            <table className="w-full text-xs border-collapse">{children}</table>
                          </div>
                        ),
                        th: ({ children }) => <th className="border-b border-[#E7E1D8] bg-[#FAF8F3] p-2.5 font-black text-left text-[#20201D]">{children}</th>,
                        td: ({ children }) => <td className="border-b border-[#E7E1D8]/60 p-2.5 text-left text-[#20201D]">{children}</td>,
                      }}
                    >
                      {activeNote.content_markdown}
                    </ReactMarkdown>
                  </div>
                </motion.div>
              )}

              {/* TAB 2: IMPORTANT EQUATIONS & TOPICS */}
              {activeTab === 'formulas' && (
                <motion.div
                  key="tab-formulas"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.2 }}
                  className="space-y-4"
                >
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-[#6F6B63] font-medium">
                      Master these core formulas to solve 90%+ of board exam numericals:
                    </p>
                  </div>

                  {activeNote.key_formulas?.length > 0 ? (
                    <div className="grid grid-cols-1 gap-3">
                      {activeNote.key_formulas.map((form: string, idx: number) => (
                        <div
                          key={idx}
                          className="p-4 sm:p-5 rounded-2xl bg-white border border-[#E7E1D8] shadow-2xs space-y-2 hover:border-amber-400 transition-colors"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] font-black uppercase text-amber-700 bg-amber-50 px-2 py-0.5 rounded-md border border-amber-200">
                              Equation #{idx + 1}
                            </span>
                            <button
                              onClick={() => {
                                navigator.clipboard.writeText(form)
                                setCopiedFormulaIdx(idx)
                                setTimeout(() => setCopiedFormulaIdx(null), 1500)
                              }}
                              className="text-[11px] font-bold px-2.5 py-1 rounded-lg bg-[#FAF8F3] hover:bg-[#F4EFE7] border border-[#E7E1D8] text-[#6F6B63] cursor-pointer flex items-center gap-1.5 transition-colors"
                            >
                              {copiedFormulaIdx === idx ? <Check size={12} className="text-emerald-600" /> : <Copy size={12} />}
                              <span>{copiedFormulaIdx === idx ? 'Copied LaTeX' : 'Copy'}</span>
                            </button>
                          </div>
                          <div className="text-sm sm:text-base font-medium text-[#20201D] py-1">
                            <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                              {form}
                            </ReactMarkdown>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-[#969188] text-center py-8">No specific formulas listed for this topic.</p>
                  )}

                  {/* Exam Tips Callout */}
                  {activeNote.exam_tips?.length > 0 && (
                    <div className="p-5 rounded-2xl bg-amber-50/60 border border-amber-200 space-y-2.5 mt-6">
                      <span className="text-xs font-black text-amber-900 flex items-center gap-1.5">
                        <Zap size={15} className="text-amber-600" /> Examiner Traps & Pro-Tips:
                      </span>
                      <ul className="space-y-1.5 text-xs text-amber-950 font-medium">
                        {activeNote.exam_tips.map((tip: string, i: number) => (
                          <li key={i} className="flex items-start gap-2">
                            <span className="text-amber-600 font-bold">•</span>
                            <span>{tip}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </motion.div>
              )}

              {/* TAB 3: SOLVED QUESTIONS PAPER */}
              {activeTab === 'questions' && (
                <motion.div
                  key="tab-questions"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.2 }}
                  className="space-y-3"
                >
                  <div className="flex items-center justify-between pb-1">
                    <p className="text-xs text-[#6F6B63] font-medium">
                      {activeNote.pyq_doc_names?.length > 0
                        ? 'Solved questions extracted from your uploaded past papers:'
                        : '5 high-yield solved questions with official board marking breakdown:'}
                    </p>
                    <button
                      onClick={() => {
                        const allExpanded = Object.keys(expandedQuestions).length === (activeNote.solved_questions?.length || 0)
                        if (allExpanded) {
                          setExpandedQuestions({})
                        } else {
                          const all: Record<number, boolean> = {}
                          activeNote.solved_questions?.forEach((_: any, i: number) => { all[i] = true })
                          setExpandedQuestions(all)
                        }
                      }}
                      className="text-xs font-bold text-[#F28A45] hover:underline cursor-pointer"
                    >
                      {Object.keys(expandedQuestions).length > 0 ? 'Collapse All' : 'Expand All'}
                    </button>
                  </div>

                  {activeNote.solved_questions?.map((q: any, i: number) => {
                    const isExpanded = expandedQuestions[i] !== false
                    const marksBadgeClass =
                      i === 0
                        ? 'text-emerald-800 bg-emerald-100 border-emerald-200'
                        : i === 1
                        ? 'text-amber-800 bg-amber-100 border-amber-200'
                        : i === 4
                        ? 'text-rose-800 bg-rose-100 border-rose-200'
                        : 'text-[#F28A45] bg-[#FFF0E4] border-[#F28A45]/30'

                    return (
                      <div
                        key={i}
                        className="rounded-2xl border border-[#E7E1D8] overflow-hidden bg-white shadow-2xs transition-all"
                      >
                        <div
                          onClick={() => toggleQuestionExpand(i)}
                          className="p-4 bg-[#FAF8F3] hover:bg-[#F4EFE7] cursor-pointer flex items-start justify-between gap-3 transition-colors"
                        >
                          <div className="space-y-1.5 min-w-0 flex-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className={`text-[10px] font-black uppercase px-2.5 py-0.5 rounded-full border ${marksBadgeClass}`}>
                                {q.year_or_type || `Question ${i + 1}`}
                              </span>
                              {q.key_concept && (
                                <span className="text-[10px] font-bold text-[#6F6B63] bg-white px-2 py-0.5 rounded-full border border-[#E7E1D8]">
                                  {q.key_concept}
                                </span>
                              )}
                            </div>
                            <p className="text-xs sm:text-sm font-black text-[#20201D] leading-snug">
                              {q.question}
                            </p>
                          </div>
                          <button className="text-[#969188] p-1 mt-0.5">
                            {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                          </button>
                        </div>

                        <AnimatePresence>
                          {isExpanded && (
                            <motion.div
                              initial={{ opacity: 0, height: 0 }}
                              animate={{ opacity: 1, height: 'auto' }}
                              exit={{ opacity: 0, height: 0 }}
                              className="p-4 bg-white border-t border-[#E7E1D8] space-y-2"
                            >
                              <span className="text-xs font-black text-[#4F8A68] flex items-center gap-1.5">
                                <CheckCircle2 size={14} /> Step-by-Step Solution & Marking Scheme:
                              </span>
                              <div className="bg-[#FAF8F3] p-4 rounded-xl border border-[#E7E1D8]/70 text-xs sm:text-sm text-[#20201D] font-medium leading-relaxed">
                                <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                                  {q.step_by_step_solution}
                                </ReactMarkdown>
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>
                    )
                  })}
                </motion.div>
              )}

            </AnimatePresence>

          </motion.div>
        ) : (
          <div className="p-12 rounded-3xl bg-white border border-[#E7E1D8] text-center space-y-3 print:hidden">
            <div className="w-12 h-12 rounded-2xl bg-[#FAF8F3] border border-[#E7E1D8] flex items-center justify-center mx-auto text-[#969188]">
              <FileText size={24} />
            </div>
            <h3 className="text-base font-black text-[#20201D]">No Note Generated Yet</h3>
            <p className="text-xs text-[#6F6B63] max-w-sm mx-auto">
              Select a chapter above and click "Generate Smart Notes" to synthesize your study guide.
            </p>
          </div>
        )}
      </div>

      {/* ─── BOTTOM ACCORDION: SAVED NOTES HISTORY ─── */}
      {savedNotes.length > 0 && (
        <div className="bg-white rounded-3xl border border-[#E7E1D8] shadow-2xs overflow-hidden print:hidden">
          <div
            onClick={() => setIsHistoryOpen(!isHistoryOpen)}
            className="p-5 bg-[#FAF8F3] hover:bg-[#F4EFE7] cursor-pointer flex items-center justify-between transition-colors"
          >
            <div className="flex items-center gap-2.5">
              <BookOpen size={16} className="text-[#F28A45]" />
              <h3 className="text-xs sm:text-sm font-black text-[#20201D]">
                My Saved Smart Notes ({savedNotes.length})
              </h3>
            </div>
            <div className="flex items-center gap-2 text-xs font-bold text-[#6F6B63]">
              <span>{isHistoryOpen ? 'Hide' : 'Show All'}</span>
              {isHistoryOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </div>
          </div>

          <AnimatePresence>
            {isHistoryOpen && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="p-5 border-t border-[#E7E1D8] space-y-4"
              >
                <div className="relative">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#969188]" />
                  <input
                    type="text"
                    placeholder="Filter saved notes..."
                    value={searchHistory}
                    onChange={(e) => setSearchHistory(e.target.value)}
                    className="w-full pl-8 pr-3 py-2 text-xs rounded-xl bg-[#FAF8F3] border border-[#E7E1D8] focus:outline-none font-medium"
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 max-h-60 overflow-y-auto pr-1">
                  {filteredSavedNotes.map((n: any) => {
                    const isSelected = activeNote?.id === n.id
                    return (
                      <div
                        key={n.id}
                        onClick={() => {
                          setActiveNoteId(n.id)
                          setActiveTab('cheat')
                          resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                        }}
                        className={`p-3 rounded-2xl border transition-all cursor-pointer flex items-center justify-between group ${
                          isSelected
                            ? 'bg-[#FFF0E4] border-[#F28A45]/50 text-[#20201D] shadow-2xs ring-1 ring-[#F28A45]/30'
                            : 'bg-[#FAF8F3] border-[#E7E1D8] hover:bg-[#F4EFE7]'
                        }`}
                      >
                        <div className="min-w-0 pr-2">
                          <p className="text-xs font-black truncate">{n.title}</p>
                          <p className="text-[10px] text-[#6F6B63] mt-0.5">
                            {n.subject} • {new Date(n.created_at).toLocaleDateString()}
                          </p>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setDeleteConfirmId(n.id)
                          }}
                          className="opacity-0 group-hover:opacity-100 text-[#969188] hover:text-red-600 p-1.5 transition-opacity cursor-pointer"
                          title="Delete note"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    )
                  })}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* ─── PRINT VIEW ─── */}
      {activeNote && (
        <div className="hidden print:block bg-white p-8 text-[#20201D]">
          <div className="border-b-2 border-[#20201D] pb-3 mb-6 flex justify-between items-start">
            <div>
              <h1 className="text-2xl font-black">{activeNote.title}</h1>
              <p className="text-xs uppercase font-bold text-[#F28A45]">Subject: {activeNote.subject} • DeepTutor Exam Notes</p>
            </div>
            <div className="text-right text-xs">
              <p>Generated: {new Date(activeNote.created_at).toLocaleDateString()}</p>
            </div>
          </div>

          <div className="prose prose-sm max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[rehypeKatex]}
            >
              {activeNote.content_markdown}
            </ReactMarkdown>
          </div>
        </div>
      )}

    </div>
  )
}
