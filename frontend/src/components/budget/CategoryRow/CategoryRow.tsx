import { memo, useCallback, useRef, useState } from 'react'
import { EyeOff, Pencil, Trash2 } from 'lucide-react'
import { useSetAssignment } from '../../../api/budgets'
import { useTarget } from '../../../api/targets'
import { useDeleteCategory, useUpdateCategory } from '../../../api/categories'
import { useUIStore } from '../../../stores/uiStore'
import { TargetBadge } from '../TargetBadge'
import { TargetEditor } from '../TargetEditor'
import { formatMoney, parseMoney } from '../../../utils/money'
import type { Category, CategoryBalance } from '../../../types'
import './CategoryRow.css'

interface Props {
  category: Category
  balance: CategoryBalance | undefined
  budgetId: string
  month: string
  orderedIds?: string[]
}

export const CategoryRow = memo(function CategoryRow({ category, balance, budgetId, month, orderedIds }: Props) {
  const [isEditing, setIsEditing] = useState(false)
  const [editValue, setEditValue] = useState('')
  const [showTargetEditor, setShowTargetEditor] = useState(false)
  const [isRenaming, setIsRenaming] = useState(false)
  const [renameValue, setRenameValue] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)

  const inputRef = useRef<HTMLInputElement>(null)
  const renameRef = useRef<HTMLInputElement>(null)

  const setAssignment = useSetAssignment(budgetId)
  const updateCategory = useUpdateCategory(budgetId)
  const deleteCategory = useDeleteCategory(budgetId)
  const { data: target } = useTarget(category.id)

  const selectedCategoryIds = useUIStore((s) => s.selectedCategoryIds)
  const toggleCategorySelection = useUIStore((s) => s.toggleCategorySelection)
  const selectOnlyCategory = useUIStore((s) => s.selectOnlyCategory)
  const setCategoryInspectorOpen = useUIStore((s) => s.setCategoryInspectorOpen)
  const inspectorUserClosed = useUIStore((s) => s.inspectorUserClosed)
  const isSelected = selectedCategoryIds.has(category.id)
  const anySelected = selectedCategoryIds.size > 0

  const assigned = Number(balance?.assigned ?? 0)
  const activity = Number(balance?.activity ?? 0)
  const available = Number(balance?.available ?? 0)

  const handleStartEdit = useCallback(() => {
    setEditValue(assigned === 0 ? '' : String(assigned))
    setIsEditing(true)
    setTimeout(() => inputRef.current?.select(), 0)
  }, [assigned])

  const handleCommit = useCallback(() => {
    const amount = editValue.trim() === '' ? 0 : parseMoney(editValue)
    setAssignment.mutate({ categoryId: category.id, month, amount })
    setIsEditing(false)
  }, [editValue, category.id, month, setAssignment])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') handleCommit()
      if (e.key === 'Escape') setIsEditing(false)
    },
    [handleCommit]
  )

  function startRename() {
    setRenameValue(category.name)
    setIsRenaming(true)
    setTimeout(() => renameRef.current?.select(), 0)
  }

  function commitRename() {
    const name = renameValue.trim()
    if (name && name !== category.name) updateCategory.mutate({ id: category.id, name })
    setIsRenaming(false)
  }

  function handleRenameKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter') { e.preventDefault(); commitRename() }
    if (e.key === 'Escape') setIsRenaming(false)
  }

  function handleHide() {
    updateCategory.mutate({ id: category.id, is_hidden: true })
  }

  function handleDelete() {
    deleteCategory.mutate(category.id)
  }

  function handleCheckboxChange(e: React.ChangeEvent<HTMLInputElement>) {
    toggleCategorySelection(category.id, e.nativeEvent instanceof MouseEvent ? (e.nativeEvent as MouseEvent).shiftKey : false, orderedIds)
  }

  function handleRowClick(e: React.MouseEvent) {
    const target = e.target as Element
    if (target.closest('input, button')) return
    selectOnlyCategory(category.id)
    if (!inspectorUserClosed) setCategoryInspectorOpen(true)
  }

  const availableClass = available < 0 ? 'negative' : available > 0 ? 'positive' : 'zero'

  function getTargetStatus(): 'funded' | 'underfunded' | 'overfunded' | null {
    if (!target) return null
    const needed = Number(target.target_amount)
    if (assigned >= needed * 1.05) return 'overfunded'
    if (assigned >= needed) return 'funded'
    return 'underfunded'
  }

  const targetStatus = getTargetStatus()

  return (
    <>
      {showTargetEditor && (
        <TargetEditor
          categoryId={category.id}
          categoryName={category.name}
          existing={target ?? null}
          onClose={() => setShowTargetEditor(false)}
        />
      )}
      <div
        className={`category-row ${category.is_hidden ? 'category-row--hidden' : ''} ${isSelected ? 'category-row--selected' : ''} ${available < 0 ? 'category-row--overspent' : ''}`}
        role="row"
        onClick={handleRowClick}
        style={{ cursor: 'default' }}
      >
        <div className={`category-row__checkbox ${anySelected ? 'category-row__checkbox--visible' : ''}`}>
          <input
            type="checkbox"
            checked={isSelected}
            onChange={handleCheckboxChange}
            onClick={(e) => e.stopPropagation()}
            aria-label={`Select ${category.name}`}
          />
        </div>

        <div className="category-row__name">
          {isRenaming ? (
            <input
              ref={renameRef}
              className="category-row__name-input"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onBlur={commitRename}
              onKeyDown={handleRenameKey}
            />
          ) : (
            <>
              <span className="category-row__name-text" onDoubleClick={startRename}>
                {category.name}
              </span>
              {targetStatus ? (
                <TargetBadge status={targetStatus} onClick={() => setShowTargetEditor(true)} />
              ) : (
                <button
                  className="category-row__target-btn"
                  onClick={() => setShowTargetEditor(true)}
                  title="Set target"
                >
                  +target
                </button>
              )}
              <div className="category-row__actions">
                <button className="category-row__action-btn" onClick={startRename} title="Rename">
                  <Pencil size={11} />
                </button>
                <button className="category-row__action-btn" onClick={handleHide} title="Hide category">
                  <EyeOff size={11} />
                </button>
                {confirmDelete ? (
                  <>
                    <button
                      className="category-row__action-btn category-row__action-btn--confirm"
                      onClick={handleDelete}
                      title="Confirm delete"
                    >
                      ✓
                    </button>
                    <button
                      className="category-row__action-btn"
                      onClick={() => setConfirmDelete(false)}
                      title="Cancel"
                    >
                      ✗
                    </button>
                  </>
                ) : (
                  <button
                    className="category-row__action-btn category-row__action-btn--danger"
                    onClick={() => setConfirmDelete(true)}
                    title="Delete category"
                  >
                    <Trash2 size={11} />
                  </button>
                )}
              </div>
            </>
          )}
        </div>

        <div className="category-row__assigned">
          {isEditing ? (
            <input
              ref={inputRef}
              className="category-row__input"
              type="text"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onBlur={handleCommit}
              onKeyDown={handleKeyDown}
              placeholder="0.00"
              inputMode="decimal"
            />
          ) : (
            <button
              className="category-row__editable tabular"
              onClick={handleStartEdit}
              title="Click to edit"
            >
              {assigned === 0 ? (
                <span className="category-row__zero">—</span>
              ) : (
                formatMoney(assigned)
              )}
            </button>
          )}
        </div>

        <div className="category-row__activity tabular">
          {activity === 0 ? (
            <span className="category-row__zero">—</span>
          ) : (
            <span className={activity < 0 ? 'negative' : 'positive'}>{formatMoney(activity)}</span>
          )}
        </div>

        <div className={`category-row__available tabular ${availableClass}`}>
          {formatMoney(available)}
        </div>
      </div>
    </>
  )
})
