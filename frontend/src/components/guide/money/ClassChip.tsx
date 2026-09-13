import { activityClassTone } from '../../../utils/activityClassTone'
import './ClassChip.css'

/** A served class, drawn with the tone every other class marker uses. The
 * dot carries the colour and the label stays in body text, so the chip reads
 * in every theme without a colour of its own passing contrast. */
export function ClassChip({ cls, label }: { cls: string; label: string }) {
  return (
    <span className={`class-chip class-chip--${activityClassTone(cls)}`}>
      <span className="class-chip__dot" aria-hidden />
      {label}
    </span>
  )
}
