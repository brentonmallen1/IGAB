import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { LogOut, MoreHorizontal, Pencil, Trash2 } from 'lucide-react'
import {
  useBudgets,
  useCreateBudget,
  useCreateSampleBudget,
  useImportYnabAsBudget,
  usePreviewYnabImport,
  useRenameBudget,
  useDeleteBudget,
  type YnabAccountPreview,
  type YnabAccountTypeChoice,
} from '../../api/budgets'
import { useLogout } from '../../api/auth'
import { useAppStore } from '../../stores/appStore'
import { ContextMenu, type ContextMenuItem } from '../../components/common/ContextMenu/ContextMenu'
import './BudgetSelectorPage.css'
import { confirmAsync } from '../../stores/confirmStore'

const CARD_MENU_ITEMS: ContextMenuItem[] = [
  { id: 'rename', label: 'Rename', icon: Pencil },
  { id: 'delete', label: 'Delete', icon: Trash2, danger: true },
]

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
  const createSample = useCreateSampleBudget()
  const importYnab = useImportYnabAsBudget()
  const renameBudget = useRenameBudget()
  const deleteBudget = useDeleteBudget()
  const [sampleError, setSampleError] = useState<string | null>(null)

  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [menuBudget, setMenuBudget] = useState<{ id: string; name: string } | null>(null)
  const [menuPos, setMenuPos] = useState({ x: 0, y: 0 })

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
    const ok = await confirmAsync({
      title: `Delete budget "${name}"?`,
      message: 'This will permanently delete all accounts and transactions in this budget.',
      confirmLabel: 'Delete budget',
      destructive: true,
    })
    if (!ok) return
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

  async function handleCreateSample() {
    setSampleError(null)
    try {
      const result = await createSample.mutateAsync()
      setCurrentBudgetId(result.budget.id)
      navigate('/budget')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setSampleError(detail ?? (err instanceof Error ? err.message : 'Failed to create sample budget'))
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
            { account_type: a.suggested_type, on_budget: a.suggested_on_budget, skip: false },
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
      const r = result.import_result
      const parts = [
        `${r.transactions.toLocaleString()} transactions`,
        `${r.accounts} accounts`,
        `${r.categories} categories`,
      ]
      if (r.assignments) parts.push(`${r.assignments.toLocaleString()} budget assignments`)
      if (r.skipped) parts.push(`${r.skipped.toLocaleString()} skipped`)
      if (r.accounts_skipped) {
        parts.push(
          `${r.accounts_skipped} account${r.accounts_skipped !== 1 ? 's' : ''} left out as requested`
        )
      }
      toast.success(`Imported ${parts.join(', ')}`, { duration: 15000 })
      if (r.errors.length > 0) {
        toast.error(
          `${r.errors.length} rows had problems — first: ${r.errors[0]}`,
          { duration: 15000 },
        )
      }
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

        {/* Existing budgets — the focal point */}
        <div className="budget-selector__main">
          <div className="section-label budget-selector__section-title">Your Budgets</div>
          {isLoading ? (
            <div className="budget-selector__empty">Loading…</div>
          ) : budgets.length === 0 ? (
            <div className="budget-selector__empty">No budgets yet — create one to get started.</div>
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
                      <button type="submit" className="budget-card__save-btn" disabled={renameBudget.isPending}>
                        Save
                      </button>
                      <button type="button" className="budget-card__menu-btn" onClick={() => setRenamingId(null)}>
                        Cancel
                      </button>
                    </div>
                  </form>
                ) : (
                  <div
                    key={b.id}
                    className="budget-card budget-card--clickable"
                    role="button"
                    tabIndex={0}
                    onClick={() => openBudget(b.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        openBudget(b.id)
                      }
                    }}
                  >
                    <div className="budget-card__info">
                      <div className="budget-card__name">{b.name}</div>
                      <div className="budget-card__meta">{b.currency_code}</div>
                    </div>
                    {b.id === currentBudgetId && (
                      <span className="budget-card__current">Current</span>
                    )}
                    <button
                      className="budget-card__menu-btn"
                      aria-label={`More actions for ${b.name}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        const rect = e.currentTarget.getBoundingClientRect()
                        setMenuPos({ x: rect.right - 140, y: rect.bottom + 4 })
                        setMenuBudget({ id: b.id, name: b.name })
                      }}
                    >
                      <MoreHorizontal size={16} />
                    </button>
                  </div>
                )
              )}
            </div>
          )}
          {menuBudget && (
            <ContextMenu
              items={CARD_MENU_ITEMS}
              position={menuPos}
              onClose={() => setMenuBudget(null)}
              onSelect={(id) => {
                const b = menuBudget
                setMenuBudget(null)
                if (!b) return
                if (id === 'rename') startRename(b.id, b.name)
                if (id === 'delete') handleDelete(b.id, b.name)
              }}
            />
          )}
        </div>

        <div className="budget-selector__aside">

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
                placeholder="e.g. Mallen 2020"
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
                  Accounts
                  <span className="ynab-mapping__hint">
                    {' '}— off-budget accounts (loans, investments) stay out of your budget
                    totals; uncheck an account to leave it and its transactions out entirely
                    (YNAB exports include archived accounts)
                  </span>
                </label>
                <div className="ynab-mapping">
                  {previewAccounts.map((a) => {
                    const skipped = accountChoices[a.name]?.skip === true
                    return (
                      <div
                        key={a.name}
                        className={`ynab-mapping__row ${skipped ? 'ynab-mapping__row--skipped' : ''}`}
                      >
                        <input
                          type="checkbox"
                          className="ynab-mapping__include"
                          checked={!skipped}
                          onChange={(e) => updateChoice(a.name, { skip: !e.target.checked })}
                          aria-label={`Import ${a.name}`}
                          title={
                            skipped
                              ? 'Excluded — this account and its transactions will not be imported'
                              : 'Uncheck to leave this account out of the import'
                          }
                        />
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
                          disabled={skipped}
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
                            disabled={skipped}
                          />
                          On budget
                        </label>
                      </div>
                    )
                  })}
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

        {/* Sample budget — always visible, secondary styling */}
        <div className="selector-card selector-card--secondary">
          <div className="selector-card__header">
            <div className="selector-card__title">Try a Sample Budget</div>
            <div className="selector-card__subtitle">
              Explore IGAB with 12 months of realistic demo data
            </div>
          </div>
          <div className="selector-card__body">
            <div className="selector-card__footer">
              <button
                type="button"
                className="selector-btn selector-btn--secondary"
                onClick={handleCreateSample}
                disabled={createSample.isPending}
              >
                {createSample.isPending ? 'Generating…' : 'Generate Sample Budget'}
              </button>
              {sampleError && (
                <div className="selector-result selector-result--error">{sampleError}</div>
              )}
            </div>
          </div>
        </div>

        </div>

      </div>
    </div>
  )
}
