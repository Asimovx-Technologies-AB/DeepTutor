import React, { useState } from 'react'
import { FileText, Download, Copy, Check, ChevronDown } from 'lucide-react'

interface StudyNotesCardProps {
  markdown: string
  title?: string
  className?: string
  onOpenViewer?: () => void
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
  onOpenViewer,
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

  const handlePrintPdf = () => {
    setDropdownOpen(false)
    const printWindow = window.open('', '_blank')
    if (printWindow) {
      printWindow.document.write(`
        <!DOCTYPE html>
        <html>
          <head>
            <title>${docTitle}</title>
            <style>
              body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, serif; padding: 40px; color: #111; line-height: 1.6; }
              h1, h2, h3 { color: #000; }
              pre { background: #f4f4f5; padding: 12px; border-radius: 6px; }
              table { width: 100%; border-collapse: collapse; margin: 16px 0; }
              th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
              th { background: #f9f9f9; }
            </style>
          </head>
          <body>
            <pre style="white-space: pre-wrap; font-family: serif; font-size: 15px;">${markdown.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>
          </body>
        </html>
      `)
      printWindow.document.close()
      printWindow.focus()
      setTimeout(() => printWindow.print(), 250)
    }
  }

  return (
    <div
      onClick={(e) => {
        const target = e.target as HTMLElement
        if (target.closest('.export-actions') || target.closest('button')) {
          return
        }
        if (onOpenViewer) onOpenViewer()
      }}
      className={`my-2 p-2.5 px-3.5 rounded-[10px] bg-white border border-slate-200 hover:border-slate-300 shadow-xs hover:shadow-sm transition-all duration-200 flex items-center justify-between gap-3 text-slate-800 ${onOpenViewer ? 'cursor-pointer group' : ''} ${className}`}
      title={onOpenViewer ? 'Click to open study notes in Markdown Viewer' : undefined}
    >
      {/* Left icon & doc info */}
      <div
        className="flex items-center gap-3 min-w-0"
      >
        <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center shrink-0 border border-slate-200/80 transition-transform duration-200 group-hover:scale-105">
          <FileText size={15} className="text-slate-600 group-hover:text-indigo-600 transition-colors" />
        </div>
        <div className="min-w-0">
          <h4 className="text-[13px] font-semibold text-slate-900 truncate tracking-tight group-hover:text-indigo-600 transition-colors">
            {docTitle}
          </h4>
          <p className="text-[11px] text-slate-500 font-medium flex items-center gap-1.5 mt-0.5">
            <span>Document</span>
            <span>·</span>
            <span className="font-semibold text-slate-600">MD</span>
            {onOpenViewer && (
              <>
                <span>·</span>
                <span className="text-indigo-600 font-semibold group-hover:underline">Open viewer →</span>
              </>
            )}
          </p>
        </div>
      </div>

      {/* Right action button */}
      <div className="relative shrink-0 flex items-center export-actions" onClick={(e) => e.stopPropagation()}>
        <div className="inline-flex rounded-lg border border-slate-200 bg-white shadow-2xs overflow-hidden">
          <button
            onClick={handleDownload}
            className="px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 flex items-center gap-1 transition cursor-pointer"
            title="Download study notes as .md file"
          >
            <Download size={12} className="text-slate-500" />
            <span>Download</span>
          </button>

          <button
            onClick={() => setDropdownOpen((prev) => !prev)}
            className="px-1 py-1 border-l border-slate-200 hover:bg-slate-50 text-slate-400 hover:text-slate-600 transition cursor-pointer"
            title="Export options"
          >
            <ChevronDown size={12} />
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
              onClick={handlePrintPdf}
              className="w-full px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 flex items-center gap-2 text-left cursor-pointer"
            >
              <FileText size={13} className="text-slate-400" />
              Print / Save PDF
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
