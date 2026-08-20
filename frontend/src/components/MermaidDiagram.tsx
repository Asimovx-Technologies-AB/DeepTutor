import { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'

mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  themeVariables: {
    primaryColor: '#FFF0E4',
    primaryTextColor: '#20201D',
    primaryBorderColor: '#F28A45',
    lineColor: '#D97706',
    secondaryColor: '#FAF8F3',
    tertiaryColor: '#FFFFFF',
    fontSize: '13px',
    fontFamily: 'Inter, system-ui, sans-serif',
  },
  securityLevel: 'loose',
})

interface Props {
  chart: string
}

export default function MermaidDiagram({ chart }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [svgContent, setSvgContent] = useState<string>('')
  const [error, setError] = useState<boolean>(false)

  useEffect(() => {
    let isMounted = true
    const renderChart = async () => {
      if (!chart || !chart.trim()) return

      try {
        const uniqueId = `mermaid-${Math.random().toString(36).substring(2, 9)}`
        // Clean markdown backticks or extra wrappers
        const cleanCode = chart
          .replace(/^```mermaid\s*/i, '')
          .replace(/```$/, '')
          .trim()

        const { svg } = await mermaid.render(uniqueId, cleanCode)
        if (isMounted) {
          setSvgContent(svg)
          setError(false)
        }
      } catch (err) {
        console.error('[Mermaid] Render error:', err)
        if (isMounted) {
          setError(true)
        }
      }
    }

    renderChart()
    return () => {
      isMounted = false
    }
  }, [chart])

  if (error) {
    return (
      <div className="my-3 p-3 rounded-2xl bg-amber-50 border border-amber-200 text-xs font-mono text-amber-900 overflow-x-auto">
        <pre>{chart}</pre>
      </div>
    )
  }

  return (
    <div className="my-4 p-4 rounded-2xl bg-[#FAF8F3] border border-[#E7E1D8] shadow-2xs overflow-x-auto flex justify-center">
      <div
        ref={containerRef}
        className="mermaid-wrapper max-w-full"
        dangerouslySetInnerHTML={{ __html: svgContent }}
      />
    </div>
  )
}
