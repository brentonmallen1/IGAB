// The month-range selector every report chart carries. It was written out
// nine times, each one its own `[6, 12, 24].map()` over an identical button,
// and the copies had already parted company: eight offered 6/12/24 while
// IncomeExpenseChart offered 3/6/12/24. That difference is real — a shorter
// horizon suits an income-vs-expense read — so it is a parameter here rather
// than a tenth copy.
//
// Sits beside LogScaleToggle, which is the same idea for the same toolbar.

// Not exported: the default is expressed in the prop below, and a second
// export here costs a react-refresh warning — debt this repo only spends
// downward.
const DEFAULT_RANGES = [6, 12, 24] as const

export function ReportRangeButtons({
  months,
  onChange,
  ranges = DEFAULT_RANGES,
}: {
  months: number
  onChange: (months: number) => void
  /** Override only where a report genuinely needs a different horizon. */
  ranges?: readonly number[]
}) {
  return (
    <>
      {ranges.map((m) => (
        <button
          key={m}
          className={`report-btn ${months === m ? 'report-btn--active' : ''}`}
          onClick={() => onChange(m)}
          type="button"
          aria-pressed={months === m}
        >
          {m}mo
        </button>
      ))}
    </>
  )
}
