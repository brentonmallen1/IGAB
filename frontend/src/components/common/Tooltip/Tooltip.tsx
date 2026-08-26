import { useState, useRef, useCallback, useEffect, useLayoutEffect } from 'react'
import { createPortal } from 'react-dom'
import { TOOLTIP_DELAY_MS } from './tooltipDelay'
import './Tooltip.css'

/** Breathing room the popup keeps from every viewport edge. */
const EDGE = 8

interface Props {
  content: React.ReactNode | null
  children: React.ReactNode
  /**
   * Fill the parent as a block instead of sitting inline. For a clipped text
   * cell (memo, payee) the host must be the block that carries the
   * ellipsis, or the text inside an inline-flex box clips without one.
   */
  block?: boolean
  /** Extra class on the host — the cell's own clipping class, typically. */
  className?: string
}

/**
 * The app's one hover tooltip. Shows after TOOLTIP_DELAY_MS on hover or
 * keyboard focus, hides on leave/blur, and clamps itself to the viewport.
 * Prefer it over a native `title` anywhere a person actually waits for the
 * text — `title` has a browser-fixed delay of about a second and no
 * styling; keep `title` for the incidental case.
 */
export function Tooltip({ content, children, block = false, className }: Props) {
  const [anchor, setAnchor] = useState<{ x: number; y: number } | null>(null)
  const ref = useRef<HTMLSpanElement>(null)
  const popupRef = useRef<HTMLSpanElement>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const cancel = useCallback(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current)
      timer.current = null
    }
  }, [])

  const show = useCallback(() => {
    cancel()
    timer.current = setTimeout(() => {
      timer.current = null
      const rect = ref.current?.getBoundingClientRect()
      if (rect) setAnchor({ x: rect.left + rect.width / 2, y: rect.top - EDGE })
    }, TOOLTIP_DELAY_MS)
  }, [cancel])

  const hide = useCallback(() => {
    cancel()
    setAnchor(null)
  }, [cancel])

  useEffect(() => cancel, [cancel])

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

  const hostClass = ['tooltip-host', block ? 'tooltip-host--block' : '', className ?? '']
    .filter(Boolean)
    .join(' ')

  return (
    <span
      ref={ref}
      className={hostClass}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
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
