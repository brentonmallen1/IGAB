/**
 * Where a fixed-position portal panel goes relative to the control that opened
 * it.
 *
 * There were five copies of this arithmetic — TagPicker, Combobox,
 * MultiSelectCombobox, AssignDropdown, InfoPopover — and they had diverged in
 * exactly the way duplicated rules do. Only two clamped horizontally, so the
 * other three ran off the right edge. Only one flipped upward, so a combobox
 * opened near the bottom of the register rendered its list below the viewport.
 * Only some capped the height against the space actually available. None of
 * that was a decision; it was five people solving the same problem on
 * different days.
 *
 * Pure on purpose: the viewport is a parameter, not a global, so every branch
 * is testable without a browser. The React wiring — measuring the trigger,
 * re-measuring on scroll — lives in useAnchoredPosition.
 *
 * The second round of this rule, 2026-09-07: three more surfaces were still
 * running off the bottom, by three different mechanisms. Every one of them
 * was a *guess about height* standing in for a measurement — this module's
 * fixed `flipThreshold`, ContextMenu's `menuHeight = 280`, and two callers
 * subtracting a magic 160 from the anchor. A panel's height is knowable; the
 * fix is to measure it and pass it here as `desiredHeight`, not to tune the
 * constants. eslint now refuses `getBoundingClientRect` and `window.inner*`
 * outside this module and its hook, so a ninth copy cannot be written by
 * accident.
 */

/** The parts of a DOMRect this needs. Taking the narrow shape, rather than
 *  DOMRect itself, is what lets tests state a case in one line. */
export interface AnchorRect {
  top: number
  bottom: number
  left: number
  width: number
}

export interface Viewport {
  width: number
  height: number
  /** How much of the viewport is occluded, top and bottom. A fixed panel is
   *  positioned against the LAYOUT viewport, so `height` stays the layout
   *  height and the occlusion is expressed separately rather than by shrinking
   *  it — otherwise every `bottom` this returns would be off by the inset.
   *  On iOS a raised keyboard occludes the bottom; useAppViewport computes the
   *  same two numbers for CSS (--vv-top / --vv-bottom) and this reuses it. */
  inset?: { top: number; bottom: number }
}

export interface AnchoredPlacement {
  /** Set when the panel hangs below the trigger. */
  top?: number
  /** Set instead of `top` when the panel flipped above it. */
  bottom?: number
  left: number
  width: number
  maxHeight: number
}

export interface AnchorOptions {
  /** A fixed width, or 'trigger' to match the control's own width. */
  width?: number | 'trigger'
  minWidth?: number
  maxWidth?: number
  /** Distance between the trigger's edge and the panel. */
  gap?: number
  /** How close to the viewport edge the panel may come. */
  margin?: number
  /** The panel's own preferred cap, before the viewport gets a say. */
  maxHeight?: number
  /** How tall the panel actually wants to be — its measured content height.
   *  This is what decides the flip: a 700px popover with 300px below it and
   *  500px above belongs above, and no fixed pixel threshold can know that.
   *  useAnchoredPosition measures it; pass it directly only when the height
   *  is known ahead of paint. */
  desiredHeight?: number
  /** The height to assume when `desiredHeight` is unknown — the first paint
   *  of an opening panel, or a caller that never measures. Below ~2 rows of
   *  options, "below" is not a placement. */
  flipThreshold?: number
  /** Which edge of the trigger the panel lines up with. 'end' puts the
   *  panel's right edge on the trigger's right edge — what a popover opened
   *  from a button at the right of a row wants. 'center' centres it over the
   *  trigger, which is what a tooltip wants. Clamped to the viewport in
   *  every case. */
  align?: 'start' | 'end' | 'center'
  /** Which side to try first. Dropdowns hang below; a tooltip sits above its
   *  host and drops below only when there is no headroom. Either way the
   *  other side is used when the preferred one cannot show the panel. */
  prefer?: 'below' | 'above'
}

const DEFAULTS = {
  gap: 2,
  margin: 8,
  maxHeight: Number.POSITIVE_INFINITY,
  flipThreshold: 160,
} as const

function resolveWidth(trigger: AnchorRect, viewport: Viewport, o: AnchorOptions, margin: number) {
  const requested = o.width === 'trigger' || o.width === undefined ? trigger.width : o.width
  const bounded = Math.min(
    Math.max(requested, o.minWidth ?? 0),
    o.maxWidth ?? Number.POSITIVE_INFINITY
  )
  // The viewport wins over every preference: a panel wider than the screen has
  // no good left edge, so cap before clamping rather than clamping to a
  // negative.
  return Math.min(bounded, viewport.width - 2 * margin)
}

/**
 * The panel's left edge: lined up with the trigger, then pulled back inside
 * the viewport when that would overhang.
 *
 * Math.max comes last so a viewport narrower than the panel still yields a
 * placement on screen rather than a negative left. MoveMoneyPopover was the
 * sixth copy of this arithmetic, and the one that expressed 'end' as
 * `rect.right - 280` with no vertical clamp and no flip — a row near the
 * bottom of the grid opened it below the fold. Tooltip was the seventh, and
 * centred with a CSS transform before clamping the centre, so a tooltip on
 * the inspector's right edge still hung half off.
 */
function resolveLeft(
  trigger: AnchorRect,
  viewport: Viewport,
  width: number,
  margin: number,
  align: AnchorOptions['align']
) {
  const preferred =
    align === 'end'
      ? trigger.left + trigger.width - width
      : align === 'center'
        ? trigger.left + trigger.width / 2 - width / 2
        : trigger.left
  return Math.max(margin, Math.min(preferred, viewport.width - width - margin))
}

/**
 * Which side of the trigger the panel goes, and how tall it may be there.
 *
 * The rule that keeps overlays on screen: the panel needs as much room as it
 * actually wants, and a side that cannot give it gives way to one that can.
 * Every off-screen overlay this app has shipped came from substituting a
 * constant for `desiredHeight` — a 160px threshold, a 280px guess, a magic
 * 160 subtracted from the anchor. SystemTagsHelp is ~700px of content: with
 * 300px below the trigger it cleared the old threshold, stayed below, and
 * painted as an unreadable sliver while several hundred px sat free above.
 */
function resolveVertical(
  trigger: AnchorRect,
  viewport: Viewport,
  options: AnchorOptions,
  gap: number,
  margin: number
): Pick<AnchoredPlacement, 'top' | 'bottom' | 'maxHeight'> {
  const cap = options.maxHeight ?? DEFAULTS.maxHeight
  const spaceBelow = viewport.height - (viewport.inset?.bottom ?? 0) - trigger.bottom - margin
  const spaceAbove = trigger.top - (viewport.inset?.top ?? 0) - margin

  // Measured height when we have it, the assumed height when we do not.
  const needed = Math.min(
    cap,
    options.desiredHeight ?? options.flipThreshold ?? DEFAULTS.flipThreshold
  )

  // The preferred side keeps ties: a dropdown in the middle of the page opens
  // downward even when the room above is a few pixels greater, and a tooltip
  // stays above its host on the same terms.
  const preferAbove = options.prefer === 'above'
  const roomPreferred = preferAbove ? spaceAbove : spaceBelow
  const roomOther = preferAbove ? spaceBelow : spaceAbove
  const gaveWay = roomPreferred < needed && roomOther > roomPreferred

  // `bottom` is measured from the LAYOUT viewport's bottom edge, because that
  // is what a fixed element's `bottom` resolves against — the occlusion inset
  // belongs in the room calculation, never here.
  return (preferAbove ? !gaveWay : gaveWay)
    ? { bottom: viewport.height - trigger.top + gap, maxHeight: Math.min(cap, spaceAbove) }
    : { top: trigger.bottom + gap, maxHeight: Math.min(cap, spaceBelow) }
}

export function placeAnchored(
  trigger: AnchorRect,
  viewport: Viewport,
  options: AnchorOptions = {}
): AnchoredPlacement {
  const gap = options.gap ?? DEFAULTS.gap
  const margin = options.margin ?? DEFAULTS.margin
  const width = resolveWidth(trigger, viewport, options, margin)

  const left = resolveLeft(trigger, viewport, width, margin, options.align)

  return { left, width, ...resolveVertical(trigger, viewport, options, gap, margin) }
}

/** Whether two placements would paint identically. Scrolling a list inside an
 *  open panel fires scroll events that re-measure an unmoved trigger; without
 *  this every one of them is a state update. Combobox used to special-case
 *  that by ignoring scrolls originating inside itself — this covers the same
 *  ground and every other no-op besides. */
export function samePlacement(a: AnchoredPlacement | null, b: AnchoredPlacement | null) {
  if (a === b) return true
  if (!a || !b) return false
  return (
    a.top === b.top &&
    a.bottom === b.bottom &&
    a.left === b.left &&
    a.width === b.width &&
    a.maxHeight === b.maxHeight
  )
}
