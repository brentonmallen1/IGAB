import { useRef, type TouchEvent } from 'react'
import { hapticTick } from '../utils/haptics'
import { resolveSwipe, scrollsHorizontally } from '../utils/gestures'
import { overlayStackDepth } from '../utils/overlayStack'

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
  /**
   * This swipe belongs to the page underneath, so it does nothing while any
   * overlay is open.
   *
   * Not an optimisation — a correctness rule, and the one the month swipe was
   * missing. A sheet or modal opened from a page is a child of that page in
   * the React tree even though it portals to document.body, and React bubbles
   * synthetic events through the tree it rendered, not the DOM. So a drag
   * inside the mobile category inspector reached the budget page's handler and
   * changed the month behind the open sheet; closing it revealed a month the
   * user never navigated to. An overlay owns its own gestures.
   *
   * False for a swipe that belongs to an overlay itself — the lightbox's
   * prev/next and swipe-down-to-close only ever run with an overlay open.
   */
  pageLevel?: boolean
  /** False while a gesture would fight something else — a pinch-zoomed image. */
  enabled?: boolean
}

/**
 * Whether the touch began inside something that scrolls sideways on its own.
 *
 * Walks from the touched node up to the element carrying the handlers, so a
 * scroller anywhere in between claims the gesture. The metrics come off the
 * DOM here; the rule itself is `scrollsHorizontally` in utils/gestures.
 */
function beganInHorizontalScroller(e: TouchEvent): boolean {
  const stop = e.currentTarget
  let el: Element | null = e.target instanceof Element ? e.target : null
  while (el) {
    const { overflowX } = getComputedStyle(el)
    if (
      scrollsHorizontally({ scrollWidth: el.scrollWidth, clientWidth: el.clientWidth, overflowX })
    ) {
      return true
    }
    if (el === stop) return false
    el = el.parentElement
  }
  return false
}

/**
 * Swipe detection as touch handlers to spread on a container.
 *
 * One hook for every swipe in the app: the budget page's month change, the
 * lightbox's prev/next and swipe-down-to-close, and the shell's edge-swipe
 * back. The thresholds live in utils/gestures; this only wires the events,
 * so a page swipe and the back gesture read the same rule and cannot
 * disagree about a touch that began at the edge — or about a touch that
 * happened while an overlay was covering the page.
 */
export function useSwipeNavigation({
  onLeft,
  onRight,
  onDown,
  onEdgeBack,
  pageLevel = false,
  enabled = true,
}: SwipeOptions): SwipeHandlers {
  const touchStartRef = useRef<{ x: number; y: number } | null>(null)
  const covered = () => pageLevel && overlayStackDepth() > 0

  return {
    onTouchStart: (e: TouchEvent) => {
      touchStartRef.current = null
      if (!enabled || covered()) return
      if (beganInHorizontalScroller(e)) return
      touchStartRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }
    },
    onTouchEnd: (e: TouchEvent) => {
      const start = touchStartRef.current
      touchStartRef.current = null
      if (!start || !enabled) return
      // Checked again at the end: an overlay that opened mid-gesture (a
      // long-press that raised a sheet) must swallow the release too.
      if (covered()) return
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
