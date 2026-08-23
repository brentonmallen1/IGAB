import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { apiClient, apiErrorMessage } from './client'
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

export function useDeleteCategoryGroup(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/category-groups/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['categoryGroups', budgetId] })
    },
  })
}

export function useDeleteCategory(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/categories/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['categories', budgetId] })
    },
  })
}
