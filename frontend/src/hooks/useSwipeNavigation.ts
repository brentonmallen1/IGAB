import { useRef, type TouchEvent } from 'react'
import { hapticTick } from '../utils/haptics'
import { resolveSwipe } from '../utils/gestures'

export interface SwipeHandlers {
  onTouchStart: (e: TouchEvent) => void
  onTouchEnd: (e: TouchEvent) => void
}

export interface SwipeOptions {
  /** Finger moved left (content advances). */
  onLeft?: () => void
  /** Finger moved right (content goes back). */
  onRight?: () => void
  /** Finger moved down past the threshold — a dismiss, on a full-screen viewer. */
  onDown?: () => void
  /** A rightward swipe that began at the left screen edge. */
  onEdgeBack?: () => void
  /** False while a gesture would fight something else — a pinch-zoomed image. */
  enabled?: boolean
}

/**
 * Swipe detection as touch handlers to spread on a container.
 *
 * One hook for every swipe in the app: the budget page's month change, the
 * lightbox's prev/next and swipe-down-to-close, and the shell's edge-swipe
 * back. The thresholds live in utils/gestures; this only wires the events,
 * so a page swipe and the back gesture read the same rule and cannot
 * disagree about a touch that began at the edge.
 */
export function useSwipeNavigation({
  onLeft,
  onRight,
  onDown,
  onEdgeBack,
  enabled = true,
}: SwipeOptions): SwipeHandlers {
  const touchStartRef = useRef<{ x: number; y: number } | null>(null)

  return {
    onTouchStart: (e: TouchEvent) => {
      if (!enabled) return
      touchStartRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }
    },
    onTouchEnd: (e: TouchEvent) => {
      const start = touchStartRef.current
      touchStartRef.current = null
      if (!start || !enabled) return
      const swipe = resolveSwipe({
        dx: e.changedTouches[0].clientX - start.x,
        dy: e.changedTouches[0].clientY - start.y,
        startX: start.x,
      })
      const handler =
        swipe === 'left'
          ? onLeft
          : swipe === 'right'
            ? onRight
            : swipe === 'down'
              ? onDown
              : swipe === 'edge-back'
                ? onEdgeBack
                : undefined
      if (!handler) return
      // Confirms the swipe committed — the change itself is the only other
      // feedback, and it lands a frame later. (Android only; iOS has no
      // vibration API, so the visible result carries it there.)
      hapticTick()
      handler()
    },
  }
}
