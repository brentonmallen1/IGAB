import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { ROOT } from './queryKeys'

/** The last four digits of a card that pays from an account
 *  (`AccountCardEnding`). An account can hold several; an ending names one
 *  account per budget. */
export interface CardEnding {
  id: string
  account_id: string
  last4: string
  label: string | null
}

export interface CardEndingIn {
  account_id: string
  last4: string
  label?: string | null
}

const key = (budgetId: string | null) => [ROOT.cardEndings, budgetId]

/** What a card-ending write stales: the list, and every AI job — each one
 *  serves `card_ending_account_id`, which follows the table. Undo calls this
 *  too, so the two cannot drift. */
export function invalidateAfterCardEndingChange(qc: QueryClient, budgetId: string) {
  qc.invalidateQueries({ queryKey: key(budgetId) })
  qc.invalidateQueries({ queryKey: [ROOT.aiJobs] })
  qc.invalidateQueries({ queryKey: [ROOT.aiJobForTxn] })
}

export function useCardEndings(budgetId: string | null) {
  return useQuery({
    queryKey: key(budgetId),
    queryFn: async () => {
      const { data } = await apiClient.get<CardEnding[]>(`/${budgetId}/card-endings`)
      return data
    },
    enabled: !!budgetId,
  })
}

export function useCreateCardEnding(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: CardEndingIn) =>
      apiClient.post<CardEnding>(`/${budgetId}/card-endings`, body).then((r) => r.data),
    onSuccess: () => invalidateAfterCardEndingChange(qc, budgetId),
  })
}

export function useUpdateCardEnding(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...patch }: Partial<CardEndingIn> & { id: string }) =>
      apiClient.patch<CardEnding>(`/${budgetId}/card-endings/${id}`, patch).then((r) => r.data),
    onSuccess: () => invalidateAfterCardEndingChange(qc, budgetId),
  })
}

export function useDeleteCardEnding(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/${budgetId}/card-endings/${id}`),
    onSuccess: () => invalidateAfterCardEndingChange(qc, budgetId),
  })
}
