import { useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { CardExample } from '../../../api/guide'
import { useFormatters } from '../../../hooks/useFormatters'
import './CardWalkthrough.css'

interface Props {
  example: CardExample
}

/**
 * One card situation, a month at a time.
 *
 * Renders only — every figure is walked by the card domain and served
 * (`guide/card_examples.py`), because a walkthrough with its own arithmetic
 * would be a second home for card situations and free to drift from the one
 * the budget page serves.
 *
 * The month is the grain on purpose: it is the grain the real row answers at,
 * and it is what makes "the month ended short" legible. Steps inside a month
 * say what each one did; the figures beneath say where the card stood once the
 * month was over.
 */
export function CardWalkthrough({ example }: Props) {
  const { formatMoney } = useFormatters()
  const [at, setAt] = useState(0)
  const month = example.months[at]
  const last = example.months.length - 1

  return (
    <div className="card-walk">
      <div className="card-walk__months" role="tablist" aria-label={`Months of ${example.title}`}>
        {example.months.map((m, i) => (
          <button
            key={m.month}
            type="button"
            role="tab"
            aria-selected={i === at}
            className={`card-walk__month-tab ${i === at ? 'is-on' : ''}`}
            onClick={() => setAt(i)}
          >
            {m.label}
          </button>
        ))}
      </div>

      <ol className="card-walk__steps">
        {month.steps.length === 0 && (
          <li className="card-walk__step card-walk__step--quiet">
            Nothing happened on the card this month.
          </li>
        )}
        {month.steps.map((s, i) => (
          <li key={`${s.kind}-${i}`} className="card-walk__step">
            {s.says}
          </li>
        ))}
      </ol>

      <div className="card-walk__figures">
        <Figure label="Set aside" value={month.set_aside} money={formatMoney} />
        <Figure label="Balance" value={month.balance} money={formatMoney} />
        <Figure label="Uncovered" value={month.uncovered} money={formatMoney} />
        {month.over_reserved > 0 && (
          <Figure label="Spare" value={month.over_reserved} money={formatMoney} />
        )}
      </div>
      <p className="card-walk__at">
        Where the card stood at the end of {month.label.toLowerCase()}.
      </p>

      <div className="card-walk__nav">
        <button type="button" onClick={() => setAt((i) => Math.max(0, i - 1))} disabled={at === 0}>
          <ChevronLeft size={13} aria-hidden /> Earlier
        </button>
        <button
          type="button"
          onClick={() => setAt((i) => Math.min(last, i + 1))}
          disabled={at === last}
        >
          Later <ChevronRight size={13} aria-hidden />
        </button>
      </div>
    </div>
  )
}

function Figure({
  label,
  value,
  money,
}: {
  label: string
  value: number
  money: (n: number) => string
}) {
  return (
    <div className="card-walk__figure">
      <span className="card-walk__figure-label">{label}</span>
      <span className={`card-walk__figure-value ${value < 0 ? 'is-negative' : ''}`}>
        {money(value)}
      </span>
    </div>
  )
}
