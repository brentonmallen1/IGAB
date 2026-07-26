import { AlertTriangle } from 'lucide-react'
import { formatMoney } from '../../../utils/money'
import type { AssignStrategy } from '../../../types'
import type { AssignStrategyTotalsResponse } from '../../../api/assign'
import { AUTO_STRATEGY_ORDER, RESET_STRATEGY_ORDER, STRATEGY_META } from './strategyMeta'

interface Props {
  totals: AssignStrategyTotalsResponse | undefined
  isLoading: boolean
  onPickStrategy: (strategy: AssignStrategy) => void
  onCoverOverspent: () => void
}

/**
 * One row per bulk strategy, each showing the dollar amount it would move —
 * the same number the preview modal and apply will produce. Clicking a row
 * opens the preview modal; nothing applies from here.
 */
export function AssignAutoTab({ totals, isLoading, onPickStrategy, onCoverOverspent }: Props) {
  if (isLoading || !totals) {
    return <div className="assign-dropdown__loading">Calculating…</div>
  }

  const byStrategy = new Map(totals.strategies.map((s) => [s.strategy, s]))
  const overspent = Number(totals.total_overspent)

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
      {AUTO_STRATEGY_ORDER.map(renderRow)}
      <div className="assign-dropdown__divider" />
      {RESET_STRATEGY_ORDER.map(renderRow)}
      {overspent > 0 && (
        <>
          <div className="assign-dropdown__divider" />
          <button
            type="button"
            data-assign-row
            className="assign-dropdown__row assign-dropdown__row--warning"
            onClick={onCoverOverspent}
          >
            <span className="assign-dropdown__row-label">
              <AlertTriangle size={13} />
              Cover Overspending
            </span>
            <span className="assign-dropdown__row-amount tabular">{formatMoney(-overspent)}</span>
          </button>
        </>
      )}
    </div>
  )
}
