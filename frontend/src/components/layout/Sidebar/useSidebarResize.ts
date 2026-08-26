import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { SIDEBAR_KEY_STEP, SIDEBAR_MAX_WIDTH, SIDEBAR_MIN_WIDTH, clampSidebarWidth } from './sidebarWidth'

/**
 * Drag and keyboard handling for the sidebar's resize handle. Pure event
 * wiring: the width itself lives in the UI store, which clamps it.
 */
export function useSidebarResize(width: number, setWidth: (px: number) => void) {
  const widthRef = useRef(width)
  useEffect(() => {
    widthRef.current = width
  }, [width])
  // Also track what we asked for, so a burst of keypresses or pointer moves
  // between renders builds on the latest request rather than the last paint.
  const apply = useCallback(
    (px: number) => {
      widthRef.current = clampSidebarWidth(px)
      setWidth(px)
    },
    [setWidth]
  )
  const drag = useRef<{ startX: number; startWidth: number } | null>(null)
  const [active, setActive] = useState(false)

  const onPointerDown = useCallback((e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    drag.current = { startX: e.clientX, startWidth: widthRef.current }
    e.currentTarget.setPointerCapture(e.pointerId)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    setActive(true)
  }, [])

  const onPointerMove = useCallback(
    (e: PointerEvent<HTMLDivElement>) => {
      if (!drag.current) return
      apply(drag.current.startWidth + (e.clientX - drag.current.startX))
    },
    [apply]
  )

  const end = useCallback((e: PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return
    drag.current = null
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    setActive(false)
  }, [])

  const onKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      const w = widthRef.current
      const next =
        e.key === 'ArrowRight' ? w + SIDEBAR_KEY_STEP
        : e.key === 'ArrowLeft' ? w - SIDEBAR_KEY_STEP
        : e.key === 'Home' ? SIDEBAR_MIN_WIDTH
        : e.key === 'End' ? SIDEBAR_MAX_WIDTH
        : null
      if (next === null) return
      e.preventDefault()
      apply(next)
    },
    [apply]
  )

  const onDoubleClick = useCallback(() => apply(SIDEBAR_MIN_WIDTH), [apply])

  return {
    active,
    handleProps: { onPointerDown, onPointerMove, onPointerUp: end, onPointerCancel: end, onKeyDown, onDoubleClick },
  }
}
