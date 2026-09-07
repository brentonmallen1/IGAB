import { useCategoryHistoryReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'

interface Props {
  categoryId: string
  budgetId: string
}

/** The last six months of this envelope, as the Category History report
 *  serves them — the same endpoint, so the two cannot disagree. */
export function HistorySection({ categoryId, budgetId }: Props) {
  const { formatMoney, formatMonth } = useFormatters()
  const { data } = useCategoryHistoryReport(budgetId, categoryId, 6)
  if (!data || data.months.length === 0) return null
  return (
    <div className="inspector-section">
      <div className="inspector-section__title">Recent history</div>
      <table className="inspector-history">
        <thead>
          <tr>
            <th scope="col">Month</th>
            <th scope="col">Assigned</th>
            <th scope="col">Spent</th>
            <th scope="col">Left</th>
          </tr>
        </thead>
        <tbody>
          {[...data.months].reverse().map((m) => (
            <tr key={m.month}>
              <td>{formatMonth(m.month)}</td>
              <td>{formatMoney(m.assigned)}</td>
              <td>{formatMoney(Math.abs(Math.min(m.activity, 0)))}</td>
              <td className={m.available < 0 ? 'inspector-history__neg' : ''}>
                {formatMoney(m.available)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
