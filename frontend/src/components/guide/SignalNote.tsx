import { Info } from 'lucide-react'
import type { ConceptInfo, Signal } from '../../api/guide'
import { useFormatters } from '../../hooks/useFormatters'

/**
 * What the app worked out about one concept, shown inside a roadmap node.
 *
 * Every figure carries the reason it was reached and a way to correct it. A
 * number the app cannot explain is one it should not show, and a number the
 * user cannot correct is one they will stop trusting.
 */
export function SignalNote({
  signal,
  concept,
  threshold,
  onCorrect,
}: {
  signal: Signal
  concept?: ConceptInfo
  /** The starter step reads the fund's smaller target, not the full one. */
  threshold?: 'starter'
  onCorrect: () => void
}) {
  const { formatMoney } = useFormatters()

  if (signal.source === 'off') return null

  if (!signal.tracked) {
    return (
      <div className="signal signal--muted">
        <span className="signal__text">
          You asked us not to track this{signal.note ? ` — ${signal.note}` : ''}.
        </span>
        <button type="button" className="guide-link-button" onClick={onCorrect}>
          Change
        </button>
      </div>
    )
  }

  const label = concept?.label ?? signal.key
  const kind = concept?.kind ?? 'amount'
  const fmt = (raw: string | null) => {
    if (raw === null) return null
    const n = Number(raw)
    if (Number.isNaN(n)) return null
    return kind === 'rate' ? `${n.toFixed(1)}%` : formatMoney(n)
  }

  const value = fmt(signal.value)
  const external = fmt(signal.external_value)
  const detected = fmt(signal.detected_value)
  const target = fmt(threshold === 'starter' ? signal.starter_target : signal.target)

  return (
    <div className={`signal ${signal.met === true ? 'signal--met' : ''}`}>
      <div className="signal__head">
        <span className="signal__label">{label}</span>
        {value !== null ? (
          <span className="signal__value tabular">{value}</span>
        ) : (
          <span className="signal__value signal__value--unknown">not known</span>
        )}
        {target !== null && signal.value !== null && (
          <span className="signal__target">of {target}</span>
        )}
      </div>

      {signal.reason && <p className="signal__reason">{signal.reason}</p>}

      {/* Say plainly which part of the figure the app can see and which part
          it was simply told, rather than presenting one blended number. */}
      {signal.external_declared && (
        <p className="signal__reason">
          {external !== null && detected !== null
            ? `${detected} from your budget, ${external} you told us about`
            : 'you told us this is handled outside IGAB'}
          {signal.external_as_of && ` · ${signal.external_as_of}`}
        </p>
      )}

      {signal.gaps.length > 0 && (
        <p className="signal__gap">
          No interest rate recorded for {signal.gaps.join(', ')} — add one and we will include it.
        </p>
      )}

      <button type="button" className="signal__correct" onClick={onCorrect}>
        <Info size={12} aria-hidden />
        {signal.source === 'auto' ? 'How we got this' : 'You set this'}
      </button>
    </div>
  )
}
