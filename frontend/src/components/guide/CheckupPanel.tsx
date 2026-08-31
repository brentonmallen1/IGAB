import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Activity } from 'lucide-react'
import { useAppStore } from '../../stores/appStore'
import { useGuideStore } from '../../stores/guideStore'
import { useGuideCheckup, useGuideOverview, useRunHealthReport } from '../../api/guide'
import type { CheckupFinding } from '../../api/guide'
import type { StageId } from '../../content/roadmap'
import { useFormatters } from '../../hooks/useFormatters'
import { Surface } from '../common/Surface'
import { CheckupBlock } from './CheckupBlock'
import { HealthReportDialog } from './HealthReportDialog'

/**
 * The Checkup tab: each metric against the target the roadmap states, and
 * the button that runs the health report.
 *
 * No composite score — a single "72/100" implies a precision nothing here can
 * support. Nothing is pushed: the markers on the roadmap and this tab are
 * things the reader glances at, and the report is something they ask for.
 */
export function CheckupPanel() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: overview } = useGuideOverview(budgetId)
  const prefs = overview?.preferences
  const enabled = !!prefs?.personalization && !!prefs?.checkup
  const { data, isLoading } = useGuideCheckup(budgetId, enabled)
  const run = useRunHealthReport(budgetId ?? '')
  const [reportOpen, setReportOpen] = useState(false)
  const { formatDateTime } = useFormatters()
  const setActiveTab = useGuideStore((s) => s.setActiveTab)
  const setRoadmapView = useGuideStore((s) => s.setRoadmapView)
  const openStage = useGuideStore((s) => s.openStage)

  function goToStage(stage: StageId) {
    setActiveTab('roadmap')
    setRoadmapView('journey')
    openStage(stage)
  }

  if (prefs && !enabled) {
    return (
      <section className="guide-checkup">
        <h2 className="guide-checkup__title">Financial checkup</h2>
        <p className="guide-checkup__lede">
          Financial health reviews are switched off for this budget. Turn them on in{' '}
          <Link to="/settings">Settings</Link> and this tab, the health report and the quiet markers
          on roadmap steps come back.
        </p>
      </section>
    )
  }

  // The most severe fired finding per kind; findings arrive ranked.
  const firedByKind = new Map<string, CheckupFinding>()
  for (const f of data?.findings ?? []) if (!firedByKind.has(f.kind)) firedByKind.set(f.kind, f)

  function runReport() {
    run.mutate(undefined, { onSuccess: () => setReportOpen(true) })
  }

  return (
    <section className="guide-checkup">
      <header className="guide-checkup__head">
        <div>
          <h2 className="guide-checkup__title">Financial checkup</h2>
          <p className="guide-checkup__lede">
            How things stand against the roadmap’s targets. Each figure says where it came from;
            none of them are added up into a score.
          </p>
        </div>
        <div className="guide-checkup__actions">
          <button
            type="button"
            className="guide-checkup__run"
            onClick={runReport}
            disabled={!budgetId || run.isPending || isLoading}
          >
            <Activity size={14} aria-hidden />
            {run.isPending ? 'Running…' : 'Run health report'}
          </button>
          <span className="guide-checkup__last">
            {data?.last_run ? `Last run ${formatDateTime(data.last_run)}` : 'Never run'}
          </span>
          {run.isError && <span className="guide-checkup__error">Couldn’t run the report</span>}
        </div>
      </header>

      {data && (
        <Surface as="div" className="guide-checkup__card">
          {data.metrics.map((m) => (
            <CheckupBlock
              key={m.key}
              metric={m}
              finding={m.finding_kinds.map((k) => firedByKind.get(k)).find(Boolean)}
              thresholds={overview?.thresholds ?? {}}
              onGoToStage={goToStage}
            />
          ))}
        </Surface>
      )}

      <p className="guide-checkup__note">
        Educational only — plain arithmetic, not advice. IGAB never sends a notification about any
        of it.
      </p>

      {reportOpen && data && (
        <HealthReportDialog
          findings={data.findings}
          asOf={data.as_of}
          onClose={() => setReportOpen(false)}
        />
      )}
    </section>
  )
}
