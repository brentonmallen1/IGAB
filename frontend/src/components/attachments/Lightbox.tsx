import { useEffect, useCallback, useRef } from 'react'
import { createPortal } from 'react-dom'
import { X, ChevronLeft, ChevronRight } from 'lucide-react'
import { usePinchZoom } from '../../hooks/usePinchZoom'
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
}

export function Lightbox({ src, alt, onClose, onPrev, onNext, hasPrev, hasNext }: Props) {
  const touchStartRef = useRef<{ x: number; y: number } | null>(null)
  const { scale, translateX, translateY, isZoomed, reset, handlers: zoomHandlers } = usePinchZoom()

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose()
    if (e.key === 'ArrowLeft' && hasPrev && onPrev) onPrev()
    if (e.key === 'ArrowRight' && hasNext && onNext) onNext()
  }, [onClose, onPrev, onNext, hasPrev, hasNext])

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = ''
    }
  }, [handleKeyDown])

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

  // Portal to document.body so the lightbox escapes any parent stacking context
  // (e.g. TransactionEditor's z-index: 100) and renders above everything.
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

      {hasPrev && onPrev && (
        <button
          className="lightbox-nav lightbox-nav--prev"
          onClick={(e) => { e.stopPropagation(); onPrev() }}
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
        style={isZoomed ? {
          transform: `scale(${scale}) translate(${translateX}px, ${translateY}px)`,
        } : undefined}
        {...zoomHandlers}
      />

      {hasNext && onNext && (
        <button
          className="lightbox-nav lightbox-nav--next"
          onClick={(e) => { e.stopPropagation(); onNext() }}
          aria-label="Next"
        >
          <ChevronRight size={32} />
        </button>
      )}
    </div>,
    document.body
  )
}
