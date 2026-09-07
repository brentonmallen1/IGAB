import { useCallback, useLayoutEffect, useState, type RefObject } from 'react'
import {
  placeAnchored,
  samePlacement,
  type AnchoredPlacement,
  type AnchorOptions,
  type Viewport,
} from '../utils/anchoredPosition'
import { computeViewportMetrics } from './useAppViewport'

/**
 * The room a fixed panel actually has, in layout-viewport coordinates.
 *
 * `window.innerHeight` alone was wrong on exactly the platform the app is
 * installed on: iOS shrinks the VISUAL viewport for the keyboard and leaves
 * the layout viewport unchanged, so a panel sized to innerHeight can open
 * under the keyboard. computeViewportMetrics is useAppViewport's — the same
 * two insets it publishes as --vv-top / --vv-bottom, not a second copy.
 */
function currentViewport(): Viewport {
  const layoutHeight = document.documentElement.clientHeight
  const vv = window.visualViewport
  const m = vv
    ? computeViewportMetrics(layoutHeight, vv.height, vv.offsetTop)
    : computeViewportMetrics(layoutHeight, layoutHeight, 0)
  return {
    width: window.innerWidth,
    height: layoutHeight,
    inset: { top: m.offsetTop, bottom: m.bottomInset },
  }
}

/**
 * How tall the panel would be if nothing capped it.
 *
 * Reading `scrollHeight` directly is self-defeating for half the panels here,
 * and silently so. Where the panel ITSELF scrolls (ContextMenu) it reports the
 * full content height and all is well. Where the panel is a flex column whose
 * BODY scrolls — InfoPopover, TagPicker, AssignDropdown, MoveMoneyPopover —
 * the body shrinks into whatever cap this hook last handed down, so the panel
 * measures exactly the cap. Feed that back in and the panel always appears to
 * fit the room it was given, so it never flips: measured 300 against a 300px
 * cap while the real content wanted 740.
 *
 * Lifting the cap for the read costs a synchronous reflow, and only when the
 * panel opens or its content resizes. It happens inside a layout effect or a
 * ResizeObserver callback, both of which run before paint, so nothing is drawn
 * at the uncapped size.
 */
function naturalHeight(panel: HTMLElement | null | undefined): number | undefined {
  if (!panel) return undefined
  const capped = panel.style.maxHeight
  panel.style.maxHeight = 'none'
  const height = panel.scrollHeight
  panel.style.maxHeight = capped
  // A panel that has not painted yet measures 0; fall back rather than
  // believe it.
  return height || undefined
}

/** Where a right-click happened. Passed instead of a ref when the thing the
 *  panel hangs off is a point rather than a control — a context menu opened
 *  on a table row has no button to measure. */
export interface AnchorPoint {
  x: number
  y: number
}

/** The trigger: an element to measure, or a bare point. */
export type AnchorSource = RefObject<HTMLElement | null> | AnchorPoint

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
 *
 * Pass `panelRef` whenever you can. Without it the placement is decided from
 * an assumed height, which is what every off-screen overlay in this app has
 * had in common.
 */
export function useAnchoredPosition(
  anchor: AnchorSource,
  open: boolean,
  options: AnchorOptions = {},
  panelRef?: RefObject<HTMLElement | null>
): AnchoredPlacement | null {
  const [placement, setPlacement] = useState<AnchoredPlacement | null>(null)

  // Destructured to primitives so callers can pass an object literal — which
  // every caller does — without a new identity restarting the effect each
  // render. A ref would work too, but writing one during render is its own
  // lint violation and its own subtle bug. The point anchor gets the same
  // treatment for the same reason.
  const { width, minWidth, maxWidth, gap, margin, maxHeight, desiredHeight, flipThreshold, align } =
    options
  const elementRef = 'current' in anchor ? anchor : null
  const pointX = elementRef ? 0 : (anchor as AnchorPoint).x
  const pointY = elementRef ? 0 : (anchor as AnchorPoint).y

  const measure = useCallback(() => {
    // A point is a zero-size trigger: "below" it is the point itself, and
    // align:'end' puts the panel's right edge there — which is what the old
    // `alignRight` flag meant, now expressed in the shared vocabulary.
    const rect = elementRef
      ? elementRef.current?.getBoundingClientRect()
      : { top: pointY, bottom: pointY, left: pointX, width: 0 }
    if (!rect) return
    const measured = naturalHeight(panelRef?.current)
    // Only when the caller states no width of its own: a menu sizes to its
    // longest label, so the horizontal clamp has nothing to work from until
    // the panel exists. Callers that pass a width keep it — measuring one they
    // then apply would be circular.
    const measuredWidth =
      width === undefined ? panelRef?.current?.offsetWidth || undefined : undefined
    const next = placeAnchored(rect, currentViewport(), {
      width: measuredWidth ?? width,
      minWidth,
      maxWidth,
      gap,
      margin,
      maxHeight,
      desiredHeight: measured ?? desiredHeight,
      flipThreshold,
      align,
    })
    // Identical placements keep the SAME object, so scrolling a list inside an
    // open panel does not re-render the whole thing on every tick.
    setPlacement((prev) => (samePlacement(prev, next) ? prev : next))
  }, [
    elementRef,
    pointX,
    pointY,
    panelRef,
    width,
    minWidth,
    maxWidth,
    gap,
    margin,
    maxHeight,
    desiredHeight,
    flipThreshold,
    align,
  ])

  useLayoutEffect(() => {
    if (!open) return
    measure()
    // Capture: triggers ride inside scroll containers (the register, a report
    // card, a modal body) that do not bubble scroll to window.
    const onMove = () => measure()
    document.addEventListener('scroll', onMove, { capture: true, passive: true })
    window.addEventListener('resize', onMove)
    window.visualViewport?.addEventListener('resize', onMove)
    return () => {
      window.visualViewport?.removeEventListener('resize', onMove)
      document.removeEventListener('scroll', onMove, { capture: true })
      window.removeEventListener('resize', onMove)
    }
  }, [open, measure])

  // The panel does not exist when the effect above first runs — nothing is
  // rendered until a placement exists — so its measurement used the assumed
  // height. `measured` re-runs this once the panel is in the DOM, and the
  // observer keeps it right afterwards: a combobox list filtering down as you
  // type changes height without the trigger moving an inch. ResizeObserver
  // delivers before paint, so the correction is not a visible jump.
  const measured = placement !== null
  useLayoutEffect(() => {
    const panel = panelRef?.current
    if (!open || !panel) return
    const observer = new ResizeObserver(() => measure())
    observer.observe(panel)
    return () => observer.disconnect()
  }, [open, measured, measure, panelRef])

  // Not cleared on close — clearing is a setState in an effect, and the stale
  // value is unreachable anyway: the layout effect above re-measures before
  // the reopened panel is painted.
  return open ? placement : null
}
