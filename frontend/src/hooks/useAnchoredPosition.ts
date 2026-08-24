import { useCallback, useLayoutEffect, useState, type RefObject } from 'react'
import {
  placeAnchored,
  samePlacement,
  type AnchoredPlacement,
  type AnchorOptions,
} from '../utils/anchoredPosition'

/**
 * Keeps a portalled panel pinned to its trigger for as long as it is open.
 *
 * The measuring half of the rule whose arithmetic lives in
 * utils/anchoredPosition — every dropdown, popover and menu in the app should
 * reach the same answer about where it goes, and this is how they share one.
 *
 * Returns null while closed, which is the signal not to render the panel. The
 * measurement runs in a layout effect, so the first paint of an opening panel
 * is already at the right place.
 */
export function useAnchoredPosition(
  triggerRef: RefObject<HTMLElement | null>,
  open: boolean,
  options: AnchorOptions = {}
): AnchoredPlacement | null {
  const [placement, setPlacement] = useState<AnchoredPlacement | null>(null)

  // Destructured to primitives so callers can pass an object literal — which
  // every caller does — without a new identity restarting the effect each
  // render. A ref would work too, but writing one during render is its own
  // lint violation and its own subtle bug.
  const { width, minWidth, maxWidth, gap, margin, maxHeight, flipThreshold } = options

  const measure = useCallback(() => {
    const el = triggerRef.current
    if (!el) return
    const next = placeAnchored(
      el.getBoundingClientRect(),
      { width: window.innerWidth, height: window.innerHeight },
      { width, minWidth, maxWidth, gap, margin, maxHeight, flipThreshold }
    )
    // Identical placements keep the SAME object, so scrolling a list inside an
    // open panel does not re-render the whole thing on every tick.
    setPlacement((prev) => (samePlacement(prev, next) ? prev : next))
  }, [triggerRef, width, minWidth, maxWidth, gap, margin, maxHeight, flipThreshold])

  useLayoutEffect(() => {
    if (!open) return
    measure()
    // Capture: triggers ride inside scroll containers (the register, a report
    // card, a modal body) that do not bubble scroll to window.
    const onMove = () => measure()
    document.addEventListener('scroll', onMove, { capture: true, passive: true })
    window.addEventListener('resize', onMove)
    return () => {
      document.removeEventListener('scroll', onMove, { capture: true })
      window.removeEventListener('resize', onMove)
    }
  }, [open, measure])

  // Not cleared on close — clearing is a setState in an effect, and the stale
  // value is unreachable anyway: the layout effect above re-measures before
  // the reopened panel is painted.
  return open ? placement : null
}
