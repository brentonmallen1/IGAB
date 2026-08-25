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
  /** Flip above the trigger when the room below is under this and the room
   *  above is greater. Below ~2 rows of options, "below" is not a placement. */
  flipThreshold?: number
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

export function placeAnchored(
  trigger: AnchorRect,
  viewport: Viewport,
  options: AnchorOptions = {}
): AnchoredPlacement {
  const gap = options.gap ?? DEFAULTS.gap
  const margin = options.margin ?? DEFAULTS.margin
  const preferredMaxHeight = options.maxHeight ?? DEFAULTS.maxHeight
  const flipThreshold = options.flipThreshold ?? DEFAULTS.flipThreshold

  const width = resolveWidth(trigger, viewport, options, margin)

  // Aligned to the trigger's left edge, pulled back inside the viewport when
  // that would overhang. Math.max last so a viewport narrower than the panel
  // still yields a placement on screen rather than a negative left.
  const left = Math.max(margin, Math.min(trigger.left, viewport.width - width - margin))

  const spaceBelow = viewport.height - trigger.bottom - margin
  const spaceAbove = trigger.top - margin

  if (spaceBelow < flipThreshold && spaceAbove > spaceBelow) {
    return {
      bottom: viewport.height - trigger.top + gap,
      left,
      width,
      maxHeight: Math.min(preferredMaxHeight, spaceAbove),
    }
  }

  return {
    top: trigger.bottom + gap,
    left,
    width,
    maxHeight: Math.min(preferredMaxHeight, spaceBelow),
  }
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
