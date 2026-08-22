import { Info } from 'lucide-react'
import type { SpendingClassExcluded } from '../../types'
import { useFormatters } from '../../hooks/useFormatters'
import './ViewHiddenNote.css'

interface Props {
  excluded: SpendingClassExcluded[]
  /** Whether the chart's "Include savings & debt payments" toggle is visible
   *  and off — the one action from here that adds the money back. */
  toggleAvailable: boolean
}

/**
 * "I selected Car Payment and it isn't here." The category is not empty — its
 * money is debt payment or savings, which a spending report deliberately
 * leaves out. Absence without this note is indistinguishable from a bug, and
 * the user has no reason to open the info panel to find out.
 */
export function ClassExcludedNote({ excluded, toggleAvailable }: Props) {
  const { formatMoney } = useFormatters()
  if (excluded.length === 0) return null

  const parts = excluded.map(
    (e) =>
      `${formatMoney(Number(e.total))} of ${e.label.toLowerCase()}s` +
      ` (${e.categories === 1 ? '1 category' : `${e.categories} categories`})`
  )

  return (
    <p className="view-hidden-note" role="note">
      <Info size={12} aria-hidden />
      <span>
        Not counted as spending here: {parts.join(' and ')}.
        {toggleAvailable && ' Tick “Include savings & debt payments” to add it.'}
      </span>
    </p>
  )
}
