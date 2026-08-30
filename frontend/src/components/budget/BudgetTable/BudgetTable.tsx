import { useCallback, useMemo, useRef, useState } from 'react'
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
import {
  renderableCategories,
  renderableCategoryIds,
  renderableGroups,
  drawnGroups,
} from '../budgetGroups'
import { canReorderCategories, canReorderGroups } from '../reorderAvailability'
import { CreditCardsSection } from '../CreditCardsSection/CreditCardsSection'
import { useDragReorder } from '../../../hooks/useDragReorder'
import { moveItem } from '../../../utils/listOrder'
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
  const addGroupRef = useRef<HTMLInputElement>(null)

  const { data: allGroups, isLoading: groupsLoading } = useCategoryGroups(budgetId, showHidden)
  // The budget's envelope groups: the system (Income) group is not drawn.
  const groups = useMemo(() => (allGroups ? renderableGroups(allGroups) : allGroups), [allGroups])
  const { data: categories, isLoading: catsLoading } = useCategories(budgetId, showHidden)
  const { data: budgetMonth, isLoading: monthLoading } = useBudgetMonth(budgetId, month)
  const { data: filters } = useBudgetFilters(budgetId)
  const { data: views } = useBudgetViews(budgetId)
  const createGroup = useCreateCategoryGroup(budgetId ?? '')
  const { mutate: reorderGroups } = useReorderCategoryGroups(budgetId ?? '')
  // A group holding nothing but card envelopes is never drawn — its rows all
  // belong to the cards section — and the server's reorder rule lets it be
  // omitted for exactly that reason (`is_card_only`).
  const ownDrawn = useMemo(() => drawnGroups(groups), [groups])
  // The ids dragging indexes into, and the order it writes back. These must be
  // the groups the grid DRAWS: built from `groups` they included a card-only
  // group that renders nowhere, so with "Show hidden" on, position i in the
  // rendered list addressed a different group here and every drag moved the
  // wrong one — silently reordering the hidden card group among them.
  const groupIds = useMemo(() => ownDrawn?.map((g) => g.id) ?? [], [ownDrawn])
  const moveGroup = useCallback(
    (from: number, to: number) => reorderGroups([...moveItem(groupIds, from, to)]),
    [groupIds, reorderGroups]
  )
  const groupDrag = useDragReorder(groupIds.length, moveGroup)

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

  const matching = renderableCategories(categories ?? []).filter(
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
  const renderableIds = renderableCategoryIds(groups ?? [], categories ?? [])
  const chipBalances = (budgetMonth?.category_balances ?? []).filter(
    (b) => renderableIds.has(b.category_id) && (!viewVisibleIds || viewVisibleIds.has(b.category_id))
  )

  const isFiltered = filterCategoryIds != null || activeQuickFilter != null || searchNeedle !== ''
  // "Credit Card Payments" never renders as a bare header, even with hidden
  // groups shown. The server decides it (`is_card_only`) and the server's
  // reorder rule reads the same expression, so the grid and the write cannot
  // disagree about it. A view arranges its own groups; dragging is off there.
  const drawn = arranged ? drawnGroups(arranged.groups) : ownDrawn
  const visibleGroups =
    isFiltered || activeView
      ? drawn?.filter((g) => (catsByGroup.get(g.id)?.length ?? 0) > 0)
      : drawn

  const allGroupIds = visibleGroups?.map((g) => g.id) ?? []

  // Whether dragging is offered, and the reason when it is not, both come from
  // `reorderAvailability` — the same module the filter bar explains itself
  // with, so the grid and the explanation cannot tell different stories.
  //
  // The one condition that stays here is content, not identity: every group the
  // grid draws must be on screen. This asked `visibleGroups === groups`, an
  // ARRAY IDENTITY check that held only while nothing was dropped — so the
  // moment a card-only group reached the client the handles vanished with
  // nothing to explain it.
  const reorderState = {
    savedFilterActive: activeFilterId != null,
    quickFilterActive: activeQuickFilter != null,
    search: categorySearch,
    viewActive: activeView != null,
  }
  const allDrawnOnScreen = visibleGroups?.length === drawn?.length
  const groupsReorderable =
    canReorderGroups(reorderState, visibleGroups?.length ?? 0) && allDrawnOnScreen
  const categoriesReorderable = canReorderCategories(reorderState)

  const allCollapsed = allGroupIds.length > 0 && allGroupIds.every((id) => collapsedGroups.has(id))

  function startAddGroup() {
    setNewGroupName('')
    setIsAddingGroup(true)
    setTimeout(() => addGroupRef.current?.focus(), 0)
  }

  function commitAddGroup() {
    const name = newGroupName.trim()
    if (name) createGroup.mutate({ name })
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
      {/* Above the category headers so the cards read as part of the month,
          not an afterthought below the fold; folds shut and stays folded. */}
      <CreditCardsSection budgetId={budgetId} month={month} />
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
            index={index}
            reorder={groupsReorderable ? groupDrag : undefined}
            canReorderCategories={categoriesReorderable}
          />
        ))}
      </div>
    </div>
  )
}
