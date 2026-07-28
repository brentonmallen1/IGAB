import { useMutation, useQuery } from '@tanstack/react-query'
import { apiClient } from './client'

export interface AIStatus {
  available: boolean
  host: string | null
}

export function useAIStatus() {
  return useQuery({
    queryKey: ['ai-status'],
    queryFn: async () => {
      const { data } = await apiClient.get<AIStatus>('/ai/status')
      return data
    },
    staleTime: 300_000, // cache for 5 minutes
    retry: false,
  })
}

export interface SuggestCategoryResult {
  category_id: string | null
  category_name: string | null
  confidence: number
}

export function useSuggestCategory(budgetId: string) {
  return useMutation({
    mutationFn: (body: { payee_name: string; amount: number; memo?: string }) =>
      apiClient
        .post<SuggestCategoryResult>(`/${budgetId}/ai/suggest-category`, body)
        .then((r) => r.data),
  })
}

export function useNormalizePayee(budgetId: string) {
  return useMutation({
    mutationFn: (payee_name: string) =>
      apiClient
        .post<{ normalized_name: string }>(`/${budgetId}/ai/normalize-payee`, { payee_name })
        .then((r) => r.data.normalized_name),
  })
}

export interface PayeeCleanupEntry {
  id: string
  name: string
}

export interface PayeeCleanupGroup {
  canonical: string
  payees: PayeeCleanupEntry[]
}

export function usePayeeCleanupSuggestions(budgetId: string | null) {
  return useQuery({
    queryKey: ['ai-payee-cleanup', budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<PayeeCleanupGroup[]>(`/${budgetId}/ai/payee-cleanup`)
      return data
    },
    enabled: false, // manual trigger only
    staleTime: 0,
  })
}

export function useSpendingInsights(budgetId: string | null, month?: string) {
  return useQuery({
    queryKey: ['ai-insights', budgetId, month],
    queryFn: async () => {
      const { data } = await apiClient.get<{ insights: string }>(
        `/${budgetId}/ai/insights`,
        { params: month ? { month } : undefined },
      )
      return data.insights
    },
    enabled: !!budgetId,
    staleTime: 300_000,
  })
}
