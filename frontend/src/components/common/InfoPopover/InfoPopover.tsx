import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Info, X } from 'lucide-react'
import { useAnchoredPosition } from '../../../hooks/useAnchoredPosition'
import './InfoPopover.css'

interface Props {
  title: string
  /** Screen-reader name for the trigger — say what it explains, since "info"
   *  on its own tells a screen-reader user nothing about which thing. */
  label?: string
  /** Panel width. The default suits a paragraph or two; explanations with
   *  examples need more room to avoid wrapping every line of code. */
  width?: number
  children: React.ReactNode
}

// Wider than the app's menus because this is prose, not a list of options.
const PANEL_WIDTH = 320
const PANEL_GAP = 6

/**
 * One titled group inside a popover body.
 *
 * The separation an explanation needs is structural, not decorative: a label
 * to enter at, and a gap wider than the text's own line spacing so proximity
 * says "new topic" instead of "next line". Popover copy that skips this reads
 * as one grey block no matter how well it is written — which is what the
 * search help had become.
 *
 * The heading is a real <h3> as well as a visual label, so the structure is
 * there for a screen reader too.
 */
export function InfoSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="info-pop__section">
      <h3 className="section-label info-pop__section-title">{title}</h3>
      {children}
    </section>
  )
}

/**
 * An ⓘ button that opens a small explanation beside it.
 *
 * Shared so that "how does this work?" looks and behaves the same wherever it
 * is asked. Closes on outside click and on Escape, and returns focus to the
 * trigger — a popover that traps focus somewhere unreachable is worse than no
 * popover for anyone navigating by keyboard.
 *
 * The panel is portalled to <body> and positioned fixed rather than absolutely
 * beside the trigger. It has to be: the app shell clips it otherwise —
 * `.main-layout__content` is `overflow: hidden` and `.main-layout__main`
 * scrolls, so an absolutely-positioned panel was cut off at the main column's
 * edge and looked like it slid under the sidebar. No z-index can outrank a
 * clip, and the toolbar it opens from is its own stacking context besides.
 */
export function InfoPopover({ title, label = 'More information', width, children }: Props) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const pos = useAnchoredPosition(triggerRef, open, {
    width: width ?? PANEL_WIDTH,
    gap: PANEL_GAP,
  })

  useEffect(() => {
    if (!open) return
    function onPointer(e: MouseEvent) {
      // Both refs: the panel is portalled, so the trigger's wrapper does not
      // contain it and a click inside the panel would read as "outside".
      const t = e.target as Node
      if (!triggerRef.current?.contains(t) && !panelRef.current?.contains(t)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key !== 'Escape') return
      // Capture phase, and the event stops here. Escape closes the INNERMOST
      // thing: this popover opens inside surfaces that close on Escape
      // themselves (the ⌘K palette, modals), and letting it through meant one
      // press dismissed both — the explanation the user just opened AND the
      // thing they were reading it about.
      e.stopPropagation()
      setOpen(false)
      triggerRef.current?.focus()
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey, true)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey, true)
    }
  }, [open])

  return (
    <div className="info-pop">
      <button
        ref={triggerRef}
        className="info-pop__btn"
        onClick={() => setOpen((v) => !v)}
        type="button"
        aria-label={label}
        aria-expanded={open}
      >
        <Info size={15} />
      </button>
      {open &&
        pos &&
        createPortal(
          <div
            ref={panelRef}
            className="info-pop__panel"
            style={{
              top: pos.top,
              bottom: pos.bottom,
              left: pos.left,
              width: pos.width,
              maxHeight: pos.maxHeight,
            }}
            role="dialog"
            aria-label={title}
          >
            <div className="info-pop__header">
              <span className="info-pop__title">{title}</span>
              <button
                className="info-pop__close"
                onClick={() => {
                  setOpen(false)
                  triggerRef.current?.focus()
                }}
                type="button"
                aria-label="Close"
              >
                <X size={13} />
              </button>
            </div>
            <div className="info-pop__body">{children}</div>
          </div>,
          document.body
        )}
    </div>
  )
}
