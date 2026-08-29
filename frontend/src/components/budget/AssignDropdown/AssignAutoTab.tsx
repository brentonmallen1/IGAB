import { AlertTriangle } from 'lucide-react'
import { useFormatters } from '../../../hooks/useFormatters'
import type { AssignStrategy } from '../../../types'
import type { AssignStrategyTotalsResponse } from '../../../api/assign'
import { AUTO_STRATEGY_ORDER, RESET_STRATEGY_ORDER, STRATEGY_META } from './strategyMeta'

interface Props {
  totals: AssignStrategyTotalsResponse | undefined
  isLoading: boolean
  /** Categories overspent this month — counted server-side beside total_overspent. */
  overspentCount: number
  onPickStrategy: (strategy: AssignStrategy) => void
  onCoverOverspent: () => void
}

/**
 * One row per bulk strategy, each showing the dollar amount it would move —
 * the same number the preview modal and apply will produce. Clicking a row
 * opens the preview modal; nothing applies from here.
 */
export function AssignAutoTab({ totals, isLoading, overspentCount, onPickStrategy, onCoverOverspent }: Props) {
  const { formatMoney } = useFormatters()

  if (isLoading || !totals) {
    return <div className="assign-dropdown__loading">Calculating…</div>
  }

  const byStrategy = new Map(totals.strategies.map((s) => [s.strategy, s]))
  // The cash part: what this row would actually fund. Credit-funded red rode
  // onto a card and no assignment retires it, so offering to cover it would
  // name a number the dialog then refuses to act on.
  const overspent = Number(totals.total_overspent_cash)
  const underfundedNeeded = Number(byStrategy.get('underfunded')?.total_needed ?? 0)
  // Overspending and underfunding measure different things: a category with
  // no target is never "underfunded" however overspent it is. When the two
  // disagree, say so where the $0 would otherwise look wrong.
  const overspentButNotUnderfunded = overspent > 0 && underfundedNeeded === 0

  function renderRow(strategy: AssignStrategy) {
    const row = byStrategy.get(strategy)
    if (!row) return null
    const totalAmount = Number(row.total_amount)
    const totalNeeded = row.total_needed === null ? null : Number(row.total_needed)
    const isUnderfunded = strategy === 'underfunded'
    const disabled = isUnderfunded
      ? totalNeeded === null || totalNeeded === 0
      : row.affected_count === 0
    const clamped = isUnderfunded && totalNeeded !== null && totalNeeded > Number(row.to_assign)

    return (
      <button
        key={strategy}
        type="button"
        data-assign-row
        className="assign-dropdown__row"
        disabled={disabled}
        onClick={() => onPickStrategy(strategy)}
      >
        <span className="assign-dropdown__row-label">{STRATEGY_META[strategy].label}</span>
        <span className="assign-dropdown__row-amount tabular">
          {formatMoney(totalAmount)}
          {clamped && (
            <span className="assign-dropdown__row-sub">of {formatMoney(totalNeeded)} needed</span>
          )}
        </span>
      </button>
    )
  }

  return (
    <div className="assign-dropdown__rows" role="menu">
      <button
        type="button"
        data-assign-row
        className={`assign-dropdown__row ${overspent > 0 ? 'assign-dropdown__row--warning' : ''}`}
        disabled={overspent === 0}
        onClick={onCoverOverspent}
      >
        <span className="assign-dropdown__row-label">
          <AlertTriangle size={13} />
          Cover Overspending
          {overspent > 0 && overspentCount > 0 && (
            <span className="assign-dropdown__row-sub">
              {overspentCount} {overspentCount === 1 ? 'category' : 'categories'}
            </span>
          )}
        </span>
        <span className="assign-dropdown__row-amount tabular">{formatMoney(-overspent)}</span>
      </button>
      {AUTO_STRATEGY_ORDER.map(renderRow)}
      {overspentButNotUnderfunded && (
        <div className="assign-dropdown__note">
          Overspending isn't a target shortfall — Cover Overspending is the row for it.
        </div>
      )}
      <div className="assign-dropdown__divider" />
      {RESET_STRATEGY_ORDER.map(renderRow)}
    </div>
  )
}
