import { useRef, useState } from 'react'
import { Archive, FolderInput, Trash2 } from 'lucide-react'
import { BudgetTable } from '../../components/budget/BudgetTable/BudgetTable'
import { CategoryInspector } from '../../components/budget/CategoryInspector/CategoryInspector'
import { CategoryMobileActions } from '../../components/budget/CategoryInspector/CategoryMobileActions'
import { BottomSheet } from '../../components/common/BottomSheet/BottomSheet'
import { BudgetFilterModal } from '../../components/budget/BudgetFilterModal/BudgetFilterModal'
import { BudgetViewModal } from '../../components/budget/BudgetViewModal/BudgetViewModal'
import { ManageViewsModal } from '../../components/budget/ManageViewsModal/ManageViewsModal'
import { ManageFiltersModal } from '../../components/budget/ManageFiltersModal/ManageFiltersModal'
import { MultiMonthSheet } from '../../components/budget/MultiMonthSheet/MultiMonthSheet'
import { TbaHero } from '../../components/budget/TbaHero/TbaHero'
import { ImportReviewGate } from '../../components/imports/ImportReviewDialog/ImportReviewGate'
import { FloatingSelectionBar } from '../../components/common/FloatingSelectionBar/FloatingSelectionBar'
import { ContextMenu, type ContextMenuItem } from '../../components/common/ContextMenu/ContextMenu'
import { useAppStore } from '../../stores/appStore'
import { useUIStore } from '../../stores/uiStore'
import { useIsMobile } from '../../hooks/useMediaQuery'
import { useSwipeNavigation } from '../../hooks/useSwipeNavigation'
import { addMonths } from '../../utils/dates'
import { useBudgets, useCreateBudget } from '../../api/budgets'
import {
  useArchiveCategories,
  useCategories,
  useCategoryGroups,
  useReorderCategories,
  useUpdateCategory,
} from '../../api/categories'
import { moveItem } from '../../utils/listOrder'
import { useDeleteCategoryFlow } from '../../components/budget/DeleteCategoryModal/useDeleteCategoryFlow'
import './BudgetPage.css'
import { confirmAsync } from '../../stores/confirmStore'

export function BudgetPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const setBudgetId = useAppStore((s) => s.setCurrentBudgetId)
  const month = useAppStore((s) => s.selectedMonth)
  const setSelectedMonth = useAppStore((s) => s.setSelectedMonth)

  const selectedCategoryIds = useUIStore((s) => s.selectedCategoryIds)
  const clearCategorySelection = useUIStore((s) => s.clearCategorySelection)
  const activeModal = useUIStore((s) => s.activeModal)
  const closeModal = useUIStore((s) => s.closeModal)
  const mobileInspectorOpen = useUIStore((s) => s.mobileInspectorOpen)
  const closeMobileInspector = useUIStore((s) => s.closeMobileInspector)
  const multiMonthOpen = useUIStore((s) => s.multiMonthOpen)
  // The sheet's Move up/down follow the grid's own rule: only on the budget's
  // own arrangement, with nothing filtered away.
  const activeViewId = useUIStore((s) => s.activeViewId)
  const activeFilterId = useUIStore((s) => s.activeFilterId)
  const activeQuickFilter = useUIStore((s) => s.activeQuickFilter)
  const categorySearch = useUIStore((s) => s.categorySearch)
  const canReorder =
    !activeViewId && !activeFilterId && !activeQuickFilter && !categorySearch.trim()
  const isMobile = useIsMobile()
  const swipeHandlers = useSwipeNavigation(
    () => setSelectedMonth(addMonths(month, -1)),
    () => setSelectedMonth(addMonths(month, 1))
  )

  const { data: budgets } = useBudgets()
  const { data: categoryGroups = [] } = useCategoryGroups(budgetId)
  const { data: categories = [] } = useCategories(budgetId)
  const updateCategory = useUpdateCategory(budgetId ?? '')
  const archiveCategories = useArchiveCategories(budgetId ?? '')
  const reorderCategories = useReorderCategories(budgetId ?? '')
  const { requestDelete, modal: deleteModal } = useDeleteCategoryFlow(
    budgetId ?? '',
    clearCategorySelection
  )
  const createBudget = useCreateBudget()

  const [newName, setNewName] = useState('')
  const [moveMenuOpen, setMoveMenuOpen] = useState(false)
  const [moveMenuPos, setMoveMenuPos] = useState({ x: 0, y: 0 })
  const moveRef = useRef<HTMLButtonElement>(null)

  // Auto-select first budget if none selected
  if (!budgetId && budgets && budgets.length > 0) {
    setBudgetId(budgets[0].id)
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!newName.trim()) return
    const budget = await createBudget.mutateAsync({ name: newName.trim() })
    setBudgetId(budget.id)
    setNewName('')
  }

  function handleMoveToGroupClick() {
    const rect = moveRef.current?.getBoundingClientRect()
    if (rect) setMoveMenuPos({ x: rect.left, y: rect.top - 10 })
    setMoveMenuOpen(true)
  }

  async function handleMoveToGroup(groupId: string) {
    const ids = Array.from(selectedCategoryIds)
    await Promise.all(
      ids.map((id) => updateCategory.mutateAsync({ id, category_group_id: groupId }))
    )
    clearCategorySelection()
  }

  async function handleArchiveSelected() {
    // Routed through the archive endpoint, not a PATCH of the flag: it refuses
    // while an envelope still holds money, because an archived envelope is off
    // the budget entirely and anything left in one is unreachable. One request
    // for the whole selection, so the refusal names the envelope that stopped
    // it instead of half the rows archiving and the rest failing.
    const count = selectedCategoryIds.size
    const ok = await confirmAsync({
      title: `Archive ${count} categor${count !== 1 ? 'ies' : 'y'}?`,
      message:
        'They leave the budget but keep their history — their spending still counts in reports. Restore them any time from See archived.',
      confirmLabel: 'Archive',
    })
    if (!ok) return
    await archiveCategories.mutateAsync({ ids: Array.from(selectedCategoryIds), month })
    clearCategorySelection()
  }

  function handleDeleteSelected() {
    const count = selectedCategoryIds.size
    requestDelete({
      kind: 'categories',
      ids: Array.from(selectedCategoryIds),
      name: `${count} categor${count !== 1 ? 'ies' : 'y'}`,
    })
  }

  const selectedCount = selectedCategoryIds.size
  const groupMenuItems: ContextMenuItem[] = categoryGroups.map((g) => ({ id: g.id, label: g.name }))

  if (!budgetId) {
    return (
      <div className="budget-page">
        <div className="budget-page__no-budget">
          <p>No budget yet. Create one to get started.</p>
          <form className="budget-page__create-form" onSubmit={handleCreate}>
            <input
              type="text"
              className="budget-page__create-input"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Budget name…"
              autoFocus
            />
            <button type="submit" className="budget-page__create-btn">
              Create Budget
            </button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="budget-page" {...(isMobile ? swipeHandlers : {})}>
      {/* A fresh import lands here; the review it produced opens once. */}
      <ImportReviewGate budgetId={budgetId} />
      <TbaHero budgetId={budgetId} month={month} />
      <div className="budget-page__body">
        <div
          className={`budget-page__table-container ${selectedCount > 0 ? 'budget-page__table-container--with-bar' : ''}`}
        >
          <BudgetTable />
        </div>
        {selectedCategoryIds.size > 0 && !isMobile && <CategoryInspector budgetId={budgetId} />}
      </div>

      {isMobile && (
        <BottomSheet
          open={mobileInspectorOpen && selectedCategoryIds.size > 0}
          onClose={() => {
            closeMobileInspector()
            clearCategorySelection()
          }}
          title={
            selectedCategoryIds.size === 1
              ? (categories.find((c) => selectedCategoryIds.has(c.id))?.name ?? 'Category')
              : `${selectedCategoryIds.size} categories selected`
          }
          height="full"
          historyKey="inspector"
        >
          <CategoryInspector budgetId={budgetId} forceOpen />
          {selectedCategoryIds.size === 1 &&
            (() => {
              const selected = categories.find((c) => selectedCategoryIds.has(c.id))
              if (!selected) return null
              // Siblings in server order — the same list the grid draws.
              const siblings = categories
                .filter((c) => c.category_group_id === selected.category_group_id)
                .map((c) => c.id)
              const at = siblings.indexOf(selected.id)
              const moveBy = (delta: -1 | 1) =>
                reorderCategories.mutate({
                  groupId: selected.category_group_id,
                  categoryIds: [...moveItem(siblings, at, at + delta)],
                })
              return (
                <CategoryMobileActions
                  budgetId={budgetId}
                  category={selected}
                  onDone={() => {
                    closeMobileInspector()
                    clearCategorySelection()
                  }}
                  onMoveUp={canReorder && at > 0 ? () => moveBy(-1) : undefined}
                  onMoveDown={canReorder && at < siblings.length - 1 ? () => moveBy(1) : undefined}
                />
              )
            })()}
        </BottomSheet>
      )}

      {selectedCount > 0 && (
        <FloatingSelectionBar
          label={`${selectedCount} categor${selectedCount !== 1 ? 'ies' : 'y'} selected`}
          onClose={clearCategorySelection}
        >
          <button ref={moveRef} className="fsb__btn" onClick={handleMoveToGroupClick}>
            <FolderInput size={14} />
            Move to Group
          </button>
          <FloatingSelectionBar.Button
            onClick={handleArchiveSelected}
            title={`Archive ${selectedCount} categories`}
          >
            <Archive size={14} />
            Archive
          </FloatingSelectionBar.Button>
          <FloatingSelectionBar.Button
            onClick={handleDeleteSelected}
            title={`Delete ${selectedCount} categories`}
          >
            <Trash2 size={14} />
            Delete
          </FloatingSelectionBar.Button>
          {moveMenuOpen && (
            <ContextMenu
              items={groupMenuItems}
              onSelect={(id) => {
                handleMoveToGroup(id)
                setMoveMenuOpen(false)
              }}
              onClose={() => setMoveMenuOpen(false)}
              position={{ x: moveMenuPos.x, y: moveMenuPos.y - 160 }}
            />
          )}
        </FloatingSelectionBar>
      )}

      {/* One slot, so these are alternatives rather than four independent
          conditions that could all be true. */}
      {activeModal?.kind === 'filter' && (
        <BudgetFilterModal
          budgetId={budgetId}
          filterId={activeModal.editingId}
          onClose={closeModal}
        />
      )}
      {activeModal?.kind === 'view' && (
        <BudgetViewModal budgetId={budgetId} viewId={activeModal.editingId} onClose={closeModal} />
      )}
      {activeModal?.kind === 'manage-views' && (
        <ManageViewsModal budgetId={budgetId} onClose={closeModal} />
      )}
      {activeModal?.kind === 'manage-filters' && (
        <ManageFiltersModal budgetId={budgetId} onClose={closeModal} />
      )}
      {!isMobile && multiMonthOpen && <MultiMonthSheet budgetId={budgetId} />}
      {deleteModal}
    </div>
  )
}
