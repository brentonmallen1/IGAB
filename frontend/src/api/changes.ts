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

export interface Change {
  id: string
  /** `budget` appears only as the subject of a `reorder` of its groups. */
  entity_type: 'transaction' | 'payee' | 'category' | 'category_group' | 'assignment' | 'budget'
  entity_id: string
  action: 'create' | 'update' | 'delete' | 'approve' | 'import' | 'merge' | 'reorder'
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  batch_id: string | null
  source: 'manual' | 'import' | 'ai' | 'system'
  undone_at: string | null
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

// Query key factory for cache invalidation
export const changesKeys = {
  all: ['changes'] as const,
  budget: (budgetId: string) => [...changesKeys.all, budgetId] as const,
}

export function useChanges(budgetId: string | null, limit = 50, offset = 0) {
  return useQuery({
    queryKey: [...changesKeys.budget(budgetId ?? ''), { limit, offset }],
    queryFn: async () => {
      const { data } = await apiClient.get<ChangesResponse>(
        `/${budgetId}/changes`,
        { params: { limit, offset } }
      )
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
      const message =
        error instanceof Error
          ? error.message
          : 'Could not undo this change'
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
      const message =
        error instanceof Error
          ? error.message
          : 'Could not undo this batch'
      toast.error(message)
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
    qc.refetchQueries({ queryKey: ['transactions', accountId] })
  } else {
    qc.invalidateQueries({ queryKey: ['transactions'] })
  }
  qc.invalidateQueries({ queryKey: ['all-transactions'] })
  qc.invalidateQueries({ queryKey: ['category-transactions', budgetId] })

  // Budget/assignment data
  qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
  qc.invalidateQueries({ queryKey: ['accounts', budgetId] })

  // Payee data
  qc.invalidateQueries({ queryKey: ['payees', budgetId] })
  qc.invalidateQueries({ queryKey: ['duplicatePayees', budgetId] })

  // Category data. Undoing a category delete restores the category, its
  // transactions, its assignments and its view placements at once, so this
  // borrows the delete's own list rather than keeping a second, shorter one
  // here — which is how `['category-groups']` sat here for months quietly
  // refreshing nothing (the real key is `['categoryGroups']`).
  invalidateAfterCategoryChange(qc, budgetId)

  // Review counts
  qc.invalidateQueries({ queryKey: ['pending-review-count'] })
  if (accountId) {
    qc.invalidateQueries({ queryKey: ['pending-review-count-account', accountId] })
  }
}
