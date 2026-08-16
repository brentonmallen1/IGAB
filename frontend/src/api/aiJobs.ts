import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { useAIStatus } from './ai'

export type AIJobStatus = 'queued' | 'processing' | 'done' | 'error'
export type AIJobKind = 'receipt' | 'nl_parse'

export interface AIJobDraft {
  payee: string | null
  amount: string
  date: string
  category: string | null
  memo: string | null
  confidence: number
}

export interface AIJobSplitLine {
  category: string
  amount: string
}

export interface AIJobRequest {
  prompt: string
  system?: string
  model?: string
  think?: boolean | null
  format?: string | null
}

export interface AIJobResult {
  extraction?: Record<string, unknown>
  draft?: AIJobDraft
  suggested_split?: AIJobSplitLine[] | null
  request?: AIJobRequest
}

export interface AIJob {
  id: string
  budget_id: string
  kind: AIJobKind
  status: AIJobStatus
  payload: {
    account_id?: string
    original_filename?: string
    content_type?: string
    text?: string
    client_today?: string
  }
  result: AIJobResult | null
  error: string | null
  model: string | null
  attempts: number
  max_attempts: number
  transaction_id: string | null
  attachment_id: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface AIJobListResponse {
  jobs: AIJob[]
  total_count: number
}

export interface NLDraft {
  payee: string | null
  amount: string
  date: string
  category_id: string | null
  category_name: string | null
  memo: string | null
  confidence: number
}

function localToday(): string {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function useAIJobs(
  budgetId: string | null,
  opts: { status?: AIJobStatus; kind?: AIJobKind; limit?: number; offset?: number } = {},
  hasActiveJobs = false
) {
  return useQuery({
    queryKey: ['ai-jobs', budgetId, opts],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (opts.status) params.set('status_filter', opts.status)
      if (opts.kind) params.set('kind', opts.kind)
      if (opts.limit) params.set('limit', String(opts.limit))
      if (opts.offset) params.set('offset', String(opts.offset))
      const { data } = await apiClient.get<AIJobListResponse>(
        `/${budgetId}/ai/jobs?${params.toString()}`
      )
      return data
    },
    enabled: !!budgetId,
    // Live-refresh the log while work is in flight
    refetchInterval: hasActiveJobs ? 4_000 : false,
  })
}

/** The AI job that created a given transaction — powers the review modal
 * when an AI transaction is opened from the register. */
export function useAIJobForTransaction(budgetId: string | null, transactionId: string | null) {
  return useQuery({
    queryKey: ['ai-job-for-txn', budgetId, transactionId],
    queryFn: async () => {
      const { data } = await apiClient.get<AIJobListResponse>(`/${budgetId}/ai/jobs`, {
        params: { transaction_id: transactionId, limit: 1 },
      })
      return data.jobs[0] ?? null
    },
    enabled: !!budgetId && !!transactionId,
    staleTime: 30_000,
  })
}

export function useActiveAIJobCount(budgetId: string | null) {
  const aiStatus = useAIStatus()
  return useQuery({
    queryKey: ['ai-jobs-active', budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<{ count: number }>(
        `/${budgetId}/ai/jobs/active-count`
      )
      return data.count
    },
    enabled: !!budgetId && aiStatus.data?.available === true,
    refetchInterval: (query) => ((query.state.data ?? 0) > 0 ? 4_000 : 30_000),
    refetchIntervalInBackground: false,
  })
}

export function useSubmitReceipt(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ file, accountId }: { file: File; accountId: string }) => {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('account_id', accountId)
      formData.append('client_today', localToday())
      const { data } = await apiClient.post<AIJob>(`/${budgetId}/ai/receipts`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ai-jobs'] })
      qc.invalidateQueries({ queryKey: ['ai-jobs-active'] })
    },
  })
}

export function useRetryAIJob(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) =>
      apiClient.post<AIJob>(`/${budgetId}/ai/jobs/${jobId}/retry`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ai-jobs'] })
      qc.invalidateQueries({ queryKey: ['ai-jobs-active'] })
    },
  })
}

export function useReprocessAIJob(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) =>
      apiClient.post<AIJob>(`/${budgetId}/ai/jobs/${jobId}/reprocess`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ai-jobs'] })
      qc.invalidateQueries({ queryKey: ['ai-jobs-active'] })
    },
  })
}

export function useDeleteAIJob(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) => apiClient.delete(`/${budgetId}/ai/jobs/${jobId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ai-jobs'] })
      qc.invalidateQueries({ queryKey: ['ai-jobs-active'] })
    },
  })
}

export function useParseNLTransaction(budgetId: string) {
  return useMutation({
    mutationFn: (text: string) =>
      apiClient
        .post<{ job_id: string; draft: NLDraft }>(`/${budgetId}/ai/parse-transaction`, {
          text,
          client_today: localToday(),
        })
        .then((r) => r.data),
  })
}

/** Poll a single job while it's in flight — powers the in-modal receipt watch. */
export function useAIJob(budgetId: string | null, jobId: string | null) {
  return useQuery({
    queryKey: ['ai-job', budgetId, jobId],
    queryFn: async () => {
      const { data } = await apiClient.get<AIJob>(`/${budgetId}/ai/jobs/${jobId}`)
      return data
    },
    enabled: !!budgetId && !!jobId,
    refetchInterval: (query) => {
      const s = query.state.data?.status
      return s === 'done' || s === 'error' ? false : 2_000
    },
  })
}
