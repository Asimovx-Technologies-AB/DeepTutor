import confetti from 'canvas-confetti'

export function triggerConfettiBurst() {
  try {
    confetti({
      particleCount: 55,
      spread: 65,
      origin: { y: 0.65 },
      colors: ['#F28A45', '#0284C7', '#10B981', '#FFD166', '#EF476F'],
      disableForReducedMotion: true,
    })
  } catch {
    // Fallback gracefully if canvas is blocked
  }
}

export function triggerQuizSuccessConfetti() {
  try {
    const end = Date.now() + 1000
    const colors = ['#10B981', '#F28A45', '#0284C7']

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
