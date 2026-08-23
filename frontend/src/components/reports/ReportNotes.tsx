import { EyeOff, Info } from 'lucide-react'
import type { SpendingClassExcluded } from '../../types'
import { useFormatters } from '../../hooks/useFormatters'
import './ReportNotes.css'

/** How each class reads mid-sentence. A bare `label + 's'` produced
 *  "savingss", and "Interest & fees" was never pluralisable at all. */
const CLASS_PHRASE: Record<string, string> = {
  savings: 'savings',
  debt_principal: 'debt payments',
  debt_interest: 'interest & fees',
}

/** The parts of a report this reads. Structural rather than a named response
 *  type: three charts carry these notes and only one of them has a view. */
export interface ReportNotesSource {
  view_hidden_categories?: number
  view_hidden_total?: number | string
  class_excluded?: SpendingClassExcluded[] | null
}

interface Props {
  report: ReportNotesSource | undefined
  /** Whether the chart's "Include savings & debt payments" toggle is visible
   *  and off — the one action from here that adds the money back. Charts
   *  without that toggle pass false; the sentence would name a control the
   *  reader cannot find. */
  toggleAvailable: boolean
}

/**
 * The chart-face caveats: what the active view hid, and what classified out
 * of spending. One component because they are one thing to the reader — the
 * reasons this chart shows less than they expected — and one flex child
 * because the section's column gap otherwise spreads each line a full step
 * apart, which read as three unrelated paragraphs.
 *
 * Renders nothing when there is nothing to explain: an empty wrapper would
 * still occupy a gap slot in the section column.
 */
export function ReportNotes({ report, toggleAvailable }: Props) {
  const { formatMoney } = useFormatters()
  if (!report) return null

  const hidden = (report.view_hidden_categories ?? 0) > 0
  const excluded: SpendingClassExcluded[] = report.class_excluded ?? []
  if (!hidden && excluded.length === 0) return null

  const parts = excluded.map(
    (e) =>
      `${formatMoney(Number(e.total))} of ${CLASS_PHRASE[e.activity_class] ?? e.label.toLowerCase()}` +
      ` (${e.categories === 1 ? '1 category' : `${e.categories} categories`})`
  )

  return (
    <div className="report-notes">
      {hidden && (
        <p className="report-notes__line" role="note">
          <EyeOff size={12} aria-hidden />
          <span>
            This view hides{' '}
            {report.view_hidden_categories === 1
              ? '1 category'
              : `${report.view_hidden_categories} categories`}{' '}
            with {formatMoney(Number(report.view_hidden_total))} of spending in this window —
            edit the view or switch it off to see everything.
          </span>
        </p>
      )}
      {excluded.length > 0 && (
        <p className="report-notes__line" role="note">
          <Info size={12} aria-hidden />
          <span>
            Not counted as spending here: {parts.join(' and ')}.
            {toggleAvailable && ' Tick “Include savings & debt payments” to add it.'}
          </span>
        </p>
      )}
    </div>
  )
}


/**
 * The one control that adds savings and debt payments back into a spending
 * chart. Shared because it was written twice, and the copies drifted: the
 * treemap's label read "Hide tagged as savings" while its state fed
 * `includeSavings`, so ticking "hide" added them. Label and meaning now
 * travel together.
 */
export function IncludeSavingsToggle({
  checked,
  onChange,
}: {
  checked: boolean
  onChange: (next: boolean) => void
}) {
  return (
    <label className="report-toggle">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span title="Money moved into savings or used to pay down a tracked debt isn't spending, so it's left out by default. Tick to add it back.">
        Include savings &amp; debt payments
      </span>
    </label>
  )
}

/**
 * What an empty spending chart says. A view that hides everything with
 * spending is not the same as a window with no spending in it, and the
 * distinction is the difference between "your filter did this" and "you
 * spent nothing".
 */
export function emptySpendingMessage(viewHiddenCategories: number | undefined): string {
  return (viewHiddenCategories ?? 0) > 0
    ? 'Everything with spending in this window is hidden by the current view.'
    : 'No spending data for this period.'
}
