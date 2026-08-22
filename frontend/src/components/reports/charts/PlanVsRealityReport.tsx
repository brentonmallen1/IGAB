import { useRef, useState } from 'react'
import { useReportStore } from '../../../stores/reportStore'
import { usePlanVsRealityReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { abbreviateValue } from './seasonalityScale'
import { monthWindow } from '../../../utils/dateWindow'
import { MetricCard } from '../MetricCard'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import type { PlanRealityCell } from '../../../types'
import './PlanVsRealityReport.css'

interface Props { budgetId: string }

/** A month is "active" when the plan or reality was non-zero — same rule the
 * backend uses for months_active/months_over. */
function isActive(cell: PlanRealityCell): boolean {
  return Number(cell.assigned) !== 0 || Number(cell.spent) !== 0
}

function cellLabel(variance: number): string {
  if (variance < 0) return `−${abbreviateValue(-variance)}`
  if (variance > 0) return `+${abbreviateValue(variance)}`
  return '0'
}

/** Overspend tint scaled by how bad the month was relative to the worst
 * overspend on screen — color only where there is genuine state. */
function overspendStyle(variance: number, maxOver: number): React.CSSProperties {
  if (variance >= 0) return {}
  const pct = Math.round(Math.min(1, -variance / maxOver) * 30) + 8
  return { background: `color-mix(in srgb, var(--chart-negative) ${pct}%, transparent)` }
}

export function PlanVsRealityReport({ budgetId }: Props) {
  const { formatMoney } = useFormatters()
  const setDrillDown = useReportStore((s) => s.setDrillDown)
  const [months, setMonths] = useState(12)
  const [chronicOnly, setChronicOnly] = useState(false)
  const { data, isLoading, isError, error, refetch } = usePlanVsRealityReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  function drillTo(categoryId: string, label: string, startMonth: string, endMonth: string) {
    setDrillDown({
      kind: 'category', label, scope: 'leaf', direction: 'outflow',
      categoryIds: [categoryId],
      startDate: monthWindow(startMonth.slice(0, 7)).start,
      endDate: monthWindow(endMonth.slice(0, 7)).end,
    })
  }

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const allMonths = data?.months ?? []
  let categories = data?.categories ?? []
  if (chronicOnly) categories = categories.filter((c) => c.chronic)

  const maxOver = Math.max(
    ...categories.flatMap((c) => c.monthly.map((m) => -Number(m.variance))),
    1,
  )

  return (
    <div className="report-section">
      <div className="report-section__header">
        <h2 className="report-section__title">Plan vs Reality</h2>
        <ReportInfoButton title="Plan vs Reality">
          <p>Each cell compares what you <strong>assigned</strong> to a category in a month against what you actually <strong>spent</strong> that month. Red cells mean spending exceeded the month's plan; the deeper the red, the bigger the overrun.</p>
          <p>Unlike the envelope view, this deliberately <strong>ignores carryover</strong> — a category coasting on last month's surplus is still over-plan if nothing was assigned this month. It measures planning discipline, not envelope health.</p>
          <p>A category over plan in <strong>3 of the last 6 months</strong> is flagged as chronic — a sign its budget doesn't match how you actually spend. Click a cell to see that month's transactions.</p>
          <ReportScopeNote scope="categories" />
        </ReportInfoButton>
        <p className="report-section__subtitle">Assigned vs spent per month — carryover ignored</p>
        <div className="flex-row ms-auto" style={{ flexWrap: 'wrap' }}>
          {([6, 12, 24] as const).map((m) => (
            <button
              key={m}
              className={`report-btn ${months === m ? 'report-btn--active' : ''}`}
              onClick={() => setMonths(m)}
              type="button"
            >
              {m}mo
            </button>
          ))}
          <label className="report-toggle">
            <input
              type="checkbox"
              checked={chronicOnly}
              onChange={(e) => setChronicOnly(e.target.checked)}
            />
            Chronic only
          </label>
          <ReportExportButton
            reportId="plan-vs-reality"
            getRows={() =>
              // Wide format mirroring the matrix: one row per category, one
              // variance column per month
              categories.map((c) => {
                const row: Record<string, unknown> = {
                  category: c.category_name,
                  group: c.category_group_name,
                }
                for (const cell of c.monthly) {
                  row[cell.month.slice(0, 7)] = Number(cell.variance)
                }
                row.total_assigned = Number(c.total_assigned)
                row.total_spent = Number(c.total_spent)
                row.months_over = c.months_over
                row.chronic = c.chronic
                return row
              })
            }
            captureRef={captureRef}
          />
        </div>
      </div>

      <div ref={captureRef} className="report-capture">
        {data && (
          <div className="report-metrics">
            <MetricCard label="Total Assigned" value={formatMoney(Number(data.total_assigned))} />
            <MetricCard label="Total Spent" value={formatMoney(Number(data.total_spent))} />
            <MetricCard label="Chronically Over" value={String(data.chronic_count)} />
          </div>
        )}

        {categories.length === 0 ? (
          <div className="reports-empty">
            {chronicOnly
              ? 'No chronically over-budget categories — the plan is holding.'
              : 'No budget or spending data for this period.'}
          </div>
        ) : (
          <div className="plan-reality__scroll">
            <table className="plan-reality__table">
              <caption className="sr-only">Budget variance by category and month</caption>
              <thead>
                <tr>
                  <th scope="col" className="plan-reality__cat-header">Category</th>
                  {allMonths.map((m) => (
                    <th scope="col" key={m} className="plan-reality__month-header">
                      {m.slice(0, 7)}
                    </th>
                  ))}
                  <th scope="col" className="plan-reality__over-header">Over</th>
                </tr>
              </thead>
              <tbody>
                {categories.map((cat) => (
                  <tr key={cat.category_id}>
                    <td className="plan-reality__cat-cell">
                      <button
                        className="plan-reality__cat-btn"
                        type="button"
                        title={`${cat.category_name} — all months`}
                        onClick={() =>
                          allMonths.length > 0 &&
                          drillTo(cat.category_id, cat.category_name, allMonths[0], allMonths[allMonths.length - 1])
                        }
                      >
                        <span className="plan-reality__cat-name">{cat.category_name}</span>
                        <span className="plan-reality__cat-group">{cat.category_group_name}</span>
                      </button>
                      {cat.chronic && <span className="plan-reality__badge">Chronic</span>}
                    </td>
                    {cat.monthly.map((cell) => {
                      const v = Number(cell.variance)
                      const active = isActive(cell)
                      const ym = cell.month.slice(0, 7)
                      return (
                        <td
                          key={cell.month}
                          className={[
                            'plan-reality__cell',
                            active ? 'plan-reality__cell--clickable' : '',
                            active && v < 0 ? 'plan-reality__cell--over' : '',
                            active && v >= 0 ? 'plan-reality__cell--under' : '',
                          ].join(' ')}
                          style={active ? overspendStyle(v, maxOver) : undefined}
                          title={`${cat.category_name} · ${ym} — assigned ${formatMoney(Number(cell.assigned))}, spent ${formatMoney(Number(cell.spent))}`}
                          onClick={
                            active
                              ? () => drillTo(cat.category_id, `${cat.category_name} · ${ym}`, cell.month, cell.month)
                              : undefined
                          }
                        >
                          {active ? cellLabel(v) : ''}
                        </td>
                      )
                    })}
                    <td className="plan-reality__over-count">
                      {cat.months_over > 0 ? `${cat.months_over}/${cat.months_active}` : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
