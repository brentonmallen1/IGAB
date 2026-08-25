import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { apiClient, apiErrorMessage } from './client'
import { invalidateAfterCategoryChange } from './invalidateAfterCategoryChange'
import type { Category, CategoryGroup, CategoryClassification } from '../types'

export function useCategoryGroups(budgetId: string | null, includeHidden = false) {
  return useQuery({
    queryKey: ['categoryGroups', budgetId, includeHidden],
    queryFn: async () => {
      const { data } = await apiClient.get<CategoryGroup[]>(`/${budgetId}/category-groups`, {
        params: { include_hidden: includeHidden },
      })
      return data
    },
    enabled: !!budgetId,
    staleTime: 60_000,
  })
}

export function useCategories(budgetId: string | null, includeHidden = false) {
  return useQuery({
    queryKey: ['categories', budgetId, includeHidden],
    queryFn: async () => {
      const { data } = await apiClient.get<Category[]>(`/${budgetId}/categories`, {
        params: { include_hidden: includeHidden },
      })
      return data
    },
    enabled: !!budgetId,
    staleTime: 60_000,
  })
}

export interface RecentPayee {
  payee_id: string
  name: string
}

/** Most recent (non-transfer) payee used in a category — add-transaction prefill */
export function useRecentPayeeForCategory(budgetId: string, categoryId: string | null) {
  return useQuery({
    queryKey: ['recentPayee', budgetId, categoryId],
    queryFn: async () => {
      const { data } = await apiClient.get<RecentPayee | null>(
        `/categories/${categoryId}/recent-payee`,
        { params: { budget_id: budgetId } }
      )
      return data
    },
    enabled: !!budgetId && !!categoryId,
    staleTime: 60_000,
  })
}

/** How this category's recent activity counts in reports — fetched when the
 *  inspector opens on one category, the same way the transaction editor asks
 *  about one row. `dominant` set = it deserves a badge. */
export function useCategoryClassification(categoryId: string | null) {
  return useQuery({
    queryKey: ['categoryClassification', categoryId],
    queryFn: async () => {
      const { data } = await apiClient.get<CategoryClassification>(
        `/categories/${categoryId}/classification`
      )
      return data
    },
    enabled: !!categoryId,
    staleTime: 60_000,
  })
}

export function useCreateCategoryGroup(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { name: string; sort_order?: number }) =>
      apiClient.post<CategoryGroup>(`/${budgetId}/category-groups`, data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['categoryGroups', budgetId] })
    },
  })
}

export function useCreateCategory(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: {
      category_group_id: string
      name: string
      subtitle?: string
      sort_order?: number
      note?: string
    }) => apiClient.post<Category>(`/${budgetId}/categories`, data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['categories', budgetId] })
    },
  })
}

export function useUpdateCategory(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...data }: Partial<Category> & { id: string }) =>
      apiClient.patch<Category>(`/categories/${id}`, data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['categories', budgetId] })
    },
  })
}

export function useUpdateCategoryGroup(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string; name?: string; is_hidden?: boolean; sort_order?: number }) =>
      apiClient.patch<CategoryGroup>(`/category-groups/${id}`, data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['categoryGroups', budgetId] })
    },
  })
}

/** Set the order of every category group in one request.
 *
 *  One request rather than a PATCH per group: a drag that half-applies leaves
 *  an order the user did not choose. The server refuses a list that does not
 *  name every live group exactly once, so a stale client fails loudly instead
 *  of shuffling rows it never showed. */
export function useReorderCategoryGroups(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (groupIds: string[]) =>
      apiClient.post(`/${budgetId}/category-groups/reorder`, { group_ids: groupIds }),
    onMutate: async (groupIds) => {
      // Optimistic: a drag that snaps back for a round trip reads as a failed
      // drag. Kept as the previous list so an error can restore it.
      await qc.cancelQueries({ queryKey: ['categoryGroups', budgetId] })
      const previous = qc.getQueryData<CategoryGroup[]>(['categoryGroups', budgetId])
      if (previous) {
        const byId = new Map(previous.map((g) => [g.id, g]))
        const reordered = groupIds
          .map((id, i) => {
            const g = byId.get(id)
            return g ? { ...g, sort_order: i } : null
          })
          .filter((g): g is CategoryGroup => g !== null)
        qc.setQueryData(['categoryGroups', budgetId], reordered)
      }
      return { previous }
    },
    onError: (err, _ids, ctx) => {
      if (ctx?.previous) qc.setQueryData(['categoryGroups', budgetId], ctx.previous)
      toast.error(apiErrorMessage(err, 'Could not save the new order'))
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['categoryGroups', budgetId] })
      // Group order is part of how the month reads, so anything caching the
      // grid's shape has to follow.
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
    },
  })
}

/** What deleting will do, so the dialog can say it before the user commits.
 *  The same numbers the delete then reports back — pinned by a differential
 *  test on the server (test_category_delete.py). */
export interface CategoryDeletePreview {
  category_ids: string[]
  category_names: string[]
  transaction_count: number
  /** Of those, how many are reconciled — they cannot be re-filed by hand
   *  afterwards without unlocking them first, so the dialog says so. */
  reconciled_count: number
  available: string
  future_assigned: string
  payee_count: number
  scheduled_count: number
  /** Non-empty means the delete is refused (a linked payment or debt
   *  category); each entry names the counterpart and what to do instead. */
  blocked_by: string[]
  /** Nothing to decide — delete without showing the dialog at all. */
  is_empty: boolean
}

export interface CategoryDeleteResult {
  /** Undo this one row to reverse the whole operation. */
  change_id: string
  category_ids: string[]
  transactions_moved: number
  transactions_uncategorized: number
  assignments_removed: number
  /** What actually reached Ready to Assign. Not the assignments removed —
   *  money already spent out of an envelope does not come back. */
  released: string
}

/** What the delete dialog is about to act on: a selection of categories, or a
 *  whole group (which cascades over the categories inside it). */
export type DeleteTarget =
  | { kind: 'categories'; ids: string[]; name: string }
  | { kind: 'group'; id: string; name: string }

export function useCategoryDeletePreview(
  budgetId: string,
  target: DeleteTarget | null,
  month: string
) {
  const key = target?.kind === 'group' ? target.id : (target?.ids.join(',') ?? '')
  return useQuery({
    queryKey: ['categoryDeletePreview', budgetId, target?.kind, key, month],
    queryFn: async () => {
      if (target?.kind === 'group') {
        const { data } = await apiClient.get<CategoryDeletePreview>(
          `/category-groups/${target.id}/delete-preview`,
          { params: { month } }
        )
        return data
      }
      const { data } = await apiClient.post<CategoryDeletePreview>(
        `/${budgetId}/categories/delete-preview`,
        { category_ids: target!.ids, month }
      )
      return data
    },
    enabled: !!target,
    // Never served from cache: it quantifies money and drives a destructive
    // button, so an answer from before the user's last edit is exactly the
    // wrong thing to put in front of them.
    staleTime: 0,
    gcTime: 0,
  })
}

export interface DeleteCategoryVars {
  target: DeleteTarget
  /** Re-file the transactions here; null leaves them uncategorized, showing
   *  "Needs Category" with a `was:` hint. */
  moveTo: string | null
  month: string
}

/**
 * One mutation for both shapes, because both are one operation on the server:
 * a selection of categories and a whole group each produce a single change row
 * carrying everything needed to undo them together.
 */
export function useDeleteCategories(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ target, moveTo, month }: DeleteCategoryVars) => {
      if (target.kind === 'group') {
        const { data } = await apiClient.delete<CategoryDeleteResult>(
          `/category-groups/${target.id}`,
          { params: { move_to: moveTo ?? undefined, month } }
        )
        return data
      }
      const { data } = await apiClient.post<CategoryDeleteResult>(
        `/${budgetId}/categories/delete`,
        { category_ids: target.ids, move_to: moveTo, month }
      )
      return data
    },
    onSuccess: () => invalidateAfterCategoryChange(qc, budgetId),
    onError: (e) => toast.error(apiErrorMessage(e, 'Could not delete')),
  })
}

export interface RepairOrphansResult {
  categories_repaired: number
  transactions_uncategorized: number
  assignments_removed: number
  released: string
  change_ids: string[]
  categories_under_deleted_groups: number
}

/** Finish the job on categories deleted before deleting was a real operation. */
export function useRepairOrphanedCategories(budgetId: string, month: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post<RepairOrphansResult>(
        `/${budgetId}/categories/hygiene/repair-orphans`,
        null,
        { params: { month } }
      )
      return data
    },
    onSuccess: () => invalidateAfterCategoryChange(qc, budgetId),
    onError: (e) => toast.error(apiErrorMessage(e, 'Could not repair categories')),
  })
}
