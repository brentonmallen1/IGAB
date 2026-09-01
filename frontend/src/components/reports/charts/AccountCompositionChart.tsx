import { useRef, useState } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useAccountCompositionReport } from '../../../api/reports'
import { useAccountTypes } from '../../../api/accountTypes'
import { accountTypeLabel } from '../../../constants/accountTypes'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { ChartTooltip } from './ChartTooltip'
import { COLOR_NET, chartColor } from './chartColors'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportRangeButtons } from './rangeButtons'

interface Props {
  budgetId: string
}

export function AccountCompositionReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(340)
  const { formatMoney } = useFormatters()
  const [months, setMonths] = useState(12)
  const { data, isLoading, isError, error, refetch } = useAccountCompositionReport(budgetId, months)
  const { data: typeRows } = useAccountTypes(budgetId)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const points = data?.points ?? []
  // Series are whatever type keys this budget actually has — custom types
  // included. Balances carry their ledger sign, so liabilities plot negative.
  const typeKeys = [...new Set(points.flatMap((p) => Object.keys(p.balances)))].sort()
  const labelFor = (key: string) => accountTypeLabel(key, typeRows)
  const chartData = points.map((p) => ({
    date: p.date.slice(0, 7),
    Net: Number(p.net_worth),
    ...Object.fromEntries(typeKeys.map((k) => [labelFor(k), Number(p.balances[k] ?? 0)])),
  }))

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Account Composition</h2>
        <ReportInfoButton title="Account Composition">
          <p>
            Shows how your balance is distributed across <strong>account types</strong> — checking,
            savings, investments, loans, and any custom types — over time, across all accounts.
          </p>
          <p>
            Balances keep their sign: asset balances stack above zero, debt balances below. The{' '}
            <strong>Net</strong> line is their sum plus any unmanaged debts — the same figure the
            Net Worth report draws.
          </p>
          <ReportScopeNote scope="all-accounts" />
        </ReportInfoButton>
        <div className="flex-row ms-auto">
          <ReportRangeButtons months={months} onChange={setMonths} />
          <ReportExportButton
            reportId="account-composition"
            getRows={() =>
              points.map((p) => ({
                date: p.date,
                net_worth: Number(p.net_worth),
                ...Object.fromEntries(typeKeys.map((k) => [k, Number(p.balances[k] ?? 0)])),
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>
      <p className="report-section__subtitle">Assets stack positive, debts negative.</p>
      {Number(points[points.length - 1]?.asset_value_total ?? 0) > 0 && (
        <p className="report-section__subtitle">
          The Net line includes {formatMoney(Number(points[points.length - 1].asset_value_total))}{' '}
          of stated asset value that no account series shows.
        </p>
      )}

      <div ref={captureRef} className="report-capture">
        {chartData.length === 0 ? (
          <div className="reports-empty">No account data available.</div>
        ) : (
          <ResponsiveContainer width="100%" height={chartHeight}>
            {/* stackOffset="sign" is load-bearing: the default ("none")
                accumulates mixed signs naively, so a negative series walked
                the stack back DOWN and the debt band rendered inside the
                asset band — the exact opposite of the subtitle's promise.
                Sign-based is also the correct rule: an overdrawn checking
                account genuinely belongs below the line, which splitting by
                classification would get wrong. */}
            <ComposedChart
              data={chartData}
              stackOffset="sign"
              margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
              <YAxis
                tickFormatter={(v) => formatMoney(v)}
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                width={90}
              />
              {/* showTotal would sum the stack AND the net line — the Net row
                  already is the total, served rather than re-derived. */}
              <Tooltip
                content={<ChartTooltip showTotal={false} />}
                offset={16}
                isAnimationActive={false}
              />
              <Legend />
              <ReferenceLine y={0} stroke="var(--border-color)" strokeWidth={2} />
              {typeKeys.map((k, i) => (
                <Area
                  key={k}
                  type="monotone"
                  dataKey={labelFor(k)}
                  stroke={chartColor(i)}
                  fill={chartColor(i)}
                  fillOpacity={0.15}
                  strokeWidth={2}
                  stackId="1"
                />
              ))}
              <Line type="monotone" dataKey="Net" stroke={COLOR_NET} strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
