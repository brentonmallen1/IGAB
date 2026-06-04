import { useState, useRef, useCallback } from 'react'
import { Paperclip, Upload, Trash2, X, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAttachments, useUploadAttachment, useDeleteAttachment, useAttachmentUrl, type Attachment } from '../../api/attachments'
import { Lightbox } from './Lightbox'
import './AttachmentPanel.css'

function AttachmentThumb({
  attachment,
  onClick,
  onDelete,
}: {
  attachment: Attachment
  onClick: () => void
  onDelete: () => void
}) {
  const { data: thumbUrl } = useAttachmentUrl(attachment.id, true)

  return (
    <div className="attachment-thumb">
      {thumbUrl ? (
        <img src={thumbUrl} alt={attachment.original_filename} onClick={onClick} />
      ) : (
        <div className="attachment-thumb__loading" />
      )}
      <button
        className="attachment-thumb__delete"
        onClick={(e) => { e.stopPropagation(); onDelete() }}
        aria-label="Delete"
      >
        <Trash2 size={12} />
      </button>
      <span className="attachment-thumb__name">{attachment.original_filename}</span>
    </div>
  )
}

function LightboxWithFetch({
  attachment,
  onClose,
  onPrev,
  onNext,
  hasPrev,
  hasNext,
}: {
  attachment: Attachment
  onClose: () => void
  onPrev: () => void
  onNext: () => void
  hasPrev: boolean
  hasNext: boolean
}) {
  const { data: fullUrl } = useAttachmentUrl(attachment.id, false)

  if (!fullUrl) return null

  return (
    <Lightbox
      src={fullUrl}
      alt={attachment.original_filename}
      onClose={onClose}
      onPrev={onPrev}
      onNext={onNext}
      hasPrev={hasPrev}
      hasNext={hasNext}
    />
  )
}

interface Props {
  transactionId: string
  onClose: () => void
}

export function AttachmentPanel({ transactionId, onClose }: Props) {
  const { data: attachments = [], isLoading } = useAttachments(transactionId)
  const upload = useUploadAttachment(transactionId)
  const deleteAttachment = useDeleteAttachment(transactionId)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)
  const [dragOver, setDragOver] = useState(false)

  const handleFiles = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return

    for (const file of Array.from(files)) {
      if (!file.type.startsWith('image/')) {
        toast.error(`${file.name} is not an image`)
        continue
      }
      if (file.size > 20 * 1024 * 1024) {
        toast.error(`${file.name} is too large (max 20MB)`)
        continue
      }
      try {
        await upload.mutateAsync(file)
        toast.success('Attachment uploaded')
      } catch {
        toast.error('Upload failed')
      }
    }
  }, [upload])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    handleFiles(e.dataTransfer.files)
  }, [handleFiles])

  const handleDelete = async (attachmentId: string) => {
    try {
      await deleteAttachment.mutateAsync(attachmentId)
      toast.success('Attachment deleted')
    } catch {
      toast.error('Delete failed')
    }
  }

  return (
    <div className="attachment-panel">
      <div className="attachment-panel__header">
        <span className="attachment-panel__title">
          <Paperclip size={14} />
          Attachments
        </span>
        <button className="attachment-panel__close" onClick={onClose} aria-label="Close">
          <X size={14} />
        </button>
      </div>

      <div
        className={`attachment-panel__drop-zone ${dragOver ? 'attachment-panel__drop-zone--active' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <Upload size={20} />
        <span>{dragOver ? 'Drop to upload' : 'Click or drag to upload'}</span>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          onChange={(e) => handleFiles(e.target.files)}
          style={{ display: 'none' }}
        />
      </div>

      {isLoading ? (
        <div className="attachment-panel__loading">
          <Loader2 size={20} className="spin" />
        </div>
      ) : attachments.length === 0 ? (
        <div className="attachment-panel__empty">No attachments yet</div>
      ) : (
        <div className="attachment-panel__grid">
          {attachments.map((att, idx) => (
            <AttachmentThumb
              key={att.id}
              attachment={att}
              onClick={() => setLightboxIndex(idx)}
              onDelete={() => handleDelete(att.id)}
            />
          ))}
        </div>
      )}

      {upload.isPending && (
        <div className="attachment-panel__uploading">
          <Loader2 size={16} className="spin" />
          Uploading…
        </div>
      )}

      {lightboxIndex !== null && attachments[lightboxIndex] && (
        <LightboxWithFetch
          attachment={attachments[lightboxIndex]}
          onClose={() => setLightboxIndex(null)}
          onPrev={() => setLightboxIndex((i) => (i !== null && i > 0 ? i - 1 : i))}
          onNext={() => setLightboxIndex((i) => (i !== null && i < attachments.length - 1 ? i + 1 : i))}
          hasPrev={lightboxIndex > 0}
          hasNext={lightboxIndex < attachments.length - 1}
        />
      )}
    </div>
  )
}
