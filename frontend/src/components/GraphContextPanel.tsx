import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Network, X, ZoomIn, ZoomOut, RefreshCw, Maximize2, Minimize2, MousePointer } from 'lucide-react'

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

/* ─── Color palette ──────────────────────────────────────────── */
const NODE_TYPE_COLORS: Record<string, string> = {
  concept:    '#818cf8',
  person:     '#fbbf24',
  place:      '#34d399',
  event:      '#f87171',
  formula:    '#22d3ee',
  law:        '#a78bfa',
  theorem:    '#f472b6',
  example_of: '#94a3b8',
}

const NODE_TYPE_GLOW: Record<string, string> = {
  concept:    'rgba(129,140,248,0.45)',
  person:     'rgba(251,191,36,0.45)',
  place:      'rgba(52,211,153,0.45)',
  event:      'rgba(248,113,113,0.45)',
  formula:    'rgba(34,211,238,0.45)',
  law:        'rgba(167,139,250,0.45)',
  theorem:    'rgba(244,114,182,0.45)',
  example_of: 'rgba(148,163,184,0.45)',
}

function getColor(type: string): string {
  return NODE_TYPE_COLORS[type?.toLowerCase()] ?? '#818cf8'
}
function getGlow(type: string): string {
  return NODE_TYPE_GLOW[type?.toLowerCase()] ?? 'rgba(129,140,248,0.45)'
}

/* ─── Force simulation types ─────────────────────────────────── */
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

/* ─── Main component ─────────────────────────────────────────── */
export default function GraphContextPanel({ entities, relationships, isOpen, onClose }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const animRef = useRef<number>(0)
  const nodesRef = useRef<SimNode[]>([])
  const edgesRef = useRef<SimEdge[]>([])

  // Camera state
  const [zoom, setZoom] = useState(1)
  const camRef = useRef({ x: 0, y: 0, zoom: 1 })

  // Interaction state
  const [selectedNode, setSelectedNode] = useState<SimNode | null>(null)
  const [hoveredNode, setHoveredNode] = useState<SimNode | null>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const dragRef = useRef<{ node: SimNode | null; offsetX: number; offsetY: number; isPanning: boolean; startX: number; startY: number; startCamX: number; startCamY: number }>({
    node: null, offsetX: 0, offsetY: 0, isPanning: false, startX: 0, startY: 0, startCamX: 0, startCamY: 0
  })

  const tickRef = useRef(0)

  /* ─── Initialize simulation ────────────────────────────────── */
  useEffect(() => {
    if (!entities.length || !isOpen) return

    const W = containerRef.current?.clientWidth ?? 900
    const H = containerRef.current?.clientHeight ?? 600
    const cx = W / 2
    const cy = H / 2

    const nodeRadius = Math.max(18, Math.min(28, 300 / Math.sqrt(entities.length)))
    const layoutRadius = Math.min(W, H) * 0.32

    const nodes: SimNode[] = entities.map((e, i) => {
      const angle = (2 * Math.PI * i) / entities.length - Math.PI / 2
      return {
        id: e.id,
        x: cx + layoutRadius * Math.cos(angle) + (Math.random() - 0.5) * 40,
        y: cy + layoutRadius * Math.sin(angle) + (Math.random() - 0.5) * 40,
        vx: 0,
        vy: 0,
        name: e.name || e.id,
        type: e.type || 'concept',
        description: e.description || '',
        radius: nodeRadius,
        pinned: false,
      }
    })

    const edges: SimEdge[] = relationships.map(r => ({
      source: r.source,
      target: r.target,
      type: r.type || '',
      description: r.description || '',
    }))

    nodesRef.current = nodes
    edgesRef.current = edges
    tickRef.current = 0

    // Reset camera
    camRef.current = { x: 0, y: 0, zoom: 1 }
    setZoom(1)
    setSelectedNode(null)
    setHoveredNode(null)
  }, [entities, relationships, isOpen])

  /* ─── Force simulation tick ────────────────────────────────── */
  const simulate = useCallback(() => {
    const nodes = nodesRef.current
    const edges = edgesRef.current
    if (!nodes.length) return

    const W = containerRef.current?.clientWidth ?? 900
    const H = containerRef.current?.clientHeight ?? 600
    const cx = W / 2
    const cy = H / 2

    // Cooling: reduce forces over time
    const cooling = Math.max(0.01, 1 - tickRef.current * 0.004)
    tickRef.current++

    // Repulsion between all nodes (Coulomb-like)
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j]
        let dx = b.x - a.x
        let dy = b.y - a.y
        let dist = Math.sqrt(dx * dx + dy * dy) || 1
        const minDist = (a.radius + b.radius) * 3
        const force = (3000 * cooling) / (dist * dist)
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        if (!a.pinned) { a.vx -= fx; a.vy -= fy }
        if (!b.pinned) { b.vx += fx; b.vy += fy }

        // Hard collision
        if (dist < minDist) {
          const overlap = (minDist - dist) / 2
          const ox = (dx / dist) * overlap
          const oy = (dy / dist) * overlap
          if (!a.pinned) { a.x -= ox; a.y -= oy }
          if (!b.pinned) { b.x += ox; b.y += oy }
        }
      }
    }

    // Spring force along edges
    const idealLen = Math.max(100, 400 / Math.sqrt(nodes.length))
    for (const edge of edges) {
      const a = nodes.find(n => n.id === edge.source)
      const b = nodes.find(n => n.id === edge.target)
      if (!a || !b) continue
      let dx = b.x - a.x
      let dy = b.y - a.y
      let dist = Math.sqrt(dx * dx + dy * dy) || 1
      const force = (dist - idealLen) * 0.04 * cooling
      const fx = (dx / dist) * force
      const fy = (dy / dist) * force
      if (!a.pinned) { a.vx += fx; a.vy += fy }
      if (!b.pinned) { b.vx -= fx; b.vy -= fy }
    }

    // Center gravity
    for (const node of nodes) {
      if (node.pinned) continue
      node.vx += (cx - node.x) * 0.003 * cooling
      node.vy += (cy - node.y) * 0.003 * cooling

      // Damping
      node.vx *= 0.85
      node.vy *= 0.85

      // Apply velocity
      node.x += node.vx
      node.y += node.vy

      // Bounds
      const margin = node.radius + 10
      node.x = Math.max(margin, Math.min(W - margin, node.x))
      node.y = Math.max(margin, Math.min(H - margin, node.y))
    }
  }, [])

  /* ─── Canvas rendering ─────────────────────────────────────── */
  const render = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const W = canvas.width
    const H = canvas.height
    const cam = camRef.current
    const nodes = nodesRef.current
    const edges = edgesRef.current
    const selected = selectedNode
    const hovered = hoveredNode
    const time = Date.now() / 1000

    // Clear
    ctx.clearRect(0, 0, W, H)
    ctx.save()

    // Camera transform
    ctx.translate(W / 2, H / 2)
    ctx.scale(cam.zoom, cam.zoom)
    ctx.translate(-W / 2 + cam.x, -H / 2 + cam.y)

    // Build adjacency for highlighting
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

    // ─── Draw edges ──────────────────────────────────
    edges.forEach((edge, i) => {
      const src = nodes.find(n => n.id === edge.source)
      const tgt = nodes.find(n => n.id === edge.target)
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
      const isDimmed = selected && !isHighlighted

      // Edge line
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.lineTo(x2, y2)
      ctx.strokeStyle = isDimmed
        ? 'rgba(100,116,139,0.08)'
        : isHighlighted
          ? 'rgba(129,140,248,0.7)'
          : 'rgba(100,116,139,0.25)'
      ctx.lineWidth = isHighlighted ? 2.5 : 1.5
      ctx.stroke()

      // Arrowhead
      const arrowLen = isHighlighted ? 10 : 7
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
      ctx.fillStyle = isDimmed
        ? 'rgba(100,116,139,0.08)'
        : isHighlighted
          ? 'rgba(129,140,248,0.8)'
          : 'rgba(100,116,139,0.3)'
      ctx.fill()

      // Edge label
      if (edge.type && !isDimmed) {
        const mx = (src.x + tgt.x) / 2
        const my = (src.y + tgt.y) / 2
        ctx.save()
        ctx.font = `${isHighlighted ? 11 : 9}px Inter, sans-serif`
        ctx.fillStyle = isHighlighted ? 'rgba(129,140,248,0.9)' : 'rgba(100,116,139,0.5)'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'bottom'
        const label = edge.type.replace(/_/g, ' ')
        // Background pill
        const textWidth = ctx.measureText(label).width
        if (isHighlighted) {
          ctx.fillStyle = 'rgba(30,27,75,0.7)'
          const px = 6, py = 3
          ctx.beginPath()
          const rx = mx - textWidth / 2 - px
          const ry = my - 16 - py
          const rw = textWidth + px * 2
          const rh = 14 + py * 2
          const r = 4
          ctx.moveTo(rx + r, ry)
          ctx.arcTo(rx + rw, ry, rx + rw, ry + rh, r)
          ctx.arcTo(rx + rw, ry + rh, rx, ry + rh, r)
          ctx.arcTo(rx, ry + rh, rx, ry, r)
          ctx.arcTo(rx, ry, rx + rw, ry, r)
          ctx.closePath()
          ctx.fill()
          ctx.fillStyle = 'rgba(165,180,252,0.95)'
        }
        ctx.fillText(label, mx, my - 6)
        ctx.restore()
      }
    })

    // ─── Draw nodes ──────────────────────────────────
    nodes.forEach((node) => {
      const color = getColor(node.type)
      const glow = getGlow(node.type)
      const isSelected = selected?.id === node.id
      const isHovered = hovered?.id === node.id
      const isConnected = connectedIds.has(node.id)
      const isDimmed = selected && !isConnected

      const r = node.radius
      const breathe = 1 + Math.sin(time * 2 + node.x * 0.01) * 0.03

      // Glow ring (for selected/hovered)
      if ((isSelected || isHovered) && !isDimmed) {
        const glowR = r * 2.2 * breathe
        const gradient = ctx.createRadialGradient(node.x, node.y, r * 0.5, node.x, node.y, glowR)
        gradient.addColorStop(0, glow)
        gradient.addColorStop(1, 'rgba(0,0,0,0)')
        ctx.beginPath()
        ctx.arc(node.x, node.y, glowR, 0, Math.PI * 2)
        ctx.fillStyle = gradient
        ctx.fill()
      }

      // Outer ring
      if (!isDimmed) {
        ctx.beginPath()
        ctx.arc(node.x, node.y, r + 3, 0, Math.PI * 2)
        ctx.strokeStyle = isSelected
          ? color
          : isHovered
            ? color
            : 'rgba(100,116,139,0.15)'
        ctx.lineWidth = isSelected ? 3 : isHovered ? 2.5 : 1
        ctx.stroke()
      }

      // Main circle
      ctx.beginPath()
      ctx.arc(node.x, node.y, r, 0, Math.PI * 2)
      const grad = ctx.createRadialGradient(node.x - r * 0.3, node.y - r * 0.3, r * 0.1, node.x, node.y, r)
      if (isDimmed) {
        grad.addColorStop(0, 'rgba(148,163,184,0.15)')
        grad.addColorStop(1, 'rgba(100,116,139,0.08)')
      } else {
        grad.addColorStop(0, color)
        grad.addColorStop(1, color + 'cc')
      }
      ctx.fillStyle = grad
      ctx.fill()

      // Inner highlight (glass effect)
      if (!isDimmed) {
        ctx.beginPath()
        ctx.arc(node.x - r * 0.2, node.y - r * 0.25, r * 0.45, 0, Math.PI * 2)
        ctx.fillStyle = 'rgba(255,255,255,0.2)'
        ctx.fill()
      }

      // Label
      const label = node.name.length > 20 ? node.name.slice(0, 18) + '…' : node.name
      ctx.font = `${isDimmed ? '500' : '600'} ${isSelected || isHovered ? 13 : 11}px Inter, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'

      if (!isDimmed) {
        // Text shadow / outline for readability
        const textY = node.y + r + 8
        ctx.fillStyle = 'rgba(255,255,255,0.85)'
        const tw = ctx.measureText(label).width
        const px = 6, py = 2
        ctx.beginPath()
        const rx = node.x - tw / 2 - px
        const ry = textY - py
        const rw = tw + px * 2
        const rh = 16 + py * 2
        const br = 6
        ctx.moveTo(rx + br, ry)
        ctx.arcTo(rx + rw, ry, rx + rw, ry + rh, br)
        ctx.arcTo(rx + rw, ry + rh, rx, ry + rh, br)
        ctx.arcTo(rx, ry + rh, rx, ry, br)
        ctx.arcTo(rx, ry, rx + rw, ry, br)
        ctx.closePath()
        ctx.fillStyle = 'rgba(255,255,255,0.88)'
        ctx.fill()
        ctx.strokeStyle = 'rgba(99,102,241,0.12)'
        ctx.lineWidth = 1
        ctx.stroke()

        ctx.fillStyle = isSelected ? '#312e81' : '#334155'
        ctx.fillText(label, node.x, textY + 1)
      } else {
        ctx.fillStyle = 'rgba(148,163,184,0.3)'
        ctx.fillText(label, node.x, node.y + r + 8)
      }

      // Type badge (only when hovered/selected)
      if ((isSelected || isHovered) && !isDimmed) {
        const typeLabel = node.type.charAt(0).toUpperCase() + node.type.slice(1)
        ctx.font = '500 9px Inter, sans-serif'
        const tw2 = ctx.measureText(typeLabel).width
        const badgeX = node.x
        const badgeY = node.y - r - 14
        const bpx = 5, bpy = 2
        ctx.beginPath()
        const brx = badgeX - tw2 / 2 - bpx
        const bry = badgeY - bpy - 4
        const brw = tw2 + bpx * 2
        const brh = 14 + bpy
        const bbr = 5
        ctx.moveTo(brx + bbr, bry)
        ctx.arcTo(brx + brw, bry, brx + brw, bry + brh, bbr)
        ctx.arcTo(brx + brw, bry + brh, brx, bry + brh, bbr)
        ctx.arcTo(brx, bry + brh, brx, bry, bbr)
        ctx.arcTo(brx, bry, brx + brw, bry, bbr)
        ctx.closePath()
        ctx.fillStyle = color + '22'
        ctx.fill()
        ctx.strokeStyle = color + '55'
        ctx.lineWidth = 1
        ctx.stroke()
        ctx.fillStyle = color
        ctx.textBaseline = 'middle'
        ctx.textAlign = 'center'
        ctx.fillText(typeLabel, badgeX, badgeY + 2)
      }
    })

    ctx.restore()
  }, [selectedNode, hoveredNode])

  /* ─── Animation loop ───────────────────────────────────────── */
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

  /* ─── Resize canvas ────────────────────────────────────────── */
  useEffect(() => {
    if (!isOpen) return
    const resize = () => {
      const canvas = canvasRef.current
      const container = containerRef.current
      if (!canvas || !container) return
      const dpr = window.devicePixelRatio || 1
      canvas.width = container.clientWidth * dpr
      canvas.height = container.clientHeight * dpr
      canvas.style.width = container.clientWidth + 'px'
      canvas.style.height = container.clientHeight + 'px'
      const ctx = canvas.getContext('2d')
      if (ctx) ctx.scale(dpr, dpr)
      // Update internal W/H used by simulation
      camRef.current = { ...camRef.current }
    }
    resize()
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [isOpen, isFullscreen])

  /* ─── Hit test ─────────────────────────────────────────────── */
  const hitTest = useCallback((clientX: number, clientY: number): SimNode | null => {
    const canvas = canvasRef.current
    if (!canvas) return null
    const rect = canvas.getBoundingClientRect()
    const cam = camRef.current
    const scaleX = canvas.width / (window.devicePixelRatio || 1) / rect.width
    const scaleY = canvas.height / (window.devicePixelRatio || 1) / rect.height
    const mx = (clientX - rect.left) * scaleX
    const my = (clientY - rect.top) * scaleY

    // Transform mouse to world coords
    const W = canvas.width / (window.devicePixelRatio || 1)
    const H = canvas.height / (window.devicePixelRatio || 1)
    const wx = (mx - W / 2) / cam.zoom + W / 2 - cam.x
    const wy = (my - H / 2) / cam.zoom + H / 2 - cam.y

    for (let i = nodesRef.current.length - 1; i >= 0; i--) {
      const node = nodesRef.current[i]
      const dx = wx - node.x
      const dy = wy - node.y
      if (dx * dx + dy * dy <= (node.radius + 6) * (node.radius + 6)) {
        return node
      }
    }
    return null
  }, [])

  /* ─── Mouse event handlers ─────────────────────────────────── */
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    const node = hitTest(e.clientX, e.clientY)
    if (node) {
      dragRef.current = {
        node,
        offsetX: 0,
        offsetY: 0,
        isPanning: false,
        startX: e.clientX,
        startY: e.clientY,
        startCamX: camRef.current.x,
        startCamY: camRef.current.y,
      }
      node.pinned = true
    } else {
      // Start panning
      dragRef.current = {
        node: null,
        offsetX: 0,
        offsetY: 0,
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
      if (!canvas) return
      const rect = canvas.getBoundingClientRect()
      const cam = camRef.current
      const W = canvas.width / (window.devicePixelRatio || 1)
      const H = canvas.height / (window.devicePixelRatio || 1)
      const scaleX = W / rect.width
      const scaleY = H / rect.height
      const mx = (e.clientX - rect.left) * scaleX
      const my = (e.clientY - rect.top) * scaleY
      const wx = (mx - W / 2) / cam.zoom + W / 2 - cam.x
      const wy = (my - H / 2) / cam.zoom + H / 2 - cam.y

      drag.node.x = wx
      drag.node.y = wy
      drag.node.vx = 0
      drag.node.vy = 0
      return
    }

    // Hover detection
    const node = hitTest(e.clientX, e.clientY)
    setHoveredNode(node)
    if (canvasRef.current) {
      canvasRef.current.style.cursor = node ? 'grab' : 'default'
    }
  }, [hitTest])

  const handleMouseUp = useCallback(() => {
    const drag = dragRef.current
    if (drag.node) {
      // If it was just a click (not a drag), toggle selection
      drag.node.pinned = false
    }
    dragRef.current = { node: null, offsetX: 0, offsetY: 0, isPanning: false, startX: 0, startY: 0, startCamX: 0, startCamY: 0 }
  }, [])

  const handleClick = useCallback((e: React.MouseEvent) => {
    const node = hitTest(e.clientX, e.clientY)
    if (node) {
      setSelectedNode(prev => prev?.id === node.id ? null : node)
    } else {
      setSelectedNode(null)
    }
  }, [hitTest])

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    const delta = e.deltaY > 0 ? 0.9 : 1.1
    const newZoom = Math.max(0.3, Math.min(3, camRef.current.zoom * delta))
    camRef.current.zoom = newZoom
    setZoom(newZoom)
  }, [])

  const resetView = useCallback(() => {
    camRef.current = { x: 0, y: 0, zoom: 1 }
    setZoom(1)
    setSelectedNode(null)
    setHoveredNode(null)
    tickRef.current = 0
    // Re-randomize positions
    const W = containerRef.current?.clientWidth ?? 900
    const H = containerRef.current?.clientHeight ?? 600
    const cx = W / 2
    const cy = H / 2
    const layoutRadius = Math.min(W, H) * 0.32
    nodesRef.current.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / nodesRef.current.length - Math.PI / 2
      node.x = cx + layoutRadius * Math.cos(angle) + (Math.random() - 0.5) * 40
      node.y = cy + layoutRadius * Math.sin(angle) + (Math.random() - 0.5) * 40
      node.vx = 0
      node.vy = 0
      node.pinned = false
    })
  }, [])

  if (!isOpen) return null

  const connectedCount = selectedNode
    ? edgesRef.current.filter(e => e.source === selectedNode.id || e.target === selectedNode.id).length
    : 0

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.25 }}
        className={`fixed inset-0 z-50 flex items-center justify-center ${isFullscreen ? 'p-0' : 'p-4 md:p-8'}`}
        style={{ background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(8px)' }}
      >
        <motion.div
          initial={{ scale: 0.92, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.92, opacity: 0 }}
          transition={{ type: 'spring', stiffness: 400, damping: 30 }}
          className={`relative flex flex-col overflow-hidden ${
            isFullscreen
              ? 'w-full h-full rounded-none'
              : 'w-full max-w-5xl rounded-2xl shadow-2xl'
          }`}
          style={{
            height: isFullscreen ? '100%' : 'min(85vh, 700px)',
            background: 'rgba(255,255,255,0.95)',
            border: '1px solid rgba(99,102,241,0.15)',
            boxShadow: '0 25px 80px rgba(0,0,0,0.15), 0 0 60px rgba(99,102,241,0.08)',
          }}
        >
          {/* ─── Header ───────────────────────────────────── */}
          <div className="flex items-center gap-3 px-5 py-3.5 border-b border-[rgba(99,102,241,0.1)]"
            style={{ background: 'rgba(248,250,252,0.9)' }}
          >
            <div className="w-9 h-9 rounded-xl flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.15), rgba(139,92,246,0.15))' }}
            >
              <Network size={18} className="text-indigo-500" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-bold" style={{ color: '#1e293b' }}>Knowledge Graph</p>
              <p className="text-[11px]" style={{ color: '#94a3b8' }}>
                {entities.length} entities · {relationships.length} relations
                {selectedNode && <span style={{ color: '#6366f1' }}> · {selectedNode.name} selected ({connectedCount} connections)</span>}
              </p>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setIsFullscreen(!isFullscreen)}
                className="p-2 rounded-lg transition-all hover:bg-indigo-50"
                title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
                style={{ color: '#64748b' }}
              >
                {isFullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
              </button>
              <button
                onClick={onClose}
                className="p-2 rounded-lg transition-all hover:bg-red-50"
                title="Close"
                style={{ color: '#64748b' }}
              >
                <X size={15} />
              </button>
            </div>
          </div>

          {/* ─── Canvas area ──────────────────────────────── */}
          <div ref={containerRef} className="flex-1 relative overflow-hidden" style={{ background: '#fafbfe' }}>
            {entities.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <Network size={48} className="mb-3" style={{ color: '#cbd5e1' }} />
                <p className="text-sm font-medium" style={{ color: '#94a3b8' }}>No graph context retrieved yet</p>
                <p className="text-xs mt-1" style={{ color: '#cbd5e1' }}>Upload a document and ask a question</p>
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
                style={{ width: '100%', height: '100%', display: 'block' }}
              />
            )}

            {/* ─── Interaction hint ──────────────────────── */}
            <div className="absolute top-3 left-3 flex items-center gap-2 px-3 py-1.5 rounded-lg"
              style={{
                background: 'rgba(255,255,255,0.85)',
                border: '1px solid rgba(99,102,241,0.1)',
                backdropFilter: 'blur(10px)',
              }}
            >
              <MousePointer size={11} style={{ color: '#94a3b8' }} />
              <span className="text-[10px]" style={{ color: '#94a3b8' }}>Click node to select · Drag to move · Scroll to zoom · Drag canvas to pan</span>
            </div>

            {/* ─── Selected node detail card ──────────────── */}
            <AnimatePresence>
              {selectedNode && (
                <motion.div
                  initial={{ opacity: 0, y: 20, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 20, scale: 0.95 }}
                  transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                  className="absolute bottom-4 left-4 right-4 md:left-auto md:right-4 md:w-80 rounded-xl p-4 z-10"
                  style={{
                    background: 'rgba(255,255,255,0.95)',
                    border: '1px solid rgba(99,102,241,0.15)',
                    backdropFilter: 'blur(20px)',
                    boxShadow: '0 15px 40px rgba(0,0,0,0.1)',
                  }}
                >
                  <div className="flex items-center gap-2.5 mb-2">
                    <div
                      className="w-4 h-4 rounded-full flex-shrink-0"
                      style={{
                        background: getColor(selectedNode.type),
                        boxShadow: `0 0 12px ${getGlow(selectedNode.type)}`,
                      }}
                    />
                    <p className="text-sm font-bold" style={{ color: '#1e293b' }}>
                      {selectedNode.name}
                    </p>
                    <span className="text-[10px] px-2 py-0.5 rounded-full font-medium ml-auto capitalize"
                      style={{
                        background: getColor(selectedNode.type) + '18',
                        color: getColor(selectedNode.type),
                        border: `1px solid ${getColor(selectedNode.type)}33`,
                      }}
                    >
                      {selectedNode.type}
                    </span>
                  </div>
                  {selectedNode.description && (
                    <p className="text-xs leading-relaxed" style={{ color: '#64748b' }}>
                      {selectedNode.description}
                    </p>
                  )}
                  <div className="mt-2 pt-2 flex items-center gap-3" style={{ borderTop: '1px solid rgba(99,102,241,0.08)' }}>
                    <span className="text-[10px] font-medium" style={{ color: '#94a3b8' }}>
                      {connectedCount} connection{connectedCount !== 1 ? 's' : ''}
                    </span>
                    <button
                      onClick={() => setSelectedNode(null)}
                      className="text-[10px] ml-auto px-2 py-1 rounded-md transition-all hover:bg-indigo-50"
                      style={{ color: '#6366f1' }}
                    >
                      Deselect
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* ─── Footer controls ──────────────────────────── */}
          <div className="flex items-center justify-between px-5 py-3 border-t border-[rgba(99,102,241,0.1)]"
            style={{ background: 'rgba(248,250,252,0.9)' }}
          >
            {/* Zoom controls */}
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => {
                  camRef.current.zoom = Math.max(0.3, camRef.current.zoom - 0.2)
                  setZoom(camRef.current.zoom)
                }}
                className="p-1.5 rounded-lg transition-all hover:bg-indigo-50"
                style={{ color: '#64748b' }}
              >
                <ZoomOut size={14} />
              </button>
              <span className="text-xs font-medium w-12 text-center" style={{ color: '#64748b' }}>
                {Math.round(zoom * 100)}%
              </span>
              <button
                onClick={() => {
                  camRef.current.zoom = Math.min(3, camRef.current.zoom + 0.2)
                  setZoom(camRef.current.zoom)
                }}
                className="p-1.5 rounded-lg transition-all hover:bg-indigo-50"
                style={{ color: '#64748b' }}
              >
                <ZoomIn size={14} />
              </button>
              <div className="w-px h-4 mx-1" style={{ background: 'rgba(99,102,241,0.1)' }} />
              <button
                onClick={resetView}
                className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg transition-all hover:bg-indigo-50"
                style={{ color: '#64748b' }}
              >
                <RefreshCw size={11} /> Reset
              </button>
            </div>

            {/* Legend */}
            <div className="flex items-center gap-3">
              <span className="text-[9px] font-semibold uppercase tracking-wider" style={{ color: '#94a3b8' }}>Legend</span>
              <div className="flex flex-wrap gap-2.5">
                {Object.entries(NODE_TYPE_COLORS).slice(0, 6).map(([type, color]) => (
                  <div key={type} className="flex items-center gap-1">
                    <div className="w-2.5 h-2.5 rounded-full" style={{ background: color, boxShadow: `0 0 6px ${color}55` }} />
                    <span className="text-[10px] capitalize" style={{ color: '#64748b' }}>{type}</span>
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
