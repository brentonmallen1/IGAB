import { useRef, type MouseEvent, type TouchEvent } from 'react'
import { hapticTick } from '../utils/haptics'

const MOVE_CANCEL_PX = 10

/**
 * Touch long-press with click passthrough. Returns handlers to spread on an
 * element: a hold of `ms` fires onLongPress (and suppresses the synthetic
 * click that follows); a normal tap falls through to onClick. Movement beyond
 * a small threshold cancels the press so scrolling never triggers it.
 */
export function useLongPress(onLongPress: () => void, onClick?: (e: MouseEvent) => void, ms = 500) {
  const timerRef = useRef<number | null>(null)
  const triggeredRef = useRef(false)
  const startPosRef = useRef<{ x: number; y: number } | null>(null)

  const clear = () => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }

  return {
    onTouchStart: (e: TouchEvent) => {
      const t = e.touches[0]
      startPosRef.current = { x: t.clientX, y: t.clientY }
      clear()
      // A latched flag from an earlier gesture must not eat THIS tap. iOS
      // can end a long-press without ever dispatching the click that used to
      // be the only thing clearing it (text-selection takeover, touchcancel),
      // and the stale flag then swallowed the user's next tap — the
      // "have to tap a transaction twice" bug.
      triggeredRef.current = false
      timerRef.current = window.setTimeout(() => {
        triggeredRef.current = true
        // The only confirmation the hold registered, and it lands before any
        // visual change does. (Android only — iOS has no vibration API.)
        hapticTick()
        onLongPress()
      }, ms)
    },
    onTouchMove: (e: TouchEvent) => {
      if (!startPosRef.current) return
      const t = e.touches[0]
      if (
        Math.abs(t.clientX - startPosRef.current.x) > MOVE_CANCEL_PX ||
        Math.abs(t.clientY - startPosRef.current.y) > MOVE_CANCEL_PX
      ) {
        clear()
      }
    },
    onTouchEnd: () => {
      clear()
      startPosRef.current = null
    },
    // Scroll/gesture takeover: the browser ends the touch without a click.
    // Without this the pending timer survived the cancelled gesture and could
    // fire onLongPress mid-scroll (silently entering selection mode).
    onTouchCancel: () => {
      clear()
      startPosRef.current = null
      triggeredRef.current = false
    },
    onClick: (e: MouseEvent) => {
      if (triggeredRef.current) {
        triggeredRef.current = false
        return
      }
      onClick?.(e)
    },
  }
}
