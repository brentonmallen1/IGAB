import { CalendarClock } from 'lucide-react'
import { useMoveHistory } from '../../../api/budgets'
import { useFormatters } from '../../../hooks/useFormatters'
import { MoveHistoryList } from './MoveHistoryList'
import './TbaHero.css'

interface Props {
  budgetId: string
  month: string
  /** Gates the move-history fetch so a closed panel costs nothing */
  open: boolean
  assignedInFuture: number
}

export function TbaDrawer({ budgetId, month, open, assignedInFuture }: Props) {
  const { formatMoney } = useFormatters()
  const { data: moves = [] } = useMoveHistory(budgetId, month, open)

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
      <div className="tba-drawer__section">
        {moves.length === 0 ? (
          <div className="tba-drawer__empty">No money moved yet this month.</div>
        ) : (
          <MoveHistoryList budgetId={budgetId} moves={moves} />
        )}
      </div>
    </div>
  )
}
