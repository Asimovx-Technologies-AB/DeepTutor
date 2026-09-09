import { useEffect, useRef } from 'react'
import { dashboardApi, getApiBaseUrl } from '../services/api'
import { useAuthStore } from '../stores/authStore'

const HEARTBEAT_INTERVAL_SECS = 30
const IDLE_TIMEOUT_MS = 90 * 1000 // 90 seconds without interaction is considered idle

export function useActiveTimeTracker() {
  const token = useAuthStore((s) => s.token)
  const activeSecondsRef = useRef(0)
  const lastInteractionRef = useRef(Date.now())

  useEffect(() => {
    if (!token) return

    // Track user activity
    const handleActivity = () => {
      lastInteractionRef.current = Date.now()
    }

    const events = ['mousemove', 'keydown', 'scroll', 'click', 'touchstart']
    events.forEach((evt) => window.addEventListener(evt, handleActivity, { passive: true }))

    const flushTime = async () => {
      const secs = activeSecondsRef.current
      if (secs < 5) return
      activeSecondsRef.current = 0

      try {
        await dashboardApi.sendHeartbeat(secs)
      } catch (err) {
        // Silently ignore network failures on heartbeat
      }
    }

    // Interval tick every second
    const intervalId = setInterval(() => {
      const isVisible = document.visibilityState === 'visible'
      const isRecentlyActive = Date.now() - lastInteractionRef.current < IDLE_TIMEOUT_MS

      if (isVisible && isRecentlyActive) {
        activeSecondsRef.current += 1

        if (activeSecondsRef.current >= HEARTBEAT_INTERVAL_SECS) {
          flushTime()
        }
      }
    }, 1000)

    // Flush remaining active seconds when tab closes or is hidden
    const handleVisibilityOrUnload = () => {
      const secs = activeSecondsRef.current
      if (secs >= 5) {
        activeSecondsRef.current = 0
        try {
          const baseUrl = getApiBaseUrl()
          const payload = JSON.stringify({ active_seconds: secs })
          fetch(`${baseUrl}/dashboard/heartbeat`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
            },
            body: payload,
            keepalive: true,
          }).catch(() => {})
        } catch {
          // ignore
        }
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityOrUnload)
    window.addEventListener('beforeunload', handleVisibilityOrUnload)

    return () => {
      clearInterval(intervalId)
      events.forEach((evt) => window.removeEventListener(evt, handleActivity))
      document.removeEventListener('visibilitychange', handleVisibilityOrUnload)
      window.removeEventListener('beforeunload', handleVisibilityOrUnload)
      flushTime()
    }
  }, [token])
}
