import { useCallback, useEffect, useRef, useState, type ReactNode, type Ref } from 'react'
import { createPortal } from 'react-dom'
import { scrollParent } from '../common/Surface'
import { MetricCompactContext } from './metricCompact'
import { summaryShown } from './reportSummary'
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
 *
 * Once the row has scrolled up under its report's pinned header
 * (`ReportHeader`), the same cards are drawn a second time, compact, in the
 * header's summary slot.
 */
export function MetricRow({ children, ref }: { children: ReactNode; ref?: Ref<HTMLDivElement> }) {
  const rowRef = useRef<HTMLDivElement | null>(null)
  const setRef = useCallback(
    (el: HTMLDivElement | null) => {
      rowRef.current = el
      if (typeof ref === 'function') ref(el)
      else if (ref) ref.current = el
    },
    [ref]
  )
  const slot = useSummarySlot(rowRef)
  return (
    <>
      <div className="metric-row" ref={setRef}>
        {children}
      </div>
      {slot &&
        createPortal(
          <MetricCompactContext.Provider value={true}>
            <div className="metric-summary">{children}</div>
          </MetricCompactContext.Provider>,
          slot
        )}
    </>
  )
}

/** The pinned header's summary slot while this row is scrolled up under it;
 *  null otherwise, and wherever the row has no report header above it.
 *
 *  Watched against the part of the scroll box below the pinned header: the
 *  observer's top margin is the header's pinned height, and it is made again
 *  whenever the header changes size (it wraps on a narrow screen, and
 *  `ReportHeader` re-measures what stays pinned first). No class check for
 *  "pinned" — that flag arrives a frame late, and one jump to the bottom is
 *  one scroll; an unpinned header sits above the row it heads anyway. */
function useSummarySlot(rowRef: { current: HTMLDivElement | null }): HTMLElement | null {
  const [slot, setSlot] = useState<HTMLElement | null>(null)
  useEffect(() => {
    const row = rowRef.current
    // The nearest card that holds a report header directly: a report's
    // section, or a dashboard's own card (Overview, Essentials).
    const header = row
      ?.closest(':has(> .report-section__header)')
      ?.querySelector<HTMLElement>(':scope > .report-section__header')
    const target = header?.querySelector<HTMLElement>(':scope > .report-section__summary')
    if (!row || !header || !target || typeof IntersectionObserver === 'undefined') return
    let observer: IntersectionObserver | null = null
    const watch = () => {
      observer?.disconnect()
      const lead = Number(header.style.getPropertyValue('--report-header-lead').replace('px', ''))
      const pinned = Math.max(0, header.offsetHeight - (lead || 0))
      observer = new IntersectionObserver(
        ([entry]) =>
          setSlot(
            summaryShown(entry.boundingClientRect.bottom, entry.rootBounds?.top ?? null)
              ? target
              : null
          ),
        { root: scrollParent(row), rootMargin: `-${pinned}px 0px 0px 0px` }
      )
      observer.observe(row)
    }
    watch()
    const resize = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(watch)
    resize?.observe(header)
    return () => {
      observer?.disconnect()
      resize?.disconnect()
    }
  }, [rowRef])
  return slot
}
