import { useEffect, useRef, useState, useId, useCallback } from 'react'
import mermaid from 'mermaid'
import { Copy, Check, ZoomIn, ZoomOut, RotateCcw, Maximize2, Minimize2, MessageSquare, X } from 'lucide-react'

mermaid.initialize({
  startOnLoad: false,
  theme: 'base',
  themeVariables: {
    primaryColor: '#FFFFFF',
    primaryTextColor: '#1E293B',
    primaryBorderColor: '#6366F1',
    lineColor: '#6366F1',
    secondaryColor: '#FFFFFF',
    tertiaryColor: '#FFFFFF',
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    fontSize: '13px',
    nodeBorder: '1.5px',
    clusterBkg: 'transparent',
    clusterBorder: '#CBD5E1',
    titleColor: '#475569',
    edgeLabelBackground: '#FFFFFF',
    
    // Mindmap branch theme variables
    git0: '#EEF2FF',
    git1: '#ECFDF5',
    git2: '#F5F3FF',
    git3: '#F0F9FF',
    git4: '#FFFBEB',
    git5: '#FFF1F2',
    git6: '#FDF4FF',
    git7: '#F8FAFC',
    gitBranchLabel0: '#312E81',
    gitBranchLabel1: '#064E3B',
    gitBranchLabel2: '#4C1D95',
    gitBranchLabel3: '#0C4A6E',
    gitBranchLabel4: '#78350F',
    gitBranchLabel5: '#881337',
    gitBranchLabel6: '#701A75',
    gitBranchLabel7: '#1E293B',
  },
  mindmap: {
    padding: 16,
    useMaxWidth: true,
  },
  flowchart: {
    htmlLabels: true,
    curve: 'basis',
    padding: 24,
    nodeSpacing: 60,
    rankSpacing: 85,
    useMaxWidth: true,
  },
  securityLevel: 'loose',
})

/**
 * Universal text wrapper that inserts `<br/>` into long Mermaid node shapes
 * (quoted or unquoted, square, rounded, stadium, diamond, circle).
 */
function wrapMermaidNodeLabels(code: string, maxCharsPerLine: number = 48): string {
  const wrapText = (text: string): string => {
    if (!text || !text.trim()) return text
    // Don't modify if it contains html tags other than simple br
    const lines = text.split(/<br\s*\/?>/i)
    const wrapped: string[] = []

    lines.forEach((line) => {
      const trimmed = line.trim()
      if (trimmed.length <= maxCharsPerLine) {
        wrapped.push(trimmed)
      } else {
        const words = trimmed.split(/\s+/)
        let cur = ''
        words.forEach((w) => {
          if (!cur) {
            cur = w
          } else if ((cur + ' ' + w).length <= maxCharsPerLine) {
            cur += ' ' + w
          } else {
            wrapped.push(cur)
            cur = w
          }
        })
        if (cur) wrapped.push(cur)
      }
    })
    return wrapped.join('<br/>')
  }

  let res = code

  // 1. Stadium nodes: id(["..."]) or id([...])
  res = res.replace(/(\(\["?)([^"\]\n\r]+)("?\]\))/g, (_, p1, content, p3) => {
    return `${p1}${wrapText(content)}${p3}`
  })

  // 2. Square nodes: id["..."] or id[...] (exclude style definitions)
  res = res.replace(/([a-zA-Z0-9_-]+\["??)([^"\]\n\r]+)("??\])/g, (_, p1, content, p3) => {
    return `${p1}${wrapText(content)}${p3}`
  })

  // 3. Rounded nodes: id("...") or id(...)
  res = res.replace(/(?<!subgraph\s+|graph\s+|flowchart\s+)([a-zA-Z0-9_-]+\("??)([^"\)\n\r]+)("??\))/g, (_, p1, content, p3) => {
    return `${p1}${wrapText(content)}${p3}`
  })

  // 4. Diamond nodes: id{"..."} or id{...}
  res = res.replace(/([a-zA-Z0-9_-]+\{"??)([^"\}\n\r]+)("??\})/g, (_, p1, content, p3) => {
    return `${p1}${wrapText(content)}${p3}`
  })

  return res
}

/**
 * Normalizes and sanitizes Mindmap syntax for Mermaid.js:
 * Wraps raw quoted lines and lines with special characters (&, (), :, etc.) in standard [ ... ] brackets.
 */
function sanitizeMindmapCode(code: string): string {
  if (!code.trim().startsWith('mindmap')) return code
  const lines = code.split('\n')
  const sanitized = lines.map((line) => {
    const indentMatch = line.match(/^(\s*)(.*)$/)
    if (!indentMatch) return line
    const indent = indentMatch[1]
    const content = indentMatch[2].trim()
    if (!content || content.startsWith('mindmap') || content.startsWith('root')) {
      return line
    }
    // If content is already enclosed in brackets, e.g. [ ... ], ( ... ), (( ... )), ) ... (, etc.
    if (/^(\[.*\]|\(.*\)|[\]\)\(].*[\]\)\(])$/.test(content)) {
      return line
    }
    // If content starts and ends with quotes: "Decision Trees & Ensembles" -> ["Decision Trees & Ensembles"]
    if (/^"[^"]+"$/.test(content)) {
      return `${indent}[${content}]`
    }
    // If content contains special characters like &, :, (), wrap safely in ["..."]
    if (/[&():,]/.test(content)) {
      const cleanContent = content.replace(/^["']+|["']+$/g, '')
      return `${indent}["${cleanContent}"]`
    }
    return line
  })
  return sanitized.join('\n')
}

interface Props {
  chart: string
  onNodeClick?: (topic: string) => void
}

export default function MermaidDiagram({ chart, onNodeClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [svgContent, setSvgContent] = useState<string>('')
  const [error, setError] = useState<boolean>(false)
  const [copied, setCopied] = useState<boolean>(false)
  const [intrinsicSize, setIntrinsicSize] = useState<{ width: number; height: number }>({ width: 650, height: 420 })
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const [popoverPos, setPopoverPos] = useState<{ x: number; y: number } | null>(null)
  const rawId = useId().replace(/:/g, '')

  // Helper to cleanup Mermaid's injected DOM error elements
  const cleanupMermaidErrorDOM = () => {
    document.querySelectorAll('[id^="dmermaid"], [id^="mermaid-"]').forEach((el) => {
      if (el.parentElement === document.body) {
        el.remove()
      }
    })
  }

  useEffect(() => {
    let isMounted = true
    const renderChart = async () => {
      if (!chart || !chart.trim()) return

      try {
        const uniqueId = `mermaid-${rawId}-${Math.random().toString(36).substring(2, 7)}`
        
        let cleanCode = chart
          .replace(/^```mermaid\s*/i, '')
          .replace(/```$/, '')
          .trim()

        // Normalize unicode arrows and dashes that LLMs sometimes output instead of ASCII '-->'
        cleanCode = cleanCode
          .replace(/[\u27F6\u2192\u2794\u279C\u279D\u279E⟶→➔➜➝➞]/g, '-->')
          .replace(/[\u27F9\u21D2⟹⇒]/g, '==>')
          .replace(/[\u27F5\u2190⟵←]/g, '<--')
          .replace(/--\s*>/g, '-->')
          .replace(/[\u2010\u2013\u2014\u2212]/g, '-')

        if (
          !cleanCode.startsWith('graph') &&
          !cleanCode.startsWith('flowchart') &&
          !cleanCode.startsWith('sequenceDiagram') &&
          !cleanCode.startsWith('classDiagram') &&
          !cleanCode.startsWith('stateDiagram') &&
          !cleanCode.startsWith('erDiagram') &&
          !cleanCode.startsWith('gantt') &&
          !cleanCode.startsWith('pie') &&
          !cleanCode.startsWith('mindmap') &&
          !cleanCode.startsWith('timeline')
        ) {
          cleanCode = `flowchart TD\n${cleanCode}`
        }

        if (cleanCode.startsWith('mindmap')) {
          cleanCode = sanitizeMindmapCode(cleanCode)
        }

        let svgResult = ''
        try {
          const formattedCode = cleanCode.startsWith('mindmap') ? cleanCode : wrapMermaidNodeLabels(cleanCode, 48)
          const res = await mermaid.render(uniqueId, formattedCode)
          svgResult = res.svg
        } catch {
          cleanupMermaidErrorDOM()
          const retryId = `mermaid-retry-${rawId}-${Math.random().toString(36).substring(2, 7)}`
          const res = await mermaid.render(retryId, cleanCode)
          svgResult = res.svg
        }

        if (isMounted && svgResult) {
          // Extract intrinsic dimensions from viewBox
          let vbW = 650
          let vbH = 420
          const vbMatch = svgResult.match(/viewBox=["']\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*["']/i)
          if (vbMatch) {
            vbW = Math.max(80, parseFloat(vbMatch[3]))
            vbH = Math.max(80, parseFloat(vbMatch[4]))
          }
          setIntrinsicSize({ width: vbW, height: vbH })

          // Strip fixed width/height/max-width to allow clean vector scaling
          const enhancedSvg = svgResult.replace(/<svg\s+([^>]+)>/, (match, attrs) => {
            const cleanAttrs = attrs
              .replace(/\s*style=["'][^"']*["']/gi, '')
              .replace(/\s*width=["'][^"']*["']/gi, '')
              .replace(/\s*height=["'][^"']*["']/gi, '')
            return `<svg ${cleanAttrs} style="width: 100%; height: 100%; display: block; margin: 0 auto; overflow: visible; background: transparent;" preserveAspectRatio="xMidYMid meet">`
          })
          setSvgContent(enhancedSvg)
          setError(false)
        }
      } catch (err) {
        console.warn('[Mermaid] Render note:', err)
        cleanupMermaidErrorDOM()
        if (isMounted) {
          setError(true)
        }
      }
    }

    renderChart()
    return () => {
      isMounted = false
      cleanupMermaidErrorDOM()
    }
  }, [chart, rawId])

  const handleCopyCode = (e?: React.MouseEvent) => {
    e?.stopPropagation()
    navigator.clipboard.writeText(chart.replace(/^```mermaid\s*/i, '').replace(/```$/, '').trim())
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleDiagramClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement
    if (target.closest('button, .node-popover')) return
    const nodeEl = target.closest('.mindmap-node, .node, g[class*="section-"]') as HTMLElement | null
    if (nodeEl) {
      const rawText = nodeEl.textContent?.trim() || ''
      const cleanText = rawText.replace(/\s+/g, ' ').trim()
      if (cleanText) {
        setSelectedNode(cleanText)
        const rect = nodeEl.getBoundingClientRect()
        const parentRect = containerRef.current?.getBoundingClientRect()
        if (parentRect) {
          setPopoverPos({
            x: rect.left - parentRect.left + rect.width / 2,
            y: Math.max(10, rect.top - parentRect.top - 10),
          })
        }
      }
    } else {
      setSelectedNode(null)
    }
  }

  if (error) {
    return (
      <div className="my-4 p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs font-mono text-slate-800 overflow-x-auto">
        <div className="text-slate-600 font-semibold mb-1 font-sans">Diagram Source</div>
        <pre>{chart}</pre>
      </div>
    )
  }

  const diagramContent = (
    <div className="relative w-full h-full flex flex-col items-center justify-center">
      {/* Floating Interactive Controls Toolbar */}
      <div className="absolute top-3 right-3 flex items-center gap-1 p-1 rounded-xl bg-white/95 backdrop-blur-sm border border-slate-200/90 shadow-sm z-20">
        <button
          onClick={handleCopyCode}
          title="Copy Diagram Code"
          className="p-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition cursor-pointer"
        >
          {copied ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
        </button>
      </div>

      {/* Interactive Node Action Popover */}
      {selectedNode && popoverPos && (
        <div
          style={{
            left: `${popoverPos.x}px`,
            top: `${popoverPos.y}px`,
            transform: 'translate(-50%, -100%)',
          }}
          className="node-popover absolute z-30 flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-900/95 backdrop-blur-md text-white text-xs font-medium shadow-xl border border-slate-700/60 animate-in fade-in zoom-in-95 duration-150"
        >
          <span className="max-w-[170px] truncate text-slate-100 font-semibold">{selectedNode}</span>
          <div className="h-3 w-px bg-slate-700" />
          {onNodeClick && (
            <button
              onClick={() => {
                onNodeClick(`Explain the concept of ${selectedNode}`)
                setSelectedNode(null)
              }}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium cursor-pointer transition shadow-xs text-[11px]"
              title="Ask DeepTutor to explain this topic"
            >
              <MessageSquare size={12} />
              <span>Ask Tutor</span>
            </button>
          )}
          <button
            onClick={() => {
              navigator.clipboard.writeText(selectedNode)
              setCopied(true)
              setTimeout(() => setCopied(false), 2000)
              setSelectedNode(null)
            }}
            className="p-1 rounded-md hover:bg-slate-800 text-slate-400 hover:text-white transition cursor-pointer"
            title="Copy Topic Name"
          >
            <Copy size={12} />
          </button>
          <button
            onClick={() => setSelectedNode(null)}
            className="p-1 rounded-md hover:bg-slate-800 text-slate-400 hover:text-white transition cursor-pointer"
            title="Close"
          >
            <X size={12} />
          </button>
        </div>
      )}

      {/* Interactive Canvas */}
      <div
        ref={containerRef}
        onClick={handleDiagramClick}
        className="mermaid-wrapper w-full overflow-auto relative rounded-xl"
      >
        <div
          className="flex justify-center min-w-max p-4"
          dangerouslySetInnerHTML={{ __html: svgContent }}
        />
      </div>
    </div>
  )

  return (
    <div className="my-4 w-full flex flex-col items-center justify-center overflow-hidden relative group bg-gradient-to-b from-slate-50/70 via-white to-slate-50/50 rounded-2xl border border-slate-200/80 shadow-xs p-4 sm:p-6 transition-all duration-300 hover:shadow-md hover:border-indigo-100">
      {diagramContent}

      <style>{`
        .mermaid-wrapper svg {
          overflow: visible !important;
          background: transparent !important;
        }

        /* ══════════════════════════════════════════════════════════════════════
           MINDMAP ULTRA-PREMIUM STYLING (VIBRANT BRANCHES, GLOWS, PILL BADGES)
           ══════════════════════════════════════════════════════════════════════ */

        /* ── Mindmap Base Nodes ── */
        .mermaid-wrapper .mindmap-node rect,
        .mermaid-wrapper .mindmap-node path,
        .mermaid-wrapper .mindmap-node polygon,
        .mermaid-wrapper g[class*="section-"] rect,
        .mermaid-wrapper g[class*="section-"] path {
          rx: 12px !important;
          ry: 12px !important;
          stroke-width: 1.75px !important;
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
          cursor: pointer !important;
        }

        .mermaid-wrapper .mindmap-node text,
        .mermaid-wrapper .mindmap-node tspan,
        .mermaid-wrapper g[class*="section-"] text {
          font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
          font-weight: 600 !important;
          font-size: 12.5px !important;
          line-height: 1.3 !important;
          text-anchor: middle !important;
          transition: fill 0.2s ease !important;
        }

        /* ── Root Node: Glowing Indigo / Violet Core Badge ── */
        .mermaid-wrapper .mindmap-node.section-root rect,
        .mermaid-wrapper .mindmap-node.section-root circle,
        .mermaid-wrapper .mindmap-node.section-root path,
        .mermaid-wrapper g.section-root rect,
        .mermaid-wrapper g.section-root circle,
        .mermaid-wrapper g.section-root path {
          fill: #FFFFFF !important;
          stroke: #6366F1 !important;
          stroke-width: 2.5px !important;
          filter: drop-shadow(0 4px 14px rgba(99, 102, 241, 0.22)) !important;
          rx: 20px !important;
          ry: 20px !important;
        }

        .mermaid-wrapper .mindmap-node.section-root text,
        .mermaid-wrapper g.section-root text {
          fill: #312E81 !important;
          font-weight: 700 !important;
          font-size: 13.5px !important;
        }

        /* ── Branch 0: Vibrant Indigo ── */
        .mermaid-wrapper .mindmap-node.section-0 rect,
        .mermaid-wrapper .mindmap-node.section-0 path,
        .mermaid-wrapper g.section-0 rect,
        .mermaid-wrapper g.section-0 path {
          fill: #EEF2FF !important;
          stroke: #6366F1 !important;
          filter: drop-shadow(0 2px 8px rgba(99, 102, 241, 0.12)) !important;
        }
        .mermaid-wrapper .mindmap-node.section-0 text,
        .mermaid-wrapper g.section-0 text {
          fill: #312E81 !important;
        }
        .mermaid-wrapper path.section-edge-0,
        .mermaid-wrapper .section-lines-0 path,
        .mermaid-wrapper line.section-edge-0 {
          stroke: #6366F1 !important;
          stroke-width: 2px !important;
        }

        /* ── Branch 1: Emerald & Mint ── */
        .mermaid-wrapper .mindmap-node.section-1 rect,
        .mermaid-wrapper .mindmap-node.section-1 path,
        .mermaid-wrapper g.section-1 rect,
        .mermaid-wrapper g.section-1 path {
          fill: #ECFDF5 !important;
          stroke: #10B981 !important;
          filter: drop-shadow(0 2px 8px rgba(16, 185, 129, 0.12)) !important;
        }
        .mermaid-wrapper .mindmap-node.section-1 text,
        .mermaid-wrapper g.section-1 text {
          fill: #064E3B !important;
        }
        .mermaid-wrapper path.section-edge-1,
        .mermaid-wrapper .section-lines-1 path,
        .mermaid-wrapper line.section-edge-1 {
          stroke: #10B981 !important;
          stroke-width: 2px !important;
        }

        /* ── Branch 2: Royal Violet & Lavender ── */
        .mermaid-wrapper .mindmap-node.section-2 rect,
        .mermaid-wrapper .mindmap-node.section-2 path,
        .mermaid-wrapper g.section-2 rect,
        .mermaid-wrapper g.section-2 path {
          fill: #F5F3FF !important;
          stroke: #8B5CF6 !important;
          filter: drop-shadow(0 2px 8px rgba(139, 92, 246, 0.12)) !important;
        }
        .mermaid-wrapper .mindmap-node.section-2 text,
        .mermaid-wrapper g.section-2 text {
          fill: #4C1D95 !important;
        }
        .mermaid-wrapper path.section-edge-2,
        .mermaid-wrapper .section-lines-2 path,
        .mermaid-wrapper line.section-edge-2 {
          stroke: #8B5CF6 !important;
          stroke-width: 2px !important;
        }

        /* ── Branch 3: Sky Blue & Cyan ── */
        .mermaid-wrapper .mindmap-node.section-3 rect,
        .mermaid-wrapper .mindmap-node.section-3 path,
        .mermaid-wrapper g.section-3 rect,
        .mermaid-wrapper g.section-3 path {
          fill: #F0F9FF !important;
          stroke: #0EA5E9 !important;
          filter: drop-shadow(0 2px 8px rgba(14, 165, 233, 0.12)) !important;
        }
        .mermaid-wrapper .mindmap-node.section-3 text,
        .mermaid-wrapper g.section-3 text {
          fill: #0C4A6E !important;
        }
        .mermaid-wrapper path.section-edge-3,
        .mermaid-wrapper .section-lines-3 path,
        .mermaid-wrapper line.section-edge-3 {
          stroke: #0EA5E9 !important;
          stroke-width: 2px !important;
        }

        /* ── Branch 4: Amber & Warm Gold ── */
        .mermaid-wrapper .mindmap-node.section-4 rect,
        .mermaid-wrapper .mindmap-node.section-4 path,
        .mermaid-wrapper g.section-4 rect,
        .mermaid-wrapper g.section-4 path {
          fill: #FFFBEB !important;
          stroke: #F59E0B !important;
          filter: drop-shadow(0 2px 8px rgba(245, 158, 11, 0.12)) !important;
        }
        .mermaid-wrapper .mindmap-node.section-4 text,
        .mermaid-wrapper g.section-4 text {
          fill: #78350F !important;
        }
        .mermaid-wrapper path.section-edge-4,
        .mermaid-wrapper .section-lines-4 path,
        .mermaid-wrapper line.section-edge-4 {
          stroke: #F59E0B !important;
          stroke-width: 2px !important;
        }

        /* ── Branch 5: Rose & Coral Pink ── */
        .mermaid-wrapper .mindmap-node.section-5 rect,
        .mermaid-wrapper .mindmap-node.section-5 path,
        .mermaid-wrapper g.section-5 rect,
        .mermaid-wrapper g.section-5 path {
          fill: #FFF1F2 !important;
          stroke: #F43F5E !important;
          filter: drop-shadow(0 2px 8px rgba(244, 63, 94, 0.12)) !important;
        }
        .mermaid-wrapper .mindmap-node.section-5 text,
        .mermaid-wrapper g.section-5 text {
          fill: #881337 !important;
        }
        .mermaid-wrapper path.section-edge-5,
        .mermaid-wrapper .section-lines-5 path,
        .mermaid-wrapper line.section-edge-5 {
          stroke: #F43F5E !important;
          stroke-width: 2px !important;
        }

        /* ── Branch 6: Fuchsia & Magenta ── */
        .mermaid-wrapper .mindmap-node.section-6 rect,
        .mermaid-wrapper .mindmap-node.section-6 path,
        .mermaid-wrapper g.section-6 rect,
        .mermaid-wrapper g.section-6 path {
          fill: #FDF4FF !important;
          stroke: #D946EF !important;
          filter: drop-shadow(0 2px 8px rgba(217, 70, 239, 0.12)) !important;
        }
        .mermaid-wrapper .mindmap-node.section-6 text,
        .mermaid-wrapper g.section-6 text {
          fill: #701A75 !important;
        }
        .mermaid-wrapper path.section-edge-6,
        .mermaid-wrapper .section-lines-6 path,
        .mermaid-wrapper line.section-edge-6 {
          stroke: #D946EF !important;
          stroke-width: 2px !important;
        }

        /* ── Mindmap Node Hover Animation ── */
        .mermaid-wrapper .mindmap-node:hover rect,
        .mermaid-wrapper .mindmap-node:hover path,
        .mermaid-wrapper .mindmap-node:hover circle,
        .mermaid-wrapper g[class*="section-"]:hover rect,
        .mermaid-wrapper g[class*="section-"]:hover path {
          transform: translateY(-2px);
          filter: drop-shadow(0 6px 16px rgba(0, 0, 0, 0.14)) !important;
          stroke-width: 2.25px !important;
        }

        /* ══════════════════════════════════════════════════════════════════════
           FLOWCHART & GRAPH ULTRA-PREMIUM CARD STYLING
           ══════════════════════════════════════════════════════════════════════ */

        /* ── Clusters / Subgraph Boxes: Transparent background with clean soft dashed outline ── */
        .mermaid-wrapper .cluster rect {
          fill: transparent !important;
          stroke: #CBD5E1 !important;
          stroke-width: 1.2px !important;
          stroke-dasharray: 4 4 !important;
          rx: 14px !important;
          ry: 14px !important;
        }

        .mermaid-wrapper .cluster text {
          font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
          font-size: 11.5px !important;
          font-weight: 600 !important;
          fill: #64748B !important;
        }

        /* ── Node Boxes: Clean white card on transparent background ── */
        .mermaid-wrapper .node rect,
        .mermaid-wrapper .node polygon {
          rx: 14px !important;
          ry: 14px !important;
          stroke: #6366F1 !important;
          stroke-width: 1.5px !important;
          fill: #FFFFFF !important;
          filter: drop-shadow(0 2px 8px rgba(99, 102, 241, 0.08)) !important;
          transition: all 0.2s ease !important;
        }

        .mermaid-wrapper .node:hover rect {
          stroke: #4F46E5 !important;
          stroke-width: 2px !important;
          fill: #FFFFFF !important;
          filter: drop-shadow(0 4px 14px rgba(99, 102, 241, 0.16)) !important;
        }

        .mermaid-wrapper .node circle {
          stroke: #6366F1 !important;
          stroke-width: 1.75px !important;
          fill: #FFFFFF !important;
        }

        .mermaid-wrapper .node foreignObject {
          overflow: visible !important;
        }

        .mermaid-wrapper .node foreignObject div {
          display: flex !important;
          flex-direction: column !important;
          align-items: center !important;
          justify-content: center !important;
          text-align: center !important;
          width: 100% !important;
          height: 100% !important;
          padding: 4px 8px !important;
          box-sizing: border-box !important;
          font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
          font-size: 13px !important;
          font-weight: 500 !important;
          line-height: 1.35 !important;
          color: #1E293B !important;
          word-break: normal !important;
          white-space: normal !important;
        }

        .mermaid-wrapper .node text {
          font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
          font-size: 13px !important;
          line-height: 1.35 !important;
          text-anchor: middle !important;
        }

        .mermaid-wrapper .edgePath path {
          stroke: #6366F1 !important;
          stroke-width: 2px !important;
          stroke-linecap: round !important;
          stroke-linejoin: round !important;
        }

        .mermaid-wrapper .marker {
          fill: #6366F1 !important;
          stroke: #6366F1 !important;
        }

        .mermaid-wrapper .edgeLabel {
          background-color: transparent !important;
        }

        .mermaid-wrapper .edgeLabel rect {
          fill: #FFFFFF !important;
          rx: 6px !important;
          ry: 6px !important;
          stroke: #E2E8F0 !important;
          stroke-width: 1px !important;
        }

        .mermaid-wrapper .edgeLabel foreignObject {
          overflow: visible !important;
        }

        .mermaid-wrapper .edgeLabel .label span,
        .mermaid-wrapper .edgeLabel span {
          background-color: #FFFFFF !important;
          padding: 3px 8px !important;
          border-radius: 6px !important;
          font-size: 11px !important;
          font-weight: 500 !important;
          color: #334155 !important;
          border: 1px solid #CBD5E1 !important;
          box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05) !important;
          display: inline-block !important;
          white-space: nowrap !important;
        }

        .mermaid-wrapper .edgeLabel text,
        .mermaid-wrapper .edgeLabel tspan {
          fill: #334155 !important;
          font-size: 11px !important;
          font-weight: 500 !important;
        }
      `}</style>
    </div>
  )
}
