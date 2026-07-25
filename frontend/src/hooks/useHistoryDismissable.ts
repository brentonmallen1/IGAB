import { useEffect, useRef } from 'react'

interface SheetHistoryState {
  igabSheet?: string
}

/**
 * Makes an overlay (bottom sheet, full-screen editor) dismissable with the
 * Android back button / browser back gesture without leaving the page.
 *
 * On open, pushes a same-URL history entry tagged with `key`; popstate then
 * fires `onClose` instead of navigating. A UI-initiated close consumes that
 * entry via history.back() so the stack stays balanced. Same-URL pushState is
 * invisible to React Router's route matching.
 */
export function useHistoryDismissable(open: boolean, onClose: () => void, key: string) {
  const closedByPopRef = useRef(false)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    if (!open) return
    closedByPopRef.current = false
    window.history.pushState({ igabSheet: key } satisfies SheetHistoryState, '')

    const handlePop = (e: PopStateEvent) => {
      // Nested sheets: every open overlay hears this event. Popping lands on
      // the entry below the closed one — if that's OUR entry, we're now the
      // top sheet and must stay open; only the sheet whose entry was popped
      // (state no longer ours) closes.
      if ((e.state as SheetHistoryState | null)?.igabSheet === key) return
      closedByPopRef.current = true
      onCloseRef.current()
    }
    window.addEventListener('popstate', handlePop)

    return () => {
      window.removeEventListener('popstate', handlePop)
      // Closed via UI (backdrop, Escape, button): consume our history entry
      if (
        !closedByPopRef.current &&
        (window.history.state as SheetHistoryState | null)?.igabSheet === key
      ) {
        window.history.back()
      }
    }
  }, [open, key])
}
