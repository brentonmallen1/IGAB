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
  balanceLabel,
  coveredAnything,
  envelopeBreakdown,
  exportRows,
  monthOverspent,
  overspendStyle,
  overspentLabel,
  planVsSpentHeadline,
  worstOverspend,
  worstTotalOverspend,
} from './planVsSpentCells'
import { Tooltip } from '../../common/Tooltip/Tooltip'
import { PlanVsSpentHeadRow } from './PlanVsSpentHead'
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
import { ReportHeader } from '../ReportHeader'

interface Props {
  budgetId: string
}

/**
 * Plan vs Spent: what each envelope had, spent and had left, month by month,
 * carryover counted — each cell is the budget page's Available at the month's
 * end, red only where the envelope went negative. The bottom row is what
 * Ready to Assign covered each month; the right-hand columns add each
 * category up across the complete months. Every figure is served (backend
 * `services/plan_vs_spent.py`); nothing is summed on this side.
 */
export function PlanVsSpentReport({ budgetId }: Props) {
  const { formatMoney, formatMonthShort, privacyMode } = useFormatters()
  const setDrillDown = useReportStore((s) => s.setDrillDown)
  const months = useReportMonths()
  // Categories, tags and a saved filter, as the filter bar offers them here.
  const reportScope = useReportScope()
  const [chronicOnly, setChronicOnly] = useState(false)
  const [overFirst, setOverFirst] = useState(false)
  const { data, isLoading, isError, error, refetch } = usePlanVsSpentReport(
    budgetId,
    months,
    reportScope
  )
  const captureRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const stripRef = useRef<HTMLDivElement>(null)

  // Open on the newest month. The matrix runs oldest to newest, and on a
  // phone only two or three months fit, so it opened on last year and the
  // month a reader came to check was a long sideways scroll away.
  useLayoutEffect(() => {
    const el = scrollRef.current
    if (!el) return
    el.scrollLeft = el.scrollWidth
    alignScroll(el, stripRef.current)
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
  if (overFirst) categories = [...categories].sort((a, b) => b.total.overspent - a.total.overspent)

  const maxOver = worstOverspend(categories)
  const maxTotalOver = worstTotalOverspend(categories)
  const headline = data ? planVsSpentHeadline(data) : null
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
      <ReportHeader>
        <h2 className="report-section__title">Plan vs Spent</h2>
        <ReportInfoButton title="Plan vs Spent">
          <p>
            Each cell is what one envelope had <strong>left</strong> at the end of a month — the
            budget page&apos;s Available. It started the month with what the month before left, then
            what you assigned and moved in, less what moved out (a transfer to a brokerage, a loan
            payment), less what you <strong>spent</strong>, net of refunds. Spending down a balance
            you funded earlier is the plan working, not overspending.
          </p>
          <p>
            Red means the envelope went negative by at least $1 and 1% of what it had — Ready to
            Assign had to cover it, and the next month starts from zero. The deeper the red, the
            more it covered. The <strong>bottom row</strong> adds up what was covered each month;
            the <strong>right-hand columns</strong> add each category up across the complete months.
          </p>
          <p>
            <span className="plan-spent__dot" aria-hidden="true" /> Negative in{' '}
            <strong>3 of the last 6 months</strong> is chronic.
          </p>
          <p>
            Every total, the chronic flag and the Over column count complete months only. The month
            in progress is the last month column, marked <em>so far</em>: its spending is still
            arriving.
          </p>
          <ReportScopeNote report="plan-vs-spent" />
        </ReportInfoButton>
        <p className="report-section__subtitle">
          What each envelope had, spent and left — carryover included
        </p>
        <div className="flex-row ms-auto" style={{ flexWrap: 'wrap' }}>
          <ReportRangeSelect />
          <Tooltip content="Show only envelopes that went negative in 3 of the last 6 months">
            <label className="report-toggle">
              <input
                type="checkbox"
                checked={chronicOnly}
                onChange={(e) => setChronicOnly(e.target.checked)}
              />
              Chronic only
            </label>
          </Tooltip>
          <Tooltip content="Put the envelopes Ready to Assign covered the most for first">
            <button
              className={`report-btn ${overFirst ? 'report-btn--active' : ''}`}
              onClick={() => setOverFirst((v) => !v)}
              type="button"
              aria-pressed={overFirst}
            >
              Sort by overspent
            </button>
          </Tooltip>
          <ReportExportButton
            reportId="plan-vs-spent"
            getRows={() => exportRows(categories)}
            captureRef={captureRef}
          />
        </div>
      </ReportHeader>

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
        {data && (
          <MetricRow>
            <MetricCard
              label="Funded"
              value={formatMoney(data.total_funded)}
              sub={windowName ? `carried in + assigned, ${windowName}` : 'carried in + assigned'}
            />
            <MetricCard label="Spent" value={formatMoney(data.total_spent)} sub="net of refunds" />
            <MetricCard
              label="Overspent"
              value={formatMoney(data.total_overspent)}
              sub="covered by Ready to Assign"
              warning={coveredAnything(data.total_overspent)}
            />
            <MetricCard
              label="Left"
              value={formatMoney(data.total_left)}
              sub="in these envelopes"
            />
          </MetricRow>
        )}
        {categories.length > 0 && (
          <p className="plan-spent__legend">
            <span className="plan-spent__dot" aria-hidden="true" /> Chronic: went negative in 3 of
            the last 6 months
          </p>
        )}

        {categories.length === 0 ? (
          <div className="reports-empty">
            {chronicOnly
              ? 'No chronically over-budget categories — the plan is holding.'
              : 'No budget or spending data for this period.'}
          </div>
        ) : (
          <>
            {/* The visible column header: pins under the report header while
              the page scrolls, and follows the table sideways. A copy of the
              table's own header row, so hidden from assistive tech. */}
            <div
              className="plan-spent__head-strip"
              ref={stripRef}
              aria-hidden="true"
              onScroll={() => alignScroll(stripRef.current, scrollRef.current)}
            >
              <table className="plan-spent__table">
                <thead>
                  <PlanVsSpentHeadRow
                    months={allMonths}
                    monthName={monthName}
                    isRunning={isRunning}
                  />
                </thead>
              </table>
            </div>
            <div
              className="plan-spent__scroll"
              ref={scrollRef}
              onScroll={() => alignScroll(scrollRef.current, stripRef.current)}
            >
              <table className="plan-spent__table">
                <caption className="sr-only">
                  What each envelope had left by month, with totals
                </caption>
                <thead className="plan-spent__head--collapsed">
                  <PlanVsSpentHeadRow
                    months={allMonths}
                    monthName={monthName}
                    isRunning={isRunning}
                    collapsed
                  />
                </thead>
                <tbody>
                  {categories.map((cat) => (
                    <tr key={cat.category_id}>
                      <th scope="row" className="plan-spent__name">
                        <button
                          className="plan-spent__name-btn"
                          type="button"
                          title={`${cat.category_name} — ${windowLabel}`}
                          onClick={() => drillCategoryTotal(cat)}
                        >
                          {cat.chronic && (
                            <span className="plan-spent__dot" data-testid="chronic-dot">
                              <span className="sr-only">Chronic: </span>
                            </span>
                          )}
                          <span className="plan-spent__name-text">
                            <span className="plan-spent__name-cat">{cat.category_name}</span>
                            <span className="plan-spent__name-group">
                              {cat.category_group_name}
                            </span>
                          </span>
                        </button>
                      </th>
                      {cat.monthly.map((cell) => {
                        const running = isRunning(cell.month)
                        const ym = monthName(cell.month)
                        const short = cell.over ? ` — ${formatMoney(cell.overspent)} short` : ''
                        return (
                          <td
                            key={cell.month}
                            className={[
                              'plan-spent__cell',
                              cell.active ? 'plan-spent__cell--clickable' : '',
                              cell.active && cell.over ? 'plan-spent__cell--over' : '',
                              running ? 'plan-spent__cell--running' : '',
                            ].join(' ')}
                            style={cell.active ? overspendStyle(cell, maxOver) : undefined}
                            title={
                              cell.active
                                ? `${cat.category_name} · ${ym}${short} — ${envelopeBreakdown(cell, formatMoney)}${cell.estimated ? ' (estimated: before the budget page can say)' : ''}`
                                : undefined
                            }
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
                            {cell.active ? balanceLabel(cell.left, privacyMode) : ''}
                          </td>
                        )
                      })}
                      <td className="plan-spent__tot plan-spent__tot--months">
                        {cat.months_over > 0 ? `${cat.months_over}/${cat.months_active}` : ''}
                      </td>
                      <td className="plan-spent__tot plan-spent__tot--funded">
                        {formatMoney(cat.total.funded)}
                      </td>
                      <td
                        className="plan-spent__tot plan-spent__tot--spent plan-spent__cell--clickable"
                        onClick={() => drillCategoryTotal(cat)}
                      >
                        {formatMoney(cat.total.spent)}
                      </td>
                      <td
                        className={[
                          'plan-spent__tot',
                          'plan-spent__tot--overspent',
                          'plan-spent__cell--clickable',
                          cat.total.over ? 'plan-spent__cell--over' : '',
                        ].join(' ')}
                        style={overspendStyle(cat.total, maxTotalOver)}
                        title={`${cat.category_name} · ${windowLabel} — ${envelopeBreakdown(cat.total, formatMoney, { span: true })}`}
                        onClick={() => drillCategoryTotal(cat)}
                      >
                        {overspentLabel(cat.total.overspent, privacyMode)}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <th scope="row" className="plan-spent__name plan-spent__foot-label">
                      Overspent, all categories
                    </th>
                    {monthTotals.map((t) => (
                      <td
                        key={t.month}
                        className={[
                          'plan-spent__cell',
                          'plan-spent__cell--clickable',
                          monthOverspent(t) ? 'plan-spent__foot--over' : 'plan-spent__foot--quiet',
                          t.partial_month ? 'plan-spent__cell--running' : '',
                        ].join(' ')}
                        title={`${monthName(t.month)} — funded ${formatMoney(t.funded)}, spent ${formatMoney(t.spent)}, left ${formatMoney(t.left)}${t.partial_month ? '' : `; ${t.categories_over} went negative, ${formatMoney(t.overspent)} covered by Ready to Assign`}`}
                        onClick={() =>
                          drillMonth(
                            everyCategory,
                            `All categories · ${monthName(t.month)}`,
                            t.month
                          )
                        }
                      >
                        {overspentLabel(t.overspent, privacyMode)}
                      </td>
                    ))}
                    <td className="plan-spent__tot plan-spent__tot--months" />
                    <td className="plan-spent__tot plan-spent__tot--funded">
                      {data ? formatMoney(data.total_funded) : ''}
                    </td>
                    <td
                      className="plan-spent__tot plan-spent__tot--spent plan-spent__cell--clickable"
                      onClick={() => drillTotal(everyCategory, `All categories · ${windowLabel}`)}
                    >
                      {data ? formatMoney(data.total_spent) : ''}
                    </td>
                    <td
                      className={`plan-spent__tot plan-spent__tot--overspent plan-spent__cell--clickable ${data && coveredAnything(data.total_overspent) ? 'plan-spent__foot--over' : 'plan-spent__foot--quiet'}`}
                      onClick={() => drillTotal(everyCategory, `All categories · ${windowLabel}`)}
                    >
                      {data ? overspentLabel(data.total_overspent, privacyMode) : ''}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

/** Keep the pinned header strip and the table scrolled to the same column,
 *  whichever of the two was swiped. Only when they differ, so the echo from
 *  the other side's scroll event settles instead of looping. */
function alignScroll(from: HTMLElement | null, to: HTMLElement | null) {
  if (from && to && to.scrollLeft !== from.scrollLeft) to.scrollLeft = from.scrollLeft
}
