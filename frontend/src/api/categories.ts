import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { apiClient, apiErrorMessage } from './client'
import { invalidateAfterCategoryChange } from './invalidateAfterCategoryChange'
import { reorderMembers } from '../utils/listOrder'
import type { Category, CategoryGroup, CategoryClassification } from '../types'

export function useCategoryGroups(budgetId: string | null, includeArchived = false) {
  return useQuery({
    queryKey: ['categoryGroups', budgetId, includeArchived],
    queryFn: async () => {
      const { data } = await apiClient.get<CategoryGroup[]>(`/${budgetId}/category-groups`, {
        params: { include_archived: includeArchived },
      })
      return data
    },
    enabled: !!budgetId,
    staleTime: 60_000,
  })
}

export function useCategories(budgetId: string | null, includeArchived = false) {
  return useQuery({
    queryKey: ['categories', budgetId, includeArchived],
    queryFn: async () => {
      const { data } = await apiClient.get<Category[]>(`/${budgetId}/categories`, {
        params: { include_archived: includeArchived },
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

/** A new group goes last; the server assigns its position. */
export function useCreateCategoryGroup(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { name: string }) =>
      apiClient.post<CategoryGroup>(`/${budgetId}/category-groups`, data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['categoryGroups', budgetId] })
    },
  })
}

/** A new category goes last in its group; the server assigns its position. */
export function useCreateCategory(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { category_group_id: string; name: string; subtitle?: string; note?: string }) =>
      apiClient.post<Category>(`/${budgetId}/categories`, data).then((r) => r.data),
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
    // Moving a category to another group changes group subtotals, view
    // placements and every report that groups by category — the same list a
    // delete stales, so the same list is invalidated.
    onSuccess: () => invalidateAfterCategoryChange(qc, budgetId),
  })
}

export function useUpdateCategoryGroup(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string; name?: string; is_archived?: boolean; sort_order?: number }) =>
      apiClient.patch<CategoryGroup>(`/category-groups/${id}`, data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['categoryGroups', budgetId] })
    },
  })
}

type CachedLists<T> = [readonly unknown[], T[] | undefined][]

/** Set the order of the budget's category groups in one request.
 *
 *  One request rather than a PATCH per group: a drag that half-applies leaves
 *  an order the user did not choose. The server refuses a list that does not
 *  name every visible group exactly once, so a stale client fails loudly
 *  instead of shuffling rows it never showed.
 *
 *  Optimistic over every cached variant of the list (`includeArchived` on and
 *  off): a drag that snaps back for a round trip reads as a failed drag. This
 *  used to write to `['categoryGroups', budgetId]` alone, a key nothing reads,
 *  so the grid never showed the new order until the refetch — and a refused
 *  reorder restored nothing. */
export function useReorderCategoryGroups(budgetId: string) {
  const qc = useQueryClient()
  const key = ['categoryGroups', budgetId]
  return useMutation({
    mutationFn: (groupIds: string[]) =>
      apiClient.post(`/${budgetId}/category-groups/reorder`, { group_ids: groupIds }),
    onMutate: async (groupIds) => {
      await qc.cancelQueries({ queryKey: key })
      const previous: CachedLists<CategoryGroup> = qc.getQueriesData<CategoryGroup[]>({ queryKey: key })
      qc.setQueriesData<CategoryGroup[]>({ queryKey: key }, (cached) =>
        cached ? reorderMembers(cached, () => true, groupIds) : cached
      )
      return { previous }
    },
    onError: (err, _ids, ctx) => {
      ctx?.previous.forEach(([k, data]) => qc.setQueryData(k, data))
      toast.error(apiErrorMessage(err, 'Could not save the new order'))
    },
    // Order moves no money, so the month's balances are left alone.
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  })
}

/** Set the order of one group's categories in one request — the same contract
 *  as the group reorder, scoped to a group. Optimistic over every cached
 *  variant of the category list; the other groups' rows are not touched. */
export function useReorderCategories(budgetId: string) {
  const qc = useQueryClient()
  const key = ['categories', budgetId]
  return useMutation({
    mutationFn: ({ groupId, categoryIds }: { groupId: string; categoryIds: string[] }) =>
      apiClient.post(`/${budgetId}/category-groups/${groupId}/categories/reorder`, {
        category_ids: categoryIds,
      }),
    onMutate: async ({ groupId, categoryIds }) => {
      await qc.cancelQueries({ queryKey: key })
      const previous: CachedLists<Category> = qc.getQueriesData<Category[]>({ queryKey: key })
      qc.setQueriesData<Category[]>({ queryKey: key }, (cached) =>
        cached ? reorderMembers(cached, (c) => c.category_group_id === groupId, categoryIds) : cached
      )
      return { previous }
    },
    onError: (err, _vars, ctx) => {
      ctx?.previous.forEach(([k, data]) => qc.setQueryData(k, data))
      toast.error(apiErrorMessage(err, 'Could not save the new order'))
    },
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
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
  /** Net posted spending filed here over the categories' whole life
   *  (positive = outflow) — what the destination absorbs, or what leaves
   *  category-keyed reports until re-filed. */
  moving_activity: string
  /** What Ready to Assign gains, one figure per mode — SERVED, the dialog
   *  never derives money. They differ when future-dated activity moves. */
  released_if_moved: string
  released_if_uncategorized: string
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

/** One archived envelope, as the archived listing serves it. `available` is
 *  normally zero — the archive flow refuses otherwise — but rows archived
 *  before that flow existed can carry a balance, and this listing is the only
 *  place the budget still shows it. */
export interface ArchivedCategory {
  id: string
  name: string
  group_name: string
  transaction_count: number
  archived_at: string | null
  available: string
}

export function useArchivedCategories(budgetId: string | null, month: string, enabled = true) {
  return useQuery({
    queryKey: ['archivedCategories', budgetId, month],
    queryFn: async () => {
      const { data } = await apiClient.get<ArchivedCategory[]>(
        `/${budgetId}/categories/archived`,
        { params: { month } }
      )
      return data
    },
    enabled: !!budgetId && enabled,
    // Quantifies money, like the delete preview: an answer from before the
    // user's last edit is the wrong thing to show beside a Delete button.
    staleTime: 0,
  })
}

export interface ArchivePreview {
  category_ids: string[]
  category_names: string[]
  transaction_count: number
  available: string
  future_assigned: string
  blocked_by_balance: string[]
  blocked_by_link: string[]
  may_archive: boolean
}

export function useArchivePreview(budgetId: string, categoryIds: string[], month: string) {
  return useQuery({
    queryKey: ['categoryArchivePreview', budgetId, categoryIds.join(','), month],
    queryFn: async () => {
      const { data } = await apiClient.post<ArchivePreview>(
        `/${budgetId}/categories/archive-preview`,
        { category_ids: categoryIds, month }
      )
      return data
    },
    enabled: categoryIds.length > 0,
    staleTime: 0,
    gcTime: 0,
  })
}

function useArchiveMutation(budgetId: string, path: 'archive' | 'unarchive', done: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ ids, month }: { ids: string[]; month: string }) => {
      const { data } = await apiClient.post<ArchivePreview>(
        `/${budgetId}/categories/${path}`,
        { category_ids: ids, month }
      )
      return data
    },
    onSuccess: async () => {
      await invalidateAfterCategoryChange(qc, budgetId)
      toast.success(done)
    },
    // The server's sentence names which envelope still holds money and what to
    // do about it. A generic fallback here would throw that away, which is the
    // mistake AddAccountModal made with the 409.
    onError: (e) => toast.error(apiErrorMessage(e, 'Could not update the archive')),
  })
}

export function useArchiveCategories(budgetId: string) {
  return useArchiveMutation(budgetId, 'archive', 'Archived')
}

export function useUnarchiveCategories(budgetId: string) {
  return useArchiveMutation(budgetId, 'unarchive', 'Restored to the budget')
}

/** What the delete dialog is about to act on: a selection of categories, or a
 *  whole group (which cascades over the categories inside it). */
export type DeleteTarget =
  | { kind: 'categories'; ids: string[]; name: string }
  | { kind: 'group'; id: string; name: string }

/** The one definition of the delete-preview fetch — the modal's query and the
 *  flow hook's skip-the-dialog prefetch both use it, so they cannot disagree
 *  about key, endpoint or freshness. */
export function deletePreviewOptions(budgetId: string, target: DeleteTarget, month: string) {
  const key = target.kind === 'group' ? target.id : target.ids.join(',')
  return {
    queryKey: ['categoryDeletePreview', budgetId, target.kind, key, month] as const,
    queryFn: async (): Promise<CategoryDeletePreview> => {
      if (target.kind === 'group') {
        const { data } = await apiClient.get<CategoryDeletePreview>(
          `/category-groups/${target.id}/delete-preview`,
          { params: { month } }
        )
        return data
      }
      const { data } = await apiClient.post<CategoryDeletePreview>(
        `/${budgetId}/categories/delete-preview`,
        { category_ids: target.ids, month }
      )
      return data
    },
    // Never served from cache: it quantifies money and drives a destructive
    // button, so an answer from before the user's last edit is exactly the
    // wrong thing to put in front of them.
    staleTime: 0,
    gcTime: 0,
  }
}

export function useCategoryDeletePreview(
  budgetId: string,
  target: DeleteTarget | null,
  month: string
) {
  const key = target?.kind === 'group' ? target.id : (target?.ids.join(',') ?? '')
  return useQuery({
    queryKey: ['categoryDeletePreview', budgetId, target?.kind ?? 'none', key, month],
    // Delegates to the shared definition — target is always set here because
    // the query is disabled without one.
    queryFn: (): Promise<CategoryDeletePreview> =>
      deletePreviewOptions(budgetId, target!, month).queryFn(),
    enabled: !!target,
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
