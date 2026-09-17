import React, { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, FileText, CheckCircle2, AlertCircle, XCircle, Loader2, Sparkles } from 'lucide-react'
import { questionPapersApi } from '../services/api'

interface DocumentItem {
  id?: string
  filename?: string
  document_name?: string
}

interface QuestionPaperValidatorModalProps {
  isOpen: boolean
  onClose: () => void
  sessionDocuments: DocumentItem[]
  onNotesGenerated: (markdown: string) => void
}

interface ValidatedQuestion {
  question_id: string
  status: 'SUPPORTED' | 'PARTIALLY_SUPPORTED' | 'NOT_SUPPORTED'
  confidence: number
  evidence_summary: string
}

interface ExtractedQuestion {
  id: string
  question_text: string
  marks?: number
  question_type?: string
  cognitive_level?: string
}

export default function QuestionPaperValidatorModal({
  isOpen,
  onClose,
  sessionDocuments,
  onNotesGenerated
}: QuestionPaperValidatorModalProps) {
  const [questionPaperId, setQuestionPaperId] = useState<string>('')
  const [studyMaterialId, setStudyMaterialId] = useState<string>('')
  const [isValidating, setIsValidating] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  
  const [extractedQuestions, setExtractedQuestions] = useState<ExtractedQuestion[]>([])
  const [validationResults, setValidationResults] = useState<ValidatedQuestion[]>([])
  const [error, setError] = useState<string | null>(null)

  // Auto-select if there are only 2 documents
  useEffect(() => {
    if (isOpen && sessionDocuments.length >= 2 && !questionPaperId && !studyMaterialId) {
      // Try to guess based on filename
      const qp = sessionDocuments.find(d => (d.filename || d.document_name || '').toLowerCase().includes('question') || (d.filename || d.document_name || '').toLowerCase().includes('paper'))
      const sm = sessionDocuments.find(d => d !== qp)
      
      if (qp && sm) {
        setQuestionPaperId(qp.id || qp.filename || '')
        setStudyMaterialId(sm.id || sm.filename || '')
      }
    }
  }, [isOpen, sessionDocuments, questionPaperId, studyMaterialId])

  useEffect(() => {
    if (!isOpen) {
      setValidationResults([])
      setExtractedQuestions([])
      setError(null)
    }
  }, [isOpen])

  const handleValidate = async () => {
    if (!questionPaperId || !studyMaterialId) {
      setError("Please select both a Question Paper and Study Material.")
      return
    }
    
    setIsValidating(true)
    setError(null)
    
    try {
      // 1. Fetch extracted questions first
      try {
        const qRes = await questionPapersApi.getExtractedQuestions(questionPaperId)
        if (qRes.data && qRes.data.questions) {
          setExtractedQuestions(qRes.data.questions)
        }
      } catch (err: any) {
        console.warn("Could not fetch extracted questions immediately", err)
      }

      // 2. Run Validation
      const res = await questionPapersApi.validatePaper(questionPaperId, studyMaterialId)
      if (res.data && res.data.results) {
        setValidationResults(res.data.results)
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "Failed to validate question paper.")
    } finally {
      setIsValidating(false)
    }
  }

  const handleGenerateNotes = async () => {
    if (!questionPaperId || !studyMaterialId) return
    setIsGenerating(true)
    setError(null)
    try {
      const res = await questionPapersApi.generateNotes(questionPaperId, studyMaterialId)
      if (res.data && res.data.study_notes) {
        onNotesGenerated(res.data.study_notes)
        onClose()
      } else {
        setError("Failed to generate notes: No output from server.")
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "Failed to generate study notes.")
    } finally {
      setIsGenerating(false)
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'SUPPORTED':
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-[10px] font-bold"><CheckCircle2 size={12} /> SUPPORTED</span>
      case 'PARTIALLY_SUPPORTED':
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 text-[10px] font-bold"><AlertCircle size={12} /> PARTIAL</span>
      case 'NOT_SUPPORTED':
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-100 text-red-700 text-[10px] font-bold"><XCircle size={12} /> UNSUPPORTED</span>
      default:
        return null
    }
  }

  if (!isOpen) return null

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 10 }}
          className="w-full max-w-3xl bg-white rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh]"
        >
          {/* Header */}
          <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-indigo-100 text-indigo-600 flex items-center justify-center">
                <FileText size={20} />
              </div>
              <div>
                <h2 className="text-lg font-bold text-slate-800 leading-tight">Question Paper Validator</h2>
                <p className="text-xs text-slate-500 font-medium">Map exam questions to your study material</p>
              </div>
            </div>
            <button onClick={onClose} className="p-2 rounded-full hover:bg-slate-200/50 text-slate-400 hover:text-slate-600 transition">
              <X size={18} />
            </button>
          </div>

          {/* Body */}
          <div className="p-6 overflow-y-auto flex-1">
            {error && (
              <div className="mb-6 p-4 rounded-xl bg-red-50 text-red-700 text-sm border border-red-200">
                {error}
              </div>
            )}

            <div className="grid grid-cols-2 gap-6 mb-8">
              {/* Selectors */}
              <div className="space-y-2">
                <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">Select Question Paper</label>
                <select
                  value={questionPaperId}
                  onChange={(e) => setQuestionPaperId(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-sm focus:outline-none focus:border-indigo-500 focus:bg-white transition"
                >
                  <option value="">-- Select Document --</option>
                  {sessionDocuments.map(d => (
                    <option key={d.id || d.filename} value={d.id || d.filename}>
                      {d.document_name || d.filename || d.id}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">Select Study Material</label>
                <select
                  value={studyMaterialId}
                  onChange={(e) => setStudyMaterialId(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-sm focus:outline-none focus:border-indigo-500 focus:bg-white transition"
                >
                  <option value="">-- Select Document --</option>
                  {sessionDocuments.map(d => (
                    <option key={d.id || d.filename} value={d.id || d.filename}>
                      {d.document_name || d.filename || d.id}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Validation Results */}
            {validationResults.length > 0 && extractedQuestions.length > 0 && (
              <div className="space-y-4">
                <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
                  Validation Results
                  <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 text-xs">{validationResults.length} Questions</span>
                </h3>
                
                <div className="space-y-3">
                  {extractedQuestions.map((q, i) => {
                    const validation = validationResults.find(v => v.question_id === q.id)
                    return (
                      <div key={q.id} className="p-4 rounded-2xl border border-slate-200 bg-white shadow-sm flex flex-col gap-2">
                        <div className="flex items-start justify-between gap-4">
                          <p className="text-sm text-slate-800 font-medium leading-relaxed">
                            <span className="font-bold text-indigo-600 mr-2">Q{i+1}.</span>
                            {q.question_text}
                          </p>
                          <div className="shrink-0 flex flex-col items-end gap-1">
                            {validation ? getStatusBadge(validation.status) : <span className="text-[10px] text-slate-400 font-bold">UNVERIFIED</span>}
                            {q.marks && <span className="text-[10px] text-slate-500 font-semibold">{q.marks} Marks</span>}
                          </div>
                        </div>
                        {validation && validation.evidence_summary && (
                          <div className="mt-2 p-3 rounded-xl bg-slate-50 border border-slate-100 text-xs text-slate-600">
                            <strong>Evidence:</strong> {validation.evidence_summary}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {validationResults.length === 0 && !isValidating && (
              <div className="py-12 text-center text-slate-400">
                <FileText size={32} className="mx-auto mb-3 opacity-20" />
                <p className="text-sm">Select documents and click Validate to begin.</p>
              </div>
            )}

            {isValidating && (
              <div className="py-12 text-center text-slate-500 flex flex-col items-center">
                <Loader2 size={32} className="animate-spin mb-3 text-indigo-500" />
                <p className="text-sm font-medium">Cross-referencing questions with study material...</p>
                <p className="text-xs mt-1 text-slate-400">This may take a minute.</p>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-6 py-4 border-t border-slate-100 bg-slate-50 flex items-center justify-between">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-slate-600 hover:bg-slate-200/50 font-bold text-sm transition"
            >
              Cancel
            </button>
            
            <div className="flex items-center gap-3">
              <button
                onClick={handleValidate}
                disabled={isValidating || isGenerating || !questionPaperId || !studyMaterialId}
                className="px-5 py-2.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 font-bold text-sm transition disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
              >
                Validate Paper
              </button>
              
              <button
                onClick={handleGenerateNotes}
                disabled={isValidating || isGenerating || validationResults.length === 0}
                className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-sm transition disabled:opacity-50 disabled:cursor-not-allowed shadow-md flex items-center gap-2"
              >
                {isGenerating ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
                Generate Study Notes
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  )
}
