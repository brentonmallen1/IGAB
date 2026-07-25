import { useCategories } from '../../../api/categories'
import { formatMoney } from '../../../utils/money'
import type { BudgetMove } from '../../../api/budgets'
import './TbaHero.css'

interface Props {
  budgetId: string
  moves: BudgetMove[]
}

/** Full move log for a month; a null side renders as "Ready to Assign". */
export function MoveHistoryList({ budgetId, moves }: Props) {
  const { data: categories = [] } = useCategories(budgetId)
  const nameOf = (id: string | null) =>
    id === null ? 'Ready to Assign' : (categories.find((c) => c.id === id)?.name ?? '—')
  const dayOf = (iso: string) =>
    new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

  return (
    <ul className="move-history">
      {moves.map((m) => (
        <li key={m.id} className="move-history__item">
          <span className="move-history__date">{dayOf(m.created_at)}</span>
          <span className="move-history__amount">{formatMoney(Number(m.amount))}</span>
          <span className="move-history__route">
            {nameOf(m.from_category_id)} → {nameOf(m.to_category_id)}
          </span>
        </li>
      ))}
    </ul>
  )
}
