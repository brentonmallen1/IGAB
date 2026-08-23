import { groupedCategorySections } from '../../../utils/categoryPickers'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { useMoveMoney } from '../../../api/budgets'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { useFormatters } from '../../../hooks/useFormatters'
import { toCents } from '../../../utils/money'
import { GroupedCategoryOptions } from '../../common/GroupedCategoryOptions/GroupedCategoryOptions'

interface Props {
  budgetId: string
  month: string
  tba: number
  onDone: () => void
}

/** Assign a dollar amount from Ready to Assign into one chosen category. */
export function AssignManualTab({ budgetId, month, tba, onDone }: Props) {
  const { formatMoney } = useFormatters()
  const { data: categories = [] } = useCategories(budgetId)
  const { data: groups = [] } = useCategoryGroups(budgetId)
  const moveMoney = useMoveMoney(budgetId)

  const [amount, setAmount] = useState(() => (tba > 0 ? tba.toFixed(2) : ''))
  const [categoryId, setCategoryId] = useState('')
  const [error, setError] = useState<string | null>(null)

  const eligible = categories.filter((c) => c.is_assignable)
  const eligibleSections = groupedCategorySections(eligible, groups)

  const cents = toCents(amount)
  const exceedsTba = !isNaN(cents) && cents / 100 > tba

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (isNaN(cents) || cents <= 0) {
      setError('Enter an amount greater than zero')
      return
    }
    if (!categoryId) {
      setError('Choose a category')
      return
    }
    setError(null)
    try {
      await moveMoney.mutateAsync({
        from_category_id: null,
        to_category_id: categoryId,
        amount: cents / 100,
        month,
      })
      const name = eligible.find((c) => c.id === categoryId)?.name ?? 'category'
      toast.success(`Assigned ${formatMoney(cents / 100)} to ${name}`)
      onDone()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      setError(detail ?? 'Assign failed')
    }
  }

  return (
    <form className="assign-dropdown__manual" onSubmit={handleSubmit}>
      <label className="assign-dropdown__field">
        <span>Assign</span>
        <input
          type="number"
          min="0.01"
          step="0.01"
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          autoFocus
          onFocus={(e) => e.target.select()}
        />
      </label>
      <label className="assign-dropdown__field">
        <span>To</span>
        <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          <option value="" disabled>
            Choose a category…
          </option>
          <GroupedCategoryOptions groups={eligibleSections} />
        </select>
      </label>
      {exceedsTba && (
        <div className="assign-dropdown__warning">
          Exceeds Ready to Assign ({formatMoney(tba)}) — TBA will go negative.
        </div>
      )}
      {error && <div className="assign-dropdown__error">{error}</div>}
      <div className="assign-dropdown__manual-actions">
        <button
          type="submit"
          className="assign-dropdown__submit"
          disabled={moveMoney.isPending}
        >
          {moveMoney.isPending ? 'Assigning…' : 'Assign'}
        </button>
      </div>
    </form>
  )
}
