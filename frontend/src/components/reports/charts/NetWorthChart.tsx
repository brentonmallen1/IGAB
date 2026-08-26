import { useRef, useState } from 'react'
import {
  Area, AreaChart, CartesianGrid, Legend,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useNetWorthReport } from '../../../api/reports'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { ChartTooltip } from './ChartTooltip'
import { MetricCard } from '../MetricCard'
import { COLOR_NEGATIVE, COLOR_NET, COLOR_POSITIVE } from './chartColors'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'

interface Props { budgetId: string }

export function NetWorthReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(340)
  const { formatMoney } = useFormatters()
  const [months, setMonths] = useState(12)
  const { data, isLoading, isError, error, refetch } = useNetWorthReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const points = data?.points ?? []
  const latest = points[points.length - 1]

  const chartData = points.map((p) => ({
    date: p.date.slice(0, 7),
    Assets: Number(p.total_assets),
    Liabilities: Number(p.total_liabilities),
    'Net Worth': Number(p.net_worth),
  }))

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Net Worth Over Time</h2>
        <ReportInfoButton title="Net Worth Over Time">
          <p><strong>Net worth</strong> = total assets minus total liabilities across <strong>all accounts</strong> — on-budget, tracking, and loans — plus any manually tracked debts.</p>
          <p>The stacked area shows how <strong>assets</strong> and <strong>liabilities</strong> compose your net worth each month. A growing gap between them means you're building wealth.</p>
          <ReportScopeNote scope="all-accounts" />
        </ReportInfoButton>
        <div className="flex-row ms-auto">
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
          <ReportExportButton
            reportId="net-worth"
            getRows={() =>
              points.map((p) => ({
                date: p.date,
                assets: Number(p.total_assets),
                liabilities: Number(p.total_liabilities),
                net_worth: Number(p.net_worth),
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>

      <div ref={captureRef} className="report-capture">
      {latest && (
        <div className="report-metrics">
          <MetricCard label="Current Net Worth" value={formatMoney(Number(latest.net_worth))} />
          <MetricCard label="Total Assets" value={formatMoney(Number(latest.total_assets))} />
          <MetricCard label="Total Liabilities" value={formatMoney(Number(latest.total_liabilities))} />
        </div>
      )}
      {Number(data?.unmanaged_liability_total ?? 0) > 0 && (
        <p className="report-section__subtitle">
          Liabilities include {formatMoney(Number(data!.unmanaged_liability_total))} of manually
          tracked debt (no linked account).
        </p>
      )}

      {chartData.length === 0 ? (
        <div className="reports-empty">No account data available.</div>
      ) : (
        <ResponsiveContainer width="100%" height={chartHeight}>
          <AreaChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="nw-assets" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={COLOR_POSITIVE} stopOpacity={0.3} />
                <stop offset="95%" stopColor={COLOR_POSITIVE} stopOpacity={0.05} />
              </linearGradient>
              <linearGradient id="nw-net" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={COLOR_NET} stopOpacity={0.3} />
                <stop offset="95%" stopColor={COLOR_NET} stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
            <YAxis tickFormatter={(v) => formatMoney(v)} tick={{ fontSize: 11, fill: 'var(--text-muted)' }} width={90} />
            <Tooltip content={<ChartTooltip showTotal={false} />} offset={16} isAnimationActive={false} />
            <Legend />
            <Area type="monotone" dataKey="Assets" stroke={COLOR_POSITIVE} fill="url(#nw-assets)" strokeWidth={2} />
            <Area type="monotone" dataKey="Liabilities" stroke={COLOR_NEGATIVE} fill="none" strokeWidth={2} strokeDasharray="5 3" />
            <Area type="monotone" dataKey="Net Worth" stroke={COLOR_NET} fill="url(#nw-net)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      )}
      </div>
    </div>
  )
}
