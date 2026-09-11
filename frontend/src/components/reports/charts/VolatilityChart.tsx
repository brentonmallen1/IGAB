import { useRef, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ErrorBar,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useReportMonths, useReportStore } from '../../../stores/reportStore'
import { useVolatilityReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { useMoneyAxis } from './useMoneyAxis'
import { ReportErrorState } from '../ReportErrorState'
import { COLOR_NEUTRAL, TOOLTIP_STYLE } from './chartColors'
import {
  buildVolatilityChartRows,
  coefficientOfVariation,
  filterVolatile,
  volatilityExport,
} from './volatilityData'
import { DrillDownTable } from '../DrillDownTable'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportRangeSelect } from './rangeSelect'

interface Props {
  budgetId: string
}

export function VolatilityReport({ budgetId }: Props) {
  const { formatMoney } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const setDrillDown = useReportStore((s) => s.setDrillDown)
  const months = useReportMonths()
  const [amortize, setAmortize] = useState(false)
  const { data, isLoading, isError, error, refetch } = useVolatilityReport(
    budgetId,
    months,
    amortize
  )
  const captureRef = useRef<HTMLDivElement>(null)

  // The window the statistics read, as served. This computed its own and the
  // two drifted: the panel added the partial current month the figures leave
  // out and dropped the oldest, so its count and total could not reconcile.
  function drillTo(categoryId: string, name: string) {
    if (!data) return
    setDrillDown({
      kind: 'category',
      label: name,
      scope: 'leaf',
      direction: 'outflow',
      categoryIds: [categoryId],
      startDate: data.window_start,
      endDate: data.window_end,
    })
  }

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const categories = filterVolatile(data?.categories ?? [])

  const chartData = buildVolatilityChartRows(categories)
  const amortized = data?.amortized ?? false
  const exported = volatilityExport(categories, amortized)

  const tableRows = categories.map((c) => ({
    id: c.category_id,
    name: c.category_name,
    subName: c.category_group_name,
    amount: c.mean,
    pct: coefficientOfVariation(c.mean, c.std_dev),
    extra: `σ ${formatMoney(c.std_dev)}`,
  }))

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Category Volatility</h2>
        <ReportInfoButton title="Category Volatility">
          <p>
            The <strong>bar</strong> shows the mean monthly spend. The <strong>whiskers</strong>{' '}
            extend from the historical minimum (drawn on the bar) to the maximum (drawn beside it) —
            the full range of variation.
          </p>
          <p>
            Categories with large error bars (wide range) are <strong>unpredictable</strong> — they
            spike and drop month to month. These are candidates for a bigger buffer or a closer look
            at what drives the spikes.
          </p>
          <p>
            <strong>Fewer, bigger payments read as volatile</strong>, and that is not a mistake: a
            month with nothing spent is a zero, so an annual insurance premium shows a wide range
            and a low mean. Its cost is steady; only its timing is lumpy.
          </p>
          <p>
            <strong>Amortize lumpy charges</strong> tells those apart. It spreads each charge
            forward over the months until the next one, so a bill of the same size every six months
            reads flat — and a category whose cost genuinely changed still shows a range. Months
            before a category&apos;s first charge in the window are left out of its figures, since a
            charge from before the window paid for them. The last charge spreads over the same gap
            as the one before it, so a bill paid in the window&apos;s final month reads at its
            monthly rate rather than its full size.
          </p>
          <p>Only categories with at least 2 months of data are shown.</p>
          <ReportScopeNote scope="categories" />
        </ReportInfoButton>
        <p className="report-section__subtitle">
          Mean monthly spending with min/max range. High variation = unstable spending.
        </p>
        <div className="flex-row ms-auto">
          <label className="report-toggle">
            <input
              type="checkbox"
              checked={amortize}
              onChange={(e) => setAmortize(e.target.checked)}
            />
            <span title="A bill paid twice a year has a steady cost and lumpy timing. Spreading each charge forward over the months until the next one separates that from a category whose cost genuinely swings.">
              Amortize lumpy charges
            </span>
          </label>
          <ReportRangeSelect />
          <ReportExportButton
            reportId={exported.reportId}
            getRows={() => exported.rows}
            captureRef={captureRef}
          />
        </div>
      </div>

      {chartData.length === 0 ? (
        <div className="reports-empty">
          Not enough data to show volatility (need at least 2 months).
        </div>
      ) : (
        <div ref={captureRef} className="report-capture">
          {/* Inside the capture, so a PNG of the amortized reading says so. */}
          {amortized && (
            <p className="report-note">
              Amortized: each charge is spread over the months it pays for.
            </p>
          )}
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
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                width={130}
              />
              <Tooltip
                formatter={(v: unknown, name: unknown) => [formatMoney(Number(v)), String(name)]}
                offset={16}
                isAnimationActive={false}
                {...TOOLTIP_STYLE}
              />
              <Bar dataKey="Mean" fill={COLOR_NEUTRAL} barSize={12} radius={[0, 2, 2, 0]}>
                {/* Two one-sided whiskers, because they land on two different
                    backgrounds: mean→min is drawn INSIDE the bar fill
                    (--chart-neutral), mean→max on the section surface. One
                    stroke cannot read on both — --text-secondary vanished on
                    the fill in every theme. --bg-primary vs --color-info is
                    ≥4.5:1 wherever the palette passes its own text checks
                    (contrast is symmetric); both pairs are pinned in
                    themes/contrast.test.ts. */}
                <ErrorBar
                  dataKey="errorLow"
                  width={8}
                  strokeWidth={2}
                  stroke="var(--bg-primary)"
                  direction="x"
                />
                <ErrorBar
                  dataKey="errorHigh"
                  width={8}
                  strokeWidth={2}
                  stroke="var(--text-primary)"
                  direction="x"
                />
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
