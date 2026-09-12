import { useEffect, useRef } from 'react'

interface SheetHistoryState {
  igabSheet?: string
}

/**
 * The one history.back() a UI close has scheduled and not yet run, shared by
 * every overlay rather than held per instance. Deferred so whatever opens next
 * in the same act can cancel it and inherit the entry — the same instance on a
 * StrictMode re-run, or a different overlay in a sheet-to-sheet handoff.
 */
let pendingBack: { timer: number; key: string } | null = null

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
  useEffect(() => {
    if (!open) return
    closedByPopRef.current = false
    const top = (window.history.state as SheetHistoryState | null)?.igabSheet
    // The entry on top is one a UI close is about to consume. Cancel that
    // back() and inherit the entry; any other pending back() is left alone.
    const pending = pendingBack
    const inherit = pending !== null && pending.key === top
    if (inherit) {
      window.clearTimeout(pending.timer)
      pendingBack = null
    }
    if (top === key) {
      // Our entry is already on top — a StrictMode re-run, or a close and
      // reopen of the same overlay before its back() landed. Keep it.
    } else if (inherit) {
      // Another overlay closed in this same act and was about to consume its
      // entry. Take the entry over instead of pushing above it: the deferred
      // back() would otherwise pop OUR entry and close us the moment we opened
      // (More -> "Ask about your budget" flashed the assistant and dropped it).
      window.history.replaceState({ igabSheet: key } satisfies SheetHistoryState, '')
    } else {
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
      // Deferred so whatever opens in the same act can inherit the entry.
      if (
        !closedByPopRef.current &&
        (window.history.state as SheetHistoryState | null)?.igabSheet === key
      ) {
        const scheduled = {
          key,
          timer: window.setTimeout(() => {
            if (pendingBack === scheduled) pendingBack = null
            window.history.back()
          }, 0),
        }
        pendingBack = scheduled
      }
    }
  }, [open, key])
}
