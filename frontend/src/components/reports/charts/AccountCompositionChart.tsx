import { useRef, useState } from 'react'
import {
  Area, AreaChart, CartesianGrid, Legend,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useAccountCompositionReport } from '../../../api/reports'
import { useAccountTypes } from '../../../api/accountTypes'
import { accountTypeLabel } from '../../../constants/accountTypes'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { ChartTooltip } from './ChartTooltip'
import { CHART_COLORS } from './chartColors'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'

interface Props { budgetId: string }

export function AccountCompositionReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(340)
  const { formatMoney } = useFormatters()
  const [months, setMonths] = useState(12)
  const { data, isLoading, isError, refetch } = useAccountCompositionReport(budgetId, months)
  const { data: typeRows } = useAccountTypes(budgetId)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState onRetry={() => refetch()} />

  const points = data?.points ?? []
  // Series are whatever type keys this budget actually has — custom types
  // included. Balances carry their ledger sign, so liabilities plot negative.
  const typeKeys = [...new Set(points.flatMap((p) => Object.keys(p.balances)))].sort()
  const labelFor = (key: string) => accountTypeLabel(key, typeRows)
  const chartData = points.map((p) => ({
    date: p.date.slice(0, 7),
    ...Object.fromEntries(typeKeys.map((k) => [labelFor(k), Number(p.balances[k] ?? 0)])),
  }))

  return (
    <div className="report-section">
      <div className="report-section__header">
        <h2 className="report-section__title">Account Composition</h2>
        <ReportInfoButton title="Account Composition">
          <p>Shows how your balance is distributed across <strong>account types</strong> — checking, savings, investments, loans, and any custom types — over time, across all accounts.</p>
          <p>Balances keep their sign: asset balances stack above zero, debt balances below. A growing asset area relative to debt is a healthy trend.</p>
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
            reportId="account-composition"
            getRows={() =>
              points.map((p) => ({
                date: p.date,
                ...Object.fromEntries(typeKeys.map((k) => [k, Number(p.balances[k] ?? 0)])),
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>
      <p className="report-section__subtitle">Assets stack positive, debts negative.</p>

      <div ref={captureRef} className="report-capture">
      {chartData.length === 0 ? (
        <div className="reports-empty">No account data available.</div>
      ) : (
        <ResponsiveContainer width="100%" height={chartHeight}>
          <AreaChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
            <YAxis tickFormatter={(v) => formatMoney(v)} tick={{ fontSize: 11, fill: 'var(--text-muted)' }} width={90} />
            <Tooltip content={<ChartTooltip showTotal />} offset={16} isAnimationActive={false} />
            <Legend />
            {typeKeys.map((k, i) => (
              <Area
                key={k}
                type="monotone"
                dataKey={labelFor(k)}
                stroke={CHART_COLORS[i % CHART_COLORS.length]}
                fill={CHART_COLORS[i % CHART_COLORS.length]}
                fillOpacity={0.15}
                strokeWidth={2}
                stackId="1"
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      )}
      </div>
    </div>
  )
}
