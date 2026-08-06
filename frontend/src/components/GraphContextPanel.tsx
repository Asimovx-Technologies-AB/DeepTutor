import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Network, X, ZoomIn, ZoomOut, RefreshCw, Maximize2, Minimize2,
  MousePointer, Search, Sparkles, ChevronRight
} from 'lucide-react'

interface GraphNode {
  id: string
  name?: string
  type?: string
  description?: string
}

interface GraphEdge {
  source: string
  target: string
  type?: string
  description?: string
}

interface Props {
  entities: GraphNode[]
  relationships: GraphEdge[]
  isOpen: boolean
  onClose: () => void
}

/* ─── Color Palette for Node Types ────────────────────────────── */
const NODE_TYPE_COLORS: Record<string, string> = {
  concept:    '#6366f1', // Indigo
  person:     '#f59e0b', // Amber
  place:      '#10b981', // Emerald
  event:      '#ef4444', // Red
  formula:    '#06b6d4', // Cyan
  law:        '#8b5cf6', // Purple
  theorem:    '#ec4899', // Pink
  document:   '#3b82f6', // Blue
  example_of: '#64748b', // Slate
}

function getColor(type: string): string {
  return NODE_TYPE_COLORS[type?.toLowerCase()] ?? '#6366f1'
}

/* ─── Simulation Node & Edge ───────────────────────────────────── */
interface SimNode {
  id: string
  x: number
  y: number
  vx: number
  vy: number
  name: string
  type: string
  description: string
  radius: number
  pinned: boolean
}

interface SimEdge {
  source: string
  target: string
  type: string
  description: string
}

export default function GraphContextPanel({ entities, relationships, isOpen, onClose }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const animRef = useRef<number>(0)
  const nodesRef = useRef<SimNode[]>([])
  const edgesRef = useRef<SimEdge[]>([])

  // Camera & Zoom state
  const [zoom, setZoom] = useState(1)
  const camRef = useRef({ x: 0, y: 0, zoom: 1 })

  // Interaction state
  const [selectedNode, setSelectedNode] = useState<SimNode | null>(null)
  const [hoveredNode, setHoveredNode] = useState<SimNode | null>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  const dragRef = useRef<{
    node: SimNode | null
    isPanning: boolean
    startX: number
    startY: number
    startCamX: number
    startCamY: number
  }>({
    node: null,
    isPanning: false,
    startX: 0,
    startY: 0,
    startCamX: 0,
    startCamY: 0,
  })

  const tickRef = useRef(0)

  /* ─── Initialize Graph & Nodes ───────────────────────────────── */
  useEffect(() => {
    if (!entities.length || !isOpen) return

    const W = containerRef.current?.clientWidth || 800
    const H = containerRef.current?.clientHeight || 500
    const cx = W / 2
    const cy = H / 2

    // Fixed elegant radius to prevent huge overlapping circles
    const nodeRadius = 12

    // Distribute nodes evenly in a circle around the canvas center (cx, cy)
    const count = entities.length
    const nodes: SimNode[] = entities.map((e, i) => {
      const angle = (2 * Math.PI * i) / count - Math.PI / 2
      const radius = Math.min(W, H) * 0.28
      return {
        id: e.id,
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
        vx: 0,
        vy: 0,
        name: e.name || e.id,
        type: e.type || 'concept',
        description: e.description || '',
        radius: nodeRadius,
        pinned: false,
      }
    })

    const edges: SimEdge[] = relationships.map((r) => ({
      source: r.source,
      target: r.target,
      type: r.type || '',
      description: r.description || '',
    }))

    nodesRef.current = nodes
    edgesRef.current = edges
    tickRef.current = 0

    // Reset camera to exact 100% zoom centered
    camRef.current = { x: 0, y: 0, zoom: 1 }
    setZoom(1)
    setSelectedNode(null)
    setHoveredNode(null)
  }, [entities, relationships, isOpen])

  /* ─── Physics Simulation Tick ──────────────────────────────────── */
  const simulate = useCallback(() => {
    const nodes = nodesRef.current
    const edges = edgesRef.current
    if (!nodes.length) return

    const W = containerRef.current?.clientWidth || 800
    const H = containerRef.current?.clientHeight || 500
    const cx = W / 2
    const cy = H / 2

    // Cooling factor: settles simulation into stable layout
    const cooling = Math.max(0.01, 1 - tickRef.current * 0.005)
    tickRef.current++

    // 1. Repulsion between nodes
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i]
        const b = nodes[j]
        let dx = b.x - a.x
        let dy = b.y - a.y
        let dist = Math.sqrt(dx * dx + dy * dy) || 1
        const minDist = (a.radius + b.radius) * 5
        const force = (12000 * cooling) / (dist * dist)
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force

        if (!a.pinned) {
          a.vx -= fx
          a.vy -= fy
        }
        if (!b.pinned) {
          b.vx += fx
          b.vy += fy
        }

        // Hard distance separation
        if (dist < minDist) {
          const overlap = (minDist - dist) / 2
          const ox = (dx / dist) * overlap
          const oy = (dy / dist) * overlap
          if (!a.pinned) {
            a.x -= ox
            a.y -= oy
          }
          if (!b.pinned) {
            b.x += ox
            b.y += oy
          }
        }
      }
    }

    // 2. Edge spring force
    const idealLen = 130
    for (const edge of edges) {
      const a = nodes.find((n) => n.id === edge.source)
      const b = nodes.find((n) => n.id === edge.target)
      if (!a || !b) continue
      let dx = b.x - a.x
      let dy = b.y - a.y
      let dist = Math.sqrt(dx * dx + dy * dy) || 1
      const force = (dist - idealLen) * 0.035 * cooling
      const fx = (dx / dist) * force
      const fy = (dy / dist) * force

      if (!a.pinned) {
        a.vx += fx
        a.vy += fy
      }
      if (!b.pinned) {
        b.vx -= fx
        b.vy -= fy
      }
    }

    // 3. Gravity toward center + position update
    for (const node of nodes) {
      if (node.pinned) continue
      node.vx += (cx - node.x) * 0.003 * cooling
      node.vy += (cy - node.y) * 0.003 * cooling

      node.vx *= 0.82
      node.vy *= 0.82

      node.x += node.vx
      node.y += node.vy

      // Keep within canvas bounds
      const margin = node.radius + 20
      node.x = Math.max(margin, Math.min(W - margin, node.x))
      node.y = Math.max(margin, Math.min(H - margin, node.y))
    }
  }, [])

  /* ─── Canvas Render Engine (Perfect DPR & Centering) ───────────── */
  const render = useCallback(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    const W = container.clientWidth
    const H = container.clientHeight
    const cam = camRef.current
    const nodes = nodesRef.current
    const edges = edgesRef.current
    const selected = selectedNode
    const hovered = hoveredNode

    // Reset Canvas Transform matrix to identity before clear
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    ctx.save()
    // 1. Apply High-DPI screen scaling
    ctx.scale(dpr, dpr)

    // 2. Center Camera Transform at exact (W/2, H/2)
    ctx.translate(W / 2 + cam.x, H / 2 + cam.y)
    ctx.scale(cam.zoom, cam.zoom)
    ctx.translate(-W / 2, -H / 2)

    // Highlight helper sets
    const connectedIds = new Set<string>()
    const connectedEdgeIndices = new Set<number>()

    if (selected) {
      connectedIds.add(selected.id)
      edges.forEach((e, i) => {
        if (e.source === selected.id || e.target === selected.id) {
          connectedIds.add(e.source)
          connectedIds.add(e.target)
          connectedEdgeIndices.add(i)
        }
      })
    }

    const searchMatchIds = new Set<string>()
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim()
      nodes.forEach((n) => {
        if (n.name.toLowerCase().includes(q) || n.type.toLowerCase().includes(q)) {
          searchMatchIds.add(n.id)
        }
      })
    }

    // ─── Draw Edges ───────────────────────────────────────────────
    edges.forEach((edge, i) => {
      const src = nodes.find((n) => n.id === edge.source)
      const tgt = nodes.find((n) => n.id === edge.target)
      if (!src || !tgt) return

      const dx = tgt.x - src.x
      const dy = tgt.y - src.y
      const dist = Math.sqrt(dx * dx + dy * dy) || 1
      const nx = dx / dist
      const ny = dy / dist

      const x1 = src.x + nx * src.radius
      const y1 = src.y + ny * src.radius
      const x2 = tgt.x - nx * (tgt.radius + 8)
      const y2 = tgt.y - ny * (tgt.radius + 8)

      const isHighlighted = selected ? connectedEdgeIndices.has(i) : false
      const isDimmed =
        (selected && !isHighlighted) ||
        (searchMatchIds.size > 0 && !searchMatchIds.has(src.id) && !searchMatchIds.has(tgt.id))

      // Edge line
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.lineTo(x2, y2)
      ctx.strokeStyle = isDimmed
        ? 'rgba(226,232,240,0.4)'
        : isHighlighted
        ? '#6366f1'
        : 'rgba(148,163,184,0.4)'
      ctx.lineWidth = isHighlighted ? 2.5 : 1.5
      ctx.stroke()

      // Arrowhead
      const arrowLen = isHighlighted ? 8 : 6
      const arrowAngle = Math.atan2(y2 - y1, x2 - x1)
      ctx.beginPath()
      ctx.moveTo(x2, y2)
      ctx.lineTo(
        x2 - arrowLen * Math.cos(arrowAngle - 0.4),
        y2 - arrowLen * Math.sin(arrowAngle - 0.4)
      )
      ctx.lineTo(
        x2 - arrowLen * Math.cos(arrowAngle + 0.4),
        y2 - arrowLen * Math.sin(arrowAngle + 0.4)
      )
      ctx.closePath()
      ctx.fillStyle = isDimmed ? 'rgba(226,232,240,0.4)' : isHighlighted ? '#6366f1' : 'rgba(148,163,184,0.5)'
      ctx.fill()

      // Relationship type text tag
      if (edge.type && !isDimmed) {
        const mx = (src.x + tgt.x) / 2
        const my = (src.y + tgt.y) / 2
        ctx.save()
        ctx.font = '600 10px Inter, sans-serif'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        const label = edge.type.replace(/_/g, ' ')
        const tw = ctx.measureText(label).width

        ctx.fillStyle = 'rgba(255,255,255,0.94)'
        ctx.fillRect(mx - tw / 2 - 4, my - 7, tw + 8, 14)
        ctx.strokeStyle = 'rgba(226,232,240,0.9)'
        ctx.strokeRect(mx - tw / 2 - 4, my - 7, tw + 8, 14)

        ctx.fillStyle = isHighlighted ? '#4338ca' : '#64748b'
        ctx.fillText(label, mx, my)
        ctx.restore()
      }
    })

    // ─── Draw Nodes ───────────────────────────────────────────────
    nodes.forEach((node) => {
      const color = getColor(node.type)
      const isSelected = selected?.id === node.id
      const isHovered = hovered?.id === node.id
      const isConnected = connectedIds.has(node.id)
      const isSearchMatch = searchMatchIds.has(node.id)
      const isDimmed = (selected && !isConnected) || (searchMatchIds.size > 0 && !isSearchMatch)

      const r = node.radius

      // Soft outer glow for selected/hovered/searched
      if ((isSelected || isHovered || isSearchMatch) && !isDimmed) {
        ctx.beginPath()
        ctx.arc(node.x, node.y, r + 6, 0, Math.PI * 2)
        ctx.fillStyle = isSelected
          ? 'rgba(99,102,241,0.25)'
          : isSearchMatch
          ? 'rgba(245,158,11,0.3)'
          : 'rgba(99,102,241,0.15)'
        ctx.fill()
      }

      // Main Node Circle
      ctx.beginPath()
      ctx.arc(node.x, node.y, r, 0, Math.PI * 2)
      ctx.fillStyle = isDimmed ? '#f1f5f9' : color
      ctx.fill()

      ctx.lineWidth = isSelected ? 3 : 2
      ctx.strokeStyle = isDimmed ? '#cbd5e1' : isSelected ? '#111111' : '#ffffff'
      ctx.stroke()

      // Center Dot
      ctx.beginPath()
      ctx.arc(node.x, node.y, r * 0.35, 0, Math.PI * 2)
      ctx.fillStyle = isDimmed ? '#cbd5e1' : '#ffffff'
      ctx.fill()

      // Node Label (Clean Crisp Pill)
      const label = node.name.length > 22 ? node.name.slice(0, 20) + '…' : node.name
      ctx.font = `${isSelected || isHovered ? '700' : '600'} ${isSelected ? '12px' : '11px'} Inter, sans-serif`
      ctx.textAlign = 'center'

      const textY = node.y + r + 11

      if (!isDimmed) {
        const tw = ctx.measureText(label).width
        const px = 6
        const py = 2
        ctx.fillStyle = isSelected ? '#111111' : 'rgba(255,255,255,0.95)'

        ctx.beginPath()
        const rx = node.x - tw / 2 - px
        const ry = textY - py - 8
        const rw = tw + px * 2
        const rh = 14 + py
        ctx.roundRect(rx, ry, rw, rh, 6)
        ctx.fill()

        ctx.strokeStyle = isSelected ? '#111111' : 'rgba(226,232,240,0.9)'
        ctx.stroke()

        ctx.fillStyle = isSelected ? '#ffffff' : '#0f172a'
        ctx.fillText(label, node.x, textY)
      } else {
        ctx.fillStyle = '#cbd5e1'
        ctx.fillText(label, node.x, textY)
      }
    })

    ctx.restore()
  }, [selectedNode, hoveredNode, searchQuery])

  /* ─── Simulation Loop ─────────────────────────────────────────── */
  useEffect(() => {
    if (!isOpen || !entities.length) return
    const loop = () => {
      simulate()
      render()
      animRef.current = requestAnimationFrame(loop)
    }
    animRef.current = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(animRef.current)
  }, [isOpen, entities, simulate, render])

  /* ─── DPR Resize Handler ──────────────────────────────────────── */
  useEffect(() => {
    if (!isOpen) return
    const resize = () => {
      const canvas = canvasRef.current
      const container = containerRef.current
      if (!canvas || !container) return
      const dpr = window.devicePixelRatio || 1
      canvas.width = container.clientWidth * dpr
      canvas.height = container.clientHeight * dpr
      canvas.style.width = `${container.clientWidth}px`
      canvas.style.height = `${container.clientHeight}px`
    }
    resize()
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [isOpen, isFullscreen])

  /* ─── Accurate Hit Testing ────────────────────────────────────── */
  const hitTest = useCallback((clientX: number, clientY: number): SimNode | null => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return null

    const rect = canvas.getBoundingClientRect()
    const W = container.clientWidth
    const H = container.clientHeight
    const cam = camRef.current

    const mx = clientX - rect.left
    const my = clientY - rect.top

    // Convert mouse to world coordinates matching render transform
    const wx = (mx - W / 2 - cam.x) / cam.zoom + W / 2
    const wy = (my - H / 2 - cam.y) / cam.zoom + H / 2

    for (let i = nodesRef.current.length - 1; i >= 0; i--) {
      const node = nodesRef.current[i]
      const dx = wx - node.x
      const dy = wy - node.y
      if (dx * dx + dy * dy <= (node.radius + 8) * (node.radius + 8)) {
        return node
      }
    }
    return null
  }, [])

  /* ─── Mouse Handlers ───────────────────────────────────────────── */
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    const node = hitTest(e.clientX, e.clientY)
    if (node) {
      dragRef.current = {
        node,
        isPanning: false,
        startX: e.clientX,
        startY: e.clientY,
        startCamX: camRef.current.x,
        startCamY: camRef.current.y,
      }
      node.pinned = true
    } else {
      dragRef.current = {
        node: null,
        isPanning: true,
        startX: e.clientX,
        startY: e.clientY,
        startCamX: camRef.current.x,
        startCamY: camRef.current.y,
      }
    }
  }, [hitTest])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    const drag = dragRef.current
    if (drag.isPanning) {
      const dx = e.clientX - drag.startX
      const dy = e.clientY - drag.startY
      camRef.current.x = drag.startCamX + dx / camRef.current.zoom
      camRef.current.y = drag.startCamY + dy / camRef.current.zoom
      return
    }

    if (drag.node) {
      const canvas = canvasRef.current
      const container = containerRef.current
      if (!canvas || !container) return

      const rect = canvas.getBoundingClientRect()
      const W = container.clientWidth
      const H = container.clientHeight
      const cam = camRef.current

      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top

      const wx = (mx - W / 2 - cam.x) / cam.zoom + W / 2
      const wy = (my - H / 2 - cam.y) / cam.zoom + H / 2

      drag.node.x = wx
      drag.node.y = wy
      drag.node.vx = 0
      drag.node.vy = 0
      return
    }

    const node = hitTest(e.clientX, e.clientY)
    setHoveredNode(node)
    if (canvasRef.current) {
      canvasRef.current.style.cursor = node ? 'pointer' : 'default'
    }
  }, [hitTest])

  const handleMouseUp = useCallback(() => {
    if (dragRef.current.node) {
      dragRef.current.node.pinned = false
    }
    dragRef.current = { node: null, isPanning: false, startX: 0, startY: 0, startCamX: 0, startCamY: 0 }
  }, [])

  const handleClick = useCallback((e: React.MouseEvent) => {
    const node = hitTest(e.clientX, e.clientY)
    if (node) {
      setSelectedNode((prev) => (prev?.id === node.id ? null : node))
    } else {
      setSelectedNode(null)
    }
  }, [hitTest])

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    const delta = e.deltaY > 0 ? 0.9 : 1.1
    const newZoom = Math.max(0.4, Math.min(2.5, camRef.current.zoom * delta))
    camRef.current.zoom = newZoom
    setZoom(newZoom)
  }, [])

  const resetView = useCallback(() => {
    camRef.current = { x: 0, y: 0, zoom: 1 }
    setZoom(1)
    setSelectedNode(null)
    setHoveredNode(null)
    setSearchQuery('')
    tickRef.current = 0
  }, [])

  if (!isOpen) return null

  // Direct connections list for selected node
  const selectedNodeConnections = selectedNode
    ? edgesRef.current
        .filter((e) => e.source === selectedNode.id || e.target === selectedNode.id)
        .map((e) => {
          const targetId = e.source === selectedNode.id ? e.target : e.source
          const targetNode = nodesRef.current.find((n) => n.id === targetId)
          return {
            edgeType: e.type,
            targetNode,
          }
        })
        .filter((c) => c.targetNode)
    : []

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4 md:p-8"
      >
        <motion.div
          initial={{ scale: 0.95, opacity: 0, y: 10 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.95, opacity: 0, y: 10 }}
          className={`relative flex flex-col bg-white rounded-3xl shadow-2xl border border-slate-200 overflow-hidden ${
            isFullscreen ? 'w-full h-full rounded-none' : 'w-full max-w-6xl'
          }`}
          style={{ height: isFullscreen ? '100%' : 'min(88vh, 760px)' }}
        >
          {/* ─── HEADER BAR ─── */}
          <div className="flex flex-wrap items-center justify-between gap-4 px-6 py-4 border-b border-slate-100 bg-white">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-[#111111] text-white flex items-center justify-center shadow-md">
                <Network size={20} />
              </div>
              <div>
                <h3 className="text-base font-black text-slate-900 leading-tight">
                  3D Knowledge Graph
                </h3>
                <p className="text-xs text-slate-500 font-semibold">
                  {entities.length} entities · {relationships.length} relationships connected
                </p>
              </div>
            </div>

            {/* Live Search Input */}
            <div className="relative w-64">
              <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search entity in graph..."
                className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-9 pr-3.5 py-2 text-xs font-semibold text-slate-800 focus:outline-none focus:border-[#111111]"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700"
                >
                  <X size={12} />
                </button>
              )}
            </div>

            {/* Action Buttons */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => setIsFullscreen(!isFullscreen)}
                className="p-2 rounded-xl text-slate-500 hover:bg-slate-100 transition-colors"
                title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
              >
                {isFullscreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
              </button>

              <button
                onClick={onClose}
                className="p-2 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                title="Close Graph"
              >
                <X size={20} />
              </button>
            </div>
          </div>

          {/* ─── CANVAS WORKSPACE AREA ─── */}
          <div ref={containerRef} className="flex-1 relative bg-slate-50 overflow-hidden">
            {entities.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center p-6">
                <Network size={48} className="text-slate-300 mb-3" />
                <h4 className="text-base font-bold text-slate-700">No Knowledge Graph Extracted Yet</h4>
                <p className="text-xs text-slate-500 max-w-sm mt-1">
                  Upload a PDF document to generate an interactive 3D concept graph.
                </p>
              </div>
            ) : (
              <canvas
                ref={canvasRef}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseUp}
                onClick={handleClick}
                onWheel={handleWheel}
                className="w-full h-full block"
              />
            )}

            {/* Instruction Badge */}
            <div className="absolute top-4 left-4 bg-white/90 border border-slate-200/80 backdrop-blur-md px-3.5 py-2 rounded-xl shadow-sm flex items-center gap-2 text-xs font-semibold text-slate-600">
              <MousePointer size={14} className="text-indigo-600" />
              <span>Click node to inspect details · Drag to move · Scroll to zoom</span>
            </div>

            {/* ─── INTERACTIVE NODE DETAIL DRAWER ─── */}
            <AnimatePresence>
              {selectedNode && (
                <motion.div
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 20 }}
                  className="absolute top-4 right-4 bottom-4 w-80 bg-white/95 border border-slate-200 backdrop-blur-md rounded-2xl shadow-xl p-5 flex flex-col justify-between z-20 overflow-y-auto"
                >
                  <div className="space-y-4">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-3.5 h-3.5 rounded-full flex-shrink-0"
                          style={{ backgroundColor: getColor(selectedNode.type) }}
                        />
                        <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500">
                          {selectedNode.type} Entity
                        </span>
                      </div>
                      <button
                        onClick={() => setSelectedNode(null)}
                        className="text-slate-400 hover:text-slate-700 p-1"
                      >
                        <X size={16} />
                      </button>
                    </div>

                    <div>
                      <h4 className="text-lg font-black text-slate-900 leading-snug">
                        {selectedNode.name}
                      </h4>
                      {selectedNode.description && (
                        <p className="text-xs text-slate-600 mt-2 leading-relaxed font-medium bg-slate-50 p-3 rounded-xl border border-slate-100">
                          {selectedNode.description}
                        </p>
                      )}
                    </div>

                    {/* Direct Connections List */}
                    <div className="space-y-2">
                      <p className="text-xs font-extrabold uppercase tracking-wider text-slate-400 flex items-center justify-between">
                        <span>Connected Entities</span>
                        <span className="text-indigo-600">{selectedNodeConnections.length}</span>
                      </p>

                      <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                        {selectedNodeConnections.map((conn, idx) => (
                          <div
                            key={idx}
                            onClick={() => conn.targetNode && setSelectedNode(conn.targetNode)}
                            className="p-2.5 rounded-xl border border-slate-200/80 bg-slate-50 hover:bg-indigo-50 hover:border-indigo-200 transition-all cursor-pointer flex items-center justify-between group"
                          >
                            <div>
                              <p className="text-xs font-bold text-slate-800 group-hover:text-indigo-600 transition-colors">
                                {conn.targetNode?.name}
                              </p>
                              {conn.edgeType && (
                                <p className="text-[10px] text-slate-400 font-semibold mt-0.5">
                                  {conn.edgeType.replace(/_/g, ' ')}
                                </p>
                              )}
                            </div>
                            <ChevronRight size={14} className="text-slate-400 group-hover:text-indigo-600 group-hover:translate-x-0.5 transition-transform" />
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  <button
                    onClick={() => setSelectedNode(null)}
                    className="w-full py-2.5 rounded-xl bg-[#111111] text-white text-xs font-bold hover:bg-[#27272a] transition-colors mt-4"
                  >
                    Close Inspection
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* ─── FOOTER & LEGEND ─── */}
          <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-3 border-t border-slate-100 bg-white text-xs text-slate-600">
            {/* Zoom Controls */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  camRef.current.zoom = Math.max(0.4, camRef.current.zoom - 0.15)
                  setZoom(camRef.current.zoom)
                }}
                className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-100 transition-colors"
                title="Zoom Out"
              >
                <ZoomOut size={14} />
              </button>
              <span className="font-extrabold w-12 text-center text-slate-800">
                {Math.round(zoom * 100)}%
              </span>
              <button
                onClick={() => {
                  camRef.current.zoom = Math.min(2.5, camRef.current.zoom + 0.15)
                  setZoom(camRef.current.zoom)
                }}
                className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-100 transition-colors"
                title="Zoom In"
              >
                <ZoomIn size={14} />
              </button>
              <button
                onClick={resetView}
                className="flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-100 transition-colors ml-2"
              >
                <RefreshCw size={12} /> Reset View
              </button>
            </div>

            {/* Entity Types Legend */}
            <div className="flex items-center gap-3 overflow-x-auto">
              <span className="text-[10px] font-extrabold uppercase text-slate-400 tracking-wider">
                Entity Types
              </span>
              <div className="flex items-center gap-3">
                {Object.entries(NODE_TYPE_COLORS).slice(0, 6).map(([type, color]) => (
                  <div key={type} className="flex items-center gap-1.5">
                    <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                    <span className="text-xs font-semibold capitalize text-slate-700">{type}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
