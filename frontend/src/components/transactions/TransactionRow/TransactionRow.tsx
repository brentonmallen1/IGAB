import { CheckCircle, Circle, Clock, Eye, Lock, MoreHorizontal, Paperclip, Split, Trash2 } from 'lucide-react'
import { useState, useRef, useMemo, memo } from 'react'
import { useUpdateTransaction, useDeleteTransaction, useUnreconcileTransaction } from '../../../api/transactions'
import { useCreateCategory } from '../../../api/categories'
import { useCreatePayee } from '../../../api/payees'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import { useLongPress } from '../../../hooks/useLongPress'
import { useTransactionEditStore } from '../../../stores/transactionEditStore'
import { useHistoryStore } from '../../../stores/historyStore'
import { useFormatters } from '../../../hooks/useFormatters'
import { SHORTCUTS, formatCombo } from '../../../keyboard/shortcuts'
import { Combobox, type ComboboxOption } from '../../common/Combobox/Combobox'
import { InlineInput } from '../../common/InlineInput/InlineInput'
import { DatePicker } from '../../common/DatePicker/DatePicker'
import { ContextMenu, type ContextMenuItem } from '../../common/ContextMenu/ContextMenu'
import { TransactionLinkIcon } from '../../simplefin/TransactionLinkPopup'
import type { Transaction, Category, CategoryGroup, Payee } from '../../../types'
import './TransactionRow.css'

interface Props {
  transaction: Transaction
  onEdit: (txn: Transaction) => void
  payeeMap: Map<string, string>
  categoryMap: Map<string, string>
  payees: Payee[]
  categories: Category[]
  categoryGroups: CategoryGroup[]
  isSelected: boolean
  orderedIds: string[]
  onSelect: (id: string, shiftKey: boolean) => void
  onStartSplit: (txn: Transaction) => void
  onDuplicate: (txn: Transaction) => void
  onMakeRepeating: (txn: Transaction) => void
  hasAttachment?: boolean
  highlighted?: boolean
}

const APPROVE_MENU_ITEMS: ContextMenuItem[] = [
  { id: 'approve', label: 'Approve', icon: CheckCircle },
  { id: 'separator', label: '', separator: true },
  { id: 'delete', label: 'Delete', icon: Trash2, danger: true },
]

const ROW_CONTEXT_ITEMS: ContextMenuItem[] = [
  { id: 'split', label: 'Split Transaction…' },
  { id: 'duplicate', label: 'Duplicate', shortcut: formatCombo(SHORTCUTS.duplicate.combo) },
  {
    id: 'make_repeating',
    label: 'Make Repeating',
    shortcut: formatCombo(SHORTCUTS.makeRepeating.combo),
  },
  { id: 'separator1', label: '', separator: true },
  { id: 'enter_now', label: 'Enter Now' },
  { id: 'approve', label: 'Approve' },
  { id: 'separator2', label: '', separator: true },
  {
    id: 'delete',
    label: 'Delete',
    shortcut: formatCombo(SHORTCUTS.deleteSelected.combo),
    danger: true,
  },
]

function txnPropsEqual(prev: Props, next: Props): boolean {
  if (prev.isSelected !== next.isSelected) return false
  if (prev.highlighted !== next.highlighted) return false
  const a = prev.transaction
  const b = next.transaction
  if (
    a.id !== b.id ||
    a.date !== b.date ||
    a.payee_id !== b.payee_id ||
    a.category_id !== b.category_id ||
    a.memo !== b.memo ||
    a.amount !== b.amount ||
    a.cleared !== b.cleared ||
    a.approved !== b.approved ||
    a.is_split !== b.is_split ||
    a.transfer_id !== b.transfer_id ||
    a.linked_transaction_id !== b.linked_transaction_id ||
    a.has_sync_source !== b.has_sync_source
  ) return false
  if (prev.payeeMap !== next.payeeMap) return false
  if (prev.categoryMap !== next.categoryMap) return false
  if (prev.payees !== next.payees) return false
  if (prev.categories !== next.categories) return false
  if (prev.categoryGroups !== next.categoryGroups) return false
  if (prev.orderedIds !== next.orderedIds) return false
  if (prev.onEdit !== next.onEdit) return false
  if (prev.onSelect !== next.onSelect) return false
  if (prev.onStartSplit !== next.onStartSplit) return false
  if (prev.onDuplicate !== next.onDuplicate) return false
  if (prev.onMakeRepeating !== next.onMakeRepeating) return false
  if (prev.hasAttachment !== next.hasAttachment) return false
  return true
}

export const TransactionRow = memo(function TransactionRow({
  transaction: txn,
  onEdit,
  payeeMap,
  categoryMap,
  payees,
  categories,
  categoryGroups,
  isSelected,
  onSelect,
  onStartSplit,
  onDuplicate,
  onMakeRepeating,
  hasAttachment,
  highlighted,
}: Props) {
  const budgetId = useAppStore((s) => s.currentBudgetId!)
  const { formatMoney, formatDate } = useFormatters()
  const updateTxn = useUpdateTransaction(budgetId)
  const deleteTxn = useDeleteTransaction(budgetId)
  const unreconcileTxn = useUnreconcileTransaction(budgetId)
  const createCat = useCreateCategory(budgetId)
  const createPayee = useCreatePayee(budgetId)
  const { editingField, startEditing, stopEditing } = useTransactionEditStore()
  const isMobile = useIsMobile()
  const anyTxnSelected = useUIStore((s) => s.selectedTransactionIds.size > 0)
  const [contextMenuOpen, setContextMenuOpen] = useState(false)
  const [contextMenuPos, setContextMenuPos] = useState<{ x: number; y: number; alignRight?: boolean }>({ x: 0, y: 0 })
  const [approveMenuOpen, setApproveMenuOpen] = useState(false)
  const [approveMenuPos, setApproveMenuPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 })
  const moreRef = useRef<HTMLButtonElement>(null)
  const eyeRef = useRef<HTMLButtonElement>(null)

  const isOutflow = Number(txn.amount) < 0
  const outflow = isOutflow ? Math.abs(Number(txn.amount)) : 0
  const inflow = !isOutflow ? Number(txn.amount) : 0

  const payeeName = txn.transfer_id
    ? 'Transfer'
    : (txn.payee_id ? (payeeMap.get(txn.payee_id) ?? '—') : '—')

  const categoryName = txn.is_split
    ? 'Split Transaction'
    : (txn.category_id ? (categoryMap.get(txn.category_id) ?? '—') : null)

  const isEditing = (field: string) =>
    editingField?.transactionId === txn.id && editingField.field === field

  const isReconciled = txn.cleared === 'reconciled'
  const isPending = txn.cleared === 'pending'

  function toggleCleared() {
    const next = txn.cleared === 'cleared' ? 'uncleared' : 'cleared'
    updateTxn.mutate({ id: txn.id, cleared: next })
  }

  function handleUnreconcile() {
    if (
      confirm(
        'Unlock this reconciled transaction? It will return to cleared and become editable again.'
      )
    ) {
      unreconcileTxn.mutate(txn.id)
    }
  }

  function commitField(field: string, value: unknown) {
    if (value !== undefined) {
      useHistoryStore.getState().push({
        transactionId: txn.id,
        field,
        before: txn[field as keyof typeof txn],
      })
      updateTxn.mutate({ id: txn.id, [field]: value } as Parameters<typeof updateTxn.mutate>[0])
    }
    stopEditing()
  }

  function commitAmount(raw: string, sign: 1 | -1) {
    const num = parseFloat(raw.replace(/[^0-9.]/g, ''))
    if (!isNaN(num) && num !== 0) {
      useHistoryStore.getState().push({
        transactionId: txn.id,
        field: 'amount',
        before: txn.amount,
      })
      updateTxn.mutate({ id: txn.id, amount: num * sign })
    }
    stopEditing()
  }

  function handleContextMenu(e: React.MouseEvent) {
    e.preventDefault()
    if (isMobile) return // long-press enters selection mode instead
    setContextMenuPos({ x: e.clientX, y: e.clientY })
    setContextMenuOpen(true)
  }

  // Mobile: tap opens the editor (or toggles selection while selecting);
  // long-press starts selection mode. Inline cell editing is desktop-only.
  function handleMobileTap(e: React.MouseEvent) {
    const target = e.target as Element
    if (target.closest('input, button, a')) return
    if (anyTxnSelected) {
      onSelect(txn.id, false)
      return
    }
    if (!isReconciled) onEdit(txn)
  }

  const longPress = useLongPress(() => {
    if (!anyTxnSelected) onSelect(txn.id, false)
  }, handleMobileTap)

  function handleMoreClick(e: React.MouseEvent) {
    e.stopPropagation()
    const rect = moreRef.current?.getBoundingClientRect()
    if (rect) setContextMenuPos({ x: rect.right, y: rect.bottom + 4, alignRight: true })
    setContextMenuOpen(true)
  }

  function handleEyeClick(e: React.MouseEvent) {
    e.stopPropagation()
    const rect = eyeRef.current?.getBoundingClientRect()
    if (rect) setApproveMenuPos({ x: rect.left, y: rect.bottom + 4 })
    setApproveMenuOpen(true)
  }

  function handleApproveAction(id: string) {
    if (id === 'approve') updateTxn.mutate({ id: txn.id, approved: true })
    else if (id === 'delete') deleteTxn.mutate({ id: txn.id, accountId: txn.account_id })
  }

  function handleContextAction(id: string) {
    switch (id) {
      case 'split':
        onStartSplit(txn)
        break
      case 'duplicate':
        onDuplicate(txn)
        break
      case 'make_repeating':
        onMakeRepeating(txn)
        break
      case 'enter_now':
        updateTxn.mutate({ id: txn.id, cleared: 'uncleared' })
        break
      case 'approve':
        updateTxn.mutate({ id: txn.id, approved: true })
        break
      case 'delete':
        deleteTxn.mutate({ id: txn.id, accountId: txn.account_id })
        break
    }
  }

  const payeeOptions = useMemo<ComboboxOption[]>(
    () => payees.filter((p) => !p.transfer_account_id).map((p) => ({ id: p.id, label: p.name })),
    [payees]
  )

  const categoryOptions = useMemo<ComboboxOption[]>(
    () => categories.map((c) => {
      const group = categoryGroups.find((g) => g.id === c.category_group_id)
      return { id: c.id, label: c.name, group: group?.name ?? '' }
    }),
    [categories, categoryGroups]
  )

  function handleCategoryChange(id: string | null) {
    if (id !== null && !txn.approved) {
      useHistoryStore.getState().push({ transactionId: txn.id, field: 'category_id', before: txn.category_id })
      updateTxn.mutate({ id: txn.id, category_id: id, approved: true })
      stopEditing()
    } else {
      commitField('category_id', id)
    }
  }

  async function handleCreatePayee(name: string): Promise<ComboboxOption | void> {
    if (!name.trim()) return
    const payee = await createPayee.mutateAsync(name.trim())
    return { id: payee.id, label: payee.name }
  }

  async function handleCreateCategory(name: string): Promise<ComboboxOption | void> {
    const defaultGroup = categoryGroups.find((g) => !g.is_hidden && !g.is_system)
    if (!defaultGroup || !name.trim()) return
    const cat = await createCat.mutateAsync({
      category_group_id: defaultGroup.id,
      name: name.trim(),
    })
    return { id: cat.id, label: cat.name, group: defaultGroup.name }
  }

  const categorySplitFooter = !isReconciled ? (
    <button
      className="combobox__footer-action"
      type="button"
      onMouseDown={(e) => { e.preventDefault(); onStartSplit(txn); stopEditing() }}
    >
      <Split size={12} />
      Split (Multiple Categories)
    </button>
  ) : undefined

  const contextItems = ROW_CONTEXT_ITEMS.filter((item) => {
    if (item.id === 'split') return !isReconciled
    if (item.id === 'enter_now') return isPending
    if (item.id === 'approve') return !txn.approved
    return true
  })

  return (
    <div
      data-txn-id={txn.id}
      className={`transaction-row ${isSelected ? 'transaction-row--selected' : ''} ${anyTxnSelected ? 'transaction-row--any-selected' : ''} ${!txn.approved ? 'unapproved' : ''} ${isReconciled ? 'reconciled' : ''} ${isPending ? 'pending' : ''} ${highlighted ? 'transaction-row--highlighted' : ''}`}
      role="row"
      onDoubleClick={() => !isMobile && !isReconciled && onEdit(txn)}
      onContextMenu={handleContextMenu}
      {...(isMobile ? longPress : {})}
    >
      {/* Checkbox */}
      <div className="txn-col txn-col--checkbox" onClick={(e) => e.stopPropagation()}>
        <input
          type="checkbox"
          className="txn-checkbox"
          checked={isSelected}
          onChange={(e) => onSelect(txn.id, (e.nativeEvent as MouseEvent).shiftKey)}
          onClick={(e) => e.stopPropagation()}
        />
      </div>

      {/* Status icons */}
      <div className="txn-col txn-col--status" onClick={(e) => e.stopPropagation()}>
        {!txn.approved && (
          <button
            ref={eyeRef}
            className="txn-status-icon txn-status-icon--unapproved"
            onClick={handleEyeClick}
            title="Unapproved — click to approve or delete"
            aria-label="Unapproved transaction"
            aria-haspopup="menu"
          >
            <Eye size={12} />
          </button>
        )}
        {txn.linked_transaction_id && (
          <TransactionLinkIcon transaction={txn} budgetId={txn.budget_id} />
        )}
        {hasAttachment && (
          <span className="txn-status-icon txn-status-icon--attachment" title="Has receipt/attachment">
            <Paperclip size={12} />
          </span>
        )}
        {approveMenuOpen && (
          <ContextMenu
            items={APPROVE_MENU_ITEMS}
            onSelect={handleApproveAction}
            onClose={() => setApproveMenuOpen(false)}
            position={approveMenuPos}
          />
        )}
      </div>

      {/* Date */}
      <div
        className="txn-col txn-col--date"
        onClick={() => !isMobile && !isReconciled && startEditing(txn.id, 'date')}
        title={
          txn.entered_date && txn.entered_date !== txn.date
            ? `Bank posted date. Originally entered ${formatDate(txn.entered_date)}.`
            : undefined
        }
      >
        {isEditing('date') ? (
          <DatePicker
            value={txn.date}
            onChange={(date) => commitField('date', date)}
            onClose={stopEditing}
          />
        ) : (
          formatDate(txn.date)
        )}
      </div>

      {/* Payee */}
      <div
        className="txn-col txn-col--payee txn-text-clip"
        onClick={() => !isMobile && !isReconciled && !txn.transfer_id && startEditing(txn.id, 'payee')}
        title={txn.import_description ?? undefined}
      >
        {isEditing('payee') ? (
          <Combobox
            value={txn.payee_id}
            options={payeeOptions}
            onChange={(id) => commitField('payee_id', id)}
            onCreateNew={handleCreatePayee}
            createLabel="New Payee…"
            placeholder="Search payees…"
            autoFocus
            onBlurClose={stopEditing}
          />
        ) : (
          <span className="txn-cell-text">{payeeName}</span>
        )}
      </div>

      {/* Category */}
      <div
        className="txn-col txn-col--category txn-text-clip"
        onClick={() => {
          if (isMobile || isReconciled) return
          if (txn.is_split) onStartSplit(txn)
          else startEditing(txn.id, 'category')
        }}
      >
        {isEditing('category') ? (
          <Combobox
            value={txn.category_id}
            options={categoryOptions}
            onChange={handleCategoryChange}
            onCreateNew={handleCreateCategory}
            createLabel="New Category…"
            footerSlot={categorySplitFooter}
            placeholder="Search categories…"
            autoFocus
            onBlurClose={stopEditing}
          />
        ) : categoryName === null ? (
          <span className="txn-needs-category">Needs Category</span>
        ) : (
          <span className={`txn-cell-text ${txn.is_split ? 'txn-split-label' : ''}`}>
            {categoryName}
          </span>
        )}
      </div>

      {/* Memo */}
      <div
        className="txn-col txn-col--memo txn-text-clip"
        onClick={() => !isMobile && !isReconciled && startEditing(txn.id, 'memo')}
      >
        {isEditing('memo') ? (
          <InlineInput
            value={txn.memo ?? ''}
            onCommit={(val) => commitField('memo', val || null)}
            onCancel={stopEditing}
            placeholder="Add memo…"
          />
        ) : (
          <span className="txn-cell-text">{txn.memo ?? ''}</span>
        )}
      </div>

      {/* Outflow */}
      <div
        className="txn-col txn-col--outflow tabular"
        onClick={() => !isMobile && !isReconciled && startEditing(txn.id, 'outflow')}
      >
        {isEditing('outflow') ? (
          <InlineInput
            value={outflow > 0 ? outflow.toFixed(2) : ''}
            onCommit={(val) => commitAmount(val, -1)}
            onCancel={stopEditing}
            type="currency"
            placeholder="0.00"
          />
        ) : (
          outflow > 0 ? <span className="txn-outflow">{formatMoney(outflow)}</span> : ''
        )}
      </div>

      {/* Inflow */}
      <div
        className="txn-col txn-col--inflow tabular"
        onClick={() => !isMobile && !isReconciled && startEditing(txn.id, 'inflow')}
      >
        {isEditing('inflow') ? (
          <InlineInput
            value={inflow > 0 ? inflow.toFixed(2) : ''}
            onCommit={(val) => commitAmount(val, 1)}
            onCancel={stopEditing}
            type="currency"
            placeholder="0.00"
          />
        ) : (
          inflow > 0 ? <span className="txn-inflow">{formatMoney(inflow)}</span> : ''
        )}
      </div>

      {/* Cleared */}
      <div className="txn-col txn-col--cleared">
        {isReconciled ? (
          <button
            className="txn-cleared-btn txn-cleared-btn--locked"
            onClick={(e) => { e.stopPropagation(); handleUnreconcile() }}
            title="Reconciled — locked. Click to unlock (unreconcile)."
            aria-label="Reconciled transaction — click to unreconcile"
          >
            <Lock size={12} />
          </button>
        ) : isPending ? (
          <span className="txn-cleared-btn txn-cleared-btn--pending" title="Pending — not yet posted">
            <Clock size={14} />
          </span>
        ) : (
          <button
            className={`txn-cleared-btn ${txn.cleared !== 'uncleared' ? 'cleared' : ''}`}
            onClick={(e) => { e.stopPropagation(); toggleCleared() }}
            title={txn.cleared}
          >
            {txn.cleared !== 'uncleared' ? <CheckCircle size={14} /> : <Circle size={14} />}
          </button>
        )}
        <button
          ref={moreRef}
          className="txn-more-btn"
          onClick={handleMoreClick}
          title="More actions"
        >
          <MoreHorizontal size={12} />
        </button>
      </div>

      {contextMenuOpen && (
        <ContextMenu
          items={contextItems}
          onSelect={handleContextAction}
          onClose={() => setContextMenuOpen(false)}
          position={contextMenuPos}
        />
      )}
    </div>
  )
}, txnPropsEqual)
