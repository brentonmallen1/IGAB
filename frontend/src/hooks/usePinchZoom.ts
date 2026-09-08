import { useState, useRef, useCallback, type TouchEvent } from 'react'
import { distance, isDoubleTap, midpoint, panTranslate, pinchScale } from '../utils/pinchZoom'

interface ZoomState {
  scale: number
  translateX: number
  translateY: number
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

  const handleTouchStart = useCallback(
    (e: TouchEvent) => {
      if (e.touches.length === 2) {
        initialDistanceRef.current = distance(e.touches[0], e.touches[1])
        initialScaleRef.current = state.scale
        initialTranslateRef.current = { x: state.translateX, y: state.translateY }
        pinchMidpointRef.current = midpoint(e.touches[0], e.touches[1])
        panStartRef.current = null
      } else if (e.touches.length === 1 && state.scale > 1) {
        panStartRef.current = {
          x: e.touches[0].clientX,
          y: e.touches[0].clientY,
          tx: state.translateX,
          ty: state.translateY,
        }
      }
    },
    [state.scale, state.translateX, state.translateY]
  )

  const handleTouchMove = useCallback(
    (e: TouchEvent) => {
      if (e.touches.length === 2 && initialDistanceRef.current !== null) {
        const newScale = pinchScale(
          initialScaleRef.current,
          initialDistanceRef.current,
          distance(e.touches[0], e.touches[1])
        )
        setState((s) => ({ ...s, scale: newScale }))
      } else if (e.touches.length === 1 && panStartRef.current && state.scale > 1) {
        const finger = { x: e.touches[0].clientX, y: e.touches[0].clientY }
        setState((s) => ({ ...s, ...panTranslate(panStartRef.current!, finger, s.scale) }))
      }
    },
    [state.scale]
  )

  const handleTouchEnd = useCallback(
    (e: TouchEvent) => {
      initialDistanceRef.current = null
      pinchMidpointRef.current = null

      if (e.touches.length === 0) {
        panStartRef.current = null

        const now = Date.now()
        if (isDoubleTap(now, lastTapRef.current)) {
          reset()
          lastTapRef.current = 0
        } else {
          lastTapRef.current = now
        }
      }
    },
    [reset]
  )

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
