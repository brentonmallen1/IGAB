import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Activity } from 'lucide-react'
import { useAppStore } from '../../stores/appStore'
import { useGuideCheckup, useGuideOverview, useRunHealthReport } from '../../api/guide'
import type { CheckupMetric } from '../../api/guide'
import { useFormatters } from '../../hooks/useFormatters'
import { MetricCard } from '../reports/MetricCard'
import { Surface } from '../common/Surface'
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
  const { formatMoney, formatDateTime } = useFormatters()

  if (prefs && !enabled) {
    return (
      <section className="guide-checkup">
        <h2 className="guide-checkup__title">Financial checkup</h2>
        <p className="guide-checkup__lede">
          Financial health reviews are switched off for this budget. Turn them on in{' '}
          <Link to="/settings">Settings</Link> and this tab, the health report and the quiet
          markers on roadmap steps come back.
        </p>
      </section>
    )
  }

  const fired = new Set((data?.findings ?? []).map((f) => f.kind))

  function display(m: CheckupMetric): { value: string; target: string | null } {
    const fmt = (raw: string | null): string | null => {
      if (raw === null) return null
      const n = Number(raw)
      if (Number.isNaN(n)) return null
      switch (m.unit) {
        case 'money':
          return formatMoney(n)
        case 'months':
          return `${n.toFixed(1)} mo`
        case 'percent':
          return `${n.toFixed(1)}%`
        case 'count':
          return String(Math.round(n))
      }
    }
    return { value: fmt(m.value) ?? '—', target: fmt(m.target) }
  }

  function runReport() {
    run.mutate(undefined, { onSuccess: () => setReportOpen(true) })
  }

  return (
    <section className="guide-checkup">
      <header className="guide-checkup__head">
        <div>
          <h2 className="guide-checkup__title">Financial checkup</h2>
          <p className="guide-checkup__lede">
            How things stand against the roadmap’s targets. Each figure says where it came
            from; none of them are added up into a score.
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
        <Surface as="div" className="guide-checkup__card guide-checkup__grid">
          {data.metrics.map((m) => {
            const { value, target } = display(m)
            const warn = m.finding_kinds.some((k) => fired.has(k))
            return (
              <MetricCard
                key={m.key}
                label={m.label}
                value={value}
                warning={warn}
                sub={
                  <span className="guide-checkup__sub">
                    {target !== null && (
                      <span className="guide-checkup__target">
                        {m.key === 'categories_funded' ? `of ${target} with targets` : `target ${target}`}
                      </span>
                    )}
                    {m.detail && <span className="guide-checkup__detail">{m.detail}</span>}
                    {m.report && (
                      <Link to={`/reports?tab=${m.report}`} className="guide-checkup__report">
                        See the report
                      </Link>
                    )}
                  </span>
                }
              />
            )
          })}
        </Surface>
      )}

      <p className="guide-checkup__note">
        Educational only — plain arithmetic, not advice. IGAB never sends a notification
        about any of it.
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
