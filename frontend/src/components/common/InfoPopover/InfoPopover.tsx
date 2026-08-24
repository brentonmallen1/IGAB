import { useEffect, useRef, useState } from 'react'
import { Info, X } from 'lucide-react'
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

/**
 * An ⓘ button that opens a small explanation beside it.
 *
 * Shared so that "how does this work?" looks and behaves the same wherever it
 * is asked. Closes on outside click and on Escape, and returns focus to the
 * trigger — a popover that traps focus somewhere unreachable is worse than no
 * popover for anyone navigating by keyboard.
 */
export function InfoPopover({ title, label = 'More information', width, children }: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    function onPointer(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
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
    <div className="info-pop" ref={ref}>
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
      {open && (
        <div className="info-pop__panel" style={width ? { width } : undefined} role="dialog" aria-label={title}>
          <div className="info-pop__header">
            <span className="info-pop__title">{title}</span>
            <button
              className="info-pop__close"
              onClick={() => { setOpen(false); triggerRef.current?.focus() }}
              type="button"
              aria-label="Close"
            >
              <X size={13} />
            </button>
          </div>
          <div className="info-pop__body">{children}</div>
        </div>
      )}
    </div>
  )
}
