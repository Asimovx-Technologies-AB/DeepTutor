import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Loader2, Zap, CheckCircle2 } from 'lucide-react'
import { healthApi } from '../services/api'

export default function ServerWarmupNotice() {
  const [status, setStatus] = useState<'checking' | 'warming' | 'ready' | 'hidden'>('checking')
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    let timer: any = null
    let pollInterval: any = null
    let isMounted = true

    const checkServer = async () => {
      try {
        // Quick check to see if server is instantly alive
        const res = await healthApi.check()

        if (res.status === 200 && isMounted) {
          setStatus('ready')
          setTimeout(() => {
            if (isMounted) setStatus('hidden')
          }, 1500)
          return
        }
      } catch {
        // Server is asleep or taking time to respond (Render Cold Start)
        if (isMounted) {
          setStatus('warming')
          // Start counting seconds so the user sees live progress
          timer = setInterval(() => {
            setElapsed((prev) => prev + 1)
          }, 1000)

          // Poll every 3 seconds until server wakes up
          pollInterval = setInterval(async () => {
            try {
              const checkRes = await healthApi.check()
              if (checkRes.status === 200) {
                clearInterval(pollInterval)
                clearInterval(timer)
                if (isMounted) {
                  setStatus('ready')
                  setTimeout(() => {
                    if (isMounted) setStatus('hidden')
                  }, 2000)
                }
              }
            } catch {
              // Still warming up...
            }
          }, 3000)
        }
      }
    }

    checkServer()

    return () => {
      isMounted = false
      if (timer) clearInterval(timer)
      if (pollInterval) clearInterval(pollInterval)
    }
  }, [])

  if (status === 'hidden' || status === 'checking') return null

  return (
    <AnimatePresence>
      <motion.div
        key="server-warmup-banner"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        className="fixed top-3 left-1/2 -translate-x-1/2 z-[9999] px-4 py-2 rounded-full shadow-lg border backdrop-blur-md flex items-center gap-2.5 text-xs font-semibold select-none"
        style={{
          backgroundColor: status === 'ready' ? 'rgba(235, 246, 238, 0.95)' : 'rgba(255, 249, 242, 0.95)',
          borderColor: status === 'ready' ? 'rgba(79, 138, 104, 0.3)' : 'rgba(242, 138, 69, 0.3)',
          color: status === 'ready' ? '#46A302' : '#1899D6',
        }}
      >
        {status === 'ready' ? (
          <>
            <CheckCircle2 size={15} className="text-[#58CC02]" />
            <span>Indie-Tutor Server Connected & Ready</span>
          </>
        ) : (
          <>
            <Loader2 size={15} className="animate-spin text-[#1CB0F6]" />
            <span>
              Waking up AI Cloud Server ({elapsed}s)...{' '}
              <span className="text-[#AFAFAF] font-normal hidden sm:inline">
                (Free tier instance takes ~30s on first load)
              </span>
            </span>
            <Zap size={13} className="text-[#1CB0F6] animate-pulse" />
          </>
        )}
      </motion.div>
    </AnimatePresence>
  )
}
