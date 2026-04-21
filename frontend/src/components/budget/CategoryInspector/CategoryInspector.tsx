import { ChevronRight, X } from 'lucide-react'
import { useUIStore } from '../../../stores/uiStore'
import { useAppStore } from '../../../stores/appStore'
import { useBudgetMonth } from '../../../api/budgets'
import { useCategories } from '../../../api/categories'
import { AvailableBreakdown } from './AvailableBreakdown'
import { TargetSection } from './TargetSection'
import { AutoAssignSection } from './AutoAssignSection'
import { CategoryNotesSection } from './CategoryNotesSection'
import { MonthSummary } from './MonthSummary'
import './CategoryInspector.css'

interface Props {
  budgetId: string
}

function formatMonthLabel(month: string) {
  const date = new Date(month + 'T00:00:00')
  return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
}

export function CategoryInspector({ budgetId }: Props) {
  const month = useAppStore((s) => s.selectedMonth)
  const selectedCategoryIds = useUIStore((s) => s.selectedCategoryIds)
  const categoryInspectorOpen = useUIStore((s) => s.categoryInspectorOpen)
  const setCategoryInspectorOpen = useUIStore((s) => s.setCategoryInspectorOpen)
  const clearCategorySelection = useUIStore((s) => s.clearCategorySelection)

  const { data: budgetMonth } = useBudgetMonth(budgetId, month)
  const { data: categories } = useCategories(budgetId)

  const selectedIds = Array.from(selectedCategoryIds)
  const count = selectedIds.length

  const selectedCategories = categories?.filter((c) => selectedCategoryIds.has(c.id)) ?? []
  const allCategoryIds = categories?.map((c) => c.id) ?? []

  const selectedBalances = budgetMonth?.category_balances.filter((b) =>
    selectedCategoryIds.has(b.category_id)
  ) ?? []

  const isSingle = count === 1
  const singleCategory = isSingle ? selectedCategories[0] : null

  const headerTitle = count === 0
    ? formatMonthLabel(month)
    : isSingle
      ? (singleCategory?.name ?? 'Category')
      : `${count} categories selected`

  return (
    <div className={`category-inspector ${categoryInspectorOpen ? '' : 'category-inspector--collapsed'}`}>
      {!categoryInspectorOpen ? (
        <button
          className="category-inspector__expand-btn"
          onClick={() => setCategoryInspectorOpen(true)}
          title="Open inspector"
        >
          <ChevronRight size={14} />
        </button>
      ) : (
        <>
          <div className="category-inspector__header">
            <button
              className="category-inspector__collapse-btn"
              onClick={() => setCategoryInspectorOpen(false)}
              title="Collapse inspector"
            >
              <ChevronRight size={14} />
            </button>
            <span className="category-inspector__title" title={headerTitle}>{headerTitle}</span>
            {count > 0 && (
              <button
                className="category-inspector__close-btn"
                onClick={clearCategorySelection}
                title="Clear selection"
              >
                <X size={14} />
              </button>
            )}
          </div>

          <div className="category-inspector__body">
            {count === 0 ? (
              <MonthSummary budgetId={budgetId} allCategoryIds={allCategoryIds} categories={categories ?? []} />
            ) : (
              <>
                <AvailableBreakdown balances={selectedBalances} />

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
                  <CategoryNotesSection category={singleCategory} budgetId={budgetId} />
                )}
              </>
            )}
          </div>
        </>
      )}
    </div>
  )
}
