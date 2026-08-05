import { useEffect, useState } from 'react'
import { motion, useSpring } from 'framer-motion'

export default function MouseSpotlight() {
  const [isHovered, setIsHovered] = useState(false)
  const [isVisible, setIsVisible] = useState(false)

  // Smooth springs for fluid mouse tracking
  const mouseX = useSpring(0, { stiffness: 400, damping: 28 })
  const mouseY = useSpring(0, { stiffness: 400, damping: 28 })

  // Larger secondary glow trailing behind
  const trailX = useSpring(0, { stiffness: 120, damping: 20 })
  const trailY = useSpring(0, { stiffness: 120, damping: 20 })

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isVisible) setIsVisible(true)
      mouseX.set(e.clientX)
      mouseY.set(e.clientY)
      trailX.set(e.clientX)
      trailY.set(e.clientY)

      // Detect hover over interactive elements
      const target = e.target as HTMLElement | null
      if (target) {
        const isInteractive = Boolean(
          target.closest('button, a, input, textarea, [role="button"], .glass-card, .sidebar-item')
        )
        setIsHovered(isInteractive)
      }
    }

    const handleMouseLeave = () => setIsVisible(false)

    window.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseleave', handleMouseLeave)

    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseleave', handleMouseLeave)
    }
  }, [mouseX, mouseY, trailX, trailY, isVisible])

  if (!isVisible) return null

  return (
    <div className="pointer-events-none fixed inset-0 z-50 overflow-hidden">
      {/* ── Outer Trailing Ambient Glow ── */}
      <motion.div
        style={{
          x: trailX,
          y: trailY,
          translateX: '-50%',
          translateY: '-50%',
        }}
        animate={{
          scale: isHovered ? 1.5 : 1,
          opacity: isHovered ? 0.3 : 0.15,
        }}
        transition={{ duration: 0.2 }}
        className="absolute w-96 h-96 rounded-full bg-gradient-to-r from-indigo-500/20 via-violet-400/15 to-cyan-400/15 blur-3xl"
      />

      {/* ── Inner Cursor Spotlight Ring ── */}
      <motion.div
        style={{
          x: mouseX,
          y: mouseY,
          translateX: '-50%',
          translateY: '-50%',
        }}
        animate={{
          scale: isHovered ? 1.6 : 1,
          borderWidth: isHovered ? '2px' : '1px',
        }}
        transition={{ type: 'spring', stiffness: 500, damping: 30 }}
        className={`absolute rounded-full border transition-colors ${
          isHovered
            ? 'w-12 h-12 border-indigo-600 bg-indigo-500/10 shadow-[0_0_20px_rgba(99,102,241,0.3)]'
            : 'w-8 h-8 border-indigo-400/30 bg-indigo-400/5'
        }`}
      />

      {/* ── Core Dot Cursor ── */}
      <motion.div
        style={{
          x: mouseX,
          y: mouseY,
          translateX: '-50%',
          translateY: '-50%',
        }}
        animate={{
          scale: isHovered ? 0.5 : 1,
        }}
        className="absolute w-2 h-2 rounded-full bg-indigo-600 shadow-[0_0_8px_#6366f1]"
      />
    </div>
  )
}
