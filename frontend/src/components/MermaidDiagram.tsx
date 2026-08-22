import { useEffect, useRef, useState, useId } from 'react'
import { createPortal } from 'react-dom'
import mermaid from 'mermaid'
import { ZoomIn, ZoomOut, RotateCcw, Maximize2, Copy, Check, Sparkles, ArrowLeft } from 'lucide-react'

mermaid.initialize({
  startOnLoad: false,
  theme: 'base',
  themeVariables: {
    primaryColor: '#FFFFFF',
    primaryTextColor: '#1F2937',
    primaryBorderColor: '#FB923C',
    lineColor: '#EA580C',
    secondaryColor: '#FFF7ED',
    tertiaryColor: '#FFFFFF',
    fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
    fontSize: '13px',
    nodeBorder: '1.75px',
    clusterBkg: '#FAF8F3',
    clusterBorder: '#E5E7EB',
    titleColor: '#1F2937',
    edgeLabelBackground: '#FFFFFF',
  },
  flowchart: {
    htmlLabels: true,
    curve: 'basis',
    padding: 24,
    nodeSpacing: 55,
    rankSpacing: 55,
    useMaxWidth: true,
  },
  securityLevel: 'loose',
})

/**
 * Safely wraps long text inside Mermaid node labels with `<br/>`
 */
function wrapMermaidNodeLabels(code: string, maxCharsPerLine: number = 36): string {
  // Only target quoted node labels ["..."] to avoid breaking subgraphs or shape definitions
  return code.replace(/(\["|\[")([^"\]\n]+)("\])/g, (match, prefix, content, suffix) => {
    if (!content || !content.trim()) return match

    const existingLines = content.split(/<br\s*\/?>/i)
    const newLines: string[] = []

    existingLines.forEach((line: string) => {
      const trimmed = line.trim()
      if (trimmed.length <= maxCharsPerLine) {
        newLines.push(trimmed)
      } else {
        const words = trimmed.split(/\s+/)
        let curLine = ''
        words.forEach((w: string) => {
          if (!curLine) {
            curLine = w
          } else if ((curLine + ' ' + w).length <= maxCharsPerLine) {
            curLine += ' ' + w
          } else {
            newLines.push(curLine)
            curLine = w
          }
        })
        if (curLine) {
          newLines.push(curLine)
        }
      }
    })

    return `${prefix}${newLines.join('<br/>')}${suffix}`
  })
}

interface Props {
  chart: string
}

export default function MermaidDiagram({ chart }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const fullscreenContainerRef = useRef<HTMLDivElement>(null)
  const cardRef = useRef<HTMLDivElement>(null)
  const [svgContent, setSvgContent] = useState<string>('')
  const [error, setError] = useState<boolean>(false)
  const [zoom, setZoom] = useState<number>(1)
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false)
  const [copied, setCopied] = useState<boolean>(false)
  const rawId = useId().replace(/:/g, '')

  // Handle ESC key to exit fullscreen
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isFullscreen) {
        setIsFullscreen(false)
        setZoom(1)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isFullscreen])

  // Helper to cleanup Mermaid's injected DOM error elements
  const cleanupMermaidErrorDOM = () => {
    document.querySelectorAll('[id^="dmermaid"], [id^="mermaid-"]').forEach((el) => {
      if (el.parentElement === document.body) {
        el.remove()
      }
    })
  }

  // Render Mermaid SVG with auto-wrapping
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

        // Try rendering with wrapped labels first, fallback to raw cleanCode
        let svgResult = ''
        try {
          const wrappedCode = wrapMermaidNodeLabels(cleanCode, 36)
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
            return `<svg ${attrs} style="max-width: 100%; height: auto; display: block; margin: 0 auto; overflow: visible;">`
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

  const handleZoomIn = () => setZoom((prev) => Math.min(prev + 0.15, 2.5))
  const handleZoomOut = () => setZoom((prev) => Math.max(prev - 0.15, 0.4))
  const handleResetZoom = () => setZoom(1)

  const handleCopyCode = () => {
    navigator.clipboard.writeText(chart.replace(/^```mermaid\s*/i, '').replace(/```$/, '').trim())
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleBackToChat = () => {
    setIsFullscreen(false)
    setZoom(1)
    setTimeout(() => {
      if (cardRef.current) {
        cardRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    }, 60)
  }

  if (error) {
    return (
      <div className="my-3 p-4 rounded-2xl bg-amber-50/80 border border-amber-200 text-xs font-mono text-amber-900 overflow-x-auto shadow-2xs">
        <div className="flex items-center gap-1.5 text-amber-800 font-semibold mb-1.5 font-sans">
          <span>Flowchart Source</span>
        </div>
        <pre>{chart}</pre>
      </div>
    )
  }

  return (
    <>
      {/* ─── Standard Inline Flowchart Card ─── */}
      <div
        ref={cardRef}
        className="my-4 rounded-3xl border border-[#E7E1D8] bg-gradient-to-b from-[#FFFDF9] to-[#FAF7F2] shadow-sm overflow-hidden relative"
      >
        {/* Top Header Bar */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-white/90 backdrop-blur-xs border-b border-[#EBE5DC]">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-lg bg-orange-100 flex items-center justify-center text-orange-600">
              <Sparkles size={13} />
            </div>
            <span className="text-xs font-bold text-[#20201D] tracking-wide">Interactive Flowchart</span>
          </div>

          {/* Toolbar Controls */}
          <div className="flex items-center gap-1.5">
            <button
              onClick={handleZoomOut}
              title="Zoom Out"
              className="p-1.5 rounded-lg hover:bg-orange-50 text-gray-600 hover:text-orange-600 transition-colors cursor-pointer"
            >
              <ZoomOut size={14} />
            </button>
            <span className="text-[11px] font-mono text-gray-500 min-w-[34px] text-center select-none font-bold">
              {Math.round(zoom * 100)}%
            </span>
            <button
              onClick={handleZoomIn}
              title="Zoom In"
              className="p-1.5 rounded-lg hover:bg-orange-50 text-gray-600 hover:text-orange-600 transition-colors cursor-pointer"
            >
              <ZoomIn size={14} />
            </button>
            <button
              onClick={handleResetZoom}
              title="Reset Zoom"
              className="p-1.5 rounded-lg hover:bg-orange-50 text-gray-600 hover:text-orange-600 transition-colors ml-0.5 cursor-pointer"
            >
              <RotateCcw size={13} />
            </button>

            <div className="h-3.5 w-px bg-gray-200 mx-1" />

            <button
              onClick={handleCopyCode}
              title="Copy Diagram Code"
              className="p-1.5 rounded-lg hover:bg-orange-50 text-gray-600 hover:text-orange-600 transition-colors cursor-pointer"
            >
              {copied ? <Check size={14} className="text-green-600" /> : <Copy size={14} />}
            </button>

            <button
              onClick={() => {
                setIsFullscreen(true)
                setZoom(1)
              }}
              title="Expand Fullscreen Modal"
              className="flex items-center gap-1 px-2.5 py-1 rounded-xl bg-orange-50 hover:bg-orange-100 text-orange-700 text-xs font-bold transition-all border border-orange-200/80 shadow-2xs cursor-pointer ml-1"
            >
              <Maximize2 size={12} />
              <span>Expand</span>
            </button>
          </div>
        </div>

        {/* Inline Diagram Canvas */}
        <div className="p-6 overflow-auto flex items-center justify-center select-none max-h-[560px]">
          <div
            ref={containerRef}
            className="mermaid-wrapper transition-transform duration-200 ease-out origin-center"
            style={{ transform: `scale(${zoom})` }}
            dangerouslySetInnerHTML={{ __html: svgContent }}
          />
        </div>
      </div>

      {/* ─── Fullscreen High-Z Modal Portal (Directly on document.body) ─── */}
      {isFullscreen &&
        createPortal(
          <div className="fixed inset-0 z-[99999] bg-black/50 backdrop-blur-xs flex items-center justify-center p-3 sm:p-6 animate-in fade-in duration-200">
            <div className="bg-[#FAF8F3] w-full max-w-7xl h-[92vh] rounded-3xl border-2 border-orange-300 shadow-2xl flex flex-col overflow-hidden relative">
              {/* Modal Header Bar */}
              <div className="flex items-center justify-between px-6 py-3.5 bg-white/95 backdrop-blur-md border-b border-[#EBE5DC] z-10 shadow-2xs">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-xl bg-orange-100 flex items-center justify-center text-orange-600">
                    <Sparkles size={16} />
                  </div>
                  <div>
                    <h3 className="text-sm font-black text-[#20201D]">Interactive Visual Flowchart</h3>
                    <p className="text-[11px] text-gray-500 font-medium">Use zoom controls or scroll to explore steps</p>
                  </div>
                </div>

                {/* Right Controls + Top-Right "Back to Chat" Button */}
                <div className="flex items-center gap-2">
                  <div className="flex items-center gap-1 bg-gray-50 border border-gray-200 rounded-xl p-1 mr-2">
                    <button
                      onClick={handleZoomOut}
                      title="Zoom Out"
                      className="p-1.5 rounded-lg hover:bg-white text-gray-700 hover:text-orange-600 transition-colors cursor-pointer"
                    >
                      <ZoomOut size={15} />
                    </button>
                    <span className="text-xs font-mono text-gray-600 min-w-[40px] text-center select-none font-bold">
                      {Math.round(zoom * 100)}%
                    </span>
                    <button
                      onClick={handleZoomIn}
                      title="Zoom In"
                      className="p-1.5 rounded-lg hover:bg-white text-gray-700 hover:text-orange-600 transition-colors cursor-pointer"
                    >
                      <ZoomIn size={15} />
                    </button>
                    <button
                      onClick={handleResetZoom}
                      title="Reset Zoom"
                      className="p-1.5 rounded-lg hover:bg-white text-gray-700 hover:text-orange-600 transition-colors cursor-pointer"
                    >
                      <RotateCcw size={14} />
                    </button>
                  </div>

                  <button
                    onClick={handleCopyCode}
                    title="Copy Code"
                    className="p-2 rounded-xl border border-gray-200 bg-white hover:bg-orange-50 text-gray-700 hover:text-orange-600 transition-colors cursor-pointer"
                  >
                    {copied ? <Check size={16} className="text-green-600" /> : <Copy size={16} />}
                  </button>

                  {/* Top-Right "Back to Chat" Button */}
                  <button
                    onClick={handleBackToChat}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-700 text-white font-extrabold text-xs shadow-md hover:shadow-lg transition-all cursor-pointer ml-1"
                    title="Close and return to chat (Esc)"
                  >
                    <ArrowLeft size={15} />
                    <span>Back to Chat</span>
                  </button>
                </div>
              </div>

              {/* Modal Fullscreen Canvas with Aesthetic Dot-Grid */}
              <div
                className="flex-1 min-h-0 p-8 overflow-auto flex items-center justify-center select-none"
                style={{
                  backgroundColor: '#FAF8F3',
                  backgroundImage: 'radial-gradient(#E8E2D8 1.2px, transparent 1.2px)',
                  backgroundSize: '24px 24px',
                }}
              >
                <div
                  ref={fullscreenContainerRef}
                  className="mermaid-wrapper transition-transform duration-200 ease-out origin-center"
                  style={{ transform: `scale(${zoom})` }}
                  dangerouslySetInnerHTML={{ __html: svgContent }}
                />
              </div>
            </div>
          </div>,
          document.body
        )}

      {/* Dynamic Aesthetic Node & Centered Text Styling */}
      <style>{`
        .mermaid-wrapper svg {
          overflow: visible !important;
        }

        /* ── Dynamic Aesthetic Card Nodes ── */
        .mermaid-wrapper .node rect,
        .mermaid-wrapper .node polygon {
          rx: 16px !important;
          ry: 16px !important;
          stroke: #FB923C !important;
          stroke-width: 1.75px !important;
          fill: #FFFFFF !important;
          filter: drop-shadow(0 4px 14px rgba(249, 115, 22, 0.12)) !important;
          transition: all 0.25s ease !important;
        }

        .mermaid-wrapper .node:hover rect {
          stroke: #EA580C !important;
          stroke-width: 2.25px !important;
          filter: drop-shadow(0 8px 22px rgba(234, 88, 12, 0.22)) !important;
          fill: #FFFDF9 !important;
        }

        .mermaid-wrapper .node circle {
          stroke: #FB923C !important;
          stroke-width: 2px !important;
          fill: #FFF7ED !important;
        }

        .mermaid-wrapper .node foreignObject {
          overflow: visible !important;
        }

        /* Perfectly Centered Text Content */
        .mermaid-wrapper .node foreignObject div {
          display: flex !important;
          flex-direction: column !important;
          align-items: center !important;
          justify-content: center !important;
          text-align: center !important;
          width: 100% !important;
          height: 100% !important;
          padding: 8px 14px !important;
          box-sizing: border-box !important;
          font-size: 12.5px !important;
          font-weight: 500 !important;
          line-height: 1.45 !important;
          color: #1F2937 !important;
          word-break: break-word !important;
        }

        /* ── Connectors & Arrows ── */
        .mermaid-wrapper .edgePath path {
          stroke: #EA580C !important;
          stroke-width: 2.2px !important;
          stroke-linecap: round !important;
          stroke-linejoin: round !important;
        }

        .mermaid-wrapper .marker {
          fill: #EA580C !important;
          stroke: #EA580C !important;
        }

        .mermaid-wrapper .edgeLabel {
          background-color: #FFFFFF !important;
          padding: 3px 8px !important;
          border-radius: 8px !important;
          font-size: 11px !important;
          font-weight: 600 !important;
          color: #4B5563 !important;
          border: 1px solid #E5E7EB !important;
          box-shadow: 0 2px 6px rgba(0,0,0,0.05) !important;
        }
      `}</style>
    </>
  )
}
