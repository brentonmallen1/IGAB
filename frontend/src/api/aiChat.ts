import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { ROOT } from './queryKeys'

export interface Conversation {
  id: string
  title: string | null
  created_at: string
  updated_at: string
  message_count: number
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'tool'
  content: string
  thinking: string | null
  /** One entry per tool the model called, with raw and resolved arguments. */
  tool_calls: ToolTraceEntry[] | null
  /** The grounding verdict, as it stood when the answer was written. */
  grounding: {
    figures: number
    grounded: number
    derived: number
    unsupported: string[]
    lookups: number
  } | null
  created_at: string
  ai_call_id: string | null
}

export interface ToolTraceEntry {
  name: string
  arguments: Record<string, unknown>
  resolved_arguments: Record<string, unknown> | null
  delegates_to: string | null
  row_count: number | null
  truncated: boolean
  duration_ms: number | null
  error: string | null
}

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[]
}

export function useConversations(budgetId: string | null) {
  return useQuery({
    queryKey: [ROOT.aiConversations, budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<Conversation[]>(`/${budgetId}/ai/conversations`)
      return data
    },
    enabled: !!budgetId,
  })
}

export function useConversation(budgetId: string | null, conversationId: string | null) {
  return useQuery({
    queryKey: [ROOT.aiConversation, budgetId, conversationId],
    queryFn: async () => {
      const { data } = await apiClient.get<ConversationDetail>(
        `/${budgetId}/ai/conversations/${conversationId}`
      )
      return data
    },
    enabled: !!budgetId && !!conversationId,
  })
}

export function useDeleteConversation(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (conversationId: string) =>
      apiClient.delete(`/${budgetId}/ai/conversations/${conversationId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.aiConversations] })
    },
  })
}

export interface AICall {
  id: string
  feature: string
  feature_label: string
  model: string
  endpoint: string
  status: 'ok' | 'error' | 'cancelled'
  error: string | null
  round: number
  duration_ms: number | null
  prompt_tokens: number | null
  completion_tokens: number | null
  tool_call_count: number
  created_at: string
}

export interface AICallDetail extends AICall {
  system: string | null
  messages: { role: string; content: string }[]
  response: string | null
  thinking: string | null
  tools: unknown[]
  tool_trace: ToolTraceEntry[]
  /** The prompt aged out of retention — not "never recorded". */
  payload_pruned: boolean
}

export function useAICalls(budgetId: string | null, opts: { limit?: number } = {}) {
  return useQuery({
    queryKey: [ROOT.aiCalls, budgetId, opts],
    queryFn: async () => {
      const { data } = await apiClient.get<{ calls: AICall[]; total_count: number }>(
        `/${budgetId}/ai/calls`,
        { params: { limit: opts.limit ?? 50 } }
      )
      return data
    },
    enabled: !!budgetId,
  })
}

export function useAICall(budgetId: string | null, callId: string | null) {
  return useQuery({
    queryKey: [ROOT.aiCall, budgetId, callId],
    queryFn: async () => {
      const { data } = await apiClient.get<AICallDetail>(`/${budgetId}/ai/calls/${callId}`)
      return data
    },
    enabled: !!budgetId && !!callId,
  })
}

/** Drop every stored prompt and response, keeping the list of calls. */
export function usePurgeCallPayloads(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.delete<{ removed: number }>(`/${budgetId}/ai/calls/payloads`)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.aiCalls] })
      qc.invalidateQueries({ queryKey: [ROOT.aiCall] })
    },
  })
}
