import { ChevronRight, Eye, EyeOff, Trash2, X } from 'lucide-react'
import { useUIStore } from '../../../stores/uiStore'
import { useAppStore } from '../../../stores/appStore'
import { useBudgetMonth } from '../../../api/budgets'
import { useCategories, useDeleteCategory, useUpdateCategory } from '../../../api/categories'
import { confirmAsync } from '../../../stores/confirmStore'
import { addMonths } from '../../../utils/dates'
import { AvailableBreakdown } from './AvailableBreakdown'
import { TargetSection } from './TargetSection'
import { AutoAssignSection } from './AutoAssignSection'
import { CategoryNotesSection } from './CategoryNotesSection'
import { CategorySubtitleSection } from './CategorySubtitleSection'
import { TagsSection } from './TagsSection'
import { MonthSummary } from './MonthSummary'
import './CategoryInspector.css'

interface Props {
  budgetId: string
  /** Skip the collapsed-strip state (used when rendered inside the mobile sheet) */
  forceOpen?: boolean
}

function formatMonthLabel(month: string) {
  const date = new Date(month + 'T00:00:00')
  return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
}

export function CategoryInspector({ budgetId, forceOpen = false }: Props) {
  const month = useAppStore((s) => s.selectedMonth)
  const selectedCategoryIds = useUIStore((s) => s.selectedCategoryIds)
  const categoryInspectorOpen = useUIStore((s) => s.categoryInspectorOpen)
  const setCategoryInspectorOpen = useUIStore((s) => s.setCategoryInspectorOpen)
  const clearCategorySelection = useUIStore((s) => s.clearCategorySelection)

  const { data: budgetMonth } = useBudgetMonth(budgetId, month)
  const { data: prevBudgetMonth } = useBudgetMonth(budgetId, addMonths(month, -1))
  const { data: categories } = useCategories(budgetId)
  const updateCategory = useUpdateCategory(budgetId)
  const deleteCategory = useDeleteCategory(budgetId)

  const selectedIds = Array.from(selectedCategoryIds)
  const count = selectedIds.length

  const selectedCategories = categories?.filter((c) => selectedCategoryIds.has(c.id)) ?? []
  const allCategoryIds = categories?.map((c) => c.id) ?? []

  const selectedBalances = budgetMonth?.category_balances.filter((b) =>
    selectedCategoryIds.has(b.category_id)
  ) ?? []
  const prevBalances = prevBudgetMonth?.category_balances.filter((b) =>
    selectedCategoryIds.has(b.category_id)
  )

  const isSingle = count === 1
  const singleCategory = isSingle ? selectedCategories[0] : null

  const allHidden = count > 0 && selectedCategories.length === count && selectedCategories.every((c) => c.is_hidden)

  async function handleHideSelected() {
    if (!allHidden && count > 1) {
      const ok = await confirmAsync({
        title: `Hide ${count} categories?`,
        message: 'Hidden categories keep their history and can be unhidden later.',
        confirmLabel: 'Hide',
      })
      if (!ok) return
    }
    await Promise.all(selectedIds.map((id) => updateCategory.mutateAsync({ id, is_hidden: !allHidden })))
    clearCategorySelection()
  }

  async function handleDeleteSelected() {
    const ok = await confirmAsync({
      title: isSingle
        ? `Delete ${singleCategory?.name ?? 'category'}?`
        : `Delete ${count} categories?`,
      message: 'Transactions will lose their category.',
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (!ok) return
    await Promise.all(selectedIds.map((id) => deleteCategory.mutateAsync(id)))
    clearCategorySelection()
  }

  const headerTitle = count === 0
    ? formatMonthLabel(month)
    : isSingle
      ? (singleCategory?.name ?? 'Category')
      : `${count} categories selected`

  return (
    <div className={`category-inspector ${categoryInspectorOpen || forceOpen ? '' : 'category-inspector--collapsed'}`}>
      {!categoryInspectorOpen && !forceOpen ? (
        <button
          className="category-inspector__expand-btn"
          onClick={() => setCategoryInspectorOpen(true)}
          title="Open inspector"
          aria-label="Open category inspector"
        >
          <ChevronRight size={14} />
        </button>
      ) : (
        <>
          {/* Inside the mobile sheet the BottomSheet owns title + dismissal —
              a second header with its own X would leave the sheet's history
              entry dangling (clearCategorySelection alone collapses the sheet
              without unwinding useHistoryDismissable). */}
          {!forceOpen && (
            <div className="category-inspector__header">
              <button
                className="category-inspector__collapse-btn"
                onClick={() => setCategoryInspectorOpen(false)}
                title="Collapse inspector"
                aria-label="Collapse category inspector"
              >
                <ChevronRight size={14} />
              </button>
              <span className="category-inspector__title" title={headerTitle}>{headerTitle}</span>
              {count > 0 && (
                <button
                  className="category-inspector__close-btn"
                  onClick={clearCategorySelection}
                  title="Clear selection"
                  aria-label="Clear category selection"
                >
                  <X size={14} />
                </button>
              )}
            </div>
          )}

          <div className="category-inspector__body">
            {count === 0 ? (
              <MonthSummary budgetId={budgetId} allCategoryIds={allCategoryIds} categories={categories ?? []} />
            ) : (
              <>
                <AvailableBreakdown balances={selectedBalances} prevBalances={prevBalances} />

                {isSingle && singleCategory && (
                  <TargetSection categoryId={singleCategory.id} />
                )}
                {!isSingle && (
                  <div className="inspector-section">
                    <div className="inspector-section__title">Target</div>
                    <p className="inspector-multi-notice">Multiple categories selected</p>
                  </div>
                )}

                <AutoAssignSection categoryIds={selectedIds} budgetId={budgetId} />

                {isSingle && singleCategory && (
                  <CategorySubtitleSection category={singleCategory} budgetId={budgetId} />
                )}

                {isSingle && singleCategory && (
                  <CategoryNotesSection category={singleCategory} budgetId={budgetId} />
                )}

                {isSingle && singleCategory && (
                  <TagsSection category={singleCategory} budgetId={budgetId} />
                )}

                {/* Mobile sheet gets these from CategoryMobileActions instead */}
                {!forceOpen && (
                  <div className="category-inspector__manage">
                    <button className="inspector-btn category-inspector__manage-btn" onClick={handleHideSelected}>
                      {allHidden ? <Eye size={13} /> : <EyeOff size={13} />}
                      {allHidden ? 'Unhide' : 'Hide'}
                    </button>
                    <button
                      className="inspector-btn inspector-btn--danger category-inspector__manage-btn"
                      onClick={handleDeleteSelected}
                    >
                      <Trash2 size={13} />
                      Delete
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </>
      )}
    </div>
  )
}
