import { useState, useRef, useCallback, type TouchEvent } from 'react'

interface ZoomState {
  scale: number
  translateX: number
  translateY: number
}

const DOUBLE_TAP_MS = 300
const MIN_SCALE = 1
const MAX_SCALE = 4

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

interface TouchPoint {
  clientX: number
  clientY: number
}

function getDistance(t1: TouchPoint, t2: TouchPoint): number {
  const dx = t1.clientX - t2.clientX
  const dy = t1.clientY - t2.clientY
  return Math.hypot(dx, dy)
}

function getMidpoint(t1: TouchPoint, t2: TouchPoint): { x: number; y: number } {
  return {
    x: (t1.clientX + t2.clientX) / 2,
    y: (t1.clientY + t2.clientY) / 2,
  }
}

/**
 * Pinch-zoom with pan support. Returns transform state and touch handlers.
 * Double-tap resets to scale=1.
 */
export function usePinchZoom() {
  const [state, setState] = useState<ZoomState>({ scale: 1, translateX: 0, translateY: 0 })

  const initialDistanceRef = useRef<number | null>(null)
  const initialScaleRef = useRef(1)
  const initialTranslateRef = useRef({ x: 0, y: 0 })
  const pinchMidpointRef = useRef<{ x: number; y: number } | null>(null)
  const lastTapRef = useRef(0)
  const panStartRef = useRef<{ x: number; y: number; tx: number; ty: number } | null>(null)

  const reset = useCallback(() => {
    setState({ scale: 1, translateX: 0, translateY: 0 })
  }, [])

  const handleTouchStart = useCallback((e: TouchEvent) => {
    if (e.touches.length === 2) {
      const distance = getDistance(e.touches[0], e.touches[1])
      initialDistanceRef.current = distance
      initialScaleRef.current = state.scale
      initialTranslateRef.current = { x: state.translateX, y: state.translateY }
      pinchMidpointRef.current = getMidpoint(e.touches[0], e.touches[1])
      panStartRef.current = null
    } else if (e.touches.length === 1 && state.scale > 1) {
      panStartRef.current = {
        x: e.touches[0].clientX,
        y: e.touches[0].clientY,
        tx: state.translateX,
        ty: state.translateY,
      }
    }
  }, [state.scale, state.translateX, state.translateY])

  const handleTouchMove = useCallback((e: TouchEvent) => {
    if (e.touches.length === 2 && initialDistanceRef.current !== null) {
      const distance = getDistance(e.touches[0], e.touches[1])
      const scaleDelta = distance / initialDistanceRef.current
      const newScale = clamp(initialScaleRef.current * scaleDelta, MIN_SCALE, MAX_SCALE)

      setState((s) => ({ ...s, scale: newScale }))
    } else if (e.touches.length === 1 && panStartRef.current && state.scale > 1) {
      const dx = e.touches[0].clientX - panStartRef.current.x
      const dy = e.touches[0].clientY - panStartRef.current.y
      setState((s) => ({
        ...s,
        translateX: panStartRef.current!.tx + dx / s.scale,
        translateY: panStartRef.current!.ty + dy / s.scale,
      }))
    }
  }, [state.scale])

  const handleTouchEnd = useCallback((e: TouchEvent) => {
    initialDistanceRef.current = null
    pinchMidpointRef.current = null

    if (e.touches.length === 0) {
      panStartRef.current = null

      const now = Date.now()
      if (now - lastTapRef.current < DOUBLE_TAP_MS) {
        reset()
        lastTapRef.current = 0
      } else {
        lastTapRef.current = now
      }
    }
  }, [reset])

  return {
    scale: state.scale,
    translateX: state.translateX,
    translateY: state.translateY,
    isZoomed: state.scale > 1,
    reset,
    handlers: {
      onTouchStart: handleTouchStart,
      onTouchMove: handleTouchMove,
      onTouchEnd: handleTouchEnd,
    },
  }
}
