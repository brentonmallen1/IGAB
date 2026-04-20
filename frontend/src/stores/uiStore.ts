import { create } from 'zustand'

type TransactionSortColumn = 'date' | 'payee' | 'category' | 'memo' | 'amount'
type SortDirection = 'asc' | 'desc'
type CollapsibleSection = 'pending' | 'uncategorized'

interface UIState {
  collapsedGroups: Set<string>
  isTransactionEditorOpen: boolean
  editingTransactionId: string | null
  isAccountEditorOpen: boolean
  mobileSidebarOpen: boolean
  selectedCategoryIds: Set<string>
  categoryInspectorOpen: boolean
  lastSelectedCategoryId: string | null

  // Transaction table state
  selectedTransactionIds: Set<string>
  lastSelectedTransactionId: string | null
  collapsedSections: Set<CollapsibleSection>
  transactionSortColumn: TransactionSortColumn
  transactionSortDirection: SortDirection
  transactionSearchQuery: string

  toggleGroupExpanded: (groupId: string) => void
  collapseAll: (groupIds: string[]) => void
  expandAll: () => void
  openTransactionEditor: (transactionId?: string) => void
  closeTransactionEditor: () => void
  openAccountEditor: () => void
  closeAccountEditor: () => void
  setMobileSidebarOpen: (open: boolean) => void
  toggleCategorySelection: (id: string, shiftKey?: boolean, orderedIds?: string[]) => void
  selectGroupCategories: (ids: string[]) => void
  clearCategorySelection: () => void
  setCategoryInspectorOpen: (open: boolean) => void

  // Transaction selection actions
  toggleTransactionSelection: (id: string, shiftKey?: boolean, orderedIds?: string[]) => void
  selectAllTransactions: (ids: string[]) => void
  clearTransactionSelection: () => void
  toggleSection: (section: CollapsibleSection) => void
  setTransactionSort: (column: TransactionSortColumn, direction: SortDirection) => void
  setTransactionSearch: (query: string) => void

  // Budget views
  activeBudgetViewId: string | null
  isViewModalOpen: boolean
  editingViewId: string | null
  setActiveBudgetView: (viewId: string | null) => void
  openViewModal: (viewId?: string) => void
  closeViewModal: () => void

  // Reconciliation mode
  isReconciling: boolean
  reconcileAccountId: string | null
  reconcileStatementBalance: number | null
  reconcileAdjustmentTxnId: string | null
  startReconciliation: (accountId: string) => void
  setReconcileStatementBalance: (balance: number) => void
  setReconcileAdjustmentTxnId: (txnId: string) => void
  cancelReconciliation: () => void
}

export const useUIStore = create<UIState>((set, get) => ({
  collapsedGroups: new Set(),
  isTransactionEditorOpen: false,
  editingTransactionId: null,
  isAccountEditorOpen: false,
  mobileSidebarOpen: false,
  selectedCategoryIds: new Set(),
  categoryInspectorOpen: true,
  lastSelectedCategoryId: null,

  selectedTransactionIds: new Set(),
  lastSelectedTransactionId: null,
  collapsedSections: new Set(),
  transactionSortColumn: 'date',
  transactionSortDirection: 'desc',
  transactionSearchQuery: '',

  toggleGroupExpanded: (groupId) => {
    const groups = new Set(get().collapsedGroups)
    if (groups.has(groupId)) {
      groups.delete(groupId)
    } else {
      groups.add(groupId)
    }
    set({ collapsedGroups: groups })
  },

  collapseAll: (groupIds) => set({ collapsedGroups: new Set(groupIds) }),
  expandAll: () => set({ collapsedGroups: new Set() }),

  openTransactionEditor: (transactionId) =>
    set({ isTransactionEditorOpen: true, editingTransactionId: transactionId ?? null }),
  closeTransactionEditor: () =>
    set({ isTransactionEditorOpen: false, editingTransactionId: null }),

  openAccountEditor: () => set({ isAccountEditorOpen: true }),
  closeAccountEditor: () => set({ isAccountEditorOpen: false }),

  setMobileSidebarOpen: (open) => set({ mobileSidebarOpen: open }),

  toggleCategorySelection: (id, shiftKey = false, orderedIds = []) => {
    const { selectedCategoryIds, lastSelectedCategoryId } = get()
    const next = new Set(selectedCategoryIds)

    if (shiftKey && lastSelectedCategoryId && orderedIds.length > 0) {
      const fromIdx = orderedIds.indexOf(lastSelectedCategoryId)
      const toIdx = orderedIds.indexOf(id)
      if (fromIdx !== -1 && toIdx !== -1) {
        const [start, end] = fromIdx < toIdx ? [fromIdx, toIdx] : [toIdx, fromIdx]
        for (let i = start; i <= end; i++) next.add(orderedIds[i])
        set({ selectedCategoryIds: next, lastSelectedCategoryId: id })
        return
      }
    }

    if (next.has(id)) {
      next.delete(id)
    } else {
      next.add(id)
    }
    set({ selectedCategoryIds: next, lastSelectedCategoryId: next.has(id) ? id : lastSelectedCategoryId })
  },

  selectGroupCategories: (ids) => {
    const { selectedCategoryIds } = get()
    const allSelected = ids.every((id) => selectedCategoryIds.has(id))
    const next = new Set(selectedCategoryIds)
    if (allSelected) {
      ids.forEach((id) => next.delete(id))
    } else {
      ids.forEach((id) => next.add(id))
    }
    set({ selectedCategoryIds: next })
  },

  clearCategorySelection: () => set({ selectedCategoryIds: new Set(), lastSelectedCategoryId: null }),

  setCategoryInspectorOpen: (open) => set({ categoryInspectorOpen: open }),

  toggleTransactionSelection: (id, shiftKey = false, orderedIds = []) => {
    const { selectedTransactionIds, lastSelectedTransactionId } = get()
    const next = new Set(selectedTransactionIds)

    if (shiftKey && lastSelectedTransactionId && orderedIds.length > 0) {
      const fromIdx = orderedIds.indexOf(lastSelectedTransactionId)
      const toIdx = orderedIds.indexOf(id)
      if (fromIdx !== -1 && toIdx !== -1) {
        const [start, end] = fromIdx < toIdx ? [fromIdx, toIdx] : [toIdx, fromIdx]
        for (let i = start; i <= end; i++) next.add(orderedIds[i])
        set({ selectedTransactionIds: next, lastSelectedTransactionId: id })
        return
      }
    }

    if (next.has(id)) {
      next.delete(id)
    } else {
      next.add(id)
    }
    set({ selectedTransactionIds: next, lastSelectedTransactionId: next.has(id) ? id : lastSelectedTransactionId })
  },

  selectAllTransactions: (ids) => set({ selectedTransactionIds: new Set(ids) }),

  clearTransactionSelection: () => set({ selectedTransactionIds: new Set(), lastSelectedTransactionId: null }),

  toggleSection: (section) => {
    const sections = new Set(get().collapsedSections)
    if (sections.has(section)) {
      sections.delete(section)
    } else {
      sections.add(section)
    }
    set({ collapsedSections: sections })
  },

  setTransactionSort: (column, direction) => set({
    transactionSortColumn: column,
    transactionSortDirection: direction,
  }),

  setTransactionSearch: (query) => set({ transactionSearchQuery: query }),

  activeBudgetViewId: null,
  isViewModalOpen: false,
  editingViewId: null,
  setActiveBudgetView: (viewId) => set({ activeBudgetViewId: viewId }),
  openViewModal: (viewId) => set({ isViewModalOpen: true, editingViewId: viewId ?? null }),
  closeViewModal: () => set({ isViewModalOpen: false, editingViewId: null }),

  isReconciling: false,
  reconcileAccountId: null,
  reconcileStatementBalance: null,
  reconcileAdjustmentTxnId: null,
  startReconciliation: (accountId) => set({
    isReconciling: true,
    reconcileAccountId: accountId,
    reconcileStatementBalance: null,
    reconcileAdjustmentTxnId: null,
  }),
  setReconcileStatementBalance: (balance) => set({ reconcileStatementBalance: balance }),
  setReconcileAdjustmentTxnId: (txnId) => set({ reconcileAdjustmentTxnId: txnId }),
  cancelReconciliation: () => set({
    isReconciling: false,
    reconcileAccountId: null,
    reconcileStatementBalance: null,
    reconcileAdjustmentTxnId: null,
  }),
}))
