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
export function useHistoryDismissable(
  open: boolean,
  onClose: () => void,
  key: string,
  /**
   * Synchronous veto. Return false to keep the overlay open; the consumed
   * history entry is pushed straight back so the stack stays balanced and a
   * second back gesture still works. Side effects are allowed and are how an
   * async confirmation is driven — raise the confirmation, return false, and
   * close for real once the user answers.
   */
  canClose?: () => boolean
) {
  const closedByPopRef = useRef(false)
  const onCloseRef = useRef(onClose)
  const canCloseRef = useRef(canClose)
  // Effect rather than render-phase assignment: popstate can only fire after
  // commit, so the handler always sees the current callbacks either way.
  useEffect(() => {
    onCloseRef.current = onClose
    canCloseRef.current = canClose
  })
  // history.back() scheduled by a cleanup, cancellable if the effect re-runs
  // immediately (StrictMode dev remount). Without this, the fake cleanup's
  // async back() lands after the re-run's pushState and instantly dismisses
  // any overlay that mounts with open=true (e.g. the transaction editor).
  const pendingBackRef = useRef<number | null>(null)

  useEffect(() => {
    if (!open) return
    closedByPopRef.current = false
    if (pendingBackRef.current !== null) {
      window.clearTimeout(pendingBackRef.current)
      pendingBackRef.current = null
    }
    // Re-runs (StrictMode) find our entry already on top — don't double-push
    if ((window.history.state as SheetHistoryState | null)?.igabSheet !== key) {
      window.history.pushState({ igabSheet: key } satisfies SheetHistoryState, '')
    }

    const handlePop = (e: PopStateEvent) => {
      // Nested sheets: every open overlay hears this event. Popping lands on
      // the entry below the closed one — if that's OUR entry, we're now the
      // top sheet and must stay open; only the sheet whose entry was popped
      // (state no longer ours) closes.
      if ((e.state as SheetHistoryState | null)?.igabSheet === key) return
      if (canCloseRef.current?.() === false) {
        // Re-arm: our entry was just consumed by the pop, so put it back.
        window.history.pushState({ igabSheet: key } satisfies SheetHistoryState, '')
        return
      }
      closedByPopRef.current = true
      onCloseRef.current()
    }
    window.addEventListener('popstate', handlePop)

    return () => {
      window.removeEventListener('popstate', handlePop)
      // Closed via UI (backdrop, Escape, button): consume our history entry.
      // Deferred so an immediate effect re-run can cancel it.
      if (
        !closedByPopRef.current &&
        (window.history.state as SheetHistoryState | null)?.igabSheet === key
      ) {
        pendingBackRef.current = window.setTimeout(() => {
          pendingBackRef.current = null
          window.history.back()
        }, 0)
      }
    }
  }, [open, key])
}
