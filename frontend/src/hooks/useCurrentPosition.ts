import { useEffect, useState } from 'react'

export interface Coords {
  latitude: number
  longitude: number
}

/**
 * Foreground-only, one-shot geolocation for quick-add. Denial, timeout, or an
 * insecure context all degrade silently to null — location is a nicety, never
 * a requirement. Requires HTTPS (or localhost).
 */
export function useCurrentPosition(enabled: boolean): Coords | null {
  const [coords, setCoords] = useState<Coords | null>(null)

  useEffect(() => {
    if (!enabled || !('geolocation' in navigator)) {
      setCoords(null)
      return
    }
    let cancelled = false
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        if (!cancelled) {
          setCoords({ latitude: pos.coords.latitude, longitude: pos.coords.longitude })
        }
      },
      () => {
        if (!cancelled) setCoords(null)
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 60_000 }
    )
    return () => {
      cancelled = true
    }
  }, [enabled])

  return coords
}
