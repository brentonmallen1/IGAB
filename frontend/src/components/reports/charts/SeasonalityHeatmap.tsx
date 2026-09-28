import { useLayoutEffect, useRef, useState } from 'react'
import { useReportMonths, useReportStore } from '../../../stores/reportStore'
import { useSeasonalityReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { abbreviateValue, buildCellMap, cellKey, intensityPct, rowMaxima } from './seasonalityScale'
import { monthWindow } from '../../../utils/dateWindow'
import { ReportInfoButton, ReportScopeNote, SpendingClassNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportRangeSelect } from './rangeSelect'
import { IncludeSavingsToggle } from '../ReportNotes'
import { categoryKey, categoryTarget } from '../drillScope'
import './SeasonalityHeatmap.css'
import { truncateLabel } from '../../../utils/truncateLabel'

interface Props {
  budgetId: string
}

function intensityStyle(value: number, rowMax: number | undefined): React.CSSProperties {
  const pct = intensityPct(value, rowMax)
  if (pct === null) return { background: 'var(--bg-secondary)' }
  return {
    background: `color-mix(in srgb, var(--heatmap-high) ${pct}%, var(--heatmap-low))`,
  }
}

export function SeasonalityReport({ budgetId }: Props) {
  const { formatMoney, formatMonthShort, privacyMode } = useFormatters()
  const setDrillDown = useReportStore((s) => s.setDrillDown)
  const months = useReportMonths()
  const [includeSavings, setIncludeSavings] = useState(false)
  const { data, isLoading, isError, error, refetch } = useSeasonalityReport(
    budgetId,
    months,
    includeSavings
  )
  const captureRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Open on the newest month. On a phone the grid is wider than the screen,
  // and it opened on the oldest months with the one a reader came for off
  // the right edge.
  useLayoutEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollLeft = el.scrollWidth
  }, [data])

  function drillTo(categoryId: string | null, categoryName: string, month: string) {
    if (!data) return
    const window = monthWindow(month)
    setDrillDown({
      kind: 'category',
      label: `${categoryName} · ${formatMonthShort(month)}`,
      scope: 'leaf',
      ...categoryTarget([categoryId]),
      // The classes the cells counted, whichever way each row went: a cell
      // is net of refunds, and an outflow drill listed more than it said.
      activityClasses: data.counted_classes,
      startDate: window.start,
      endDate: window.end,
    })
  }

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const allMonths = data?.months ?? []
  const categories = data?.categories ?? []
  const cells = data?.cells ?? []

  const cellMap = buildCellMap(cells)
  const maxima = rowMaxima(cells)
  const shownOf =
    data && data.category_count > categories.length
      ? `The top ${categories.length} of ${data.category_count} categories by spending`
      : 'Every category that spent'

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Seasonality Heatmap</h2>
        <ReportInfoButton title="Seasonality Heatmap">
          <p>
            Each cell is one category&apos;s spending in one month. Shading is per row: the darkest
            cell in a row is that category&apos;s busiest month and the lightest its quietest, so a
            small category&apos;s seasons show as clearly as a large one&apos;s. Read sizes from the
            figures in the cells.
          </p>
          <p>
            Look for the same months darkening year after year — holidays, annual subscriptions,
            seasonal utilities. Hover any cell for the exact amount; click it for the transactions.
          </p>
          <ReportScopeNote report="seasonality" />
          <SpendingClassNote />
        </ReportInfoButton>
        <p className="report-section__subtitle">{shownOf}, complete months only</p>
        <div className="flex-row ms-auto">
          <IncludeSavingsToggle checked={includeSavings} onChange={setIncludeSavings} />
          <ReportRangeSelect />
          <ReportExportButton
            reportId="seasonality"
            getRows={() =>
              // Wide format: one row per category, one column per month
              categories.map((cat) => {
                const row: Record<string, unknown> = { category: cat.name }
                for (const m of allMonths) {
                  row[String(m).slice(0, 7)] = cellMap.get(cellKey(cat.id, String(m))) ?? 0
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
          <div className="heatmap__scroll" ref={scrollRef}>
            <table className="heatmap__table">
              <caption className="sr-only">Spending by category and month</caption>
              <thead>
                <tr>
                  <th scope="col" className="heatmap__cat-header">
                    Category
                  </th>
                  {allMonths.map((m) => (
                    <th scope="col" key={String(m)} className="heatmap__month-header">
                      {formatMonthShort(String(m))}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {categories.map((cat) => (
                  <tr key={categoryKey(cat.id)}>
                    <th scope="row" className="heatmap__cat-name" title={cat.name}>
                      {truncateLabel(cat.name, 20)}
                    </th>
                    {allMonths.map((m) => {
                      const val = cellMap.get(cellKey(cat.id, String(m))) ?? 0
                      return (
                        <td
                          key={String(m)}
                          className={`heatmap__cell ${val !== 0 ? 'heatmap__cell--clickable' : ''}`}
                          style={intensityStyle(val, maxima.get(categoryKey(cat.id)))}
                          title={`${cat.name} · ${formatMonthShort(String(m))}: ${formatMoney(val)}`}
                          onClick={
                            val !== 0 ? () => drillTo(cat.id, cat.name, String(m)) : undefined
                          }
                        >
                          {val !== 0 && (
                            <span className="heatmap__cell-value">
                              {abbreviateValue(val, privacyMode)}
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
            <span className="heatmap__legend-label">Quietest</span>
            <div className="heatmap__legend-scale" />
            <span className="heatmap__legend-label">Busiest month, per category</span>
          </div>
        </div>
      )}
    </div>
  )
}
