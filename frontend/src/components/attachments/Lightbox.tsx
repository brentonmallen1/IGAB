import { useEffect, useCallback, useRef } from 'react'
import { createPortal } from 'react-dom'
import { X, ChevronLeft, ChevronRight, RotateCw, Download, Printer, Loader2 } from 'lucide-react'
import { usePinchZoom } from '../../hooks/usePinchZoom'
import { lockBodyScroll, unlockBodyScroll } from '../../utils/scrollLock'
import {
  downloadAttachment,
  isPdfAttachment,
  useAttachmentUrl,
  useRotateAttachment,
  type Attachment,
} from '../../api/attachments'
import './Lightbox.css'

const SWIPE_THRESHOLD_PX = 60

interface Props {
  src: string
  alt: string
  onClose: () => void
  onPrev?: () => void
  onNext?: () => void
  hasPrev?: boolean
  hasNext?: boolean
  /** When set, the toolbar (rotate / download / print) is shown. */
  attachment?: Pick<Attachment, 'id' | 'original_filename' | 'content_type'>
}

export function Lightbox({
  src,
  alt,
  onClose,
  onPrev,
  onNext,
  hasPrev,
  hasNext,
  attachment,
}: Props) {
  const touchStartRef = useRef<{ x: number; y: number } | null>(null)
  const { scale, translateX, translateY, isZoomed, reset, handlers: zoomHandlers } = usePinchZoom()
  const rotate = useRotateAttachment()
  const canRotate = attachment !== undefined && !isPdfAttachment(attachment)

  function handlePrint() {
    const w = window.open('', '_blank')
    if (!w) return
    const title = (attachment?.original_filename ?? alt).replace(/[<>&"]/g, '')
    w.document.write(
      `<!doctype html><html><head><title>${title}</title>` +
        '<style>body{margin:0;display:flex;justify-content:center}img{max-width:100%}</style>' +
        `</head><body><img src="${src}" onload="setTimeout(function(){window.print()},50)"></body></html>`
    )
    w.document.close()
  }

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft' && hasPrev && onPrev) onPrev()
      if (e.key === 'ArrowRight' && hasNext && onNext) onNext()
    },
    [onClose, onPrev, onNext, hasPrev, hasNext]
  )

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  // Separate effect with no deps: handleKeyDown changes on every navigation
  // between images, and the lock must span the whole lightbox lifetime rather
  // than churning the shared refcount on each arrow press.
  useEffect(() => {
    lockBodyScroll()
    return unlockBodyScroll
  }, [])

  function handleTouchStart(e: React.TouchEvent) {
    if (isZoomed) return
    touchStartRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }
  }

  function handleTouchEnd(e: React.TouchEvent) {
    if (isZoomed) return
    const start = touchStartRef.current
    touchStartRef.current = null
    if (!start) return
    const dx = e.changedTouches[0].clientX - start.x
    const dy = e.changedTouches[0].clientY - start.y
    // Horizontal swipe navigates; ignore mostly-vertical gestures
    if (Math.abs(dx) < SWIPE_THRESHOLD_PX || Math.abs(dy) > Math.abs(dx)) return
    if (dx < 0 && hasNext && onNext) onNext()
    if (dx > 0 && hasPrev && onPrev) onPrev()
  }

  // Reset zoom when navigating to a different image
  useEffect(() => {
    reset()
  }, [src, reset])

  // Portal to document.body so the lightbox escapes any parent stacking
  // context, and rank it at --z-nested-overlay: it is opened from inside
  // another overlay and must sit above the one that raised it.
  return createPortal(
    <div
      className="lightbox-overlay"
      onClick={onClose}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      <button className="lightbox-close" onClick={onClose} aria-label="Close">
        <X size={24} />
      </button>

      {attachment && (
        <div className="lightbox-toolbar" onClick={(e) => e.stopPropagation()}>
          {canRotate && (
            <button
              className="lightbox-toolbar__btn"
              onClick={() => rotate.mutate({ attachmentId: attachment.id, degrees: 90 })}
              disabled={rotate.isPending}
              aria-label="Rotate 90° clockwise"
              title="Rotate 90° clockwise (saved)"
            >
              {rotate.isPending ? <Loader2 size={18} className="spin" /> : <RotateCw size={18} />}
            </button>
          )}
          <button
            className="lightbox-toolbar__btn"
            onClick={() => void downloadAttachment(attachment)}
            aria-label="Download"
            title="Download"
          >
            <Download size={18} />
          </button>
          <button
            className="lightbox-toolbar__btn"
            onClick={handlePrint}
            aria-label="Print"
            title="Print"
          >
            <Printer size={18} />
          </button>
        </div>
      )}

      {hasPrev && onPrev && (
        <button
          className="lightbox-nav lightbox-nav--prev"
          onClick={(e) => {
            e.stopPropagation()
            onPrev()
          }}
          aria-label="Previous"
        >
          <ChevronLeft size={32} />
        </button>
      )}

      <img
        className={`lightbox-image ${isZoomed ? 'lightbox-image--zoomed' : ''}`}
        src={src}
        alt={alt}
        onClick={(e) => e.stopPropagation()}
        style={
          isZoomed
            ? {
                transform: `scale(${scale}) translate(${translateX}px, ${translateY}px)`,
              }
            : undefined
        }
        {...zoomHandlers}
      />

      {hasNext && onNext && (
        <button
          className="lightbox-nav lightbox-nav--next"
          onClick={(e) => {
            e.stopPropagation()
            onNext()
          }}
          aria-label="Next"
        >
          <ChevronRight size={32} />
        </button>
      )}
    </div>,
    document.body
  )
}

/**
 * Lightbox driven by the attachment blob query rather than a pre-fetched URL,
 * so the image refreshes in place after a rotate invalidates the blob cache.
 */
export function AttachmentLightbox({
  attachment,
  onClose,
  onPrev,
  onNext,
  hasPrev,
  hasNext,
}: {
  attachment: Pick<Attachment, 'id' | 'original_filename' | 'content_type'>
  onClose: () => void
  onPrev?: () => void
  onNext?: () => void
  hasPrev?: boolean
  hasNext?: boolean
}) {
  const { data: fullUrl } = useAttachmentUrl(attachment.id, false)

  if (!fullUrl) return null

  return (
    <Lightbox
      src={fullUrl}
      alt={attachment.original_filename}
      attachment={attachment}
      onClose={onClose}
      onPrev={onPrev}
      onNext={onNext}
      hasPrev={hasPrev}
      hasNext={hasNext}
    />
  )
}
