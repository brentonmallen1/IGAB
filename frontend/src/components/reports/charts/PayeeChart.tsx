import { useRef, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Cell,
} from 'recharts'
import { useReportStore } from '../../../stores/reportStore'
import { usePayeeAnalysisReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { useMoneyAxis } from './useMoneyAxis'
import { ReportErrorState } from '../ReportErrorState'
import { DrillDownTable } from '../DrillDownTable'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { CHART_COLORS, TOOLTIP_STYLE } from './chartColors'
import { ReportInfoButton, ReportScopeNote, SpendingClassNote } from '../ReportInfoButton'
import { LogScaleToggle, logAxisProps } from './logScale'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { truncateLabel } from './chartLabel'

interface Props {
  budgetId: string
}

export function PayeeReport({ budgetId }: Props) {
  const { formatMoney } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const { filters, setDrillDown } = useReportStore()
  const payeeIds = filters.payeeIds.length > 0 ? filters.payeeIds : undefined
  const acctIds = filters.accountIds.length > 0 ? filters.accountIds : undefined
  const { data, isLoading, isError, error, refetch } = usePayeeAnalysisReport(
    budgetId,
    filters.startDate,
    filters.endDate,
    25,
    payeeIds,
    acctIds
  )
  const [view, setView] = useState<'top' | 'recurring'>('top')
  const [logScale, setLogScale] = useState(false)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const payees = data?.payees ?? []
  const recurring = payees.filter((p) => p.is_recurring)
  const displayed = view === 'recurring' ? recurring : payees.slice(0, 20)

  const chartData = displayed.map((p) => ({
    name: truncateLabel(p.payee_name, 18),
    fullName: p.payee_name,
    payeeId: p.payee_id,
    Amount: p.total,
    Visits: p.count,
    isRecurring: p.is_recurring,
  }))

  function drillTo(payeeId: string, name: string) {
    setDrillDown({
      kind: 'payee',
      label: name,
      scope: 'parent',
      direction: 'outflow',
      payeeIds: [payeeId],
      startDate: filters.startDate,
      endDate: filters.endDate,
    })
  }

  const tableRows = displayed.map((p) => ({
    id: p.payee_id,
    name: p.payee_name,
    subName: p.is_recurring ? 'Recurring' : `${p.count} transactions`,
    amount: p.total,
    pct: p.pct,
  }))

  // The server's own figure, over EVERY payee in the window — not a sum of
  // the 25 it ranked. `pct` is a share of this, so a client-side sum of the
  // visible rows disagreed with the percentages beside them.
  const grandTotal = Number(data?.total ?? 0)
  const payeeCount = data?.payee_count ?? payees.length
  const ranked = payees.length

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Payee Analysis</h2>
        <ReportInfoButton title="Payee Analysis">
          <p>
            Ranks your top payees by total spending in the selected period.{' '}
            <strong>Highlighted bars</strong> indicate recurring payees (appeared in 3+ different
            months).
          </p>
          <p>
            The chart and table show the <strong>25 largest</strong> payees; the Total Payees card
            and Total Spent cover <strong>every</strong> payee in the period, so the rows below can
            add up to less than the total. Each row&apos;s percentage is a share of that whole.
          </p>
          <p>
            Use <em>Recurring</em> mode to focus only on fixed or habitual expenses — subscriptions,
            utilities, regular vendors. These are the easiest targets for cutting predictable
            spending.
          </p>
          <ReportScopeNote scope="on-budget-filterable" />
          <SpendingClassNote />
        </ReportInfoButton>
        <p className="report-section__subtitle">
          Top payees by spending. Recurring = appeared in 3+ months.
        </p>
        <div className="flex-row ms-auto">
          <button
            className={`report-btn ${view === 'top' ? 'report-btn--active' : ''}`}
            onClick={() => setView('top')}
            type="button"
          >
            Top 20
          </button>
          <button
            className={`report-btn ${view === 'recurring' ? 'report-btn--active' : ''}`}
            onClick={() => setView('recurring')}
            type="button"
          >
            Recurring ({recurring.length})
          </button>
          <LogScaleToggle enabled={logScale} onToggle={() => setLogScale((v) => !v)} />
          <ReportExportButton
            reportId="payees"
            getRows={() =>
              payees.map((p) => ({
                payee: p.payee_name,
                total: p.total,
                count: p.count,
                pct: p.pct,
                recurring: p.is_recurring,
              }))
            }
            captureRef={captureRef}
            window={{ start: filters.startDate, end: filters.endDate }}
          />
        </div>
      </div>

      <div ref={captureRef} className="report-capture">
        {payees.length > 0 && (
          <MetricRow>
            {/* The window's payee count, served. This card read
                `payees.length` — the server's ranking cap — so a budget with
                three hundred payees was told it had 25, beside a Total Spent
                that was those 25 rows added up. */}
            <MetricCard
              label="Total Payees"
              value={String(payeeCount)}
              sub={ranked < payeeCount ? `top ${ranked} shown` : undefined}
            />
            <MetricCard
              label="Recurring Payees"
              value={String(recurring.length)}
              sub={ranked < payeeCount ? `of the top ${ranked}` : undefined}
            />
            <MetricCard label="Total Spent" value={formatMoney(grandTotal)} sub="all payees" />
          </MetricRow>
        )}

        {chartData.length === 0 ? (
          <div className="reports-empty">No spending data for this period.</div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={Math.max(300, chartData.length * 34)}>
              <BarChart
                data={chartData}
                layout="vertical"
                margin={{ top: 4, right: 80, left: 4, bottom: 4 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="var(--border-color)"
                  horizontal={false}
                />
                <XAxis
                  type="number"
                  tickFormatter={moneyAxis.tickFormatter}
                  tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                  {...logAxisProps(logScale)}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                  width={140}
                />
                <Tooltip
                  formatter={(v: unknown, name: unknown) =>
                    name === 'Amount' ? [formatMoney(Number(v)), name] : [Number(v), String(name)]
                  }
                  offset={16}
                  isAnimationActive={false}
                  {...TOOLTIP_STYLE}
                />
                <Bar
                  dataKey="Amount"
                  barSize={14}
                  radius={[0, 2, 2, 0]}
                  cursor="pointer"
                  onClick={(data) => {
                    const d = data as {
                      payeeId?: string
                      fullName?: string
                      payload?: { payeeId?: string; fullName?: string }
                    }
                    const id = d.payeeId ?? d.payload?.payeeId
                    const name = d.fullName ?? d.payload?.fullName
                    if (id && name) drillTo(id, name)
                  }}
                >
                  {chartData.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={entry.isRecurring ? CHART_COLORS[1] : CHART_COLORS[0]}
                      fillOpacity={0.85}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div className="chart-key">
              <span className="chart-key__item">
                <span className="chart-key__swatch" style={{ background: CHART_COLORS[0] }} />
                One-off
              </span>
              <span className="chart-key__item">
                <span className="chart-key__swatch" style={{ background: CHART_COLORS[1] }} />
                Recurring (3+ months)
              </span>
            </div>
            <DrillDownTable
              rows={tableRows}
              wider={{ total: grandTotal, count: payeeCount, label: 'payees' }}
              amountLabel="Spent"
              onRowClick={(row) => drillTo(row.id, row.name)}
            />
          </>
        )}
      </div>
    </div>
  )
}
