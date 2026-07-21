import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LogOut } from 'lucide-react'
import {
  useBudgets,
  useCreateBudget,
  useImportYnabAsBudget,
  usePreviewYnabImport,
  useRenameBudget,
  useDeleteBudget,
  type YnabAccountPreview,
  type YnabAccountTypeChoice,
} from '../../api/budgets'
import { useLogout } from '../../api/auth'
import { useAppStore } from '../../stores/appStore'
import './BudgetSelectorPage.css'

const ACCOUNT_TYPE_OPTIONS = [
  { value: 'checking', label: 'Checking' },
  { value: 'savings', label: 'Savings' },
  { value: 'credit_card', label: 'Credit Card' },
  { value: 'loan', label: 'Loan' },
  { value: 'tracking', label: 'Tracking' },
]

export function BudgetSelectorPage() {
  const navigate = useNavigate()
  const setCurrentBudgetId = useAppStore((s) => s.setCurrentBudgetId)
  const currentBudgetId = useAppStore((s) => s.currentBudgetId)
  const clearCurrentBudget = useAppStore((s) => s.clearCurrentBudget)

  const logout = useLogout()

  const { data: budgets = [], isLoading } = useBudgets()
  const createBudget = useCreateBudget()
  const importYnab = useImportYnabAsBudget()
  const renameBudget = useRenameBudget()
  const deleteBudget = useDeleteBudget()

  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')

  // Create form
  const [createName, setCreateName] = useState('')
  const [createError, setCreateError] = useState<string | null>(null)

  // YNAB import form — two steps: preview (parse accounts) → mapped import
  const [importName, setImportName] = useState('')
  const importFileRef = useRef<HTMLInputElement>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const previewYnab = usePreviewYnabImport()
  const [previewAccounts, setPreviewAccounts] = useState<YnabAccountPreview[] | null>(null)
  const [accountChoices, setAccountChoices] = useState<Record<string, YnabAccountTypeChoice>>({})

  function updateChoice(name: string, patch: Partial<YnabAccountTypeChoice>) {
    setAccountChoices((prev) => ({ ...prev, [name]: { ...prev[name], ...patch } }))
  }

  function openBudget(id: string) {
    setCurrentBudgetId(id)
    navigate('/budget')
  }

  function startRename(id: string, name: string) {
    setRenamingId(id)
    setRenameValue(name)
  }

  async function saveRename(e: React.FormEvent) {
    e.preventDefault()
    if (!renamingId || !renameValue.trim()) return
    await renameBudget.mutateAsync({ id: renamingId, name: renameValue.trim() })
    setRenamingId(null)
  }

  async function handleDelete(id: string, name: string) {
    if (!confirm(`Delete budget "${name}"? This will permanently delete all accounts and transactions in this budget.`)) return
    await deleteBudget.mutateAsync(id)
    if (currentBudgetId === id) clearCurrentBudget()
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setCreateError(null)
    try {
      const budget = await createBudget.mutateAsync({ name: createName.trim() })
      setCurrentBudgetId(budget.id)
      navigate('/budget')
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create budget')
    }
  }

  async function handlePreview(e: React.FormEvent) {
    e.preventDefault()
    const file = importFileRef.current?.files?.[0]
    if (!file) return
    setImportError(null)
    try {
      const preview = await previewYnab.mutateAsync(file)
      setPreviewAccounts(preview.accounts)
      setAccountChoices(
        Object.fromEntries(
          preview.accounts.map((a) => [
            a.name,
            { account_type: a.suggested_type, on_budget: a.suggested_on_budget },
          ])
        )
      )
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setImportError(detail ?? (err instanceof Error ? err.message : 'Could not read the export'))
    }
  }

  async function handleImport(e: React.FormEvent) {
    e.preventDefault()
    const file = importFileRef.current?.files?.[0]
    if (!file) return
    setImportError(null)
    try {
      const result = await importYnab.mutateAsync({
        name: importName.trim(),
        file,
        accountTypes: accountChoices,
      })
      setCurrentBudgetId(result.budget.id)
      navigate('/budget')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setImportError(detail ?? (err instanceof Error ? err.message : 'Import failed'))
    }
  }

  function resetImportPreview() {
    setPreviewAccounts(null)
    setAccountChoices({})
    setImportError(null)
  }

  return (
    <div className="budget-selector">
      <div className="budget-selector__header">
        <div className="budget-selector__logo">IGAB</div>
        <div className="budget-selector__tagline">I've Got A Budget</div>
        <button className="budget-selector__logout" onClick={logout} title="Sign out">
          <LogOut size={15} />
          <span>Sign out</span>
        </button>
      </div>

      <div className="budget-selector__body">

        {/* Existing budgets */}
        <div>
          <div className="budget-selector__section-title">Your Budgets</div>
          {isLoading ? (
            <div className="budget-selector__empty">Loading…</div>
          ) : budgets.length === 0 ? (
            <div className="budget-selector__empty">No budgets yet — create one below.</div>
          ) : (
            <div className="budget-list">
              {budgets.map((b) =>
                renamingId === b.id ? (
                  <form key={b.id} className="budget-card budget-card--renaming" onSubmit={saveRename}>
                    <input
                      className="budget-card__rename-input"
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      autoFocus
                    />
                    <div className="budget-card__actions">
                      <button type="submit" className="budget-card__open-btn" disabled={renameBudget.isPending}>
                        Save
                      </button>
                      <button type="button" className="budget-card__action-btn" onClick={() => setRenamingId(null)}>
                        Cancel
                      </button>
                    </div>
                  </form>
                ) : (
                  <div key={b.id} className="budget-card">
                    <div>
                      <div className="budget-card__name">{b.name}</div>
                      <div className="budget-card__meta">{b.currency_code}</div>
                    </div>
                    <div className="budget-card__actions">
                      <button className="budget-card__open-btn" onClick={() => openBudget(b.id)}>
                        Open
                      </button>
                      <button className="budget-card__action-btn" onClick={() => startRename(b.id, b.name)}>
                        Rename
                      </button>
                      <button className="budget-card__action-btn budget-card__action-btn--danger" onClick={() => handleDelete(b.id, b.name)}>
                        Delete
                      </button>
                    </div>
                  </div>
                )
              )}
            </div>
          )}
        </div>

        {/* Create new budget */}
        <div className="selector-card">
          <div className="selector-card__header">
            <div className="selector-card__title">Create New Budget</div>
            <div className="selector-card__subtitle">Start fresh with an empty budget</div>
          </div>
          <form className="selector-card__body" onSubmit={handleCreate}>
            <div className="selector-field">
              <label className="selector-field__label">Budget name</label>
              <input
                className="selector-field__input"
                type="text"
                placeholder="e.g. My Budget 2026"
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                required
              />
            </div>
            <div className="selector-card__footer">
              <button
                type="submit"
                className="selector-btn"
                disabled={createBudget.isPending || !createName.trim()}
              >
                {createBudget.isPending ? 'Creating…' : 'Create Budget'}
              </button>
              {createError && (
                <div className="selector-result selector-result--error">{createError}</div>
              )}
            </div>
          </form>
        </div>

        {/* Import from YNAB */}
        <div className="selector-card">
          <div className="selector-card__header">
            <div className="selector-card__title">Import from YNAB</div>
            <div className="selector-card__subtitle">
              Migrate an existing YNAB budget — creates a new budget from your export ZIP
            </div>
          </div>
          <form
            className="selector-card__body"
            onSubmit={previewAccounts ? handleImport : handlePreview}
          >
            <div className="selector-field">
              <label className="selector-field__label">Budget name</label>
              <input
                className="selector-field__input"
                type="text"
                placeholder="e.g. Household 2020"
                value={importName}
                onChange={(e) => setImportName(e.target.value)}
                required
              />
            </div>
            <div className="selector-field">
              <label className="selector-field__label">YNAB export file (.zip)</label>
              <input
                ref={importFileRef}
                type="file"
                className="selector-field__input"
                accept=".zip,application/zip"
                required
                onChange={resetImportPreview}
              />
            </div>

            {previewAccounts && (
              <div className="selector-field">
                <label className="selector-field__label">
                  Account types
                  <span className="ynab-mapping__hint">
                    {' '}— off-budget accounts (loans, investments) stay out of your budget totals
                  </span>
                </label>
                <div className="ynab-mapping">
                  {previewAccounts.map((a) => (
                    <div key={a.name} className="ynab-mapping__row">
                      <div className="ynab-mapping__name">
                        {a.name}
                        <span className="ynab-mapping__count">
                          {a.transaction_count} txns
                        </span>
                      </div>
                      <select
                        className="selector-field__input ynab-mapping__type"
                        value={accountChoices[a.name]?.account_type ?? a.suggested_type}
                        onChange={(e) => updateChoice(a.name, { account_type: e.target.value })}
                      >
                        {ACCOUNT_TYPE_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                      <label className="ynab-mapping__budget-toggle">
                        <input
                          type="checkbox"
                          checked={accountChoices[a.name]?.on_budget ?? a.suggested_on_budget}
                          onChange={(e) => updateChoice(a.name, { on_budget: e.target.checked })}
                        />
                        On budget
                      </label>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="selector-card__footer">
              <button
                type="submit"
                className="selector-btn"
                disabled={previewYnab.isPending || importYnab.isPending || !importName.trim()}
              >
                {previewAccounts
                  ? importYnab.isPending
                    ? 'Importing…'
                    : 'Import Budget'
                  : previewYnab.isPending
                    ? 'Reading export…'
                    : 'Review Accounts'}
              </button>
              {importError && (
                <div className="selector-result selector-result--error">{importError}</div>
              )}
            </div>
          </form>
        </div>

      </div>
    </div>
  )
}
