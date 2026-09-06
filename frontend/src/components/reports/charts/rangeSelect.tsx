import { useReportRange } from '../../../api/reports'
import { useAppStore } from '../../../stores/appStore'

/**
 * The month-range picker every report chart carries.
 *
 * It was nine hand-written `[6, 12, 24].map()` button rows before it was one
 * component, and three buttons is all a row of buttons can hold — which is
 * why the horizon stopped at two years no matter how much history a budget
 * had. A select holds as many windows as the data justifies and costs the
 * same width.
 *
 * The options are DERIVED from what the budget actually contains
 * (`/reports/range`), not from a fixed list. Offering 60 months to a budget
 * with 18 draws 42 empty leading months, which reads as data loss rather than
 * as an empty window — and it is also why "All time" is resolved to a real
 * number here rather than sent as a sentinel the nine report endpoints would
 * each have to interpret.
 *
 * Sits beside LogScaleToggle, which is the same idea for the same toolbar.
 */

/** Windows worth offering, before the budget's own history narrows them. */
const STEPS = [3, 6, 12, 24, 36, 48, 60] as const

export interface RangeOption {
  months: number
  label: string
}

/**
 * The offered windows for a budget with `monthsAvailable` months of history,
 * plus whatever the chart is currently showing.
 *
 * `current` is included even when the history no longer justifies it: a
 * select whose value matches no option renders blank, and a blank control
 * over a chart that is plainly showing something is worse than an option that
 * is merely generous. Picking anything else removes it.
 *
 * `monthsAvailable` of 0 (an empty budget, or the range not fetched yet) means
 * "unknown", not "nothing" — the plain ladder is the honest fallback there.
 */
export function rangeOptions(monthsAvailable: number, current: number): RangeOption[] {
  const label = (m: number) => ({ months: m, label: `${m} months` })
  const options = monthsAvailable
    ? [
        ...STEPS.filter((m) => m < monthsAvailable).map(label),
        { months: monthsAvailable, label: `All time (${monthsAvailable} months)` },
      ]
    : STEPS.map(label)
  return options.some((o) => o.months === current) ? options : [...options, label(current)]
}

export function ReportRangeSelect({
  months,
  onChange,
}: {
  months: number
  onChange: (months: number) => void
}) {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: range } = useReportRange(budgetId)
  const options = rangeOptions(range?.months_available ?? 0, months)

  return (
    <select
      className="report-select"
      value={months}
      onChange={(e) => onChange(Number(e.target.value))}
      aria-label="Date range"
    >
      {options.map((o) => (
        <option key={o.months} value={o.months}>
          {o.label}
        </option>
      ))}
    </select>
  )
}
