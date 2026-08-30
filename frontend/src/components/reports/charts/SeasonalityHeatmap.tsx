import { useRef, useState } from 'react'
import { useReportStore } from '../../../stores/reportStore'
import { useSeasonalityReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { abbreviateValue, buildCellMap, intensityPct, maxCellValue } from './seasonalityScale'
import { monthWindow } from '../../../utils/dateWindow'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportRangeButtons } from './rangeButtons'
import './SeasonalityHeatmap.css'

interface Props { budgetId: string }

function intensityStyle(value: number, max: number): React.CSSProperties {
  const pct = intensityPct(value, max)
  if (pct === null) return { background: 'var(--bg-secondary)' }
  return {
    background: `color-mix(in srgb, var(--heatmap-high) ${pct}%, var(--heatmap-low))`,
  }
}

export function SeasonalityReport({ budgetId }: Props) {
  const { formatMoney } = useFormatters()
  const setDrillDown = useReportStore((s) => s.setDrillDown)
  const [months, setMonths] = useState(12)
  const { data, isLoading, isError, error, refetch } = useSeasonalityReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  function drillTo(categoryId: string, categoryName: string, month: string) {
    const ym = month.slice(0, 7)
    const window = monthWindow(ym)
    setDrillDown({
      kind: 'category', label: `${categoryName} · ${ym}`, scope: 'leaf',
      direction: 'outflow', categoryIds: [categoryId],
      startDate: window.start, endDate: window.end,
    })
  }

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const allMonths = data?.months ?? []
  const categories = data?.categories ?? []
  const cells = data?.cells ?? []

  const cellMap = buildCellMap(cells)
  const maxVal = maxCellValue(cells)

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Seasonality Heatmap</h2>
        <ReportInfoButton title="Seasonality Heatmap">
          <p>Each cell shows spending for a <strong>category × month</strong> combination. Color intensity goes from <strong>cool blue</strong> (low spend) to <strong>red</strong> (peak spend).</p>
          <p>Look for recurring red columns — these are months where that category consistently spikes (holidays, annual subscriptions, seasonal utilities). Hover any cell for the exact amount.</p>
          <ReportScopeNote scope="categories" />
        </ReportInfoButton>
        <p className="report-section__subtitle">Monthly spending intensity per category</p>
        <div className="flex-row ms-auto">
          <ReportRangeButtons
            months={months}
            onChange={setMonths}
          />
          <ReportExportButton
            reportId="seasonality"
            getRows={() =>
              // Wide format: one row per category, one column per month
              categories.map((cat) => {
                const row: Record<string, unknown> = { category: cat.name }
                for (const m of allMonths) {
                  row[String(m).slice(0, 7)] = cellMap.get(`${cat.id}|${String(m)}`) ?? 0
                }
                return row
              })
            }
            captureRef={captureRef}
          />
        </div>
      </div>

      {categories.length === 0 ? (
        <div className="reports-empty">No spending data for this period.</div>
      ) : (
        <div className="heatmap" ref={captureRef}>
          <div className="heatmap__scroll">
            <table className="heatmap__table">
              <caption className="sr-only">Spending by category and month</caption>
              <thead>
                <tr>
                  <th scope="col" className="heatmap__cat-header">Category</th>
                  {allMonths.map((m) => (
                    <th scope="col" key={String(m)} className="heatmap__month-header">
                      {String(m).slice(0, 7)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {categories.map((cat) => (
                  <tr key={cat.id}>
                    <td className="heatmap__cat-name" title={cat.name}>
                      {cat.name.length > 20 ? cat.name.slice(0, 18) + '…' : cat.name}
                    </td>
                    {allMonths.map((m) => {
                      const val = cellMap.get(`${cat.id}|${String(m)}`) ?? 0
                      return (
                        <td
                          key={String(m)}
                          className={`heatmap__cell ${val > 0 ? 'heatmap__cell--clickable' : ''}`}
                          style={intensityStyle(val, maxVal)}
                          title={`${cat.name} · ${String(m).slice(0, 7)}: ${formatMoney(val)}`}
                          onClick={val > 0 ? () => drillTo(cat.id, cat.name, String(m)) : undefined}
                        >
                          {val > 0 && (
                            <span className="heatmap__cell-value">{abbreviateValue(val)}</span>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="heatmap__legend">
            <span className="heatmap__legend-label">Low</span>
            <div className="heatmap__legend-scale" />
            <span className="heatmap__legend-label">High ({formatMoney(maxVal)})</span>
          </div>
        </div>
      )}
    </div>
  )
}
