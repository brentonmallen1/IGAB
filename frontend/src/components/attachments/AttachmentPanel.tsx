import { useState, useRef, useCallback } from 'react'
import { Camera, Paperclip, Upload, Trash2, X, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  ATTACHMENT_ACCEPT,
  MAX_ATTACHMENT_LABEL,
  isTooLargeToAttach,
  fetchAttachmentBlob,
  isAttachableFile,
  isPdfAttachment,
  useAttachments,
  useUploadAttachment,
  useDeleteAttachment,
  useAttachmentUrl,
  type Attachment,
} from '../../api/attachments'
import { AttachmentLightbox } from './Lightbox'
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
        <img src={thumbUrl} alt={attachment.original_filename} loading="lazy" onClick={onClick} />
      ) : (
        <div className="attachment-thumb__loading" />
      )}
      <button
        className="attachment-thumb__delete"
        onClick={(e) => {
          e.stopPropagation()
          onDelete()
        }}
        aria-label="Delete"
      >
        <Trash2 size={12} />
      </button>
      <span className="attachment-thumb__name">{attachment.original_filename}</span>
    </div>
  )
}

interface Props {
  transactionId: string
  onClose?: () => void
  /** Rendered inside another surface (transaction editor): no header chrome */
  embedded?: boolean
}

export function AttachmentPanel({ transactionId, onClose, embedded = false }: Props) {
  const { data: attachments = [], isLoading } = useAttachments(transactionId)
  // Lightbox prev/next navigates images only; PDFs open in a new tab
  const imageAttachments = attachments.filter((a) => !isPdfAttachment(a))
  const upload = useUploadAttachment(transactionId)
  const deleteAttachment = useDeleteAttachment(transactionId)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const cameraInputRef = useRef<HTMLInputElement>(null)
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)
  const [dragOver, setDragOver] = useState(false)

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return

      for (const file of Array.from(files)) {
        if (!isAttachableFile(file)) {
          toast.error(`${file.name} is not an image or PDF`)
          continue
        }
        if (isTooLargeToAttach(file)) {
          toast.error(`${file.name} is too large (max ${MAX_ATTACHMENT_LABEL})`)
          continue
        }
        try {
          await upload.mutateAsync(file)
          toast.success('Attachment uploaded')
        } catch {
          toast.error('Upload failed')
        }
      }
    },
    [upload]
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      handleFiles(e.dataTransfer.files)
    },
    [handleFiles]
  )

  const handleDelete = async (attachmentId: string) => {
    try {
      await deleteAttachment.mutateAsync(attachmentId)
      toast.success('Attachment deleted')
    } catch {
      toast.error('Delete failed')
    }
  }

  return (
    <div className={`attachment-panel ${embedded ? 'attachment-panel--embedded' : ''}`}>
      {!embedded && (
        <div className="attachment-panel__header">
          <span className="attachment-panel__title">
            <Paperclip size={14} />
            Attachments
          </span>
          <button className="attachment-panel__close" onClick={onClose} aria-label="Close">
            <X size={14} />
          </button>
        </div>
      )}

      <div
        className={`attachment-panel__drop-zone ${dragOver ? 'attachment-panel__drop-zone--active' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <Upload size={20} />
        <span>{dragOver ? 'Drop to upload' : 'Click or drag to upload'}</span>
        <input
          ref={fileInputRef}
          type="file"
          accept={ATTACHMENT_ACCEPT}
          multiple
          onChange={(e) => handleFiles(e.target.files)}
          style={{ display: 'none' }}
        />
      </div>

      <button
        type="button"
        className="attachment-panel__camera-btn"
        onClick={() => cameraInputRef.current?.click()}
      >
        <Camera size={15} />
        Take photo
      </button>
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        onChange={(e) => handleFiles(e.target.files)}
        style={{ display: 'none' }}
      />

      {isLoading ? (
        <div className="attachment-panel__loading">
          <Loader2 size={20} className="spin" />
        </div>
      ) : attachments.length === 0 ? (
        <div className="attachment-panel__empty">No attachments yet</div>
      ) : (
        <div className="attachment-panel__grid">
          {attachments.map((att) => (
            <AttachmentThumb
              key={att.id}
              attachment={att}
              onClick={() => {
                // The lightbox is an image viewer — PDFs open in the
                // browser's native viewer in a new tab
                if (isPdfAttachment(att)) {
                  void fetchAttachmentBlob(att.id).then((url) => window.open(url, '_blank'))
                } else {
                  setLightboxIndex(imageAttachments.indexOf(att))
                }
              }}
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

      {lightboxIndex !== null && imageAttachments[lightboxIndex] && (
        <AttachmentLightbox
          attachment={imageAttachments[lightboxIndex]}
          onClose={() => setLightboxIndex(null)}
          onPrev={() => setLightboxIndex((i) => (i !== null && i > 0 ? i - 1 : i))}
          onNext={() =>
            setLightboxIndex((i) => (i !== null && i < imageAttachments.length - 1 ? i + 1 : i))
          }
          hasPrev={lightboxIndex > 0}
          hasNext={lightboxIndex < imageAttachments.length - 1}
        />
      )}
    </div>
  )
}
