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
export function MoveMoneyPopover({ budgetId, month, category, available, position, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
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
