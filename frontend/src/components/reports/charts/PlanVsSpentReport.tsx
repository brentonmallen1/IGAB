import { useLayoutEffect, useRef, useState } from 'react'
import {
  planSpentDrill,
  useReportMonths,
  useReportScope,
  useReportStore,
} from '../../../stores/reportStore'
import { usePlanVsSpentReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { drillScope, type DrillScope } from '../drillScope'
import {
  cellLabel,
  exportRows,
  grainGap,
  monthTotalTone,
  overspendStyle,
  planVsSpentHeadline,
  totalShareLabel,
  varianceHeadline,
  worstOverspend,
  worstTotalOverspend,
} from './planVsSpentCells'
import { planLabel } from './planLabel'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportNotes } from '../ReportNotes'
import { ReportRangeSelect } from './rangeSelect'
import { monthRange, reportMonthLabel } from '../../../utils/reportMonths'
import { monthWindow } from '../../../utils/dateWindow'
import type { PlanVsSpentCategory } from '../../../types'
import './PlanVsSpentReport.css'

interface Props {
  budgetId: string
}

/**
 * Plan vs Spent: each category's plan against what it spent, month by month,
 * with a total per month (the bottom row) and per category (the right-hand
 * columns). It was three reports — Budget vs Actual, Cumulative Variance and
 * Plan vs Reality — over one dataset, and every figure here is still served
 * (backend `services/plan_vs_spent.py`); nothing is summed on this side.
 */
export function PlanVsSpentReport({ budgetId }: Props) {
  const { formatMoney, formatMonthShort, privacyMode } = useFormatters()
  const setDrillDown = useReportStore((s) => s.setDrillDown)
  const months = useReportMonths()
  // Categories, tags and a saved filter, as the filter bar offers them here.
  const reportScope = useReportScope()
  const [chronicOnly, setChronicOnly] = useState(false)
  const [overFirst, setOverFirst] = useState(false)
  const [showRunning, setShowRunning] = useState(false)
  const { data, isLoading, isError, error, refetch } = usePlanVsSpentReport(
    budgetId,
    months,
    reportScope
  )
  const captureRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Open on the newest month. The matrix runs oldest to newest, and on a
  // phone only two or three months fit, so it opened on last year and the
  // month a reader came to check was a long sideways scroll away.
  useLayoutEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollLeft = el.scrollWidth
  }, [data, chronicOnly])

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const allMonths = data?.months ?? []
  const monthTotals = data?.month_totals ?? []
  // The running month's cells are month-to-date: drawn, marked "so far", and
  // counted in no verdict or total (served — `running_month`).
  const isRunning = (month: string) => month === data?.running_month
  const monthName = (m: string) => reportMonthLabel(m, isRunning(m), formatMonthShort)
  let categories = data?.categories ?? []
  if (chronicOnly) categories = categories.filter((c) => c.chronic)
  if (overFirst) categories = [...categories].sort((a, b) => a.total.variance - b.total.variance)

  const maxOver = worstOverspend(categories)
  const maxTotalOver = worstTotalOverspend(categories)
  const headline = data ? planVsSpentHeadline(data) : null
  const variance = data ? varianceHeadline(data.total_variance, formatMoney) : null
  const gap = data ? grainGap(data) : null
  // What the Total column covers: the complete months. Null before the first
  // one closes, when the column is all zeros and opens nothing.
  const totalsWindow =
    data?.totals_start && data.totals_end
      ? { startDate: data.totals_start, endDate: data.totals_end }
      : null
  const lastComplete = monthTotals.filter((m) => !m.partial_month).at(-1)?.month
  const windowName = monthRange(data?.totals_start, lastComplete, formatMonthShort)
  const windowLabel = windowName ?? 'complete months'
  // A month total covers every category the report does, so its drill
  // carries the report's scope rather than any one category.
  const everyCategory: DrillScope = drillScope(reportScope)

  function drillMonth(target: DrillScope, label: string, month: string) {
    // The running month's window ends today, as its figures do.
    const { start, end } = monthWindow(month)
    setDrillDown(planSpentDrill(target, label, { startDate: start, endDate: end }))
  }

  function drillTotal(target: DrillScope, label: string) {
    if (totalsWindow) setDrillDown(planSpentDrill(target, label, totalsWindow))
  }

  function drillCategoryTotal(cat: PlanVsSpentCategory) {
    drillTotal({ categoryIds: [cat.category_id] }, `${cat.category_name} · ${windowLabel}`)
  }

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Plan vs Spent</h2>
        <ReportInfoButton title="Plan vs Spent">
          <p>
            Each cell is one category&apos;s month: its <strong>plan</strong> — what you assigned,
            plus money moved into the envelope (a transfer from savings), less money moved out of it
            (a transfer to a brokerage, a loan payment) — against what you <strong>spent</strong>,
            net of refunds. Red went over plan by at least $1 and 1% of it; the deeper the red, the
            bigger the overrun.
          </p>
          <p>
            The <strong>bottom row</strong> adds each month up across categories, and{' '}
            <em>Running total</em> keeps a tally of it month to month. The{' '}
            <strong>right-hand columns</strong> add each category up across the complete months. The
            two tallies agree unless an envelope had money moved out beyond its month&apos;s plan: a
            month counts that plan as zero, while the category total nets it against the other
            months.
          </p>
          <p>
            Over plan in <strong>3 of the last 6 months</strong> is chronic. Sinking funds
            (Long-term expense) never are — paying the bill they saved for is the plan working.
          </p>
          <p>
            Every total, the chronic flag and the Over column count complete months only. The month
            in progress is the last month column, marked <em>so far</em>: its plan is in, its
            spending is still arriving.
          </p>
          <ReportScopeNote report="plan-vs-spent" />
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
          <label className="report-toggle">
            <input
              type="checkbox"
              checked={showRunning}
              onChange={(e) => setShowRunning(e.target.checked)}
            />
            Running total
          </label>
          <button
            className={`report-btn ${overFirst ? 'report-btn--active' : ''}`}
            onClick={() => setOverFirst((v) => !v)}
            type="button"
            aria-pressed={overFirst}
          >
            Sort by overspent
          </button>
          <ReportExportButton
            reportId="plan-vs-spent"
            getRows={() => exportRows(categories)}
            captureRef={captureRef}
          />
        </div>
      </div>

      {/* A deleted saved filter drops its share of the scope; say so rather
          than let the report read as a quiet period. */}
      <ReportNotes report={data} toggleAvailable={false} />

      <div ref={captureRef} className="report-capture">
        {headline && (
          <p className="plan-spent__headline">
            <span className={headline.chronic > 0 ? 'plan-spent__headline--warn' : undefined}>
              <strong>{headline.chronic}</strong> chronic
            </span>
            {' · '}
            {headline.lastMonth ? (
              <span>
                <strong>{headline.lastMonth.over}</strong> over in{' '}
                {formatMonthShort(headline.lastMonth.month)}
              </span>
            ) : (
              <span>no complete month yet</span>
            )}
            {' · '}
            {headline.mostOver ? (
              <span
                title={`over in ${headline.mostOver.monthsOver} of ${headline.mostOver.monthsActive} months`}
              >
                most over: <strong>{headline.mostOver.name}</strong>
              </span>
            ) : (
              <span>nothing went over plan</span>
            )}
          </p>
        )}
        {data && variance && (
          <MetricRow>
            <MetricCard label="Planned" value={formatMoney(data.total_plan)} sub={windowName} />
            <MetricCard label="Spent" value={formatMoney(data.total_spent)} sub="net of refunds" />
            <MetricCard label={variance.label} value={variance.value} warning={variance.over} />
          </MetricRow>
        )}

        {categories.length === 0 ? (
          <div className="reports-empty">
            {chronicOnly
              ? 'No chronically over-budget categories — the plan is holding.'
              : 'No budget or spending data for this period.'}
          </div>
        ) : (
          <div className="plan-spent__scroll" ref={scrollRef}>
            <table className="plan-spent__table">
              <caption className="sr-only">
                Plan vs spent by category and month, with totals
              </caption>
              <thead>
                <tr>
                  <th scope="col" className="plan-spent__cat-header">
                    Category
                  </th>
                  {allMonths.map((m) => (
                    <th
                      scope="col"
                      key={m}
                      className={`plan-spent__month-header${isRunning(m) ? ' plan-spent__month-header--running' : ''}`}
                    >
                      {monthName(m)}
                    </th>
                  ))}
                  <th scope="col" className="plan-spent__num-header plan-spent__col--first-total">
                    Over
                  </th>
                  <th scope="col" className="plan-spent__num-header plan-spent__col--wide">
                    Planned
                  </th>
                  <th scope="col" className="plan-spent__num-header plan-spent__col--wide">
                    Spent
                  </th>
                  <th scope="col" className="plan-spent__num-header">
                    Total
                  </th>
                </tr>
              </thead>
              <tbody>
                {categories.map((cat) => (
                  <tr key={cat.category_id}>
                    <th scope="row" className="plan-spent__cat-cell">
                      <button
                        className="plan-spent__cat-btn"
                        type="button"
                        title={`${cat.category_name} — ${windowLabel}`}
                        onClick={() => drillCategoryTotal(cat)}
                      >
                        <span className="plan-spent__cat-name">{cat.category_name}</span>
                        <span className="plan-spent__cat-group">{cat.category_group_name}</span>
                      </button>
                      {cat.chronic && <span className="plan-spent__badge">Chronic</span>}
                      {cat.sinking_fund && cat.months_over > 0 && (
                        <span
                          className="plan-spent__badge plan-spent__badge--quiet"
                          title="Long-term expense: paying the bill it saved for is never chronic"
                        >
                          Sinking fund
                        </span>
                      )}
                    </th>
                    {cat.monthly.map((cell) => {
                      const running = isRunning(cell.month)
                      const ym = monthName(cell.month)
                      const planned = `planned ${planLabel(cell, formatMoney)}`
                      return (
                        <td
                          key={cell.month}
                          className={[
                            'plan-spent__cell',
                            cell.active ? 'plan-spent__cell--clickable' : '',
                            cell.active && cell.over ? 'plan-spent__cell--over' : '',
                            // The running month is neither over nor under yet.
                            cell.active && !cell.over && !running ? 'plan-spent__cell--under' : '',
                            running ? 'plan-spent__cell--running' : '',
                          ].join(' ')}
                          style={cell.active ? overspendStyle(cell, maxOver) : undefined}
                          title={`${cat.category_name} · ${ym} — ${planned}, spent ${formatMoney(cell.spent)}`}
                          onClick={
                            cell.active
                              ? () =>
                                  drillMonth(
                                    { categoryIds: [cat.category_id] },
                                    `${cat.category_name} · ${ym}`,
                                    cell.month
                                  )
                              : undefined
                          }
                        >
                          {cell.active ? cellLabel(cell.variance, privacyMode) : ''}
                        </td>
                      )
                    })}
                    <td className="plan-spent__num plan-spent__col--first-total">
                      {cat.months_over > 0 ? `${cat.months_over}/${cat.months_active}` : ''}
                    </td>
                    <td
                      className="plan-spent__num plan-spent__col--wide"
                      title={`planned ${planLabel(cat.total, formatMoney)}`}
                    >
                      {formatMoney(cat.total.plan)}
                    </td>
                    <td
                      className="plan-spent__num plan-spent__col--wide plan-spent__cell--clickable"
                      onClick={() => drillCategoryTotal(cat)}
                    >
                      {formatMoney(cat.total.spent)}
                    </td>
                    <td
                      className={[
                        'plan-spent__cell',
                        'plan-spent__total',
                        'plan-spent__cell--clickable',
                        cat.total.over ? 'plan-spent__cell--over' : 'plan-spent__cell--under',
                      ].join(' ')}
                      style={overspendStyle(cat.total, maxTotalOver)}
                      title={`${cat.category_name} · ${windowLabel} — planned ${planLabel(cat.total, formatMoney)}, spent ${formatMoney(cat.total.spent)}, ${totalShareLabel(cat.total)}`}
                      onClick={() => drillCategoryTotal(cat)}
                    >
                      {cellLabel(cat.total.variance, privacyMode)}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="plan-spent__totals-row">
                  <th scope="row" className="plan-spent__cat-cell plan-spent__foot-label">
                    All categories
                  </th>
                  {monthTotals.map((t) => (
                    <td
                      key={t.month}
                      className={[
                        'plan-spent__cell',
                        'plan-spent__cell--clickable',
                        `plan-spent__month-total--${t.partial_month ? 'running' : monthTotalTone(t)}`,
                        t.partial_month ? 'plan-spent__cell--running' : '',
                      ].join(' ')}
                      title={`${monthName(t.month)} — planned ${formatMoney(t.plan)}, spent ${formatMoney(t.spent)}${t.partial_month ? '' : `, ${t.categories_over} over`}`}
                      onClick={() =>
                        drillMonth(everyCategory, `All categories · ${monthName(t.month)}`, t.month)
                      }
                    >
                      {cellLabel(t.variance, privacyMode)}
                    </td>
                  ))}
                  <td className="plan-spent__num plan-spent__col--first-total" />
                  <td className="plan-spent__num plan-spent__col--wide">
                    {data ? formatMoney(data.total_plan) : ''}
                  </td>
                  <td
                    className="plan-spent__num plan-spent__col--wide plan-spent__cell--clickable"
                    onClick={() => drillTotal(everyCategory, `All categories · ${windowLabel}`)}
                  >
                    {data ? formatMoney(data.total_spent) : ''}
                  </td>
                  <td
                    className={`plan-spent__cell plan-spent__total plan-spent__cell--clickable plan-spent__month-total--${variance?.over ? 'over' : 'under'}`}
                    onClick={() => drillTotal(everyCategory, `All categories · ${windowLabel}`)}
                  >
                    {data ? cellLabel(data.total_variance, privacyMode) : ''}
                  </td>
                </tr>
                {showRunning && (
                  <tr className="plan-spent__running-row">
                    <th scope="row" className="plan-spent__cat-cell plan-spent__foot-label">
                      Running total
                    </th>
                    {monthTotals.map((t) => (
                      <td
                        key={t.month}
                        className="plan-spent__cell plan-spent__cell--under"
                        title={
                          t.cumulative_variance === null
                            ? 'The month in progress is in no running total'
                            : `through ${monthName(t.month)}`
                        }
                      >
                        {t.cumulative_variance === null
                          ? '—'
                          : cellLabel(t.cumulative_variance, privacyMode)}
                      </td>
                    ))}
                    <td className="plan-spent__num plan-spent__col--first-total" />
                    <td className="plan-spent__num plan-spent__col--wide" />
                    <td className="plan-spent__num plan-spent__col--wide" />
                    <td className="plan-spent__num" />
                  </tr>
                )}
              </tfoot>
            </table>
          </div>
        )}
        {gap && categories.length > 0 && (
          <p className="plan-spent__grain-note">
            Month by month the bottom row adds up to {formatMoney(gap.byMonth)}; the Total column
            says {formatMoney(gap.byWindow)}. Money taken back out of an envelope after the month it
            was assigned counts as nothing in the month it left, but the Total nets it against the
            month it came from.
          </p>
        )}
      </div>
    </div>
  )
}
