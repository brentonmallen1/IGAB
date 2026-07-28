import { useRef, type TouchEvent } from 'react'

const SWIPE_THRESHOLD_PX = 60

/**
 * Horizontal swipe detection for navigation. Returns touch handlers to spread
 * on a container. Ignores mostly-vertical gestures so scrolling works normally.
 */
export function useSwipeNavigation(onPrev: () => void, onNext: () => void) {
  const touchStartRef = useRef<{ x: number; y: number } | null>(null)

  return {
    onTouchStart: (e: TouchEvent) => {
      touchStartRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }
    },
    onTouchEnd: (e: TouchEvent) => {
      const start = touchStartRef.current
      touchStartRef.current = null
      if (!start) return
      const dx = e.changedTouches[0].clientX - start.x
      const dy = e.changedTouches[0].clientY - start.y
      if (Math.abs(dx) < SWIPE_THRESHOLD_PX || Math.abs(dy) > Math.abs(dx)) return
      if (dx > 0) onPrev()
      else onNext()
    },
  }
}
