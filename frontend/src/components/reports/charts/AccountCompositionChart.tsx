import { useRef, useState } from 'react'
import {
  Area, AreaChart, CartesianGrid, Legend,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useAccountCompositionReport } from '../../../api/reports'
import { formatMoney } from '../../../utils/money'
import { ChartTooltip } from './ChartTooltip'
import { CHART_COLORS } from './chartColors'
import { ReportInfoButton } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'

const TYPE_LABELS: Record<string, string> = {
  checking: 'Checking',
  savings: 'Savings',
  credit_card: 'Credit Card',
  loan: 'Loan',
  tracking: 'Tracking',
}

interface Props { budgetId: string }

export function AccountCompositionReport({ budgetId }: Props) {
  const [months, setMonths] = useState(12)
  const { data, isLoading } = useAccountCompositionReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading…</div>

  const points = data?.points ?? []
  const chartData = points.map((p) => ({
    date: p.date.slice(0, 7),
    Checking: Number(p.checking),
    Savings: Number(p.savings),
    'Credit Card': -Number(p.credit_card),
    Loan: -Number(p.loan),
    Tracking: Number(p.tracking),
  }))

  return (
    <div className="report-section">
      <div className="report-section__controls">
        <h2 className="report-section__title">Account Composition</h2>
        <ReportInfoButton title="Account Composition">
          <p>Shows how your balance is distributed across <strong>account types</strong> (checking, savings, credit cards, loans) over time.</p>
          <p>Credit card and loan balances are shown as negative to reflect that they're liabilities. A growing savings area relative to credit card debt is a healthy trend.</p>
        </ReportInfoButton>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
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
                checking: Number(p.checking),
                savings: Number(p.savings),
                credit_card: Number(p.credit_card),
                loan: Number(p.loan),
                tracking: Number(p.tracking),
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>
      <p className="report-section__subtitle">Assets shown positive, liabilities negative.</p>

      <div ref={captureRef} className="report-capture">
      {chartData.length === 0 ? (
        <div className="reports-empty">No account data available.</div>
      ) : (
        <ResponsiveContainer width="100%" height={340}>
          <AreaChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis tickFormatter={(v) => formatMoney(v)} tick={{ fontSize: 11 }} width={90} />
            <Tooltip content={<ChartTooltip showTotal />} offset={16} isAnimationActive={false} />
            <Legend />
            {Object.keys(TYPE_LABELS).map((k, i) => (
              <Area
                key={k}
                type="monotone"
                dataKey={TYPE_LABELS[k]}
                stroke={CHART_COLORS[i]}
                fill={CHART_COLORS[i]}
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
