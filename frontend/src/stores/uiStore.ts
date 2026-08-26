import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { PERSIST_KEYS } from './persistKeys'
import { SIDEBAR_MIN_WIDTH, clampSidebarWidth } from '../components/layout/Sidebar/sidebarWidth'
import type { AssignStrategy } from '../types'

type TransactionSortColumn = 'date' | 'account' | 'payee' | 'category' | 'memo' | 'amount'
type SortDirection = 'asc' | 'desc'
type CollapsibleSection = 'pending' | 'uncategorized' | 'upcoming'
export type QuickFilter = 'overspent' | 'underfunded' | 'money-available' | 'overfunded'

export const ALL_QUICK_FILTERS: QuickFilter[] = ['overspent', 'underfunded', 'money-available', 'overfunded']

/** How a quick filter reads, and which state colour it carries. Here rather
 *  than in either component that draws them: the bar and the manage modal
 *  each had their own copy, so renaming a filter in one left the chip and its
 *  settings row disagreeing about what the same filter is called. */
export const QUICK_FILTER_LABELS: Record<QuickFilter, string> = {
  overspent: 'Overspent',
  underfunded: 'Underfunded',
  'money-available': 'Money Available',
  overfunded: 'Overfunded',
}

export const QUICK_FILTER_VARIANTS: Record<QuickFilter, string> = {
  overspent: 'negative',
  underfunded: 'warning',
  'money-available': 'positive',
  overfunded: 'positive',
}

/** Every dialog whose open/closed state is global rather than local to the
 *  component that raises it. Promise-based questions (confirmStore) are not
 *  here: they have one slot of their own and resolve to a value. */
export type ModalKind =
  | 'transaction'
  | 'account'
  | 'add-account'
  | 'liability'
  | 'view'
  | 'manage-views'
  | 'filter'
  | 'manage-filters'

export interface ActiveModal {
  kind: ModalKind
  /** The row being edited; null means "new". */
  editingId: string | null
}

interface UIState {
  collapsedGroups: Set<string>
  /** One slot, so opening a dialog closes whatever was open.
   *
   *  This was eight independent booleans, each with its own editing-id and its
   *  own open/close pair — and nothing stopped two being true at once, so
   *  raising the filter dialog while the view dialog stood rendered both,
   *  stacked. Being able to represent that at all was the bug. */
  activeModal: ActiveModal | null
  sidebarCollapsed: boolean
  /** Resizable sidebar width in px; clamped by setSidebarWidth. */
  sidebarWidth: number
  /** Which sidebar account groups are folded shut, by the ids in
   *  `SIDEBAR_SECTION_IDS` / `sidebarTypeGroupId`. Separate from
   *  `collapsedGroups`, which is the budget page's category groups: one Set
   *  for both would make renaming a category group collapse a sidebar
   *  section. */
  collapsedSidebarGroups: Set<string>

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
  openModal: (kind: ModalKind, editingId?: string | null) => void
  closeModal: () => void
  toggleSidebarCollapsed: () => void
  setSidebarWidth: (px: number) => void
  toggleSidebarGroup: (groupId: string) => void
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
  setActiveFilter: (filterId: string | null) => void

  // Quick filters
  activeQuickFilter: QuickFilter | null
  quickFilterOrder: QuickFilter[]
  setActiveQuickFilter: (filter: QuickFilter | null) => void
  reorderQuickFilters: (order: QuickFilter[]) => void

  // Category name filter (combines with filters/quick filters)
  categorySearch: string
  setCategorySearch: (query: string) => void

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
  activeModal: null,
  sidebarCollapsed: false,
  sidebarWidth: SIDEBAR_MIN_WIDTH,
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

  openModal: (kind, editingId) => set({ activeModal: { kind, editingId: editingId ?? null } }),
  closeModal: () => set({ activeModal: null }),


  toggleSidebarCollapsed: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setSidebarWidth: (px) => set({ sidebarWidth: clampSidebarWidth(px) }),

  collapsedSidebarGroups: new Set<string>(),
  toggleSidebarGroup: (groupId) => {
    const groups = new Set(get().collapsedSidebarGroups)
    if (groups.has(groupId)) groups.delete(groupId)
    else groups.add(groupId)
    set({ collapsedSidebarGroups: groups })
  },

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
  setActiveFilter: (filterId) => set({ activeFilterId: filterId, activeQuickFilter: null }),

  activeQuickFilter: null,
  quickFilterOrder: [...ALL_QUICK_FILTERS],
  setActiveQuickFilter: (filter) => set({ activeQuickFilter: filter, activeFilterId: null }),
  reorderQuickFilters: (order) => set({ quickFilterOrder: order }),

  categorySearch: '',
  setCategorySearch: (query) => set({ categorySearch: query }),


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
        // A width someone dragged to is a deliberate choice, like a filter.
        sidebarWidth: s.sidebarWidth,
        // So is folding a section shut. A Set does not survive JSON — it
        // stringifies to `{}` — so it is stored as an array and rebuilt in
        // merge() below. Persisting the Set directly rehydrates a plain
        // object whose `.has` is undefined, which throws on first render.
        collapsedSidebarGroups: [...s.collapsedSidebarGroups],
      }),
      merge: (persisted, current) => {
        const saved = (persisted ?? {}) as Partial<
          Omit<UIState, 'collapsedSidebarGroups'> & { collapsedSidebarGroups: string[] }
        >
        return {
          ...current,
          ...saved,
          collapsedSidebarGroups: new Set(saved.collapsedSidebarGroups ?? []),
        }
      },
    }
  )
)
