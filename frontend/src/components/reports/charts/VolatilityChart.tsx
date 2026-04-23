import { useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, ErrorBar,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useVolatilityReport } from '../../../api/reports'
import { formatMoney } from '../../../utils/money'
import { DrillDownTable } from '../DrillDownTable'
import { ReportInfoButton } from '../ReportInfoButton'

interface Props { budgetId: string }

export function VolatilityReport({ budgetId }: Props) {
  const [months, setMonths] = useState(12)
  const { data, isLoading } = useVolatilityReport(budgetId, months)

  if (isLoading) return <div className="report-loading">Loading…</div>

  const categories = (data?.categories ?? []).filter((c) => c.months_included >= 2)

  const chartData = categories.slice(0, 20).map((c) => ({
    name: c.category_name.length > 16 ? c.category_name.slice(0, 14) + '…' : c.category_name,
    Mean: Number(c.mean),
    errorY: [Number(c.mean) - Number(c.min_val), Number(c.max_val) - Number(c.mean)],
    StdDev: Number(c.std_dev),
    Min: Number(c.min_val),
    Max: Number(c.max_val),
  }))

  const tableRows = categories.map((c) => ({
    id: c.category_id,
    name: c.category_name,
    subName: c.category_group_name,
    amount: -Number(c.mean),
    pct: Number(c.mean) > 0 ? (Number(c.std_dev) / Number(c.mean)) * 100 : 0,
    extra: `σ ${formatMoney(Number(c.std_dev))}`,
  }))

  return (
    <div className="report-section">
      <div className="report-section__controls">
        <h2 className="report-section__title">Category Volatility</h2>
        <ReportInfoButton title="Category Volatility">
          <p>The <strong>bar</strong> shows the mean monthly spend. The <strong>error bars</strong> extend from the historical minimum to maximum, showing the full range of variation.</p>
          <p>Categories with large error bars (wide range) are <strong>unpredictable</strong> — they spike and drop month to month. These are candidates for a bigger buffer or a closer look at what drives the spikes.</p>
          <p>Only categories with at least 2 months of data are shown.</p>
        </ReportInfoButton>
        <p className="report-section__subtitle" style={{ margin: 0 }}>
          Mean monthly spending with min/max range. High variation = unstable spending.
        </p>
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
        </div>
      </div>

      {chartData.length === 0 ? (
        <div className="reports-empty">Not enough data to show volatility (need at least 2 months).</div>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={Math.max(300, chartData.length * 34)}>
            <BarChart
              data={chartData}
              layout="vertical"
              margin={{ top: 4, right: 80, left: 4, bottom: 4 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" horizontal={false} />
              <XAxis type="number" tickFormatter={(v) => formatMoney(v)} tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={130} />
              <Tooltip
                formatter={(v: number, name: string) => [formatMoney(v), name]}
                offset={16}
                isAnimationActive={false}
              />
              <Bar dataKey="Mean" fill="#4e79a7" barSize={12} radius={[0, 2, 2, 0]}>
                <ErrorBar dataKey="errorY" width={4} strokeWidth={2} stroke="#1e3a6e" direction="x" />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <DrillDownTable rows={tableRows} amountLabel="Mean/Month" />
        </>
      )}
    </div>
  )
}
