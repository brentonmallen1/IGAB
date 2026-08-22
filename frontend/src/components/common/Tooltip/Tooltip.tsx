import { useState, useRef, useCallback, useLayoutEffect } from 'react'
import { createPortal } from 'react-dom'
import './Tooltip.css'

/** Breathing room the popup keeps from every viewport edge. */
const EDGE = 8

interface Props {
  content: React.ReactNode | null
  children: React.ReactNode
}

export function Tooltip({ content, children }: Props) {
  const [anchor, setAnchor] = useState<{ x: number; y: number } | null>(null)
  const ref = useRef<HTMLSpanElement>(null)
  const popupRef = useRef<HTMLSpanElement>(null)

  const show = useCallback(() => {
    const rect = ref.current?.getBoundingClientRect()
    if (rect) setAnchor({ x: rect.left + rect.width / 2, y: rect.top - EDGE })
  }, [])

  const hide = useCallback(() => setAnchor(null), [])

  // The anchor is where the popup *wants* to sit — centred over the host.
  // Only once it has rendered do we know its size, so clamping to the
  // viewport happens here, before paint: pull it back from either side
  // edge, and flip it below the host when there is no headroom above.
  // Hosts near a screen edge (the inspector hugs the right one) otherwise
  // push half the popup off the screen.
  useLayoutEffect(() => {
    const host = ref.current
    const pop = popupRef.current
    if (!anchor || !host || !pop) return

    const half = pop.offsetWidth / 2
    const x = Math.min(Math.max(anchor.x, EDGE + half), window.innerWidth - EDGE - half)
    pop.style.left = `${x}px`

    if (anchor.y - pop.offsetHeight < EDGE) {
      pop.style.top = `${host.getBoundingClientRect().bottom + EDGE}px`
      pop.style.transform = 'translate(-50%, 0)'
    }
  }, [anchor])

  return (
    <span ref={ref} className="tooltip-host" onMouseEnter={show} onMouseLeave={hide}>
      {children}
      {anchor && content != null &&
        createPortal(
          <span
            ref={popupRef}
            className="tooltip-popup"
            style={{ left: anchor.x, top: anchor.y }}
            role="tooltip"
          >
            {content}
          </span>,
          document.body,
        )}
    </span>
  )
}
