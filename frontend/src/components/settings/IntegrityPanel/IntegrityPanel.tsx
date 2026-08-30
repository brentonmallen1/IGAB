import { useState } from 'react'
import toast from 'react-hot-toast'
import { CheckCircle, AlertTriangle, ShieldCheck, Wrench } from 'lucide-react'
import { apiClient } from '../../../api/client'
import { useRepairOrphanedCategories } from '../../../api/categories'
import { useAppStore } from '../../../stores/appStore'
import { useFormatters } from '../../../hooks/useFormatters'
import { parseApiDecimal } from '../../../utils/money'
import './IntegrityPanel.css'

interface IntegrityCheck {
  name: string
  description: string
  passed: boolean
  problem_count: number
  details: string[]
}

interface IntegrityReport {
  all_passed: boolean
  checks: IntegrityCheck[]
}

interface Props {
  budgetId: string
}

export function IntegrityPanel({ budgetId }: Props) {
  const [report, setReport] = useState<IntegrityReport | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const month = useAppStore((s) => s.selectedMonth)
  const { formatMoney } = useFormatters()
  const repairOrphans = useRepairOrphanedCategories(budgetId, month)

  /**
   * Finish the job on categories deleted before deleting was a real operation.
   *
   * An action rather than a migration, deliberately: it returns money stranded
   * on a deleted category to Ready to Assign, and a change to the user's
   * numbers belongs somewhere they can watch it happen — which is here, in
   * front of the check that just told them about it.
   */
  async function repair() {
    let result
    try {
      result = await repairOrphans.mutateAsync()
    } catch {
      return // the mutation's onError toast has already said so
    }
    const released = parseApiDecimal(result.released)
    const parts = [`${result.categories_repaired} categories tidied`]
    if (result.transactions_uncategorized > 0) {
      parts.push(`${result.transactions_uncategorized} transactions now need a category`)
    }
    if (released !== 0) parts.push(`${formatMoney(released)} back in Ready to Assign`)
    // "Restores": undoing a repair from Activity brings the category back to
    // the budget, live — pinned server-side; re-orphaning would recreate the
    // stranded money the repair just fixed.
    if (result.categories_repaired > 0) {
      parts.push('undo from Activity restores a category to your budget')
    }
    toast.success(parts.join(' · '))
    if (result.categories_under_deleted_groups > 0) {
      // Not repairable from here: restoring the group and deleting the
      // categories deliberately are both defensible, and this has no basis
      // for choosing between them.
      toast(
        `${result.categories_under_deleted_groups} categories sit under a deleted group — ` +
          'they still hold money but the budget page cannot draw them. Restore the group from ' +
          'Activity to get at them.',
        { duration: 9000 }
      )
    }
    await runChecks()
  }

  async function runChecks() {
    setRunning(true)
    setError(null)
    try {
      const { data } = await apiClient.get<IntegrityReport>(`/budgets/${budgetId}/integrity`)
      setReport(data)
    } catch {
      setError('Could not run the integrity checks. Is the server reachable?')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="integrity-panel">
      <div className="integrity-panel__intro">
        <p>
          Verifies the financial invariants against your live data: splits sum
          to their totals, transfer pairs balance to zero, account balances and
          category activity see the same money, and no stale bank authorizations
          or orphaned review matches linger.
        </p>
        <button
          className="integrity-panel__run-btn"
          onClick={runChecks}
          disabled={running}
        >
          <ShieldCheck size={14} />
          {running ? 'Checking…' : 'Run integrity check'}
        </button>
      </div>

      {error && <div className="integrity-panel__error">{error}</div>}

      {report && (
        <div className="integrity-panel__results">
          <div
            className={`integrity-panel__verdict ${
              report.all_passed
                ? 'integrity-panel__verdict--pass'
                : 'integrity-panel__verdict--fail'
            }`}
          >
            {report.all_passed
              ? 'All checks passed — your ledger is internally consistent.'
              : 'Problems found — details below.'}
          </div>
          <ul className="integrity-panel__checks">
            {report.checks.map((check) => (
              <li key={check.name} className="integrity-panel__check">
                <span
                  className={`integrity-panel__check-icon ${
                    check.passed
                      ? 'integrity-panel__check-icon--pass'
                      : 'integrity-panel__check-icon--fail'
                  }`}
                >
                  {check.passed ? <CheckCircle size={14} /> : <AlertTriangle size={14} />}
                </span>
                <div className="integrity-panel__check-body">
                  <span className="integrity-panel__check-desc">{check.description}</span>
                  {!check.passed && (
                    <>
                      <span className="integrity-panel__check-count">
                        {check.problem_count} problem{check.problem_count === 1 ? '' : 's'}
                      </span>
                      <ul className="integrity-panel__details">
                        {check.details.map((d, i) => (
                          <li key={i}>{d}</li>
                        ))}
                      </ul>
                      {check.name === 'orphaned_categories' && (
                        <button
                          type="button"
                          className="integrity-panel__fix-btn"
                          onClick={repair}
                          disabled={repairOrphans.isPending}
                        >
                          <Wrench size={13} />
                          {repairOrphans.isPending ? 'Tidying…' : 'Tidy these up'}
                        </button>
                      )}
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
