import { useCallback, useRef } from 'react'
import { useUIStore } from '../../../stores/uiStore'
import { CHAT_PANEL_KEY_STEP, CHAT_PANEL_MIN_WIDTH, clampChatPanelWidth } from './chatPanelWidth'

/**
 * Dragging the panel's left edge.
 *
 * The wiring half of the pair: `chatPanelWidth.ts` holds the arithmetic with no
 * DOM, this holds the pointer capture and the keyboard fallback. Width grows
 * leftwards, so the delta is inverted relative to the left sidebar's.
 */
export function useChatPanelResize() {
  const width = useUIStore((s) => s.chatPanelWidth)
  const setWidth = useUIStore((s) => s.setChatPanelWidth)
  const start = useRef<{ x: number; width: number } | null>(null)

  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      e.currentTarget.setPointerCapture(e.pointerId)
      start.current = { x: e.clientX, width }
    },
    [width]
  )

  const onPointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!start.current) return
      // Dragging left makes the panel wider.
      setWidth(clampChatPanelWidth(start.current.width - (e.clientX - start.current.x)))
    },
    [setWidth]
  )

  const onPointerUp = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId)
    }
    start.current = null
  }, [])

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === 'ArrowLeft') {
        e.preventDefault()
        setWidth(width + CHAT_PANEL_KEY_STEP)
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        setWidth(width - CHAT_PANEL_KEY_STEP)
      } else if (e.key === 'Home') {
        e.preventDefault()
        setWidth(CHAT_PANEL_MIN_WIDTH)
      }
    },
    [setWidth, width]
  )

  return {
    handleProps: {
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onKeyDown,
      onDoubleClick: () => setWidth(CHAT_PANEL_MIN_WIDTH),
      role: 'separator' as const,
      'aria-orientation': 'vertical' as const,
      'aria-label': 'Resize chat panel',
      tabIndex: 0,
    },
  }
}
