import { useCategories } from '../../../api/categories'
import { useUndoMove } from '../../../api/budgets'
import { Undo2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { useFormatters } from '../../../hooks/useFormatters'
import type { BudgetMove } from '../../../api/budgets'
import './TbaHero.css'

interface Props {
  budgetId: string
  moves: BudgetMove[]
}

/** Full move log for a month; a null side renders as "Ready to Assign". */
export function MoveHistoryList({ budgetId, moves }: Props) {
  const { formatMoney, formatDate } = useFormatters()
  const { data: categories = [] } = useCategories(budgetId)
  const undoMove = useUndoMove(budgetId)
  // A real undo, scoped to this one move: the server reverses its amount and
  // drops the row, so the list shrinks instead of gaining a mirror-image move
  // that could itself be "undone" forever.
  async function undo(m: BudgetMove) {
    try {
      await undoMove.mutateAsync({ id: m.id, month: m.month })
      toast.success(
        `Undid the ${formatMoney(Number(m.amount))} move to ${nameOf(m.to_category_id)}`
      )
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Could not undo this move')
    }
  }
  const nameOf = (id: string | null) =>
    id === null ? 'Ready to Assign' : (categories.find((c) => c.id === id)?.name ?? '—')
  const dayOf = (iso: string) => {
    const d = formatDate(iso.slice(0, 10))
    const parts = d.split(/[\s/-]/)
    return parts.length >= 2 ? `${parts[0]} ${parts[1].replace(/,$/, '')}` : d
  }

  return (
    <ul className="move-history">
      {moves.map((m) => (
        <li key={m.id} className="move-history__item">
          <span className="move-history__date">{dayOf(m.created_at)}</span>
          <span className="move-history__amount">{formatMoney(Number(m.amount))}</span>
          <span className="move-history__route">
            {nameOf(m.from_category_id)} → {nameOf(m.to_category_id)}
          </span>
          <button
            type="button"
            className="move-history__back"
            onClick={() => void undo(m)}
            disabled={undoMove.isPending}
            aria-label={`Undo the ${formatMoney(Number(m.amount))} move to ${nameOf(m.to_category_id)}`}
            title="Undo this move"
          >
            <Undo2 size={13} />
          </button>
        </li>
      ))}
    </ul>
  )
}
