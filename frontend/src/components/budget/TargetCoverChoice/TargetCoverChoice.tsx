import { useFormatters } from '../../../hooks/useFormatters'
import type { TargetCoverPick } from '../../../utils/targetCover'
import './TargetCoverChoice.css'

interface Props {
  /** The current pick; null reads as neither (a "same for all" control over
   *  rows that differ). */
  value: TargetCoverPick | null
  onChange: (pick: TargetCoverPick) => void
  /** Names the group for a screen reader: the category, or "All". */
  label: string
  /** The served figure each pick sets assigned to. Omitted on a "same for
   *  all" control, which has no single figure. */
  targetAmount?: number
  coverAmount?: number
  disabled?: boolean
}

/**
 * Target or Cover + target, for one envelope or for all of them. One
 * control, used by the inspector's several-selected dialog and by the Assign
 * dropdown's preview, so the two surfaces ask the question the same way.
 * The figures are served; this only shows them.
 */
export function TargetCoverChoice({
  value,
  onChange,
  label,
  targetAmount,
  coverAmount,
  disabled,
}: Props) {
  const { formatMoney } = useFormatters()
  const options: { pick: TargetCoverPick; text: string; amount?: number }[] = [
    { pick: 'target', text: 'Target', amount: targetAmount },
    { pick: 'cover', text: 'Cover + target', amount: coverAmount },
  ]
  return (
    <div className="target-cover-choice" role="radiogroup" aria-label={label}>
      {options.map(({ pick, text, amount }) => (
        <button
          key={pick}
          type="button"
          role="radio"
          aria-checked={value === pick}
          className={`target-cover-choice__option${value === pick ? ' is-selected' : ''}`}
          onClick={() => onChange(pick)}
          disabled={disabled}
        >
          <span>{text}</span>
          {amount !== undefined && (
            <span className="target-cover-choice__amount tabular">{formatMoney(amount)}</span>
          )}
        </button>
      ))}
    </div>
  )
}
