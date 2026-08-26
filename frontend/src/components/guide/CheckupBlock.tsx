import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import type { CheckupFinding, CheckupMetric } from '../../api/guide'
import { findStage, type StageId } from '../../content/roadmap'
import { useFormatters } from '../../hooks/useFormatters'
import { InfoPopover } from '../common/InfoPopover/InfoPopover'
import { GlossaryChips } from './GlossaryChips'
import { NameChips } from './NameChips'
import { TOOLS } from './tools/toolRegistry'
import { stagesForFinding } from './checkupLeds'
import {
  explainerFor,
  formatMetricTarget,
  formatMetricValue,
  metricProgress,
  metricStatus,
} from './checkupCopy'

interface Props {
  metric: CheckupMetric
  /** The most severe fired finding this row is the home of, if any. */
  finding?: CheckupFinding
  thresholds: Record<string, number>
  onGoToStage: (stage: StageId) => void
}

/**
 * One checkup figure, with room to understand it.
 *
 * Left: the number against its target, a bar where a bar means something,
 * and where the number came from. Right: what it helps you decide, and the
 * places to act — the roadmap step, the calculator, the report, the terms.
 * The ⓘ carries the definition and the roadmap's reasoning.
 */
export function CheckupBlock({ metric, finding, thresholds, onGoToStage }: Props) {
  const fmt = useFormatters()
  const copy = explainerFor(metric.key)
  const fired = !!finding
  const { status, text } = metricStatus(metric, fired)
  const progress = metricProgress(metric)
  const stage: StageId | undefined = finding ? stagesForFinding(finding)[0] : copy?.stage
  const stageDef = stage ? findStage(stage) : null
  const value = formatMetricValue(metric, fmt)
  const target = formatMetricTarget(metric, fmt, thresholds)

  return (
    <article className={`checkup-block checkup-block--${status}`} aria-label={metric.label}>
      <div className="checkup-block__main">
        <header className="checkup-block__head">
          <h3 className="checkup-block__label">{metric.label}</h3>
          {copy && (
            <InfoPopover title={metric.label} label={`About ${metric.label}`}>
              <p>{copy.what}</p>
              <p>{copy.why}</p>
            </InfoPopover>
          )}
          {text && <span className={`checkup-block__status checkup-block__status--${status}`}>{text}</span>}
        </header>
        <div className="checkup-block__figure">
          <span className="checkup-block__value tabular">{value}</span>
          {target && <span className="checkup-block__target">{target}</span>}
        </div>
        {progress !== null && (
          <div
            className="checkup-block__bar"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(progress * 100)}
            aria-label={`${Math.round(progress * 100)}% of target`}
          >
            <div className="checkup-block__bar-fill" style={{ width: `${Math.round(progress * 100)}%` }} />
          </div>
        )}
        {finding && <p className="checkup-block__finding">{finding.title}</p>}
        {metric.detail && <p className="checkup-block__detail">{metric.detail}</p>}
        <NameChips
          names={metric.names.length > 0 ? metric.names : (finding?.names ?? [])}
          label={`${metric.label}: what this counts`}
        />
      </div>

      <div className="checkup-block__side">
        {copy && (
          <>
            <p className="checkup-block__side-label">Helps you decide</p>
            <ul className="checkup-block__decide">
              {copy.decide.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          </>
        )}
        <div className="checkup-block__actions">
          {stageDef && (
            <button type="button" className="guide-link-button" onClick={() => onGoToStage(stageDef.id)}>
              Step {stageDef.step} — {stageDef.title}
              <ArrowRight size={11} aria-hidden />
            </button>
          )}
          {copy?.tool && (
            <Link to={`/guide?tab=tools&tool=${copy.tool}`} className="guide-link-button">
              {TOOLS[copy.tool].linkLabel}
            </Link>
          )}
          {metric.report && (
            <Link to={`/reports?tab=${metric.report}`} className="guide-link-button">
              See the report
            </Link>
          )}
        </div>
        {copy?.glossary && copy.glossary.length > 0 && <GlossaryChips terms={copy.glossary} />}
      </div>
    </article>
  )
}
