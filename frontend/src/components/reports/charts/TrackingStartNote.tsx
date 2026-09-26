import { arrivalLine, type ArrivalMark } from '../../../utils/trackingStart'
import './TrackingStartNote.css'

interface Props {
  marks: ArrivalMark[]
  formatMoney: (n: number) => string
  formatMonthShort: (month: string) => string
}

/**
 * The key to a balance chart's arrival markers: each numbered month, what
 * began being counted in it, and each arrival by name.
 *
 * A step up on a balance chart reads as growth. When the step is an account
 * being linked with its balance, or a house first given a value, it is the
 * register filling in — and without this list the reader cannot tell which.
 * Rendered by every chart that draws `arrivalLines`, so the numbers on the
 * chart always have a key beside them.
 */
export function TrackingStartNote({ marks, formatMoney, formatMonthShort }: Props) {
  if (marks.length === 0) return null
  return (
    <section className="tracking-start-note" aria-label="When counting began">
      <h3 className="tracking-start-note__title">Started tracking</h3>
      <ol className="tracking-start-note__list">
        {marks.map((m) => (
          <li key={m.date} className="tracking-start-note__row">
            <span className="tracking-start-note__badge" aria-hidden>
              {m.label}
            </span>
            <span>
              <span className="tracking-start-note__month">{formatMonthShort(m.date)}</span>{' '}
              {m.summary}
              <span className="tracking-start-note__names">
                {' '}
                ({m.entries.map((e) => arrivalLine(e, formatMoney)).join(' · ')})
              </span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
}
