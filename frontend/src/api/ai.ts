import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'

export interface AIStatus {
  enabled: boolean
  available: boolean
  host: string | null
  model: string | null
  /** Raw ollama_vision_model setting (null when no override is set). */
  vision_model: string | null
  /** The model receipt scans will actually use — the vision override when
   * set, otherwise the main model. Resolved server-side so the UI never
   * re-implements the fallback chain. */
  receipt_model: string
  /** Whether that model supports vision, from the same /api/show probe the
   * worker gates receipt scans on. null = unknown (Ollama unreachable, or
   * too old to report capabilities) — never render that as "unsupported". */
  receipt_model_vision: boolean | null
}

/**
 * Ollama names models "name:tag" with ":latest" implied when untagged — an
 * env-seeded "gemma4" and the tile's "gemma4:latest" are the same model.
 * Without this the selected tile silently loses its highlight.
 */
export function sameOllamaModel(
  a: string | null | undefined,
  b: string | null | undefined
): boolean {
  if (!a || !b) return false
  const norm = (m: string) => (m.endsWith(':latest') ? m.slice(0, -':latest'.length) : m)
  return norm(a) === norm(b)
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

/** Force a fresh AI status check (bypasses cache). */
export function useTestAIConnection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.get<AIStatus>('/ai/status')
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ai-status'] })
    },
  })
}

export interface OllamaModel {
  name: string
  size: number
  capabilities: string[]
}

export function useOllamaModels() {
  return useQuery({
    queryKey: ['ollama-models'],
    queryFn: async () => {
      const { data } = await apiClient.get<{ models: OllamaModel[] }>('/ai/models')
      return data.models
    },
    staleTime: 60_000, // cache for 1 minute
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


export function useSuggestRegex(budgetId: string) {
  return useMutation({
    mutationFn: (names: string[]) =>
      apiClient
        .post<{ pattern: string | null }>(`/${budgetId}/ai/suggest-regex`, { names })
        .then((r) => r.data.pattern),
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
