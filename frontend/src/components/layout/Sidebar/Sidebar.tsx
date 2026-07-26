import { NavLink, useNavigate } from 'react-router-dom'
import { LayoutDashboard, Wallet, Settings, Upload, BarChart2, CalendarClock, Users, ChevronLeft, PanelLeftClose, PanelLeftOpen, LogOut, Plus, Link2, PenLine } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAccounts } from '../../../api/accounts'
import { useBudgets } from '../../../api/budgets'
import { useLiabilities } from '../../../api/liabilities'
import { useSimpleFINConnections, useSyncSimpleFIN, useSimpleFINRateLimitStatus } from '../../../api/simplefin'
import { SyncStatusIcon } from '../../simplefin/SyncStatusIcon'
import { AddAccountModal } from '../../accounts/AddAccountModal'
import { useLogout } from '../../../api/auth'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { formatMoney } from '../../../utils/money'
import type { Account } from '../../../types'
import './Sidebar.css'

function accountTypeLabel(type: string): string {
  switch (type) {
    case 'checking': return 'Checking'
    case 'savings': return 'Savings'
    case 'credit_card': return 'Credit Cards'
    case 'loan': return 'Loans'
    case 'tracking': return 'Tracking'
    default: return 'Other'
  }
}

function groupAccounts(accounts: Account[]): Map<string, Account[]> {
  const groups = new Map<string, Account[]>()
  for (const acc of accounts) {
    const key = acc.on_budget ? acc.account_type : 'tracking'
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(acc)
  }
  return groups
}


export function Sidebar() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const clearCurrentBudget = useAppStore((s) => s.clearCurrentBudget)
  const setSelectedAccount = useAppStore((s) => s.setSelectedAccountId)
  const navigate = useNavigate()
  const { data: accounts } = useAccounts(budgetId)
  const { data: budgets = [] } = useBudgets()
  const { data: liabilities = [] } = useLiabilities(budgetId)
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed)
  const toggleSidebarCollapsed = useUIStore((s) => s.toggleSidebarCollapsed)
  const isAddAccountModalOpen = useUIStore((s) => s.isAddAccountModalOpen)
  const openAddAccountModal = useUIStore((s) => s.openAddAccountModal)
  const closeAddAccountModal = useUIStore((s) => s.closeAddAccountModal)
  const openLiabilityEditor = useUIStore((s) => s.openLiabilityEditor)

  const logout = useLogout()

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

  const grouped = accounts ? groupAccounts(accounts) : new Map()
  const onBudgetTypes = ['checking', 'savings', 'credit_card', 'loan']
  const onBudgetTotal = accounts
    ?.filter((a) => a.on_budget)
    .reduce((sum, a) => sum + Number(a.balance), 0) ?? 0

  // Tracking accounts grouped by classification
  const trackingAccounts = accounts?.filter((a) => !a.on_budget) ?? []
  const assetAccounts = trackingAccounts.filter((a) => a.classification === 'asset')
  const liabilityAccounts = trackingAccounts.filter((a) => a.classification === 'liability')
  const assetsTotal = assetAccounts.reduce((sum, a) => sum + Number(a.balance), 0)
  const liabilityAccountsTotal = liabilityAccounts.reduce((sum, a) => sum + Number(a.balance), 0)

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
        <NavLink to="/budget" className={({ isActive }) => `sidebar__nav-item ${isActive ? 'active' : ''}`} title="Budget">
          <LayoutDashboard size={16} />
          {!collapsed && <span>Budget</span>}
        </NavLink>
        <NavLink to="/reports" className={({ isActive }) => `sidebar__nav-item ${isActive ? 'active' : ''}`} title="Reports">
          <BarChart2 size={16} />
          {!collapsed && <span>Reports</span>}
        </NavLink>
        <NavLink to="/scheduled" className={({ isActive }) => `sidebar__nav-item ${isActive ? 'active' : ''}`} title="Scheduled">
          <CalendarClock size={16} />
          {!collapsed && <span>Scheduled</span>}
        </NavLink>
        <NavLink to="/payees" className={({ isActive }) => `sidebar__nav-item ${isActive ? 'active' : ''}`} title="Payees">
          <Users size={16} />
          {!collapsed && <span>Payees</span>}
        </NavLink>
        <NavLink to="/import" className={({ isActive }) => `sidebar__nav-item ${isActive ? 'active' : ''}`} title="Import">
          <Upload size={16} />
          {!collapsed && <span>Import</span>}
        </NavLink>
        <NavLink to="/settings" className={({ isActive }) => `sidebar__nav-item ${isActive ? 'active' : ''}`} title="Settings">
          <Settings size={16} />
          {!collapsed && <span>Settings</span>}
        </NavLink>
        <button className="sidebar__nav-item sidebar__nav-item--logout" onClick={logout} title="Sign out">
          <LogOut size={16} />
          {!collapsed && <span>Sign out</span>}
        </button>
      </nav>

      {!collapsed && <div className="sidebar__section-header">
        <button
          className="sidebar__section-header-link"
          onClick={() => navigate('/accounts')}
          title="All accounts"
        >
          Budget Accounts
        </button>
        <span className="sidebar__section-header-actions">
          <span className="sidebar__total tabular">{formatMoney(onBudgetTotal)}</span>
          <button
            className="sidebar__add-account"
            onClick={openAddAccountModal}
            aria-label="Add account"
            title="Add account"
          >
            <Plus size={12} />
          </button>
        </span>
      </div>}

      {!collapsed && onBudgetTypes.map((type) => {
        const typeAccounts: Account[] = grouped.get(type) ?? []
        if (typeAccounts.length === 0) return null
        return (
          <div key={type} className="sidebar__account-group">
            <div className="sidebar__account-type">{accountTypeLabel(type)}</div>
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

      {!collapsed && (assetAccounts.length > 0 || budgetId) && (
        <>
          <div className="sidebar__section-header">
            <span>Assets</span>
            <span className="sidebar__section-header-actions">
              <span className="sidebar__total tabular">{formatMoney(assetsTotal)}</span>
              <button
                className="sidebar__add-account"
                onClick={openAddAccountModal}
                aria-label="Add asset"
                title="Add asset"
              >
                <Plus size={12} />
              </button>
            </span>
          </div>
          {assetAccounts.map((acc) => (
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

      {!collapsed && (liabilityAccounts.length > 0 || liabilities.length > 0) && (
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
                {formatMoney(liabilityAccountsTotal - liabilities.filter(l => !l.linked_account_id).reduce((sum, l) => sum + Number(l.current_balance), 0))}
              </span>
              <button
                className="sidebar__add-liability"
                onClick={() => { openLiabilityEditor(null); navigate('/liabilities') }}
                aria-label="Add liability"
                title="Add liability"
              >
                <Plus size={12} />
              </button>
            </span>
          </div>
          {liabilityAccounts.map((acc) => {
            const tracker = liabilities.find(l => l.linked_account_id === acc.id)
            return (
              <button
                key={acc.id}
                className="sidebar__account"
                onClick={() => tracker ? navigate(`/liabilities/${tracker.id}`) : handleAccountClick(acc)}
              >
                <span className="sidebar__account-name">
                  {tracker && (
                    <span className="sidebar__liability-icon sidebar__liability-icon--managed" title="Payoff tracking enabled">
                      <Link2 size={12} />
                    </span>
                  )}
                  {acc.name}
                </span>
                <span className="sidebar__account-balance tabular negative">
                  {formatMoney(Number(acc.balance))}
                </span>
              </button>
            )
          })}
          {/* Unmanaged liabilities (no linked account) */}
          {liabilities.filter(l => !l.linked_account_id).map((liability) => (
            <button
              key={liability.id}
              className="sidebar__account"
              onClick={() => navigate(`/liabilities/${liability.id}`)}
            >
              <span className="sidebar__account-name">
                <span className="sidebar__liability-icon" title="Manually tracked">
                  <PenLine size={12} />
                </span>
                {liability.name}
              </span>
              <span className="sidebar__account-balance tabular negative">
                {formatMoney(-Number(liability.current_balance))}
              </span>
            </button>
          ))}
        </>
      )}
      {!collapsed && liabilityAccounts.length === 0 && liabilities.length === 0 && budgetId && (
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
            onClick={() => { openLiabilityEditor(null); navigate('/liabilities') }}
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
          {[...onBudgetTypes, 'tracking'].flatMap((type) =>
            (grouped.get(type) ?? []).map((acc: Account) => (
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
            ))
          )}
        </div>
      )}

      {!budgetId && (
        <div className="sidebar__empty">
          <Wallet size={20} />
          {!collapsed && <span>No budget selected</span>}
        </div>
      )}

      {isAddAccountModalOpen && <AddAccountModal onClose={closeAddAccountModal} />}
    </aside>
  )
}
