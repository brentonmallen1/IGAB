import { useRef, useState } from 'react'
import { ChevronsDownUp, ChevronsUpDown, Eye, Plus } from 'lucide-react'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { useBudgetMonth } from '../../../api/budgets'
import {
  useCategories,
  useCategoryGroups,
  useCreateCategoryGroup,
} from '../../../api/categories'
import { useBudgetViews } from '../../../api/budgetViews'
import { useTargetsByBudget } from '../../../api/targets'
import { CategoryGroupRow } from '../CategoryGroupRow/CategoryGroupRow'
import { BudgetViewBar } from '../BudgetViewBar/BudgetViewBar'
import type { CategoryBalance, CategoryGroup } from '../../../types'
import './BudgetTable.css'

export function BudgetTable() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const month = useAppStore((s) => s.selectedMonth)

  const collapsedGroups = useUIStore((s) => s.collapsedGroups)
  const collapseAll = useUIStore((s) => s.collapseAll)
  const expandAll = useUIStore((s) => s.expandAll)
  const activeBudgetViewId = useUIStore((s) => s.activeBudgetViewId)
  const activeQuickFilter = useUIStore((s) => s.activeQuickFilter)
  const categorySearch = useUIStore((s) => s.categorySearch)

  const [showHidden, setShowHidden] = useState(false)
  const [isAddingGroup, setIsAddingGroup] = useState(false)
  const [newGroupName, setNewGroupName] = useState('')
  const addGroupRef = useRef<HTMLInputElement>(null)

  const { data: groups, isLoading: groupsLoading } = useCategoryGroups(budgetId, showHidden)
  const { data: categories, isLoading: catsLoading } = useCategories(budgetId, showHidden)
  const { data: budgetMonth, isLoading: monthLoading } = useBudgetMonth(budgetId, month)
  const { data: views } = useBudgetViews(budgetId)
  const { data: targets } = useTargetsByBudget(budgetId)
  const createGroup = useCreateCategoryGroup(budgetId ?? '')

  if (!budgetId) {
    return (
      <div className="budget-table__empty">
        <p>No budget selected. Create or select a budget to get started.</p>
      </div>
    )
  }

  if (groupsLoading || catsLoading || monthLoading) {
    return <div className="budget-table__loading">Loading...</div>
  }

  const balanceMap = new Map<string, CategoryBalance>()
  budgetMonth?.category_balances.forEach((b) => balanceMap.set(b.category_id, b))

  const targetMap = new Map((targets ?? []).map((t) => [t.category_id, t]))

  const activeView = views?.find((v) => v.id === activeBudgetViewId) ?? null
  const viewCategoryIds = activeView ? new Set(activeView.category_ids) : null

  const groupNameById = new Map((groups ?? []).map((g) => [g.id, g.name]))
  const searchNeedle = categorySearch.trim().toLowerCase()

  function categoryMatchesFilter(catId: string): boolean {
    if (viewCategoryIds) return viewCategoryIds.has(catId)
    if (!activeQuickFilter) return true
    const balance = balanceMap.get(catId)
    const target = targetMap.get(catId)
    switch (activeQuickFilter) {
      case 'overspent': return (balance?.available ?? 0) < 0
      case 'underfunded': return target != null && (balance?.assigned ?? 0) < target.target_amount
      case 'money-available': return (balance?.available ?? 0) > 0
      case 'overfunded': return target != null && (balance?.assigned ?? 0) > target.target_amount
    }
  }

  // Text search matches the category name or its group's name, and stacks
  // with the active view / quick filter
  function categoryMatchesSearch(cat: { id: string; name: string; category_group_id: string }) {
    if (!searchNeedle) return true
    if (cat.name.toLowerCase().includes(searchNeedle)) return true
    return (groupNameById.get(cat.category_group_id) ?? '').toLowerCase().includes(searchNeedle)
  }

  const catsByGroup = new Map<string, typeof categories>()
  categories?.forEach((cat) => {
    if (!categoryMatchesFilter(cat.id) || !categoryMatchesSearch(cat)) return
    if (!catsByGroup.has(cat.category_group_id)) catsByGroup.set(cat.category_group_id, [])
    catsByGroup.get(cat.category_group_id)!.push(cat)
  })

  const isFiltered = viewCategoryIds != null || activeQuickFilter != null || searchNeedle !== ''
  const visibleGroups = isFiltered
    ? groups?.filter((g) => (catsByGroup.get(g.id)?.length ?? 0) > 0)
    : groups

  const allGroupIds = visibleGroups?.map((g) => g.id) ?? []
  const allCollapsed = allGroupIds.length > 0 && allGroupIds.every((id) => collapsedGroups.has(id))

  function startAddGroup() {
    setNewGroupName('')
    setIsAddingGroup(true)
    setTimeout(() => addGroupRef.current?.focus(), 0)
  }

  function commitAddGroup() {
    const name = newGroupName.trim()
    if (name) createGroup.mutate({ name, sort_order: groups?.length ?? 0 })
    setIsAddingGroup(false)
    setNewGroupName('')
  }

  function handleAddGroupKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter') { e.preventDefault(); commitAddGroup() }
    if (e.key === 'Escape') { setIsAddingGroup(false); setNewGroupName('') }
  }

  return (
    <div className="budget-table">
      <BudgetViewBar
        budgetId={budgetId}
        categoryBalances={budgetMonth?.category_balances ?? []}
        targets={targets ?? []}
      />
      <div className="budget-table__header">
        <div className="budget-table__col budget-table__col--name">
          Category
          <div className="budget-table__header-actions">
            <button
              className="budget-table__header-btn"
              onClick={() => allCollapsed ? expandAll() : collapseAll(allGroupIds)}
              title={allCollapsed ? 'Expand all groups' : 'Collapse all groups'}
            >
              {allCollapsed ? <ChevronsUpDown size={11} /> : <ChevronsDownUp size={11} />}
              {allCollapsed ? 'Expand all' : 'Collapse all'}
            </button>
            {isAddingGroup ? (
              <input
                ref={addGroupRef}
                className="budget-table__add-group-input"
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                onBlur={commitAddGroup}
                onKeyDown={handleAddGroupKey}
                placeholder="Group name…"
              />
            ) : (
              <button className="budget-table__header-btn" onClick={startAddGroup} title="Add group">
                <Plus size={11} /> Add Group
              </button>
            )}
            <button
              className={`budget-table__header-btn ${showHidden ? 'active' : ''}`}
              onClick={() => setShowHidden((v) => !v)}
              title={showHidden ? 'Hide hidden items' : 'Show hidden items'}
            >
              <Eye size={11} />
              {showHidden ? 'Hide hidden' : 'Show hidden'}
            </button>
          </div>
        </div>
        <div className="budget-table__col budget-table__col--money">Assigned</div>
        <div className="budget-table__col budget-table__col--money">Activity</div>
        <div className="budget-table__col budget-table__col--money">Available</div>
      </div>

      <div className="budget-table__body">
        {visibleGroups?.map((group: CategoryGroup) => (
          <CategoryGroupRow
            key={group.id}
            group={group}
            categories={catsByGroup.get(group.id) ?? []}
            balanceMap={balanceMap}
            budgetId={budgetId}
            month={month}
          />
        ))}
      </div>
    </div>
  )
}
