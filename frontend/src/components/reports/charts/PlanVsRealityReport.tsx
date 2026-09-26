import { useLayoutEffect, useRef, useState } from 'react'
import { useReportMonths, useReportStore } from '../../../stores/reportStore'
import { usePlanVsRealityReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { cellLabel, overspendStyle, planRealityHeadline, worstOverspend } from './planRealityCells'
import { monthWindow } from '../../../utils/dateWindow'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportRangeSelect } from './rangeSelect'
import { reportMonthLabel } from '../../../utils/reportMonths'
import './PlanVsRealityReport.css'

interface Props {
  budgetId: string
}

export function PlanVsRealityReport({ budgetId }: Props) {
  const { formatMoney, formatMonthShort, privacyMode } = useFormatters()
  const setDrillDown = useReportStore((s) => s.setDrillDown)
  const months = useReportMonths()
  const [chronicOnly, setChronicOnly] = useState(false)
  const { data, isLoading, isError, error, refetch } = usePlanVsRealityReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Open on the newest month. The matrix runs oldest to newest, and on a
  // phone only two or three months fit, so it opened on last year and the
  // month a reader came to check was a long sideways scroll away.
  useLayoutEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollLeft = el.scrollWidth
  }, [data, chronicOnly])

  function drillTo(categoryId: string, label: string, startMonth: string, endMonth: string) {
    setDrillDown({
      kind: 'category',
      label,
      scope: 'leaf',
      direction: 'outflow',
      categoryIds: [categoryId],
      startDate: monthWindow(startMonth.slice(0, 7)).start,
      endDate: monthWindow(endMonth.slice(0, 7)).end,
    })
  }

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const allMonths = data?.months ?? []
  // The running month's cells are month-to-date: drawn, marked "so far", and
  // counted in no verdict or total (served — `running_month`).
  const isRunning = (month: string) => month === data?.running_month
  let categories = data?.categories ?? []
  if (chronicOnly) categories = categories.filter((c) => c.chronic)

  const maxOver = worstOverspend(categories)
  const headline = data ? planRealityHeadline(data) : null

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Plan vs Reality</h2>
        <ReportInfoButton title="Plan vs Reality">
          <p>
            Each cell compares a category&apos;s <strong>plan</strong> for the month — what you
            assigned, plus any money moved into the envelope, like a transfer from savings — against
            what you <strong>spent</strong>, net of refunds. Red cells went over plan by at least $1
            and 1% of it; the deeper the red, the bigger the overrun.
          </p>
          <p>
            It deliberately <strong>ignores carryover</strong>: a category living on last
            month&apos;s surplus is still over plan if nothing was planned this month.
          </p>
          <p>
            Over plan in <strong>3 of the last 6 months</strong> is chronic. Sinking funds
            (Long-term expense) never are — paying the bill they saved for is the plan working.
          </p>
          <p>
            The totals, the chronic flag and the Over column count complete months only. The month
            in progress is the last column, marked <em>so far</em>: its plan is in, its spending is
            still arriving.
          </p>
          <ReportScopeNote report="plan-reality" />
        </ReportInfoButton>
        <p className="report-section__subtitle">Plan vs spent per month — carryover ignored</p>
        <div className="flex-row ms-auto" style={{ flexWrap: 'wrap' }}>
          <ReportRangeSelect />
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
                  row[cell.month.slice(0, 7)] = cell.variance
                }
                row.total_assigned = c.total_assigned
                row.total_moved_in = c.total_moved_in
                row.total_spent = c.total_spent
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
        {headline && (
          <MetricRow>
            <MetricCard
              label="Chronic"
              value={String(headline.chronic)}
              sub="over in 3 of the last 6 months"
              warning={headline.chronic > 0}
            />
            <MetricCard
              label="Over last month"
              value={headline.lastMonth ? String(headline.lastMonth.over) : '—'}
              sub={
                headline.lastMonth ? `in ${formatMonthShort(headline.lastMonth.month)}` : undefined
              }
            />
            <MetricCard
              label="Worst"
              value={headline.worst?.name ?? 'None'}
              sub={
                headline.worst
                  ? `over in ${headline.worst.monthsOver} of ${headline.worst.monthsActive} months`
                  : 'nothing went over plan'
              }
            />
          </MetricRow>
        )}

        {categories.length === 0 ? (
          <div className="reports-empty">
            {chronicOnly
              ? 'No chronically over-budget categories — the plan is holding.'
              : 'No budget or spending data for this period.'}
          </div>
        ) : (
          <div className="plan-reality__scroll" ref={scrollRef}>
            <table className="plan-reality__table">
              <caption className="sr-only">Plan vs spent by category and month</caption>
              <thead>
                <tr>
                  <th scope="col" className="plan-reality__cat-header">
                    Category
                  </th>
                  {allMonths.map((m) => (
                    <th
                      scope="col"
                      key={m}
                      className={`plan-reality__month-header${isRunning(m) ? ' plan-reality__month-header--running' : ''}`}
                    >
                      {reportMonthLabel(m, isRunning(m), formatMonthShort)}
                    </th>
                  ))}
                  <th scope="col" className="plan-reality__over-header">
                    Over
                  </th>
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
                          drillTo(
                            cat.category_id,
                            cat.category_name,
                            allMonths[0],
                            allMonths[allMonths.length - 1]
                          )
                        }
                      >
                        <span className="plan-reality__cat-name">{cat.category_name}</span>
                        <span className="plan-reality__cat-group">{cat.category_group_name}</span>
                      </button>
                      {cat.chronic && <span className="plan-reality__badge">Chronic</span>}
                      {cat.sinking_fund && cat.months_over > 0 && (
                        <span
                          className="plan-reality__badge plan-reality__badge--quiet"
                          title="Long-term expense: paying the bill it saved for is never chronic"
                        >
                          Sinking fund
                        </span>
                      )}
                    </td>
                    {cat.monthly.map((cell) => {
                      const running = isRunning(cell.month)
                      const ym = reportMonthLabel(cell.month, running, formatMonthShort)
                      const planned =
                        cell.moved_in !== 0
                          ? `planned ${formatMoney(cell.plan)} (assigned ${formatMoney(cell.assigned)} + moved in ${formatMoney(cell.moved_in)})`
                          : `planned ${formatMoney(cell.plan)}`
                      return (
                        <td
                          key={cell.month}
                          className={[
                            'plan-reality__cell',
                            cell.active ? 'plan-reality__cell--clickable' : '',
                            cell.active && cell.over ? 'plan-reality__cell--over' : '',
                            // The running month is neither over nor under yet.
                            cell.active && !cell.over && !running
                              ? 'plan-reality__cell--under'
                              : '',
                            running ? 'plan-reality__cell--running' : '',
                          ].join(' ')}
                          style={cell.active ? overspendStyle(cell, maxOver) : undefined}
                          title={`${cat.category_name} · ${ym} — ${planned}, spent ${formatMoney(cell.spent)}`}
                          onClick={
                            cell.active
                              ? () =>
                                  drillTo(
                                    cat.category_id,
                                    `${cat.category_name} · ${ym}`,
                                    cell.month,
                                    cell.month
                                  )
                              : undefined
                          }
                        >
                          {cell.active ? cellLabel(cell.variance, privacyMode) : ''}
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
