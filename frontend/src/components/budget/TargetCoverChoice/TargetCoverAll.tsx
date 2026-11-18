import { sharedPick } from '../../../utils/targetCover'
import { TargetCoverChoice } from './TargetCoverChoice'
import './TargetCoverChoice.css'

interface Props {
  /** Every envelope offered the choice. */
  offered: readonly string[]
  /** Those currently on Cover + target. */
  coverIds: ReadonlySet<string>
  /** The new set: all of `offered`, or none. */
  onChange: (coverIds: Set<string>) => void
  /** The words beside the control. */
  caption: string
  disabled?: boolean
}

/**
 * "Same for all": one Target / Cover + target control over every offered
 * envelope, reading neither when the rows differ. The inspector's dialog and
 * the Assign preview both put one above their rows; it renders nothing for
 * fewer than two, where a row's own control already says it.
 */
export function TargetCoverAll({ offered, coverIds, onChange, caption, disabled }: Props) {
  if (offered.length < 2) return null
  return (
    <div className="target-cover-all">
      <span className="target-cover-all__caption">{caption}</span>
      <TargetCoverChoice
        value={sharedPick(offered, coverIds)}
        label={`${caption}: same for all`}
        onChange={(pick) => onChange(new Set(pick === 'cover' ? offered : []))}
        disabled={disabled}
      />
    </div>
  )
}
