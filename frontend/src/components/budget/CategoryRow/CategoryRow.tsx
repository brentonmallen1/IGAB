import React, { memo, useCallback, useRef, useState } from 'react'
import { Pencil, Plus } from 'lucide-react'
import { useSetAssignment } from '../../../api/budgets'
import { useTarget } from '../../../api/targets'
import {
  targetMeasuresBalance,
  targetNeededThisMonth,
  targetProgress as computeTargetProgress,
  targetStatus as computeTargetStatus,
} from '../../../utils/targets'
import { useUpdateCategory } from '../../../api/categories'
import { useUIStore } from '../../../stores/uiStore'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import { useLongPress } from '../../../hooks/useLongPress'
import { TargetBadge, getTargetTooltip } from '../TargetBadge'
import { TargetEditor } from '../TargetEditor'
import { MoveMoneyPopover } from '../MoveMoneyPopover/MoveMoneyPopover'
import { MoveMoneyForm } from '../MoveMoneyPopover/MoveMoneyForm'
import { BottomSheet } from '../../common/BottomSheet/BottomSheet'
import { TransactionEditor } from '../../transactions/TransactionEditor/TransactionEditor'
import { CategoryTransactionsModal } from '../CategoryTransactionsModal/CategoryTransactionsModal'
import { toCents } from '../../../utils/money'
import { parseAssignmentInput } from '../../../utils/amountExpression'
import { AmountInput } from '../../common/AmountInput/AmountInput'
import { today } from '../../../utils/dates'
import { useFormatters } from '../../../hooks/useFormatters'
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
  const [subtitleValue, setSubtitleValue] = useState('')
  const [movePopoverPos, setMovePopoverPos] = useState<{ x: number; y: number } | null>(null)
  const [moveSheetOpen, setMoveSheetOpen] = useState(false)
  const [showAddTxn, setShowAddTxn] = useState(false)
  const [showTxnList, setShowTxnList] = useState(false)
  const isMobile = useIsMobile()
  const { formatMoney } = useFormatters()

  const inputRef = useRef<HTMLInputElement>(null)
  const renameRef = useRef<HTMLInputElement>(null)
  // True while a keyboard commit/cancel is in flight, so blur doesn't re-commit
  const committedRef = useRef(false)

  const setAssignment = useSetAssignment(budgetId)
  const updateCategory = useUpdateCategory(budgetId)
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
    committedRef.current = false
    setEditValue(assigned === 0 ? '' : String(assigned))
    setIsEditing(true)
    setTimeout(() => inputRef.current?.select(), 0)
  }, [assigned])

  const handleCommit = useCallback(() => {
    // Expression-aware: "+50" / "*2" adjust the current assignment
    const amount = editValue.trim() === '' ? 0 : parseAssignmentInput(editValue, assigned)
    if (isNaN(amount)) {
      // Unparseable input must never silently write $0 into the budget
      setIsEditing(false)
      return
    }
    setAssignment.mutate({ categoryId: category.id, month, amount })
    setIsEditing(false)
  }, [editValue, assigned, category.id, month, setAssignment])

  // Open the adjacent visible row's assignment editor. DOM order handles
  // groups, collapse, and filtering for free.
  const moveToAdjacent = useCallback(
    (dir: 1 | -1) => {
      const cells = Array.from(document.querySelectorAll<HTMLElement>('[data-assign-id]'))
      const idx = cells.findIndex((el) => el.dataset.assignId === category.id)
      if (idx === -1) return
      cells[idx + dir]?.querySelector<HTMLElement>('button.category-row__editable')?.click()
    },
    [category.id]
  )

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === 'ArrowDown') {
        e.preventDefault()
        committedRef.current = true
        handleCommit()
        moveToAdjacent(1)
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        committedRef.current = true
        handleCommit()
        moveToAdjacent(-1)
      } else if (e.key === 'Escape') {
        committedRef.current = true
        setIsEditing(false)
      }
    },
    [handleCommit, moveToAdjacent]
  )

  // The keyboard handlers above commit before focus moves; skip the
  // resulting blur so the same edit isn't committed twice.
  const handleBlur = useCallback(() => {
    if (committedRef.current) {
      committedRef.current = false
      return
    }
    handleCommit()
  }, [handleCommit])

  function startRename() {
    setRenameValue(category.name)
    setSubtitleValue(category.subtitle ?? '')
    setIsRenaming(true)
    setTimeout(() => renameRef.current?.select(), 0)
  }

  function commitRename() {
    const name = renameValue.trim()
    const subtitle = subtitleValue.trim() || null
    const changes: { name?: string; subtitle?: string | null } = {}
    if (name && name !== category.name) changes.name = name
    if (subtitle !== (category.subtitle ?? null)) changes.subtitle = subtitle
    if (Object.keys(changes).length > 0) updateCategory.mutate({ id: category.id, ...changes })
    setIsRenaming(false)
  }

  function handleRenameKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter') { e.preventDefault(); commitRename() }
    if (e.key === 'Escape') setIsRenaming(false)
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

  // Status and progress share one measure per target type (utils/targets) —
  // they used to be computed independently, and a savings-balance category
  // whose balance met the goal showed a full bar beside an "Underfunded"
  // pill. Overfunded renders as funded here: the row only distinguishes
  // "needs money" from "doesn't".
  const targetStatus: 'funded' | 'underfunded' | null =
    !target || isTargetExpired
      ? null
      : computeTargetStatus(target, assigned, available) === 'underfunded'
        ? 'underfunded'
        : 'funded'

  const targetProgress =
    !target || isTargetExpired ? null : computeTargetProgress(target, assigned, available)

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
      {showAddTxn && (
        <TransactionEditor
          budgetId={budgetId}
          transaction={null}
          initialCategoryId={category.id}
          onClose={() => setShowAddTxn(false)}
        />
      )}
      {showTxnList && (
        <CategoryTransactionsModal
          budgetId={budgetId}
          categoryId={category.id}
          categoryName={category.name}
          onClose={() => setShowTxnList(false)}
          onAddTransaction={() => {
            setShowTxnList(false)
            setShowAddTxn(true)
          }}
        />
      )}
      <div
        className={`category-row ${category.is_hidden ? 'category-row--hidden' : ''} ${isSelected ? 'category-row--selected' : ''} ${anySelected ? 'category-row--any-selected' : ''} ${available < 0 ? 'category-row--overspent' : ''} ${targetProgress !== null && budgetRowMode === 'expanded' ? 'category-row--has-pill' : ''} ${budgetRowMode === 'compressed' ? 'category-row--compressed' : ''}`}
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
            <div
              className="category-row__rename"
              onBlur={(e) => {
                // Commit only when focus leaves both inputs, not when tabbing
                // between name and subtitle
                if (!e.currentTarget.contains(e.relatedTarget as Node)) commitRename()
              }}
            >
              <input
                ref={renameRef}
                className="category-row__name-input"
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                onKeyDown={handleRenameKey}
                placeholder="Name"
              />
              <input
                className="category-row__name-input category-row__subtitle-input"
                value={subtitleValue}
                onChange={(e) => setSubtitleValue(e.target.value)}
                onKeyDown={handleRenameKey}
                placeholder="Subtitle (optional)"
              />
            </div>
          ) : (
            <>
              <span
                className="category-row__name-text"
                onDoubleClick={startRename}
                title="Double-click to rename"
              >
                {category.name}
              </span>
              {category.subtitle && (
                <span
                  className="category-row__subtitle"
                  onDoubleClick={startRename}
                  title={category.subtitle}
                >
                  {category.subtitle}
                </span>
              )}
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
                    title={getTargetTooltip(targetStatus, monthlyNeeded ?? undefined, formatMoney)}
                    aria-label={`${category.name}: ${getTargetTooltip(targetStatus, monthlyNeeded ?? undefined, formatMoney)}`}
                    onClick={(e) => { e.stopPropagation(); setShowTargetEditor(true) }}
                  />
                ) : (
                  <TargetBadge
                    status={targetStatus}
                    monthlyNeeded={monthlyNeeded ?? undefined}
                    onClick={() => setShowTargetEditor(true)}
                  />
                )
              ) : null}
              <div className="category-row__actions" role="group" aria-label={`${category.name} actions`}>
                <button
                  className="category-row__action-btn"
                  onClick={() => setShowAddTxn(true)}
                  title="Add transaction"
                  aria-label={`Add transaction to ${category.name}`}
                >
                  <Plus size={13} />
                </button>
                <button className="category-row__action-btn" onClick={startRename} title="Rename" aria-label={`Rename ${category.name}`}>
                  <Pencil size={13} />
                </button>
              </div>
            </>
          )}
        </div>

        <div className="category-row__assigned" data-assign-id={category.id}>
          {isEditing ? (
            <AmountInput
              ref={inputRef}
              className="category-row__input"
              value={editValue}
              onValueChange={setEditValue}
              baseCents={toCents(assigned)}
              onBlur={handleBlur}
              onKeyDown={handleKeyDown}
              placeholder="0.00"
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
          <button
            className="category-row__activity-btn"
            onClick={(e) => {
              e.stopPropagation()
              setShowTxnList(true)
            }}
            title="View transactions"
            aria-label={`View transactions for ${category.name}`}
          >
            {activity === 0 ? (
              <span className="category-row__zero">—</span>
            ) : (
              <span className={activity < 0 ? 'negative' : 'positive'}>{formatMoney(activity)}</span>
            )}
          </button>
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
        const isBalanceGoal = targetMeasuresBalance(target!)
        // Balance goals state the whole shortfall ("Save X more"); funding
        // targets state what's left of this month's duty.
        const amountRemaining = isBalanceGoal
          ? Math.max(0, Number(target!.target_amount) - available)
          : Math.max(0, targetNeededThisMonth(target!, available) - assigned)
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
                  {isBalanceGoal ? `Save ${formatMoney(amountRemaining)} more` : `Need ${formatMoney(amountRemaining)} this month`}
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
