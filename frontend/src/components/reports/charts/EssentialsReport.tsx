import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useEssentialsReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { MetricCard } from '../MetricCard'
import { ReportInfoButton } from '../ReportInfoButton'
import { ReportErrorState } from '../ReportErrorState'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import './EssentialsReport.css'

interface Props {
  budgetId: string
}

const WINDOWS = [6, 12, 24] as const

/**
 * What a lean month costs, from what the household tagged Essential — and
 * what a reserve of one, three, six or twelve months of it would be.
 *
 * One figure, three readers: the headline here is the Guide's
 * essential-expenses signal (rolling 90 days ÷ 3, the number its
 * emergency-fund target is built from) and the Overview card's. The table
 * averages complete months instead, so a partial current month cannot drag
 * every category down. Nothing self-reported from the Guide appears here.
 */
export function EssentialsReport({ budgetId }: Props) {
  const { formatMoney, formatMonth } = useFormatters()
  const [months, setMonths] = useState<(typeof WINDOWS)[number]>(12)
  const { data, isLoading, isError, error, refetch } = useEssentialsReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />
  if (!data) return <div className="reports-empty">No data available.</div>

  const maxAverage = Math.max(0, ...data.categories.map((c) => c.monthly_average))
  const maxMonth = Math.max(0, ...data.monthly_series.map((m) => m.total))
  const [rangeLow, rangeHigh] = data.roadmap_range

  return (
    <div className="essentials-report">
      <div className="essentials-report__section surface">
        <div className="report-section__header">
          <h2 className="report-section__title">Essentials</h2>
          <ReportInfoButton title="Essentials">
            <p>
              Spending in categories and payees tagged <strong>Essential</strong> — the things you
              could not cut in an emergency. The headline is the last 90 days averaged per month,
              the same figure the Guide’s emergency-fund target uses; the table averages the last{' '}
              {months} complete months.
            </p>
            <p>
              A reserve is that monthly figure times the months you want covered. The roadmap
              suggests {rangeLow}–{rangeHigh} months once expensive debt is gone.
            </p>
          </ReportInfoButton>
          <div className="flex-row ms-auto">
            <div className="essentials-report__windows" role="group" aria-label="Months of history">
              {WINDOWS.map((n) => (
                <button
                  key={n}
                  type="button"
                  className={`report-btn ${n === months ? 'report-btn--active' : ''}`}
                  aria-pressed={n === months}
                  onClick={() => setMonths(n)}
                >
                  {n}mo
                </button>
              ))}
            </div>
            <ReportExportButton
              reportId="essentials"
              getRows={() => [
                { metric: 'essentials_90d', value: data.essentials_90d },
                ...data.reserve.map((r) => ({
                  metric: `reserve_${r.months}mo`,
                  value: r.amount,
                })),
                ...data.categories.map((c) => ({
                  metric: `avg_${c.name}`,
                  value: c.monthly_average,
                })),
              ]}
              captureRef={captureRef}
              window={{ start: data.window_start, end: data.window_end }}
            />
          </div>
        </div>

        {!data.tagged ? (
          <div className="essentials-report__empty">
            <p>
              Nothing is tagged <strong>Essential</strong> yet. Tag a category in its inspector on
              the Budget page, or a payee on the Payees page, and this report — the Overview card
              and the Guide’s emergency-fund target with it — narrows to what a lean month actually
              costs.
            </p>
          </div>
        ) : (
          <div ref={captureRef}>
            <div className="overview-report__metrics-grid">
              <MetricCard
                label="Essentials / month"
                value={formatMoney(data.essentials_90d)}
                sub="90-day average"
              />
              {data.reserve.map((r) => {
                const inRange = r.months >= rangeLow && r.months <= rangeHigh
                return (
                  <MetricCard
                    key={r.months}
                    label={`${r.months}-month reserve`}
                    value={formatMoney(r.amount)}
                    sub={inRange ? 'Roadmap range' : r.months === 1 ? 'Starter buffer' : undefined}
                    accent={inRange}
                  />
                )
              })}
            </div>
            <p className="essentials-report__note">
              Save targets, not balances — what you have set aside lives on the{' '}
              <Link to="/guide">roadmap</Link>.
            </p>

            <div className="essentials-report__table-wrap">
              <table className="essentials-report__table">
                <thead>
                  <tr>
                    <th scope="col">Category</th>
                    <th scope="col" className="essentials-report__num">
                      Avg / month
                    </th>
                    <th scope="col" className="essentials-report__bar-col">
                      <span className="visually-hidden">Share</span>
                    </th>
                    <th scope="col" className="essentials-report__num">
                      Total
                    </th>
                    <th scope="col" className="essentials-report__num">
                      Months
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.categories.map((c) => {
                    const avg = c.monthly_average
                    const width = maxAverage > 0 ? (avg / maxAverage) * 100 : 0
                    return (
                      <tr key={c.category_id ?? 'uncategorized'}>
                        <td>
                          <span className="essentials-report__name">{c.name}</span>
                          {c.group_name && (
                            <span className="essentials-report__group">{c.group_name}</span>
                          )}
                        </td>
                        <td className="essentials-report__num tabular">{formatMoney(avg)}</td>
                        <td className="essentials-report__bar-col">
                          <div
                            className="essentials-report__bar"
                            title={`${c.name}: ${formatMoney(avg)} per month over ${months} months`}
                          >
                            <div
                              className="essentials-report__bar-fill"
                              style={{ width: `${width}%` }}
                            />
                          </div>
                        </td>
                        <td className="essentials-report__num tabular">{formatMoney(c.total)}</td>
                        <td className="essentials-report__num tabular">
                          {c.months_with_spend}/{months}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
                <tfoot>
                  <tr>
                    <th scope="row">All essentials</th>
                    <td className="essentials-report__num tabular">
                      {formatMoney(data.monthly_total_average)}
                    </td>
                    <td />
                    <td className="essentials-report__num tabular">
                      {formatMoney(data.monthly_total_average * months)}
                    </td>
                    <td />
                  </tr>
                </tfoot>
              </table>
            </div>

            <div className="essentials-report__months" aria-label="Essentials by month">
              {data.monthly_series.map((m) => {
                const total = m.total
                const height = maxMonth > 0 ? (total / maxMonth) * 100 : 0
                return (
                  <div
                    key={m.month}
                    className="essentials-report__month"
                    title={`${formatMonth(m.month)}: ${formatMoney(total)}`}
                  >
                    <div className="essentials-report__month-bar">
                      <div
                        className="essentials-report__month-fill"
                        style={{ height: `${height}%` }}
                      />
                    </div>
                    <span className="essentials-report__month-label">
                      {formatMonth(m.month).slice(0, 3)}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
