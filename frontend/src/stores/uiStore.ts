import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { PERSIST_KEYS } from './persistKeys'
import type { AssignStrategy } from '../types'

type TransactionSortColumn = 'date' | 'account' | 'payee' | 'category' | 'memo' | 'amount'
type SortDirection = 'asc' | 'desc'
type CollapsibleSection = 'pending' | 'uncategorized' | 'upcoming'
export type QuickFilter = 'overspent' | 'underfunded' | 'money-available' | 'overfunded'

export const ALL_QUICK_FILTERS: QuickFilter[] = ['overspent', 'underfunded', 'money-available', 'overfunded']

interface UIState {
  collapsedGroups: Set<string>
  isTransactionEditorOpen: boolean
  editingTransactionId: string | null
  isAccountEditorOpen: boolean
  editingAccountId: string | null
  isAddAccountModalOpen: boolean
  isLiabilityEditorOpen: boolean
  editingLiabilityId: string | null
  sidebarCollapsed: boolean

  // Mobile shell (bottom nav)
  quickAddOpen: boolean
  moreSheetOpen: boolean
  mobileInspectorOpen: boolean
  openQuickAdd: () => void
  closeQuickAdd: () => void
  openMoreSheet: () => void
  closeMoreSheet: () => void
  openMobileInspector: () => void
  closeMobileInspector: () => void
  budgetRowMode: 'expanded' | 'compressed'
  selectedCategoryIds: Set<string>
  categoryInspectorOpen: boolean
  inspectorUserClosed: boolean
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
  openAccountEditor: (accountId: string) => void
  closeAccountEditor: () => void
  openAddAccountModal: () => void
  closeAddAccountModal: () => void
  openLiabilityEditor: (liabilityId: string | null) => void
  closeLiabilityEditor: () => void
  toggleSidebarCollapsed: () => void
  toggleBudgetRowMode: () => void
  toggleCategorySelection: (id: string, shiftKey?: boolean, orderedIds?: string[]) => void
  selectOnlyCategory: (id: string) => void
  selectGroupCategories: (ids: string[]) => void
  clearCategorySelection: () => void
  setCategoryInspectorOpen: (open: boolean) => void

  // Transaction selection actions
  toggleTransactionSelection: (id: string, shiftKey?: boolean, orderedIds?: string[]) => void
  selectAllTransactions: (ids: string[]) => void
  clearTransactionSelection: () => void

  // Payee selection actions
  selectedPayeeIds: Set<string>
  lastSelectedPayeeId: string | null
  togglePayeeSelection: (id: string, shiftKey?: boolean, orderedIds?: string[]) => void
  selectAllPayees: (ids: string[]) => void
  clearPayeeSelection: () => void
  toggleSection: (section: CollapsibleSection) => void
  setTransactionSort: (column: TransactionSortColumn, direction: SortDirection) => void
  setTransactionSearch: (query: string) => void

  // Budget filters
  activeFilterId: string | null
  /** How categories are grouped on the budget page. Orthogonal to
   *  activeFilterId: a view decides the arrangement, a filter decides which of
   *  those categories show. Both can be on at once. */
  activeViewId: string | null
  setActiveView: (viewId: string | null) => void
  isViewModalOpen: boolean
  editingViewId: string | null
  openViewModal: (viewId?: string) => void
  closeViewModal: () => void
  isManageViewsModalOpen: boolean
  openManageViewsModal: () => void
  closeManageViewsModal: () => void
  isFilterModalOpen: boolean
  editingFilterId: string | null
  setActiveFilter: (filterId: string | null) => void
  openFilterModal: (filterId?: string) => void
  closeFilterModal: () => void

  // Quick filters
  activeQuickFilter: QuickFilter | null
  quickFilterOrder: QuickFilter[]
  setActiveQuickFilter: (filter: QuickFilter | null) => void
  reorderQuickFilters: (order: QuickFilter[]) => void

  // Category name filter (combines with filters/quick filters)
  categorySearch: string
  setCategorySearch: (query: string) => void

  // Manage filters modal
  isManageFiltersModalOpen: boolean
  openManageFiltersModal: () => void
  closeManageFiltersModal: () => void

  // Command palette
  isPaletteOpen: boolean
  openPalette: () => void
  closePalette: () => void
  togglePalette: () => void

  // TBA hero (store-driven so the palette can trigger them from anywhere)
  assignDropdownOpen: boolean
  setAssignDropdownOpen: (open: boolean) => void
  assignPreviewStrategy: AssignStrategy | null
  setAssignPreviewStrategy: (strategy: AssignStrategy | null) => void
  isCoverOverspentOpen: boolean
  setCoverOverspentOpen: (open: boolean) => void
  tbaDrawerOpen: boolean
  setTbaDrawerOpen: (open: boolean) => void

  // Multi-month side-by-side view (desktop only)
  multiMonthOpen: boolean
  setMultiMonthOpen: (open: boolean) => void

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

export const useUIStore = create<UIState>()(
  persist(
    (set, get) => ({
  collapsedGroups: new Set(),
  isTransactionEditorOpen: false,
  editingTransactionId: null,
  isAccountEditorOpen: false,
  editingAccountId: null,
  isAddAccountModalOpen: false,
  isLiabilityEditorOpen: false,
  editingLiabilityId: null,
  sidebarCollapsed: false,
  budgetRowMode: 'expanded',
  selectedCategoryIds: new Set(),
  categoryInspectorOpen: true,
  inspectorUserClosed: false,
  lastSelectedCategoryId: null,

  selectedTransactionIds: new Set(),
  lastSelectedTransactionId: null,

  selectedPayeeIds: new Set(),
  lastSelectedPayeeId: null,
  collapsedSections: new Set<CollapsibleSection>(['pending']),
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

  openAccountEditor: (accountId) => set({ isAccountEditorOpen: true, editingAccountId: accountId }),
  closeAccountEditor: () => set({ isAccountEditorOpen: false, editingAccountId: null }),
  openAddAccountModal: () => set({ isAddAccountModalOpen: true }),
  closeAddAccountModal: () => set({ isAddAccountModalOpen: false }),
  openLiabilityEditor: (liabilityId) =>
    set({ isLiabilityEditorOpen: true, editingLiabilityId: liabilityId }),
  closeLiabilityEditor: () => set({ isLiabilityEditorOpen: false, editingLiabilityId: null }),

  toggleSidebarCollapsed: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  quickAddOpen: false,
  moreSheetOpen: false,
  mobileInspectorOpen: false,
  openQuickAdd: () => set({ quickAddOpen: true }),
  closeQuickAdd: () => set({ quickAddOpen: false }),
  openMoreSheet: () => set({ moreSheetOpen: true }),
  closeMoreSheet: () => set({ moreSheetOpen: false }),
  openMobileInspector: () => set({ mobileInspectorOpen: true }),
  closeMobileInspector: () => set({ mobileInspectorOpen: false }),
  toggleBudgetRowMode: () => set((s) => ({ budgetRowMode: s.budgetRowMode === 'expanded' ? 'compressed' : 'expanded' })),

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

  selectOnlyCategory: (id) => {
    const { selectedCategoryIds } = get()
    // Clicking the already-sole selection deselects it
    if (selectedCategoryIds.size === 1 && selectedCategoryIds.has(id)) {
      set({ selectedCategoryIds: new Set(), lastSelectedCategoryId: null })
    } else {
      set({ selectedCategoryIds: new Set([id]), lastSelectedCategoryId: id })
    }
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

  setCategoryInspectorOpen: (open) => set({ categoryInspectorOpen: open, inspectorUserClosed: !open }),

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

  togglePayeeSelection: (id, shiftKey = false, orderedIds = []) => {
    const { selectedPayeeIds, lastSelectedPayeeId } = get()
    const next = new Set(selectedPayeeIds)

    if (shiftKey && lastSelectedPayeeId && orderedIds.length > 0) {
      const fromIdx = orderedIds.indexOf(lastSelectedPayeeId)
      const toIdx = orderedIds.indexOf(id)
      if (fromIdx !== -1 && toIdx !== -1) {
        const [start, end] = fromIdx < toIdx ? [fromIdx, toIdx] : [toIdx, fromIdx]
        for (let i = start; i <= end; i++) next.add(orderedIds[i])
        set({ selectedPayeeIds: next, lastSelectedPayeeId: id })
        return
      }
    }

    if (next.has(id)) {
      next.delete(id)
    } else {
      next.add(id)
    }
    set({ selectedPayeeIds: next, lastSelectedPayeeId: next.has(id) ? id : lastSelectedPayeeId })
  },

  selectAllPayees: (ids) => set({ selectedPayeeIds: new Set(ids) }),

  clearPayeeSelection: () => set({ selectedPayeeIds: new Set(), lastSelectedPayeeId: null }),

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

  activeFilterId: null,
  activeViewId: null,
  setActiveView: (viewId) => set({ activeViewId: viewId }),
  isViewModalOpen: false,
  editingViewId: null,
  openViewModal: (viewId) => set({ isViewModalOpen: true, editingViewId: viewId ?? null }),
  closeViewModal: () => set({ isViewModalOpen: false, editingViewId: null }),
  isManageViewsModalOpen: false,
  openManageViewsModal: () => set({ isManageViewsModalOpen: true }),
  closeManageViewsModal: () => set({ isManageViewsModalOpen: false }),
  isFilterModalOpen: false,
  editingFilterId: null,
  setActiveFilter: (filterId) => set({ activeFilterId: filterId, activeQuickFilter: null }),
  openFilterModal: (filterId) => set({ isFilterModalOpen: true, editingFilterId: filterId ?? null }),
  closeFilterModal: () => set({ isFilterModalOpen: false, editingFilterId: null }),

  activeQuickFilter: null,
  quickFilterOrder: [...ALL_QUICK_FILTERS],
  setActiveQuickFilter: (filter) => set({ activeQuickFilter: filter, activeFilterId: null }),
  reorderQuickFilters: (order) => set({ quickFilterOrder: order }),

  categorySearch: '',
  setCategorySearch: (query) => set({ categorySearch: query }),

  isManageFiltersModalOpen: false,
  openManageFiltersModal: () => set({ isManageFiltersModalOpen: true }),
  closeManageFiltersModal: () => set({ isManageFiltersModalOpen: false }),

  isPaletteOpen: false,
  openPalette: () => set({ isPaletteOpen: true }),
  closePalette: () => set({ isPaletteOpen: false }),
  togglePalette: () => set((s) => ({ isPaletteOpen: !s.isPaletteOpen })),

  assignDropdownOpen: false,
  setAssignDropdownOpen: (open) => set({ assignDropdownOpen: open }),
  assignPreviewStrategy: null,
  setAssignPreviewStrategy: (strategy) => set({ assignPreviewStrategy: strategy }),
  isCoverOverspentOpen: false,
  setCoverOverspentOpen: (open) => set({ isCoverOverspentOpen: open }),
  tbaDrawerOpen: false,
  setTbaDrawerOpen: (open) => set({ tbaDrawerOpen: open }),

  multiMonthOpen: false,
  setMultiMonthOpen: (open) => set({ multiMonthOpen: open }),

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
}),
    {
      name: PERSIST_KEYS.ui,
      // Only the two selections a user makes deliberately and expects to find
      // still applied. Everything else here is transient dialog state that
      // would be actively wrong to restore — reloading into a half-open
      // reconciliation or editor is worse than losing it.
      partialize: (s) => ({
        activeFilterId: s.activeFilterId,
        activeViewId: s.activeViewId,
        quickFilterOrder: s.quickFilterOrder,
      }),
    }
  )
)
