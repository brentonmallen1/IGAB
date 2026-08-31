import { useState, useRef, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Upload, X, Loader2, Sparkles, AlertTriangle, FileText } from 'lucide-react'
import toast from 'react-hot-toast'
import { useQueryClient } from '@tanstack/react-query'
import {
  ATTACHMENT_ACCEPT,
  MAX_ATTACHMENT_LABEL,
  isAttachableFile,
  isTooLargeToAttach,
} from '../../../api/attachments'
import { useSubmitReceipt, useAIJob, type AIJob } from '../../../api/aiJobs'
import './ReceiptScanTab.css'
import { apiErrorMessage } from '../../../api/client'
import { invalidateAfterTransactionChange } from '../../../api/invalidateAfterTransactionChange'
import { ROOT } from '../../../api/queryKeys'

type Stage =
  | { kind: 'pick' }
  | { kind: 'preview'; file: File }
  | { kind: 'watching'; jobId: string }
  | { kind: 'failed'; message: string }

interface Props {
  budgetId: string
  /** Resolved account (fixed or picked in the editor); '' when unpicked. */
  accountId: string
  /** Ollama reachable? false renders the explanatory empty state. */
  aiAvailable: boolean
  /** Job finished with a transaction (done, or error→stub): open review. */
  onReviewReady: (job: AIJob) => void
  /** Persist sticky last-used account after a successful submit. */
  onRememberAccount: () => void
  /** Called before navigating away (Settings, AI Activity links). */
  onClose: () => void
}

export function ReceiptScanTab({
  budgetId,
  accountId,
  aiAvailable,
  onReviewReady,
  onRememberAccount,
  onClose,
}: Props) {
  const qc = useQueryClient()
  const submitReceipt = useSubmitReceipt(budgetId)
  const [stage, setStage] = useState<Stage>({ kind: 'pick' })
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const handled = useRef(false)

  // Poll the job while watching
  const { data: job } = useAIJob(budgetId, stage.kind === 'watching' ? stage.jobId : null)

  // Object URL for preview thumbnail
  const previewUrl = useMemo(
    () => (stage.kind === 'preview' ? URL.createObjectURL(stage.file) : null),
    [stage]
  )
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    }
  }, [previewUrl])

  // Clipboard paste handler — only active while this tab is mounted
  useEffect(() => {
    if (stage.kind === 'watching' || !aiAvailable) return
    function onPaste(e: ClipboardEvent) {
      const file = Array.from(e.clipboardData?.files ?? []).find(isAttachableFile)
      if (!file) return
      e.preventDefault()
      selectFile(file)
    }
    document.addEventListener('paste', onPaste)
    return () => document.removeEventListener('paste', onPaste)
  }, [stage.kind, aiAvailable])

  // Handle job completion
  useEffect(() => {
    if (!job || handled.current) return
    if (job.status !== 'done' && job.status !== 'error') return
    handled.current = true

    // The worker created/updated a transaction outside any mutation hook, so
    // this asks for exactly what a manual create asks for — by calling the
    // same helper rather than by copying its list, which is how this copy
    // came to be the only one carrying no account or budget id at all.
    void invalidateAfterTransactionChange(qc, {
      budgetId: null,
      transactionIds: job.transaction_id ? [job.transaction_id] : [],
    })
    // Job state is this component's own, not a transaction's.
    qc.invalidateQueries({ queryKey: [ROOT.aiJobs] })
    qc.invalidateQueries({ queryKey: [ROOT.aiJobsActive] })
    qc.invalidateQueries({ queryKey: [ROOT.aiJobForTxn] })

    if (job.transaction_id) {
      onReviewReady(job)
    } else {
      setStage({ kind: 'failed', message: job.error ?? 'Receipt scan failed' })
    }
  }, [job, qc, onReviewReady])

  function selectFile(file: File) {
    if (!isAttachableFile(file)) {
      toast.error(`${file.name} is not an image or PDF`)
      return
    }
    if (isTooLargeToAttach(file)) {
      toast.error(`${file.name} is too large (max ${MAX_ATTACHMENT_LABEL})`)
      return
    }
    setStage({ kind: 'preview', file })
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) selectFile(file)
  }

  async function handleScan() {
    if (stage.kind !== 'preview' || !accountId) return
    try {
      const result = await submitReceipt.mutateAsync({ file: stage.file, accountId })
      onRememberAccount()
      handled.current = false
      setStage({ kind: 'watching', jobId: result.id })
    } catch (err: unknown) {
      toast.error(apiErrorMessage(err, 'Failed to queue receipt'))
    }
  }

  // AI unavailable: explanatory empty state
  if (!aiAvailable) {
    return (
      <div className="receipt-scan">
        <div className="receipt-scan__empty">
          <Sparkles size={20} />
          <p>Receipt scanning requires a configured Ollama server.</p>
          <Link to="/settings" className="receipt-scan__link" onClick={onClose}>
            Configure AI in Settings
          </Link>
        </div>
      </div>
    )
  }

  // Failed state (no stub transaction)
  if (stage.kind === 'failed') {
    return (
      <div className="receipt-scan">
        <div className="receipt-scan__error">
          <AlertTriangle size={20} />
          <p>{stage.message}</p>
          <Link to="/ai-activity" className="receipt-scan__link" onClick={onClose}>
            View AI activity
          </Link>
        </div>
      </div>
    )
  }

  // Watching state (polling job)
  if (stage.kind === 'watching') {
    const statusText =
      job?.status === 'processing'
        ? 'Reading receipt…'
        : job?.status === 'queued'
          ? 'Waiting in queue…'
          : 'Processing…'
    const attemptText =
      job && job.attempts > 1 ? ` (attempt ${job.attempts}/${job.max_attempts})` : ''

    return (
      <div className="receipt-scan">
        <div className="receipt-scan__progress">
          {previewUrl && (
            <img src={previewUrl} alt="Receipt preview" className="receipt-scan__progress-thumb" />
          )}
          <div className="receipt-scan__progress-status">
            <Loader2 size={20} className="spin" />
            <span>
              {statusText}
              {attemptText}
            </span>
          </div>
          <p className="receipt-scan__progress-note">
            You can close this window — the scan keeps running and the transaction will arrive for
            review.
          </p>
          <Link to="/ai-activity" className="receipt-scan__link" onClick={onClose}>
            View AI activity
          </Link>
        </div>
      </div>
    )
  }

  // Preview state (file selected, ready to scan)
  if (stage.kind === 'preview') {
    const isPdf = stage.file.type === 'application/pdf'
    return (
      <div className="receipt-scan">
        <div className="receipt-scan__preview">
          {isPdf ? (
            <div className="receipt-scan__preview-pdf">
              <FileText size={32} />
              <span className="receipt-scan__preview-name">{stage.file.name}</span>
            </div>
          ) : (
            <img src={previewUrl!} alt="Receipt preview" className="receipt-scan__preview-img" />
          )}
          <button
            type="button"
            className="receipt-scan__preview-remove"
            onClick={() => setStage({ kind: 'pick' })}
            aria-label="Remove"
          >
            <X size={14} />
          </button>
        </div>
        <button
          type="button"
          className="receipt-scan__submit"
          onClick={handleScan}
          disabled={!accountId || submitReceipt.isPending}
        >
          <Sparkles size={13} />
          {submitReceipt.isPending ? 'Queuing…' : 'Scan receipt'}
        </button>
      </div>
    )
  }

  // Pick state (drop zone)
  return (
    <div className="receipt-scan">
      <div
        className={`receipt-scan__drop-zone ${dragOver ? 'receipt-scan__drop-zone--active' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <Upload size={20} />
        <span>{dragOver ? 'Drop receipt to scan' : 'Click, drag, or paste a receipt'}</span>
        <span className="receipt-scan__hint">Image or PDF, max {MAX_ATTACHMENT_LABEL}</span>
        <input
          ref={fileInputRef}
          type="file"
          accept={ATTACHMENT_ACCEPT}
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) selectFile(file)
            e.target.value = ''
          }}
          style={{ display: 'none' }}
        />
      </div>
    </div>
  )
}
