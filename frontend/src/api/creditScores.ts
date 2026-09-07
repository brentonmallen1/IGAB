import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { ROOT } from './queryKeys'

export interface CreditScore {
  id: string
  budget_id: string
  recorded_on: string
  score: number
  bureau: string | null
  source: string | null
  note: string | null
}

export interface CreditScoreIn {
  recorded_on: string
  score: number
  bureau?: string | null
  source?: string | null
  note?: string | null
}

const key = (budgetId: string | null) => [ROOT.creditScores, budgetId]

export function useCreditScores(budgetId: string | null) {
  return useQuery({
    queryKey: key(budgetId),
    queryFn: async () => {
      const { data } = await apiClient.get<CreditScore[]>(`/${budgetId}/credit-scores`)
      return data
    },
    enabled: !!budgetId,
  })
}

export function useCreateCreditScore(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: CreditScoreIn) =>
      apiClient.post<CreditScore>(`/${budgetId}/credit-scores`, body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(budgetId) }),
  })
}

export function useDeleteCreditScore(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/${budgetId}/credit-scores/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(budgetId) }),
  })
}
