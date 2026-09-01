import type { ReactNode, Ref } from 'react'
import './MetricCard.css'

/**
 * The one row of MetricCards.
 *
 * Three containers existed for this concept — `.report-metrics` (flex,
 * content-width, 17 call sites), `.overview-report__metrics-grid` (grid,
 * 170px tracks that a 1.5rem tabular value overflowed by ~30px, 2 sites) and
 * `.liability-page__metrics` (a third grid) — so the same card was
 * equal-width on one page and ragged on the next, and Essentials depended on
 * OverviewReport's stylesheet happening to be loaded. One component, its CSS
 * beside the card's.
 */
export function MetricRow({ children, ref }: { children: ReactNode; ref?: Ref<HTMLDivElement> }) {
  return (
    <div className="metric-row" ref={ref}>
      {children}
    </div>
  )
}
