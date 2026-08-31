import { useRef, useState } from 'react'
import { Surface } from '../../components/common/Surface'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import {
  ChevronDown,
  ChevronUp,
  HelpCircle,
  LogOut,
  MoreHorizontal,
  Pencil,
  Trash2,
  Users,
} from 'lucide-react'
import {
  useBudgets,
  useCreateBudget,
  useCreateSampleBudget,
  useImportYnabAsBudget,
  usePreviewYnabImport,
  useRenameBudget,
  useDeleteBudget,
  type SampleTier,
  type YnabAccountPreview,
  type YnabAccountTypeChoice,
} from '../../api/budgets'
import { useLogout } from '../../api/auth'
import { useAppStore } from '../../stores/appStore'
import { ContextMenu, type ContextMenuItem } from '../../components/common/ContextMenu/ContextMenu'
import { formatMoney } from '../../utils/money'
import './BudgetSelectorPage.css'
import { confirmAsync } from '../../stores/confirmStore'
import { SharingModal } from '../../components/budgets/SharingModal'
import { useCurrentUser } from '../../api/auth'
import { BUILTIN_ACCOUNT_TYPES } from '../../constants/accountTypes'
import { AccountTypeInfoModal } from '../../components/accounts/AccountTypeInfoModal'
import {
  activityLabel,
  classificationWarning,
  choiceForDisposition,
  dispositionOf,
  dormantOpenCount,
  groupAccounts,
  isDormant,
  type Disposition,
} from './accountMapping'

const CARD_MENU_ITEMS: ContextMenuItem[] = [
  { id: 'rename', label: 'Rename', icon: Pencil },
  { id: 'sharing', label: 'Sharing', icon: Users },
  { id: 'delete', label: 'Delete', icon: Trash2, danger: true },
]

// The budget (and its type registry) doesn't exist yet at mapping time, so
// the choices are the built-ins; custom types can be created after import.
const ACCOUNT_TYPE_OPTIONS = BUILTIN_ACCOUNT_TYPES

/**
 * A selector card whose header toggles its body. The Create / Import /
 * Sample forms used to sit in a cramped second column; collapsed sections
 * under the budget list give each form the page's full width — which is what
 * makes the YNAB account-mapping rows readable.
 */
function SelectorSection({
  title,
  subtitle,
  open,
  onToggle,
  children,
  dashed = false,
}: {
  title: string
  subtitle: string
  open: boolean
  onToggle: () => void
  children: React.ReactNode
  /** Demoted affordance (the throwaway sample budget). */
  dashed?: boolean
}) {
  return (
    <Surface as="section" className="selector-card" dashed={dashed}>
      <button
        type="button"
        className="selector-card__header selector-card__header--toggle"
        onClick={onToggle}
        aria-expanded={open}
      >
        <div>
          <div className="section-label surface__title">{title}</div>
          <div className="selector-card__subtitle">{subtitle}</div>
        </div>
        {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>
      {open && children}
    </Surface>
  )
}

export function BudgetSelectorPage() {
  const navigate = useNavigate()
  const setCurrentBudgetId = useAppStore((s) => s.setCurrentBudgetId)
  const currentBudgetId = useAppStore((s) => s.currentBudgetId)
  const clearCurrentBudget = useAppStore((s) => s.clearCurrentBudget)

  const logout = useLogout()
  const { data: me } = useCurrentUser()

  const { data: budgets = [], isLoading } = useBudgets()
  const createBudget = useCreateBudget()
  const createSample = useCreateSampleBudget()
  const importYnab = useImportYnabAsBudget()
  const renameBudget = useRenameBudget()
  const deleteBudget = useDeleteBudget()
  const [sampleError, setSampleError] = useState<string | null>(null)
  const [sampleTier, setSampleTier] = useState<SampleTier>('starter')

  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [menuBudget, setMenuBudget] = useState<{ id: string; name: string } | null>(null)
  const [sharingBudget, setSharingBudget] = useState<{ id: string; name: string } | null>(null)
  const [menuPos, setMenuPos] = useState({ x: 0, y: 0 })

  // Create form
  const [createName, setCreateName] = useState('')
  const [createError, setCreateError] = useState<string | null>(null)

  // Collapsible action sections — independent, all closed by default. null =
  // "no explicit choice yet": Create auto-opens for a brand-new user with
  // zero budgets so the empty state has an obvious path.
  const [createToggled, setCreateToggled] = useState<boolean | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [sampleOpen, setSampleOpen] = useState(false)
  const createOpen = createToggled ?? (!isLoading && budgets.length === 0)

  // YNAB import form — two steps: preview (parse accounts) → mapped import
  const [importName, setImportName] = useState('')
  const importFileRef = useRef<HTMLInputElement>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const previewYnab = usePreviewYnabImport()
  const [previewAccounts, setPreviewAccounts] = useState<YnabAccountPreview[] | null>(null)
  const [accountChoices, setAccountChoices] = useState<Record<string, YnabAccountTypeChoice>>({})
  const [showTypeInfo, setShowTypeInfo] = useState(false)

  // Offered once rather than per row: a real export left 22 of 47 accounts
  // dormant, and 22 identical notes is a wall to scroll past rather than a
  // suggestion. Each row still shows when it last moved, and its own picker
  // still wins for anyone who wants only some of them closed.
  const dormantCount = dormantOpenCount(previewAccounts ?? [], accountChoices)

  function closeDormantAccounts() {
    setAccountChoices((prev) => {
      const next = { ...prev }
      for (const a of previewAccounts ?? []) {
        if (dispositionOf(next[a.name]) === 'import' && isDormant(a.last_activity)) {
          next[a.name] = { ...next[a.name], ...choiceForDisposition('close') }
        }
      }
      return next
    })
  }

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

  // The row being deleted right now — cascading over every transaction can
  // take a while on a large budget, so the row needs a visible pending state.
  const deletingId = deleteBudget.isPending ? deleteBudget.variables : null

  async function handleDelete(id: string, name: string) {
    const ok = await confirmAsync({
      title: `Delete budget "${name}"?`,
      message: 'This will permanently delete all accounts and transactions in this budget.',
      confirmLabel: 'Delete budget',
      destructive: true,
    })
    if (!ok) return
    const toastId = toast.loading(`Deleting "${name}"…`)
    try {
      await deleteBudget.mutateAsync(id)
      toast.success(`Deleted "${name}"`, { id: toastId })
      if (currentBudgetId === id) clearCurrentBudget()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail ?? 'Failed to delete budget', { id: toastId })
    }
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
      const result = await createSample.mutateAsync(sampleTier)
      setCurrentBudgetId(result.budget.id)
      navigate('/budget')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setSampleError(
        detail ?? (err instanceof Error ? err.message : 'Failed to create sample budget')
      )
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
            {
              account_type: a.suggested_type,
              on_budget: a.suggested_on_budget,
              skip: false,
              close: false,
            },
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
      // One line, and then the review. Everything this used to say — the
      // parity check against the export's own figures, which plan rows were
      // left out, which categories were given a classification-overriding tag,
      // and up to fifty per-row errors of which one was shown — went out as six
      // stacked toasts, fired while this navigated away. It is stored on the
      // budget now, and ImportReviewGate opens it on the other side.
      const r = result.import_result
      toast.success(
        `Imported ${r.transactions.toLocaleString()} transactions across ${r.accounts} accounts.`
      )
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
        {me && (
          <div className="budget-selector__whoami">Signed in as {me.display_name || me.email}</div>
        )}
        <button className="budget-selector__logout" onClick={logout} title="Sign out">
          <LogOut size={15} />
          <span>Sign out</span>
        </button>
      </div>

      <div className="budget-selector__body">
        {/* Existing budgets — the focal point */}
        <div className="budget-selector__main">
          <div className="section-label budget-selector__section-title">
            Your Budgets
            {budgets.length > 1 && <span className="budget-selector__count">{budgets.length}</span>}
          </div>
          {isLoading ? (
            <div className="budget-selector__empty">Loading…</div>
          ) : budgets.length === 0 ? (
            <div className="budget-selector__empty">
              No budgets yet — create one to get started.
            </div>
          ) : (
            <div className="budget-list">
              {budgets.map((b) =>
                renamingId === b.id ? (
                  <form
                    key={b.id}
                    className="budget-card surface budget-card--renaming"
                    onSubmit={saveRename}
                  >
                    <input
                      className="budget-card__rename-input"
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      autoFocus
                    />
                    <div className="budget-card__actions">
                      <button
                        type="submit"
                        className="budget-card__save-btn"
                        disabled={renameBudget.isPending}
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        className="budget-card__menu-btn"
                        onClick={() => setRenamingId(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                ) : (
                  <div
                    key={b.id}
                    className={`budget-card surface budget-card--clickable ${
                      b.id === deletingId ? 'budget-card--deleting' : ''
                    }`}
                    role="button"
                    tabIndex={0}
                    onClick={() => b.id !== deletingId && openBudget(b.id)}
                    onKeyDown={(e) => {
                      if ((e.key === 'Enter' || e.key === ' ') && b.id !== deletingId) {
                        e.preventDefault()
                        openBudget(b.id)
                      }
                    }}
                  >
                    <div className="budget-card__info">
                      <div className="budget-card__name">{b.name}</div>
                      <div className="budget-card__meta">{b.currency_code}</div>
                    </div>
                    {b.role === 'member' && (
                      <span className="budget-card__shared" title="Shared with you by its owner">
                        Shared
                      </span>
                    )}
                    {b.id === currentBudgetId && (
                      <span className="budget-card__current">Current</span>
                    )}
                    {b.id === deletingId ? (
                      <span className="budget-card__deleting">Deleting…</span>
                    ) : (
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
                    )}
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
                if (id === 'sharing') setSharingBudget(b)
                if (id === 'delete') handleDelete(b.id, b.name)
              }}
            />
          )}
          {sharingBudget && (
            <SharingModal
              budgetId={sharingBudget.id}
              budgetName={sharingBudget.name}
              onClose={() => setSharingBudget(null)}
            />
          )}
        </div>

        <div className="budget-selector__actions">
          <div className="section-label budget-selector__section-title">Add a Budget</div>

          {/* Create new budget */}
          <SelectorSection
            title="Create New Budget"
            subtitle="Start fresh with an empty budget"
            open={createOpen}
            onToggle={() => setCreateToggled(!createOpen)}
          >
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
          </SelectorSection>

          {/* Import from YNAB — or from IGAB's own export, which is written in
            the same shape on purpose, so this reader takes both. */}
          <SelectorSection
            title="Import from YNAB or an IGAB export"
            subtitle="Creates a new budget from an export ZIP — YNAB's, or one IGAB wrote"
            open={importOpen}
            onToggle={() => setImportOpen((v) => !v)}
          >
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
                <label className="selector-field__label">Export file (.zip)</label>
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
                  <div className="ynab-mapping__heading">
                    <span className="selector-field__label" id="ynab-accounts-label">
                      Accounts
                    </span>
                    <button
                      type="button"
                      className="ynab-mapping__type-help"
                      onClick={() => setShowTypeInfo(true)}
                    >
                      <HelpCircle size={12} /> What do these types mean?
                    </button>
                  </div>
                  <p className="ynab-mapping__guidance">
                    Uncheck an account to leave it out — its transactions don't come with it, and
                    transfers to it won't match up. Need a type that isn't listed? You can add
                    custom ones after the import.
                  </p>
                  {!previewAccounts.some((a) => a.needs_review) && (
                    <p className="ynab-mapping__note">
                      An IGAB export carries the real account types, so there is nothing to guess
                      here. A YNAB export does not, and the types below would be read from account
                      names instead.
                    </p>
                  )}
                  {previewAccounts.some((a) => a.needs_review) && (
                    <p className="ynab-mapping__review-note">
                      We couldn't tell what {previewAccounts.filter((a) => a.needs_review).length}{' '}
                      of these are from their names — they're marked <strong>Check</strong> below.
                      The balance is the clue: a large one usually means something you own (a house,
                      a car, a brokerage), which belongs <em>off</em> budget. An account left on
                      budget by mistake throws off every total.
                    </p>
                  )}
                  {dormantCount > 0 && (
                    <p className="ynab-mapping__note">
                      {dormantCount} of these {dormantCount === 1 ? 'has' : 'have'} seen no activity
                      in over a year.{' '}
                      <button
                        type="button"
                        className="ynab-mapping__note-action"
                        onClick={closeDormantAccounts}
                      >
                        Import &amp; close {dormantCount === 1 ? 'it' : 'them'}
                      </button>{' '}
                      to keep every transaction while leaving them out of your account pickers.
                    </p>
                  )}
                  <Surface
                    variant="sunken"
                    className="ynab-mapping"
                    role="group"
                    aria-labelledby="ynab-accounts-label"
                  >
                    {groupAccounts(previewAccounts).map((section) => (
                      <div key={section.label ?? `solo-${section.accounts[0].name}`}>
                        {section.label && (
                          <p className="ynab-mapping__family">
                            <span className="ynab-mapping__family-name">{section.label}</span>
                            <span className="ynab-mapping__family-hint">
                              related — often an institution's accounts, or something you own and
                              the debt against it. Compare their balances.
                            </span>
                          </p>
                        )}
                        {section.accounts.map((a) => {
                          const choice = accountChoices[a.name]
                          const disposition = dispositionOf(choice)
                          const skipped = disposition === 'skip'
                          const typeKey = choice?.account_type ?? a.suggested_type
                          const warning = skipped
                            ? null
                            : classificationWarning(
                                ACCOUNT_TYPE_OPTIONS.find((o) => o.key === a.suggested_type)
                                  ?.classification,
                                ACCOUNT_TYPE_OPTIONS.find((o) => o.key === typeKey)?.classification
                              )
                          const lastSeen = activityLabel(a.last_activity)
                          return (
                            <div
                              key={a.name}
                              className={`ynab-mapping__row ${skipped ? 'ynab-mapping__row--skipped' : ''} ${
                                a.needs_review && !skipped ? 'ynab-mapping__row--review' : ''
                              }`}
                            >
                              <select
                                className="selector-field__input ynab-mapping__disposition"
                                value={disposition}
                                onChange={(e) =>
                                  updateChoice(
                                    a.name,
                                    choiceForDisposition(e.target.value as Disposition)
                                  )
                                }
                                aria-label={`What to do with ${a.name}`}
                              >
                                <option value="import">Import</option>
                                <option value="close">Import &amp; close</option>
                                <option value="skip">Leave out</option>
                              </select>
                              <div className="ynab-mapping__name">
                                {a.name}
                                {a.needs_review && !skipped && (
                                  <span
                                    className="ynab-mapping__review"
                                    title="We couldn't identify this account from its name — confirm the type and whether it belongs on budget"
                                  >
                                    Check
                                  </span>
                                )}
                                <span className="ynab-mapping__count">
                                  {a.transaction_count} txns
                                  <span className="ynab-mapping__balance">
                                    {formatMoney(Number(a.implied_balance))}
                                  </span>
                                  {lastSeen && (
                                    <span className="ynab-mapping__activity">
                                      last activity {lastSeen}
                                    </span>
                                  )}
                                </span>
                              </div>
                              <select
                                className="selector-field__input ynab-mapping__type"
                                value={typeKey}
                                onChange={(e) => {
                                  // Picking a type resets the on-budget checkbox to
                                  // that type's default; still user-overridable.
                                  const picked = ACCOUNT_TYPE_OPTIONS.find(
                                    (o) => o.key === e.target.value
                                  )
                                  updateChoice(a.name, {
                                    account_type: e.target.value,
                                    on_budget: picked?.default_on_budget ?? true,
                                  })
                                }}
                                disabled={skipped}
                              >
                                {ACCOUNT_TYPE_OPTIONS.map((o) => (
                                  <option key={o.key} value={o.key}>
                                    {o.label}
                                  </option>
                                ))}
                              </select>
                              <label className="ynab-mapping__budget-toggle">
                                <input
                                  type="checkbox"
                                  checked={choice?.on_budget ?? a.suggested_on_budget}
                                  onChange={(e) =>
                                    updateChoice(a.name, { on_budget: e.target.checked })
                                  }
                                  disabled={skipped}
                                />
                                On budget
                              </label>
                              {warning && <p className="ynab-mapping__warn">{warning}</p>}
                            </div>
                          )
                        })}
                      </div>
                    ))}
                  </Surface>
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
          </SelectorSection>

          {/* Sample budget */}
          <SelectorSection
            title="Try a Sample Budget"
            subtitle="Explore IGAB with realistic, ready-made demo data"
            open={sampleOpen}
            onToggle={() => setSampleOpen((v) => !v)}
            dashed
          >
            <div className="selector-card__body">
              <div className="sample-tier">
                <label
                  className={`sample-tier__option ${sampleTier === 'starter' ? 'sample-tier__option--active' : ''}`}
                >
                  <input
                    type="radio"
                    name="sample-tier"
                    checked={sampleTier === 'starter'}
                    onChange={() => setSampleTier('starter')}
                  />
                  <span>
                    <strong>Quick demo</strong>
                    <small>5 accounts · about a year of history</small>
                  </span>
                </label>
                <label
                  className={`sample-tier__option ${sampleTier === 'full' ? 'sample-tier__option--active' : ''}`}
                >
                  <input
                    type="radio"
                    name="sample-tier"
                    checked={sampleTier === 'full'}
                    onChange={() => setSampleTier('full')}
                  />
                  <span>
                    <strong>Full household</strong>
                    <small>
                      16 accounts, 2½ years, thousands of transactions — mortgage, investments,
                      hidden categories, a 0%-promo loan
                    </small>
                  </span>
                </label>
              </div>
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
          </SelectorSection>
        </div>
      </div>
      {showTypeInfo && (
        <AccountTypeInfoModal context="import" onClose={() => setShowTypeInfo(false)} />
      )}
    </div>
  )
}
