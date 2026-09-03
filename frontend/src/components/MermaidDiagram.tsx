import { useEffect, useRef, useState, useId } from 'react'
import mermaid from 'mermaid'
import { Copy, Check } from 'lucide-react'

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
    fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
    fontSize: '12.5px',
    nodeBorder: '1.5px',
    clusterBkg: 'transparent',
    clusterBorder: '#CBD5E1',
    titleColor: '#64748B',
    edgeLabelBackground: '#FFFFFF',
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
 * Universal text wrapper that inserts `<br/>` into all Mermaid node shapes
 * (quoted or unquoted, square, rounded, stadium, diamond, circle).
 */
function wrapMermaidNodeLabels(code: string, maxCharsPerLine: number = 28): string {
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

interface Props {
  chart: string
}

export default function MermaidDiagram({ chart }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [svgContent, setSvgContent] = useState<string>('')
  const [error, setError] = useState<boolean>(false)
  const [copied, setCopied] = useState<boolean>(false)
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

        let svgResult = ''
        try {
          const wrappedCode = wrapMermaidNodeLabels(cleanCode, 26)
          const res = await mermaid.render(uniqueId, wrappedCode)
          svgResult = res.svg
        } catch {
          cleanupMermaidErrorDOM()
          const retryId = `mermaid-retry-${rawId}-${Math.random().toString(36).substring(2, 7)}`
          const res = await mermaid.render(retryId, cleanCode)
          svgResult = res.svg
        }

        if (isMounted && svgResult) {
          const enhancedSvg = svgResult.replace(/<svg\s+([^>]+)>/, (match, attrs) => {
            return `<svg ${attrs} style="max-width: 100%; height: auto; display: block; margin: 0 auto; overflow: visible; background: transparent;">`
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

  const handleCopyCode = () => {
    navigator.clipboard.writeText(chart.replace(/^```mermaid\s*/i, '').replace(/```$/, '').trim())
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (error) {
    return (
      <div className="my-4 p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs font-mono text-slate-800 overflow-x-auto">
        <div className="text-slate-600 font-semibold mb-1 font-sans">Diagram Source</div>
        <pre>{chart}</pre>
      </div>
    )
  }

  return (
    <div className="my-4 w-full flex items-center justify-center overflow-x-auto relative group bg-transparent py-2">
      {/* Subtle Copy Button in corner on hover */}
      <div className="absolute top-0 right-0 opacity-0 group-hover:opacity-100 transition-opacity z-10">
        <button
          onClick={handleCopyCode}
          title="Copy Diagram Code"
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white hover:bg-slate-50 border border-slate-200 text-xs font-medium text-slate-600 hover:text-slate-900 shadow-xs cursor-pointer transition"
        >
          {copied ? (
            <>
              <Check size={13} className="text-emerald-600" />
              <span className="text-emerald-700 text-xs font-medium">Copied</span>
            </>
          ) : (
            <>
              <Copy size={13} />
              <span className="text-xs">Copy</span>
            </>
          )}
        </button>
      </div>

      {/* Pure Seamless Flowchart SVG */}
      <div
        ref={containerRef}
        className="mermaid-wrapper w-full flex items-center justify-center select-none overflow-x-auto"
        dangerouslySetInnerHTML={{ __html: svgContent }}
      />

      <style>{`
        .mermaid-wrapper svg {
          overflow: visible !important;
          background: transparent !important;
        }

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
          font-size: 12.5px !important;
          font-weight: 500 !important;
          line-height: 1.35 !important;
          color: #1E293B !important;
          word-break: normal !important;
          white-space: normal !important;
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
