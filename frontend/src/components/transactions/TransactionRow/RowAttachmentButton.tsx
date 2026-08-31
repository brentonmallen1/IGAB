import { useRef, useState } from 'react'
import { Image as ImageIcon } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { apiClient } from '../../../api/client'
import {
  ATTACHMENT_ACCEPT,
  fetchAttachmentBlob,
  isAttachableFile,
  isPdfAttachment,
  uploadFilesToTransaction,
  type Attachment,
} from '../../../api/attachments'
import { AttachmentLightbox } from '../../attachments/Lightbox'
import { ROOT } from '../../../api/queryKeys'

interface Props {
  transactionId: string
  hasAttachment: boolean
}

/**
 * Per-row image button: muted when the transaction has no attachment (click
 * to add one), accent-colored when it does (click to view). Registers are
 * dense — this stays a 12px icon like the other status glyphs.
 */
export function RowAttachmentButton({ transactionId, hasAttachment }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()
  const [viewer, setViewer] = useState<{ atts: Attachment[]; index: number } | null>(null)
  const [busy, setBusy] = useState(false)

  async function openViewer() {
    setBusy(true)
    try {
      const { data } = await apiClient.get<Attachment[]>(
        `/transactions/${transactionId}/attachments`
      )
      if (data.length === 0) {
        // Indicator was stale — fall through to add
        fileRef.current?.click()
        return
      }
      // Lightbox shows images; PDFs use the browser's native viewer
      const images = data.filter((a) => !isPdfAttachment(a))
      if (images.length > 0) {
        setViewer({ atts: images, index: 0 })
      } else {
        const url = await fetchAttachmentBlob(data[0].id)
        window.open(url, '_blank')
      }
    } catch {
      toast.error('Could not load attachment')
    } finally {
      setBusy(false)
    }
  }

  async function onFiles(list: FileList | null) {
    const files = Array.from(list ?? []).filter(isAttachableFile)
    if (files.length === 0) return
    setBusy(true)
    try {
      const { ok, failed } = await uploadFilesToTransaction(transactionId, files)
      if (ok > 0) {
        qc.invalidateQueries({ queryKey: [ROOT.attachmentCheck] })
        qc.invalidateQueries({ queryKey: [ROOT.attachments, transactionId] })
      }
      if (failed.length > 0) {
        toast.error(`${failed.length} file${failed.length !== 1 ? 's' : ''} failed to upload`)
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button
        type="button"
        className={`txn-status-icon txn-attach-btn ${hasAttachment ? 'txn-attach-btn--has' : ''}`}
        onClick={(e) => {
          e.stopPropagation()
          if (busy) return
          if (hasAttachment) void openViewer()
          else fileRef.current?.click()
        }}
        title={hasAttachment ? 'View attachment' : 'Add image'}
        aria-label={hasAttachment ? 'View attachment' : 'Add image'}
      >
        <ImageIcon size={12} />
      </button>
      <input
        ref={fileRef}
        type="file"
        accept={ATTACHMENT_ACCEPT}
        multiple
        onChange={(e) => {
          void onFiles(e.target.files)
          e.target.value = ''
        }}
        style={{ display: 'none' }}
        onClick={(e) => e.stopPropagation()}
      />
      {viewer && (
        <AttachmentLightbox
          attachment={viewer.atts[viewer.index]}
          onClose={() => setViewer(null)}
          hasPrev={viewer.index > 0}
          hasNext={viewer.index < viewer.atts.length - 1}
          onPrev={() => setViewer((v) => v && { ...v, index: Math.max(0, v.index - 1) })}
          onNext={() =>
            setViewer((v) => v && { ...v, index: Math.min(v.atts.length - 1, v.index + 1) })
          }
        />
      )}
    </>
  )
}
