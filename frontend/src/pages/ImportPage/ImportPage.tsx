import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAppStore } from '../../stores/appStore'
import { useAccounts } from '../../api/accounts'
import { importCsv, type CsvImportResult } from '../../api/imports'
import { invalidateAfterImport } from '../../api/invalidateAfterImport'
import { useToastUndo } from '../../utils/toastUndo'
import './ImportPage.css'
import { Surface } from '../../components/common/Surface'

export function ImportPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const qc = useQueryClient()
  const { data: accounts = [] } = useAccounts(budgetId)
  const showUndo = useToastUndo(budgetId ?? '')

  const csvFileRef = useRef<HTMLInputElement>(null)
  const [csvAccountId, setCsvAccountId] = useState('')
  const [csvLoading, setCsvLoading] = useState(false)
  const [csvResult, setCsvResult] = useState<CsvImportResult | null>(null)
  const [csvError, setCsvError] = useState<string | null>(null)

  async function handleCsvImport(e: React.FormEvent) {
    e.preventDefault()
    const file = csvFileRef.current?.files?.[0]
    if (!file || !budgetId || !csvAccountId) return

    setCsvLoading(true)
    setCsvResult(null)
    setCsvError(null)
    try {
      const result = await importCsv(budgetId, csvAccountId, file)
      setCsvResult(result)
      if (csvFileRef.current) csvFileRef.current.value = ''
      if (result.batch_id && result.imported > 0) {
        showUndo(result.batch_id, `Imported ${result.imported} transaction${result.imported > 1 ? 's' : ''}`)
      }
      invalidateAfterImport(qc, budgetId)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Import failed'
      setCsvError(msg)
    } finally {
      setCsvLoading(false)
    }
  }

  if (!budgetId) {
    return (
      <div className="import-page">
        <p style={{ color: 'var(--text-muted)', fontSize: 'var(--font-size-sm)' }}>
          Select or create a budget before importing.
        </p>
      </div>
    )
  }

  return (
    <div className="import-page">
      <Surface
        className="import-card"
        header={
          <div>
            <span className="section-label surface__title">Import Transactions</span>
            <div className="import-card__subtitle">Import transactions from a bank export CSV file</div>
          </div>
        }
      >
        <form className="import-card__body" onSubmit={handleCsvImport}>
          <div className="import-field">
            <label className="import-field__label">Account</label>
            <select
              className="import-field__select"
              value={csvAccountId}
              onChange={(e) => setCsvAccountId(e.target.value)}
              required
            >
              <option value="">Select account…</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>
          <div className="import-field">
            <label className="import-field__label">CSV file</label>
            <input
              ref={csvFileRef}
              type="file"
              className="import-field__input"
              accept=".csv,text/csv"
              required
            />
          </div>
          <div className="import-card__footer">
            <button type="submit" className="import-btn" disabled={csvLoading}>
              {csvLoading ? 'Importing…' : 'Import CSV'}
            </button>
            {csvResult && (
              <div className="import-result import-result--success">
                Imported {csvResult.imported} transactions
                {csvResult.skipped ? `, ${csvResult.skipped} skipped` : ''}
              </div>
            )}
            {csvError && (
              <div className="import-result import-result--error">{csvError}</div>
            )}
          </div>
        </form>
      </Surface>
    </div>
  )
}
