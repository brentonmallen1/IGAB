import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { CategoryTarget } from '../types'

export interface TargetUpsert {
  target_type: string
  target_amount: number
  target_date?: string | null
  repeat_frequency?: string | null
}

export function useTarget(categoryId: string | null) {
  return useQuery({
    queryKey: ['target', categoryId],
    queryFn: async () => {
      const { data } = await apiClient.get<CategoryTarget | null>(
        `/categories/${categoryId}/target`,
      )
      return data
    },
    enabled: !!categoryId,
    staleTime: 60_000,
  })
}

export function useUpsertTarget(categoryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TargetUpsert) =>
      apiClient.post<CategoryTarget>(`/categories/${categoryId}/target`, body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['target', categoryId] })
    },
  })
}

export function useDeleteTarget(categoryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiClient.delete(`/categories/${categoryId}/target`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['target', categoryId] })
    },
  })
}
