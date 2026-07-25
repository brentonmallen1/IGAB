import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { WifiOff } from 'lucide-react'
import './OfflineBanner.css'

/**
 * Slim top banner shown when the app can't reach the server — either the
 * device is offline (navigator.onLine) or an API request failed at the
 * network level (client.ts dispatches igab:network-error / igab:network-ok).
 * The app is network-required by design; this makes that state explicit
 * instead of leaving broken screens.
 */
export function OfflineBanner() {
  const queryClient = useQueryClient()
  const [browserOffline, setBrowserOffline] = useState(() => !navigator.onLine)
  const [serverUnreachable, setServerUnreachable] = useState(false)

  useEffect(() => {
    const goOffline = () => setBrowserOffline(true)
    const goOnline = () => setBrowserOffline(false)
    const serverDown = () => setServerUnreachable(true)
    const serverUp = () => setServerUnreachable(false)

    window.addEventListener('offline', goOffline)
    window.addEventListener('online', goOnline)
    window.addEventListener('igab:network-error', serverDown)
    window.addEventListener('igab:network-ok', serverUp)
    return () => {
      window.removeEventListener('offline', goOffline)
      window.removeEventListener('online', goOnline)
      window.removeEventListener('igab:network-error', serverDown)
      window.removeEventListener('igab:network-ok', serverUp)
    }
  }, [])

  if (!browserOffline && !serverUnreachable) return null

  return (
    <div className="offline-banner" role="status">
      <WifiOff size={14} aria-hidden />
      <span className="offline-banner__text">
        Can&apos;t reach the server — changes won&apos;t save
      </span>
      <button
        className="offline-banner__retry"
        onClick={() => queryClient.refetchQueries({ type: 'active' })}
      >
        Retry
      </button>
    </div>
  )
}
