import confetti from 'canvas-confetti'

export function triggerConfettiBurst() {
  try {
    confetti({
      particleCount: 55,
      spread: 65,
      origin: { y: 0.65 },
      colors: ['#4F46E5', '#818CF8', '#10B981', '#F59E0B', '#6366F1'],
      disableForReducedMotion: true,
    })
  } catch {
    // Fallback gracefully if canvas is blocked
  }
}

export function triggerQuizSuccessConfetti() {
  try {
    const end = Date.now() + 1000
    const colors = ['#4F46E5', '#10B981', '#818CF8']

    ;(function frame() {
      confetti({
        particleCount: 3,
        angle: 60,
        spread: 55,
        origin: { x: 0 },
        colors: colors,
        disableForReducedMotion: true,
      })
      confetti({
        particleCount: 3,
        angle: 120,
        spread: 55,
        origin: { x: 1 },
        colors: colors,
        disableForReducedMotion: true,
      })

      if (Date.now() < end) {
        requestAnimationFrame(frame)
      }
    })()
  } catch {
    // Fallback gracefully
  }
}
