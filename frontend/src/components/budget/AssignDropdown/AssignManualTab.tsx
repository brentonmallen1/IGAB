import { useState } from 'react'
import toast from 'react-hot-toast'
import { useMoveMoney } from '../../../api/budgets'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { formatMoney, toCents } from '../../../utils/money'

interface Props {
  budgetId: string
  month: string
  tba: number
  onDone: () => void
}

/** Assign a dollar amount from Ready to Assign into one chosen category. */
export function AssignManualTab({ budgetId, month, tba, onDone }: Props) {
  const { data: categories = [] } = useCategories(budgetId)
  const { data: groups = [] } = useCategoryGroups(budgetId)
  const moveMoney = useMoveMoney(budgetId)

  const [amount, setAmount] = useState(() => (tba > 0 ? tba.toFixed(2) : ''))
  const [categoryId, setCategoryId] = useState('')
  const [error, setError] = useState<string | null>(null)

  const systemGroupIds = new Set(groups.filter((g) => g.is_system).map((g) => g.id))
  const eligibleGroups = groups.filter((g) => !g.is_system && !g.is_hidden)
  const categoriesByGroup = (groupId: string) =>
    categories.filter((c) => c.category_group_id === groupId && !c.is_hidden)
  const eligible = categories.filter(
    (c) => !c.is_hidden && !systemGroupIds.has(c.category_group_id)
  )

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
          {eligibleGroups.map((g) => {
            const cats = categoriesByGroup(g.id)
            if (cats.length === 0) return null
            return (
              <optgroup key={g.id} label={g.name}>
                {cats.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </optgroup>
            )
          })}
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
