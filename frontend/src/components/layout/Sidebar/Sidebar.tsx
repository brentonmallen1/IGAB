import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { UserCircle2, LayoutDashboard, List, Wallet, Settings, Upload, BarChart2, CalendarClock, Users, ChevronLeft, PanelLeftClose, PanelLeftOpen, LogOut, Plus, Link2, PenLine, Sparkles, History, Compass } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAccounts } from '../../../api/accounts'
import { useAccountTypes } from '../../../api/accountTypes'
import { accountTypeLabel } from '../../../constants/accountTypes'
import {
  assetsTotal as sumAssets,
  buildLiabilityRows,
  liabilityHeaderTotal,
  orderedOnBudgetKeys,
  partitionAccounts,
} from './sidebarGroups'
import { useBudgets } from '../../../api/budgets'
import { useLiabilities } from '../../../api/liabilities'
import { useSimpleFINConnections, useSyncSimpleFIN, useSimpleFINRateLimitStatus } from '../../../api/simplefin'
import { useUpdateStatus } from '../../../api/system'
import { SyncStatusIcon } from '../../simplefin/SyncStatusIcon'
import { AddAccountModal } from '../../accounts/AddAccountModal'
import { useCurrentUser, useLogout } from '../../../api/auth'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { useFormatters } from '../../../hooks/useFormatters'
import type { Account } from '../../../types'
import './Sidebar.css'

// Group headers pluralize the built-in labels; custom types fall back to the
// registry-aware label helper.
function groupLabel(type: string, registry?: { key: string; label: string }[]): string {
  switch (type) {
    case 'checking': return 'Checking'
    case 'savings': return 'Savings'
    case 'cash': return 'Cash'
    case 'credit_card': return 'Credit Cards'
    case 'mortgage': return 'Mortgages'
    case 'auto_loan': return 'Auto Loans'
    case 'student_loan': return 'Student Loans'
    case 'loan': return 'Loans'
    case 'investment': return 'Investments'
    case 'other_asset': return 'Other Assets'
    case 'other_liability': return 'Other Liabilities'
    case 'tracking': return 'Tracking'
    default: return accountTypeLabel(type, registry)
  }
}



export function Sidebar() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const clearCurrentBudget = useAppStore((s) => s.clearCurrentBudget)
  const setSelectedAccount = useAppStore((s) => s.setSelectedAccountId)
  const navigate = useNavigate()
  const { formatMoney } = useFormatters()
  const { data: accounts } = useAccounts(budgetId)
  const { data: typeRows } = useAccountTypes(budgetId)
  const { data: budgets = [] } = useBudgets()
  const { data: liabilities = [] } = useLiabilities(budgetId)
  const updateAvailable = useUpdateStatus().data?.update_available === true
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed)
  const toggleSidebarCollapsed = useUIStore((s) => s.toggleSidebarCollapsed)
  const activeModal = useUIStore((s) => s.activeModal)
  const openModal = useUIStore((s) => s.openModal)
  const closeModal = useUIStore((s) => s.closeModal)

  const logout = useLogout()
  const { data: me } = useCurrentUser()
  // Assets "+" opens the add-account modal preset to an off-budget investment
  const [assetModalOpen, setAssetModalOpen] = useState(false)

  const { data: connections = [] } = useSimpleFINConnections()
  const primaryConnection = connections[0] ?? null
  const { data: rateLimitStatus } = useSimpleFINRateLimitStatus(primaryConnection?.id ?? null)
  const syncMutation = useSyncSimpleFIN(budgetId)
  const syncingAccountId = syncMutation.isPending ? (syncMutation.variables as { accountSimplefinId?: string })?.accountSimplefinId : undefined

  function handleAccountSync(account: Account, e: React.MouseEvent) {
    e.stopPropagation()
    if (!primaryConnection || !budgetId || !account.simplefin_account_id || syncMutation.isPending) return
    if (rateLimitStatus && !rateLimitStatus.can_sync_account) {
      toast.error('Daily sync limit reached. Resets at midnight UTC.')
      return
    }
    syncMutation.mutate(
      { connectionId: primaryConnection.id, accountSimplefinId: account.simplefin_account_id },
      {
        onSuccess: (result) => {
          if (result.error) {
            toast.error(result.error)
          } else {
            toast.success(`Synced ${account.name}`)
          }
        },
        onError: () => toast.error(`Failed to sync ${account.name}`),
      },
    )
  }

  const currentBudgetName = budgets.find((b) => b.id === budgetId)?.name ?? null

  function handleAllBudgets() {
    clearCurrentBudget()
    navigate('/budgets')
  }

  const { onBudgetByType, offBudgetAssets, offBudgetLiabilityAccounts } = partitionAccounts(
    accounts ?? []
  )
  const onBudgetTypes = orderedOnBudgetKeys(onBudgetByType)
  const onBudgetTotal = accounts
    ?.filter((a) => a.on_budget)
    .reduce((sum, a) => sum + Number(a.balance), 0) ?? 0

  const assetsTotal = sumAssets(offBudgetAssets)
  // Every debt exactly once: liability-classified accounts (tracker balance
  // when linked), managed liabilities whose account lives elsewhere, and
  // unmanaged liabilities. The header total is the sum of what's listed.
  // On-budget ids are passed so a credit card's companion doesn't list the
  // card a second time down here — it already has a row above.
  const onBudgetAccountIds = new Set(
    (accounts ?? []).filter((a) => a.on_budget).map((a) => a.id)
  )
  const liabilityRows = buildLiabilityRows(
    offBudgetLiabilityAccounts,
    liabilities,
    onBudgetAccountIds
  )
  const liabilitiesTotal = liabilityHeaderTotal(liabilityRows)

  function handleAccountClick(account: Account) {
    setSelectedAccount(account.id)
    navigate(`/accounts/${account.id}`)
  }

  const collapsed = sidebarCollapsed

  return (
    <aside className={`sidebar ${collapsed ? 'sidebar--collapsed' : ''}`}>
      <div className="sidebar__logo">
        {!collapsed && <span className="sidebar__logo-text">IGAB</span>}
        <button
          className="sidebar__collapse-btn"
          onClick={toggleSidebarCollapsed}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
      </div>

      {!collapsed && (
        <button className="sidebar__budget-back" onClick={handleAllBudgets} title="Switch budget">
          <ChevronLeft size={14} />
          <span className="sidebar__budget-name">{currentBudgetName ?? 'All budgets'}</span>
        </button>
      )}

      <nav className="sidebar__nav">
        <NavLink to="/budget" className={({ isActive }) => `sidebar__nav-item ${isActive ? 'active' : ''}`} title="Budget" aria-label="Budget">
          <LayoutDashboard size={16} />
          {!collapsed && <span>Budget</span>}
        </NavLink>
        <NavLink to="/reports" className={({ isActive }) => `sidebar__nav-item ${isActive ? 'active' : ''}`} title="Reports" aria-label="Reports">
          <BarChart2 size={16} />
          {!collapsed && <span>Reports</span>}
        </NavLink>
        <NavLink to="/guide" className={({ isActive }) => `sidebar__nav-item ${isActive ? 'active' : ''}`} title="Guide" aria-label="Guide">
          <Compass size={16} />
          {!collapsed && <span>Guide</span>}
        </NavLink>
        <NavLink to="/scheduled" className={({ isActive }) => `sidebar__nav-item ${isActive ? 'active' : ''}`} title="Scheduled" aria-label="Scheduled">
          <CalendarClock size={16} />
          {!collapsed && <span>Scheduled</span>}
        </NavLink>
        <NavLink to="/payees" className={({ isActive }) => `sidebar__nav-item ${isActive ? 'active' : ''}`} title="Payees" aria-label="Payees">
          <Users size={16} />
          {!collapsed && <span>Payees</span>}
        </NavLink>
        <NavLink to="/ai-activity" className={({ isActive }) => `sidebar__nav-item ${isActive ? 'active' : ''}`} title="AI Activity" aria-label="AI Activity">
          <Sparkles size={16} />
          {!collapsed && <span>AI Activity</span>}
        </NavLink>
        <NavLink to="/activity" className={({ isActive }) => `sidebar__nav-item ${isActive ? 'active' : ''}`} title="Activity" aria-label="Activity">
          <History size={16} />
          {!collapsed && <span>Activity</span>}
        </NavLink>
        <NavLink to="/import" className={({ isActive }) => `sidebar__nav-item ${isActive ? 'active' : ''}`} title="Import" aria-label="Import">
          <Upload size={16} />
          {!collapsed && <span>Import</span>}
        </NavLink>
        <NavLink to="/settings" className={({ isActive }) => `sidebar__nav-item ${isActive ? 'active' : ''}`} title="Settings" aria-label="Settings">
          <Settings size={16} />
          {!collapsed && <span>Settings</span>}
          {updateAvailable && (
            <span
              className="sidebar__update-badge"
              title="Update available — see Settings → Updates"
            />
          )}
        </NavLink>
        {me && (
          <div
            className="sidebar__whoami"
            title={`Signed in as ${me.display_name || me.email}`}
          >
            <UserCircle2 size={16} />
            {!collapsed && (
              <span className="sidebar__whoami-name">{me.display_name || me.email}</span>
            )}
          </div>
        )}
        <button className="sidebar__nav-item sidebar__nav-item--logout" onClick={logout} title="Sign out" aria-label="Sign out">
          <LogOut size={16} />
          {!collapsed && <span>Sign out</span>}
        </button>
      </nav>

      {!collapsed && <div className="sidebar__section-header">
        <button
          className="sidebar__section-header-link"
          onClick={() => navigate('/transactions')}
          title="All transactions across accounts"
        >
          Budget Accounts
        </button>
        <span className="sidebar__section-header-actions">
          <span className="sidebar__total tabular">{formatMoney(onBudgetTotal)}</span>
          <button
            className="sidebar__add-account"
            onClick={() => navigate('/accounts')}
            aria-label="Manage accounts"
            title="Manage accounts"
          >
            <Settings size={12} />
          </button>
          <button
            className="sidebar__add-account"
            onClick={() => openModal('add-account')}
            aria-label="Add account"
            title="Add account"
          >
            <Plus size={12} />
          </button>
        </span>
      </div>}

      {!collapsed && onBudgetTypes.map((type) => {
        const typeAccounts: Account[] = onBudgetByType.get(type) ?? []
        if (typeAccounts.length === 0) return null
        return (
          <div key={type} className="sidebar__account-group">
            <div className="sidebar__account-type">{groupLabel(type, typeRows)}</div>
            {typeAccounts.map((acc) => (
              <button
                key={acc.id}
                className="sidebar__account"
                onClick={() => handleAccountClick(acc)}
              >
                <span className="sidebar__account-name">
                  {acc.name}
                  {acc.uncategorized_count > 0 && (
                    <span className="sidebar__uncategorized-badge" title={`${acc.uncategorized_count} uncategorized`}>
                      {acc.uncategorized_count}
                    </span>
                  )}
                </span>
                <span className="sidebar__account-right">
                  {acc.simplefin_account_id && (
                    <SyncStatusIcon
                      account={acc}
                      isSyncing={syncMutation.isPending && syncingAccountId === acc.simplefin_account_id}
                      onSyncClick={(e) => handleAccountSync(acc, e)}
                      lastSyncError={primaryConnection?.last_sync_error}
                    />
                  )}
                  <span className={`sidebar__account-balance tabular ${Number(acc.balance) < 0 ? 'negative' : ''}`}>
                    {formatMoney(Number(acc.balance))}
                  </span>
                </span>
              </button>
            ))}
          </div>
        )
      })}

      {!collapsed && (offBudgetAssets.length > 0 || budgetId) && (
        <>
          <div className="sidebar__section-header">
            <span>Assets</span>
            <span className="sidebar__section-header-actions">
              <span className="sidebar__total tabular">{formatMoney(assetsTotal)}</span>
              <button
                className="sidebar__add-account"
                onClick={() => setAssetModalOpen(true)}
                aria-label="Add asset"
                title="Add asset"
              >
                <Plus size={12} />
              </button>
            </span>
          </div>
          {offBudgetAssets.map((acc) => (
            <button
              key={acc.id}
              className="sidebar__account"
              onClick={() => handleAccountClick(acc)}
            >
              <span className="sidebar__account-name">{acc.name}</span>
              <span className="sidebar__account-balance tabular">
                {formatMoney(Number(acc.balance))}
              </span>
            </button>
          ))}
        </>
      )}

      {!collapsed && liabilityRows.length > 0 && (
        <>
          <div className="sidebar__section-header">
            <button
              className="sidebar__section-header-link"
              onClick={() => navigate('/liabilities')}
              title="All liabilities"
            >
              Liabilities
            </button>
            <span className="sidebar__section-header-actions">
              <span className="sidebar__total tabular negative">
                {formatMoney(liabilitiesTotal)}
              </span>
              <button
                className="sidebar__add-liability"
                onClick={() => { openModal('liability'); navigate('/liabilities') }}
                aria-label="Add liability"
                title="Add liability"
              >
                <Plus size={12} />
              </button>
            </span>
          </div>
          {liabilityRows.map((row) => (
            <div
              key={row.key}
              className="sidebar__account"
              role="button"
              tabIndex={0}
              onClick={() => {
                const target = row.target
                if (target.kind === 'liability') {
                  navigate(`/liabilities/${target.liabilityId}`)
                } else {
                  const acc = offBudgetLiabilityAccounts.find((a) => a.id === target.accountId)
                  if (acc) handleAccountClick(acc)
                }
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  e.currentTarget.click()
                }
              }}
            >
              <span className="sidebar__account-name">
                {row.icon === 'managed' && (
                  <span className="sidebar__liability-icon sidebar__liability-icon--managed" title="Payoff tracking enabled">
                    <Link2 size={12} />
                  </span>
                )}
                {row.icon === 'manual' && (
                  <span className="sidebar__liability-icon" title="Manually tracked">
                    <PenLine size={12} />
                  </span>
                )}
                {row.name}
              </span>
              <span className="sidebar__account-right">
                {row.registerAccountId && (
                  <button
                    className="sidebar__register-btn"
                    onClick={(e) => {
                      e.stopPropagation()
                      setSelectedAccount(row.registerAccountId!)
                      navigate(`/accounts/${row.registerAccountId}`)
                    }}
                    aria-label={`Open ${row.name} register`}
                    title="Open account register"
                  >
                    <List size={12} />
                  </button>
                )}
                <span className="sidebar__account-balance tabular negative">
                  {formatMoney(row.balance)}
                </span>
              </span>
            </div>
          ))}
        </>
      )}
      {!collapsed && liabilityRows.length === 0 && budgetId && (
        <div className="sidebar__section-header">
          <button
            className="sidebar__section-header-link"
            onClick={() => navigate('/liabilities')}
            title="Track a liability"
          >
            Liabilities
          </button>
          <button
            className="sidebar__add-liability"
            onClick={() => { openModal('liability'); navigate('/liabilities') }}
            aria-label="Add liability"
            title="Add liability"
          >
            <Plus size={12} />
          </button>
        </div>
      )}

      {collapsed && accounts && accounts.length > 0 && (
        <div className="sidebar__accounts-mini">
          <div className="sidebar__accounts-mini-divider" />
          {[
            ...onBudgetTypes.flatMap((type) => onBudgetByType.get(type) ?? []),
            ...offBudgetAssets,
            ...offBudgetLiabilityAccounts,
          ].map((acc: Account) => (
            <button
              key={acc.id}
              className="sidebar__account-mini"
              onClick={() => handleAccountClick(acc)}
              title={`${acc.name}\n${formatMoney(Number(acc.balance))}`}
            >
              <span className="sidebar__account-mini-letter">
                {acc.name.charAt(0).toUpperCase()}
              </span>
              {acc.uncategorized_count > 0 && (
                <span className="sidebar__account-mini-dot" />
              )}
            </button>
          ))}
        </div>
      )}

      {!budgetId && (
        <div className="sidebar__empty">
          <Wallet size={20} />
          {!collapsed && <span>No budget selected</span>}
        </div>
      )}

      {activeModal?.kind === 'add-account' && <AddAccountModal onClose={closeModal} />}
      {assetModalOpen && (
        <AddAccountModal
          initialTypeKey="investment"
          onClose={() => setAssetModalOpen(false)}
        />
      )}
    </aside>
  )
}
