import { useRef, useState } from 'react'
import { Surface } from '../../components/common/Surface'
import { Link, useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import {
  Copy,
  HelpCircle,
  LogOut,
  Server,
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
  useForgetRememberedAccounts,
  usePreviewBudgetImport,
  useRenameBudget,
  useDeleteBudget,
  type SampleTier,
  type YnabAccountPreview,
  type YnabAccountTypeChoice,
} from '../../api/budgets'
import { useImportSnapshot, type SnapshotInspection } from '../../api/budgetSnapshots'
import { useLogout } from '../../api/auth'
import { useAppStore } from '../../stores/appStore'
import { ContextMenu, type ContextMenuItem } from '../../components/common/ContextMenu/ContextMenu'
import { formatMoney } from '../../utils/money'
import { SelectorSection } from './SelectorSection'
import { RestoreSection } from './RestoreSection'
import { SETTINGS_PAGES } from '../SettingsPage/settingsSections'
import './BudgetSelectorPage.css'
import { confirmAsync } from '../../stores/confirmStore'
import { SharingModal } from '../../components/budgets/SharingModal'
import { CloneBudgetModal } from '../../components/budgets/CloneBudgetModal'
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
  seedChoices,
  type Disposition,
} from './accountMapping'
import { MappingNotes } from './MappingNotes'
import { parseLocalDate } from '../../utils/dates'

const CARD_MENU_ITEMS: ContextMenuItem[] = [
  { id: 'rename', label: 'Rename', icon: Pencil },
  { id: 'clone', label: 'Copy…', icon: Copy },
  { id: 'sharing', label: 'Sharing', icon: Users },
  { id: 'delete', label: 'Delete', icon: Trash2, danger: true },
]

/** Copying reads a whole budget out and writes a new one — the owner's
 *  decision, like deleting, and what the endpoint enforces. */
const OWNER_ONLY_ACTIONS = new Set(['clone', 'sharing', 'delete'])

// The budget (and its type registry) doesn't exist yet at mapping time, so
// the choices are the built-ins; custom types can be created after import.
const ACCOUNT_TYPE_OPTIONS = BUILTIN_ACCOUNT_TYPES

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
  const [menuBudget, setMenuBudget] = useState<{
    id: string
    name: string
    role: string | null
  } | null>(null)
  const [sharingBudget, setSharingBudget] = useState<{ id: string; name: string } | null>(null)
  const [cloningBudget, setCloningBudget] = useState<{ id: string; name: string } | null>(null)
  // One mutable ref rather than one per card: only a single menu is open at a
  // time, and the ref's identity must stay stable for the placement hook.
  const menuAnchorRef = useRef<HTMLButtonElement | null>(null)

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

  // Import form — two steps: preview (the server says which kind of file
  // this is and parses it) → import. Step 2 is either the YNAB account
  // mapping or the snapshot verdict, whichever the file turned out to be.
  const [importName, setImportName] = useState('')
  const importFileRef = useRef<HTMLInputElement>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const previewImport = usePreviewBudgetImport()
  const forgetRemembered = useForgetRememberedAccounts()
  const importSnapshot = useImportSnapshot()
  const [previewAccounts, setPreviewAccounts] = useState<YnabAccountPreview[] | null>(null)
  // B for the file being previewed — see YnabPreviewResult.anchor_month.
  const [previewAnchorMonth, setPreviewAnchorMonth] = useState<string | null>(null)
  // Rows dated after today — upcoming transactions, not register history.
  const [previewHeldOut, setPreviewHeldOut] = useState(0)
  const [snapshotPreview, setSnapshotPreview] = useState<SnapshotInspection | null>(null)
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
    await runPreview()
  }

  /** Re-read the chosen file and rebuild the mapping form from the server.
   *  Split out so forgetting the remembered choices can show the screen
   *  without them — the DELETE has committed by the time it answers, so this
   *  reads the state it just wrote. */
  async function runPreview() {
    const file = importFileRef.current?.files?.[0]
    if (!file) return
    setImportError(null)
    try {
      const preview = await previewImport.mutateAsync(file)
      if (preview.kind === 'snapshot') {
        setSnapshotPreview(preview.snapshot)
        if (!importName.trim()) setImportName(preview.snapshot.budget_name)
        return
      }
      setPreviewAccounts(preview.ynab.accounts)
      setPreviewAnchorMonth(preview.ynab.anchor_month)
      setPreviewHeldOut(preview.ynab.held_out_future_count)
      setAccountChoices(seedChoices(preview.ynab.accounts))
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setImportError(detail ?? (err instanceof Error ? err.message : 'Could not read the file'))
    }
  }

  async function handleImport(e: React.FormEvent) {
    e.preventDefault()
    const file = importFileRef.current?.files?.[0]
    if (!file) return
    setImportError(null)
    if (snapshotPreview) {
      try {
        const result = await importSnapshot.mutateAsync({
          file,
          name: importName.trim() || undefined,
        })
        setCurrentBudgetId(result.budget_id)
        navigate('/budget')
      } catch (err: unknown) {
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail
        setImportError(detail ?? (err instanceof Error ? err.message : 'Import failed'))
      }
      return
    }
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
    setPreviewAnchorMonth(null)
    setSnapshotPreview(null)
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
        <div className="budget-selector__links">
          {/* System is where server backups, restore, updates and users live —
              reachable from here because this is the page you land on when
              there is no budget left to open. */}
          <Link to={SETTINGS_PAGES.system.path} className="budget-selector__link">
            <Server size={15} />
            <span>{SETTINGS_PAGES.system.label}</span>
          </Link>
          <button className="budget-selector__link" onClick={logout} title="Sign out">
            <LogOut size={15} />
            <span>Sign out</span>
          </button>
        </div>
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
                          menuAnchorRef.current = e.currentTarget
                          setMenuBudget({ id: b.id, name: b.name, role: b.role ?? null })
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
              items={
                menuBudget.role === 'member'
                  ? CARD_MENU_ITEMS.filter((i) => !OWNER_ONLY_ACTIONS.has(i.id))
                  : CARD_MENU_ITEMS
              }
              anchor={menuAnchorRef}
              alignRight
              onClose={() => setMenuBudget(null)}
              onSelect={(id) => {
                const b = menuBudget
                setMenuBudget(null)
                if (!b) return
                if (id === 'rename') startRename(b.id, b.name)
                if (id === 'clone') setCloningBudget(b)
                if (id === 'sharing') setSharingBudget(b)
                if (id === 'delete') handleDelete(b.id, b.name)
              }}
            />
          )}
          {cloningBudget && (
            <CloneBudgetModal
              budgetId={cloningBudget.id}
              budgetName={cloningBudget.name}
              onClose={() => setCloningBudget(null)}
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

          {/* One entry point for "here is a budget file". The server reads
            the zip and says which importer it belongs to — a YNAB export,
            IGAB's YNAB-shaped export, or an IGAB snapshot — so the person
            uploading never has to know which kind of file they hold. */}
          <SelectorSection
            title="Import a Budget"
            subtitle="From a YNAB export or any file IGAB wrote — the format is detected for you"
            open={importOpen}
            onToggle={() => setImportOpen((v) => !v)}
          >
            <form
              className="selector-card__body"
              onSubmit={previewAccounts || snapshotPreview ? handleImport : handlePreview}
            >
              <div className="selector-field">
                <label className="selector-field__label">Budget name</label>
                <input
                  className="selector-field__input"
                  type="text"
                  placeholder="e.g. Household 2020 — a snapshot fills this in itself"
                  value={importName}
                  onChange={(e) => setImportName(e.target.value)}
                  required={!!previewAccounts}
                />
              </div>
              <div className="selector-field">
                <label className="selector-field__label">Budget file (.zip)</label>
                <input
                  ref={importFileRef}
                  type="file"
                  className="selector-field__input"
                  accept=".zip,.igab.zip,application/zip"
                  required
                  onChange={resetImportPreview}
                />
              </div>

              {snapshotPreview && (
                <div className="selector-field">
                  <Surface variant="sunken" className="snapshot-verdict" role="status">
                    <p className="snapshot-verdict__headline">
                      An IGAB snapshot of <strong>{snapshotPreview.budget_name}</strong>, exported{' '}
                      {new Date(snapshotPreview.exported_at).toLocaleDateString()} —{' '}
                      {(snapshotPreview.row_counts['transactions'] ?? 0).toLocaleString()}{' '}
                      transactions across {snapshotPreview.row_counts['accounts'] ?? 0} accounts.
                      Importing creates a new budget; nothing existing is touched.
                    </p>
                    {snapshotPreview.refusals.map((r) => (
                      <p key={r} className="snapshot-verdict__refusal">
                        {r}
                      </p>
                    ))}
                    {snapshotPreview.warnings.map((w) => (
                      <p key={w} className="snapshot-verdict__warning">
                        {w}
                      </p>
                    ))}
                  </Surface>
                </div>
              )}

              {previewAccounts && (
                <div className="selector-field">
                  <Surface variant="sunken" className="snapshot-verdict" role="status">
                    {previewAnchorMonth ? (
                      <p className="snapshot-verdict__headline">
                        This budget will start where YNAB left off — every envelope and card reserve
                        anchored at{' '}
                        <strong>
                          {parseLocalDate(previewAnchorMonth).toLocaleDateString(undefined, {
                            month: 'long',
                            year: 'numeric',
                          })}
                        </strong>
                        . Earlier history still imports into the register and reports. Keep YNAB
                        around until you&apos;re confident in the handoff.
                      </p>
                    ) : (
                      <p className="snapshot-verdict__headline">
                        No plan in this export — envelope history will be re-derived from the
                        transactions instead of starting from YNAB&apos;s own figures.
                      </p>
                    )}
                    {previewHeldOut > 0 && (
                      <p className="snapshot-verdict__headline">
                        {previewHeldOut.toLocaleString()} future-dated row
                        {previewHeldOut === 1 ? '' : 's'} will become upcoming transaction
                        {previewHeldOut === 1 ? '' : 's'} rather than posted ones — YNAB exports a
                        scheduled transaction as its next date only, so the import review will ask
                        how often each repeats.
                      </p>
                    )}
                  </Surface>
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
                  <MappingNotes
                    accounts={previewAccounts}
                    dormantCount={dormantCount}
                    forgetPending={forgetRemembered.isPending}
                    onForgetRemembered={async () => {
                      await forgetRemembered.mutateAsync()
                      await runPreview()
                    }}
                    onCloseDormant={closeDormantAccounts}
                  />
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
                                {a.suggestion_source === 'remembered' && !skipped && (
                                  <span
                                    className="ynab-mapping__remembered"
                                    title="Set the way you left it the last time you imported an account with this name"
                                  >
                                    Remembered
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
                  disabled={
                    previewImport.isPending ||
                    importYnab.isPending ||
                    importSnapshot.isPending ||
                    (!!previewAccounts && !importName.trim()) ||
                    (!!snapshotPreview && !snapshotPreview.ok)
                  }
                >
                  {previewAccounts || snapshotPreview
                    ? importYnab.isPending || importSnapshot.isPending
                      ? 'Importing…'
                      : 'Import Budget'
                    : previewImport.isPending
                      ? 'Reading file…'
                      : 'Review File'}
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

          {/* Last, and its own concern: this replaces every budget rather than
              adding one. See RestoreSection for why it is on this page. */}
          {me?.is_admin && <RestoreSection />}
        </div>
      </div>
      {showTypeInfo && (
        <AccountTypeInfoModal context="import" onClose={() => setShowTypeInfo(false)} />
      )}
    </div>
  )
}
