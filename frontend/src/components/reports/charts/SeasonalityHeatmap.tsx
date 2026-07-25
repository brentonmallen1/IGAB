import { useRef, useState } from 'react'
import { useReportStore } from '../../../stores/reportStore'
import { useSeasonalityReport } from '../../../api/reports'
import { formatMoney } from '../../../utils/money'
import { monthWindow } from '../../../utils/dateWindow'
import { ReportInfoButton } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import './SeasonalityHeatmap.css'

interface Props { budgetId: string }

function intensityColor(value: number, max: number): string {
  if (max === 0 || value === 0) return 'var(--bg-secondary)'
  const t = Math.min(1, value / max)
  // Interpolate from a muted blue to a vibrant red
  const r = Math.round(78 + (225 - 78) * t)
  const g = Math.round(121 + (50 - 121) * t)
  const b = Math.round(167 + (50 - 167) * t)
  return `rgba(${r},${g},${b},${0.2 + 0.7 * t})`
}

export function SeasonalityReport({ budgetId }: Props) {
  const setDrillDown = useReportStore((s) => s.setDrillDown)
  const [months, setMonths] = useState(12)
  const { data, isLoading } = useSeasonalityReport(budgetId, months)
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

  const allMonths = data?.months ?? []
  const categories = data?.categories ?? []
  const cells = data?.cells ?? []

  // Build lookup: category_id + month -> total
  const cellMap = new Map<string, number>()
  for (const cell of cells) {
    cellMap.set(`${cell.category_id}|${cell.month}`, Number(cell.total))
  }

  // Find max for color scale
  const maxVal = Math.max(...cells.map((c) => Number(c.total)), 1)

  return (
    <div className="report-section">
      <div className="report-section__controls">
        <h2 className="report-section__title">Seasonality Heatmap</h2>
        <ReportInfoButton title="Seasonality Heatmap">
          <p>Each cell shows spending for a <strong>category × month</strong> combination. Color intensity goes from <strong>cool blue</strong> (low spend) to <strong>red</strong> (peak spend).</p>
          <p>Look for recurring red columns — these are months where that category consistently spikes (holidays, annual subscriptions, seasonal utilities). Hover any cell for the exact amount.</p>
        </ReportInfoButton>
        <p className="report-section__subtitle" style={{ margin: 0 }}>Monthly spending intensity per category</p>
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
              <thead>
                <tr>
                  <th className="heatmap__cat-header">Category</th>
                  {allMonths.map((m) => (
                    <th key={String(m)} className="heatmap__month-header">
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
                          style={{ background: intensityColor(val, maxVal) }}
                          title={`${cat.name} · ${String(m).slice(0, 7)}: ${formatMoney(val)}`}
                          onClick={val > 0 ? () => drillTo(cat.id, cat.name, String(m)) : undefined}
                        >
                          {val > 0 && (
                            <span className="heatmap__cell-value">
                              {val >= 1000 ? `${(val / 1000).toFixed(1)}k` : val.toFixed(0)}
                            </span>
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
