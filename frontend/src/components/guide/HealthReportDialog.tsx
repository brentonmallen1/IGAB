import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import type { CheckupFinding } from '../../api/guide'
import { findStage } from '../../content/roadmap'
import { useGuideStore } from '../../stores/guideStore'
import { useFormatters } from '../../hooks/useFormatters'
import { GuideDialog } from './GuideDialog'
import { splitFindings, stagesForFinding } from './checkupLeds'
import { findingTone } from './checkupCopy'
import { NameChips } from './NameChips'

/**
 * What the app noticed, because the user asked.
 *
 * Findings, not a dashboard: only things past a threshold appear, ranked,
 * the first few shown and the rest counted. A clean run is a real result and
 * says so. Every finding leads somewhere it can be acted on — a step, a
 * report — because a finding with no next step is just criticism.
 */
export function HealthReportDialog({
  findings,
  asOf,
  onClose,
}: {
  findings: CheckupFinding[]
  asOf: string
  onClose: () => void
}) {
  const { formatMoney, formatDate } = useFormatters()
  const setActiveTab = useGuideStore((s) => s.setActiveTab)
  const setRoadmapView = useGuideStore((s) => s.setRoadmapView)
  const openStage = useGuideStore((s) => s.openStage)
  const { shown, more } = splitFindings(findings)

  function figure(f: CheckupFinding): string | null {
    if (f.value === null) return null
    const n = Number(f.value)
    if (Number.isNaN(n)) return null
    switch (f.kind) {
      case 'ef_not_started':
        // "No emergency fund yet — $0.00" says the same thing twice.
        return null
      case 'retirement_below_target':
        return `${n.toFixed(1)}%`
      case 'chronic_overspend':
        return `${n} ${n === 1 ? 'category' : 'categories'}`
      case 'unknown_rates':
        return `${n} ${n === 1 ? 'debt' : 'debts'}`
      default:
        return formatMoney(n)
    }
  }

  function goTo(f: CheckupFinding) {
    const stageId = stagesForFinding(f)[0]
    if (!stageId) return
    setActiveTab('roadmap')
    setRoadmapView('journey')
    openStage(stageId)
    onClose()
  }

  return (
    <GuideDialog title="Health report" onClose={onClose} historyKey="guide-health-report">
      <div className="guide-dialog__body guide-report">
        <p className="guide-report__meta">
          {formatDate(asOf)} ·{' '}
          {findings.length === 0
            ? 'nothing stood out'
            : `${findings.length} ${findings.length === 1 ? 'thing' : 'things'} worth a look`}
        </p>

        {findings.length === 0 ? (
          <p className="guide-report__clean">
            Nothing stood out. Everything the roadmap measures is within its target — worth a
            look again next month.
          </p>
        ) : (
          <ol className="guide-report__list">
            {shown.map((f) => {
              const stage = stagesForFinding(f)[0]
              const stageDef = stage ? findStage(stage) : undefined
              const value = figure(f)
              const tone = findingTone(f.kind)
              return (
                <li key={`${f.kind}:${f.concept_key ?? ''}`} className="guide-report__item">
                  <span className={`guide-report__led guide-report__led--${tone}`} aria-hidden />
                  <div className="guide-report__text">
                    <p className={`guide-report__title guide-report__title--${tone}`}>
                      {f.title}
                      {value && <span className="guide-report__value tabular"> — {value}</span>}
                    </p>
                    {f.detail && <p className="guide-report__detail">{f.detail}</p>}
                    <NameChips names={f.names} limit={4} label={`${f.title}: what this counts`} />
                    <div className="guide-report__links">
                      {stageDef && (
                        <button
                          type="button"
                          className="guide-link-button"
                          onClick={() => goTo(f)}
                        >
                          Step {stageDef.step} — {stageDef.title}
                          <ArrowRight size={11} aria-hidden />
                        </button>
                      )}
                      {f.kind === 'chronic_overspend' && (
                        <Link
                          to="/reports?tab=plan-reality"
                          className="guide-link-button"
                          onClick={onClose}
                        >
                          Plan vs Reality
                        </Link>
                      )}
                      {(f.kind === 'unknown_rates' ||
                        f.kind === 'high_interest_debt' ||
                        f.kind === 'moderate_debt') && (
                        <Link to="/liabilities" className="guide-link-button" onClick={onClose}>
                          Your liabilities
                        </Link>
                      )}
                    </div>
                  </div>
                </li>
              )
            })}
          </ol>
        )}

        {more > 0 && (
          <p className="guide-report__more">
            and {more} more — the {shown.length} above are the ones that matter most.
          </p>
        )}
        {findings.length > 0 && more === 0 && (
          <p className="guide-report__more">Nothing else stood out.</p>
        )}
      </div>
    </GuideDialog>
  )
}
