import { X } from 'lucide-react'
import type { NarrowingKey, NarrowingPart } from '../gridNarrowing'
import './BudgetFilterStrip.css'

/**
 * What a phone's grid is not showing, pinned above it while anything narrows
 * it: one chip per status, saved filter, search or view, each undone on its
 * own. The controls that set these are in the Tools sheet, out of sight, so a
 * filtered list would otherwise read like a short budget.
 *
 * Takes the desktop filter bar's place in the grid's sticky stack — the column
 * header is offset by its measured height (`--budget-filter-bar-h`) — and is
 * absent, height zero, when the grid is showing everything.
 */
export function BudgetFilterStrip({
  parts,
  onClear,
  stripRef,
}: {
  parts: NarrowingPart[]
  onClear: (key: NarrowingKey) => void
  stripRef?: (node: HTMLDivElement | null) => void
}) {
  if (parts.length === 0) return null
  return (
    <div className="budget-filter-strip surface surface--chrome" ref={stripRef}>
      <span className="budget-filter-strip__label">Showing</span>
      <ul className="budget-filter-strip__parts">
        {parts.map((p) => (
          <li key={p.key}>
            <button
              type="button"
              className="budget-filter-strip__chip"
              onClick={() => onClear(p.key)}
              aria-label={`Stop showing only ${p.label}`}
            >
              {p.label}
              <X size={13} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
