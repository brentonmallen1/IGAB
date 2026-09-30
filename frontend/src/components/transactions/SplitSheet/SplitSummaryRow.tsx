import { ChevronRight } from 'lucide-react'
import { useFormatters } from '../../../hooks/useFormatters'
import { checkSplit } from '../../../utils/splits'
import type { SplitDraft } from '../../../stores/transactionEditStore'
import { splitLabel, splitProgress, splitStatus } from './splitSummary'
import './SplitSheet.css'

/**
 * A split, folded into one row of the form: which envelopes, how far along,
 * what is left. Tapping it opens the SplitSheet — the lines themselves need
 * the whole screen, not a strip of the form.
 */
export function SplitSummaryRow({
  totalCents,
  legs,
  nameOf,
  onOpen,
  framed = false,
}: {
  totalCents: number
  legs: SplitDraft[]
  nameOf: (categoryId: string) => string
  onOpen: () => void
  /** Draw its own box — for a form whose fields are boxes, not rows. */
  framed?: boolean
}) {
  const { formatMoney } = useFormatters()
  const check = checkSplit(totalCents, legs)
  const status = splitStatus(check, formatMoney)
  return (
    <button
      type="button"
      className={`split-summary ${framed ? 'split-summary--framed' : ''}`}
      onClick={onOpen}
      aria-label="Edit split"
    >
      <span className="split-summary__label">Split</span>
      <span className="split-summary__body">
        <span className="split-summary__names">{splitLabel(legs, nameOf)}</span>
        <span className="split-sheet__bar" aria-hidden>
          <span
            className={`split-sheet__bar-fill split-sheet__tone-bg--${status.tone}`}
            style={{ width: `${splitProgress(check)}%` }}
          />
        </span>
        <span className={`split-summary__status split-sheet__tone--${status.tone}`}>
          {status.text}
        </span>
      </span>
      <ChevronRight size={16} className="split-summary__chevron" aria-hidden />
    </button>
  )
}
