import { useEffect, useRef } from 'react'
import { MoveMoneyForm } from './MoveMoneyForm'
import type { Category } from '../../../types'
import './MoveMoneyPopover.css'

interface Props {
  budgetId: string
  month: string
  category: Category
  /** Current available for this category (negative = overspent) */
  available: number
  position: { x: number; y: number }
  onClose: () => void
}

/** Desktop positioning + dismiss wrapper around MoveMoneyForm (mobile uses a BottomSheet). */
export function MoveMoneyPopover({
  budgetId,
  month,
  category,
  available,
  position,
  onClose,
}: Props) {
  const ref = useRef<HTMLDivElement>(null)

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

  return (
    <div
      ref={ref}
      className="move-money-popover"
      style={{ top: position.y, left: position.x }}
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
