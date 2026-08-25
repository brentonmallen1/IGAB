import { useRef, useState } from 'react'
import { ChevronsDownUp, ChevronsUpDown, Eye, Plus } from 'lucide-react'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { useBudgetMonth } from '../../../api/budgets'
import {
  useCategories,
  useCategoryGroups,
  useCreateCategoryGroup,
  useReorderCategoryGroups,
} from '../../../api/categories'
import { useBudgetFilters } from '../../../api/budgetFilters'
import { useBudgetViews } from '../../../api/budgetViews'
import { groupByView, visibleCategoryIds } from './viewGrouping'
import { CategoryGroupRow } from '../CategoryGroupRow/CategoryGroupRow'
import { BudgetFilterBar } from '../BudgetFilterBar/BudgetFilterBar'
import type { CategoryBalance, CategoryGroup } from '../../../types'
import './BudgetTable.css'

export function BudgetTable() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const month = useAppStore((s) => s.selectedMonth)

  const collapsedGroups = useUIStore((s) => s.collapsedGroups)
  const collapseAll = useUIStore((s) => s.collapseAll)
  const expandAll = useUIStore((s) => s.expandAll)
  const activeFilterId = useUIStore((s) => s.activeFilterId)
  const activeViewId = useUIStore((s) => s.activeViewId)
  const activeQuickFilter = useUIStore((s) => s.activeQuickFilter)
  const categorySearch = useUIStore((s) => s.categorySearch)

  const [showHidden, setShowHidden] = useState(false)
  const [isAddingGroup, setIsAddingGroup] = useState(false)
  const [newGroupName, setNewGroupName] = useState('')
  const [dragGroupIndex, setDragGroupIndex] = useState<number | null>(null)
  const [dragOverGroupIndex, setDragOverGroupIndex] = useState<number | null>(null)
  const addGroupRef = useRef<HTMLInputElement>(null)

  const { data: groups, isLoading: groupsLoading } = useCategoryGroups(budgetId, showHidden)
  const { data: categories, isLoading: catsLoading } = useCategories(budgetId, showHidden)
  const { data: budgetMonth, isLoading: monthLoading } = useBudgetMonth(budgetId, month)
  const { data: filters } = useBudgetFilters(budgetId)
  const { data: views } = useBudgetViews(budgetId)
  const createGroup = useCreateCategoryGroup(budgetId ?? '')
  const reorderGroups = useReorderCategoryGroups(budgetId ?? '')

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

  const activeFilter = filters?.find((f) => f.id === activeFilterId) ?? null
  const filterCategoryIds = activeFilter ? new Set(activeFilter.category_ids) : null

  const groupNameById = new Map((groups ?? []).map((g) => [g.id, g.name]))
  const searchNeedle = categorySearch.trim().toLowerCase()

  function categoryMatchesFilter(catId: string): boolean {
    if (filterCategoryIds) return filterCategoryIds.has(catId)
    if (!activeQuickFilter) return true
    const balance = balanceMap.get(catId)
    // The chip's count and the rows it filters read the same served field, so
    // they cannot disagree — they were computed from two different lists.
    switch (activeQuickFilter) {
      case 'overspent': return (balance?.available ?? 0) < 0
      case 'underfunded': return balance?.target_status === 'underfunded'
      case 'money-available': return (balance?.available ?? 0) > 0
      case 'overfunded': return balance?.target_status === 'overfunded'
    }
  }

  // Text search matches the category name or its group's name, and stacks
  // with the active view / quick filter
  function categoryMatchesSearch(cat: { id: string; name: string; category_group_id: string }) {
    if (!searchNeedle) return true
    if (cat.name.toLowerCase().includes(searchNeedle)) return true
    return (groupNameById.get(cat.category_group_id) ?? '').toLowerCase().includes(searchNeedle)
  }

  // A view replaces how categories are grouped; a filter still decides which
  // of them show. The two are independent axes and both can be active.
  const activeView = views?.find((v) => v.id === activeViewId) ?? null

  const matching = (categories ?? []).filter(
    (cat) => categoryMatchesFilter(cat.id) && categoryMatchesSearch(cat)
  )

  const arranged = activeView ? groupByView(activeView, matching, budgetId) : null

  const catsByGroup = new Map<string, typeof categories>()
  if (arranged) {
    arranged.byGroup.forEach((list, groupId) => catsByGroup.set(groupId, list))
  } else {
    matching.forEach((cat) => {
      if (!catsByGroup.has(cat.category_group_id)) catsByGroup.set(cat.category_group_id, [])
      catsByGroup.get(cat.category_group_id)!.push(cat)
    })
  }

  // Chip counts must describe the rows the grid will actually render. A view
  // drops hidden placements, and with hide_unassigned drops every unplaced
  // category — counting from the unfiltered balances made "Overspent 5" open
  // a list of 2 with nothing to explain the gap.
  const viewVisibleIds = activeView
    ? visibleCategoryIds(activeView, categories ?? [], budgetId)
    : null
  // A chip's count and the rows clicking it produces must be the same set.
  // These spanned every balance the month returned — including system and
  // hidden categories the table never renders — so the chip promised rows it
  // could not show.
  const renderableIds = new Set((categories ?? []).map((c) => c.id))
  const chipBalances = (budgetMonth?.category_balances ?? []).filter(
    (b) => renderableIds.has(b.category_id) && (!viewVisibleIds || viewVisibleIds.has(b.category_id))
  )

  const isFiltered = filterCategoryIds != null || activeQuickFilter != null || searchNeedle !== ''
  const sourceGroups = arranged?.groups ?? groups
  const visibleGroups =
    isFiltered || activeView
      ? sourceGroups?.filter((g) => (catsByGroup.get(g.id)?.length ?? 0) > 0)
      : sourceGroups

  const allGroupIds = visibleGroups?.map((g) => g.id) ?? []

  // Dragging is offered only on the budget's own arrangement, showing every
  // group. A filtered or searched grid hides groups, so a drop there would
  // reorder against a list the user cannot see; a view has its own order,
  // which is edited in the view editor.
  const canReorderGroups =
    !isFiltered && !activeView && (groups?.length ?? 0) > 1 && visibleGroups === groups

  function moveGroup(from: number, to: number) {
    if (!groups || from === to || to < 0 || to >= groups.length) return
    const next = groups.map((g) => g.id)
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    reorderGroups.mutate(next)
  }

  function handleGroupDrop(dropIndex: number) {
    if (dragGroupIndex !== null) moveGroup(dragGroupIndex, dropIndex)
    setDragGroupIndex(null)
    setDragOverGroupIndex(null)
  }
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
      <BudgetFilterBar budgetId={budgetId} categoryBalances={chipBalances} />
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
            {/* Add Group creates a group in the budget's own arrangement. With
                a view active that is not what the user is looking at, so it is
                hidden rather than quietly editing the thing behind the view. */}
            {activeView ? null : isAddingGroup ? (
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
        {visibleGroups?.map((group: CategoryGroup, index: number) => (
          <CategoryGroupRow
            key={group.id}
            group={group}
            categories={catsByGroup.get(group.id) ?? []}
            balanceMap={balanceMap}
            budgetId={budgetId}
            month={month}
            readOnlyGroup={activeView != null}
            reorder={
              canReorderGroups
                ? {
                    isDragging: dragGroupIndex === index,
                    isDragOver: dragOverGroupIndex === index && dragGroupIndex !== index,
                    onDragStart: () => setDragGroupIndex(index),
                    onDragOver: () => setDragOverGroupIndex(index),
                    onDrop: () => handleGroupDrop(index),
                    onDragEnd: () => {
                      setDragGroupIndex(null)
                      setDragOverGroupIndex(null)
                    },
                    // Keyboard equivalent: dragging is not reachable without a
                    // pointer, and the order of a budget is not a mouse-only
                    // decision.
                    onMoveUp: index > 0 ? () => moveGroup(index, index - 1) : undefined,
                    onMoveDown:
                      index < (visibleGroups?.length ?? 0) - 1
                        ? () => moveGroup(index, index + 1)
                        : undefined,
                  }
                : undefined
            }
          />
        ))}
      </div>
    </div>
  )
}
