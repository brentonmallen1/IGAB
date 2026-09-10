import { useMemo, useRef, useState } from 'react'
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { useSpendingGroupedReport } from '../../../api/reports'
import { useReportStore, spendingDrillClasses } from '../../../stores/reportStore'
import { useFormatters } from '../../../hooks/useFormatters'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { ReportErrorState } from '../ReportErrorState'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ChartTooltip } from './ChartTooltip'
import { chartColor } from './chartColors'
import { useReportScope } from '../../../stores/reportStore'
import { ReportNotes } from '../ReportNotes'

interface Props {
  budgetId: string
}

/**
 * A period's spending as a donut: groups first, click one to see its
 * categories. Reads the same grouped rollup the Pareto and treemap read.
 */
export function SpendingBreakdownReport({ budgetId }: Props) {
  const { formatMoney } = useFormatters()
  const chartHeight = useChartHeight(360)
  const { filters, setDrillDown } = useReportStore()
  const [includeSavings, setIncludeSavings] = useState(false)
  const [openGroup, setOpenGroup] = useState<string | null>(null)
  const captureRef = useRef<HTMLDivElement>(null)

  const reportScope = useReportScope()
  const { data, isLoading, isError, error, refetch } = useSpendingGroupedReport(
    budgetId,
    filters.startDate,
    filters.endDate,
    reportScope,
    filters.accountIds.length ? filters.accountIds : undefined,
    includeSavings,
    filters.viewId
  )

  const groups = useMemo(() => {
    const by = new Map<string, { key: string; name: string; total: number; items: typeof items }>()
    const items = data?.groups ?? []
    for (const it of items) {
      const key = it.parent_id ?? '__none__'
      const g = by.get(key) ?? { key, name: it.parent_name ?? 'Ungrouped', total: 0, items: [] }
      g.total += it.total
      g.items.push(it)
      by.set(key, g)
    }
    return [...by.values()].sort((a, b) => b.total - a.total)
  }, [data])

  if (isLoading) return <div className="report-loading">Loading...</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />
  if (!data) return null

  const open = groups.find((g) => g.key === openGroup) ?? null
  const slices = open
    ? open.items.map((it) => ({ key: it.id, name: it.name, value: it.total }))
    : groups.map((g) => ({ key: g.key, name: g.name, value: g.total }))
  const total = open ? open.total : data.total

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Spending Breakdown</h2>
        <ReportInfoButton title="Spending Breakdown">
          <p>
            Where the period&apos;s spending went, by group. Click a slice or a row to open that
            group&apos;s categories. Percentages are of what is on screen.
          </p>
          <ReportScopeNote scope="categories" />
        </ReportInfoButton>
        <div className="flex-row">
          {open && (
            <button type="button" className="report-btn" onClick={() => setOpenGroup(null)}>
              ← All groups
            </button>
          )}
          <label className="report-toggle">
            <input
              type="checkbox"
              checked={includeSavings}
              onChange={(e) => setIncludeSavings(e.target.checked)}
            />
            Include savings &amp; debt payments
          </label>
        </div>
        <div style={{ marginLeft: 'auto' }}>
          <ReportExportButton
            reportId="spending-breakdown"
            getRows={() =>
              (data.groups ?? []).map((it) => ({
                group: it.parent_name ?? '',
                category: it.name,
                total: it.total,
                pct: it.pct,
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>

      {/* `ReportNotes` owns all three caveats. This chart re-implemented the
          view-hidden sentence, never rendered the served `class_excluded` note
          at all, and had nothing for a missing saved filter — so money the
          report deliberately left out simply went missing from the screen. */}
      <ReportNotes report={data} toggleAvailable={false} />

      {slices.length === 0 ? (
        <div className="reports-empty">
          <p>Nothing spent in this window.</p>
        </div>
      ) : (
        <div ref={captureRef} className="report-capture">
          <MetricRow>
            <MetricCard label={open ? open.name : 'Total spending'} value={formatMoney(total)} />
            <MetricCard label={open ? 'Categories' : 'Groups'} value={String(slices.length)} />
          </MetricRow>
          <div className="report-chart" style={{ height: chartHeight }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={slices}
                  dataKey="value"
                  nameKey="name"
                  innerRadius="55%"
                  outerRadius="85%"
                  paddingAngle={1}
                  onClick={(_, idx) => {
                    if (!open) setOpenGroup(slices[idx]?.key ?? null)
                  }}
                >
                  {slices.map((s, idx) => (
                    <Cell
                      key={s.key}
                      fill={chartColor(idx)}
                      cursor={open ? 'default' : 'pointer'}
                    />
                  ))}
                </Pie>
                <Tooltip
                  content={({ active, payload }) => (
                    <ChartTooltip
                      active={active}
                      payload={payload?.map((p) => ({
                        name: String(p.name ?? ''),
                        value: Number(p.value ?? 0),
                        color: p.color,
                        fill: p.fill,
                      }))}
                      label=""
                      formatter={formatMoney}
                    />
                  )}
                />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <table className="report-table">
            <caption className="sr-only">Spending breakdown</caption>
            <thead>
              <tr>
                <th scope="col" style={{ textAlign: 'left' }}>
                  {open ? 'Category' : 'Group'}
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Spent
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Share
                </th>
              </tr>
            </thead>
            <tbody>
              {slices.map((s) => (
                <tr
                  key={s.key}
                  style={{ cursor: 'pointer' }}
                  onClick={() => {
                    if (!open) {
                      setOpenGroup(s.key)
                      return
                    }
                    setDrillDown({
                      kind: 'category',
                      label: s.name,
                      scope: 'leaf',
                      direction: 'outflow',
                      categoryIds: [s.key],
                      activityClasses: spendingDrillClasses(includeSavings),
                      startDate: filters.startDate,
                      endDate: filters.endDate,
                    })
                  }}
                >
                  <td>{s.name}</td>
                  <td style={{ textAlign: 'right' }}>{formatMoney(s.value)}</td>
                  <td style={{ textAlign: 'right', color: 'var(--text-muted)' }}>
                    {total > 0 ? `${Math.round((s.value / total) * 100)}%` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
