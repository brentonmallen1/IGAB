import { Fragment, memo, useEffect, useMemo, useRef, useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Search, X } from 'lucide-react'
import { fetchBudgetMonth, useSetAssignment } from '../../../api/budgets'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { useFormatters } from '../../../hooks/useFormatters'
import { addMonths } from '../../../utils/dates'
import { toCents } from '../../../utils/money'
import { parseAssignmentCommit } from '../../../utils/amountExpression'
import { AmountInput } from '../../common/AmountInput/AmountInput'
import type { BudgetMonth, Category, CategoryBalance } from '../../../types'
import { renderableGroups } from '../budgetGroups'
import './MultiMonthSheet.css'
import { ROOT } from '../../../api/queryKeys'

interface Props {
  budgetId: string
}

const COUNTS = [3, 4, 5, 6] as const

/** Editable assigned amount for one (category, month) cell. Commits ripple
 * into later months via the budget-wide budgetMonth invalidation. */
const AssignCell = memo(function AssignCell({
  budgetId,
  categoryId,
  month,
  assigned,
}: {
  budgetId: string
  categoryId: string
  month: string
  assigned: number
}) {
  const { formatMoney } = useFormatters()
  const setAssignment = useSetAssignment(budgetId)
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  function startEdit() {
    setValue(assigned === 0 ? '' : String(assigned))
    setEditing(true)
    setTimeout(() => inputRef.current?.select(), 0)
  }

  function commit() {
    // Expression-aware: "+50" / "*2" adjust the current assignment
    const amount = parseAssignmentCommit(value, assigned)
    if (isNaN(amount)) {
      // Unparseable input must never silently write $0 into the budget
      setEditing(false)
      return
    }
    if (amount !== assigned) setAssignment.mutate({ categoryId, month, amount })
    setEditing(false)
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') commit()
    if (e.key === 'Escape') {
      // Cancel the edit without closing the sheet
      e.stopPropagation()
      setEditing(false)
    }
  }

  if (editing) {
    return (
      <AmountInput
        ref={inputRef}
        className="mm-sheet__assign-input"
        value={value}
        onValueChange={setValue}
        baseCents={toCents(assigned)}
        onBlur={commit}
        onKeyDown={handleKeyDown}
        placeholder="0.00"
      />
    )
  }
  return (
    <button className="mm-sheet__assign-btn tabular" onClick={startEdit} title="Click to edit">
      {assigned === 0 ? <span className="mm-sheet__zero">—</span> : formatMoney(assigned)}
    </button>
  )
})

function moneyClass(n: number): string {
  return n < 0 ? 'negative' : n > 0 ? 'positive' : 'zero'
}

export function MultiMonthSheet({ budgetId }: Props) {
  const selectedMonth = useAppStore((s) => s.selectedMonth)
  const setMultiMonthOpen = useUIStore((s) => s.setMultiMonthOpen)
  const { formatMoney, formatMonth } = useFormatters()

  // Independent anchor: the sheet navigates months without moving the page's
  // selected month.
  const [anchor, setAnchor] = useState(selectedMonth)
  const [count, setCount] = useState<number>(4)
  const [search, setSearch] = useState('')

  const months = useMemo(
    () => Array.from({ length: count }, (_, i) => addMonths(anchor, i)),
    [anchor, count]
  )

  const monthQueries = useQueries({
    queries: months.map((m) => ({
      queryKey: [ROOT.budgetMonth, budgetId, m],
      queryFn: () => fetchBudgetMonth(budgetId, m),
      staleTime: 10_000,
    })),
  })

  const { data: groups = [] } = useCategoryGroups(budgetId)
  const { data: categories = [] } = useCategories(budgetId)

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setMultiMonthOpen(false)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [setMultiMonthOpen])

  // One balance lookup per month, keyed by category id
  const balanceMaps: (Map<string, CategoryBalance> | null)[] = months.map((_, i) => {
    const data: BudgetMonth | undefined = monthQueries[i].data
    if (!data) return null
    return new Map(data.category_balances.map((b) => [b.category_id, b]))
  })

  const query = search.trim().toLowerCase()
  const visibleGroups = renderableGroups(groups)
    .map((g) => ({
      group: g,
      cats: categories.filter(
        (c) =>
          c.category_group_id === g.id && (query === '' || c.name.toLowerCase().includes(query))
      ),
    }))
    .filter(({ cats }) => cats.length > 0)

  function subtotal(cats: Category[], i: number) {
    const map = balanceMaps[i]
    let assigned = 0
    let activity = 0
    let available = 0
    if (map) {
      for (const c of cats) {
        const b = map.get(c.id)
        if (!b) continue
        assigned += Number(b.assigned)
        activity += Number(b.activity)
        available += Number(b.available)
      }
    }
    return { assigned, activity, available }
  }

  return (
    <div className="mm-sheet" role="dialog" aria-modal="true" aria-label="Multi-month view">
      <div className="mm-sheet__toolbar">
        <h2 className="mm-sheet__title">Multi-Month View</h2>

        <div className="mm-sheet__nav">
          <button
            className="mm-sheet__nav-btn"
            onClick={() => setAnchor(addMonths(anchor, -1))}
            title="Earlier month"
            aria-label="Shift window one month earlier"
          >
            <ChevronLeft size={16} />
          </button>
          <span className="mm-sheet__range">
            {formatMonth(months[0])} – {formatMonth(months[months.length - 1])}
          </span>
          <button
            className="mm-sheet__nav-btn"
            onClick={() => setAnchor(addMonths(anchor, 1))}
            title="Later month"
            aria-label="Shift window one month later"
          >
            <ChevronRight size={16} />
          </button>
        </div>

        <div className="mm-sheet__counts">
          {COUNTS.map((n) => (
            <button
              key={n}
              className={`mm-sheet__count-btn ${count === n ? 'mm-sheet__count-btn--active' : ''}`}
              onClick={() => setCount(n)}
              type="button"
            >
              {n}
            </button>
          ))}
        </div>

        <div className="mm-sheet__search">
          <Search size={13} />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter categories…"
            aria-label="Filter categories"
          />
        </div>

        <button
          className="mm-sheet__close"
          onClick={() => setMultiMonthOpen(false)}
          title="Close"
          aria-label="Close multi-month view"
        >
          <X size={18} />
        </button>
      </div>

      <div className="mm-sheet__scroll">
        <table className="mm-sheet__table">
          <thead>
            <tr className="mm-sheet__month-row">
              <th scope="col" className="mm-sheet__corner" />
              {months.map((m, i) => {
                const data = monthQueries[i].data
                return (
                  <th scope="colgroup" colSpan={3} key={m} className="mm-sheet__month-header">
                    <span className="mm-sheet__month-name">{formatMonth(m)}</span>
                    <span
                      className={`mm-sheet__month-tba tabular ${data ? moneyClass(Number(data.to_be_assigned)) : ''}`}
                    >
                      {data ? `${formatMoney(Number(data.to_be_assigned))} to assign` : '…'}
                    </span>
                  </th>
                )
              })}
            </tr>
            <tr className="mm-sheet__label-row">
              <th scope="col" className="mm-sheet__cat-header">
                Category
              </th>
              {months.map((m) => (
                <Fragment key={m}>
                  <th scope="col" className="mm-sheet__col-label mm-sheet__col-label--first">
                    Assigned
                  </th>
                  <th scope="col" className="mm-sheet__col-label">
                    Activity
                  </th>
                  <th scope="col" className="mm-sheet__col-label">
                    Available
                  </th>
                </Fragment>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleGroups.map(({ group, cats }) => (
              <Fragment key={group.id}>
                <tr className="mm-sheet__group-row">
                  <th scope="row" className="mm-sheet__group-name">
                    {group.name}
                  </th>
                  {months.map((m, i) => {
                    const s = subtotal(cats, i)
                    return (
                      <Fragment key={m}>
                        <td className="mm-sheet__group-cell tabular mm-sheet__cell--first">
                          {formatMoney(s.assigned)}
                        </td>
                        <td className="mm-sheet__group-cell tabular">{formatMoney(s.activity)}</td>
                        <td className={`mm-sheet__group-cell tabular ${moneyClass(s.available)}`}>
                          {formatMoney(s.available)}
                        </td>
                      </Fragment>
                    )
                  })}
                </tr>
                {cats.map((cat) => (
                  <tr key={cat.id} className="mm-sheet__cat-row">
                    <th scope="row" className="mm-sheet__cat-name" title={cat.name}>
                      {cat.name}
                    </th>
                    {months.map((m, i) => {
                      const b = balanceMaps[i]?.get(cat.id)
                      const activity = Number(b?.activity ?? 0)
                      const available = Number(b?.available ?? 0)
                      return (
                        <Fragment key={m}>
                          <td className="mm-sheet__cell mm-sheet__cell--first">
                            {balanceMaps[i] ? (
                              <AssignCell
                                budgetId={budgetId}
                                categoryId={cat.id}
                                month={m}
                                assigned={Number(b?.assigned ?? 0)}
                              />
                            ) : (
                              <span className="mm-sheet__zero">…</span>
                            )}
                          </td>
                          <td className="mm-sheet__cell tabular">
                            {activity === 0 ? (
                              <span className="mm-sheet__zero">—</span>
                            ) : (
                              <span className={activity < 0 ? 'negative' : 'positive'}>
                                {formatMoney(activity)}
                              </span>
                            )}
                          </td>
                          <td className={`mm-sheet__cell tabular ${moneyClass(available)}`}>
                            {balanceMaps[i] ? formatMoney(available) : ''}
                          </td>
                        </Fragment>
                      )
                    })}
                  </tr>
                ))}
              </Fragment>
            ))}
            {visibleGroups.length === 0 && (
              <tr>
                <td className="mm-sheet__empty" colSpan={1 + months.length * 3}>
                  {query ? 'No categories match the filter.' : 'No categories yet.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
