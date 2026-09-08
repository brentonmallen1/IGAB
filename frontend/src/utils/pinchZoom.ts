/**
 * The arithmetic behind pinch-to-zoom, pure so each rule is a line of test.
 * The hook (hooks/usePinchZoom.ts) owns the refs and the touch events.
 */

export const MIN_SCALE = 1
export const MAX_SCALE = 4
export const DOUBLE_TAP_MS = 300

export interface Point {
  clientX: number
  clientY: number
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

export function distance(a: Point, b: Point): number {
  return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY)
}

export function midpoint(a: Point, b: Point): { x: number; y: number } {
  return { x: (a.clientX + b.clientX) / 2, y: (a.clientY + b.clientY) / 2 }
}

/** The scale after a pinch: the starting scale times how far the fingers
 *  spread, held between 1× and 4×. */
export function pinchScale(initialScale: number, initialDistance: number, current: number): number {
  if (initialDistance <= 0) return initialScale
  return clamp(initialScale * (current / initialDistance), MIN_SCALE, MAX_SCALE)
}

/** Where a one-finger pan puts the image: the finger's travel in screen px,
 *  divided by the scale so the image follows the finger rather than racing it. */
export function panTranslate(
  start: { x: number; y: number; tx: number; ty: number },
  current: { x: number; y: number },
  scale: number
): { translateX: number; translateY: number } {
  return {
    translateX: start.tx + (current.x - start.x) / scale,
    translateY: start.ty + (current.y - start.y) / scale,
  }
}

/** Two taps inside the window make a double tap, which resets the zoom. */
export function isDoubleTap(now: number, lastTap: number): boolean {
  return now - lastTap < DOUBLE_TAP_MS
}
