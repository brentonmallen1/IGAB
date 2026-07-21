import { useState } from 'react'
import { CheckCircle, AlertTriangle, ShieldCheck } from 'lucide-react'
import { apiClient } from '../../../api/client'
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
