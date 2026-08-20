import { useState, useRef, useEffect, useCallback, useMemo, memo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Network, X, ZoomIn, ZoomOut, RefreshCw, Maximize2, Minimize2,
  MousePointer, Search, Sparkles, ChevronRight, Layers, Sun, Moon,
  Info, Filter, Eye, MessageSquare, Lightbulb, BookOpen, Target,
  CheckCircle2, HelpCircle
} from 'lucide-react'
import { documentsApi } from '../services/api'

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
  onAskTutor?: (conceptName: string) => void
}

/* ─── Rich Vibrant Color Palette for Node Types ─────────────────── */
const NODE_TYPE_COLORS: Record<string, { bg: string; border: string; glow: string }> = {
  concept:    { bg: '#F28A45', border: '#FFF0E4', glow: 'rgba(242, 138, 69, 0.4)' },  // Apricot Orange
  person:     { bg: '#D99A32', border: '#FFF3D8', glow: 'rgba(217, 154, 50, 0.4)' },  // Warm Amber
  place:      { bg: '#4F8A68', border: '#E3F0E5', glow: 'rgba(79, 138, 104, 0.4)' },  // Sage Green
  event:      { bg: '#C85C52', border: '#FBE7E4', glow: 'rgba(200, 92, 82, 0.4)' },   // Soft Red
  formula:    { bg: '#06b6d4', border: '#22d3ee', glow: 'rgba(6, 182, 212, 0.4)' },   // Cyan
  law:        { bg: '#A99BCB', border: '#F0ECF7', glow: 'rgba(169, 155, 203, 0.4)' },  // Soft Lavender
  theorem:    { bg: '#ec4899', border: '#f472b6', glow: 'rgba(236, 72, 153, 0.4)' },  // Pink
  document:   { bg: '#3b82f6', border: '#60a5fa', glow: 'rgba(59, 130, 246, 0.4)' },  // Blue
  example_of: { bg: '#6F6B63', border: '#E7E1D8', glow: 'rgba(111, 107, 99, 0.4)' }, // Soft Ink
}

function getNodeColor(type?: string) {
  const key = type?.toLowerCase() ?? 'concept'
  return NODE_TYPE_COLORS[key] || NODE_TYPE_COLORS.concept
}

/* ─── Physics Simulation Interfaces ────────────────────────────── */
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

function GraphContextPanel({ entities, relationships, isOpen, onClose, onAskTutor }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const animRef = useRef<number>(0)
  const nodesRef = useRef<SimNode[]>([])
  const edgesRef = useRef<SimEdge[]>([])

  // Camera & Viewport
  const [zoom, setZoom] = useState(1)
  const camRef = useRef({ x: 0, y: 0, zoom: 1 })

  // UI States
  const [selectedNode, setSelectedNode] = useState<SimNode | null>(null)
  const [hoveredNode, setHoveredNode] = useState<SimNode | null>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedTypeFilter, setSelectedTypeFilter] = useState<string | null>(null)
  const [darkMode, setDarkMode] = useState(false) // Default to warm light theme matching DeepTutor design system

  // Dynamic AI Concept Explanation State
  const [conceptDetails, setConceptDetails] = useState<{
    definition?: string
    key_takeaway?: string
    application?: string
    exam_tip?: string
  } | null>(null)
  const [loadingDetails, setLoadingDetails] = useState(false)
  const detailsCacheRef = useRef<Map<string, any>>(new Map())

  useEffect(() => {
    if (!selectedNode?.name || selectedNode.type === 'document') {
      setConceptDetails(null)
      return
    }

    const name = selectedNode.name
    if (detailsCacheRef.current.has(name)) {
      setConceptDetails(detailsCacheRef.current.get(name))
      return
    }

    setLoadingDetails(true)
    documentsApi
      .explainConcept(name)
      .then((res) => {
        if (res.data) {
          detailsCacheRef.current.set(name, res.data)
          setConceptDetails(res.data)
        }
      })
      .catch(() => {})
      .finally(() => {
        setLoadingDetails(false)
      })
  }, [selectedNode])

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

  /* ─── Extract Unique Entity Types for Filter Bar ──────────────── */
  const uniqueTypes = useMemo(() => {
    const types = new Set<string>()
    entities.forEach((e) => {
      if (e.type) types.add(e.type.toLowerCase())
    })
    return Array.from(types)
  }, [entities])

  /* ─── Initialize Simulation Nodes ─────────────────────────────── */
  useEffect(() => {
    if (!entities.length || !isOpen) return

    const W = containerRef.current?.clientWidth || 1000
    const H = containerRef.current?.clientHeight || 650
    const cx = W / 2
    const cy = H / 2

    const nodeRadius = 14
    const count = entities.length

    const nodes: SimNode[] = entities.map((e, i) => {
      const angle = (2 * Math.PI * i) / count - Math.PI / 2
      const radius = Math.min(W, H) * 0.32
      return {
        id: e.id,
        x: cx + radius * Math.cos(angle) + (Math.random() - 0.5) * 40,
        y: cy + radius * Math.sin(angle) + (Math.random() - 0.5) * 40,
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

    camRef.current = { x: 0, y: 0, zoom: 1 }
    setZoom(1)
    setSelectedNode(null)
    setHoveredNode(null)
    setSelectedTypeFilter(null)
  }, [entities, relationships, isOpen])

  /* ─── Physics Simulation Tick ──────────────────────────────────── */
  const simulate = useCallback(() => {
    const nodes = nodesRef.current
    const edges = edgesRef.current
    if (!nodes.length) return

    const W = containerRef.current?.clientWidth || 1000
    const H = containerRef.current?.clientHeight || 650
    const cx = W / 2
    const cy = H / 2

    const cooling = Math.max(0.01, 1 - tickRef.current * 0.005)
    tickRef.current++

    // 1. Repulsion force between nodes
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i]
        const b = nodes[j]
        let dx = b.x - a.x
        let dy = b.y - a.y
        let dist = Math.sqrt(dx * dx + dy * dy) || 1
        const minDist = (a.radius + b.radius) * 4.5
        const force = (14000 * cooling) / (dist * dist)
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
    const idealLen = 140
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

      const margin = node.radius + 24
      node.x = Math.max(margin, Math.min(W - margin, node.x))
      node.y = Math.max(margin, Math.min(H - margin, node.y))
    }
  }, [])

  /* ─── Canvas Render Engine ─────────────────────────────────────── */
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

    // Reset Canvas Transform
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // Canvas Background Fill
    ctx.fillStyle = darkMode ? '#0B0F19' : '#F8FAFC'
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    ctx.save()
    ctx.scale(dpr, dpr)

    // Apply Camera Transform
    ctx.translate(W / 2 + cam.x, H / 2 + cam.y)
    ctx.scale(cam.zoom, cam.zoom)
    ctx.translate(-W / 2, -H / 2)

    // Render Grid Pattern
    const gridSize = 40
    ctx.strokeStyle = darkMode ? 'rgba(255, 255, 255, 0.03)' : 'rgba(0, 0, 0, 0.03)'
    ctx.lineWidth = 1
    for (let x = 0; x < W * 2; x += gridSize) {
      ctx.beginPath()
      ctx.moveTo(x - W / 2, -H / 2)
      ctx.lineTo(x - W / 2, H * 1.5)
      ctx.stroke()
    }
    for (let y = 0; y < H * 2; y += gridSize) {
      ctx.beginPath()
      ctx.moveTo(-W / 2, y - H / 2)
      ctx.lineTo(W * 1.5, y - H / 2)
      ctx.stroke()
    }

    // Highlight Sets
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

      const isTypeFilterMatch = !selectedTypeFilter || 
        src.type.toLowerCase() === selectedTypeFilter || 
        tgt.type.toLowerCase() === selectedTypeFilter

      const isHighlighted = selected ? connectedEdgeIndices.has(i) : false
      const isDimmed =
        (selected && !isHighlighted) ||
        (searchMatchIds.size > 0 && !searchMatchIds.has(src.id) && !searchMatchIds.has(tgt.id)) ||
        (!isTypeFilterMatch)

      const dx = tgt.x - src.x
      const dy = tgt.y - src.y
      const dist = Math.sqrt(dx * dx + dy * dy) || 1
      const nx = dx / dist
      const ny = dy / dist

      const x1 = src.x + nx * src.radius
      const y1 = src.y + ny * src.radius
      const x2 = tgt.x - nx * (tgt.radius + 8)
      const y2 = tgt.y - ny * (tgt.radius + 8)

      // Edge Line
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.lineTo(x2, y2)
      ctx.strokeStyle = isDimmed
        ? (darkMode ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)')
        : isHighlighted
        ? '#818cf8'
        : (darkMode ? 'rgba(148,163,184,0.35)' : 'rgba(100,116,139,0.35)')
      ctx.lineWidth = isHighlighted ? 3 : 1.8
      ctx.stroke()

      // Arrowhead
      const arrowLen = isHighlighted ? 9 : 7
      const arrowAngle = Math.atan2(y2 - y1, x2 - x1)
      ctx.beginPath()
      ctx.moveTo(x2, y2)
      ctx.lineTo(
        x2 - arrowLen * Math.cos(arrowAngle - 0.45),
        y2 - arrowLen * Math.sin(arrowAngle - 0.45)
      )
      ctx.lineTo(
        x2 - arrowLen * Math.cos(arrowAngle + 0.45),
        y2 - arrowLen * Math.sin(arrowAngle + 0.45)
      )
      ctx.closePath()
      ctx.fillStyle = isDimmed
        ? (darkMode ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)')
        : isHighlighted
        ? '#818cf8'
        : (darkMode ? 'rgba(148,163,184,0.45)' : 'rgba(100,116,139,0.45)')
      ctx.fill()

      // Relationship Tag Pill
      if (edge.type && !isDimmed) {
        const mx = (src.x + tgt.x) / 2
        const my = (src.y + tgt.y) / 2
        ctx.save()
        ctx.font = '600 10px Inter, sans-serif'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        const label = edge.type.replace(/_/g, ' ')
        const tw = ctx.measureText(label).width

        ctx.fillStyle = darkMode ? 'rgba(15, 23, 42, 0.92)' : 'rgba(255, 255, 255, 0.94)'
        ctx.beginPath()
        ctx.roundRect(mx - tw / 2 - 5, my - 8, tw + 10, 16, 4)
        ctx.fill()
        ctx.strokeStyle = isHighlighted
          ? '#6366f1'
          : (darkMode ? 'rgba(255, 255, 255, 0.12)' : 'rgba(226, 232, 240, 0.9)')
        ctx.stroke()

        ctx.fillStyle = isHighlighted
          ? (darkMode ? '#c7d2fe' : '#4338ca')
          : (darkMode ? '#94a3b8' : '#64748b')
        ctx.fillText(label, mx, my)
        ctx.restore()
      }
    })

    // ─── Draw Nodes ───────────────────────────────────────────────
    nodes.forEach((node) => {
      const colors = getNodeColor(node.type)
      const isSelected = selected?.id === node.id
      const isHovered = hovered?.id === node.id
      const isConnected = connectedIds.has(node.id)
      const isSearchMatch = searchMatchIds.has(node.id)
      const isTypeMatch = !selectedTypeFilter || node.type.toLowerCase() === selectedTypeFilter
      const isDimmed = (selected && !isConnected) || 
                       (searchMatchIds.size > 0 && !isSearchMatch) ||
                       (!isTypeMatch)

      const r = node.radius

      // Glowing outer halo
      if ((isSelected || isHovered || isSearchMatch) && !isDimmed) {
        ctx.beginPath()
        ctx.arc(node.x, node.y, r + 8, 0, Math.PI * 2)
        ctx.fillStyle = colors.glow
        ctx.fill()
      }

      // Main Node Circle
      ctx.beginPath()
      ctx.arc(node.x, node.y, r, 0, Math.PI * 2)
      ctx.fillStyle = isDimmed ? (darkMode ? '#1e293b' : '#f1f5f9') : colors.bg
      ctx.fill()

      ctx.lineWidth = isSelected ? 3.5 : 2
      ctx.strokeStyle = isDimmed
        ? (darkMode ? '#334155' : '#cbd5e1')
        : isSelected
        ? '#ffffff'
        : colors.border
      ctx.stroke()

      // Center Core Dot
      ctx.beginPath()
      ctx.arc(node.x, node.y, r * 0.35, 0, Math.PI * 2)
      ctx.fillStyle = isDimmed ? (darkMode ? '#475569' : '#cbd5e1') : '#ffffff'
      ctx.fill()

      // Node Label (Clean Crisp Badge)
      const label = node.name.length > 24 ? node.name.slice(0, 22) + '…' : node.name
      ctx.font = `${isSelected || isHovered ? '700' : '600'} ${isSelected ? '12px' : '11px'} Inter, sans-serif`
      ctx.textAlign = 'center'

      const textY = node.y + r + 13

      if (!isDimmed) {
        const tw = ctx.measureText(label).width
        const px = 7
        const py = 3
        ctx.fillStyle = isSelected
          ? (darkMode ? '#ffffff' : '#0F172A')
          : (darkMode ? 'rgba(15, 23, 42, 0.92)' : 'rgba(255, 255, 255, 0.95)')

        ctx.beginPath()
        const rx = node.x - tw / 2 - px
        const ry = textY - py - 8
        const rw = tw + px * 2
        const rh = 16 + py
        ctx.roundRect(rx, ry, rw, rh, 6)
        ctx.fill()

        ctx.strokeStyle = isSelected
          ? colors.bg
          : (darkMode ? 'rgba(255, 255, 255, 0.12)' : 'rgba(226, 232, 240, 0.9)')
        ctx.stroke()

        ctx.fillStyle = isSelected
          ? (darkMode ? '#0F172A' : '#ffffff')
          : (darkMode ? '#f8fafc' : '#0f172a')
        ctx.fillText(label, node.x, textY)
      } else {
        ctx.fillStyle = darkMode ? '#475569' : '#94a3b8'
        ctx.fillText(label, node.x, textY)
      }
    })

    ctx.restore()
  }, [selectedNode, hoveredNode, searchQuery, selectedTypeFilter, darkMode])

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

  /* ─── High DPI Canvas Resize Handler ───────────────────────────── */
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

  /* ─── Hit Testing for Interactive Selection ────────────────────── */
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

    const wx = (mx - W / 2 - cam.x) / cam.zoom + W / 2
    const wy = (my - H / 2 - cam.y) / cam.zoom + H / 2

    for (let i = nodesRef.current.length - 1; i >= 0; i--) {
      const node = nodesRef.current[i]
      const dx = wx - node.x
      const dy = wy - node.y
      if (dx * dx + dy * dy <= (node.radius + 10) * (node.radius + 10)) {
        return node
      }
    }
    return null
  }, [])

  /* ─── Mouse Event Handlers ─────────────────────────────────────── */
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

      drag.node.x = (mx - W / 2 - cam.x) / cam.zoom + W / 2
      drag.node.y = (my - H / 2 - cam.y) / cam.zoom + H / 2
      return
    }

    const hover = hitTest(e.clientX, e.clientY)
    setHoveredNode(hover)
  }, [hitTest])

  const handleMouseUp = useCallback(() => {
    if (dragRef.current.node) {
      dragRef.current.node.pinned = false
    }
    dragRef.current = {
      node: null,
      isPanning: false,
      startX: 0,
      startY: 0,
      startCamX: 0,
      startCamY: 0,
    }
  }, [])

  const handleClick = useCallback((e: React.MouseEvent) => {
    const node = hitTest(e.clientX, e.clientY)
    if (node) {
      setSelectedNode(node)
    } else {
      setSelectedNode(null)
    }
  }, [hitTest])

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    const zoomFactor = e.deltaY < 0 ? 1.12 : 0.88
    const newZoom = Math.max(0.35, Math.min(3.0, camRef.current.zoom * zoomFactor))
    camRef.current.zoom = newZoom
    setZoom(newZoom)
  }, [])

  const resetView = useCallback(() => {
    camRef.current = { x: 0, y: 0, zoom: 1 }
    setZoom(1)
    setSelectedNode(null)
    setSearchQuery('')
    setSelectedTypeFilter(null)
  }, [])

  if (!isOpen) return null

  // Connected Nodes for Inspection Drawer
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
        className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 backdrop-blur-md p-2 sm:p-4 md:p-6"
      >
        <motion.div
          initial={{ scale: 0.96, opacity: 0, y: 15 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.96, opacity: 0, y: 15 }}
          className={`relative flex flex-col rounded-3xl shadow-2xl border transition-all duration-300 overflow-hidden ${
            darkMode 
              ? 'bg-[#0B0F19] border-slate-800 text-slate-100' 
              : 'bg-white border-slate-200 text-slate-900'
          } ${
            isFullscreen 
              ? 'w-full h-full rounded-none border-none' 
              : 'w-[96vw] max-w-[1400px] h-[92vh] max-h-[880px]'
          }`}
        >
          {/* ─── TOP HEADER CONTROL BAR ─── */}
          <div className={`flex flex-wrap items-center justify-between gap-4 px-6 py-4 border-b ${
            darkMode ? 'border-slate-800/80 bg-[#0F172A]/80' : 'border-slate-100 bg-white'
          }`}>
            <div className="flex items-center gap-3">
              <div className={`w-11 h-11 rounded-2xl flex items-center justify-center shadow-lg transition-transform hover:scale-105 ${
                darkMode ? 'bg-indigo-600 text-white shadow-indigo-500/20' : 'bg-slate-900 text-white'
              }`}>
                <Network size={22} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-black tracking-tight leading-tight">
                    3D Knowledge Graph
                  </h3>
                  <span className={`text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full ${
                    darkMode ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30' : 'bg-indigo-50 text-indigo-600 border border-indigo-200'
                  }`}>
                    Live Interactive
                  </span>
                </div>
                <p className={`text-xs font-semibold mt-0.5 ${darkMode ? 'text-slate-400' : 'text-slate-500'}`}>
                  {entities.length} concept entities · {relationships.length} relationships connected
                </p>
              </div>
            </div>

            {/* Controls Right Section */}
            <div className="flex items-center gap-3">
              {/* Search Bar */}
              <div className="relative w-64 md:w-72">
                <Search size={15} className={`absolute left-3.5 top-1/2 -translate-y-1/2 ${
                  darkMode ? 'text-slate-400' : 'text-slate-400'
                }`} />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search entity in graph..."
                  className={`w-full rounded-xl pl-9 pr-8 py-2 text-xs font-semibold focus:outline-none transition-all ${
                    darkMode 
                      ? 'bg-slate-900/90 border border-slate-700/80 text-slate-100 placeholder:text-slate-500 focus:border-indigo-500' 
                      : 'bg-slate-50 border border-slate-200 text-slate-800 focus:border-slate-900'
                  }`}
                />
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery('')}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
                  >
                    <X size={13} />
                  </button>
                )}
              </div>

              {/* Dark / Light Mode Canvas Toggle */}
              <button
                onClick={() => setDarkMode(!darkMode)}
                className={`p-2.5 rounded-xl border transition-all ${
                  darkMode 
                    ? 'bg-slate-800/80 border-slate-700 text-amber-400 hover:bg-slate-800' 
                    : 'bg-slate-100 border-slate-200 text-slate-700 hover:bg-slate-200'
                }`}
                title={darkMode ? 'Switch to Light Studio' : 'Switch to Dark Cyberpunk'}
              >
                {darkMode ? <Sun size={17} /> : <Moon size={17} />}
              </button>

              {/* Fullscreen Toggle */}
              <button
                onClick={() => setIsFullscreen(!isFullscreen)}
                className={`p-2.5 rounded-xl border transition-all ${
                  darkMode 
                    ? 'bg-slate-800/80 border-slate-700 text-slate-300 hover:bg-slate-800' 
                    : 'bg-slate-100 border-slate-200 text-slate-700 hover:bg-slate-200'
                }`}
                title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
              >
                {isFullscreen ? <Minimize2 size={17} /> : <Maximize2 size={17} />}
              </button>

              {/* Close Button */}
              <button
                onClick={onClose}
                className={`p-2.5 rounded-xl border transition-all ${
                  darkMode 
                    ? 'bg-slate-800/80 border-slate-700 text-slate-400 hover:text-white hover:bg-red-500/20 hover:border-red-500/30' 
                    : 'bg-slate-100 border-slate-200 text-slate-500 hover:text-slate-900 hover:bg-slate-200'
                }`}
                title="Close Graph"
              >
                <X size={19} />
              </button>
            </div>
          </div>

          {/* ─── CANVAS WORKSPACE AREA ─── */}
          <div ref={containerRef} className="flex-1 relative overflow-hidden">
            {entities.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center p-6">
                <Network size={56} className={darkMode ? 'text-slate-700 mb-4' : 'text-slate-300 mb-4'} />
                <h4 className={`text-lg font-bold ${darkMode ? 'text-slate-300' : 'text-slate-700'}`}>
                  No Knowledge Graph Extracted Yet
                </h4>
                <p className={`text-xs max-w-md mt-1.5 leading-relaxed ${darkMode ? 'text-slate-500' : 'text-slate-500'}`}>
                  Upload a PDF document or ask a question to construct an interactive 3D concept graph automatically.
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
                className="w-full h-full block cursor-grab active:cursor-grabbing"
              />
            )}

            {/* Floating Navigation Instruction Pill */}
            <div className={`absolute top-4 left-4 backdrop-blur-xl px-4 py-2.5 rounded-2xl shadow-xl border flex items-center gap-2.5 text-xs font-bold ${
              darkMode 
                ? 'bg-slate-900/90 border-slate-700/80 text-slate-300' 
                : 'bg-white/90 border-slate-200/80 text-slate-700'
            }`}>
              <MousePointer size={15} className="text-indigo-500 animate-pulse" />
              <span>Click node to inspect · Drag to move · Scroll to zoom</span>
            </div>

            {/* Live Search Match Counter */}
            {searchQuery && (
              <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-amber-500/20 border border-amber-500/40 backdrop-blur-md px-4 py-1.5 rounded-full text-xs font-bold text-amber-400 shadow-lg">
                Matching nodes highlighted
              </div>
            )}

            {/* ─── SLIDE-OVER NODE DETAIL DRAWER ─── */}
            <AnimatePresence>
              {selectedNode && (
                <motion.div
                  initial={{ opacity: 0, x: 30 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 30 }}
                  className={`absolute top-4 right-4 bottom-4 w-88 md:w-96 backdrop-blur-xl rounded-3xl shadow-2xl p-6 flex flex-col justify-between z-20 overflow-y-auto border ${
                    darkMode 
                      ? 'bg-slate-900/95 border-slate-700 text-slate-100' 
                      : 'bg-white/95 border-slate-200 text-slate-900'
                  }`}
                >
                  <div className="space-y-5">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-4 h-4 rounded-full flex-shrink-0 shadow-md"
                          style={{ backgroundColor: getNodeColor(selectedNode.type).bg }}
                        />
                        <span className={`text-[11px] font-extrabold uppercase tracking-wider ${
                          darkMode ? 'text-slate-400' : 'text-slate-500'
                        }`}>
                          {selectedNode.type} Entity
                        </span>
                      </div>
                      <button
                        onClick={() => setSelectedNode(null)}
                        className={`p-1.5 rounded-xl transition-colors ${
                          darkMode ? 'text-slate-400 hover:text-white hover:bg-slate-800' : 'text-slate-400 hover:text-slate-700 hover:bg-slate-100'
                        }`}
                      >
                        <X size={17} />
                      </button>
                    </div>

                    <div>
                      <h4 className="text-xl font-black leading-snug tracking-tight">
                        {selectedNode.name}
                      </h4>

                      {/* Main Educational Definition */}
                      {loadingDetails ? (
                        <div className={`mt-3 p-4 rounded-2xl border text-xs space-y-2.5 animate-pulse ${
                          darkMode ? 'bg-slate-800/60 border-slate-700/60 text-slate-400' : 'bg-slate-50 border-slate-200/80 text-slate-500'
                        }`}>
                          <div className="flex items-center gap-2 text-indigo-500 font-bold">
                            <Sparkles size={14} className="animate-spin" />
                            <span>DeepTutor is analyzing textbook context...</span>
                          </div>
                          <div className="h-2 bg-slate-300 dark:bg-slate-700 rounded-full w-full" />
                          <div className="h-2 bg-slate-300 dark:bg-slate-700 rounded-full w-4/5" />
                        </div>
                      ) : (
                        <div className="space-y-2.5 mt-3">
                          {/* Core Meaning Card */}
                          <div className={`text-xs leading-relaxed font-medium p-3.5 rounded-2xl border ${
                            darkMode 
                              ? 'bg-slate-800/80 border-slate-700 text-slate-200' 
                              : 'bg-emerald-50/70 border-emerald-200/80 text-emerald-950'
                          }`}>
                            <div className="flex items-center gap-1.5 font-black text-[11px] text-emerald-700 dark:text-emerald-400 uppercase tracking-wide mb-1">
                              <BookOpen size={13} />
                              <span>Core Meaning</span>
                            </div>
                            <p>{conceptDetails?.definition || selectedNode.description || 'Core concept extracted from study material.'}</p>
                          </div>

                          {/* Key Takeaway / Formula */}
                          {conceptDetails?.key_takeaway && (
                            <div className={`text-xs leading-relaxed font-medium p-3 rounded-2xl border ${
                              darkMode 
                                ? 'bg-amber-950/30 border-amber-800/50 text-amber-200' 
                                : 'bg-amber-50/70 border-amber-200/80 text-amber-950'
                            }`}>
                              <div className="flex items-center gap-1.5 font-black text-[11px] text-amber-700 dark:text-amber-400 uppercase tracking-wide mb-0.5">
                                <Lightbulb size={13} />
                                <span>Key Rule / Formula</span>
                              </div>
                              <p>{conceptDetails.key_takeaway}</p>
                            </div>
                          )}

                          {/* Exam Tip */}
                          {conceptDetails?.exam_tip && (
                            <div className={`text-xs leading-relaxed font-medium p-3 rounded-2xl border ${
                              darkMode 
                                ? 'bg-orange-950/30 border-orange-800/50 text-orange-200' 
                                : 'bg-orange-50/70 border-orange-200/80 text-orange-950'
                            }`}>
                              <div className="flex items-center gap-1.5 font-black text-[11px] text-orange-700 dark:text-orange-400 uppercase tracking-wide mb-0.5">
                                <Target size={13} />
                                <span>Exam Focus</span>
                              </div>
                              <p>{conceptDetails.exam_tip}</p>
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Direct Connections List */}
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className={`text-xs font-extrabold uppercase tracking-wider ${
                          darkMode ? 'text-slate-400' : 'text-slate-500'
                        }`}>
                          Connected Entities
                        </span>
                        <span className="text-xs font-black px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
                          {selectedNodeConnections.length}
                        </span>
                      </div>

                      <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                        {selectedNodeConnections.length === 0 ? (
                          <p className={`text-xs italic py-2 ${darkMode ? 'text-slate-500' : 'text-slate-400'}`}>
                            No direct connections found.
                          </p>
                        ) : (
                          selectedNodeConnections.map((conn, idx) => (
                            <div
                              key={idx}
                              onClick={() => conn.targetNode && setSelectedNode(conn.targetNode)}
                              className={`p-2.5 rounded-2xl border transition-all cursor-pointer flex items-center justify-between group ${
                                darkMode 
                                  ? 'bg-slate-800/50 border-slate-700/80 hover:bg-indigo-950/40 hover:border-indigo-500/50' 
                                  : 'bg-slate-50 border-slate-200/80 hover:bg-indigo-50 hover:border-indigo-200'
                              }`}
                            >
                              <div className="flex items-center gap-2.5">
                                <div
                                  className="w-3 h-3 rounded-full flex-shrink-0"
                                  style={{ backgroundColor: getNodeColor(conn.targetNode?.type).bg }}
                                />
                                <div>
                                  <p className="text-xs font-bold group-hover:text-indigo-400 transition-colors truncate max-w-[200px]">
                                    {conn.targetNode?.name}
                                  </p>
                                  {conn.edgeType && (
                                    <p className={`text-[10px] font-semibold mt-0.5 capitalize ${
                                      darkMode ? 'text-slate-400' : 'text-slate-500'
                                    }`}>
                                      {conn.edgeType.replace(/_/g, ' ')}
                                    </p>
                                  )}
                                </div>
                              </div>
                              <ChevronRight size={15} className={`group-hover:translate-x-1 transition-transform ${
                                darkMode ? 'text-slate-500 group-hover:text-indigo-400' : 'text-slate-400 group-hover:text-indigo-600'
                              }`} />
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2 mt-4 pt-3 border-t border-slate-200/60 dark:border-slate-800">
                    {onAskTutor && selectedNode.type !== 'document' && (
                      <button
                        onClick={() => {
                          const name = selectedNode.name
                          setSelectedNode(null)
                          onClose()
                          onAskTutor(name)
                        }}
                        className="w-full py-2.5 px-4 rounded-2xl font-black text-xs transition-all shadow-sm flex items-center justify-center gap-2 bg-orange-600 hover:bg-orange-700 text-white cursor-pointer"
                      >
                        <MessageSquare size={14} />
                        <span>Ask DeepTutor About "{selectedNode.name}"</span>
                      </button>
                    )}

                    <button
                      onClick={() => setSelectedNode(null)}
                      className={`w-full py-2.5 rounded-2xl font-bold text-xs transition-all border cursor-pointer ${
                        darkMode 
                          ? 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700' 
                          : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'
                      }`}
                    >
                      Close Inspection
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* ─── FOOTER BAR: ZOOM CONTROLS & ENTITY TYPE FILTERS ─── */}
          <div className={`flex flex-wrap items-center justify-between gap-4 px-6 py-3.5 border-t text-xs ${
            darkMode ? 'border-slate-800/80 bg-[#0F172A]/90 text-slate-300' : 'border-slate-100 bg-white text-slate-700'
          }`}>
            {/* Zoom & View Controls */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  camRef.current.zoom = Math.max(0.35, camRef.current.zoom - 0.15)
                  setZoom(camRef.current.zoom)
                }}
                className={`p-2 rounded-xl border transition-all ${
                  darkMode ? 'bg-slate-800/80 border-slate-700 hover:bg-slate-700' : 'bg-slate-100 border-slate-200 hover:bg-slate-200'
                }`}
                title="Zoom Out"
              >
                <ZoomOut size={15} />
              </button>
              
              <span className="font-extrabold w-12 text-center text-xs">
                {Math.round(zoom * 100)}%
              </span>

              <button
                onClick={() => {
                  camRef.current.zoom = Math.min(3.0, camRef.current.zoom + 0.15)
                  setZoom(camRef.current.zoom)
                }}
                className={`p-2 rounded-xl border transition-all ${
                  darkMode ? 'bg-slate-800/80 border-slate-700 hover:bg-slate-700' : 'bg-slate-100 border-slate-200 hover:bg-slate-200'
                }`}
                title="Zoom In"
              >
                <ZoomIn size={15} />
              </button>

              <button
                onClick={resetView}
                className={`flex items-center gap-1.5 font-bold px-3.5 py-2 rounded-xl border transition-all ml-2 ${
                  darkMode ? 'bg-slate-800/80 border-slate-700 hover:bg-slate-700' : 'bg-slate-100 border-slate-200 hover:bg-slate-200'
                }`}
              >
                <RefreshCw size={13} /> Reset View
              </button>
            </div>

            {/* Entity Types Filter Bar */}
            <div className="flex items-center gap-3 overflow-x-auto max-w-full py-1">
              <span className={`text-[10px] font-extrabold uppercase tracking-wider flex items-center gap-1 ${
                darkMode ? 'text-slate-400' : 'text-slate-400'
              }`}>
                <Filter size={12} /> Entity Filter:
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setSelectedTypeFilter(null)}
                  className={`px-3 py-1 rounded-xl text-xs font-bold transition-all ${
                    selectedTypeFilter === null
                      ? (darkMode ? 'bg-indigo-600 text-white shadow-md' : 'bg-slate-900 text-white')
                      : (darkMode ? 'bg-slate-800/60 border border-slate-700/60 text-slate-400 hover:text-slate-200' : 'bg-slate-100 border border-slate-200 text-slate-600')
                  }`}
                >
                  All ({entities.length})
                </button>

                {uniqueTypes.map((type) => {
                  const colors = getNodeColor(type)
                  const count = entities.filter((e) => e.type?.toLowerCase() === type).length
                  const isSelected = selectedTypeFilter === type

                  return (
                    <button
                      key={type}
                      onClick={() => setSelectedTypeFilter(isSelected ? null : type)}
                      className={`flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-bold transition-all border ${
                        isSelected
                          ? (darkMode ? 'bg-indigo-500/30 border-indigo-500 text-white' : 'bg-indigo-50 border-indigo-300 text-indigo-700')
                          : (darkMode ? 'bg-slate-800/60 border-slate-700/60 text-slate-300 hover:border-slate-600' : 'bg-white border-slate-200 text-slate-700 hover:border-slate-300')
                      }`}
                    >
                      <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: colors.bg }} />
                      <span className="capitalize">{type}</span>
                      <span className={`text-[10px] opacity-75 font-normal`}>({count})</span>
                    </button>
                  )
                })}
              </div>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}

export default memo(GraphContextPanel)
