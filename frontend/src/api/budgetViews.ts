import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { BudgetView } from '../types'
import { ROOT } from './queryKeys'

const key = (budgetId: string | null) => [ROOT.budgetViews, budgetId]

/** Editing a view changes how reports roll up, so their cache is stale the
 *  moment a mutation lands — without this, pareto/treemap keep showing the
 *  old arrangement for up to a minute after a save. */
function invalidate(qc: ReturnType<typeof useQueryClient>, budgetId: string) {
  qc.invalidateQueries({ queryKey: key(budgetId) })
  // Only spending-grouped takes view_id. ['reports'] dumped all ~21 report
  // caches on any view mutation — including a rename, which changes no report
  // data — and a new-view save fires POST then PATCH, so it ran twice.
  qc.invalidateQueries({ queryKey: [ROOT.reports, 'spending-grouped'] })
}

export function useBudgetViews(budgetId: string | null) {
  return useQuery({
    queryKey: key(budgetId),
    queryFn: async () => {
      const { data } = await apiClient.get<BudgetView[]>(`/${budgetId}/views`)
      return data
    },
    enabled: !!budgetId,
    staleTime: 60_000,
  })
}

export function useCreateBudgetView(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: {
      name: string
      groups?: string[]
      hide_unassigned?: boolean
      /** Sent with the same request so create is atomic — a failed follow-up
       *  PATCH used to leave a committed zero-group view behind. `group_name`
       *  resolves against `groups` above server-side. */
      placements?: {
        category_id: string
        group_id?: string | null
        group_name?: string | null
        sort_order?: number
        is_hidden?: boolean
      }[]
    }) => apiClient.post<BudgetView>(`/${budgetId}/views`, data).then((r) => r.data),
    onSuccess: () => invalidate(qc, budgetId),
  })
}

export function useUpdateBudgetView(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      ...data
    }: {
      id: string
      name?: string
      hide_unassigned?: boolean
      groups?: string[]
      /** `group_name` resolves against the groups saved in the same request,
       *  so new groups and their contents go up together. */
      placements?: {
        category_id: string
        group_id?: string | null
        group_name?: string | null
        sort_order?: number
        is_hidden?: boolean
      }[]
    }) => apiClient.patch<BudgetView>(`/views/${id}`, data).then((r) => r.data),
    onSuccess: () => invalidate(qc, budgetId),
  })
}

export function useDeleteBudgetView(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/views/${id}`),
    onSuccess: () => invalidate(qc, budgetId),
  })
}
