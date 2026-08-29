import type { CSSProperties } from 'react'
import { useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { UserCircle2, LayoutDashboard, List, Wallet, Settings, Upload, BarChart2, CalendarClock, Users, ChevronLeft, PanelLeftClose, PanelLeftOpen, LogOut, Plus, Link2, PenLine, RefreshCw, Sparkles, History, Compass } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAccounts } from '../../../api/accounts'
import { useAccountTypes } from '../../../api/accountTypes'
import {
  SIDEBAR_SECTION_IDS,
  accountKind,
  accountTarget,
  accountsTotal,
  buildLiabilityRows,
  groupLabel,
  isRowActive,
  onBudgetTotals,
  liabilityHeaderTotal,
  orderedOnBudgetKeys,
  parseSidebarLocation,
  partitionAccounts,
  sidebarTypeGroupId,
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
import { useSyncAllAccounts } from '../../../hooks/useSyncAllAccounts'
import type { Account } from '../../../types'
import './Sidebar.css'
import { useSidebarResize } from './useSidebarResize'
import { SIDEBAR_MAX_WIDTH, SIDEBAR_MIN_WIDTH } from './sidebarWidth'
import { SidebarAccountRow } from './SidebarAccountRow'
import { SidebarGroupHeader } from './SidebarGroupHeader'



export function Sidebar() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const clearCurrentBudget = useAppStore((s) => s.clearCurrentBudget)
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { formatMoney } = useFormatters()
  const { data: accounts } = useAccounts(budgetId)
  const { data: typeRows } = useAccountTypes(budgetId)
  const { data: budgets = [] } = useBudgets()
  const { data: liabilities = [] } = useLiabilities(budgetId)
  const updateAvailable = useUpdateStatus().data?.update_available === true
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed)
  const toggleSidebarCollapsed = useUIStore((s) => s.toggleSidebarCollapsed)
  const sidebarWidth = useUIStore((s) => s.sidebarWidth)
  const setSidebarWidth = useUIStore((s) => s.setSidebarWidth)
  const collapsedGroups = useUIStore((s) => s.collapsedSidebarGroups)
  const toggleGroup = useUIStore((s) => s.toggleSidebarGroup)
  const resize = useSidebarResize(sidebarWidth, setSidebarWidth)
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
  const syncAll = useSyncAllAccounts()
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
  // Summed from the same map the groups render from, so the section header is
  // by construction the sum of the subtotals listed under it.
  const onBudget = onBudgetTotals(onBudgetByType)

  const assetsTotal = accountsTotal(offBudgetAssets)
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

  // Which row is open, decided once from the URL and handed to every section.
  // Deriving it per section is how the liability rows would have ended up
  // with a rule that forgot the register shortcut.
  const sidebarLocation = parseSidebarLocation(pathname)

  function handleAccountClick(account: Account) {
    navigate(`/accounts/${account.id}`)
  }

  const collapsed = sidebarCollapsed
  const isFolded = (groupId: string) => collapsedGroups.has(groupId)

  return (
    <aside
      className={`sidebar ${collapsed ? 'sidebar--collapsed' : ''}`}
      style={collapsed ? undefined : ({ '--sidebar-width': `${sidebarWidth}px` } as CSSProperties)}
    >
      {!collapsed && (
        <div
          className={`sidebar__resizer ${resize.active ? 'sidebar__resizer--active' : ''}`}
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize sidebar"
          aria-valuemin={SIDEBAR_MIN_WIDTH}
          aria-valuemax={SIDEBAR_MAX_WIDTH}
          aria-valuenow={sidebarWidth}
          tabIndex={0}
          title="Drag to resize · double-click to reset"
          {...resize.handleProps}
        />
      )}
      <div className="sidebar__scroll">
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

      {!collapsed && (
        <div className="sidebar__section">
          <SidebarGroupHeader
            level="section"
            label="Budget Accounts"
            total={onBudget.net}
            collapsible={onBudgetTypes.length > 0}
            collapsed={isFolded(SIDEBAR_SECTION_IDS.budgetAccounts)}
            onToggle={() => toggleGroup(SIDEBAR_SECTION_IDS.budgetAccounts)}
            onLabelClick={() => navigate('/transactions')}
            labelTitle="All transactions across accounts"
            actions={
              <>
                {/* Reachable from every page, beside the balances it
                    refreshes — and it covers every connection, which the
                    Accounts page's button did not. */}
                {syncAll.available && (
                  <button
                    className="sidebar__group-action"
                    onClick={syncAll.syncAll}
                    disabled={syncAll.isPending}
                    aria-label="Sync all accounts"
                    title="Sync all accounts"
                  >
                    <RefreshCw size={12} className={syncAll.isPending ? 'spin' : undefined} />
                  </button>
                )}
                <button
                  className="sidebar__group-action"
                  onClick={() => navigate('/accounts')}
                  aria-label="Manage accounts"
                  title="Manage accounts"
                >
                  <Settings size={12} />
                </button>
                <button
                  className="sidebar__group-action"
                  onClick={() => openModal('add-account')}
                  aria-label="Add account"
                  title="Add account"
                >
                  <Plus size={12} />
                </button>
              </>
            }
          />
          {/* Cash, said plainly. The section total nets the cards against it,
              which answers neither "what have I got" nor "what do I owe", and
              a card's balance is not money you have — the budget itself stopped
              counting it as cash when cards left Ready to Assign. Drawn only
              when the two figures actually differ, and labelled, because two
              unexplained totals in one section is the failure mode here. */}
          {!isFolded(SIDEBAR_SECTION_IDS.budgetAccounts) && onBudget.cards !== 0 && (
            <div
              className="sidebar__cash"
              title={`Your on-budget cash accounts, before card debt. The section total above is this minus the ${formatMoney(Math.abs(onBudget.cards))} owed on cards.`}
            >
              <span className="sidebar__cash-label">Cash on hand</span>
              <span className="sidebar__cash-value tabular">{formatMoney(onBudget.cash)}</span>
            </div>
          )}
          {!isFolded(SIDEBAR_SECTION_IDS.budgetAccounts) &&
            onBudgetTypes.map((type) => {
              const typeAccounts: Account[] = onBudgetByType.get(type) ?? []
              if (typeAccounts.length === 0) return null
              const typeGroupId = sidebarTypeGroupId(type)
              return (
                <div key={type} className="sidebar__account-group">
                  <SidebarGroupHeader
                    level="type"
                    label={groupLabel(type, typeRows)}
                    // A one-account group's subtotal is that account's own
                    // balance printed again one line below it. Shown only when
                    // it says something the rows don't: two or more accounts,
                    // or a group folded shut over the number.
                    total={
                      typeAccounts.length > 1 || isFolded(typeGroupId)
                        ? accountsTotal(typeAccounts)
                        : null
                    }
                    collapsed={isFolded(typeGroupId)}
                    onToggle={() => toggleGroup(typeGroupId)}
                  />
                  {!isFolded(typeGroupId) &&
                    typeAccounts.map((acc) => (
                      <SidebarAccountRow
                        key={acc.id}
                        name={acc.name}
                        balance={Number(acc.balance)}
                        kind={accountKind(acc)}
                        badgeCount={acc.uncategorized_count}
                        onClick={() => handleAccountClick(acc)}
                        isActive={isRowActive(accountTarget(acc.id), null, sidebarLocation)}
                        trailing={
                          acc.simplefin_account_id ? (
                            <SyncStatusIcon
                              account={acc}
                              isSyncing={
                                syncMutation.isPending &&
                                syncingAccountId === acc.simplefin_account_id
                              }
                              onSyncClick={(e) => handleAccountSync(acc, e)}
                              lastSyncError={primaryConnection?.last_sync_error}
                            />
                          ) : undefined
                        }
                      />
                    ))}
                </div>
              )
            })}
        </div>
      )}

      {!collapsed && (offBudgetAssets.length > 0 || budgetId) && (
        <div className="sidebar__section">
          <SidebarGroupHeader
            level="section"
            label="Assets"
            total={assetsTotal}
            collapsible={offBudgetAssets.length > 0}
            collapsed={isFolded(SIDEBAR_SECTION_IDS.assets)}
            onToggle={() => toggleGroup(SIDEBAR_SECTION_IDS.assets)}
            actions={
              <button
                className="sidebar__group-action"
                onClick={() => setAssetModalOpen(true)}
                aria-label="Add asset"
                title="Add asset"
              >
                <Plus size={12} />
              </button>
            }
          />
          {!isFolded(SIDEBAR_SECTION_IDS.assets) &&
            offBudgetAssets.map((acc) => (
              <SidebarAccountRow
                key={acc.id}
                name={acc.name}
                balance={Number(acc.balance)}
                kind={accountKind(acc)}
                onClick={() => handleAccountClick(acc)}
                isActive={isRowActive(accountTarget(acc.id), null, sidebarLocation)}
              />
            ))}
        </div>
      )}

      {!collapsed && (liabilityRows.length > 0 || budgetId) && (
        <div className="sidebar__section">
          <SidebarGroupHeader
            level="section"
            label="Liabilities"
            total={liabilityRows.length > 0 ? liabilitiesTotal : null}
            collapsible={liabilityRows.length > 0}
            collapsed={isFolded(SIDEBAR_SECTION_IDS.liabilities)}
            onToggle={() => toggleGroup(SIDEBAR_SECTION_IDS.liabilities)}
            onLabelClick={() => navigate('/liabilities')}
            labelTitle={liabilityRows.length > 0 ? 'All liabilities' : 'Track a liability'}
            actions={
              <button
                className="sidebar__group-action"
                onClick={() => {
                  openModal('liability')
                  navigate('/liabilities')
                }}
                aria-label="Add liability"
                title="Add liability"
              >
                <Plus size={12} />
              </button>
            }
          />
          {!isFolded(SIDEBAR_SECTION_IDS.liabilities) &&
            liabilityRows.map((row) => (
              <SidebarAccountRow
                key={row.key}
                name={row.name}
                balance={row.balance}
                kind="debt"
                isActive={isRowActive(row.target, row.registerAccountId, sidebarLocation)}
                onClick={() => {
                  const target = row.target
                  if (target.kind === 'liability') {
                    navigate(`/liabilities/${target.liabilityId}`)
                  } else {
                    const acc = offBudgetLiabilityAccounts.find((a) => a.id === target.accountId)
                    if (acc) handleAccountClick(acc)
                  }
                }}
                leadingIcon={
                  row.icon ? (
                    <span
                      className={`sidebar__liability-icon ${row.icon === 'managed' ? 'sidebar__liability-icon--managed' : ''}`}
                      title={
                        row.icon === 'managed' ? 'Payoff tracking enabled' : 'Manually tracked'
                      }
                    >
                      {row.icon === 'managed' ? <Link2 size={12} /> : <PenLine size={12} />}
                    </span>
                  ) : undefined
                }
                trailing={
                  row.registerAccountId ? (
                    <button
                      className="sidebar__register-btn"
                      onClick={(e) => {
                        e.stopPropagation()
                        navigate(`/accounts/${row.registerAccountId}`)
                      }}
                      aria-label={`Open ${row.name} register`}
                      title="Open account register"
                    >
                      <List size={12} />
                    </button>
                  ) : undefined
                }
              />
            ))}
        </div>
      )}

      {collapsed && accounts && accounts.length > 0 && (
        <div className="sidebar__accounts-mini">
          <div className="sidebar__accounts-mini-divider" />
          {[
            ...onBudgetTypes.flatMap((type) => onBudgetByType.get(type) ?? []),
            ...offBudgetAssets,
            ...offBudgetLiabilityAccounts,
          ].map((acc: Account) => {
            const active = isRowActive(accountTarget(acc.id), null, sidebarLocation)
            return (
              <button
                key={acc.id}
                className={`sidebar__account-mini ${active ? 'sidebar__account-mini--active' : ''}`}
                aria-current={active ? 'page' : undefined}
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
            )
          })}
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
      </div>
    </aside>
  )
}
