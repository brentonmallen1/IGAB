import { useRef, useState } from 'react'
import {
  Bar,
  Cell,
  ComposedChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  expensesDrill,
  incomeDrill,
  useReportMonths,
  useReportStore,
} from '../../../stores/reportStore'
import { useIncomeExpenseReport } from '../../../api/reports'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import { ReportErrorState } from '../ReportErrorState'
import { monthWindow } from '../../../utils/dateWindow'
import { monthRange, reportMonthLabel, RUNNING_MONTH_OPACITY } from '../../../utils/reportMonths'
import { DEBT_PAYMENTS, SAVED } from '../../../utils/flowLabels'
import { ChartTooltip } from './ChartTooltip'
import { ChartLegend } from './ChartLegend'
import { FLOW_COLORS } from './chartColors'
import { MIXED_SIGN_STACK } from './mixedSignStack'
import { windowTotals } from './incomeExpenseView'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportRangeSelect } from './rangeSelect'
import { SAVED_DEFINITION } from '../savingsRateBreakdown'
import './IncomeExpenseChart.css'

interface Props {
  budgetId: string
}

/** The chart's series, by the name the legend, tooltip and table say. */
const SERIES = {
  income: 'Income',
  expenses: 'Expenses',
  saved: SAVED,
  debt: DEBT_PAYMENTS,
  net: 'Net',
} as const

/** How far a series fades while the legend highlights another. */
const DIMMED = 0.25

export function IncomeExpenseReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(340)
  const { formatMoney, formatMonthShort } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const setDrillDown = useReportStore((s) => s.setDrillDown)
  const months = useReportMonths()
  const [highlight, setHighlight] = useState<string | null>(null)
  const { data, isLoading, isError, error, refetch } = useIncomeExpenseReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  /** The rows behind one month's bar. Both figures net — refunds in
   *  Expenses, clawbacks in Income — so each list carries both directions
   *  and totals the bar that opened it. */
  function drillTo(month: string, figure: 'income' | 'expenses') {
    if (!data) return
    const window = monthWindow(month)
    const range = { startDate: window.start, endDate: window.end }
    const label = formatMonthShort(month)
    setDrillDown(
      figure === 'income'
        ? incomeDrill(`Income · ${label}`, range)
        : expensesDrill(`Expenses · ${label}`, range, data.expense_classes)
    )
  }

  const monthBarClick = (figure: 'income' | 'expenses') => (data: unknown) => {
    const d = data as { iso?: string; payload?: { iso?: string } }
    const month = d.iso ?? d.payload?.iso
    if (month) drillTo(month, figure)
  }

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const rows = data?.months ?? []
  const dim = (name: string) => (highlight && highlight !== name ? DIMMED : 1)
  const monthLabel = (m: { month: string; partial_month: boolean }) =>
    reportMonthLabel(m.month, m.partial_month, formatMonthShort)
  // The running month is drawn — lighter, and "so far" — so its partial
  // figures never read as a finished month beside the others.
  const chartData = rows.map((m) => ({
    iso: m.month,
    month: monthLabel(m),
    partial: m.partial_month,
    [SERIES.income]: m.income,
    [SERIES.expenses]: m.expenses,
    // Saved and Debt payments stack as one bar of money kept, each its own
    // segment. It was one bar called "Saved" that added debt payments, while
    // the ⓘ under it defined Saved without them and the Savings Rate tab a
    // click away drew Saved without them too: one word, two figures.
    [SERIES.saved]: m.savings,
    [SERIES.debt]: m.debt_principal,
    // No line point for the running month: a line joins it to the finished
    // months as if it were one. Its bars say "so far"; the table has its net.
    [SERIES.net]: m.partial_month ? null : m.net,
  }))
  const hasDebt = rows.some((m) => m.debt_principal !== 0)
  const bars = [
    { key: SERIES.income, color: FLOW_COLORS.income, drill: 'income' as const },
    { key: SERIES.expenses, color: FLOW_COLORS.spent, drill: 'expenses' as const },
    { key: SERIES.saved, color: FLOW_COLORS.saved, stack: 'kept' },
    ...(hasDebt ? [{ key: SERIES.debt, color: FLOW_COLORS.debtPayments, stack: 'kept' }] : []),
  ]
  const totals = windowTotals(rows)
  const totalsLabel = totals
    ? `Total · ${monthRange(totals.first, totals.last, formatMonthShort)}`
    : null

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Income vs Expenses</h2>
        <ReportInfoButton title="Income vs Expenses">
          <p>
            Monthly <strong>Income</strong> and <strong>Expenses</strong> as bars, what you kept
            beside them, and a Net line drawn over them.
          </p>
          <p>
            <strong>Saved</strong> is money that stayed yours rather than being spent.{' '}
            {SAVED_DEFINITION} <strong>Debt payments</strong> — money paid into a tracked debt —
            stack on it as their own segment. Neither is inside Expenses, because neither is money
            spent.
          </p>
          <p>
            <strong>Net</strong> is how much your budget accounts grew that month: cash, less what
            you owe on cards. It counts only money that left them — money held in an envelope is
            still in them, so it does not lower Net. Below zero means they shrank, which is a
            deficit only if you spent it: moving money into savings or investments lowers Net too.
          </p>
          <p>
            The picker&apos;s months are complete months, and the table&apos;s total adds up those.
            The month in progress is drawn after them, lighter and marked <em>so far</em>: its pay
            and bills are still arriving.
          </p>
          <ReportScopeNote report="income-expense" />
        </ReportInfoButton>
        <div className="flex-row ms-auto">
          <ReportRangeSelect />
          <ReportExportButton
            reportId="income-expense"
            getRows={() =>
              rows.map((m) => ({
                month: m.month.slice(0, 7),
                partial_month: m.partial_month,
                income: m.income,
                expenses: m.expenses,
                savings: m.savings,
                savings_moved: m.savings_moved,
                savings_held: m.savings_held,
                debt_principal: m.debt_principal,
                net: m.net,
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>
      {chartData.length === 0 ? (
        <div className="reports-empty">No data for this period.</div>
      ) : (
        <div ref={captureRef} className="report-capture">
          <ResponsiveContainer width="100%" height={chartHeight}>
            {/* Saved goes below zero in a month that drew money back out of
                savings, and Debt payments stack on it. */}
            <ComposedChart
              data={chartData}
              {...MIXED_SIGN_STACK}
              margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
              <YAxis
                tickFormatter={moneyAxis.tickFormatter}
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                width={moneyAxis.width}
              />
              <Tooltip
                content={<ChartTooltip showTotal={false} formatter={formatMoney} />}
                offset={16}
                isAnimationActive={false}
              />
              {bars.map(({ key, color, stack, drill }) => (
                <Bar
                  key={key}
                  dataKey={key}
                  stackId={stack}
                  fill={color}
                  radius={stack ? undefined : [2, 2, 0, 0]}
                  cursor={drill ? 'pointer' : undefined}
                  onClick={drill ? monthBarClick(drill) : undefined}
                  isAnimationActive={false}
                >
                  {chartData.map((d) => (
                    <Cell
                      key={d.iso}
                      fillOpacity={(d.partial ? RUNNING_MONTH_OPACITY : 1) * dim(key)}
                    />
                  ))}
                </Bar>
              ))}
              <Line
                dataKey={SERIES.net}
                stroke={FLOW_COLORS.line}
                strokeOpacity={dim(SERIES.net)}
                strokeWidth={2}
                dot={{ r: 3 }}
                type="linear"
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
          <ChartLegend
            series={[
              ...bars.map((b) => ({ name: b.key, color: b.color })),
              { name: SERIES.net, color: FLOW_COLORS.line },
            ]}
            active={highlight}
            onHover={setHighlight}
          />
          <div className="income-expense__table">
            <table className="report-table">
              <caption className="sr-only">Income, expenses, saved and net by month</caption>
              <thead>
                <tr>
                  <th scope="col" style={{ textAlign: 'left' }}>
                    Month
                  </th>
                  <th scope="col" style={{ textAlign: 'right' }}>
                    {SERIES.income}
                  </th>
                  <th scope="col" style={{ textAlign: 'right' }}>
                    {SERIES.expenses}
                  </th>
                  <th scope="col" style={{ textAlign: 'right' }}>
                    {SERIES.saved}
                  </th>
                  {hasDebt && (
                    <th scope="col" style={{ textAlign: 'right' }}>
                      {SERIES.debt}
                    </th>
                  )}
                  <th scope="col" style={{ textAlign: 'right' }}>
                    {SERIES.net}
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((m) => {
                  const label = monthLabel(m)
                  return (
                    <tr key={m.month}>
                      <td>{label}</td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          type="button"
                          className="report-table__drill"
                          aria-label={`Income, ${label}: ${formatMoney(m.income)}. Show the rows`}
                          onClick={() => drillTo(m.month, 'income')}
                        >
                          {formatMoney(m.income)}
                        </button>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        {/* Positive is spending, under a column headed
                            Expenses. A month whose refunds exceeded its
                            spending is negative and reads negative: the table
                            used to abs() this, so "we got $40 back" drew as
                            "we spent $40". */}
                        <button
                          type="button"
                          className="report-table__drill"
                          aria-label={`Expenses, ${label}: ${formatMoney(m.expenses)}. Show the rows`}
                          onClick={() => drillTo(m.month, 'expenses')}
                        >
                          {formatMoney(m.expenses)}
                        </button>
                      </td>
                      <td style={{ textAlign: 'right' }}>{formatMoney(m.savings)}</td>
                      {hasDebt && (
                        <td style={{ textAlign: 'right' }}>{formatMoney(m.debt_principal)}</td>
                      )}
                      <td style={{ textAlign: 'right' }}>{formatMoney(m.net)}</td>
                    </tr>
                  )
                })}
              </tbody>
              {totals && (
                <tfoot>
                  <tr className="income-expense__total">
                    <th scope="row" style={{ textAlign: 'left' }}>
                      {totalsLabel}
                    </th>
                    <td style={{ textAlign: 'right' }}>{formatMoney(totals.income)}</td>
                    <td style={{ textAlign: 'right' }}>{formatMoney(totals.expenses)}</td>
                    <td style={{ textAlign: 'right' }}>{formatMoney(totals.savings)}</td>
                    {hasDebt && (
                      <td style={{ textAlign: 'right' }}>{formatMoney(totals.debt_principal)}</td>
                    )}
                    <td style={{ textAlign: 'right' }}>{formatMoney(totals.net)}</td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
