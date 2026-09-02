import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { downscaleForUpload } from '../utils/imageUpload'
import { useAIStatus } from './ai'
import { ROOT } from './queryKeys'

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
  /** Exactly what the model returned, pre-parse — present on success AND on
   * failure, so a structured-output problem is distinguishable from
   * everything else. */
  raw_response?: string | null
  /** Thinking transcript, when the model produced one. */
  thinking?: string
  done_reason?: string
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
  /** The linked transaction was deleted after this job ran */
  transaction_removed?: boolean
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
  opts: { status?: AIJobStatus; kind?: AIJobKind; limit?: number; offset?: number } = {}
) {
  return useQuery({
    queryKey: [ROOT.aiJobs, budgetId, opts],
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
    // Poll while THIS list shows in-flight work. Deriving from the list's own
    // data (not the separate counts query, as before) matters: the counts
    // query flips active→0 the instant a job finishes, and react-query
    // CANCELS a pending tick when the interval turns off — the list froze on
    // the pre-completion snapshot forever. Self-derived, the interval turns
    // off only after the fetch that rendered the terminal state.
    refetchInterval: (query) =>
      query.state.data?.jobs.some((j) => j.status === 'queued' || j.status === 'processing')
        ? 4_000
        : false,
    // Catch up when the PWA is foregrounded — "walk away, come back" is the
    // designed receipt flow (the app-wide default is false).
    refetchOnWindowFocus: true,
  })
}

/** The AI job that created a given transaction — powers the review modal
 * when an AI transaction is opened from the register. */
export function useAIJobForTransaction(budgetId: string | null, transactionId: string | null) {
  return useQuery({
    queryKey: [ROOT.aiJobForTxn, budgetId, transactionId],
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

export interface AIJobCounts {
  /** Jobs queued or processing right now. */
  active: number
  /** AI-created transactions still waiting to be reviewed. */
  needsReview: number
}

/**
 * The header badge's two numbers. `active` alone drops to zero at exactly the
 * moment the work finishes — i.e. when there is finally something for the user
 * to look at — so the badge has to know about both.
 */
export function useAIJobCounts(budgetId: string | null) {
  const aiStatus = useAIStatus()
  return useQuery({
    queryKey: [ROOT.aiJobsActive, budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<{ count: number; needs_review?: number }>(
        `/${budgetId}/ai/jobs/active-count`
      )
      return { active: data.count, needsReview: data.needs_review ?? 0 } satisfies AIJobCounts
    },
    // Gated on `enabled`, not `available`: how many transactions are waiting
    // for review is a fact about the user's own data. Hiding it because Ollama
    // happens not to answer a ping right now would drop the notification
    // precisely when nothing new can arrive to replace it.
    enabled: !!budgetId && aiStatus.data?.enabled === true,
    refetchInterval: (query) => ((query.state.data?.active ?? 0) > 0 ? 4_000 : 30_000),
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  })
}

export function useSubmitReceipt(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ file, accountId }: { file: File; accountId: string }) => {
      const formData = new FormData()
      // API-layer downscale: covers ReceiptScanTab too, which used to send
      // the raw camera file. Re-running on an already-downscaled file is a
      // no-op (size gate in shouldDownscale).
      formData.append('file', await downscaleForUpload(file))
      formData.append('account_id', accountId)
      formData.append('client_today', localToday())
      const { data } = await apiClient.post<AIJob>(`/${budgetId}/ai/receipts`, formData)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.aiJobs] })
      qc.invalidateQueries({ queryKey: [ROOT.aiJobsActive] })
    },
  })
}

export function useRetryAIJob(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) =>
      apiClient.post<AIJob>(`/${budgetId}/ai/jobs/${jobId}/retry`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.aiJobs] })
      qc.invalidateQueries({ queryKey: [ROOT.aiJobsActive] })
    },
  })
}

export function useReprocessAIJob(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) =>
      apiClient.post<AIJob>(`/${budgetId}/ai/jobs/${jobId}/reprocess`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.aiJobs] })
      qc.invalidateQueries({ queryKey: [ROOT.aiJobsActive] })
    },
  })
}

export function useDeleteAIJob(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) => apiClient.delete(`/${budgetId}/ai/jobs/${jobId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.aiJobs] })
      qc.invalidateQueries({ queryKey: [ROOT.aiJobsActive] })
    },
  })
}

export function useParseNLTransaction(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (text: string) =>
      apiClient
        .post<{ job_id: string; draft: NLDraft }>(`/${budgetId}/ai/parse-transaction`, {
          text,
          client_today: localToday(),
        })
        .then((r) => r.data),
    // The endpoint writes an ai_jobs audit row whether the parse succeeds or
    // fails — the AI Activity log should show it either way.
    onSettled: () => {
      qc.invalidateQueries({ queryKey: [ROOT.aiJobs] })
      qc.invalidateQueries({ queryKey: [ROOT.aiJobsActive] })
    },
  })
}

/** Poll a single job while it's in flight — powers the in-modal receipt watch. */
export function useAIJob(budgetId: string | null, jobId: string | null) {
  return useQuery({
    queryKey: [ROOT.aiJob, budgetId, jobId],
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
