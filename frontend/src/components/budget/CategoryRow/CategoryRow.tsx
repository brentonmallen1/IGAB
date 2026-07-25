import React, { memo, useCallback, useRef, useState } from 'react'
import { EyeOff, Pencil, Trash2 } from 'lucide-react'
import { useSetAssignment } from '../../../api/budgets'
import { useTarget } from '../../../api/targets'
import { useDeleteCategory, useUpdateCategory } from '../../../api/categories'
import { useUIStore } from '../../../stores/uiStore'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import { useLongPress } from '../../../hooks/useLongPress'
import { TargetBadge, getTargetTooltip } from '../TargetBadge'
import { TargetEditor } from '../TargetEditor'
import { MoveMoneyPopover } from '../MoveMoneyPopover/MoveMoneyPopover'
import { MoveMoneyForm } from '../MoveMoneyPopover/MoveMoneyForm'
import { BottomSheet } from '../../common/BottomSheet/BottomSheet'
import { formatMoney, parseMoney } from '../../../utils/money'
import { today } from '../../../utils/dates'
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
  const [movePopoverPos, setMovePopoverPos] = useState<{ x: number; y: number } | null>(null)
  const [moveSheetOpen, setMoveSheetOpen] = useState(false)
  const isMobile = useIsMobile()

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
  const openMobileInspector = useUIStore((s) => s.openMobileInspector)
  const budgetRowMode = useUIStore((s) => s.budgetRowMode)
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
    if (isNaN(amount)) {
      // Unparseable input must never silently write $0 into the budget
      setIsEditing(false)
      return
    }
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
    if (isMobile) {
      // In selection mode taps toggle; otherwise a tap opens the inspector sheet
      if (anySelected) {
        toggleCategorySelection(category.id)
      } else {
        selectOnlyCategory(category.id)
        openMobileInspector()
      }
      return
    }
    selectOnlyCategory(category.id)
    if (!inspectorUserClosed) setCategoryInspectorOpen(true)
  }

  const longPress = useLongPress(() => {
    if (!anySelected) toggleCategorySelection(category.id)
  }, handleRowClick)

  const availableClass = available < 0 ? 'negative' : available > 0 ? 'positive' : 'zero'

  const isTargetExpired = !!(target?.target_date && String(target.target_date) < today())

  function getTargetStatus(): 'funded' | 'underfunded' | null {
    if (!target || isTargetExpired) return null
    const needed = Number(target.target_amount)
    if (assigned >= needed) return 'funded'
    return 'underfunded'
  }

  const targetStatus = getTargetStatus()

  const targetProgress = (() => {
    if (!target || isTargetExpired) return null
    const amount = Number(target.target_amount)
    if (amount <= 0) return null
    const numerator = target.target_type === 'savings_balance' ? available : assigned
    return Math.min(Math.max(numerator / amount, 0), 1)
  })()

  const monthlyNeeded = (() => {
    if (!target || target.target_type !== 'savings_balance' || !target.target_date) return null
    const targetDate = new Date(target.target_date + 'T00:00:00')
    const now = new Date()
    const monthsLeft = (targetDate.getFullYear() - now.getFullYear()) * 12 + (targetDate.getMonth() - now.getMonth())
    if (monthsLeft <= 0) return null
    const remaining = Number(target.target_amount) - available
    if (remaining <= 0) return 0
    return remaining / monthsLeft
  })()

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
        className={`category-row ${category.is_hidden ? 'category-row--hidden' : ''} ${isSelected ? 'category-row--selected' : ''} ${anySelected ? 'category-row--any-selected' : ''} ${available < 0 ? 'category-row--overspent' : ''} ${targetProgress !== null && budgetRowMode === 'expanded' ? 'category-row--has-pill' : ''}`}
        role="row"
        {...(isMobile ? longPress : { onClick: handleRowClick })}
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
              <span
                className="category-row__name-text"
                onDoubleClick={startRename}
                title="Double-click to rename"
              >
                {category.name}
              </span>
              {isTargetExpired ? (
                <button
                  className="category-row__target-expired"
                  title="Target date has passed — click to update"
                  aria-label={`${category.name} target expired — click to update`}
                  onClick={(e) => { e.stopPropagation(); setShowTargetEditor(true) }}
                >
                  expired
                </button>
              ) : targetStatus ? (
                budgetRowMode === 'compressed' ? (
                  <button
                    className={`category-row__target-led category-row__target-led--${targetStatus}`}
                    title={getTargetTooltip(targetStatus, monthlyNeeded ?? undefined)}
                    aria-label={`${category.name}: ${getTargetTooltip(targetStatus, monthlyNeeded ?? undefined)}`}
                    onClick={(e) => { e.stopPropagation(); setShowTargetEditor(true) }}
                  />
                ) : (
                  <TargetBadge
                    status={targetStatus}
                    monthlyNeeded={monthlyNeeded ?? undefined}
                    onClick={() => setShowTargetEditor(true)}
                  />
                )
              ) : (
                <button
                  className="category-row__target-btn"
                  onClick={() => setShowTargetEditor(true)}
                  title="Set target"
                >
                  +target
                </button>
              )}
              <div className="category-row__actions" role="group" aria-label={`${category.name} actions`}>
                <button className="category-row__action-btn" onClick={startRename} title="Rename" aria-label={`Rename ${category.name}`}>
                  <Pencil size={11} />
                </button>
                <button className="category-row__action-btn" onClick={handleHide} title="Hide category" aria-label={`Hide ${category.name}`}>
                  <EyeOff size={11} />
                </button>
                {confirmDelete ? (
                  <>
                    <button
                      className="category-row__action-btn category-row__action-btn--confirm"
                      onClick={handleDelete}
                      title="Confirm delete"
                      aria-label={`Confirm delete ${category.name}`}
                    >
                      ✓
                    </button>
                    <button
                      className="category-row__action-btn"
                      onClick={() => setConfirmDelete(false)}
                      title="Cancel"
                      aria-label="Cancel delete"
                    >
                      ✗
                    </button>
                  </>
                ) : (
                  <button
                    className="category-row__action-btn category-row__action-btn--danger"
                    onClick={() => setConfirmDelete(true)}
                    title="Delete category"
                    aria-label={`Delete ${category.name}`}
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

        <div
          className={`category-row__available tabular ${availableClass} category-row__available--clickable`}
          onClick={(e) => {
            e.stopPropagation()
            if (isMobile) {
              setMoveSheetOpen(true)
              return
            }
            const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
            setMovePopoverPos({ x: Math.max(8, rect.right - 280), y: rect.bottom + 4 })
          }}
          title={
            available < 0
              ? 'Overspent — click to cover from another envelope'
              : 'Click to move money to another envelope'
          }
        >
          {formatMoney(available)}
        </div>

        {movePopoverPos && !isMobile && (
          <MoveMoneyPopover
            budgetId={budgetId}
            month={month}
            category={category}
            available={available}
            position={movePopoverPos}
            onClose={() => setMovePopoverPos(null)}
          />
        )}

      </div>

      {isMobile && (
        <BottomSheet
          open={moveSheetOpen}
          onClose={() => setMoveSheetOpen(false)}
          historyKey={`move-money-${category.id}`}
        >
          <div className="category-row__move-sheet">
            <MoveMoneyForm
              budgetId={budgetId}
              month={month}
              category={category}
              available={available}
              onClose={() => setMoveSheetOpen(false)}
            />
          </div>
        </BottomSheet>
      )}

      {targetProgress !== null && targetStatus !== null && budgetRowMode === 'expanded' && (() => {
        const pct = Math.round(targetProgress * 100)
        const isSavings = target!.target_type === 'savings_balance'
        const amountRemaining = Math.max(0, Number(target!.target_amount) - (isSavings ? available : assigned))
        const pctInside = targetProgress > 0.22

        return (
          <div className="target-pill-row">
            <div className="target-pill-wrap">
              <div className={`target-pill-track target-pill-track--${targetStatus}`}>
                <div
                  className={`target-pill-fill target-pill-fill--${targetStatus}`}
                  style={{ '--fill-scale': targetProgress } as React.CSSProperties}
                />
                <span
                  className={`target-pill-pct ${pctInside ? 'target-pill-pct--inside' : 'target-pill-pct--outside'}`}
                  style={pctInside ? { left: `${targetProgress * 100}%` } : undefined}
                >
                  {pct}%
                </span>
              </div>
            </div>
            <div className="target-pill-stats">
              {targetStatus === 'funded' ? (
                <span className="target-pill-stat target-pill-stat--funded">Funded</span>
              ) : amountRemaining > 0 ? (
                <span className="target-pill-stat">
                  {isSavings ? `Save ${formatMoney(amountRemaining)} more` : `Need ${formatMoney(amountRemaining)} this month`}
                </span>
              ) : null}
              {monthlyNeeded !== null && monthlyNeeded > 0 && (
                <span className="target-pill-stat">{formatMoney(monthlyNeeded)}/mo to goal</span>
              )}
            </div>
          </div>
        )
      })()}
    </>
  )
})
