import { useState, useRef, useCallback, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { useAnchoredPosition } from '../../../hooks/useAnchoredPosition'
import { markTooltipHidden, tooltipDelayNow } from './tooltipDelay'
import './Tooltip.css'

/** Breathing room the popup keeps from its host. The distance it keeps from
 *  the viewport edges is `margin` in anchoredPosition, which used to be
 *  written here a second time as this same number. */
const GAP = 8

interface Props {
  content: React.ReactNode | null
  children: React.ReactNode
  /**
   * Fill the parent as a block instead of sitting inline. For a clipped text
   * cell (memo, payee) the host must be the block that carries the
   * ellipsis, or the text inside an inline-flex box clips without one.
   */
  block?: boolean
  /** Extra class on the host — the cell's own clipping class, typically. */
  className?: string
}

/**
 * The app's one hover tooltip. Shows after the cold delay on hover or
 * keyboard focus — at once when another tooltip just closed (see
 * tooltipDelay.ts) — hides on leave/blur or a press, and clamps itself to
 * the viewport. Never shows for a tap.
 * Prefer it over a native `title` anywhere a person actually waits for the
 * text — `title` has a browser-fixed delay of about a second and no
 * styling; keep `title` for the incidental case.
 */
export function Tooltip({ content, children, block = false, className }: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLSpanElement>(null)
  const popupRef = useRef<HTMLSpanElement>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Set by a press on the host, cleared when the pointer leaves or focus
  // moves on. A press means the person is acting, not asking: a click on the
  // approve glyph opened its menu under a tooltip that still covered it. On a
  // phone the press is the only signal at all — a tap fires an emulated
  // mouseenter and a focus but never the mouseleave, so the tooltip outlived
  // the tap and hung over the editor the row opened. Every touch starts with
  // pointerdown, so a tap never opens one.
  const pressed = useRef(false)

  // A tooltip is the same placement problem as every dropdown: centre it on
  // the host, keep it inside the viewport, and drop below when there is no
  // headroom. This used to be its own copy — its own EDGE constant, its own
  // horizontal clamp, its own flip, and no height cap at all.
  const pos = useAnchoredPosition(
    ref,
    open,
    { align: 'center', prefer: 'above', gap: GAP },
    popupRef
  )

  const cancel = useCallback(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current)
      timer.current = null
    }
  }, [])

  const show = useCallback(() => {
    if (pressed.current) return
    cancel()
    timer.current = setTimeout(() => {
      timer.current = null
      setOpen(true)
    }, tooltipDelayNow())
  }, [cancel])

  const hide = useCallback(() => {
    cancel()
    setOpen((wasOpen) => {
      if (wasOpen) markTooltipHidden()
      return false
    })
  }, [cancel])

  const press = useCallback(() => {
    pressed.current = true
    hide()
  }, [hide])

  const release = useCallback(() => {
    pressed.current = false
    hide()
  }, [hide])

  useEffect(() => cancel, [cancel])

  const hostClass = ['tooltip-host', block ? 'tooltip-host--block' : '', className ?? '']
    .filter(Boolean)
    .join(' ')

  return (
    <span
      ref={ref}
      className={hostClass}
      onMouseEnter={show}
      onMouseLeave={release}
      onPointerDown={press}
      onFocus={show}
      onBlur={release}
    >
      {children}
      {open &&
        content != null &&
        createPortal(
          <span
            ref={popupRef}
            className="tooltip-popup"
            style={{
              top: pos?.top,
              bottom: pos?.bottom,
              left: pos?.left,
              maxHeight: pos?.maxHeight,
              visibility: pos ? undefined : 'hidden',
            }}
            role="tooltip"
          >
            {content}
          </span>,
          document.body
        )}
    </span>
  )
}
