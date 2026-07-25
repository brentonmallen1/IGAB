import { useRef, useState } from 'react'
import { FolderInput, Trash2 } from 'lucide-react'
import { BudgetTable } from '../../components/budget/BudgetTable/BudgetTable'
import { CategoryInspector } from '../../components/budget/CategoryInspector/CategoryInspector'
import { CategoryMobileActions } from '../../components/budget/CategoryInspector/CategoryMobileActions'
import { BottomSheet } from '../../components/common/BottomSheet/BottomSheet'
import { BudgetViewModal } from '../../components/budget/BudgetViewModal/BudgetViewModal'
import { ManageViewsModal } from '../../components/budget/ManageViewsModal/ManageViewsModal'
import { TbaHero } from '../../components/budget/TbaHero/TbaHero'
import { FloatingSelectionBar } from '../../components/common/FloatingSelectionBar/FloatingSelectionBar'
import { ContextMenu, type ContextMenuItem } from '../../components/common/ContextMenu/ContextMenu'
import { useAppStore } from '../../stores/appStore'
import { useUIStore } from '../../stores/uiStore'
import { useIsMobile } from '../../hooks/useMediaQuery'
import { useBudgets, useCreateBudget } from '../../api/budgets'
import { useCategories, useCategoryGroups, useUpdateCategory, useDeleteCategory } from '../../api/categories'
import './BudgetPage.css'

export function BudgetPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const setBudgetId = useAppStore((s) => s.setCurrentBudgetId)
  const month = useAppStore((s) => s.selectedMonth)

  const selectedCategoryIds = useUIStore((s) => s.selectedCategoryIds)
  const clearCategorySelection = useUIStore((s) => s.clearCategorySelection)
  const isViewModalOpen = useUIStore((s) => s.isViewModalOpen)
  const editingViewId = useUIStore((s) => s.editingViewId)
  const closeViewModal = useUIStore((s) => s.closeViewModal)
  const isManageViewsModalOpen = useUIStore((s) => s.isManageViewsModalOpen)
  const closeManageViewsModal = useUIStore((s) => s.closeManageViewsModal)
  const mobileInspectorOpen = useUIStore((s) => s.mobileInspectorOpen)
  const closeMobileInspector = useUIStore((s) => s.closeMobileInspector)
  const isMobile = useIsMobile()

  const { data: budgets } = useBudgets()
  const { data: categoryGroups = [] } = useCategoryGroups(budgetId)
  const { data: categories = [] } = useCategories(budgetId)
  const updateCategory = useUpdateCategory(budgetId ?? '')
  const deleteCategory = useDeleteCategory(budgetId ?? '')
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
    await Promise.all(ids.map((id) => updateCategory.mutateAsync({ id, category_group_id: groupId })))
    clearCategorySelection()
  }

  async function handleDeleteSelected() {
    const count = selectedCategoryIds.size
    if (!confirm(`Delete ${count} categor${count !== 1 ? 'ies' : 'y'}? Transactions will lose their category.`)) return
    const ids = Array.from(selectedCategoryIds)
    await Promise.all(ids.map((id) => deleteCategory.mutateAsync(id)))
    clearCategorySelection()
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
    <div className="budget-page">
      <TbaHero budgetId={budgetId} month={month} />
      <div className="budget-page__body">
        <div className="budget-page__table-container">
          <BudgetTable />
        </div>
        {selectedCategoryIds.size > 0 && !isMobile && (
          <CategoryInspector budgetId={budgetId} />
        )}
      </div>

      {isMobile && (
        <BottomSheet
          open={mobileInspectorOpen && selectedCategoryIds.size > 0}
          onClose={() => {
            closeMobileInspector()
            clearCategorySelection()
          }}
          height="full"
          historyKey="inspector"
        >
          <CategoryInspector budgetId={budgetId} forceOpen />
          {selectedCategoryIds.size === 1 && (() => {
            const selected = categories.find((c) => selectedCategoryIds.has(c.id))
            return selected ? (
              <CategoryMobileActions
                budgetId={budgetId}
                category={selected}
                onDone={() => {
                  closeMobileInspector()
                  clearCategorySelection()
                }}
              />
            ) : null
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
            onClick={handleDeleteSelected}
            title={`Delete ${selectedCount} categories`}
          >
            <Trash2 size={14} />
            Delete
          </FloatingSelectionBar.Button>
          {moveMenuOpen && (
            <ContextMenu
              items={groupMenuItems}
              onSelect={(id) => { handleMoveToGroup(id); setMoveMenuOpen(false) }}
              onClose={() => setMoveMenuOpen(false)}
              position={{ x: moveMenuPos.x, y: moveMenuPos.y - 160 }}
            />
          )}
        </FloatingSelectionBar>
      )}

      {isViewModalOpen && (
        <BudgetViewModal
          budgetId={budgetId}
          viewId={editingViewId}
          onClose={closeViewModal}
        />
      )}
      {isManageViewsModalOpen && (
        <ManageViewsModal
          budgetId={budgetId}
          onClose={closeManageViewsModal}
        />
      )}
    </div>
  )
}
