import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  Check,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Clock,
  Copy,
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
import {
  useAIJobs,
  useAIJobCounts,
  useDeleteAIJob,
  useReprocessAIJob,
  type AIJob,
  type AIJobStatus,
} from '../../api/aiJobs'
import { fetchAttachmentBlob, useAttachmentUrl } from '../../api/attachments'
import { AttachmentLightbox } from '../../components/attachments/Lightbox'
import { useFormatters } from '../../hooks/useFormatters'
import './AIActivityPage.css'
import { confirmAsync } from '../../stores/confirmStore'
import { scanFailureReason } from '../../components/transactions/TransactionEditor/scanFailure'

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

function CopyButton({ text, title }: { text: string; title: string }) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      toast.error('Could not copy — clipboard unavailable')
    }
  }

  return (
    <button
      className={`ai-activity__copy ${copied ? 'ai-activity__copy--copied' : ''}`}
      onClick={handleCopy}
      title={title}
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  )
}

function JobThumbnail({ attachmentId, onOpen }: { attachmentId: string; onOpen: () => void }) {
  const { data: url } = useAttachmentUrl(attachmentId, true)
  if (!url) return <div className="ai-activity__thumb ai-activity__thumb--empty" />
  return (
    <button
      type="button"
      className="ai-activity__thumb-btn"
      onClick={onOpen}
      title="View receipt image"
      aria-label="View receipt image"
    >
      <img className="ai-activity__thumb" src={url} alt="Receipt thumbnail" loading="lazy" />
    </button>
  )
}

function JobRow({ job, budgetId }: { job: AIJob; budgetId: string }) {
  const navigate = useNavigate()
  const { formatMoney } = useFormatters()
  const reprocess = useReprocessAIJob(budgetId)
  const remove = useDeleteAIJob(budgetId)
  const [errorOpen, setErrorOpen] = useState(false)
  const [responseOpen, setResponseOpen] = useState(false)
  const [promptOpen, setPromptOpen] = useState(false)
  const [viewerOpen, setViewerOpen] = useState(false)

  // The job log stores only the attachment id + original upload metadata; the
  // stored file is the transaction attachment (WebP for images, PDF verbatim).
  const isPdf = job.payload.content_type === 'application/pdf'
  const viewerAttachment = job.attachment_id
    ? {
        id: job.attachment_id,
        original_filename: job.payload.original_filename ?? 'receipt',
        content_type: isPdf ? 'application/pdf' : 'image/webp',
      }
    : null

  function openImage() {
    if (!viewerAttachment) return
    if (isPdf) {
      // PDFs use the browser's native viewer, same as the attachment panel
      void fetchAttachmentBlob(viewerAttachment.id)
        .then((url) => window.open(url, '_blank'))
        .catch(() => toast.error('Could not load the receipt file'))
    } else {
      setViewerOpen(true)
    }
  }

  const draft = job.result?.draft
  const reason = job.result?.extraction?.reason
  const title =
    draft?.payee ??
    job.payload.text ??
    job.payload.original_filename ??
    (job.kind === 'receipt' ? 'Receipt' : 'Text entry')
  const amount = draft ? parseFloat(draft.amount) : null

  async function handleReprocess() {
    try {
      await reprocess.mutateAsync(job.id)
      toast.success('Reprocessing with current model — check back shortly')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      toast.error(detail ?? 'Reprocess failed')
    }
  }

  async function handleDelete() {
    const ok = await confirmAsync({
      title: 'Remove this entry from the AI activity log?',
      message: 'The transaction (if any) is kept.',
      confirmLabel: 'Remove',
      destructive: true,
    })
    if (!ok) return
    await remove.mutateAsync(job.id)
  }

  return (
    <div className={`ai-activity__row ai-activity__row--${job.status}`}>
      {job.attachment_id ? (
        <JobThumbnail attachmentId={job.attachment_id} onOpen={openImage} />
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
          {job.model && <span className="ai-activity__model">{job.model}</span>}
          <span className="ai-activity__time">
            {new Date(job.created_at).toLocaleString()}
          </span>
          {job.attempts > 1 && (
            <span className="ai-activity__attempts">
              attempt {job.attempts}/{job.max_attempts}
            </span>
          )}
          {job.transaction_removed && (
            <span
              className="ai-activity__chip ai-activity__chip--removed"
              title="The transaction this job created has since been deleted — the log entry is kept for the record"
            >
              <Trash2 size={11} />
              Transaction removed
            </span>
          )}
        </div>
        {typeof reason === 'string' && reason && (
          <div className="ai-activity__reason" title="The model's stated reason for its category choice">
            {reason}
          </div>
        )}
        {job.error && (
          <div className="ai-activity__error">
            <button
              className="ai-activity__error-toggle"
              onClick={() => setErrorOpen((v) => !v)}
            >
              {errorOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              Error details
            </button>
            {/* Through scanFailureReason so the user reads the reason, not the
                worker's exception class name ("NonRetryableJobError: …"). */}
            {errorOpen && (
              <pre className="ai-activity__error-text">{scanFailureReason(job.error)}</pre>
            )}
          </div>
        )}
        {job.result?.extraction && (
          <div className="ai-activity__response">
            <button
              className="ai-activity__response-toggle"
              onClick={() => setResponseOpen((v) => !v)}
            >
              {responseOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              LLM response
            </button>
            <CopyButton
              text={JSON.stringify(job.result.extraction, null, 2)}
              title="Copy LLM response as JSON"
            />
            {responseOpen && (
              <pre className="ai-activity__response-text">
                {JSON.stringify(job.result.extraction, null, 2)}
              </pre>
            )}
          </div>
        )}
        {job.result?.request?.prompt && (
          <div className="ai-activity__response">
            <button
              className="ai-activity__response-toggle"
              onClick={() => setPromptOpen((v) => !v)}
            >
              {promptOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              Prompt
            </button>
            <CopyButton text={job.result.request.prompt} title="Copy the exact prompt sent" />
            {promptOpen && (
              <pre className="ai-activity__response-text">
                {[
                  `model: ${job.result.request.model ?? '?'}  think: ${String(job.result.request.think)}  format: ${job.result.request.format ?? 'none'}`,
                  job.result.request.system ? `system: ${job.result.request.system}` : null,
                  '',
                  job.result.request.prompt,
                ]
                  .filter((l) => l !== null)
                  .join('\n')}
              </pre>
            )}
          </div>
        )}
      </div>

      <div className="ai-activity__actions">
        {job.transaction_id && !job.transaction_removed && (
          <button
            className="ai-activity__action"
            onClick={() => navigate(`/transactions?highlight=${job.transaction_id}`)}
            title="View transaction"
          >
            <ExternalLink size={14} />
            <span>View</span>
          </button>
        )}
        {(job.status === 'done' || job.status === 'error') && (
          <button
            className="ai-activity__action"
            onClick={handleReprocess}
            disabled={reprocess.isPending}
            title="Reprocess with current model"
          >
            <RotateCcw size={14} />
            <span>Reprocess</span>
          </button>
        )}
        {job.status !== 'processing' && job.status !== 'queued' && (
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

      {viewerOpen && viewerAttachment && (
        <AttachmentLightbox
          attachment={viewerAttachment}
          onClose={() => setViewerOpen(false)}
        />
      )}
    </div>
  )
}

export function AIActivityPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const [statusFilter, setStatusFilter] = useState<AIJobStatus | ''>('')
  const [offset, setOffset] = useState(0)

  const { data: counts } = useAIJobCounts(budgetId)
  const activeCount = counts?.active ?? 0
  const { data, isLoading } = useAIJobs(
    budgetId,
    { status: statusFilter || undefined, limit: PAGE_SIZE, offset },
    activeCount > 0
  )

  const jobs = useMemo(() => data?.jobs ?? [], [data])
  const total = data?.total_count ?? 0


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
