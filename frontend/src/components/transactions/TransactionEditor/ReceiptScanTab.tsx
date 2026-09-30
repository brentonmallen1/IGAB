import { useState, useRef, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Upload, X, Sparkles, FileText } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  ATTACHMENT_ACCEPT,
  MAX_ATTACHMENT_LABEL,
  isAttachableFile,
  isTooLargeToAttach,
} from '../../../api/attachments'
import { useSubmitReceipt } from '../../../api/aiJobs'
import { queuedMessage, WAITS_FOR_AN_ACCOUNT } from '../../ai/queuedMessage'
import './ReceiptScanTab.css'
import { apiErrorMessage } from '../../../api/client'
import { sectionHref } from '../../../pages/SettingsPage/settingsSections'

type Stage = { kind: 'pick' } | { kind: 'preview'; file: File }

interface Props {
  budgetId: string
  /** Resolved account (fixed or picked in the editor); '' when unpicked —
   *  the receipt then waits in AI Activity until a person chooses one. */
  accountId: string
  /** AI is configured. Not whether the model answers right now: the scan is
   *  queued and the worker retries, as on the phone. */
  aiEnabled: boolean
  /** Queued: the editor is done. */
  onQueued: () => void
  /** Called before navigating away (Settings). */
  onClose: () => void
}

/**
 * Scan a receipt from the desktop editor — the same hand-off as the phone's
 * Scan button. The receipt is queued and the editor closes; the row turns up
 * in the register to review (the AI badge's watch refreshes it), or, with no
 * account chosen, waits in AI Activity. It used to sit here polling the job
 * and open a review editor when it finished, which is waiting on the model
 * all the same.
 */
export function ReceiptScanTab({ budgetId, accountId, aiEnabled, onQueued, onClose }: Props) {
  const submitReceipt = useSubmitReceipt(budgetId)
  const [stage, setStage] = useState<Stage>({ kind: 'pick' })
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

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
    if (!aiEnabled) return
    function onPaste(e: ClipboardEvent) {
      const file = Array.from(e.clipboardData?.files ?? []).find(isAttachableFile)
      if (!file) return
      e.preventDefault()
      selectFile(file)
    }
    document.addEventListener('paste', onPaste)
    return () => document.removeEventListener('paste', onPaste)
  }, [aiEnabled])

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
    if (stage.kind !== 'preview') return
    try {
      await submitReceipt.mutateAsync({ file: stage.file, accountId: accountId || null })
      toast.success(queuedMessage('receipt', 1, !accountId), { duration: 6000 })
      onQueued()
    } catch (err: unknown) {
      // Nothing was queued: the photo stays in the preview to try again.
      toast.error(apiErrorMessage(err, 'Failed to queue receipt'))
    }
  }

  // AI not set up: explanatory empty state
  if (!aiEnabled) {
    return (
      <div className="receipt-scan">
        <div className="receipt-scan__empty">
          <Sparkles size={20} />
          <p>Receipt scanning requires a configured Ollama server.</p>
          <Link
            to={sectionHref({ id: 'ai', page: 'system' })}
            className="receipt-scan__link"
            onClick={onClose}
          >
            Configure AI in System settings
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
          disabled={submitReceipt.isPending}
        >
          <Sparkles size={13} />
          {submitReceipt.isPending ? 'Queuing…' : 'Scan receipt'}
        </button>
        <span className="receipt-scan__hint">
          {accountId
            ? "It's read in the background and turns up in your transactions to review."
            : WAITS_FOR_AN_ACCOUNT}
        </span>
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
