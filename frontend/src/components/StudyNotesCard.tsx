import React, { useState } from 'react'
import { FileText, Download, Copy, Check, ChevronDown } from 'lucide-react'

interface StudyNotesCardProps {
  markdown: string
  title?: string
  className?: string
}

export function extractDocTitle(markdown: string): string {
  if (!markdown) return ''
  const match = markdown.match(/^#\s+(.+)$/m)
  if (match && match[1]) {
    return match[1].replace(/#.*$/, '').trim()
  }
  return ''
}

export function downloadMarkdownFile(content: string, title?: string) {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  const baseName = (title || 'study_notes')
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '')
  link.href = url
  link.download = `${baseName || 'study_notes'}.md`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

export const StudyNotesCard: React.FC<StudyNotesCardProps> = ({
  markdown,
  title,
  className = '',
}) => {
  const [copied, setCopied] = useState(false)
  const [dropdownOpen, setDropdownOpen] = useState(false)

  const docTitle = title || extractDocTitle(markdown) || 'Study Notes'

  const handleDownload = () => {
    downloadMarkdownFile(markdown, docTitle)
    setDropdownOpen(false)
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(markdown)
    setCopied(true)
    setDropdownOpen(false)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div
      className={`my-3 p-3.5 rounded-2xl bg-white border border-slate-200/90 shadow-xs flex items-center justify-between gap-3 text-slate-800 ${className}`}
    >
      {/* Left icon & doc info */}
      <div className="flex items-center gap-3.5 min-w-0">
        <div className="w-11 h-11 rounded-xl bg-slate-100 flex items-center justify-center shrink-0 border border-slate-200/60 shadow-2xs">
          <FileText size={20} className="text-slate-600" />
        </div>
        <div className="min-w-0">
          <h4 className="text-sm font-semibold text-slate-900 truncate tracking-tight">
            {docTitle}
          </h4>
          <p className="text-xs text-slate-400 font-medium flex items-center gap-1.5 mt-0.5">
            <span>Document</span>
            <span>·</span>
            <span className="font-semibold text-slate-500">MD</span>
          </p>
        </div>
      </div>

      {/* Right action button */}
      <div className="relative shrink-0 flex items-center">
        <div className="inline-flex rounded-xl border border-slate-200 bg-white shadow-2xs overflow-hidden">
          <button
            onClick={handleDownload}
            className="px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 flex items-center gap-1.5 transition cursor-pointer"
            title="Download study notes as .md file"
          >
            <Download size={13} className="text-slate-500" />
            <span>Download</span>
          </button>

          <button
            onClick={() => setDropdownOpen((prev) => !prev)}
            className="px-1.5 py-1.5 border-l border-slate-200 hover:bg-slate-50 text-slate-400 hover:text-slate-600 transition cursor-pointer"
            title="More export options"
          >
            <ChevronDown size={13} />
          </button>
        </div>

        {dropdownOpen && (
          <div className="absolute right-0 top-full mt-1.5 w-44 rounded-xl bg-white border border-slate-200 shadow-lg py-1 z-30 animate-in fade-in zoom-in-95 duration-100">
            <button
              onClick={handleDownload}
              className="w-full px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 flex items-center gap-2 text-left cursor-pointer"
            >
              <Download size={13} className="text-slate-400" />
              Download .md
            </button>
            <button
              onClick={handleCopy}
              className="w-full px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 flex items-center gap-2 text-left cursor-pointer"
            >
              {copied ? (
                <>
                  <Check size={13} className="text-emerald-600" />
                  <span className="text-emerald-600">Copied!</span>
                </>
              ) : (
                <>
                  <Copy size={13} className="text-slate-400" />
                  Copy Markdown
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default StudyNotesCard
