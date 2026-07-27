import { useMemo, useRef, useEffect, useState, useCallback, memo } from 'react'
import { Plus, ChevronUp, ChevronDown, Info, Link2, GitMerge, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { useShallow } from 'zustand/react/shallow'
import { useInfiniteTransactions, usePayees, useBulkUpdateCleared, useBulkCategorize, useBulkDeleteTransactions, useUpdateTransaction, useCreateTransaction, useBulkApprove, useMergeTransactions, usePendingReviewCountForAccount } from '../../../api/transactions'
import { useCheckAttachments } from '../../../api/attachments'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { useUIStore } from '../../../stores/uiStore'
import { useTransactionEditStore } from '../../../stores/transactionEditStore'
import { TransactionRow } from '../TransactionRow/TransactionRow'
import { TransactionEditor } from '../TransactionEditor/TransactionEditor'
import { SplitTransactionEditor } from '../SplitTransactionEditor/SplitTransactionEditor'
import { ScheduledTransactionEditor } from '../../scheduled/ScheduledTransactionEditor'
import { useScheduledTransactionsByAccount, useEnterScheduledTransaction, useSkipScheduledTransaction } from '../../../api/scheduledTransactions'
import { SelectionActionBar } from '../SelectionActionBar/SelectionActionBar'
import { MergePreviewModal } from '../MergePreviewModal/MergePreviewModal'
import { MatchReviewModal } from '../../simplefin/MatchReviewModal'
import { TransactionSearch } from '../TransactionSearch/TransactionSearch'
import { AttachmentPanel } from '../../attachments/AttachmentPanel'
import { Collapsible } from '../../common/Collapsible/Collapsible'
import { parseTransactionSearch } from '../../../utils/searchParser'
import { useHistoryStore } from '../../../stores/historyStore'
import { usePendingMatchesForAccount, useRejectMatch } from '../../../api/simplefin'
import { useShortcut } from '../../../hooks/useShortcut'
import { SHORTCUTS } from '../../../keyboard/shortcuts'
import { today } from '../../../utils/dates'
import { useFormatters } from '../../../hooks/useFormatters'
import type { Transaction, ClearedStatus, ScheduledTransaction, TransactionMatch } from '../../../types'
import type { ComboboxOption } from '../../common/Combobox/Combobox'
import './TransactionTable.css'

interface Props {
  accountId: string
  budgetId: string
}

type SortColumn = 'date' | 'payee' | 'category' | 'memo' | 'amount'

const HEADER_COLS: { key: SortColumn; label: string }[] = [
  { key: 'date', label: 'Date' },
  { key: 'payee', label: 'Payee' },
  { key: 'category', label: 'Category' },
  { key: 'memo', label: 'Memo' },
]

const FREQ_LABELS: Record<string, string> = {
  daily: 'Daily', weekly: 'Weekly', biweekly: 'Every 2 weeks', monthly: 'Monthly', yearly: 'Yearly',
}

interface SortableHeaderProps {
  col: SortColumn
  label: string
  currentCol: SortColumn
  currentDir: 'asc' | 'desc'
  onSort: (col: SortColumn) => void
}

const SortableHeader = memo(function SortableHeader({ col, label, currentCol, currentDir, onSort }: SortableHeaderProps) {
  const isActive = currentCol === col
  return (
    <button className={`txn-col txn-col--${col} txn-sort-header ${isActive ? 'txn-sort-header--active' : ''}`} onClick={() => onSort(col)}>
      {label}
      {isActive && (currentDir === 'asc' ? <ChevronUp size={11} /> : <ChevronDown size={11} />)}
    </button>
  )
})

export function TransactionTable({ accountId, budgetId }: Props) {
  const { formatMoney } = useFormatters()
  const { data: payees = [] } = usePayees(budgetId)
  const { data: categories = [] } = useCategories(budgetId)
  const { data: categoryGroups = [] } = useCategoryGroups(budgetId)
  const bulkSetCleared = useBulkUpdateCleared(budgetId)
  const bulkCategorize = useBulkCategorize(budgetId)
  const bulkDelete = useBulkDeleteTransactions(budgetId)
  const bulkApprove = useBulkApprove(budgetId)
  const mergeTxns = useMergeTransactions(budgetId)
  const [showMergeModal, setShowMergeModal] = useState(false)
  const [matchModalInitialId, setMatchModalInitialId] = useState<string | null>(null)
  const [showAttachmentPanel, setShowAttachmentPanel] = useState(false)
  const [attachmentTxnId, setAttachmentTxnId] = useState<string | null>(null)

  const {
    selectedTransactionIds,
    collapsedSections,
    transactionSortColumn,
    transactionSortDirection,
    transactionSearchQuery,
    toggleTransactionSelection,
    selectAllTransactions,
    clearTransactionSelection,
    toggleSection,
    setTransactionSort,
    setTransactionSearch,
    isTransactionEditorOpen,
    editingTransactionId,
    openTransactionEditor,
    closeTransactionEditor,
  } = useUIStore(
    useShallow((s) => ({
      selectedTransactionIds: s.selectedTransactionIds,
      collapsedSections: s.collapsedSections,
      transactionSortColumn: s.transactionSortColumn,
      transactionSortDirection: s.transactionSortDirection,
      transactionSearchQuery: s.transactionSearchQuery,
      toggleTransactionSelection: s.toggleTransactionSelection,
      selectAllTransactions: s.selectAllTransactions,
      clearTransactionSelection: s.clearTransactionSelection,
      toggleSection: s.toggleSection,
      setTransactionSort: s.setTransactionSort,
      setTransactionSearch: s.setTransactionSearch,
      isTransactionEditorOpen: s.isTransactionEditorOpen,
      editingTransactionId: s.editingTransactionId,
      openTransactionEditor: s.openTransactionEditor,
      closeTransactionEditor: s.closeTransactionEditor,
    }))
  )

  useEffect(() => {
    if (selectedTransactionIds.size !== 1) {
      setShowAttachmentPanel(false)
      setAttachmentTxnId(null)
    } else {
      const id = Array.from(selectedTransactionIds)[0]
      if (showAttachmentPanel && id !== attachmentTxnId) {
        setAttachmentTxnId(id)
      }
    }
  }, [selectedTransactionIds, showAttachmentPanel, attachmentTxnId])
  const undoTxn = useUpdateTransaction(budgetId)
  const { data: pendingMatches = [] } = usePendingMatchesForAccount(accountId)
  const rejectMatch = useRejectMatch(accountId)
  const createTxn = useCreateTransaction(budgetId)
  const [makeRepeatingTxn, setMakeRepeatingTxn] = useState<Transaction | null>(null)
  const [editingScheduledTxn, setEditingScheduledTxn] = useState<ScheduledTransaction | null>(null)
  const { data: upcomingScheduled = [] } = useScheduledTransactionsByAccount(budgetId, accountId)
  const enterScheduled = useEnterScheduledTransaction(budgetId)
  const skipScheduled = useSkipScheduledTransaction(budgetId)

  useShortcut(SHORTCUTS.undo.combo, () => {
    const entry = useHistoryStore.getState().undo()
    if (entry) {
      undoTxn.mutate({ id: entry.transactionId, [entry.field]: entry.before } as Parameters<typeof undoTxn.mutate>[0])
    }
  })

  const { splitEditing, startSplitEditing } = useTransactionEditStore()

  const payeeMap = useMemo(() => new Map(payees.map((p) => [p.id, p.name])), [payees])
  const categoryMap = useMemo(() => new Map(categories.map((c) => [c.id, c.name])), [categories])

  const filters = useMemo(
    () => parseTransactionSearch(transactionSearchQuery, categoryMap, payeeMap),
    [transactionSearchQuery, categoryMap, payeeMap]
  )

  const {
    data: txnPages,
    isLoading,
    isFetching,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
  } = useInfiniteTransactions(accountId, filters)

  const transactions = useMemo(() => txnPages?.pages.flat() ?? [], [txnPages])
  const transactionMap = useMemo(
    () => new Map(transactions.map((t) => [t.id, t])),
    [transactions]
  )
  const transactionIds = useMemo(() => transactions.map((t) => t.id), [transactions])
  const { data: attachmentMap = {} } = useCheckAttachments(transactionIds)

  const editingTxn = useMemo(
    () => transactions.find((t) => t.id === editingTransactionId) ?? null,
    [transactions, editingTransactionId]
  )

  // Load more pages only while important transactions aren't fully loaded yet.
  // Backend sorts pending → needs-category → uncleared → rest, so these always arrive first.
  const { data: reviewCounts } = usePendingReviewCountForAccount(accountId)
  const sentinelRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!hasNextPage || isFetching) return
    const loadedImportant = transactions.filter(
      (t) => !t.approved || (!t.category_id && !t.transfer_id && !t.is_split)
    ).length
    const knownImportant = reviewCounts?.total ?? 0
    if (loadedImportant < knownImportant) fetchNextPage()
  }, [isFetching, hasNextPage, fetchNextPage, transactions, reviewCounts])

  // Sort (server returns date-desc; client sort applies across loaded pages)
  const sorted = useMemo(() => {
    return [...transactions].sort((a, b) => {
      let cmp = 0
      switch (transactionSortColumn) {
        case 'date':
          cmp = a.date.localeCompare(b.date)
          break
        case 'payee':
          cmp = (payeeMap.get(a.payee_id ?? '') ?? '').localeCompare(payeeMap.get(b.payee_id ?? '') ?? '')
          break
        case 'category':
          cmp = (categoryMap.get(a.category_id ?? '') ?? '').localeCompare(categoryMap.get(b.category_id ?? '') ?? '')
          break
        case 'memo':
          cmp = (a.memo ?? '').localeCompare(b.memo ?? '')
          break
        case 'amount':
          cmp = Number(a.amount) - Number(b.amount)
          break
      }
      return transactionSortDirection === 'asc' ? cmp : -cmp
    })
  }, [transactions, transactionSortColumn, transactionSortDirection, payeeMap, categoryMap])

  // Partition into sections
  const pendingTxns = useMemo(() => sorted.filter((t) => t.cleared === 'pending'), [sorted])
  const uncategorizedTxns = useMemo(
    () => sorted.filter((t) => t.cleared !== 'pending' && !t.category_id && !t.transfer_id && !t.is_split),
    [sorted]
  )
  const regularTxns = useMemo(
    () => sorted.filter((t) => t.cleared !== 'pending' && (t.category_id || t.transfer_id || t.is_split)),
    [sorted]
  )

  // Build map: txn_id → TransactionMatch for pending duplicate pairs
  const pendingMatchMap = useMemo(() => {
    const map = new Map<string, TransactionMatch>()
    for (const m of pendingMatches) {
      map.set(m.synced_transaction_id, m)
      map.set(m.manual_transaction_id, m)
    }
    return map
  }, [pendingMatches])

  const allOrderedIds = useMemo(() => sorted.map((t) => t.id), [sorted])
  const allSelected = sorted.length > 0 && sorted.every((t) => selectedTransactionIds.has(t.id))
  const someSelected = sorted.some((t) => selectedTransactionIds.has(t.id))

  const selectedTotal = useMemo(
    () => transactions
      .filter((t) => selectedTransactionIds.has(t.id))
      .reduce((sum, t) => sum + Number(t.amount), 0),
    [transactions, selectedTransactionIds]
  )
  const headerCheckboxRef = useRef<HTMLInputElement>(null)

  if (headerCheckboxRef.current) {
    headerCheckboxRef.current.indeterminate = someSelected && !allSelected
  }

  const handleSelectAll = useCallback(() => {
    if (allSelected) clearTransactionSelection()
    else selectAllTransactions(allOrderedIds)
  }, [allSelected, clearTransactionSelection, selectAllTransactions, allOrderedIds])

  const handleSelectLinked = useCallback(() => {
    const linkedIds = sorted.filter((t) => t.has_sync_source).map((t) => t.id)
    if (linkedIds.length > 0) selectAllTransactions(linkedIds)
  }, [sorted, selectAllTransactions])

  const hasLinkedTransactions = useMemo(
    () => sorted.some((t) => t.has_sync_source),
    [sorted]
  )

  const handleSelect = useCallback((id: string, shiftKey: boolean) => {
    toggleTransactionSelection(id, shiftKey, allOrderedIds)
  }, [toggleTransactionSelection, allOrderedIds])

  const handleSort = useCallback((col: SortColumn) => {
    if (transactionSortColumn === col) {
      setTransactionSort(col, transactionSortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      setTransactionSort(col, col === 'date' ? 'desc' : 'asc')
    }
  }, [transactionSortColumn, transactionSortDirection, setTransactionSort])

  const handleStartSplit = useCallback((txn: Transaction) => {
    const existingSplits = transactions
      .filter((t) => t.parent_transaction_id === txn.id)
      .map((t) => ({
        tempId: t.id,
        amount: String(Math.abs(Number(t.amount))),
        categoryId: t.category_id,
        memo: t.memo ?? '',
      }))
    startSplitEditing(txn.id, Number(txn.amount), existingSplits.length > 0 ? existingSplits : undefined)
  }, [transactions, startSplitEditing])

  // Bulk operations
  const handleBulkCategorize = useCallback((categoryId: string) => {
    bulkCategorize.mutate(
      { transactionIds: [...selectedTransactionIds], categoryId, accountId },
      { onSuccess: clearTransactionSelection }
    )
  }, [bulkCategorize, selectedTransactionIds, accountId, clearTransactionSelection])

  const handleBulkSetCleared = useCallback((clearedStatus: ClearedStatus) => {
    bulkSetCleared.mutate(
      { transactionIds: [...selectedTransactionIds], cleared: clearedStatus, accountId },
      { onSuccess: clearTransactionSelection }
    )
  }, [bulkSetCleared, selectedTransactionIds, accountId, clearTransactionSelection])

  const handleBulkDelete = useCallback(() => {
    const eligibleIds = [...selectedTransactionIds].filter((id) => {
      const txn = transactionMap.get(id)
      return txn && txn.cleared !== 'reconciled'
    })
    bulkDelete.mutate({ transactionIds: eligibleIds, accountId }, { onSuccess: clearTransactionSelection })
  }, [bulkDelete, selectedTransactionIds, transactionMap, accountId, clearTransactionSelection])

  const duplicateTransaction = useCallback((txn: Transaction) => {
    createTxn.mutate({
      account_id: txn.account_id,
      date: today(),
      amount: Number(txn.amount),
      payee_id: txn.payee_id ?? undefined,
      category_id: txn.category_id ?? undefined,
      memo: txn.memo ?? undefined,
      cleared: 'uncleared',
      approved: false,
    })
  }, [createTxn])

  const handleBulkDuplicate = useCallback(() => {
    const selected = [...selectedTransactionIds]
      .map((id) => transactionMap.get(id))
      .filter((t): t is Transaction => !!t && t.cleared !== 'reconciled' && !t.parent_transaction_id)
    selected.forEach(duplicateTransaction)
    clearTransactionSelection()
  }, [selectedTransactionIds, transactionMap, duplicateTransaction, clearTransactionSelection])

  // Selection shortcuts share the exact handlers behind the context menu and
  // selection bar, so menu hints and key behavior can never diverge
  const hasSelection = selectedTransactionIds.size > 0
  useShortcut(SHORTCUTS.duplicate.combo, handleBulkDuplicate, { enabled: hasSelection })
  useShortcut(
    SHORTCUTS.makeRepeating.combo,
    () => {
      const [onlyId] = [...selectedTransactionIds]
      const txn = onlyId ? transactionMap.get(onlyId) : undefined
      if (txn && !txn.parent_transaction_id) setMakeRepeatingTxn(txn)
    },
    { enabled: selectedTransactionIds.size === 1 }
  )
  useShortcut('delete', handleBulkDelete, { enabled: hasSelection })
  useShortcut('backspace', handleBulkDelete, { enabled: hasSelection })

  const handleBulkApprove = useCallback(() => {
    bulkApprove.mutate(
      { transactionIds: [...selectedTransactionIds], accountId },
      { onSuccess: clearTransactionSelection }
    )
  }, [bulkApprove, selectedTransactionIds, accountId, clearTransactionSelection])

  const canApprove = useMemo(
    () => [...selectedTransactionIds].some((id) => {
      const t = transactionMap.get(id)
      return t && !t.approved && t.cleared !== 'reconciled'
    }),
    [selectedTransactionIds, transactionMap]
  )

  const mergeEligiblePair = useMemo((): [Transaction, Transaction] | null => {
    if (selectedTransactionIds.size !== 2) return null
    const [id1, id2] = [...selectedTransactionIds]
    const t1 = transactionMap.get(id1)
    const t2 = transactionMap.get(id2)
    if (!t1 || !t2) return null
    if (t1.account_id !== t2.account_id) return null
    if (t1.cleared === 'reconciled' && t2.cleared === 'reconciled') return null
    if (t1.is_split || t2.is_split || t1.parent_transaction_id || t2.parent_transaction_id) return null
    if (t1.transfer_id || t2.transfer_id) return null
    return [t1, t2]
  }, [selectedTransactionIds, transactionMap])

  const handleConfirmMerge = useCallback(async (survivorId?: string) => {
    await mergeTxns.mutateAsync(
      { transactionIds: [...selectedTransactionIds], survivorId },
    )
    setShowMergeModal(false)
    clearTransactionSelection()
    toast.success('Transactions merged')
  }, [mergeTxns, selectedTransactionIds, clearTransactionSelection])

  const categoryComboboxOptions = useMemo<ComboboxOption[]>(
    () => categories.map((c) => {
      const group = categoryGroups.find((g) => g.id === c.category_group_id)
      return { id: c.id, label: c.name, group: group?.name ?? '' }
    }),
    [categories, categoryGroups]
  )

  function renderUpcomingRow(s: ScheduledTransaction) {
    const amount = Number(s.amount)
    const isOutflow = amount < 0
    const payeeName = payeeMap.get(s.payee_id ?? '') ?? (s.transfer_account_id ? 'Transfer' : '—')
    const catName = s.category_id ? categoryMap.get(s.category_id) ?? '—' : '—'

    return (
      <div key={s.id} className="upcoming-row" onClick={() => setEditingScheduledTxn(s)}>
        <div className="txn-col txn-col--checkbox" />
        <div className="txn-col txn-col--date upcoming-row__date">
          {s.next_occurrence_date}
          <span className="upcoming-row__freq">{FREQ_LABELS[s.frequency] ?? s.frequency}</span>
        </div>
        <div className="txn-col txn-col--payee txn-text-clip">{payeeName}</div>
        <div className="txn-col txn-col--category txn-text-clip">{catName}</div>
        <div className="txn-col txn-col--memo txn-text-clip">{s.memo ?? ''}</div>
        <div className="txn-col txn-col--outflow tabular">
          {isOutflow ? formatMoney(Math.abs(amount)) : ''}
        </div>
        <div className="txn-col txn-col--inflow tabular">
          {!isOutflow ? formatMoney(amount) : ''}
        </div>
        <div className="txn-col txn-col--cleared upcoming-row__actions" onClick={(e) => e.stopPropagation()}>
          <button
            className="upcoming-row__btn"
            title="Enter now"
            onClick={() => enterScheduled.mutate(s.id)}
            disabled={enterScheduled.isPending}
          >
            Enter
          </button>
          <button
            className="upcoming-row__btn upcoming-row__btn--secondary"
            title="Skip next occurrence"
            onClick={() => skipScheduled.mutate(s.id)}
            disabled={skipScheduled.isPending}
          >
            Skip
          </button>
        </div>
      </div>
    )
  }

  const handleEdit = useCallback((txn: Transaction) => {
    openTransactionEditor(txn.id)
  }, [openTransactionEditor])

  function renderTxnRow(txn: Transaction) {
    return (
      <>
        <TransactionRow
          transaction={txn}
          onEdit={handleEdit}
          payeeMap={payeeMap}
          categoryMap={categoryMap}
          payees={payees}
          categories={categories}
          categoryGroups={categoryGroups}
          isSelected={selectedTransactionIds.has(txn.id)}
          orderedIds={allOrderedIds}
          onSelect={handleSelect}
          onStartSplit={handleStartSplit}
          onDuplicate={duplicateTransaction}
          onMakeRepeating={setMakeRepeatingTxn}
          hasAttachment={attachmentMap[txn.id]}
        />
        {splitEditing?.transactionId === txn.id && (
          <SplitTransactionEditor
            transaction={txn}
            categories={categories}
            categoryGroups={categoryGroups}
          />
        )}
      </>
    )
  }

  function renderRows(txns: Transaction[]) {
    const rendered = new Set<string>()
    const items: React.ReactNode[] = []

    for (const txn of txns) {
      if (rendered.has(txn.id)) continue

      const match = pendingMatchMap.get(txn.id)
      if (match) {
        const partnerId =
          match.synced_transaction_id === txn.id
            ? match.manual_transaction_id
            : match.synced_transaction_id
        const partnerTxn = txns.find((t) => t.id === partnerId)

        if (partnerTxn && !rendered.has(partnerId)) {
          rendered.add(txn.id)
          rendered.add(partnerId)
          items.push(
            <div key={match.id} className="txn-duplicate-group">
              {renderTxnRow(txn)}
              {renderTxnRow(partnerTxn)}
              <div className="txn-duplicate-group__bar">
                <span className="txn-duplicate-group__label">
                  <Link2 size={11} />
                  Potential duplicate
                </span>
                <div className="txn-duplicate-group__actions">
                  <button
                    className="txn-duplicate-group__btn txn-duplicate-group__btn--merge"
                    onClick={() => setMatchModalInitialId(match.id)}
                  >
                    <GitMerge size={11} />
                    Merge
                  </button>
                  <button
                    className="txn-duplicate-group__btn txn-duplicate-group__btn--dismiss"
                    onClick={() => rejectMatch.mutate(match.id)}
                    disabled={rejectMatch.isPending}
                  >
                    <X size={11} />
                    Dismiss
                  </button>
                </div>
              </div>
            </div>
          )
          continue
        }
      }

      rendered.add(txn.id)
      items.push(<div key={txn.id}>{renderTxnRow(txn)}</div>)
    }

    return items
  }

  return (
    <div className="transaction-table">
      {showMergeModal && mergeEligiblePair && (
        <MergePreviewModal
          transactions={mergeEligiblePair}
          payeeMap={payeeMap}
          categoryMap={categoryMap}
          onConfirm={handleConfirmMerge}
          onCancel={() => setShowMergeModal(false)}
          isPending={mergeTxns.isPending}
        />
      )}

      {matchModalInitialId && pendingMatches.length > 0 && (
        <MatchReviewModal
          matches={pendingMatches}
          budgetId={budgetId}
          initialMatchId={matchModalInitialId}
          onClose={() => setMatchModalInitialId(null)}
        />
      )}

      {makeRepeatingTxn && (
        <ScheduledTransactionEditor
          budgetId={budgetId}
          existing={null}
          initial={{
            account_id: makeRepeatingTxn.account_id,
            amount: Number(makeRepeatingTxn.amount),
            category_id: makeRepeatingTxn.category_id ?? undefined,
            memo: makeRepeatingTxn.memo ?? undefined,
          }}
          onClose={() => setMakeRepeatingTxn(null)}
        />
      )}

      {editingScheduledTxn && (
        <ScheduledTransactionEditor
          budgetId={budgetId}
          existing={editingScheduledTxn}
          onClose={() => setEditingScheduledTxn(null)}
        />
      )}

      {/* Toolbar */}
      <div className="transaction-table__toolbar">
        <TransactionSearch
          value={transactionSearchQuery}
          onChange={setTransactionSearch}
        />
        <button className="transaction-table__add-btn" onClick={() => openTransactionEditor()}>
          <Plus size={14} />
          Add Transaction
        </button>
      </div>

      {/* Selection bar */}
      {someSelected && (
        <SelectionActionBar
          selectedCount={selectedTransactionIds.size}
          selectedTotal={selectedTotal}
          categoryOptions={categoryComboboxOptions}
          onCategorize={handleBulkCategorize}
          onSetCleared={handleBulkSetCleared}
          onDelete={handleBulkDelete}
          onDuplicate={handleBulkDuplicate}
          onClear={clearTransactionSelection}
          onApprove={canApprove ? handleBulkApprove : undefined}
          onMerge={() => setShowMergeModal(true)}
          canMerge={!!mergeEligiblePair}
          onAttachments={() => {
            setShowAttachmentPanel(true)
            setAttachmentTxnId(Array.from(selectedTransactionIds)[0])
          }}
        />
      )}

      {/* Sticky header */}
      <div className="transaction-table__header">
        <div className="txn-col txn-col--checkbox txn-col--checkbox-group">
          <input
            ref={headerCheckboxRef}
            type="checkbox"
            className="txn-checkbox"
            checked={allSelected}
            onChange={handleSelectAll}
            style={{ opacity: 1 }}
          />
          {hasLinkedTransactions && (
            <button
              className="txn-select-linked-btn"
              onClick={handleSelectLinked}
              title="Select linked transactions"
            >
              <Link2 size={10} />
            </button>
          )}
        </div>
        <div className="txn-col txn-col--status" title="Transaction status" style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Info size={11} />
        </div>
        {HEADER_COLS.map(({ key, label }) => (
          <SortableHeader
            key={key}
            col={key}
            label={label}
            currentCol={transactionSortColumn}
            currentDir={transactionSortDirection}
            onSort={handleSort}
          />
        ))}
        <button
          className={`txn-col txn-col--amount txn-sort-header ${transactionSortColumn === 'amount' ? 'txn-sort-header--active' : ''}`}
          onClick={() => handleSort('amount')}
          style={{ textAlign: 'center' }}
        >
          Outflow
          {transactionSortColumn === 'amount' && (transactionSortDirection === 'asc' ? <ChevronUp size={11} /> : <ChevronDown size={11} />)}
        </button>
        <div className="txn-col txn-col--inflow" style={{ textAlign: 'center' }}>Inflow</div>
        <div className="txn-col txn-col--cleared" style={{ textAlign: 'center' }}>Cleared</div>
      </div>

      {isLoading ? (
        <div className="transaction-table__loading">Loading transactions…</div>
      ) : sorted.length === 0 ? (
        <div className="transaction-table__empty">
          {transactionSearchQuery ? 'No transactions match your search.' : 'No transactions yet.'}
        </div>
      ) : (
        <>
          {upcomingScheduled.length > 0 && (
            <Collapsible
              title="Upcoming"
              count={upcomingScheduled.length}
              isOpen={!collapsedSections.has('upcoming')}
              onToggle={() => toggleSection('upcoming')}
            >
              {upcomingScheduled.map(renderUpcomingRow)}
            </Collapsible>
          )}

          {pendingTxns.length > 0 && (
            <Collapsible
              title="Pending"
              count={pendingTxns.length}
              isOpen={!collapsedSections.has('pending')}
              onToggle={() => toggleSection('pending')}
            >
              {renderRows(pendingTxns)}
            </Collapsible>
          )}

          {uncategorizedTxns.length > 0 && (
            <Collapsible
              title="Needs Category"
              count={uncategorizedTxns.length}
              isOpen={!collapsedSections.has('uncategorized')}
              onToggle={() => toggleSection('uncategorized')}
            >
              {renderRows(uncategorizedTxns)}
            </Collapsible>
          )}

          <div className="transaction-table__body">
            {renderRows(regularTxns)}
          </div>
          <div ref={sentinelRef} className="transaction-table__sentinel" />
          {isFetchingNextPage && (
            <div className="transaction-table__loading">Loading more…</div>
          )}
        </>
      )}

      {isTransactionEditorOpen && (
        <TransactionEditor
          budgetId={budgetId}
          accountId={accountId}
          transaction={editingTxn}
          onClose={closeTransactionEditor}
        />
      )}

      {showAttachmentPanel && attachmentTxnId && (
        <AttachmentPanel
          transactionId={attachmentTxnId}
          onClose={() => {
            setShowAttachmentPanel(false)
            setAttachmentTxnId(null)
          }}
        />
      )}
    </div>
  )
}
