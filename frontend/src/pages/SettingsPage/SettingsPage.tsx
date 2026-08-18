import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useAppStore, THEMES, FONT_SCALES, type Theme, type FontScale } from '../../stores/appStore'
import { useAccounts, useCreateAccount, useUpdateAccount, useDeleteAccount } from '../../api/accounts'
import { useBudgets, useUpdateBudget } from '../../api/budgets'
import {
  useSimpleFINConnections,
  useSimpleFINRateLimitStatus,
  useUpdateSimpleFINConnection,
  useDeleteSimpleFINConnection,
} from '../../api/simplefin'
import { SimpleFINSetup } from '../../components/simplefin/SimpleFINSetup'
import { AccountSettingsModal } from '../../components/accounts/AccountSettingsModal'
import { IntegrityPanel } from '../../components/settings/IntegrityPanel/IntegrityPanel'
import { BackupsPanel } from '../../components/settings/BackupsPanel/BackupsPanel'
import { UpdatesPanel } from '../../components/settings/UpdatesPanel/UpdatesPanel'
import { TagsPanel } from '../../components/settings/TagsPanel'
import { AISettingsPanel } from '../../components/settings/AISettingsPanel'
import { formatMoneyWithOptions } from '../../utils/money'
import { formatDateWithOptions, formatTimeWithOptions } from '../../utils/dates'
import { useFormatters } from '../../hooks/useFormatters'
import { useUIStore } from '../../stores/uiStore'
import type { AccountType, NumberFormat, DateFormat, TimeFormat } from '../../types'
import './SettingsPage.css'
import { confirmAsync } from '../../stores/confirmStore'

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


const ACCOUNT_TYPES: { value: AccountType; label: string }[] = [
  { value: 'checking', label: 'Checking' },
  { value: 'savings', label: 'Savings' },
  { value: 'credit_card', label: 'Credit Card' },
  { value: 'loan', label: 'Loan' },
  { value: 'tracking', label: 'Tracking' },
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
  const createAccount = useCreateAccount(budgetId ?? '')
  const updateAccount = useUpdateAccount(budgetId ?? '')
  const deleteAccount = useDeleteAccount(budgetId ?? '')
  const updateBudget = useUpdateBudget()

  const { isAccountEditorOpen, editingAccountId, openAccountEditor, closeAccountEditor } = useUIStore()


  const { data: sfConnections } = useSimpleFINConnections()
  const updateConnection = useUpdateSimpleFINConnection()
  const deleteConnection = useDeleteSimpleFINConnection()

  const firstConnectionId = sfConnections && sfConnections.length > 0 ? sfConnections[0].id : null
  const { data: rateLimitStatus } = useSimpleFINRateLimitStatus(firstConnectionId)

  async function handleDeleteAccount(id: string, name: string) {
    const ok = await confirmAsync({
      title: `Delete account "${name}"?`,
      message: 'This cannot be undone.',
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (!ok) return
    await deleteAccount.mutateAsync(id)
  }

  async function handleToggleClose(id: string, isClosed: boolean) {
    await updateAccount.mutateAsync({ id, is_closed: !isClosed })
  }

  const [newAccName, setNewAccName] = useState('')
  const [newAccType, setNewAccType] = useState<AccountType>('checking')

  async function handleAddAccount(e: React.FormEvent) {
    e.preventDefault()
    if (!newAccName.trim() || !budgetId) return
    await createAccount.mutateAsync({ name: newAccName.trim(), account_type: newAccType })
    setNewAccName('')
  }

  function handleLogout() {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    window.location.href = '/login'
  }

  const currentBudget = budgets?.find((b) => b.id === budgetId)

  // Track active section for nav highlighting
  const [activeSection, setActiveSection] = useState<string>('appearance')

  const sections = [
    { id: 'appearance', label: 'Appearance' },
    { id: 'budget', label: 'Budget' },
    ...(budgetId ? [{ id: 'tags', label: 'Tags' }] : []),
    { id: 'mobile', label: 'Mobile' },
    ...(budgetId ? [{ id: 'accounts', label: 'Accounts' }] : []),
    ...(budgetId ? [{ id: 'integrity', label: 'Data Integrity' }] : []),
    { id: 'data', label: 'Backups' },
    { id: 'updates', label: 'Updates' },
    { id: 'simplefin', label: 'SimpleFIN' },
    { id: 'ai', label: 'AI' },
    { id: 'session', label: 'Session' },
  ]

  // Deep links (e.g. /settings#integrity from the command palette) scroll to
  // their section once the page renders
  const location = useLocation()
  useEffect(() => {
    if (!location.hash) return
    const sectionId = location.hash.slice(1)
    document.getElementById(sectionId)?.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    })
    setActiveSection(sectionId)
  }, [location.hash])

  // Observe which section is in view to update nav highlighting
  useEffect(() => {
    const contentEl = document.querySelector('.settings-content')
    if (!contentEl) return

    const observer = new IntersectionObserver(
      (entries) => {
        // Find the entry with highest intersection ratio
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
        if (visible?.target.id) {
          setActiveSection(visible.target.id)
        }
      },
      { root: contentEl, rootMargin: '-20% 0px -60% 0px', threshold: [0, 0.25, 0.5, 0.75, 1] }
    )

    sections.forEach(({ id }) => {
      const el = document.getElementById(id)
      if (el) observer.observe(el)
    })

    return () => observer.disconnect()
  }, [budgetId]) // Re-run if budgetId changes (sections list changes)

  function scrollToSection(id: string) {
    const el = document.getElementById(id)
    const contentEl = document.querySelector('.settings-content')
    if (el && contentEl) {
      contentEl.scrollTo({ top: el.offsetTop - 20, behavior: 'smooth' })
      setActiveSection(id)
    }
  }

  return (
    <div className="settings-page">
      {/* Navigation sidebar */}
      <nav className="settings-nav" aria-label="Settings sections">
        {sections.map(({ id, label }) => (
          <button
            key={id}
            className={`settings-nav__link ${activeSection === id ? 'settings-nav__link--active' : ''}`}
            onClick={() => scrollToSection(id)}
          >
            {label}
          </button>
        ))}
      </nav>

      {/* Scrollable content */}
      <div className="settings-content">
      {/* Appearance */}
      <div className="settings-section" id="appearance">
        <div className="settings-section__header">
          <div className="settings-section__title">Appearance</div>
        </div>
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
      </div>

      {/* Budget */}
      <div className="settings-section" id="budget">
        <div className="settings-section__header">
          <div className="settings-section__title">Budget</div>
        </div>
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
                  {formatMoneyWithOptions(-1234.56, currentBudget.currency_code, currentBudget.number_format)}
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
              <div className="settings-row__desc">Skip the budget selector when opening the app</div>
            </div>
            <input
              type="checkbox"
              checked={autoOpenLastBudget}
              onChange={(e) => setAutoOpenLastBudget(e.target.checked)}
            />
          </div>
        </div>
      </div>

      {/* Tags */}
      {budgetId && (
        <div className="settings-section" id="tags">
          <div className="settings-section__header">
            <div className="settings-section__title">Tags</div>
          </div>
          <div className="settings-section__body">
            <TagsPanel budgetId={budgetId} />
          </div>
        </div>
      )}

      {/* Mobile — per-device settings (not synced to the server) */}
      <div className="settings-section" id="mobile">
        <div className="settings-section__header">
          <div className="settings-section__title">Mobile</div>
        </div>
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
        </div>
      </div>

      {/* Accounts */}
      {budgetId && (
        <div className="settings-section" id="accounts">
          <div className="settings-section__header">
            <div className="settings-section__title">Accounts</div>
          </div>
          <div className="settings-section__body">
            <div className="settings-account-list">
              {accounts?.map((acc) => (
                <div key={acc.id} className={`settings-account-item ${acc.is_closed ? 'settings-account-item--closed' : ''}`}>
                  <div>
                    <div className="settings-account-item__name">{acc.name}</div>
                    <div className="settings-account-item__type">
                      {acc.account_type.replace('_', ' ')}
                      {acc.simplefin_account_name ? ` · ${acc.simplefin_account_name}` : ''}
                      {acc.is_closed ? ' · closed' : ''}
                    </div>
                  </div>
                  <div className="settings-account-item__actions">
                    <span className={`settings-account-item__balance ${Number(acc.balance) < 0 ? 'negative' : ''}`}>
                      {formatMoney(Number(acc.balance))}
                    </span>
                    <button
                      className="settings-btn settings-btn--secondary"
                      onClick={() => openAccountEditor(acc.id)}
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
                      onClick={() => handleDeleteAccount(acc.id, acc.name)}
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
                  onChange={(e) => setNewAccType(e.target.value as AccountType)}
                >
                  {ACCOUNT_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </div>
              <button type="submit" className="settings-btn settings-btn--primary" style={{ alignSelf: 'flex-start' }}>
                Add Account
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Data integrity — the health check belongs next to your data, not below
          the integrations */}
      {budgetId && (
        <div className="settings-section" id="integrity">
          <div className="settings-section__header">
            <div className="settings-section__title">Data Integrity</div>
          </div>
          <div className="settings-section__body">
            <IntegrityPanel budgetId={budgetId} />
          </div>
        </div>
      )}

      {/* Backups */}
      <div className="settings-section" id="data">
        <div className="settings-section__header">
          <div className="settings-section__title">Backups</div>
        </div>
        <div className="settings-section__body">
          <BackupsPanel />
        </div>
      </div>

      {/* Updates */}
      <div className="settings-section" id="updates">
        <div className="settings-section__header">
          <div className="settings-section__title">Updates</div>
        </div>
        <div className="settings-section__body">
          <UpdatesPanel />
        </div>
      </div>

      {/* SimpleFIN */}
      <div className="settings-section" id="simplefin">
        <div className="settings-section__header">
          <div className="settings-section__title">SimpleFIN Bank Connection</div>
        </div>
        <div className="settings-section__body">
          {sfConnections && sfConnections.length > 0 ? (
            sfConnections.map((conn) => (
              <div key={conn.id} className="sf-connection">
                <div className="settings-row">
                  <div>
                    <div className="settings-row__label">Sync enabled</div>
                    <div className="settings-row__desc">
                      Last synced: {conn.last_sync_at ? new Date(conn.last_sync_at).toLocaleString() : 'Never'}
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={conn.sync_enabled}
                    onChange={(e) => updateConnection.mutate({ id: conn.id, sync_enabled: e.target.checked })}
                  />
                </div>

                <div className="settings-row">
                  <div>
                    <div className="settings-row__label">Daily auto-sync time</div>
                    <div className="settings-row__desc">Hour of day (UTC) to automatically sync</div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <select
                      className="settings-select"
                      value={conn.daily_sync_time ? String(parseInt(conn.daily_sync_time.split(':')[0], 10)) : ''}
                      onChange={(e) => {
                        const val = e.target.value
                        updateConnection.mutate({
                          id: conn.id,
                          daily_sync_time: val === '' ? null : `${val.padStart(2, '0')}:00:00`,
                        })
                      }}
                      style={{ minWidth: 130 }}
                    >
                      <option value="">Disabled</option>
                      {Array.from({ length: 24 }, (_, i) => (
                        <option key={i} value={String(i)}>
                          {String(i).padStart(2, '0')}:00 UTC
                        </option>
                      ))}
                    </select>
                    {conn.daily_sync_time && (
                      <span className="settings-row__local-time">
                        = {(() => {
                          const utcHour = parseInt(conn.daily_sync_time.split(':')[0], 10)
                          const d = new Date()
                          d.setUTCHours(utcHour, 0, 0, 0)
                          return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
                        })()} your time
                      </span>
                    )}
                  </div>
                </div>

                {rateLimitStatus && (
                  <div className="sf-usage">
                    <div className="sf-usage__row">
                      <span className="sf-usage__label">Global syncs today</span>
                      <span className="sf-usage__count">{rateLimitStatus.global_used} / 12</span>
                    </div>
                    <div className="sf-usage__bar">
                      <div
                        className="sf-usage__fill"
                        style={{ transform: `scaleX(${Math.min(1, rateLimitStatus.global_used / 12)})` }}
                      />
                    </div>
                    <div className="sf-usage__row" style={{ marginTop: 6 }}>
                      <span className="sf-usage__label">Account syncs today</span>
                      <span className="sf-usage__count">{rateLimitStatus.account_used} / 12</span>
                    </div>
                    <div className="sf-usage__bar">
                      <div
                        className="sf-usage__fill"
                        style={{ transform: `scaleX(${Math.min(1, rateLimitStatus.account_used / 12)})` }}
                      />
                    </div>
                    <div className="sf-usage__reset">Resets at midnight UTC</div>
                  </div>
                )}

                {conn.last_sync_error && (
                  <div className="sf-error">
                    <span className="sf-error__label">Last sync error</span>
                    <span className="sf-error__msg">{conn.last_sync_error}</span>
                    {conn.last_sync_error_at && (
                      <span className="sf-error__time">{new Date(conn.last_sync_error_at).toLocaleString()}</span>
                    )}
                  </div>
                )}

                <div style={{ paddingTop: 4 }}>
                  <button
                    className="settings-btn settings-btn--danger"
                    onClick={async () => {
                      const ok = await confirmAsync({
                        title: 'Remove this SimpleFIN connection?',
                        confirmLabel: 'Remove',
                        destructive: true,
                      })
                      if (ok) deleteConnection.mutate(conn.id)
                    }}
                  >
                    Remove connection
                  </button>
                </div>
              </div>
            ))
          ) : (
            <SimpleFINSetup onDone={() => {}} />
          )}
        </div>
      </div>


      {/* AI Settings */}
      <AISettingsPanel />

      {/* Session */}
      <div className="settings-section" id="session">
        <div className="settings-section__header">
          <div className="settings-section__title">Session</div>
        </div>
        <div className="settings-section__body">
          <div className="settings-row">
            <div className="settings-row__label">Sign out</div>
            <button className="settings-btn settings-btn--secondary" onClick={handleLogout}>
              Sign out
            </button>
          </div>
        </div>
      </div>

      {isAccountEditorOpen && editingAccountId && (
        <AccountSettingsModal accountId={editingAccountId} onClose={closeAccountEditor} />
      )}
      </div>
    </div>
  )
}
