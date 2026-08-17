import { useEffect, useState } from 'react'

/**
 * Height of the visual viewport while the on-screen keyboard is up, else null.
 *
 * iOS Safari ignores `interactive-widget=resizes-content` — the keyboard
 * overlays the layout viewport instead of resizing it, so `100dvh` panels keep
 * their footers hidden behind the keyboard. Clamping a panel to this height
 * keeps its footer reachable. Only reports when the visual viewport is
 * meaningfully smaller than the layout viewport (keyboard up).
 */
export function useVisualViewportHeight(active: boolean): number | null {
  const [height, setHeight] = useState<number | null>(null)

  useEffect(() => {
    if (!active) return
    const vv = window.visualViewport
    if (!vv) return
    const update = () => {
      setHeight(vv.height < window.innerHeight - 50 ? vv.height : null)
    }
    update()
    vv.addEventListener('resize', update)
    return () => {
      vv.removeEventListener('resize', update)
      setHeight(null)
    }
  }, [active])

  return height
}
