import { History } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useImportHistoryMonth } from '../../../api/budgets'
import { useFormatters } from '../../../hooks/useFormatters'
import { formatMonth } from '../../../utils/dates'
import { Surface } from '../../common/Surface/Surface'
import { groupImportHistory } from './importHistoryGroups'
import './ImportHistoryView.css'

interface Props {
  budgetId: string
  month: string
  /** The import month (served `anchor_month`), named in the banner. */
  importMonth: string
}

/**
 * A month before the import, as YNAB displayed it: Assigned, Activity and
 * Available per category, read-only. Not a budget month — there is no Ready
 * to Assign and no card position, because YNAB's export carries neither per
 * month and IGAB does not re-derive history to invent them.
 */
export function ImportHistoryView({ budgetId, month, importMonth }: Props) {
  const { formatMoney, formatMoneyOrDash } = useFormatters()
  const { data, isLoading, isError } = useImportHistoryMonth(budgetId, month, true)

  return (
    <div className="import-history">
      <p className="import-history__banner" role="note">
        <History size={14} aria-hidden />
        <span>
          Before your budget started — YNAB&apos;s own figures for {formatMonth(month)}, as you
          imported them. Read-only: your budget starts in {formatMonth(importMonth)}. To edit
          earlier months, turn on <Link to="/settings/budget">Edit months before the import</Link>.
        </span>
      </p>
      {isLoading && <p className="import-history__status">Loading {formatMonth(month)}…</p>}
      {isError && (
        <p className="import-history__status">
          This month&apos;s imported figures could not be loaded.
        </p>
      )}
      {data && (
        <Surface variant="raised" className="import-history__table-wrap">
          <table className="import-history__table">
            <thead>
              <tr>
                <th scope="col">Category</th>
                <th scope="col" className="import-history__num">
                  Assigned
                </th>
                <th scope="col" className="import-history__num">
                  Activity
                </th>
                <th scope="col" className="import-history__num">
                  Available
                </th>
              </tr>
            </thead>
            {groupImportHistory(data.rows).map((group) => (
              <tbody key={group.name}>
                <tr className="import-history__group">
                  <th scope="rowgroup" colSpan={3}>
                    {group.name}
                  </th>
                  <td className="import-history__num">{formatMoneyOrDash(group.available)}</td>
                </tr>
                {group.rows.map((row) => (
                  <tr key={`${group.name}/${row.category}`}>
                    <th scope="row" className="import-history__category">
                      {row.category}
                    </th>
                    <td className="import-history__num">{formatMoney(row.assigned)}</td>
                    <td className="import-history__num">{formatMoneyOrDash(row.activity)}</td>
                    <td
                      className={`import-history__num${
                        row.available !== null && row.available < 0
                          ? ' import-history__num--negative'
                          : ''
                      }`}
                    >
                      {formatMoneyOrDash(row.available)}
                    </td>
                  </tr>
                ))}
              </tbody>
            ))}
          </table>
        </Surface>
      )}
    </div>
  )
}
