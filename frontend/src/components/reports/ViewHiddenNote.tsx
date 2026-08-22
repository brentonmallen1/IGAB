import { EyeOff } from 'lucide-react'
import { useFormatters } from '../../hooks/useFormatters'
import './ViewHiddenNote.css'

interface Props {
  categories: number
  /** Decimal over the wire — may arrive as a string. */
  total: number | string
}

/**
 * Stated on the chart face, not in the info panel: when the active view hides
 * categories, the report shrinks and nothing else says why. A budget that
 * "loses" thirty categories of spending without a word reads as data loss,
 * however deliberate the view's arrangement is.
 */
export function ViewHiddenNote({ categories, total }: Props) {
  const { formatMoney } = useFormatters()
  if (categories <= 0) return null
  return (
    <p className="view-hidden-note" role="note">
      <EyeOff size={12} aria-hidden />
      <span>
        This view hides {categories === 1 ? '1 category' : `${categories} categories`} with{' '}
        {formatMoney(Number(total))} of spending in this window — edit the view or switch it
        off to see everything.
      </span>
    </p>
  )
}
