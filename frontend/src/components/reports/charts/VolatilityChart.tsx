import { useRef, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, ErrorBar,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useReportStore } from '../../../stores/reportStore'
import { useVolatilityReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { COLOR_NEUTRAL, TOOLTIP_STYLE } from './chartColors'
import { buildVolatilityChartRows, coefficientOfVariation, filterVolatile } from './volatilityData'
import { monthsAgoStartISO } from '../../../utils/dateWindow'
import { today } from '../../../utils/dates'
import { DrillDownTable } from '../DrillDownTable'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'

interface Props { budgetId: string }

export function VolatilityReport({ budgetId }: Props) {
  const { formatMoney } = useFormatters()
  const setDrillDown = useReportStore((s) => s.setDrillDown)
  const [months, setMonths] = useState(12)
  const { data, isLoading, isError, error, refetch } = useVolatilityReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  // Same window the backend aggregates over: first-of-month (months-1) ago → today
  function drillTo(categoryId: string, name: string) {
    setDrillDown({
      kind: 'category', label: name, scope: 'leaf', direction: 'outflow',
      categoryIds: [categoryId], startDate: monthsAgoStartISO(months - 1), endDate: today(),
    })
  }

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const categories = filterVolatile(data?.categories ?? [])

  const chartData = buildVolatilityChartRows(categories)

  const tableRows = categories.map((c) => ({
    id: c.category_id,
    name: c.category_name,
    subName: c.category_group_name,
    amount: -Number(c.mean),
    pct: coefficientOfVariation(Number(c.mean), Number(c.std_dev)),
    extra: `σ ${formatMoney(Number(c.std_dev))}`,
  }))

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Category Volatility</h2>
        <ReportInfoButton title="Category Volatility">
          <p>The <strong>bar</strong> shows the mean monthly spend. The <strong>error bars</strong> extend from the historical minimum to maximum, showing the full range of variation.</p>
          <p>Categories with large error bars (wide range) are <strong>unpredictable</strong> — they spike and drop month to month. These are candidates for a bigger buffer or a closer look at what drives the spikes.</p>
          <p>Only categories with at least 2 months of data are shown.</p>
          <ReportScopeNote scope="categories" />
        </ReportInfoButton>
        <p className="report-section__subtitle">
          Mean monthly spending with min/max range. High variation = unstable spending.
        </p>
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
            reportId="volatility"
            getRows={() =>
              categories.map((c) => ({
                category: c.category_name,
                group: c.category_group_name,
                mean: Number(c.mean),
                std_dev: Number(c.std_dev),
                min: Number(c.min_val),
                max: Number(c.max_val),
                months: c.months_included,
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>

      {chartData.length === 0 ? (
        <div className="reports-empty">Not enough data to show volatility (need at least 2 months).</div>
      ) : (
        <div ref={captureRef} className="report-capture">
          <ResponsiveContainer width="100%" height={Math.max(300, chartData.length * 34)}>
            <BarChart
              data={chartData}
              layout="vertical"
              margin={{ top: 4, right: 80, left: 4, bottom: 4 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" horizontal={false} />
              <XAxis type="number" tickFormatter={(v) => formatMoney(v)} tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} width={130} />
              <Tooltip
                formatter={(v: unknown, name: unknown) => [formatMoney(Number(v)), String(name)]}
                offset={16}
                isAnimationActive={false}
                {...TOOLTIP_STYLE}
              />
              <Bar dataKey="Mean" fill={COLOR_NEUTRAL} barSize={12} radius={[0, 2, 2, 0]}>
                <ErrorBar dataKey="errorY" width={4} strokeWidth={2} stroke="var(--text-secondary)" direction="x" />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <DrillDownTable
            rows={tableRows}
            amountLabel="Mean/Month"
            onRowClick={(row) => drillTo(row.id, row.name)}
          />
        </div>
      )}
    </div>
  )
}
