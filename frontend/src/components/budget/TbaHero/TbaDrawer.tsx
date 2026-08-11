import { AlertTriangle, CalendarClock } from 'lucide-react'
import { useMoveHistory } from '../../../api/budgets'
import { useFormatters } from '../../../hooks/useFormatters'
import { MoveHistoryList } from './MoveHistoryList'
import './TbaHero.css'

interface Props {
  budgetId: string
  month: string
  /** Gates the move-history fetch so closed drawers cost nothing */
  open: boolean
  totalOverspent: number
  overspentCount: number
  assignedInFuture: number
  onCoverOverspent: () => void
}

export function TbaDrawer({
  budgetId,
  month,
  open,
  totalOverspent,
  overspentCount,
  assignedInFuture,
  onCoverOverspent,
}: Props) {
  const { formatMoney } = useFormatters()
  const { data: moves = [] } = useMoveHistory(budgetId, month, open)
  const hasOverspending = Number(totalOverspent) > 0

  return (
    <div className="tba-drawer">
      {assignedInFuture !== 0 && (
        <div className="tba-drawer__section">
          <div className="tba-drawer__future">
            <CalendarClock size={14} className="tba-drawer__future-icon" />
            <span className="tba-drawer__future-text">
              {formatMoney(assignedInFuture)} assigned in future months — already deducted from To
              Be Assigned
            </span>
          </div>
        </div>
      )}
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
