import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { Category, CategoryGroup } from '../types'

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
