import { useEffect, useRef, useState } from 'react'
import { ArrowRightLeft } from 'lucide-react'
import { useMoveHistory, useMoveMoney } from '../../../api/budgets'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { formatMoney, toCents } from '../../../utils/money'
import type { Category } from '../../../types'
import './MoveMoneyPopover.css'

const TBA = '__tba__'

interface Props {
  budgetId: string
  month: string
  category: Category
  /** Current available for this category (negative = overspent) */
  available: number
  position: { x: number; y: number }
  onClose: () => void
}

/**
 * The core envelope action: cover an overspent category from another
 * envelope (or Ready to Assign), or move surplus out of this one.
 */
export function MoveMoneyPopover({ budgetId, month, category, available, position, onClose }: Props) {
  const isCover = available < 0
  const { data: categories = [] } = useCategories(budgetId)
  const { data: groups = [] } = useCategoryGroups(budgetId)
  const moveMoney = useMoveMoney(budgetId)
  const { data: history = [] } = useMoveHistory(budgetId, month, true)

  const [otherId, setOtherId] = useState<string>(TBA)
  const [amount, setAmount] = useState(() => Math.abs(available).toFixed(2))
  const [error, setError] = useState<string | null>(null)
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

  const systemGroupIds = new Set(groups.filter((g) => g.is_system).map((g) => g.id))
  const otherCategories = categories.filter(
    (c) => c.id !== category.id && !c.is_hidden && !systemGroupIds.has(c.category_group_id)
  )
  const nameOf = (id: string | null) =>
    id === null ? 'Ready to Assign' : (categories.find((c) => c.id === id)?.name ?? '—')

  const categoryMoves = history
    .filter((m) => m.from_category_id === category.id || m.to_category_id === category.id)
    .slice(0, 4)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const cents = toCents(amount)
    if (isNaN(cents) || cents <= 0) {
      setError('Enter an amount greater than zero')
      return
    }
    setError(null)
    const other = otherId === TBA ? null : otherId
    try {
      await moveMoney.mutateAsync({
        from_category_id: isCover ? other : category.id,
        to_category_id: isCover ? category.id : other,
        amount: cents / 100,
        month,
      })
      onClose()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'Move failed')
    }
  }

  return (
    <div
      ref={ref}
      className="move-money-popover"
      style={{ top: position.y, left: position.x }}
      role="dialog"
      aria-label={isCover ? 'Cover overspending' : 'Move money'}
    >
      <div className="move-money-popover__title">
        <ArrowRightLeft size={13} />
        {isCover
          ? `Cover ${formatMoney(Math.abs(available))} overspent in ${category.name}`
          : `Move money out of ${category.name}`}
      </div>

      <form className="move-money-popover__form" onSubmit={handleSubmit}>
        <label className="move-money-popover__field">
          <span>{isCover ? 'From' : 'To'}</span>
          <select value={otherId} onChange={(e) => setOtherId(e.target.value)}>
            <option value={TBA}>Ready to Assign</option>
            {otherCategories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </label>
        <label className="move-money-popover__field">
          <span>Amount</span>
          <input
            type="number"
            min="0.01"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            autoFocus
            onFocus={(e) => e.target.select()}
          />
        </label>
        <button
          type="submit"
          className="move-money-popover__submit"
          disabled={moveMoney.isPending}
        >
          {moveMoney.isPending ? 'Moving…' : isCover ? 'Cover Overspending' : 'Move Money'}
        </button>
        {error && <div className="move-money-popover__error">{error}</div>}
      </form>

      {categoryMoves.length > 0 && (
        <div className="move-money-popover__history">
          <div className="move-money-popover__history-title">Moves this month</div>
          <ul>
            {categoryMoves.map((m) => (
              <li key={m.id}>
                {formatMoney(Number(m.amount))} · {nameOf(m.from_category_id)} →{' '}
                {nameOf(m.to_category_id)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
