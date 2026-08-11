import { useState } from 'react'
import { ExternalLink, Maximize2 } from 'lucide-react'
import { useAttachmentUrl } from '../../api/attachments'
import { Lightbox } from '../attachments/Lightbox'
import './ReceiptPane.css'

interface Props {
  attachmentId: string
  /** MIME of the stored attachment — PDFs render via the browser's native
   * viewer (iframe) instead of the image pipeline. */
  contentType?: string | null
  alt?: string
}

/**
 * Zoomable receipt beside the review form. Images: scrollable inline view,
 * tap expands to the full Lightbox with pinch zoom. PDFs: embedded native
 * viewer with an open-in-tab affordance.
 */
export function ReceiptPane({ attachmentId, contentType = null, alt = 'Receipt' }: Props) {
  const { data: url } = useAttachmentUrl(attachmentId)
  const [expanded, setExpanded] = useState(false)
  const isPdf = contentType === 'application/pdf'

  if (!url) {
    return <div className="receipt-pane receipt-pane--loading" aria-label="Loading receipt" />
  }

  if (isPdf) {
    return (
      <div className="receipt-pane">
        <button
          type="button"
          className="receipt-pane__expand"
          onClick={() => window.open(url, '_blank')}
          aria-label="Open PDF in new tab"
          title="Open in new tab"
        >
          <ExternalLink size={14} />
        </button>
        <iframe className="receipt-pane__pdf" src={url} title={alt} />
      </div>
    )
  }

  return (
    <>
      <div className="receipt-pane">
        <button
          type="button"
          className="receipt-pane__expand"
          onClick={() => setExpanded(true)}
          aria-label="Expand receipt"
          title="Expand"
        >
          <Maximize2 size={14} />
        </button>
        <div className="receipt-pane__scroll">
          <img
            src={url}
            alt={alt}
            className="receipt-pane__image"
            onClick={() => setExpanded(true)}
          />
        </div>
      </div>
      {expanded && <Lightbox src={url} alt={alt} onClose={() => setExpanded(false)} />}
    </>
  )
}
