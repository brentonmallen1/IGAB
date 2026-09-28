import { useLayoutEffect, type ReactNode } from 'react'
import { scrollParent, useStuck } from '../common/Surface'
import { mayPin, pinnedLead } from './reportSummary'

/**
 * A report's header row — title, info, subtitle and its controls — pinned to
 * the top of the reports pane while the report scrolls under it, so the
 * range, toggles and export stay in reach at the bottom of a long table.
 *
 * Where the header stacks (a phone), only its last row — the controls — stays
 * pinned: the rows above it scroll away (`pinnedLead`, published as
 * `--report-header-lead` for the sticky offset). One whose controls would
 * still cover too much of the pane (`mayPin`) does not pin at all.
 *
 * It carries the summary slot a `MetricRow` fills once its value boxes have
 * scrolled up under it (`reportSummary.ts`): the slot hangs below the
 * header, out of flow, so showing it never changes the page's height.
 */
export function ReportHeader({ children, className }: { children: ReactNode; className?: string }) {
  const { ref, stuck } = useStuck<HTMLDivElement>(true)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => {
      const rows = [...el.children].filter(
        (c): c is HTMLElement =>
          c instanceof HTMLElement && !c.classList.contains('report-section__summary')
      )
      const last = rows.at(-1)
      const first = rows[0]
      const lead =
        first && last
          ? pinnedLead(last.offsetTop, first.offsetTop, first.offsetTop + first.offsetHeight)
          : 0
      const pinned = el.offsetHeight - lead
      const pins = mayPin(pinned, scrollParent(el)?.clientHeight ?? 0)
      el.style.setProperty('--report-header-lead', `${lead}px`)
      // A data attribute, not a class: React owns className and rewrites it
      // whenever the stuck shadow toggles.
      el.dataset.pinned = pins ? 'yes' : 'no'
      // What stays pinned, and the summary line's room beneath it — on the
      // section, where a strip that pins under the header (Plan vs Spent's
      // column header) reads where to stop. Nothing, when it does not pin.
      const section = el.parentElement
      section?.style.setProperty('--report-header-pinned', `${pins ? pinned : 0}px`)
      section?.style.setProperty('--report-summary-room', pins ? 'var(--report-summary-h)' : '0px')
    }
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [ref])

  return (
    <div
      ref={ref}
      className={[
        'report-section__header',
        stuck ? 'report-section__header--stuck' : '',
        className ?? '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {children}
      {/* A copy of figures the page already shows in full: hidden from
          assistive tech, which reads the value boxes themselves. */}
      <div className="report-section__summary" aria-hidden="true" />
    </div>
  )
}
