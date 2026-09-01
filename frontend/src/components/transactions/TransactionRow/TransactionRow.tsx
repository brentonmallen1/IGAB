import {
  CheckCircle,
  Circle,
  Clock,
  Eye,
  Lock,
  MoreHorizontal,
  Sparkles,
  Split,
  Trash2,
  ChevronRight,
  Pencil,
  Unlock,
  CalendarClock,
} from 'lucide-react'
import { useState, useRef, useMemo, memo } from 'react'
import {
  useUpdateTransaction,
  useDeleteTransaction,
  useUnreconcileTransaction,
} from '../../../api/transactions'
import { useScheduledTransactions } from '../../../api/scheduledTransactions'
import { confirmDeleteTransaction } from '../../../api/attachments'
import { useCreateCategory } from '../../../api/categories'
import { useCreatePayee } from '../../../api/payees'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import { useLongPress } from '../../../hooks/useLongPress'
import { useTransactionEditStore, type EditableField } from '../../../stores/transactionEditStore'
import { nextEditableField } from './fieldOrder'
import { useFormatters } from '../../../hooks/useFormatters'
import { SHORTCUTS, formatCombo } from '../../../keyboard/shortcuts'
import { useToastUndo } from '../../../utils/toastUndo'
import { parseAmountExpressionInput } from '../../../utils/amountExpression'
import { transactionDisplayPayee } from '../../../utils/transferDisplay'
import { Combobox, type ComboboxOption } from '../../common/Combobox/Combobox'
import { InlineInput } from '../../common/InlineInput/InlineInput'
import { DatePicker } from '../../common/DatePicker/DatePicker'
import { ContextMenu, type ContextMenuItem } from '../../common/ContextMenu/ContextMenu'
import { BankRecordIcon } from '../../simplefin/BankRecordIcon'
import { Tooltip } from '../../common/Tooltip/Tooltip'
import { RowAttachmentButton } from './RowAttachmentButton'
import type { Transaction, Category, CategoryGroup, Payee } from '../../../types'
import './TransactionRow.css'
import { confirmAsync } from '../../../stores/confirmStore'

interface Props {
  transaction: Transaction
  onEdit: (txn: Transaction) => void
  payeeMap: Map<string, string>
  /** id → name for every budget account, so transfer legs can name their
   *  destination ("Transfer : Savings") instead of the bare word. */
  accountMap: Map<string, string>
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
  /** All-accounts register: source account name; renders an extra column */
  accountLabel?: string
  /** CSS color value (e.g. `var(--chart-3)`) for the account's identity dot */
  accountColor?: string
  /** Off-budget accounts don't use categories: no yellow chip, no editor */
  accountOnBudget?: boolean
}

const APPROVE_MENU_ITEMS: ContextMenuItem[] = [
  { id: 'approve', label: 'Approve', icon: CheckCircle },
  { id: 'separator', label: '', separator: true },
  { id: 'delete', label: 'Delete', icon: Trash2, danger: true },
]

const ROW_CONTEXT_ITEMS: ContextMenuItem[] = [
  // The full editor, for every row. A reconciled row's only route to a
  // memo or category fix used to be a 12px lock glyph and an unreconcile.
  { id: 'edit', label: 'Edit…', icon: Pencil },
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
  { id: 'unlock', label: 'Unlock (unreconcile)…', icon: Unlock },
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
    // The category cell renders from this, and it can change without any
    // other field moving — reopening a counterpart account on budget flips it.
    a.needs_category !== b.needs_category ||
    // Served field; a repair/retarget changes it with no other field moving.
    a.counterpart_account_id !== b.counterpart_account_id ||
    // Deleting a category writes this and clears category_id in one bulk
    // update, and undoing clears it again — both without touching anything
    // else on the row, so the chip's "was …" would go stale without this.
    a.prior_category_name !== b.prior_category_name ||
    a.bank_amount !== b.bank_amount ||
    a.entered_amount !== b.entered_amount ||
    // Both are provenance the status cluster renders from.
    a.created_via !== b.created_via ||
    a.scheduled_transaction_id !== b.scheduled_transaction_id ||
    a.bank_payee !== b.bank_payee ||
    a.has_sync_source !== b.has_sync_source
  )
    return false
  if (prev.payeeMap !== next.payeeMap) return false
  if (prev.accountMap !== next.accountMap) return false
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
  if (prev.accountLabel !== next.accountLabel) return false
  if (prev.accountColor !== next.accountColor) return false
  if (prev.accountOnBudget !== next.accountOnBudget) return false
  return true
}

export const TransactionRow = memo(function TransactionRow({
  transaction: txn,
  onEdit,
  payeeMap,
  accountMap,
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
  accountLabel,
  accountColor,
  accountOnBudget = true,
}: Props) {
  const budgetId = useAppStore((s) => s.currentBudgetId!)
  const { formatMoney, formatDate } = useFormatters()
  const updateTxn = useUpdateTransaction(budgetId)
  const deleteTxn = useDeleteTransaction(budgetId)
  const showUndo = useToastUndo(budgetId, txn.account_id)
  const unreconcileTxn = useUnreconcileTransaction(budgetId)
  const createCat = useCreateCategory(budgetId)
  const createPayee = useCreatePayee(budgetId)
  const { editingField, startEditing, stopEditing } = useTransactionEditStore()
  const isMobile = useIsMobile()
  const anyTxnSelected = useUIStore((s) => s.selectedTransactionIds.size > 0)
  const [contextMenuOpen, setContextMenuOpen] = useState(false)
  const [contextMenuPos, setContextMenuPos] = useState<{
    x: number
    y: number
    alignRight?: boolean
  }>({ x: 0, y: 0 })
  const [approveMenuOpen, setApproveMenuOpen] = useState(false)
  const [approveMenuPos, setApproveMenuPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 })
  const moreRef = useRef<HTMLButtonElement>(null)
  const eyeRef = useRef<HTMLButtonElement>(null)

  const isOutflow = txn.amount < 0
  const outflow = isOutflow ? Math.abs(txn.amount) : 0
  const inflow = !isOutflow ? txn.amount : 0

  const payeeName = transactionDisplayPayee(txn, payeeMap, accountMap)

  const categoryName = txn.is_split
    ? 'Split Transaction'
    : txn.category_id
      ? (categoryMap.get(txn.category_id) ?? '—')
      : null

  const isEditing = (field: string) =>
    editingField?.transactionId === txn.id && editingField.field === field

  const isReconciled = txn.cleared === 'reconciled'
  const isPending = txn.cleared === 'pending'

  const dateProvenance =
    [
      txn.bank_posted_date && txn.bank_posted_date !== txn.date
        ? `Bank posted ${formatDate(txn.bank_posted_date)}.`
        : null,
      txn.entered_date && txn.entered_date !== txn.date
        ? `Originally entered ${formatDate(txn.entered_date)}.`
        : null,
    ]
      .filter(Boolean)
      .join(' ') || null

  // Only rows entered from a schedule fetch the schedules (the query is
  // disabled otherwise), and the list is shared with the register's upcoming
  // rows, so this costs nothing extra.
  const { data: schedules } = useScheduledTransactions(
    txn.scheduled_transaction_id ? budgetId : null
  )
  const schedule = txn.scheduled_transaction_id
    ? schedules?.find((s) => s.id === txn.scheduled_transaction_id)
    : undefined
  const scheduleLabel = schedule
    ? `Entered from schedule: ${schedule.payee_id ? (payeeMap.get(schedule.payee_id) ?? 'schedule') : 'schedule'} · ${schedule.frequency}`
    : 'Entered from a schedule'

  function toggleCleared() {
    const next = txn.cleared === 'cleared' ? 'uncleared' : 'cleared'
    updateTxn.mutate({ id: txn.id, cleared: next })
  }

  async function handleUnreconcile() {
    const ok = await confirmAsync({
      title: 'Unlock this reconciled transaction?',
      message: 'It will return to cleared and become editable again.',
      confirmLabel: 'Unlock',
    })
    if (ok) unreconcileTxn.mutate(txn.id)
  }

  // Tab from a cell: the next cell this row can edit opens, or editing
  // ends past the last one. The rule lives in fieldOrder.ts.
  function advance(from: EditableField, direction: 1 | -1) {
    const next = nextEditableField(from, direction, {
      isTransfer: !!txn.transfer_id,
      isSplit: txn.is_split,
      onBudget: !!accountOnBudget,
    })
    if (next) startEditing(txn.id, next)
    else stopEditing()
  }

  function commitField(field: string, value: unknown) {
    if (value !== undefined) {
      updateTxn.mutate({ id: txn.id, [field]: value } as Parameters<typeof updateTxn.mutate>[0])
    }
    stopEditing()
  }

  function commitAmount(raw: string, sign: 1 | -1) {
    const num = parseAmountExpressionInput(raw)
    if (!isNaN(num) && num !== 0) {
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
    onEdit(txn)
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

  async function handleDelete() {
    if (!(await confirmDeleteTransaction(txn.id))) return
    const { batchId } = await deleteTxn.mutateAsync({ id: txn.id, accountId: txn.account_id })
    showUndo(batchId, 'Transaction deleted')
  }

  function handleApproveAction(id: string) {
    if (id === 'approve') updateTxn.mutate({ id: txn.id, approved: true })
    else if (id === 'delete') void handleDelete()
  }

  function handleContextAction(id: string) {
    switch (id) {
      case 'edit':
        onEdit(txn)
        break
      case 'unlock':
        void handleUnreconcile()
        break
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
        void handleDelete()
        break
    }
  }

  const payeeOptions = useMemo<ComboboxOption[]>(
    () => payees.filter((p) => !p.transfer_account_id).map((p) => ({ id: p.id, label: p.name })),
    [payees]
  )

  const categoryOptions = useMemo<ComboboxOption[]>(
    // `is_categorizable`, like every other category picker — the server
    // decides what a leg may be filed to. Offering the raw list put each
    // card's set-aside envelope in the register's most-used control, under
    // a blank group heading (its group is hidden, so no name resolved), and
    // filing a row there hid the money from the budget entirely.
    () =>
      categories
        .filter((c) => c.is_categorizable)
        .map((c) => {
          const group = categoryGroups.find((g) => g.id === c.category_group_id)
          return { id: c.id, label: c.name, group: group?.name ?? '' }
        }),
    [categories, categoryGroups]
  )

  function handleCategoryChange(id: string | null) {
    commitField('category_id', id)
  }

  async function handleCreatePayee(name: string): Promise<ComboboxOption | void> {
    if (!name.trim()) return
    const payee = await createPayee.mutateAsync(name.trim())
    return { id: payee.id, label: payee.name }
  }

  async function handleCreateCategory(name: string): Promise<ComboboxOption | void> {
    const defaultGroup = categoryGroups.find((g) => !g.is_archived && !g.is_system)
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
      onMouseDown={(e) => {
        e.preventDefault()
        onStartSplit(txn)
        stopEditing()
      }}
    >
      <Split size={12} />
      Split (Multiple Categories)
    </button>
  ) : undefined

  const contextItems = ROW_CONTEXT_ITEMS.filter((item) => {
    if (item.id === 'split') return !isReconciled
    if (item.id === 'enter_now') return isPending
    if (item.id === 'approve') return !txn.approved
    if (item.id === 'unlock') return isReconciled
    // The server refuses to delete a reconciled row; offering it and then
    // failing silently was worse than not offering it.
    if (item.id === 'delete') return !isReconciled
    return true
  })

  return (
    <div
      data-txn-id={txn.id}
      className={`transaction-row ${isSelected ? 'transaction-row--selected' : ''} ${anyTxnSelected ? 'transaction-row--any-selected' : ''} ${!txn.approved ? 'unapproved' : ''} ${isReconciled ? 'reconciled' : ''} ${isPending ? 'pending' : ''} ${highlighted ? 'transaction-row--highlighted' : ''}`}
      role="row"
      onDoubleClick={() => !isMobile && onEdit(txn)}
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
          <Tooltip content="Unapproved — click to approve or delete">
            <button
              ref={eyeRef}
              className="txn-status-icon txn-status-icon--unapproved"
              onClick={handleEyeClick}
              aria-label="Unapproved transaction"
              aria-haspopup="menu"
            >
              <Eye size={12} />
            </button>
          </Tooltip>
        )}
        {/* Separates an AI-extracted row from an unapproved bank import: both
            are dimmed and carry the warning eye, but only one of them was
            read off a photo and may have got the details wrong. Accent
            Sparkles is the app's established "AI" pairing (header badge,
            review banner). Non-interactive — tapping the row already opens
            the review modal, and the cluster is crowded enough. Drops away on
            approve, like every other glyph here: it means "this needs you". */}
        {!txn.approved && txn.created_via?.startsWith('ai') && (
          <Tooltip content="Extracted from an image by AI — needs review">
            <span
              className="txn-status-icon txn-status-icon--ai"
              role="img"
              aria-label="Extracted from an image by AI — needs review"
            >
              <Sparkles size={12} />
            </span>
          </Tooltip>
        )}
        {txn.scheduled_transaction_id && (
          <Tooltip content={scheduleLabel}>
            <span
              className="txn-status-icon txn-status-icon--scheduled"
              role="img"
              aria-label={scheduleLabel}
            >
              <CalendarClock size={11} />
            </span>
          </Tooltip>
        )}
        <BankRecordIcon transaction={txn} />
        {/* Mobile cards only show the icon when an image exists (view); adding
            happens through the editor. Desktop always offers add-or-view. */}
        {(!isMobile || hasAttachment) && (
          <RowAttachmentButton transactionId={txn.id} hasAttachment={!!hasAttachment} />
        )}
        {/* Mobile card hides the cleared column; surface non-default states read-only */}
        {isMobile && txn.cleared === 'cleared' && (
          <span className="txn-status-icon txn-status-icon--cleared" title="Cleared">
            <CheckCircle size={12} />
          </span>
        )}
        {isMobile && isReconciled && (
          <span className="txn-status-icon txn-status-icon--reconciled" title="Reconciled">
            <Lock size={12} />
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
      >
        {isEditing('date') ? (
          <DatePicker
            value={txn.date}
            onChange={(date) => commitField('date', date)}
            onClose={stopEditing}
            onTabOut={(d) => advance('date', d)}
          />
        ) : dateProvenance ? (
          <Tooltip content={dateProvenance}>
            <span>{formatDate(txn.date)}</span>
          </Tooltip>
        ) : (
          formatDate(txn.date)
        )}
      </div>

      {/* Account (all-accounts register only) */}
      {accountLabel !== undefined && (
        <div className="txn-col txn-col--account txn-text-clip" title={accountLabel}>
          <span
            className="txn-account-dot"
            style={accountColor ? { backgroundColor: accountColor } : undefined}
            aria-hidden
          />
          <span className="txn-cell-text">{accountLabel}</span>
        </div>
      )}

      {/* Payee */}
      <div
        className="txn-col txn-col--payee txn-text-clip"
        onClick={() =>
          !isMobile && !isReconciled && !txn.transfer_id && startEditing(txn.id, 'payee')
        }
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
            onTabOut={(d) => advance('payee', d)}
          />
        ) : txn.import_description ? (
          <Tooltip content={txn.import_description} block className="txn-text-clip">
            <span className="txn-cell-text">{payeeName}</span>
          </Tooltip>
        ) : (
          <span className="txn-cell-text">{payeeName}</span>
        )}
      </div>

      {/* Category */}
      <div
        className="txn-col txn-col--category txn-text-clip"
        onClick={() => {
          if (isMobile || !accountOnBudget) return
          // A reconciled split's lines are still viewable and editable —
          // through the editor, which locks the money and nothing else.
          if (txn.is_split) {
            if (isReconciled) onEdit(txn)
            else onStartSplit(txn)
            return
          }
          if (!isReconciled) startEditing(txn.id, 'category')
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
            onTabOut={(d) => advance('category', d)}
          />
        ) : txn.is_split ? (
          <Tooltip content="Split — click to view and edit the lines">
            <span className="txn-cell-text txn-split-label">
              <ChevronRight size={11} className="txn-split-label__chevron" aria-hidden />
              {categoryName}
            </span>
          </Tooltip>
        ) : categoryName !== null ? (
          <span className="txn-cell-text">{categoryName}</span>
        ) : txn.needs_category ? (
          // `prior_category_name` is provenance, never a category: this row
          // IS uncategorized and the chip says so. The hint only answers
          // "why did this suddenly need filing?" for rows a category delete
          // emptied — without it they look like a gap the user forgot about.
          <span className="txn-needs-category">
            Needs Category
            {txn.prior_category_name && (
              <span className="txn-needs-category__was">was {txn.prior_category_name}</span>
            )}
          </span>
        ) : accountOnBudget ? (
          // No category and none needed, on a budget account: the only way
          // that happens is a transfer between two on-budget accounts —
          // internal money movement, not a gap. (The categorized side of a
          // spending transfer lives on the on-budget leg.)
          //
          // This used to read `transfer_id !== null`, which recognises only a
          // transfer whose partner also imported, so every unpaired leg wore
          // the amber chip. The server decides now; see `needs_category`.
          <span className="txn-cell-text">Transfer</span>
        ) : (
          // Off-budget accounts don't use categories at all
          <span className="txn-cell-text" title="Tracking accounts don't use categories">
            —
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
            onTabOut={(d) => advance('memo', d)}
            placeholder="Add memo…"
          />
        ) : txn.memo ? (
          // The only place a clipped memo is readable without opening the
          // editor — so it must not take a second to appear.
          <Tooltip content={txn.memo} block className="txn-text-clip">
            <span className="txn-cell-text">{txn.memo}</span>
          </Tooltip>
        ) : (
          <span className="txn-cell-text" />
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
            onTabOut={(d) => advance('outflow', d)}
            type="currency"
            placeholder="0.00"
          />
        ) : outflow > 0 ? (
          <span className="txn-outflow">{formatMoney(outflow)}</span>
        ) : (
          ''
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
            onTabOut={(d) => advance('inflow', d)}
            type="currency"
            placeholder="0.00"
          />
        ) : inflow > 0 ? (
          <span className="txn-inflow">{formatMoney(inflow)}</span>
        ) : (
          ''
        )}
      </div>

      {/* Cleared */}
      <div className="txn-col txn-col--cleared">
        {isReconciled ? (
          <Tooltip content="Reconciled — locked. Click to unlock (unreconcile).">
            <button
              className="txn-cleared-btn txn-cleared-btn--locked"
              onClick={(e) => {
                e.stopPropagation()
                handleUnreconcile()
              }}
              aria-label="Reconciled transaction — click to unreconcile"
            >
              <Lock size={12} />
            </button>
          </Tooltip>
        ) : isPending ? (
          <Tooltip content="Pending — the bank reports a hold that has not posted. Not counted in balances until it does.">
            <span
              className="txn-cleared-btn txn-cleared-btn--pending"
              role="img"
              aria-label="Pending"
            >
              <Clock size={14} />
            </span>
          </Tooltip>
        ) : (
          <Tooltip
            content={
              txn.cleared === 'uncleared'
                ? 'Uncleared — entered by you, not yet confirmed by the bank. Click to mark cleared.'
                : 'Cleared — confirmed by the bank. Click to mark uncleared.'
            }
          >
            <button
              className={`txn-cleared-btn ${txn.cleared !== 'uncleared' ? 'cleared' : ''}`}
              onClick={(e) => {
                e.stopPropagation()
                toggleCleared()
              }}
              aria-label={
                txn.cleared === 'uncleared'
                  ? 'Uncleared — mark cleared'
                  : 'Cleared — mark uncleared'
              }
            >
              {txn.cleared !== 'uncleared' ? <CheckCircle size={14} /> : <Circle size={14} />}
            </button>
          </Tooltip>
        )}
        <Tooltip content="More actions">
          <button
            ref={moreRef}
            className="txn-more-btn"
            onClick={handleMoreClick}
            aria-label="More actions"
          >
            <MoreHorizontal size={12} />
          </button>
        </Tooltip>
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
