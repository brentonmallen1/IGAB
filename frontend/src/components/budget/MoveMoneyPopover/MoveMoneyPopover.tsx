import { useEffect, useRef, type RefObject } from 'react'
import { MoveMoneyForm } from './MoveMoneyForm'
import { useAnchoredPosition } from '../../../hooks/useAnchoredPosition'
import type { Category } from '../../../types'
import './MoveMoneyPopover.css'

/** The one width the popover has — read by the geometry, not restated in CSS. */
const POPOVER_WIDTH = 320

interface Props {
  budgetId: string
  month: string
  category: Category
  /** Current available for this category (negative = overspent) */
  available: number
  /** The button that opened it; the popover hangs off its right edge and
   *  flips above it near the bottom of the viewport. */
  anchorRef: RefObject<HTMLElement | null>
  onClose: () => void
}

/** Desktop positioning + dismiss wrapper around MoveMoneyForm (mobile uses a BottomSheet). */
export function MoveMoneyPopover({
  budgetId,
  month,
  category,
  available,
  anchorRef,
  onClose,
}: Props) {
  const ref = useRef<HTMLDivElement>(null)
  // The same geometry every dropdown and popover uses: viewport-clamped,
  // flipping above when the room below runs out. This was the sixth copy.
  // It used to raise flipThreshold to 260 to guess its own height; passing
  // the panel means the hook measures it instead, and the guess goes.
  const placement = useAnchoredPosition(
    anchorRef,
    true,
    { width: POPOVER_WIDTH, align: 'end', gap: 4 },
    ref
  )

  useEffect(() => {
    function handler(e: MouseEvent) {
      const target = e.target as HTMLElement
      // The category combobox portals its dropdown to <body>; clicking an
      // option there must not dismiss the popover
      if (ref.current && !ref.current.contains(target) && !target.closest('.combobox__dropdown')) {
        onClose()
      }
    }
    function onKey(e: KeyboardEvent) {
      // Let an open combobox consume Escape to close just its dropdown
      if (e.key === 'Escape' && !(e.target as HTMLElement).closest?.('.combobox--open')) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handler)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', handler)
      document.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  const isCover = available < 0
  if (!placement) return null

  return (
    <div
      ref={ref}
      className="move-money-popover"
      style={{
        top: placement.top,
        bottom: placement.bottom,
        left: placement.left,
        width: placement.width,
        maxHeight: placement.maxHeight,
      }}
      role="dialog"
      aria-label={isCover ? 'Cover overspending' : 'Move money'}
    >
      <MoveMoneyForm
        budgetId={budgetId}
        month={month}
        category={category}
        available={available}
        onClose={onClose}
      />
    </div>
  )
}
