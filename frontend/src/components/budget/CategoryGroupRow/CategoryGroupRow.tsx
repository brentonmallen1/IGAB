import { useRef, useState } from 'react'
import { ChevronDown, ChevronRight, EyeOff, Pencil, Plus, Trash2 } from 'lucide-react'
import { useUIStore } from '../../../stores/uiStore'
import {
  useCreateCategory,
  useDeleteCategoryGroup,
  useUpdateCategoryGroup,
} from '../../../api/categories'
import { CategoryRow } from '../CategoryRow/CategoryRow'
import { useFormatters } from '../../../hooks/useFormatters'
import type { Category, CategoryBalance, CategoryGroup } from '../../../types'
import './CategoryGroupRow.css'



interface Props {
  group: CategoryGroup
  categories: Category[]
  balanceMap: Map<string, CategoryBalance>
  budgetId: string
  month: string
}

export function CategoryGroupRow({ group, categories, balanceMap, budgetId, month }: Props) {
  const { formatMoney } = useFormatters()
  const collapsedGroups = useUIStore((s) => s.collapsedGroups)
  const toggleGroup = useUIStore((s) => s.toggleGroupExpanded)
  const selectedCategoryIds = useUIStore((s) => s.selectedCategoryIds)
  const selectGroupCategories = useUIStore((s) => s.selectGroupCategories)
  const anySelected = selectedCategoryIds.size > 0
  const categoryIds = categories.map((c) => c.id)
  const allGroupSelected = categoryIds.length > 0 && categoryIds.every((id) => selectedCategoryIds.has(id))
  const someGroupSelected = categoryIds.some((id) => selectedCategoryIds.has(id))
  const isExpanded = !collapsedGroups.has(group.id)

  const [isRenaming, setIsRenaming] = useState(false)
  const [renameValue, setRenameValue] = useState('')
  const [isAddingCategory, setIsAddingCategory] = useState(false)
  const [newCatName, setNewCatName] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)

  const renameRef = useRef<HTMLInputElement>(null)
  const addCatRef = useRef<HTMLInputElement>(null)

  const updateGroup = useUpdateCategoryGroup(budgetId)
  const deleteGroup = useDeleteCategoryGroup(budgetId)
  const createCategory = useCreateCategory(budgetId)

  const groupAssigned = categories.reduce((sum, cat) => sum + Number(balanceMap.get(cat.id)?.assigned ?? 0), 0)
  const groupActivity = categories.reduce((sum, cat) => sum + Number(balanceMap.get(cat.id)?.activity ?? 0), 0)
  const groupAvailable = categories.reduce((sum, cat) => sum + Number(balanceMap.get(cat.id)?.available ?? 0), 0)

  function startRename() {
    setRenameValue(group.name)
    setIsRenaming(true)
    setTimeout(() => renameRef.current?.select(), 0)
  }

  function commitRename() {
    const name = renameValue.trim()
    if (name && name !== group.name) updateGroup.mutate({ id: group.id, name })
    setIsRenaming(false)
  }

  function handleRenameKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter') { e.preventDefault(); commitRename() }
    if (e.key === 'Escape') setIsRenaming(false)
  }

  function handleHide() {
    updateGroup.mutate({ id: group.id, is_hidden: true })
  }

  function handleDelete() {
    deleteGroup.mutate(group.id)
  }

  function startAddCategory() {
    setNewCatName('')
    setIsAddingCategory(true)
    if (!isExpanded) toggleGroup(group.id)
    setTimeout(() => addCatRef.current?.focus(), 50)
  }

  function commitAddCategory() {
    const name = newCatName.trim()
    if (name) createCategory.mutate({ category_group_id: group.id, name, sort_order: categories.length })
    setIsAddingCategory(false)
    setNewCatName('')
  }

  function handleAddCatKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter') { e.preventDefault(); commitAddCategory() }
    if (e.key === 'Escape') { setIsAddingCategory(false); setNewCatName('') }
  }

  return (
    <div className="category-group-row">
      <div className="category-group-row__header">
        <button
          className="category-group-row__toggle"
          onClick={() => toggleGroup(group.id)}
          aria-expanded={isExpanded}
          aria-label={isExpanded ? 'Collapse group' : 'Expand group'}
        >
          {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>

        <div className={`category-group-row__checkbox ${anySelected ? 'category-group-row__checkbox--visible' : ''}`}>
          <input
            type="checkbox"
            checked={allGroupSelected}
            ref={(el) => { if (el) el.indeterminate = someGroupSelected && !allGroupSelected }}
            onChange={() => selectGroupCategories(categoryIds)}
            onClick={(e) => e.stopPropagation()}
            aria-label={`Select all in ${group.name}`}
          />
        </div>

        {isRenaming ? (
          <input
            ref={renameRef}
            className="category-group-row__rename-input"
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onBlur={commitRename}
            onKeyDown={handleRenameKey}
          />
        ) : (
          <span
            className="category-group-row__name"
            onDoubleClick={!group.is_system ? startRename : undefined}
          >
            {group.name}
          </span>
        )}

        {!isRenaming && (
          <div className="category-group-row__actions">
            {!group.is_system && (
              <button className="category-group-row__action-btn" onClick={startRename} aria-label={`Rename group ${group.name}`} title="Rename">
                <Pencil size={12} />
              </button>
            )}
            {!group.is_system && (
              <button className="category-group-row__action-btn" onClick={handleHide} aria-label={`Hide group ${group.name}`} title="Hide group">
                <EyeOff size={12} />
              </button>
            )}
            {!group.is_system && (
              confirmDelete ? (
                <>
                  <button
                    className="category-group-row__action-btn category-group-row__action-btn--confirm"
                    onClick={handleDelete}
                    aria-label="Confirm delete"
                    title="Confirm delete"
                  >
                    ✓
                  </button>
                  <button
                    className="category-group-row__action-btn"
                    onClick={() => setConfirmDelete(false)}
                    aria-label="Cancel delete"
                    title="Cancel"
                  >
                    ✗
                  </button>
                </>
              ) : (
                <button
                  className="category-group-row__action-btn category-group-row__action-btn--danger"
                  onClick={() => setConfirmDelete(true)}
                  aria-label={`Delete group ${group.name}`}
                  title="Delete group"
                >
                  <Trash2 size={12} />
                </button>
              )
            )}
            <button className="category-group-row__action-btn" onClick={startAddCategory} aria-label={`Add category to ${group.name}`} title="Add category">
              <Plus size={12} />
            </button>
          </div>
        )}

        <span className="category-group-row__assigned tabular">{formatMoney(groupAssigned)}</span>
        <span className="category-group-row__activity tabular">{formatMoney(groupActivity)}</span>
        <span
          className={`category-group-row__available tabular ${groupAvailable < 0 ? 'negative' : groupAvailable > 0 ? 'positive' : 'zero'}`}
        >
          {formatMoney(groupAvailable)}
        </span>

        {/* Collapsed groups on mobile hide the assigned/activity columns —
            this sub-line keeps the totals visible (desktop: display none) */}
        {!isExpanded && (
          <span className="category-group-row__mobile-summary tabular">
            Assigned {formatMoney(groupAssigned)} · Activity {formatMoney(groupActivity)}
          </span>
        )}
      </div>

      {isExpanded && (
        <div className="category-group-row__categories">
          {categories.map((cat) => (
            <CategoryRow
              key={cat.id}
              category={cat}
              balance={balanceMap.get(cat.id)}
              budgetId={budgetId}
              month={month}
              orderedIds={categoryIds}
            />
          ))}
          {isAddingCategory && (
            <div className="category-group-row__add-cat-row">
              <div />
              <input
                ref={addCatRef}
                className="category-group-row__add-cat-input"
                value={newCatName}
                onChange={(e) => setNewCatName(e.target.value)}
                onBlur={commitAddCategory}
                onKeyDown={handleAddCatKey}
                placeholder="Category name…"
              />
            </div>
          )}
          {!isAddingCategory && (
            <button className="category-group-row__add-cat-btn" onClick={startAddCategory}>
              <Plus size={11} /> Add Category
            </button>
          )}
        </div>
      )}
    </div>
  )
}
