import { CheckCircle, Circle, Clock, Lock, MoreHorizontal, Split } from 'lucide-react'
import { useState, useRef } from 'react'
import { useUpdateTransaction, useDeleteTransaction } from '../../../api/transactions'
import { useCreateCategory } from '../../../api/categories'
import { useAppStore } from '../../../stores/appStore'
import { useTransactionEditStore } from '../../../stores/transactionEditStore'
import { useHistoryStore } from '../../../stores/historyStore'
import { formatDate } from '../../../utils/dates'
import { formatMoney } from '../../../utils/money'
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
}

const ROW_CONTEXT_ITEMS: ContextMenuItem[] = [
  { id: 'split', label: 'Split Transaction…' },
  { id: 'duplicate', label: 'Duplicate', shortcut: 'shift D' },
  { id: 'make_repeating', label: 'Make Repeating', shortcut: 'shift T' },
  { id: 'separator1', label: '', separator: true },
  { id: 'enter_now', label: 'Enter Now' },
  { id: 'approve', label: 'Approve' },
  { id: 'separator2', label: '', separator: true },
  { id: 'delete', label: 'Delete', shortcut: 'delete', danger: true },
]

export function TransactionRow({
  transaction: txn,
  onEdit,
  payeeMap,
  categoryMap,
  payees,
  categories,
  categoryGroups,
  isSelected,
  orderedIds,
  onSelect,
  onStartSplit,
  onDuplicate,
  onMakeRepeating,
}: Props) {
  const budgetId = useAppStore((s) => s.currentBudgetId!)
  const updateTxn = useUpdateTransaction(budgetId)
  const deleteTxn = useDeleteTransaction(budgetId)
  const createCat = useCreateCategory(budgetId)
  const { editingField, startEditing, stopEditing } = useTransactionEditStore()
  const [contextMenuOpen, setContextMenuOpen] = useState(false)
  const [contextMenuPos, setContextMenuPos] = useState<{ x: number; y: number; alignRight?: boolean }>({ x: 0, y: 0 })
  const moreRef = useRef<HTMLButtonElement>(null)

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
    setContextMenuPos({ x: e.clientX, y: e.clientY })
    setContextMenuOpen(true)
  }

  function handleMoreClick(e: React.MouseEvent) {
    e.stopPropagation()
    const rect = moreRef.current?.getBoundingClientRect()
    if (rect) setContextMenuPos({ x: rect.right, y: rect.bottom + 4, alignRight: true })
    setContextMenuOpen(true)
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

  const payeeOptions: ComboboxOption[] = payees
    .filter((p) => !p.transfer_account_id)
    .map((p) => ({ id: p.id, label: p.name }))

  const categoryOptions: ComboboxOption[] = categories.map((c) => {
    const group = categoryGroups.find((g) => g.id === c.category_group_id)
    return { id: c.id, label: c.name, group: group?.name ?? '' }
  })

  function handleCategoryChange(id: string | null) {
    commitField('category_id', id)
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
      className={`transaction-row ${isSelected ? 'transaction-row--selected' : ''} ${!txn.approved ? 'unapproved' : ''} ${isReconciled ? 'reconciled' : ''} ${isPending ? 'pending' : ''}`}
      role="row"
      onDoubleClick={() => !isReconciled && onEdit(txn)}
      onContextMenu={handleContextMenu}
    >
      {/* Checkbox */}
      <div className="txn-col txn-col--checkbox" onClick={(e) => e.stopPropagation()}>
        <input
          type="checkbox"
          className="txn-checkbox"
          checked={isSelected}
          onChange={(e) => onSelect(txn.id, e.nativeEvent.shiftKey)}
          onClick={(e) => e.stopPropagation()}
        />
      </div>

      {/* Date */}
      <div
        className="txn-col txn-col--date"
        onClick={() => !isReconciled && startEditing(txn.id, 'date')}
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
        onClick={() => !isReconciled && !txn.transfer_id && startEditing(txn.id, 'payee')}
        title={txn.import_description ?? undefined}
      >
        {isEditing('payee') ? (
          <Combobox
            value={txn.payee_id}
            options={payeeOptions}
            onChange={(id) => commitField('payee_id', id)}
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
          if (isReconciled) return
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
        onClick={() => !isReconciled && startEditing(txn.id, 'memo')}
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
        onClick={() => !isReconciled && startEditing(txn.id, 'outflow')}
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
        onClick={() => !isReconciled && startEditing(txn.id, 'inflow')}
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
        {txn.linked_transaction_id && (
          <TransactionLinkIcon
            transaction={txn}
            budgetId={txn.budget_id}
          />
        )}
        {isReconciled ? (
          <span className="txn-cleared-btn txn-cleared-btn--locked" title="Reconciled — locked">
            <Lock size={12} />
          </span>
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
}
