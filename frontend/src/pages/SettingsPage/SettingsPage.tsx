import { useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { useAppStore, THEMES, FONT_SCALES, type Theme, type FontScale } from '../../stores/appStore'
import { MAX_FUNDING_DAY } from '../../utils/targets'
import {
  useAccounts,
  useCreateAccount,
  useUpdateAccount,
  useDeleteAccount,
} from '../../api/accounts'
import {
  fetchWishlistRetirePreview,
  useGuideOverview,
  useSetGuidePreferences,
} from '../../api/guide'
import { useLiabilities } from '../../api/liabilities'
import { confirmAccountDeletion } from '../../utils/confirmAccountDeletion'
import { useBudgets, useUpdateBudget } from '../../api/budgets'
import { AccountSettingsModal } from '../../components/accounts/AccountSettingsModal'
import { AccountTypeInfoModal } from '../../components/accounts/AccountTypeInfoModal'
import { ArrowRight, HelpCircle } from 'lucide-react'
import { IntegrityPanel } from '../../components/settings/IntegrityPanel/IntegrityPanel'
import { BudgetSnapshotsPanel } from '../../components/settings/BudgetSnapshotsPanel/BudgetSnapshotsPanel'
import { SETTINGS_PAGES, visibleSettingsSections } from './settingsSections'
import { SettingsShell } from '../../components/settings/SettingsShell/SettingsShell'
import { TagsPanel } from '../../components/settings/TagsPanel'
import { SystemTagsHelp } from '../../components/settings/TagsPanel/SystemTagsHelp'
import { ViewportPanel } from '../../components/settings/ViewportPanel/ViewportPanel'
import { ImportReviewButton } from '../../components/imports/ImportReviewDialog/ImportReviewButton'
import { formatMoneyWithOptions } from '../../utils/money'
import { formatDateWithOptions, formatTimeWithOptions } from '../../utils/dates'
import { useFormatters } from '../../hooks/useFormatters'
import { wishlistToggleOutcome } from './wishlistToggle'
import { useUIStore } from '../../stores/uiStore'
import { changePassword, useCurrentUser, useLogout } from '../../api/auth'
import { apiErrorMessage } from '../../api/client'
import { useUsers } from '../../api/users'
import type { NumberFormat, DateFormat, TimeFormat } from '../../types'
import { useAccountTypes } from '../../api/accountTypes'
import { BUILTIN_ACCOUNT_TYPES } from '../../constants/accountTypes'
import './SettingsPage.css'
import { confirmAsync } from '../../stores/confirmStore'
import { Surface } from '../../components/common/Surface'

const NUMBER_FORMATS: { value: NumberFormat; label: string; example: string }[] = [
  { value: 'comma_dot', label: 'US/UK', example: '1,234.56' },
  { value: 'dot_comma', label: 'European', example: '1.234,56' },
  { value: 'space_comma', label: 'French', example: '1 234,56' },
]

const DATE_FORMATS: { value: DateFormat; label: string; example: string }[] = [
  { value: 'mdy', label: 'US (M/D/Y)', example: 'Jan 15, 2024' },
  { value: 'dmy', label: 'European (D/M/Y)', example: '15 Jan 2024' },
  { value: 'ymd', label: 'ISO (Y-M-D)', example: '2024-01-15' },
]

const TIME_FORMATS: { value: TimeFormat; label: string; example: string }[] = [
  { value: '12h', label: '12-hour', example: '3:45 PM' },
  { value: '24h', label: '24-hour', example: '15:45' },
]

const CURRENCIES: { value: string; label: string; symbol: string }[] = [
  { value: 'USD', label: 'US Dollar', symbol: '$' },
  { value: 'EUR', label: 'Euro', symbol: '€' },
  { value: 'GBP', label: 'British Pound', symbol: '£' },
  { value: 'CAD', label: 'Canadian Dollar', symbol: 'CA$' },
  { value: 'AUD', label: 'Australian Dollar', symbol: 'A$' },
  { value: 'JPY', label: 'Japanese Yen', symbol: '¥' },
  { value: 'CHF', label: 'Swiss Franc', symbol: 'CHF' },
  { value: 'SEK', label: 'Swedish Krona', symbol: 'kr' },
  { value: 'NOK', label: 'Norwegian Krone', symbol: 'kr' },
  { value: 'DKK', label: 'Danish Krone', symbol: 'kr' },
  { value: 'PLN', label: 'Polish Zloty', symbol: 'zł' },
  { value: 'CZK', label: 'Czech Koruna', symbol: 'Kč' },
  { value: 'INR', label: 'Indian Rupee', symbol: '₹' },
  { value: 'CNY', label: 'Chinese Yuan', symbol: '¥' },
  { value: 'KRW', label: 'South Korean Won', symbol: '₩' },
  { value: 'BRL', label: 'Brazilian Real', symbol: 'R$' },
  { value: 'MXN', label: 'Mexican Peso', symbol: 'MX$' },
]

export function SettingsPage() {
  const { formatMoney } = useFormatters()
  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)
  const fontScale = useAppStore((s) => s.fontScale)
  const setFontScale = useAppStore((s) => s.setFontScale)
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const autoOpenLastBudget = useAppStore((s) => s.autoOpenLastBudget)
  const setAutoOpenLastBudget = useAppStore((s) => s.setAutoOpenLastBudget)
  const locationEnabled = useAppStore((s) => s.locationEnabled)
  const setLocationEnabled = useAppStore((s) => s.setLocationEnabled)

  const { data: budgets } = useBudgets()
  const { data: accounts } = useAccounts(budgetId)
  const { data: typeRows } = useAccountTypes(budgetId)
  const typeOptions = typeRows ?? BUILTIN_ACCOUNT_TYPES
  const createAccount = useCreateAccount(budgetId ?? '')
  const updateAccount = useUpdateAccount(budgetId ?? '')
  const deleteAccount = useDeleteAccount(budgetId ?? '')
  const { data: liabilities = [] } = useLiabilities(budgetId)
  const updateBudget = useUpdateBudget()

  const activeModal = useUIStore((s) => s.activeModal)
  const openModal = useUIStore((s) => s.openModal)
  const closeModal = useUIStore((s) => s.closeModal)

  async function handleDeleteAccount(id: string) {
    const account = accounts?.find((a) => a.id === id)
    if (!account) return
    const choice = await confirmAccountDeletion(account, liabilities)
    if (!choice.proceed) return
    try {
      await deleteAccount.mutateAsync({ accountId: id, liability: choice.liability })
    } catch (err: unknown) {
      toast.error(apiErrorMessage(err, 'Could not delete the account'))
    }
  }

  async function handleToggleClose(id: string, isClosed: boolean) {
    try {
      await updateAccount.mutateAsync({ id, is_closed: !isClosed })
    } catch (err: unknown) {
      toast.error(
        apiErrorMessage(
          err,
          isClosed ? 'Could not reopen the account' : 'Could not close the account'
        )
      )
    }
  }

  const [newAccName, setNewAccName] = useState('')
  const [newAccType, setNewAccType] = useState('checking')
  const [showTypeInfo, setShowTypeInfo] = useState(false)

  async function handleAddAccount(e: React.FormEvent) {
    e.preventDefault()
    if (!newAccName.trim() || !budgetId) return
    try {
      await createAccount.mutateAsync({ name: newAccName.trim(), account_type: newAccType })
    } catch (err: unknown) {
      // The server's message is the useful one — a name collision names the
      // problem exactly. Swallowing it left the form looking inert.
      toast.error(apiErrorMessage(err, 'Could not create the account'))
      return
    }
    setNewAccName('')
  }

  const handleLogout = useLogout()
  const { data: me } = useCurrentUser()

  const currentBudget = budgets?.find((b) => b.id === budgetId)

  const guideOverview = useGuideOverview(budgetId)
  const setGuidePrefs = useSetGuidePreferences(budgetId ?? '')
  // Both default on; the server is the source of truth once it answers.
  const guidePrefs = guideOverview.data?.preferences ?? {
    personalization: true,
    checkup: true,
    wishlist: true,
  }

  // The decision lives in `wishlistToggle.ts` so it can be tested without
  // mounting this page; what is left here is the wiring it needs.
  async function handleWishlistToggle(next: boolean) {
    if (!budgetId) return
    const outcome = await wishlistToggleOutcome(next, {
      fetchPreview: () => fetchWishlistRetirePreview(budgetId),
      confirm: confirmAsync,
      formatMoney,
      onPreviewFailed: () =>
        toast.error('Could not check what turning the wishlist off would move'),
    })
    if (outcome) setGuidePrefs.mutate(outcome)
  }

  // The list itself lives in settingsSections.ts, because the command palette
  // builds a row per section from the same array and the same gates — and
  // because it also decides which sections belong to System instead.
  const sections = visibleSettingsSections({
    budgetId,
    isAdmin: !!me?.is_admin,
    page: 'settings',
  })

  return (
    <SettingsShell
      sections={sections}
      navLabel="Settings sections"
      navFooter={
        <Link to={SETTINGS_PAGES.system.path} className="settings-nav__link">
          {SETTINGS_PAGES.system.label} settings
          <ArrowRight size={12} aria-hidden="true" />
        </Link>
      }
    >
      {/* Appearance */}
      <Surface as="section" className="settings-section" id="appearance" title="Appearance">
        <div className="settings-section__body">
          <div className="settings-row">
            <div>
              <div className="settings-row__label">Theme</div>
              <div className="settings-row__desc">Choose your color palette</div>
            </div>
            <select
              className="settings-select"
              value={theme}
              onChange={(e) => setTheme(e.target.value as Theme)}
            >
              {THEMES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
          <div className="settings-row">
            <div>
              <div className="settings-row__label">Text size</div>
              <div className="settings-row__desc">Adjust font size across the app</div>
            </div>
            <select
              className="settings-select"
              value={fontScale}
              onChange={(e) => setFontScale(e.target.value as FontScale)}
            >
              {FONT_SCALES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Surface>

      {/* Budget */}
      <Surface as="section" className="settings-section" id="budget" title="Budget">
        <div className="settings-section__body">
          {currentBudget ? (
            <>
              <div className="settings-row">
                <div>
                  <div className="settings-budget-name">{currentBudget.name}</div>
                  <div className="settings-budget-name__id">{currentBudget.id}</div>
                </div>
              </div>

              <div className="settings-subsection">
                <div className="settings-subsection__title">Targets</div>

                <div className="settings-row">
                  <div>
                    <div className="settings-row__label">Funding day</div>
                    <div className="settings-row__desc">
                      Targets show as pending until this day of the month, then as underfunded. A
                      target can set its own day.
                    </div>
                  </div>
                  <select
                    className="settings-select"
                    value={currentBudget.funding_day}
                    onChange={(e) =>
                      updateBudget.mutate({
                        id: currentBudget.id,
                        funding_day: Number(e.target.value),
                      })
                    }
                  >
                    {Array.from({ length: MAX_FUNDING_DAY }, (_, i) => i + 1).map((day) => (
                      <option key={day} value={day}>
                        {day}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="settings-subsection">
                <div className="settings-subsection__title">Display Formats</div>

                <div className="settings-row">
                  <div>
                    <div className="settings-row__label">Currency</div>
                    <div className="settings-row__desc">Symbol shown with amounts</div>
                  </div>
                  <select
                    className="settings-select"
                    value={currentBudget.currency_code}
                    onChange={(e) =>
                      updateBudget.mutate({ id: currentBudget.id, currency_code: e.target.value })
                    }
                  >
                    {CURRENCIES.map((c) => (
                      <option key={c.value} value={c.value}>
                        {c.symbol} — {c.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="settings-row">
                  <div>
                    <div className="settings-row__label">Numbers</div>
                    <div className="settings-row__desc">Thousands and decimal separators</div>
                  </div>
                  <select
                    className="settings-select"
                    value={currentBudget.number_format}
                    onChange={(e) =>
                      updateBudget.mutate({ id: currentBudget.id, number_format: e.target.value })
                    }
                  >
                    {NUMBER_FORMATS.map((f) => (
                      <option key={f.value} value={f.value}>
                        {f.example} ({f.label})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="settings-row">
                  <div>
                    <div className="settings-row__label">Dates</div>
                    <div className="settings-row__desc">Order of day, month, year</div>
                  </div>
                  <select
                    className="settings-select"
                    value={currentBudget.date_format}
                    onChange={(e) =>
                      updateBudget.mutate({ id: currentBudget.id, date_format: e.target.value })
                    }
                  >
                    {DATE_FORMATS.map((f) => (
                      <option key={f.value} value={f.value}>
                        {f.example} ({f.label})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="settings-row">
                  <div>
                    <div className="settings-row__label">Times</div>
                    <div className="settings-row__desc">12-hour or 24-hour clock</div>
                  </div>
                  <select
                    className="settings-select"
                    value={currentBudget.time_format}
                    onChange={(e) =>
                      updateBudget.mutate({ id: currentBudget.id, time_format: e.target.value })
                    }
                  >
                    {TIME_FORMATS.map((f) => (
                      <option key={f.value} value={f.value}>
                        {f.example} ({f.label})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="settings-format-preview">
                  Preview:{' '}
                  {formatMoneyWithOptions(
                    -1234.56,
                    currentBudget.currency_code,
                    currentBudget.number_format
                  )}
                  {' • '}
                  {formatDateWithOptions('2024-01-15', currentBudget.date_format)}
                  {' • '}
                  {formatTimeWithOptions(15, 45, currentBudget.time_format)}
                </div>
              </div>
            </>
          ) : null}

          <div className="settings-row">
            <div>
              <div className="settings-row__label">Auto-open last budget</div>
              <div className="settings-row__desc">
                Skip the budget selector when opening the app
              </div>
            </div>
            <input
              type="checkbox"
              checked={autoOpenLastBudget}
              onChange={(e) => setAutoOpenLastBudget(e.target.checked)}
            />
          </div>
        </div>
      </Surface>

      {/* Guide */}
      {budgetId && (
        <Surface as="section" className="settings-section" id="guide" title="Guide">
          <div className="settings-section__body">
            <div className="settings-row">
              <div>
                <div className="settings-row__label">Personalise the roadmap</div>
                <div className="settings-row__desc">
                  Use your budget to show where you are on the roadmap. Every figure it works out is
                  explained, and you can correct or switch off any of them. Turn this off and the
                  roadmap becomes plain reading — nothing is calculated at all.
                </div>
              </div>
              <input
                type="checkbox"
                checked={guidePrefs.personalization}
                disabled={setGuidePrefs.isPending}
                onChange={(e) => setGuidePrefs.mutate({ personalization: e.target.checked })}
              />
            </div>

            <div className="settings-row">
              <div>
                <div className="settings-row__label">Financial health reviews</div>
                <div className="settings-row__desc">
                  {guidePrefs.personalization
                    ? 'Show a quiet marker on any roadmap step worth a look, and offer a health report you can run when you want it. IGAB never sends you a notification about your money.'
                    : 'Unavailable while the roadmap is not personalised — health reviews are built from the same figures.'}
                </div>
              </div>
              <input
                type="checkbox"
                checked={guidePrefs.checkup}
                disabled={!guidePrefs.personalization || setGuidePrefs.isPending}
                onChange={(e) => setGuidePrefs.mutate({ checkup: e.target.checked })}
              />
            </div>

            <div className="settings-row">
              <div>
                <div className="settings-row__label">Wishlist</div>
                <div className="settings-row__desc">
                  Keep a wishlist — a Wishlist group in your budget and its own Wishlist page.
                  Turning it off archives those envelopes and returns anything saved in them to
                  Ready to Assign; it asks first, and says how much.
                </div>
              </div>
              <input
                type="checkbox"
                checked={guidePrefs.wishlist}
                disabled={setGuidePrefs.isPending}
                onChange={(e) => void handleWishlistToggle(e.target.checked)}
              />
            </div>
          </div>
        </Surface>
      )}

      {/* Tags */}
      {budgetId && (
        <Surface
          as="section"
          className="settings-section"
          id="tags"
          title={
            <span className="settings-section__title-help">
              Tags
              <SystemTagsHelp />
            </span>
          }
          actions={<ImportReviewButton budgetId={budgetId} />}
        >
          <div className="settings-section__body">
            <TagsPanel budgetId={budgetId} />
          </div>
        </Surface>
      )}

      {/* Mobile — per-device settings (not synced to the server) */}
      <Surface as="section" className="settings-section" id="mobile" title="Mobile">
        <div className="settings-section__body">
          <div className="settings-row">
            <div>
              <div className="settings-row__label">Suggest payees near me</div>
              <div className="settings-row__desc">
                Uses your location only while adding a transaction; coordinates are stored with the
                transaction on your server. Applies to this device and requires HTTPS.
              </div>
            </div>
            <input
              type="checkbox"
              checked={locationEnabled}
              onChange={(e) => setLocationEnabled(e.target.checked)}
            />
          </div>
          <ViewportPanel />
        </div>
      </Surface>

      {/* Accounts */}
      {budgetId && (
        <Surface as="section" className="settings-section" id="accounts" title="Accounts">
          <div className="settings-section__body">
            <div className="settings-account-list scroll-list surface surface--sunken">
              {accounts?.map((acc) => (
                <div
                  key={acc.id}
                  className={`settings-account-item ${acc.is_closed ? 'settings-account-item--closed' : ''}`}
                >
                  <div>
                    <div className="settings-account-item__name">{acc.name}</div>
                    <div className="settings-account-item__type">
                      {acc.account_type.replace('_', ' ')}
                      {acc.simplefin_account_name ? ` · ${acc.simplefin_account_name}` : ''}
                      {acc.is_closed ? ' · closed' : ''}
                    </div>
                  </div>
                  <div className="settings-account-item__actions">
                    <span
                      className={`settings-account-item__balance ${acc.balance < 0 ? 'negative' : ''}`}
                    >
                      {formatMoney(acc.balance)}
                    </span>
                    <button
                      className="settings-btn settings-btn--secondary"
                      onClick={() => openModal('account', acc.id)}
                    >
                      Edit
                    </button>
                    <button
                      className="settings-btn settings-btn--secondary"
                      onClick={() => handleToggleClose(acc.id, acc.is_closed ?? false)}
                    >
                      {acc.is_closed ? 'Reopen' : 'Close'}
                    </button>
                    <button
                      className="settings-btn settings-btn--danger"
                      onClick={() => handleDeleteAccount(acc.id)}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <form className="settings-add-form" onSubmit={handleAddAccount}>
              <div className="settings-add-form__row">
                <input
                  type="text"
                  className="settings-input"
                  value={newAccName}
                  onChange={(e) => setNewAccName(e.target.value)}
                  placeholder="Account name…"
                />
                <select
                  className="settings-input"
                  value={newAccType}
                  onChange={(e) => setNewAccType(e.target.value)}
                >
                  {typeOptions.map((t) => (
                    <option key={t.key} value={t.key}>
                      {t.label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="settings-btn"
                  onClick={() => setShowTypeInfo(true)}
                  aria-label="What do account types mean?"
                  title="What do account types mean?"
                >
                  <HelpCircle size={14} />
                </button>
              </div>
              <button
                type="submit"
                className="settings-btn settings-btn--primary"
                style={{ alignSelf: 'flex-start' }}
              >
                Add Account
              </button>
            </form>
          </div>
        </Surface>
      )}

      {/* Data integrity — the health check belongs next to your data, not below
          the integrations */}
      {budgetId && (
        <Surface as="section" className="settings-section" id="integrity" title="Data Integrity">
          <div className="settings-section__body">
            <IntegrityPanel budgetId={budgetId} />
          </div>
        </Surface>
      )}

      {/* This budget's own backups — a file holding one budget, which is what
          makes a per-budget list possible at all. The panel below backs up the
          whole installation and cannot be filtered down to one budget. */}
      {currentBudget && (
        <Surface
          as="section"
          className="settings-section"
          id="budget-backups"
          title="Budget Backups"
        >
          <div className="settings-section__body">
            <BudgetSnapshotsPanel budgetId={currentBudget.id} budgetName={currentBudget.name} />
          </div>
        </Surface>
      )}

      {/* Account */}
      <Surface as="section" className="settings-section" id="account" title="Account">
        <div className="settings-section__body">
          <div className="settings-row">
            <div>
              <div className="settings-row__label">Signed in as</div>
              <div className="settings-row__desc">
                {me ? (me.display_name ? `${me.display_name} — ${me.email}` : me.email) : '…'}
                {me?.is_admin ? ' (admin)' : ''}
              </div>
            </div>
          </div>
          <ChangePasswordRow />
          <div className="settings-row">
            <div className="settings-row__label">Sign out</div>
            <button className="settings-btn settings-btn--secondary" onClick={handleLogout}>
              Sign out
            </button>
          </div>
        </div>
      </Surface>

      {activeModal?.kind === 'account' && activeModal.editingId && (
        <AccountSettingsModal accountId={activeModal.editingId} onClose={closeModal} />
      )}
      {showTypeInfo && (
        <AccountTypeInfoModal
          types={typeRows}
          budgetId={budgetId}
          onClose={() => setShowTypeInfo(false)}
        />
      )}
    </SettingsShell>
  )
}

/**
 * Self-service password change. The env-managed admin gets an explanatory
 * note instead of a form — ADMIN_PASSWORD owns that credential and the boot
 * sync would silently revert an in-app change.
 */
function ChangePasswordRow() {
  const { data: me } = useCurrentUser()
  const { data: users } = useUsers()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isEnvAdmin = users?.find((u) => u.id === me?.id)?.is_env_admin ?? false

  if (isEnvAdmin) {
    return (
      <div className="settings-row">
        <div>
          <div className="settings-row__label">Password</div>
          <div className="settings-row__desc">
            This admin credential is managed by the ADMIN_PASSWORD environment variable — change it
            in .env and restart the server.
          </div>
        </div>
      </div>
    )
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (next !== confirm) {
      setError('New passwords do not match')
      return
    }
    setSaving(true)
    try {
      await changePassword(current, next)
      toast.success('Password changed')
      setCurrent('')
      setNext('')
      setConfirm('')
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'Could not change the password'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="settings-row settings-row--stacked">
      <div>
        <div className="settings-row__label">Change password</div>
      </div>
      <form className="settings-password-form" onSubmit={handleSubmit}>
        <input
          className="settings-input"
          type="password"
          placeholder="Current password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          required
          autoComplete="current-password"
        />
        <input
          className="settings-input"
          type="password"
          placeholder="New password (min 8)"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          minLength={8}
          required
          autoComplete="new-password"
        />
        <input
          className="settings-input"
          type="password"
          placeholder="Repeat new password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          minLength={8}
          required
          autoComplete="new-password"
        />
        <div className="settings-password-actions">
          {error && <span className="settings-password-error">{error}</span>}
          <button
            type="submit"
            className="settings-btn settings-btn--primary"
            disabled={saving || !current || next.length < 8 || confirm.length < 8}
          >
            {saving ? 'Saving…' : 'Change password'}
          </button>
        </div>
      </form>
    </div>
  )
}
