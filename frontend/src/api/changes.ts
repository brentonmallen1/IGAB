/**
 * Change history and undo API hooks.
 *
 * A "change" is an atomic user-visible mutation (create/update/delete/approve/merge)
 * recorded by the backend. Batched operations (e.g. bulk delete, transfers, splits)
 * share a batch_id so they can be undone together.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { apiClient } from './client'
import { invalidateAfterCategoryChange } from './invalidateAfterCategoryChange'
import { ROOT } from './queryKeys'

export interface Change {
  id: string
  /** The log's one total order, newest highest. */
  seq: number
  /** `budget` appears only as the subject of a `reorder` of its groups;
   *  `wishlist` is the same pseudo-subject for a reorder of wishes or
   *  wish projects. */
  entity_type:
    | 'transaction'
    | 'payee'
    | 'category'
    | 'category_group'
    | 'assignment'
    | 'budget'
    | 'wishlist_item'
    | 'wishlist_project'
    | 'wishlist'
    | 'category_target'
    | 'liability'
    | 'liability_snapshot'
    | 'asset'
    | 'asset_value'
    | 'scheduled_transaction'
    | 'budget_view'
    | 'budget_filter'
    | 'tag'
    | 'category_tags'
    | 'payee_tags'
    | 'account'
    | 'account_type'
  entity_id: string
  action:
    | 'create'
    | 'update'
    | 'delete'
    | 'approve'
    | 'import'
    | 'merge'
    | 'reorder'
    | 'archive'
    | 'unarchive'
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  batch_id: string | null
  source: 'manual' | 'import' | 'ai' | 'system'
  undone_at: string | null
  /** Redo-stack order: the undone row with the highest value is the redo
   *  head. Null while live. */
  undo_seq: number | null
  created_at: string
  /** Actor — null for system/AI changes. */
  user_id: string | null
  user_display_name: string | null
}

interface ChangesResponse {
  changes: Change[]
  total: number
}

interface UndoResponse {
  undone_change_ids: string[]
}

/** What ⌘Z undid — served with the result so the toast needs no second fetch. */
export interface UndoLatestResponse extends UndoResponse {
  action: Change['action']
  entity_type: Change['entity_type']
}

// Query key factory for cache invalidation
export const changesKeys = {
  all: [ROOT.changes] as const,
  budget: (budgetId: string) => [...changesKeys.all, budgetId] as const,
}

export function useChanges(budgetId: string | null, limit = 50, offset = 0) {
  return useQuery({
    queryKey: [...changesKeys.budget(budgetId ?? ''), { limit, offset }],
    queryFn: async () => {
      const { data } = await apiClient.get<ChangesResponse>(`/${budgetId}/changes`, {
        params: { limit, offset },
      })
      return data
    },
    enabled: !!budgetId,
  })
}

/**
 * Undo a single change (or the whole batch if this change belongs to one).
 *
 * Use `onSuccess` of the returned mutation to invalidate any UI-specific queries
 * (transaction lists, budget month, etc). This hook handles the changes cache
 * and shows a toast on error.
 */
export function useUndoChange(budgetId: string) {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async ({ changeId, force = false }: { changeId: string; force?: boolean }) => {
      const { data } = await apiClient.post<UndoResponse>(
        `/${budgetId}/changes/${changeId}/undo`,
        null,
        { params: { force } }
      )
      return data
    },
    onSuccess: () => {
      // Invalidate changes list so undone_at updates
      qc.invalidateQueries({ queryKey: changesKeys.budget(budgetId) })
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Could not undo this change'
      toast.error(message)
    },
  })
}

/**
 * Undo an entire batch of changes.
 *
 * Prefer useUndoChange (by changeId) when you only have a single change reference;
 * this is for explicit batch-undo UI (e.g. "Undo import").
 */
export function useUndoBatch(budgetId: string) {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async ({ batchId, force = false }: { batchId: string; force?: boolean }) => {
      const { data } = await apiClient.post<UndoResponse>(
        `/${budgetId}/changes/batch/${batchId}/undo`,
        null,
        { params: { force } }
      )
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: changesKeys.budget(budgetId) })
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Could not undo this batch'
      toast.error(message)
    },
  })
}

/**
 * Undo everything recorded after this change — the Activity page's line
 * between two entries, where the id passed is the newest entry BELOW it.
 *
 * `dryRun` asks what would go without touching anything, so the confirmation
 * counts with the same query that does the work rather than a second one that
 * could disagree with it.
 */
export function useUndoNewer(budgetId: string) {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async ({
      changeId,
      dryRun = false,
      force = false,
    }: {
      changeId: string
      dryRun?: boolean
      force?: boolean
    }) => {
      const { data } = await apiClient.post<UndoResponse>(
        `/${budgetId}/changes/${changeId}/undo-newer`,
        null,
        { params: { dry_run: dryRun, force } }
      )
      return data
    },
    onSuccess: (_data, variables) => {
      if (!variables.dryRun) {
        qc.invalidateQueries({ queryKey: changesKeys.budget(budgetId) })
      }
    },
  })
}

/**
 * Invalidate all data that might be affected by an undo operation.
 *
 * Call this from component-level onSuccess handlers after using useUndoChange
 * or useUndoBatch. The queries to invalidate depend on what kind of entity
 * was undone; this helper invalidates everything conservatively.
 */
export function invalidateAfterUndo(
  qc: ReturnType<typeof useQueryClient>,
  budgetId: string,
  accountId?: string | null
) {
  // Transaction data
  if (accountId) {
    qc.refetchQueries({ queryKey: [ROOT.transactions, accountId] })
  } else {
    qc.invalidateQueries({ queryKey: [ROOT.transactions] })
  }
  qc.invalidateQueries({ queryKey: [ROOT.allTransactions] })
  qc.invalidateQueries({ queryKey: [ROOT.budgetTransactions] })
  qc.invalidateQueries({ queryKey: [ROOT.transactionsPeek] })
  qc.invalidateQueries({ queryKey: [ROOT.payeeTransactions] })

  // Budget/assignment data
  qc.invalidateQueries({ queryKey: [ROOT.budgetMonth, budgetId] })
  qc.invalidateQueries({ queryKey: [ROOT.accounts, budgetId] })

  // Payee data
  qc.invalidateQueries({ queryKey: [ROOT.payees, budgetId] })
  // No duplicate-payee entry: `useFetchPayeeDuplicates` is a mutation that
  // holds its result in component state, so there is no cache to refresh.
  // `['duplicatePayees']` was invalidated here and answered by nothing.

  // Category data. Undoing a category delete restores the category, its
  // transactions, its assignments and its view placements at once, so this
  // borrows the delete's own list rather than keeping a second, shorter one
  // here — which is how `['category-groups']` sat here for months quietly
  // refreshing nothing (the real key is `['categoryGroups']`).
  invalidateAfterCategoryChange(qc, budgetId)

  // Review counts
  qc.invalidateQueries({ queryKey: [ROOT.pendingReviewCount] })
  if (accountId) {
    qc.invalidateQueries({ queryKey: [ROOT.pendingReviewCountAccount, accountId] })
  }

  // Wishlist: wishes, projects, and their reorders all live under one key.
  qc.invalidateQueries({ queryKey: [ROOT.wishlist, budgetId] })

  // Targets — never in invalidateAfterCategoryChange, so listed here.
  qc.invalidateQueries({ queryKey: [ROOT.target] })
  qc.invalidateQueries({ queryKey: [ROOT.targets] })

  // Debts and assets, including their balance/value histories.
  qc.invalidateQueries({ queryKey: [ROOT.liabilities] })
  qc.invalidateQueries({ queryKey: [ROOT.liabilityAmortization] })
  qc.invalidateQueries({ queryKey: [ROOT.assets] })
  qc.invalidateQueries({ queryKey: [ROOT.assetValues] })

  // Tags and their memberships.
  qc.invalidateQueries({ queryKey: [ROOT.tags] })
  qc.invalidateQueries({ queryKey: [ROOT.tagSuggestions] })

  // Accounts and their types (ROOT.accounts is budget-scoped above).
  qc.invalidateQueries({ queryKey: [ROOT.accountTypes] })
  qc.invalidateQueries({ queryKey: [ROOT.accountHygiene] })
  qc.invalidateQueries({ queryKey: [ROOT.cardTimeline] })
  qc.invalidateQueries({ queryKey: [ROOT.scheduledTransactions] })
}
