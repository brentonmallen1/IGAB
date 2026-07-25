import { useEffect, useRef } from 'react'
import toast from 'react-hot-toast'
import { RefreshCw } from 'lucide-react'
import { useRegisterSW } from 'virtual:pwa-register/react'
import './UpdateToast.css'

const UPDATE_CHECK_MS = 60 * 60 * 1000 // hourly

/**
 * Registers the service worker and surfaces a persistent "update available"
 * toast when a new build is waiting. registerType is 'prompt' — the app never
 * reloads itself out from under the user.
 */
export function UpdateToast() {
  const intervalRef = useRef<number | null>(null)
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisteredSW(_url, registration) {
      if (registration && intervalRef.current === null) {
        intervalRef.current = window.setInterval(() => registration.update(), UPDATE_CHECK_MS)
      }
    },
  })

  useEffect(() => {
    return () => {
      if (intervalRef.current !== null) window.clearInterval(intervalRef.current)
    }
  }, [])

  useEffect(() => {
    if (!needRefresh) return
    toast(
      () => (
        <div className="update-toast">
          <span className="update-toast__text">A new version of IGAB is ready.</span>
          <button
            className="update-toast__button"
            onClick={() => updateServiceWorker(true)}
          >
            <RefreshCw size={13} />
            Update
          </button>
          <button
            className="update-toast__dismiss"
            onClick={() => {
              setNeedRefresh(false)
              toast.dismiss('sw-update')
            }}
          >
            Later
          </button>
        </div>
      ),
      { id: 'sw-update', duration: Infinity }
    )
  }, [needRefresh, setNeedRefresh, updateServiceWorker])

  return null
}
