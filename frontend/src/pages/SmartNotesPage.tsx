import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import {
  FileText, Upload, Sparkles, Brain, CheckCircle2,
  Trash2, Download, Copy, Check, Printer, HelpCircle,
  Clock, AlertTriangle, BookOpen, Layers, Plus,
  Search, ExternalLink, ChevronRight, RefreshCw, X,
  FileCheck, ShieldAlert, ArrowRight, Zap, Target
} from 'lucide-react'
import { notesApi, documentsApi } from '../services/api'
import MermaidDiagram from '../components/MermaidDiagram'
import ConfirmModal from '../components/ConfirmModal'

const PRESET_SUBJECTS = [
  { id: 'math-10-1', subject: 'Mathematics', title: 'Arithmetic Sequences' },
  { id: 'math-10-2', subject: 'Mathematics', title: 'Circles and Angles' },
  { id: 'math-10-6', subject: 'Mathematics', title: 'Trigonometry' },
  { id: 'phys-10-1', subject: 'Physics', title: 'Wave Motion & Oscillations' },
  { id: 'phys-10-2', subject: 'Physics', title: 'Refraction of Light & Lenses' },
  { id: 'phys-10-4', subject: 'Physics', title: 'Magnetic Effect of Electric Current' },
  { id: 'chem-10-1', subject: 'Chemistry', title: 'Nomenclature of Organic Compounds' },
  { id: 'chem-10-3', subject: 'Chemistry', title: 'Periodic Table & Electron Configuration' },
  { id: 'chem-10-4', subject: 'Chemistry', title: 'Gas Laws and Mole Concept' },
]

const NOTE_TYPES = [
  {
    id: 'high_yield_master',
    name: 'Master Revision Note',
    icon: '🌟',
    desc: 'Comprehensive theory + PYQ weightage + solved problems + Mermaid flowchart',
  },
  {
    id: 'pyq_analysis',
    name: 'PYQ Exam Trends',
    icon: '🎯',
    desc: 'Year-by-year recurring patterns, marks weightage & predicted questions',
  },
  {
    id: 'quick_cheat_sheet',
    name: '5-Min Cheat Sheet',
    icon: '⚡',
    desc: 'High-density formulas, definitions, mnemonics & exam traps to avoid',
  },
  {
    id: 'solved_qa',
    name: 'Solved PYQ Question Bank',
    icon: '📝',
    desc: 'Step-by-step solutions with marking scheme criteria and key concepts',
  },
]

export default function SmartNotesPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Selection & Upload State
  const [selectedPreset, setSelectedPreset] = useState<string>('')
  const [subjectName, setSubjectName] = useState<string>('Mathematics')
  const [noteType, setNoteType] = useState<string>('high_yield_master')
  const [customInstructions, setCustomInstructions] = useState<string>('')
  
  const [materialFile, setMaterialFile] = useState<File | null>(null)
  const [pyqFiles, setPyqFiles] = useState<File[]>([])
  const [isGenerating, setIsGenerating] = useState(false)
  const [copied, setCopied] = useState(false)
  const [activeNoteId, setActiveNoteId] = useState<string | null>(null)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)
  const [searchNotes, setSearchNotes] = useState<string>('')

  const materialInputRef = useRef<HTMLInputElement>(null)
  const pyqInputRef = useRef<HTMLInputElement>(null)

  // Fetch saved notes
  const { data: savedNotes = [], isLoading: isLoadingNotes } = useQuery({
    queryKey: ['saved-study-notes'],
    queryFn: () => notesApi.list().then((r) => r.data),
    staleTime: 30_000,
  })

  // Currently displayed note
  const activeNote = savedNotes.find((n: any) => n.id === activeNoteId) || savedNotes[0] || null

  const handleMaterialChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setMaterialFile(e.target.files[0])
      setSelectedPreset('')
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

  const handlePresetSelect = (presetId: string) => {
    setSelectedPreset(presetId)
    setMaterialFile(null)
    const match = PRESET_SUBJECTS.find((p) => p.id === presetId)
    if (match) {
      setSubjectName(match.subject)
    }
  }

  const handleGenerate = async () => {
    setIsGenerating(true)
    try {
      const matchPreset = PRESET_SUBJECTS.find((p) => p.id === selectedPreset)
      const res = await notesApi.generate({
        materialFile,
        pyqFiles,
        topicId: selectedPreset || 'general',
        subject: matchPreset?.subject || subjectName || 'General Studies',
        noteType,
        customInstructions,
      })

      await queryClient.invalidateQueries({ queryKey: ['saved-study-notes'] })
      await queryClient.invalidateQueries({ queryKey: ['student-record'] })
      setActiveNoteId(res.data.id)
      
      // Clear uploaded temp state
      setMaterialFile(null)
      setPyqFiles([])
      setCustomInstructions('')
    } catch (err: any) {
      console.error('Failed to generate smart note:', err)
      alert(err.response?.data?.detail || 'Failed to generate study note. Please try again.')
    } finally {
      setIsGenerating(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteConfirmId) return
    try {
      await notesApi.delete(deleteConfirmId)
      await queryClient.invalidateQueries({ queryKey: ['saved-study-notes'] })
      await queryClient.invalidateQueries({ queryKey: ['student-record'] })
      if (activeNoteId === deleteConfirmId) {
        setActiveNoteId(null)
      }
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

  const handlePrint = () => {
    window.print()
  }

  const filteredSavedNotes = savedNotes.filter((n: any) =>
    n.title.toLowerCase().includes(searchNotes.toLowerCase()) ||
    n.subject.toLowerCase().includes(searchNotes.toLowerCase())
  )

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-8 bg-transparent text-text-primary font-sans antialiased">
      
      {/* Delete Confirmation Modal */}
      <ConfirmModal
        isOpen={Boolean(deleteConfirmId)}
        title="Delete Smart Note?"
        message="Are you sure you want to permanently delete this Smart Note? This action cannot be undone."
        confirmText="Delete Note"
        cancelText="Cancel"
        variant="danger"
        onConfirm={handleDelete}
        onCancel={() => setDeleteConfirmId(null)}
      />

      {/* ─── 1. TOP HEADER ─── */}
      <div className="print:hidden space-y-4">
        {/* Embedded AI Generated Hero Image */}
        <div className="w-full overflow-hidden relative">
          <div className="relative w-full h-32 sm:h-48 rounded-3xl overflow-hidden shadow-sm border border-white">
            <img src="/assets/images/smart_notes_hero.jpg" alt="Smart Notes Hero" className="w-full h-full object-cover object-center scale-105" />
            <div className="absolute inset-0 bg-gradient-to-r from-brand-primary/90 to-transparent flex items-center p-6 sm:p-8">
              <div className="text-white space-y-2 relative z-10">
                <h1 className="text-3xl sm:text-4xl font-bold tracking-tight flex items-center gap-3 !text-white drop-shadow-md" style={{ color: '#ffffff' }}>
                  Smart Notes & PYQ Generator
                  <span className="text-[10px] font-bold !text-text-primary bg-white px-2 py-0.5 rounded-full uppercase tracking-wider shadow-sm drop-shadow-none" style={{ color: 'var(--color-text-primary)' }}>
                    AI Powered
                  </span>
                </h1>
                <p className="text-sm !text-white/95 font-medium max-w-lg drop-shadow" style={{ color: 'rgba(255, 255, 255, 0.95)' }}>
                  Upload your syllabus and PYQs to synthesize beautiful, high-yield revision notes instantly.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Action Buttons Row */}
        {activeNote && (
          <div className="flex items-center justify-end gap-3 border-b border-border pb-4">
            <button
              onClick={handleCopyMarkdown}
              className="px-3.5 py-2.5 rounded-xl border border-border bg-white hover:bg-black/5 text-text-primary font-bold text-xs flex items-center gap-1.5 shadow-sm transition-all cursor-pointer"
            >
              {copied ? <Check size={14} className="text-success" /> : <Copy size={14} />}
              <span>{copied ? 'Copied' : 'Copy Markdown'}</span>
            </button>
            <button
              onClick={() => window.print()}
              className="btn-primary font-bold text-xs py-2.5 px-4 rounded-xl flex items-center gap-1.5 shadow-sm cursor-pointer"
            >
              <Printer size={15} />
              <span>Export / Print Note</span>
            </button>
          </div>
        )}
      </div>

      
      {/* ─── 2. GENERATOR DASHBOARD (Horizontal) ─── */}
      <div className="card p-5 sm:p-6 mb-6 print:hidden">
        <div className="flex items-center justify-between mb-4 border-b border-border/50 pb-4">
          <h2 className="text-base font-bold text-text-primary flex items-center gap-2">
            <Upload size={18} className="text-brand-primary" />
            <span>Generate New Smart Note</span>
          </h2>
          <span className="text-[10px] uppercase font-bold text-text-secondary bg-black/5 px-2 py-1 rounded-md tracking-wider">Step 1 to 3</span>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 lg:gap-8">
          
          {/* Col 1: Material */}
          <div className="space-y-4">
            {/* Dropzone 1: Chapter / Study Material */}
            <div className="space-y-2">
              <label className="text-xs font-bold text-text-secondary uppercase tracking-wider block">
                Chapter / Textbook Material
              </label>

              {/* Preset Selector */}
              <div className="grid grid-cols-1 gap-2 max-h-40 overflow-y-auto pr-1 custom-scrollbar">
                {PRESET_SUBJECTS.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => handlePresetSelect(p.id)}
                    className={`text-left px-4 py-3 rounded-2xl text-xs font-bold transition-all flex items-center justify-between border cursor-pointer ${
                      selectedPreset === p.id
                        ? 'bg-brand-primary text-white border-brand-primary shadow-md'
                        : 'bg-white/50 text-text-secondary border-border hover:bg-white hover:border-brand-primary/30 hover:shadow-sm'
                    }`}
                  >
                    <span className="truncate flex items-center gap-2">
                      <BookOpen size={14} className={selectedPreset === p.id ? 'text-white' : 'text-brand-primary'} />
                      {p.title}
                    </span>
                    <span className={`text-[10px] uppercase ${selectedPreset === p.id ? 'text-white/80' : 'text-text-muted'}`}>{p.subject}</span>
                  </button>
                ))}
              </div>

              {/* Or Custom File Upload */}
              <div
                onClick={() => materialInputRef.current?.click()}
                className={`p-4 rounded-2xl border-2 border-dashed cursor-pointer text-center transition-all ${
                  materialFile
                    ? 'bg-success-soft/60 border-success text-success'
                    : 'bg-transparent border-border hover:border-brand-primary/30 text-text-secondary'
                }`}
              >
                <input
                  ref={materialInputRef}
                  type="file"
                  accept=".pdf,.docx,.doc,.txt"
                  className="hidden"
                  onChange={handleMaterialChange}
                />
                <div className="flex flex-col items-center gap-1.5">
                  <FileText size={22} className={materialFile ? 'text-success' : 'text-brand-primary'} />
                  <p className="text-xs font-bold truncate max-w-xs">
                    {materialFile ? materialFile.name : 'Or Upload Custom Chapter / Syllabus PDF'}
                  </p>
                  <span className="text-[10px] text-text-muted">PDF, DOCX, TXT up to 50MB</span>
                </div>
              </div>
            </div>
          </div>

          {/* Col 2: PYQ & Custom Instructions */}
          <div className="space-y-4">
            {/* Dropzone 2: Previous Year Question Papers (PYQ) */}
            <div className="space-y-2 ">
              <div className="flex items-center justify-between">
                <label className="text-xs font-bold text-text-secondary uppercase tracking-wider block">
                  Previous Year Question Papers (PYQs)
                </label>
                <span className="text-[11px] font-bold text-brand-primary">{pyqFiles.length} papers added</span>
              </div>

              <div
                onClick={() => pyqInputRef.current?.click()}
                className="p-4 rounded-2xl border-2 border-dashed border-brand-primary/30 bg-brand-primary-soft/30 hover:bg-brand-primary-soft/60 cursor-pointer text-center transition-all"
              >
                <input
                  ref={pyqInputRef}
                  type="file"
                  multiple
                  accept=".pdf,.docx,.doc,.txt,.png,.jpg,.jpeg"
                  className="hidden"
                  onChange={handlePyqChange}
                />
                <div className="flex flex-col items-center gap-1">
                  <Plus size={20} className="text-brand-primary" />
                  <p className="text-xs font-bold text-text-primary">
                    + Add PYQ Papers (2024, 2023, 2022...)
                  </p>
                  <span className="text-[10px] text-text-secondary">Multi-file PDF / Image papers supported</span>
                </div>
              </div>

              {/* Uploaded PYQ list */}
              {pyqFiles.length > 0 && (
                <div className="space-y-1.5 pt-1 max-h-32 overflow-y-auto">
                  {pyqFiles.map((file, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between px-3 py-1.5 rounded-xl bg-transparent border border-border text-xs font-semibold text-text-primary"
                    >
                      <span className="truncate max-w-[200px] flex items-center gap-1.5">
                        <FileCheck size={13} className="text-success" />
                        {file.name}
                      </span>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          removePyqFile(idx)
                        }}
                        className="text-text-muted hover:text-error p-1"
                      >
                        <X size={13} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            {/* Custom Instructions */}
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-text-secondary">
                Custom Exam Focus (Optional)
              </label>
              <input
                type="text"
                placeholder="e.g., Focus on 4-mark questions, numerical derivations & IUPAC"
                value={customInstructions}
                onChange={(e) => setCustomInstructions(e.target.value)}
                className="w-full text-xs p-3 rounded-xl bg-transparent border border-border focus:outline-none focus:border-brand-primary font-medium"
              />
            </div>
          </div>

          {/* Col 3: Mode & Generate */}
          <div className="space-y-4 flex flex-col justify-between">
            <div>
              {/* Note Mode Selector */}
            <div className="space-y-2 ">
              <label className="text-xs font-bold text-text-secondary uppercase tracking-wider block">
                2. Note Synthesis Mode
              </label>
              <div className="grid grid-cols-2 gap-2">
                {NOTE_TYPES.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setNoteType(t.id)}
                    className={`p-4 rounded-2xl border text-left transition-all cursor-pointer flex flex-col justify-between ${
                      noteType === t.id
                        ? 'bg-brand-primary text-white border-brand-primary shadow-md transform scale-[1.02]'
                        : 'bg-white/50 text-text-primary border-border hover:bg-white hover:shadow-sm'
                    }`}
                  >
                    <span className="text-xl block mb-1.5">{t.icon}</span>
                    <p className="text-xs font-bold leading-tight mb-1">{t.name}</p>
                    <p className={`text-[10px] leading-relaxed line-clamp-2 ${noteType === t.id ? 'text-white/80' : 'text-text-secondary'}`}>
                      {t.desc}
                    </p>
                  </button>
                ))}
              </div>
            </div>
            </div>
            <div className="pt-2 mt-auto">
              {/* Generate Button */}
            <button
              onClick={handleGenerate}
              disabled={isGenerating || (!materialFile && !selectedPreset)}
              className={`w-full py-3.5 px-4 rounded-2xl font-bold text-sm flex items-center justify-center gap-2 shadow-md transition-all ${
                isGenerating || (!materialFile && !selectedPreset)
                  ? 'bg-[#E7E1D8] text-text-muted cursor-not-allowed'
                  : 'btn-primary active:scale-[0.98] cursor-pointer'
              }`}
            >
              {isGenerating ? (
                <>
                  <RefreshCw size={17} className="animate-spin" />
                  <span>Synthesizing High-Yield Notes...</span>
                </>
              ) : (
                <>
                  <Sparkles size={17} />
                  <span>Generate Complete Smart Notes</span>
                </>
              )}
            </button>
            </div>
          </div>

        </div>
      </div>

      {/* ─── 3. MAIN WORKSPACE ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 print:hidden">
        
        {/* Sidebar: Saved Notes (4 cols) */}
        <div className="lg:col-span-4">
          {/* Saved Notes Quick Library Sidebar */}
          <div className="card p-6 space-y-4 h-full max-h-[800px] flex flex-col">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                <BookOpen size={16} className="text-success" />
                <span>Saved Notes Library ({savedNotes.length})</span>
              </h3>
              <span className="text-[10px] text-text-muted uppercase font-bold">Offline & Cloud</span>
            </div>

            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                type="text"
                placeholder="Filter saved notes..."
                value={searchNotes}
                onChange={(e) => setSearchNotes(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl bg-transparent border border-border focus:outline-none font-medium"
              />
            </div>

            <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
              {filteredSavedNotes.length === 0 ? (
                <p className="text-center text-xs text-text-muted py-4">No notes generated yet.</p>
              ) : (
                filteredSavedNotes.map((n: any) => {
                  const isSelected = activeNote?.id === n.id
                  return (
                    <div
                      key={n.id}
                      onClick={() => setActiveNoteId(n.id)}
                      className={`p-3 rounded-2xl border transition-all cursor-pointer flex items-center justify-between group ${
                        isSelected
                          ? 'bg-brand-primary-soft border-brand-primary/30 text-text-primary shadow-2xs'
                          : 'bg-transparent border-border hover:bg-black/5'
                      }`}
                    >
                      <div className="min-w-0 pr-2">
                        <p className="text-xs font-bold truncate">{n.title}</p>
                        <p className="text-[10px] text-text-secondary mt-0.5">
                          {n.subject} • {new Date(n.created_at).toLocaleDateString()}
                        </p>
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setDeleteConfirmId(n.id)
                        }}
                        className="opacity-0 group-hover:opacity-100 text-text-muted hover:text-error p-1.5 transition-opacity"
                        title="Delete note"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </div>

        {/* Main: Note Viewer (8 cols) */}
        <div className="lg:col-span-8">
          {activeNote ? (
            <div className="card p-6 sm:p-8 space-y-6">
              
              {/* Note Metadata Header */}
              <div className="border-b border-border/70 pb-5 space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="px-3 py-1 rounded-full bg-brand-primary-soft text-brand-primary text-xs font-bold uppercase tracking-wider border border-brand-primary/30">
                    {activeNote.subject}
                  </span>
                  <span className="px-3 py-1 rounded-full bg-success-soft text-success text-xs font-bold">
                    {activeNote.note_type.replace(/_/g, ' ').toUpperCase()}
                  </span>
                  <span className="text-xs text-text-muted font-medium ml-auto">
                    Created {new Date(activeNote.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                  </span>
                </div>

                <h2 className="text-xl sm:text-2xl font-bold text-text-primary tracking-tight">
                  {activeNote.title}
                </h2>

                {/* Sources Pill Row */}
                <div className="flex flex-wrap items-center gap-2 text-xs text-text-secondary">
                  {activeNote.material_doc_name && (
                    <span className="px-2.5 py-1 rounded-xl bg-transparent border border-border flex items-center gap-1 font-semibold">
                      📖 {activeNote.material_doc_name}
                    </span>
                  )}
                  {activeNote.pyq_doc_names?.map((pname: string, i: number) => (
                    <span key={i} className="px-2.5 py-1 rounded-xl bg-brand-primary-soft/60 text-brand-primary border border-brand-primary/30 flex items-center gap-1 font-bold">
                      📝 {pname}
                    </span>
                  ))}
                </div>
              </div>

              {/* High-Yield Topics Chip Strip */}
              {activeNote.high_yield_topics?.length > 0 && (
                <div className="bg-transparent p-4 rounded-2xl border border-border space-y-2">
                  <p className="text-[11px] font-bold text-brand-primary uppercase tracking-wider flex items-center gap-1.5">
                    <Zap size={13} />
                    High-Yield Exam Topics Identified
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {activeNote.high_yield_topics.map((topic: string, i: number) => (
                      <span
                        key={i}
                        className="px-2.5 py-1 rounded-xl bg-white border border-border text-xs font-bold text-text-primary shadow-2xs"
                      >
                        ⭐ {topic}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Solved Questions Accordion Card */}
              {activeNote.solved_questions?.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                    <Target size={16} className="text-success" />
                    <span>Solved Previous Year Questions (PYQs)</span>
                  </h3>
                  <div className="space-y-2.5">
                    {activeNote.solved_questions.map((q: any, i: number) => (
                      <div key={i} className="p-4 rounded-2xl bg-transparent border border-border space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[11px] font-bold uppercase text-brand-primary bg-brand-primary-soft px-2 py-0.5 rounded-md">
                            {q.year_or_type || `PYQ ${i + 1}`}
                          </span>
                          {q.key_concept && (
                            <span className="text-[10px] text-text-muted font-bold">Concept: {q.key_concept}</span>
                          )}
                        </div>
                        <p className="text-xs font-bold text-text-primary">{q.question}</p>
                        <div className="bg-white p-3 rounded-xl border border-border/60 text-xs text-text-primary font-medium whitespace-pre-line leading-relaxed">
                          <span className="font-bold text-success block mb-1">Step-by-Step AI Solution:</span>
                          {q.step_by_step_solution}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Complete Markdown Document Render */}
              <div className="prose prose-sm max-w-none text-text-primary space-y-4 pt-2 border-t border-border/60">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm, remarkMath]}
                  rehypePlugins={[rehypeKatex]}
                  components={{
                    code({ className, children, ...props }: any) {
                      const match = /language-(\w+)/.exec(className || '')
                      const isMermaid = match && match[1] === 'mermaid'
                      const isInline = !match

                      if (isMermaid) {
                        return <MermaidDiagram chart={String(children).replace(/\n$/, '')} />
                      }
                      if (isInline) {
                        return (
                          <code className="bg-transparent text-brand-primary px-1.5 py-0.5 rounded-md text-xs font-mono font-bold border border-border">
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
                    h1: ({ children }) => <h1 className="text-xl sm:text-2xl font-bold text-text-primary mt-6 mb-3 border-b pb-2 border-border">{children}</h1>,
                    h2: ({ children }) => <h2 className="text-lg font-bold text-text-primary mt-5 mb-2">{children}</h2>,
                    h3: ({ children }) => <h3 className="text-base font-bold text-text-primary mt-4 mb-2">{children}</h3>,
                    p: ({ children }) => <p className="text-xs sm:text-sm text-text-primary leading-relaxed mb-3">{children}</p>,
                    ul: ({ children }) => <ul className="list-disc pl-5 space-y-1 text-xs sm:text-sm text-text-primary mb-3">{children}</ul>,
                    ol: ({ children }) => <ol className="list-decimal pl-5 space-y-1 text-xs sm:text-sm text-text-primary mb-3">{children}</ol>,
                    blockquote: ({ children }) => (
                      <blockquote className="border-l-4 border-brand-primary pl-4 py-1.5 my-3 bg-brand-primary-soft/40 rounded-r-xl text-xs sm:text-sm text-text-primary italic">
                        {children}
                      </blockquote>
                    ),
                    table: ({ children }) => (
                      <div className="overflow-x-auto my-3">
                        <table className="w-full text-xs border-collapse border border-border">{children}</table>
                      </div>
                    ),
                    th: ({ children }) => <th className="border border-border bg-black/5 p-2 font-bold text-left">{children}</th>,
                    td: ({ children }) => <td className="border border-border p-2 text-left">{children}</td>,
                  }}
                >
                  {activeNote.content_markdown}
                </ReactMarkdown>
              </div>

              {/* Bottom Quick Action Bar */}
              <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-6 border-t border-border">
                <button
                  onClick={() => navigate('/quiz/general')}
                  className="btn-primary font-bold text-xs py-3 px-5 rounded-xl flex items-center justify-center gap-2 shadow-xs w-full sm:w-auto cursor-pointer"
                >
                  <Brain size={16} />
                  <span>Quiz Me on this Note</span>
                </button>
                <button
                  onClick={() => navigate('/chat')}
                  className="bg-transparent hover:bg-black/5 text-text-primary border border-border font-bold text-xs py-3 px-5 rounded-xl flex items-center justify-center gap-2 transition-all w-full sm:w-auto cursor-pointer"
                >
                  <Sparkles size={16} className="text-brand-primary" />
                  <span>Ask AI Tutor Questions</span>
                </button>
              </div>
            </div>
          ) : (
            <div className="card p-12 text-center space-y-5 h-full min-h-[600px] flex flex-col items-center justify-center relative overflow-hidden">
              <div className="absolute inset-0 bg-gradient-to-br from-brand-primary-soft/40 to-transparent -z-10" />
              <div className="w-24 h-24 rounded-full bg-white text-brand-primary flex items-center justify-center mx-auto shadow-sm border border-border elevation-1">
                <FileText size={40} className="opacity-80" />
              </div>
              <h3 className="text-2xl font-bold text-text-primary mt-4">No Smart Note Selected</h3>
              <p className="text-sm text-text-secondary max-w-sm mx-auto leading-relaxed">
                Select a chapter material from the presets or upload your own PDF with Previous Year Question papers to generate instant complete notes.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* ─── 3. PRINT VIEW (Full clean layout on print) ─── */}
      {activeNote && (
        <div className="hidden print:block bg-white p-8 text-text-primary">
          <div className="border-b-2 border-[#20201D] pb-3 mb-6 flex justify-between items-start">
            <div>
              <h1 className="text-2xl font-bold">{activeNote.title}</h1>
              <p className="text-xs uppercase font-bold text-brand-primary">Subject: {activeNote.subject} • IndieTutor Exam Notes</p>
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
