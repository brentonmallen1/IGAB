import { useState } from 'react'
import { useAppStore, type Theme } from '../../stores/appStore'
import { useAccounts, useCreateAccount, useUpdateAccount, useDeleteAccount } from '../../api/accounts'
import { useBudgets } from '../../api/budgets'
import { useSettings, useUpdateSetting } from '../../api/settings'
import {
  useSimpleFINConnections,
  useSetupSimpleFIN,
  useUpdateSimpleFINInterval,
  useDeleteSimpleFINConnection,
} from '../../api/simplefin'
import { SimpleFINSetup } from '../../components/simplefin/SimpleFINSetup'
import { formatMoney } from '../../utils/money'
import type { AccountType } from '../../types'
import './SettingsPage.css'

const THEMES: { value: Theme; label: string }[] = [
  { value: 'dark', label: 'Dark' },
  { value: 'light', label: 'Light' },
  { value: 'gruvbox-dark', label: 'Gruvbox Dark' },
  { value: 'gruvbox-light', label: 'Gruvbox Light' },
  { value: 'catppuccin-mocha', label: 'Catppuccin Mocha' },
  { value: 'catppuccin-latte', label: 'Catppuccin Latte' },
  { value: 'rose-pine', label: 'Rosé Pine' },
  { value: 'rose-pine-moon', label: 'Rosé Pine Moon' },
  { value: 'nord', label: 'Nord' },
]

const ACCOUNT_TYPES: { value: AccountType; label: string }[] = [
  { value: 'checking', label: 'Checking' },
  { value: 'savings', label: 'Savings' },
  { value: 'credit_card', label: 'Credit Card' },
  { value: 'loan', label: 'Loan' },
  { value: 'tracking', label: 'Tracking' },
]

export function SettingsPage() {
  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const autoOpenLastBudget = useAppStore((s) => s.autoOpenLastBudget)
  const setAutoOpenLastBudget = useAppStore((s) => s.setAutoOpenLastBudget)

  const { data: budgets } = useBudgets()
  const { data: accounts } = useAccounts(budgetId)
  const createAccount = useCreateAccount(budgetId ?? '')
  const updateAccount = useUpdateAccount(budgetId ?? '')
  const deleteAccount = useDeleteAccount(budgetId ?? '')

  const [editingAccountId, setEditingAccountId] = useState<string | null>(null)
  const [editAccName, setEditAccName] = useState('')
  const [editAccType, setEditAccType] = useState<AccountType>('checking')

  const { data: appSettings } = useSettings()
  const updateSetting = useUpdateSetting()

  const ollamaHost = appSettings?.find((s) => s.key === 'ollama_host')?.value ?? ''
  const ollamaModel = appSettings?.find((s) => s.key === 'ollama_model')?.value ?? ''
  const [editOllamaHost, setEditOllamaHost] = useState('')
  const [editOllamaModel, setEditOllamaModel] = useState('')
  const [ollamaEditing, setOllamaEditing] = useState(false)

  function startOllamaEdit() {
    setEditOllamaHost(ollamaHost)
    setEditOllamaModel(ollamaModel)
    setOllamaEditing(true)
  }

  async function saveOllamaSettings(e: React.FormEvent) {
    e.preventDefault()
    if (editOllamaHost.trim())
      await updateSetting.mutateAsync({ key: 'ollama_host', value: editOllamaHost.trim() })
    if (editOllamaModel.trim())
      await updateSetting.mutateAsync({ key: 'ollama_model', value: editOllamaModel.trim() })
    setOllamaEditing(false)
  }

  const { data: sfConnections } = useSimpleFINConnections()
  const updateInterval = useUpdateSimpleFINInterval()
  const deleteConnection = useDeleteSimpleFINConnection()

  function startEditAccount(acc: { id: string; name: string; account_type: AccountType }) {
    setEditingAccountId(acc.id)
    setEditAccName(acc.name)
    setEditAccType(acc.account_type)
  }

  async function saveEditAccount(e: React.FormEvent) {
    e.preventDefault()
    if (!editingAccountId || !editAccName.trim()) return
    await updateAccount.mutateAsync({ id: editingAccountId, name: editAccName.trim(), account_type: editAccType })
    setEditingAccountId(null)
  }

  async function handleDeleteAccount(id: string, name: string) {
    if (!confirm(`Delete account "${name}"? This cannot be undone.`)) return
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

  return (
    <div className="settings-page">
      {/* Appearance */}
      <div className="settings-section">
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
        </div>
      </div>

      {/* Budget */}
      <div className="settings-section">
        <div className="settings-section__header">
          <div className="settings-section__title">Budget</div>
        </div>
        <div className="settings-section__body">
          {currentBudget ? (
            <div className="settings-row">
              <div>
                <div className="settings-budget-name">{currentBudget.name}</div>
                <div className="settings-budget-name__id">{currentBudget.id}</div>
              </div>
            </div>
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

      {/* Accounts */}
      {budgetId && (
        <div className="settings-section">
          <div className="settings-section__header">
            <div className="settings-section__title">Accounts</div>
          </div>
          <div className="settings-section__body">
            <div className="settings-account-list">
              {accounts?.map((acc) =>
                editingAccountId === acc.id ? (
                  <form key={acc.id} className="settings-account-edit" onSubmit={saveEditAccount}>
                    <input
                      className="settings-input"
                      value={editAccName}
                      onChange={(e) => setEditAccName(e.target.value)}
                      autoFocus
                    />
                    <select
                      className="settings-input"
                      value={editAccType}
                      onChange={(e) => setEditAccType(e.target.value as AccountType)}
                    >
                      {ACCOUNT_TYPES.map((t) => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </select>
                    <button type="submit" className="settings-btn settings-btn--primary">Save</button>
                    <button type="button" className="settings-btn settings-btn--secondary" onClick={() => setEditingAccountId(null)}>Cancel</button>
                  </form>
                ) : (
                  <div key={acc.id} className={`settings-account-item ${acc.is_closed ? 'settings-account-item--closed' : ''}`}>
                    <div>
                      <div className="settings-account-item__name">{acc.name}</div>
                      <div className="settings-account-item__type">
                        {acc.account_type.replace('_', ' ')}
                        {acc.is_closed ? ' · closed' : ''}
                      </div>
                    </div>
                    <div className="settings-account-item__actions">
                      <span className={`settings-account-item__balance ${Number(acc.balance) < 0 ? 'negative' : ''}`}>
                        {formatMoney(Number(acc.balance))}
                      </span>
                      <button
                        className="settings-btn settings-btn--secondary"
                        onClick={() => startEditAccount(acc)}
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
                )
              )}
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

      {/* SimpleFIN */}
      <div className="settings-section">
        <div className="settings-section__header">
          <div className="settings-section__title">SimpleFIN Bank Connection</div>
        </div>
        <div className="settings-section__body">
          {sfConnections && sfConnections.length > 0 ? (
            sfConnections.map((conn) => (
              <div key={conn.id} className="settings-row" style={{ flexWrap: 'wrap', gap: '8px' }}>
                <div>
                  <div className="settings-row__label">Connection</div>
                  <div className="settings-row__desc">
                    Last synced: {conn.last_sync_at ? new Date(conn.last_sync_at).toLocaleString() : 'Never'}
                    {' · '}Requests today: {conn.requests_today}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <select
                    className="settings-select"
                    value={conn.sync_interval_hours}
                    onChange={(e) =>
                      updateInterval.mutate({ id: conn.id, sync_interval_hours: Number(e.target.value) })
                    }
                  >
                    {[1, 4, 8, 12, 24, 48].map((h) => (
                      <option key={h} value={h}>{h}h interval</option>
                    ))}
                  </select>
                  <button
                    className="settings-btn settings-btn--secondary"
                    onClick={() => {
                      if (confirm('Remove this SimpleFIN connection?')) deleteConnection.mutate(conn.id)
                    }}
                  >
                    Remove
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
      <div className="settings-section">
        <div className="settings-section__header">
          <div className="settings-section__title">AI (Ollama)</div>
        </div>
        <div className="settings-section__body">
          {!ollamaEditing ? (
            <>
              <div className="settings-row">
                <div>
                  <div className="settings-row__label">Host</div>
                  <div className="settings-row__desc">{ollamaHost || '—'}</div>
                </div>
              </div>
              <div className="settings-row">
                <div>
                  <div className="settings-row__label">Model</div>
                  <div className="settings-row__desc">{ollamaModel || '—'}</div>
                </div>
              </div>
              <button className="settings-btn settings-btn--secondary" onClick={startOllamaEdit}>
                Edit
              </button>
            </>
          ) : (
            <form onSubmit={saveOllamaSettings} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div className="settings-row">
                <div className="settings-row__label">Host</div>
                <input
                  type="text"
                  className="settings-input"
                  value={editOllamaHost}
                  onChange={(e) => setEditOllamaHost(e.target.value)}
                  placeholder="http://localhost:11434"
                />
              </div>
              <div className="settings-row">
                <div className="settings-row__label">Model</div>
                <input
                  type="text"
                  className="settings-input"
                  value={editOllamaModel}
                  onChange={(e) => setEditOllamaModel(e.target.value)}
                  placeholder="llama3.2"
                />
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button type="submit" className="settings-btn settings-btn--primary">Save</button>
                <button type="button" className="settings-btn settings-btn--secondary" onClick={() => setOllamaEditing(false)}>Cancel</button>
              </div>
            </form>
          )}
        </div>
      </div>

      {/* Session */}
      <div className="settings-section">
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
    </div>
  )
}
