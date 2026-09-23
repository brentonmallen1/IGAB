import { groupedCategorySections } from '../../../utils/categoryPickers'
import { useState } from 'react'
import { ArrowRightLeft } from 'lucide-react'
import { useMoveHistory, useMoveMoney } from '../../../api/budgets'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { CategoryCombobox } from '../../common/CategoryCombobox/CategoryCombobox'
import { useFormatters } from '../../../hooks/useFormatters'
import { AmountInput } from '../../common/AmountInput/AmountInput'
import { expressionToCents } from '../../../utils/amountExpression'
import type { Category } from '../../../types'
import type { ReactNode } from 'react'
import './MoveMoneyPopover.css'

const TBA = '__tba__'

interface Props {
  budgetId: string
  month: string
  category: Category
  /** Current available for this category (negative = overspent) */
  available: number
  /** What the amount box opens at, where the whole balance is the wrong
   *  offer. A card's envelope is the case: it is holding money for a bill, so
   *  the useful default is the part of it no debt needs, not all of it.
   *  Presentation only — the move itself is unchanged, which is why this is a
   *  prop here rather than a second form somewhere else. */
  prefill?: number
  /** Stated under the amount box: what taking this money out will do. Shown
   *  where the consequence is not obvious from the row the user is looking
   *  at. */
  footnote?: ReactNode
  /** Called after a successful move (and only then) */
  onClose: () => void
}

/**
 * The core envelope action: cover an overspent category from another envelope
 * (or Ready to Assign), or move surplus out of this one. Rendered inside the
 * desktop popover and the mobile bottom sheet.
 */
export function MoveMoneyForm({
  budgetId,
  month,
  category,
  available,
  prefill,
  footnote,
  onClose,
}: Props) {
  const { formatMoney } = useFormatters()
  const isCover = available < 0
  const { data: categories = [] } = useCategories(budgetId)
  const { data: groups = [] } = useCategoryGroups(budgetId)
  const moveMoney = useMoveMoney(budgetId)
  const { data: history = [] } = useMoveHistory(budgetId, month, true)

  const [otherId, setOtherId] = useState<string>(TBA)
  const [amount, setAmount] = useState(() => (prefill ?? Math.abs(available)).toFixed(2))
  const [error, setError] = useState<string | null>(null)

  const otherCategories = categories.filter((c) => c.is_assignable && c.id !== category.id)
  const groupedOthers = groupedCategorySections(otherCategories, groups)
  const nameOf = (id: string | null) =>
    id === null ? 'Ready to Assign' : (categories.find((c) => c.id === id)?.name ?? '—')

  const categoryMoves = history
    .filter((m) => m.from_category_id === category.id || m.to_category_id === category.id)
    .slice(0, 4)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    // The same parser the box evaluates with, so an expression the user
    // never blurred out of ("40 + 20", then Enter) commits as the number it
    // shows. `toCents` was parseFloat underneath and read "1,250" as 1.
    const cents = expressionToCents(amount)
    if (isNaN(cents)) {
      setError('That isn’t an amount — digits, or a sum like 40 + 20.')
      return
    }
    if (cents <= 0) {
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
    <>
      <div className="move-money-popover__title">
        <ArrowRightLeft size={13} />
        {isCover
          ? `Cover ${formatMoney(Math.abs(available))} overspent in ${category.name}`
          : `Move money out of ${category.name}`}
      </div>

      <form className="move-money-popover__form" onSubmit={handleSubmit}>
        <div className="move-money-popover__field">
          <span>{isCover ? 'From' : 'To'}</span>
          <CategoryCombobox
            value={otherId}
            onChange={(id) => setOtherId(id ?? TBA)}
            groups={groupedOthers}
            topOptions={[{ id: TBA, label: 'Ready to Assign' }]}
            sheetTitle={isCover ? 'Cover from' : 'Move to'}
            aria-label={isCover ? 'Cover from' : 'Move to'}
          />
        </div>
        <label className="move-money-popover__field">
          <span>Amount</span>
          <AmountInput
            value={amount}
            onValueChange={setAmount}
            autoFocus
            onFocus={(e) => e.target.select()}
          />
        </label>
        {footnote && <div className="move-money-popover__footnote">{footnote}</div>}
        <button type="submit" className="move-money-popover__submit" disabled={moveMoney.isPending}>
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
    </>
  )
}
