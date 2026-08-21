import { type Variants, type Transition } from 'framer-motion'

// ─── Default Spring & Ease Transitions ─────────────────────────────────────────
export const smoothTransition: Transition = {
  type: 'spring',
  stiffness: 380,
  damping: 30,
}

export const gentleTransition: Transition = {
  duration: 0.35,
  ease: [0.16, 1, 0.3, 1],
}

// ─── Fade In & Up ─────────────────────────────────────────────────────────────
export const fadeInUp: Variants = {
  initial: { opacity: 0, y: 15 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.35, ease: 'easeOut' as const } },
  exit: { opacity: 0, y: -10, transition: { duration: 0.2 } },
}

// ─── Scale In ─────────────────────────────────────────────────────────────────
export const scaleIn: Variants = {
  initial: { scale: 0.85, opacity: 0 },
  animate: { scale: 1, opacity: 1, transition: { type: 'spring', stiffness: 400, damping: 25 } },
  exit: { scale: 0.9, opacity: 0, transition: { duration: 0.15 } },
}

// ─── Stagger Children Container ───────────────────────────────────────────────
export const staggerContainer: Variants = {
  initial: {},
  animate: {
    transition: {
      staggerChildren: 0.08,
      delayChildren: 0.05,
    },
  },
}

export const staggerItem: Variants = {
  initial: { opacity: 0, y: 12 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.3, ease: 'easeOut' as const },
  },
  exit: { opacity: 0, scale: 0.95, transition: { duration: 0.15 } },
}

// ─── Interactive Card Hover ───────────────────────────────────────────────────
export const cardHover = {
  hover: {
    y: -4,
    boxShadow: '0 12px 30px -8px rgba(0, 0, 0, 0.08), 0 4px 10px -2px rgba(0, 0, 0, 0.03)',
    transition: { duration: 0.2, ease: 'easeOut' as const },
  },
  tap: {
    scale: 0.98,
    transition: { duration: 0.1 },
  },
}

// ─── Button Tap Feedback ──────────────────────────────────────────────────────
export const buttonPress = {
  tap: { scale: 0.95 },
  hover: { scale: 1.02 },
}

// ─── Shake Animation (Wrong File / Error) ──────────────────────────────────────
export const errorShake: Variants = {
  idle: { x: 0 },
  shake: {
    x: [0, -8, 8, -6, 6, -3, 3, 0],
    transition: { duration: 0.45, ease: 'easeInOut' },
  },
}

// ─── Accordion Smooth Height ──────────────────────────────────────────────────
export const accordionVariants: Variants = {
  collapsed: {
    opacity: 0,
    height: 0,
    overflow: 'hidden',
    transition: { duration: 0.25, ease: [0.04, 0.62, 0.23, 0.98] },
  },
  open: {
    opacity: 1,
    height: 'auto',
    overflow: 'hidden',
    transition: { duration: 0.35, ease: [0.04, 0.62, 0.23, 0.98] },
  },
}

// ─── Toast Slide In ───────────────────────────────────────────────────────────
export const toastVariants: Variants = {
  initial: { x: 80, opacity: 0, scale: 0.9 },
  animate: { x: 0, opacity: 1, scale: 1, transition: { type: 'spring', stiffness: 450, damping: 30 } },
  exit: { x: 60, opacity: 0, scale: 0.9, transition: { duration: 0.2 } },
}

// ─── Looping Mascot Pulse ─────────────────────────────────────────────────────
export const pulsingMascot: Variants = {
  pulse: {
    scale: [1, 1.08, 1],
    rotate: [0, -2, 2, 0],
    transition: {
      duration: 2.2,
      repeat: Infinity,
      ease: 'easeInOut',
    },
  },
}

// ─── SVG Animated Checkmark Path ──────────────────────────────────────────────
export const checkmarkPath: Variants = {
  hidden: { pathLength: 0, opacity: 0 },
  visible: {
    pathLength: 1,
    opacity: 1,
    transition: {
      pathLength: { duration: 0.45, ease: 'easeInOut' },
      opacity: { duration: 0.1 },
    },
  },
}
