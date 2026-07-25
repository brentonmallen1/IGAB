import { AlertTriangle } from 'lucide-react'
import { useMoveHistory } from '../../../api/budgets'
import { formatMoney } from '../../../utils/money'
import { MoveHistoryList } from './MoveHistoryList'
import './TbaHero.css'

interface Props {
  budgetId: string
  month: string
  /** Gates the move-history fetch so closed drawers cost nothing */
  open: boolean
  totalOverspent: number
  overspentCount: number
  onCoverOverspent: () => void
}

export function TbaDrawer({
  budgetId,
  month,
  open,
  totalOverspent,
  overspentCount,
  onCoverOverspent,
}: Props) {
  const { data: moves = [] } = useMoveHistory(budgetId, month, open)
  const hasOverspending = Number(totalOverspent) > 0

  return (
    <div className="tba-drawer">
      {hasOverspending && (
        <div className="tba-drawer__section">
          <div className="tba-drawer__overspent">
            <AlertTriangle size={14} className="tba-drawer__overspent-icon" />
            <span className="tba-drawer__overspent-text">
              {overspentCount > 0
                ? `${overspentCount} ${overspentCount === 1 ? 'category' : 'categories'} overspent`
                : 'Overspent'}{' '}
              · {formatMoney(-totalOverspent)}
            </span>
            <button className="tba-drawer__cover-btn" onClick={onCoverOverspent}>
              Cover overspending
            </button>
          </div>
        </div>
      )}
      <div className="tba-drawer__section">
        <div className="tba-drawer__section-title">Money moved this month</div>
        {moves.length === 0 ? (
          <div className="tba-drawer__empty">No money moved yet this month.</div>
        ) : (
          <MoveHistoryList budgetId={budgetId} moves={moves} />
        )}
      </div>
    </div>
  )
}
