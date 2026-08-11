import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Clock,
  ExternalLink,
  Loader2,
  MessageSquareText,
  ReceiptText,
  RotateCcw,
  Sparkles,
  Trash2,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { useAppStore } from '../../stores/appStore'
import { useAIStatus } from '../../api/ai'
import {
  useAIJobs,
  useActiveAIJobCount,
  useDeleteAIJob,
  useRetryAIJob,
  type AIJob,
  type AIJobStatus,
} from '../../api/aiJobs'
import { useAttachmentUrl } from '../../api/attachments'
import { useFormatters } from '../../hooks/useFormatters'
import './AIActivityPage.css'

const PAGE_SIZE = 50

const STATUS_LABEL: Record<AIJobStatus, string> = {
  queued: 'Queued',
  processing: 'Processing',
  done: 'Done',
  error: 'Failed',
}

function StatusChip({ status }: { status: AIJobStatus }) {
  return (
    <span className={`ai-activity__chip ai-activity__chip--${status}`}>
      {status === 'processing' && <Loader2 size={11} className="ai-activity__spin" />}
      {status === 'queued' && <Clock size={11} />}
      {status === 'done' && <CheckCircle size={11} />}
      {status === 'error' && <AlertTriangle size={11} />}
      {STATUS_LABEL[status]}
    </span>
  )
}

function JobThumbnail({ attachmentId }: { attachmentId: string }) {
  const { data: url } = useAttachmentUrl(attachmentId, true)
  if (!url) return <div className="ai-activity__thumb ai-activity__thumb--empty" />
  return <img className="ai-activity__thumb" src={url} alt="Receipt thumbnail" loading="lazy" />
}

function JobRow({ job, budgetId }: { job: AIJob; budgetId: string }) {
  const navigate = useNavigate()
  const { formatMoney } = useFormatters()
  const retry = useRetryAIJob(budgetId)
  const remove = useDeleteAIJob(budgetId)
  const [errorOpen, setErrorOpen] = useState(false)

  const draft = job.result?.draft
  const title =
    draft?.payee ??
    job.payload.text ??
    job.payload.original_filename ??
    (job.kind === 'receipt' ? 'Receipt' : 'Text entry')
  const amount = draft ? parseFloat(draft.amount) : null

  async function handleRetry() {
    try {
      await retry.mutateAsync(job.id)
      toast.success('Retrying — check back shortly')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      toast.error(detail ?? 'Retry failed')
    }
  }

  async function handleDelete() {
    if (!confirm('Remove this entry from the AI activity log? The transaction (if any) is kept.'))
      return
    await remove.mutateAsync(job.id)
  }

  return (
    <div className={`ai-activity__row ai-activity__row--${job.status}`}>
      {job.attachment_id ? (
        <JobThumbnail attachmentId={job.attachment_id} />
      ) : (
        <div className="ai-activity__thumb ai-activity__thumb--icon">
          {job.kind === 'receipt' ? <ReceiptText size={18} /> : <MessageSquareText size={18} />}
        </div>
      )}

      <div className="ai-activity__main">
        <div className="ai-activity__title-line">
          <span className="ai-activity__title">{title}</span>
          {amount != null && !Number.isNaN(amount) && (
            <span className={`ai-activity__amount ${amount < 0 ? 'txn-outflow' : 'txn-inflow'}`}>
              {formatMoney(amount)}
            </span>
          )}
        </div>
        <div className="ai-activity__meta">
          <StatusChip status={job.status} />
          <span className="ai-activity__kind">
            {job.kind === 'receipt' ? 'Receipt scan' : 'Text entry'}
          </span>
          <span className="ai-activity__time">
            {new Date(job.created_at).toLocaleString()}
          </span>
          {job.attempts > 1 && (
            <span className="ai-activity__attempts">
              attempt {job.attempts}/{job.max_attempts}
            </span>
          )}
        </div>
        {job.error && (
          <div className="ai-activity__error">
            <button
              className="ai-activity__error-toggle"
              onClick={() => setErrorOpen((v) => !v)}
            >
              {errorOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              Error details
            </button>
            {errorOpen && <pre className="ai-activity__error-text">{job.error}</pre>}
          </div>
        )}
      </div>

      <div className="ai-activity__actions">
        {job.transaction_id && (
          <button
            className="ai-activity__action"
            onClick={() => navigate(`/transactions?highlight=${job.transaction_id}`)}
            title="View transaction"
          >
            <ExternalLink size={14} />
            <span>View</span>
          </button>
        )}
        {job.status === 'error' && (
          <button
            className="ai-activity__action"
            onClick={handleRetry}
            disabled={retry.isPending}
            title="Retry extraction"
          >
            <RotateCcw size={14} />
            <span>Retry</span>
          </button>
        )}
        {job.status !== 'processing' && (
          <button
            className="ai-activity__action ai-activity__action--danger"
            onClick={handleDelete}
            disabled={remove.isPending}
            title="Remove from log"
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>
    </div>
  )
}

export function AIActivityPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const aiStatus = useAIStatus()
  const [statusFilter, setStatusFilter] = useState<AIJobStatus | ''>('')
  const [offset, setOffset] = useState(0)

  const { data: activeCount = 0 } = useActiveAIJobCount(budgetId)
  const { data, isLoading } = useAIJobs(
    budgetId,
    { status: statusFilter || undefined, limit: PAGE_SIZE, offset },
    activeCount > 0
  )

  const jobs = useMemo(() => data?.jobs ?? [], [data])
  const total = data?.total_count ?? 0

  if (aiStatus.data && !aiStatus.data.available) {
    return (
      <div className="ai-activity ai-activity--unavailable">
        <Sparkles size={24} />
        <h2>AI is not set up</h2>
        <p>
          Connect a local Ollama server in Settings → AI to scan receipts and use
          natural-language entry. Activity will appear here.
        </p>
      </div>
    )
  }

  return (
    <div className="ai-activity">
      <div className="ai-activity__header">
        <h1 className="ai-activity__page-title">
          <Sparkles size={18} />
          AI Activity
        </h1>
        <select
          className="ai-activity__filter"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value as AIJobStatus | '')
            setOffset(0)
          }}
          aria-label="Filter by status"
        >
          <option value="">All statuses</option>
          <option value="queued">Queued</option>
          <option value="processing">Processing</option>
          <option value="done">Done</option>
          <option value="error">Failed</option>
        </select>
      </div>

      <p className="ai-activity__desc">
        Every receipt scan and AI text entry is logged here — the permanent record of what
        the AI created, so nothing lands in your budget unseen.
      </p>

      {isLoading ? (
        <div className="ai-activity__empty">Loading…</div>
      ) : jobs.length === 0 ? (
        <div className="ai-activity__empty">
          {statusFilter ? 'No jobs with this status.' : 'No AI activity yet. Scan a receipt from the mobile quick-add to get started.'}
        </div>
      ) : (
        <div className="ai-activity__list">
          {jobs.map((job) => (
            <JobRow key={job.id} job={job} budgetId={budgetId!} />
          ))}
        </div>
      )}

      {total > PAGE_SIZE && (
        <div className="ai-activity__pager">
          <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
            Newer
          </button>
          <span>
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
          </span>
          <button
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Older
          </button>
        </div>
      )}
    </div>
  )
}
