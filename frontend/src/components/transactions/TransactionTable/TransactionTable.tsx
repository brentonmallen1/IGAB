import { useMemo, useRef, useEffect, useState } from 'react'
import { Plus, ChevronUp, ChevronDown } from 'lucide-react'
import { useTransactions, usePayees, useBulkUpdateCleared, useBulkCategorize, useBulkDeleteTransactions, useUpdateTransaction, useCreateTransaction } from '../../../api/transactions'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { useTransactionEditStore } from '../../../stores/transactionEditStore'
import { TransactionRow } from '../TransactionRow/TransactionRow'
import { TransactionEditor } from '../TransactionEditor/TransactionEditor'
import { SplitTransactionEditor } from '../SplitTransactionEditor/SplitTransactionEditor'
import { ScheduledTransactionEditor } from '../../scheduled/ScheduledTransactionEditor'
import { useScheduledTransactionsByAccount, useEnterScheduledTransaction, useSkipScheduledTransaction } from '../../../api/scheduledTransactions'
import { SelectionActionBar } from '../SelectionActionBar/SelectionActionBar'
import { TransactionSearch } from '../TransactionSearch/TransactionSearch'
import { Collapsible } from '../../common/Collapsible/Collapsible'
import { parseTransactionSearch, filterTransactions } from '../../../utils/searchParser'
import { useHistoryStore } from '../../../stores/historyStore'
import { today } from '../../../utils/dates'
import { formatMoney } from '../../../utils/money'
import type { Transaction, ClearedStatus, ScheduledTransaction } from '../../../types'
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

export function TransactionTable({ accountId, budgetId }: Props) {
  const { data: transactions = [], isLoading } = useTransactions(accountId)
  const { data: payees = [] } = usePayees(budgetId)
  const { data: categories = [] } = useCategories(budgetId)
  const { data: categoryGroups = [] } = useCategoryGroups(budgetId)
  const bulkSetCleared = useBulkUpdateCleared(budgetId)
  const bulkCategorize = useBulkCategorize(budgetId)
  const bulkDelete = useBulkDeleteTransactions(budgetId)
  const undoTxn = useUpdateTransaction(budgetId)
  const createTxn = useCreateTransaction(budgetId)
  const [makeRepeatingTxn, setMakeRepeatingTxn] = useState<Transaction | null>(null)
  const [editingScheduledTxn, setEditingScheduledTxn] = useState<ScheduledTransaction | null>(null)
  const { data: upcomingScheduled = [] } = useScheduledTransactionsByAccount(budgetId, accountId)
  const enterScheduled = useEnterScheduledTransaction(budgetId)
  const skipScheduled = useSkipScheduledTransaction(budgetId)

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey) || e.key !== 'z' || e.shiftKey) return
      const active = document.activeElement
      if (active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement) return
      e.preventDefault()
      const entry = useHistoryStore.getState().undo()
      if (entry) {
        undoTxn.mutate({ id: entry.transactionId, [entry.field]: entry.before } as Parameters<typeof undoTxn.mutate>[0])
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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
  } = useUIStore()

  const { splitEditing, startSplitEditing } = useTransactionEditStore()

  const payeeMap = useMemo(() => new Map(payees.map((p) => [p.id, p.name])), [payees])
  const categoryMap = useMemo(() => new Map(categories.map((c) => [c.id, c.name])), [categories])

  const editingTxn = useMemo(
    () => transactions.find((t) => t.id === editingTransactionId) ?? null,
    [transactions, editingTransactionId]
  )

  // Parse search
  const parsedSearch = useMemo(
    () => parseTransactionSearch(transactionSearchQuery, categoryMap, payeeMap),
    [transactionSearchQuery, categoryMap, payeeMap]
  )

  // Filter top-level transactions (exclude split children)
  const topLevel = useMemo(
    () => transactions.filter((t) => !t.parent_transaction_id),
    [transactions]
  )

  const filtered = useMemo(
    () => transactionSearchQuery ? filterTransactions(topLevel, parsedSearch, payeeMap) : topLevel,
    [topLevel, transactionSearchQuery, parsedSearch, payeeMap]
  )

  // Sort
  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
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
  }, [filtered, transactionSortColumn, transactionSortDirection, payeeMap, categoryMap])

  // Partition into sections
  const pendingTxns = useMemo(() => sorted.filter((t) => t.cleared === 'pending'), [sorted])
  const uncategorizedTxns = useMemo(
    () => sorted.filter((t) => t.cleared !== 'pending' && !t.category_id && !t.is_split),
    [sorted]
  )
  const regularTxns = useMemo(
    () => sorted.filter((t) => t.cleared !== 'pending' && (t.category_id || t.is_split)),
    [sorted]
  )

  const allOrderedIds = sorted.map((t) => t.id)
  const allSelected = sorted.length > 0 && sorted.every((t) => selectedTransactionIds.has(t.id))
  const someSelected = sorted.some((t) => selectedTransactionIds.has(t.id))
  const headerCheckboxRef = useRef<HTMLInputElement>(null)

  if (headerCheckboxRef.current) {
    headerCheckboxRef.current.indeterminate = someSelected && !allSelected
  }

  function handleSelectAll() {
    if (allSelected) clearTransactionSelection()
    else selectAllTransactions(allOrderedIds)
  }

  function handleSelect(id: string, shiftKey: boolean) {
    toggleTransactionSelection(id, shiftKey, allOrderedIds)
  }

  function handleSort(col: SortColumn) {
    if (transactionSortColumn === col) {
      setTransactionSort(col, transactionSortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      setTransactionSort(col, col === 'date' ? 'desc' : 'asc')
    }
  }

  function handleStartSplit(txn: Transaction) {
    const existingSplits = transactions
      .filter((t) => t.parent_transaction_id === txn.id)
      .map((t) => ({
        tempId: t.id,
        amount: String(Math.abs(Number(t.amount))),
        categoryId: t.category_id,
        memo: t.memo ?? '',
      }))
    startSplitEditing(txn.id, Number(txn.amount), existingSplits.length > 0 ? existingSplits : undefined)
  }

  // Bulk operations
  function handleBulkCategorize(categoryId: string) {
    bulkCategorize.mutate(
      { transactionIds: [...selectedTransactionIds], categoryId },
      { onSuccess: clearTransactionSelection }
    )
  }

  function handleBulkSetCleared(clearedStatus: ClearedStatus) {
    bulkSetCleared.mutate(
      { transactionIds: [...selectedTransactionIds], cleared: clearedStatus },
      { onSuccess: clearTransactionSelection }
    )
  }

  function handleBulkDelete() {
    const eligibleIds = [...selectedTransactionIds].filter((id) => {
      const txn = transactions.find((t) => t.id === id)
      return txn && txn.cleared !== 'reconciled'
    })
    bulkDelete.mutate(eligibleIds, { onSuccess: clearTransactionSelection })
  }

  function duplicateTransaction(txn: Transaction) {
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
  }

  function handleBulkDuplicate() {
    const selected = [...selectedTransactionIds]
      .map((id) => transactions.find((t) => t.id === id))
      .filter((t): t is Transaction => !!t && t.cleared !== 'reconciled' && !t.parent_transaction_id)
    selected.forEach(duplicateTransaction)
    clearTransactionSelection()
  }

  const categoryComboboxOptions: ComboboxOption[] = categories.map((c) => {
    const group = categoryGroups.find((g) => g.id === c.category_group_id)
    return { id: c.id, label: c.name, group: group?.name ?? '' }
  })

  function SortableHeader({ col, label }: { col: SortColumn; label: string }) {
    const isActive = transactionSortColumn === col
    const dir = transactionSortDirection
    return (
      <button className={`txn-col txn-col--${col} txn-sort-header ${isActive ? 'txn-sort-header--active' : ''}`} onClick={() => handleSort(col)}>
        {label}
        {isActive && (dir === 'asc' ? <ChevronUp size={11} /> : <ChevronDown size={11} />)}
      </button>
    )
  }

  const FREQ_LABELS: Record<string, string> = {
    daily: 'Daily', weekly: 'Weekly', biweekly: 'Every 2 weeks', monthly: 'Monthly', yearly: 'Yearly',
  }

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

  function renderRows(txns: Transaction[]) {
    return txns.map((txn) => (
      <div key={txn.id}>
        <TransactionRow
          transaction={txn}
          onEdit={(t) => openTransactionEditor(t.id)}
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
        />
        {splitEditing?.transactionId === txn.id && (
          <SplitTransactionEditor
            transaction={txn}
            categories={categories}
            categoryGroups={categoryGroups}
          />
        )}
      </div>
    ))
  }

  return (
    <div className="transaction-table">
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
          categoryOptions={categoryComboboxOptions}
          onCategorize={handleBulkCategorize}
          onSetCleared={handleBulkSetCleared}
          onDelete={handleBulkDelete}
          onDuplicate={handleBulkDuplicate}
          onClear={clearTransactionSelection}
        />
      )}

      {/* Sticky header */}
      <div className="transaction-table__header">
        <div className="txn-col txn-col--checkbox">
          <input
            ref={headerCheckboxRef}
            type="checkbox"
            className="txn-checkbox"
            checked={allSelected}
            onChange={handleSelectAll}
            style={{ opacity: 1 }}
          />
        </div>
        {HEADER_COLS.map(({ key, label }) => (
          <SortableHeader key={key} col={key} label={label} />
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
    </div>
  )
}
