import React, { useState } from 'react'
import { Award, CheckCircle, XCircle, AlertCircle, BarChart3, Copy, Check, ChevronDown, ChevronUp, BookOpen } from 'lucide-react'

interface ExamReportCardProps {
  markdown: string
  className?: string
}

export function isExamReportContent(msgOrContent: any): boolean {
  if (!msgOrContent) return false
  if (typeof msgOrContent === 'string') {
    const trimmed = msgOrContent.trimStart()
    const lower = msgOrContent.toLowerCase()
    return (
      trimmed.startsWith('# 📊 Exam Report') ||
      trimmed.startsWith('# Exam Report') ||
      (lower.includes('exam report:') && lower.includes('overall performance')) ||
      (lower.includes('## overall performance') && lower.includes('accuracy'))
    )
  }
  if (msgOrContent.response_format === 'exam_report' || msgOrContent.type === 'exam_report') {
    return true
  }
  const text = msgOrContent.text || msgOrContent.content || ''
  const trimmed = text.trimStart()
  const lower = text.toLowerCase()
  return (
    trimmed.startsWith('# 📊 Exam Report') ||
    trimmed.startsWith('# Exam Report') ||
    (lower.includes('exam report:') && lower.includes('overall performance')) ||
    (lower.includes('## overall performance') && lower.includes('accuracy'))
  )
}

interface ParsedExamStats {
  title: string
  score: string
  percentage: string
  accuracy: string
  attempted: string
  correct: string
  incorrect: string
  unanswered: string
}

function parseExamStats(markdown: string): ParsedExamStats {
  const titleMatch = markdown.match(/#\s+(?:📊\s*)?Exam Report:\s*(.+)/i)
  const scoreMatch = markdown.match(/Score\*\*:\s*([^\n\r]+)/i)
  const percentMatch = markdown.match(/Percentage\*\*:\s*([^\n\r%]+)%?/i)
  const accuracyMatch = markdown.match(/Accuracy\*\*:\s*([^\n\r%]+)%?/i)
  const attemptedMatch = markdown.match(/Questions Attempted\*\*:\s*([^\n\r]+)/i)
  const correctMatch = markdown.match(/Correct\*\*:\s*(?:✅\s*)?([^\n\r]+)/i)
  const incorrectMatch = markdown.match(/Incorrect\*\*:\s*(?:❌\s*)?([^\n\r]+)/i)
  const unansweredMatch = markdown.match(/Unanswered\*\*:\s*(?:⬜\s*)?([^\n\r]+)/i)

  return {
    title: titleMatch ? titleMatch[1].trim() : 'Assessment Report',
    score: scoreMatch ? scoreMatch[1].trim() : '0',
    percentage: percentMatch ? percentMatch[1].trim() : '0',
    accuracy: accuracyMatch ? accuracyMatch[1].trim() : '0',
    attempted: attemptedMatch ? attemptedMatch[1].trim() : '0',
    correct: correctMatch ? correctMatch[1].trim() : '0',
    incorrect: incorrectMatch ? incorrectMatch[1].trim() : '0',
    unanswered: unansweredMatch ? unansweredMatch[1].trim() : '0',
  }
}

export default function ExamReportCard({ markdown, className = '' }: ExamReportCardProps) {
  const [copied, setCopied] = useState(false)
  const [showDetails, setShowDetails] = useState(false)

  const stats = parseExamStats(markdown)
  const numericPercentage = parseFloat(stats.percentage) || 0

  let badgeColor = 'bg-amber-100 text-amber-800 border-amber-300'
  let badgeLabel = 'Developing'
  if (numericPercentage >= 85) {
    badgeColor = 'bg-emerald-100 text-emerald-800 border-emerald-300'
    badgeLabel = 'Advanced Mastery'
  } else if (numericPercentage >= 70) {
    badgeColor = 'bg-blue-100 text-blue-800 border-blue-300'
    badgeLabel = 'Proficient'
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(markdown)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className={`rounded-2xl border border-indigo-200 bg-gradient-to-br from-white via-indigo-50/20 to-blue-50/30 p-5 shadow-md overflow-hidden ${className}`}>
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-indigo-100">
        <div className="flex items-center gap-2.5">
          <div className="w-10 h-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center shadow-sm">
            <Award size={22} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-gray-900 text-base sm:text-lg">
                Exam Report: {stats.title}
              </h3>
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${badgeColor}`}>
                {badgeLabel}
              </span>
            </div>
            <p className="text-xs text-gray-500">Comprehensive Performance Assessment</p>
          </div>
        </div>

        <button
          onClick={handleCopy}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 text-xs font-medium text-gray-700 transition shadow-xs"
          title="Copy Report Markdown"
        >
          {copied ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
          <span>{copied ? 'Copied!' : 'Copy'}</span>
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 my-4">
        {/* Score */}
        <div className="rounded-xl border border-indigo-100 bg-white p-3 shadow-2xs text-center">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">Score</span>
          <div className="text-xl font-bold text-indigo-700 mt-0.5">{stats.score}</div>
          <span className="text-[10px] text-gray-400">Total Marks</span>
        </div>

        {/* Percentage */}
        <div className="rounded-xl border border-indigo-100 bg-white p-3 shadow-2xs text-center">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">Percentage</span>
          <div className="text-xl font-bold text-gray-800 mt-0.5">{stats.percentage}%</div>
          <div className="w-full bg-gray-100 h-1.5 rounded-full mt-1.5 overflow-hidden">
            <div
              className="bg-indigo-600 h-full rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, Math.max(0, numericPercentage))}%` }}
            />
          </div>
        </div>

        {/* Accuracy */}
        <div className="rounded-xl border border-indigo-100 bg-white p-3 shadow-2xs text-center">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">Accuracy</span>
          <div className="text-xl font-bold text-gray-800 mt-0.5">{stats.accuracy}%</div>
          <span className="text-[10px] text-gray-400">On Attempted</span>
        </div>

        {/* Attempted */}
        <div className="rounded-xl border border-indigo-100 bg-white p-3 shadow-2xs text-center">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">Attempted</span>
          <div className="text-xl font-bold text-gray-800 mt-0.5">{stats.attempted}</div>
          <span className="text-[10px] text-gray-400">Questions</span>
        </div>
      </div>

      {/* Answer Distribution Pills */}
      <div className="flex flex-wrap items-center gap-2 p-3 rounded-xl bg-indigo-50/50 border border-indigo-100/60 mb-2">
        <div className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200/60 px-3 py-1 rounded-lg">
          <CheckCircle size={14} className="text-emerald-600" />
          <span>Correct: {stats.correct}</span>
        </div>
        <div className="inline-flex items-center gap-1.5 text-xs font-semibold text-rose-700 bg-rose-50 border border-rose-200/60 px-3 py-1 rounded-lg">
          <XCircle size={14} className="text-rose-600" />
          <span>Incorrect: {stats.incorrect}</span>
        </div>
        <div className="inline-flex items-center gap-1.5 text-xs font-semibold text-amber-700 bg-amber-50 border border-amber-200/60 px-3 py-1 rounded-lg">
          <AlertCircle size={14} className="text-amber-600" />
          <span>Unanswered: {stats.unanswered}</span>
        </div>
      </div>

      {/* Toggle Details Action */}
      <div className="mt-2 text-center">
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-800 transition py-1"
        >
          <span>{showDetails ? 'Hide Detailed Analysis' : 'Show Full Breakdown & Revision Plan'}</span>
          {showDetails ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {/* Collapsible Details Body */}
      {showDetails && (
        <div className="mt-3 pt-3 border-t border-indigo-100/80 space-y-3 text-xs text-gray-700">
          <div className="flex items-center gap-1.5 font-semibold text-indigo-900 mb-1">
            <BookOpen size={14} className="text-indigo-600" />
            <span>Detailed Analysis & Feedback</span>
          </div>
          <p className="text-gray-600 leading-relaxed">
            Scroll down in the message response below to review the question-by-question breakdown,
            topic-wise mastery stats, and tailored revision recommendations.
          </p>
        </div>
      )}
    </div>
  )
}
