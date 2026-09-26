import { useRef, useState } from 'react'
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useSavingsRateReport } from '../../../api/reports'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import { ReportErrorState } from '../ReportErrorState'
import { ChartTooltip } from './ChartTooltip'
import { ChartLegend } from './ChartLegend'
import { FLOW_COLORS } from './chartColors'
import { MIXED_SIGN_STACK } from './mixedSignStack'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportRangeSelect } from './rangeSelect'
import { SavingsRateDialog } from '../SavingsRateDialog'
import { INVISIBLE_SAVING, SAVED_DEFINITION } from '../savingsRateBreakdown'
import { keptFigure, pct, RATE_SERIES, ratePercent, rateTooltip } from './savingsRateView'
import { useReportMonths } from '../../../stores/reportStore'
import {
  completeMonthRows,
  monthRange,
  reportMonthLabel,
  RUNNING_MONTH_OPACITY,
} from '../../../utils/reportMonths'
import { DEBT_PAYMENTS, SAVED, SAVED_WITH_DEBT, savingsRateLabel } from '../../../utils/flowLabels'
import { GuideTabLink } from '../../guide/GuideTabLink'

interface Props {
  budgetId: string
}

/** The money panel's series names — what the legend and the tooltip say. */
const BAR = { income: 'Income', saved: SAVED, debt: DEBT_PAYMENTS } as const

/** The rate panel's height. It holds one line, read against its own zero. */
const RATE_PANEL_HEIGHT = 150

/** How far a series fades while the legend highlights another. */
const DIMMED = 0.25

export function SavingsRateReport({ budgetId }: Props) {
  const moneyHeight = useChartHeight(260)
  const { formatMoney, formatMonthShort } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const months = useReportMonths()
  // Off by default, as on the Overview: the rate everyone quotes is saved ÷
  // income. The tab opened with debt payments counted while the Overview's
  // card — and the server's comment on it — said the plain rate was the
  // default, so one August read 4.9% here and 0.0% there.
  const [withDebt, setWithDebt] = useState(false)
  const [contributorsOpen, setContributorsOpen] = useState(false)
  const [highlight, setHighlight] = useState<string | null>(null)
  const { data, isLoading, isError, error, refetch } = useSavingsRateReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const rows = data?.months ?? []
  const summary = data?.summary
  const rateKey = withDebt ? 'savings_rate_with_debt' : 'savings_rate'
  const rateLabel = savingsRateLabel(withDebt)
  const dim = (name: string) => (highlight && highlight !== name ? DIMMED : 1)

  // The bars are the rate's two terms — Income, what it divides by, and what
  // was kept of it — so a month's bars show the fraction its point on the line
  // states. They used to be Saved, Debt Paid and Spent: Spent is in no
  // savings rate, and Income, which is in every one, was not drawn at all.
  const chartData = rows.map((m) => ({
    iso: m.month,
    date: reportMonthLabel(m.month, m.partial_month, formatMonthShort),
    partial: m.partial_month,
    [BAR.income]: Number(m.income),
    [BAR.saved]: Number(m.savings),
    // Only while the rate counts them: a bar the rate leaves out would make
    // the stack say one fraction and the line another.
    ...(withDebt ? { [BAR.debt]: Number(m.debt_principal) } : {}),
    // null leaves a gap in the line rather than dropping it to zero, which
    // would read as "saved nothing" in a month with no income at all. The
    // running month has no rate either: its bills are in and its pay may not
    // be, so a mid-month rate is the calendar talking — its bars say so far.
    [RATE_SERIES]: m[rateKey] === null || m.partial_month ? null : ratePercent(m[rateKey]),
  }))
  const bars: { key: string; color: string; stack?: string }[] = [
    { key: BAR.income, color: FLOW_COLORS.income },
    { key: BAR.saved, color: FLOW_COLORS.saved, stack: 'kept' },
    ...(withDebt ? [{ key: BAR.debt, color: FLOW_COLORS.debtPayments, stack: 'kept' }] : []),
  ]
  // The summary is the complete months alone, served; the card says which.
  const complete = completeMonthRows(rows)
  const covered = monthRange(complete[0]?.month, complete.at(-1)?.month, formatMonthShort)

  const hasAnything = rows.some(
    (m) => Number(m.income) !== 0 || Number(m.savings) !== 0 || Number(m.debt_principal) !== 0
  )

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Savings Rate</h2>
        <ReportInfoButton title="Savings Rate">
          <p>How much of what came in you kept, month by month.</p>
          <p>
            <strong>Savings rate</strong> = saved ÷ income. {SAVED_DEFINITION} Assigning to an
            envelope that counts while it’s in the budget counts as saved, spending from it lowers
            saved, and moving its money on to a savings account nets to zero.
          </p>
          <p>
            <em>Include debt payments</em> adds what you paid into a tracked debt, and the rate is
            then labelled <em>with debt payments</em>. It is off unless you turn it on: a payment
            carries interest and escrow as well as principal, so not all of it is money kept.
          </p>
          <p>
            The top panel is the rate. The bars under it are the two figures it divides: income, and
            what you kept of it.
          </p>
          <p>{INVISIBLE_SAVING}</p>
          <p>
            Growth <em>inside</em> a tracked account — dividends, market movement — is deliberately{' '}
            <strong>not</strong> counted. It changes your net worth, but you didn’t save it, and
            counting it would make this number climb in a good market while you did nothing.
          </p>
          <p>
            Of your tracked accounts, only one that <strong>counts as savings</strong> is saving.
            Selling a car or a house tracked as an asset counts as income, and buying one as
            spending — turn the setting off on the account for things like that.
          </p>
          <p>
            A month with no income shows a gap rather than 0%: having no income recorded isn’t the
            same as saving none of it.
          </p>
          <p>
            The headline covers the picker&apos;s complete months. The month in progress is drawn
            after them, lighter and marked <em>so far</em>, with no rate: until its pay has landed a
            partial month&apos;s rate says more about the calendar than about saving.
          </p>
          <p>
            Open the rate to see where the savings went, which debts were paid and where the income
            came from.
          </p>
          <p>
            <GuideTabLink tab="aside" anchor="savings-modes">
              How Savings envelopes count
            </GuideTabLink>
          </p>
          <ReportScopeNote report="savings-rate" />
        </ReportInfoButton>
        <p className="report-section__subtitle">Share of income kept</p>
        <div className="flex-row ms-auto">
          <ReportRangeSelect />
          <button
            className={`report-btn ${withDebt ? 'report-btn--active' : ''}`}
            aria-pressed={withDebt}
            onClick={() => setWithDebt((v) => !v)}
            type="button"
            title="Count money paid into a tracked debt as kept"
          >
            Include debt payments
          </button>
          <ReportExportButton
            reportId="savings-rate"
            getRows={() =>
              rows.map((m) => ({
                month: m.month,
                partial_month: m.partial_month,
                income: Number(m.income),
                spending: Number(m.spending),
                savings: Number(m.savings),
                savings_moved: Number(m.savings_moved),
                savings_held: Number(m.savings_held),
                debt_principal: Number(m.debt_principal),
                savings_rate: m.savings_rate,
                savings_rate_with_debt: m.savings_rate_with_debt,
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>

      <div ref={captureRef} className="report-capture">
        {summary && (
          <MetricRow>
            <MetricCard
              label={rateLabel}
              value={pct(summary[rateKey])}
              sub={covered ?? undefined}
              details={{
                label: `${rateLabel} ${pct(summary[rateKey])}. Show what contributed`,
                onOpen: () => setContributorsOpen(true),
              }}
            />
            <MetricCard label="Income" value={formatMoney(Number(summary.income))} />
            <MetricCard
              label={withDebt ? SAVED_WITH_DEBT : SAVED}
              value={formatMoney(
                keptFigure(
                  {
                    savings: Number(summary.savings),
                    debt_principal: Number(summary.debt_principal),
                  },
                  withDebt
                )
              )}
            />
            <MetricCard
              label={DEBT_PAYMENTS}
              value={formatMoney(Number(summary.debt_principal))}
              sub={withDebt ? 'in this rate' : 'not in this rate'}
            />
          </MetricRow>
        )}
        {data && contributorsOpen && (
          // The window the summary covers, as served — so the dialog's totals
          // are this card's, not a range rebuilt from `months`.
          <SavingsRateDialog
            budgetId={budgetId}
            startDate={data.start_date}
            endDate={data.end_date}
            rate={data.summary[rateKey]}
            withDebt={withDebt}
            onClose={() => setContributorsOpen(false)}
          />
        )}

        {!hasAnything ? (
          <div className="reports-empty">
            No income or savings recorded yet. Once money comes in and some of it is saved — moved
            to a savings or investment account, or held in a Savings envelope — the rate appears
            here.
          </div>
        ) : (
          <>
            {/* Two panels on one month axis, never two scales on one plot. The
                rate shared a chart with the money bars on a second axis whose
                zero sat a third of the way up the first, so a 0% month drew
                level with $11,000 and a negative rate dipped below bars that
                were positive. Each panel now has one scale and its own zero;
                `syncId` keeps their tooltips on the same month, and the rate
                panel's axis takes the money axis's width so the months line
                up. */}
            <ResponsiveContainer width="100%" height={RATE_PANEL_HEIGHT}>
              <LineChart
                data={chartData}
                syncId="savings-rate"
                margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                {/* A band scale, as the bar panel's is: a line chart's default
                    point scale runs edge to edge, so its points sat off the
                    bars they describe. */}
                <XAxis dataKey="date" hide scale="band" />
                <YAxis
                  tickFormatter={(v) => `${v}%`}
                  tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                  width={moneyAxis.width}
                />
                <ReferenceLine y={0} stroke="var(--text-muted)" />
                <Tooltip
                  content={<ChartTooltip showTotal={false} formatter={rateTooltip} />}
                  offset={16}
                  isAnimationActive={false}
                />
                <Line
                  type="linear"
                  dataKey={RATE_SERIES}
                  name={rateLabel}
                  stroke={FLOW_COLORS.line}
                  strokeOpacity={dim(rateLabel)}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
            <ResponsiveContainer width="100%" height={moneyHeight}>
              {/* Saved goes negative in a month that drew money back out of
                  savings, and Debt payments stack on it. */}
              <ComposedChart
                data={chartData}
                syncId="savings-rate"
                {...MIXED_SIGN_STACK}
                margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
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
                {bars.map(({ key, color, stack }) => (
                  <Bar
                    key={key}
                    dataKey={key}
                    stackId={stack}
                    fill={color}
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
              </ComposedChart>
            </ResponsiveContainer>
            <ChartLegend
              series={[
                { name: rateLabel, color: FLOW_COLORS.line },
                ...bars.map((b) => ({ name: b.key, color: b.color })),
              ]}
              active={highlight}
              onHover={setHighlight}
            />
          </>
        )}
      </div>
    </div>
  )
}
