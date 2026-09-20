import { useEffect, useRef } from 'react'
import { isCellEditor } from '../keyboard/cellEditor'

export function isEditableTarget(): boolean {
  const active = document.activeElement
  return (
    active instanceof HTMLInputElement ||
    active instanceof HTMLTextAreaElement ||
    active instanceof HTMLSelectElement ||
    (active instanceof HTMLElement && active.isContentEditable)
  )
}

interface ShortcutOptions {
  /** Fire even while an input/textarea/select/contentEditable has focus */
  allowInInputs?: boolean
  /**
   * Fire while a *cell* editor has focus — a one-keystroke amount box marked
   * `data-cell-editor` (see keyboard/cellEditor). Only undo/redo want this:
   * committing an assignment opens the next row's box, so a bare guard left
   * ⌘Z permanently swallowed on the budget page.
   */
  allowInCellEditors?: boolean
  enabled?: boolean
}

/**
 * Register a global keyboard shortcut.
 *
 * Combo format: "mod+k", "shift+d", "?", "[" — "mod" is ⌘ on macOS and Ctrl
 * elsewhere. Symbol keys ("?", "[") match on the produced character, so their
 * physical Shift is not treated as a modifier mismatch.
 */
export function useShortcut(
  combo: string,
  handler: (e: KeyboardEvent) => void,
  opts: ShortcutOptions = {}
) {
  const handlerRef = useRef(handler)
  handlerRef.current = handler
  const { allowInInputs = false, allowInCellEditors = false, enabled = true } = opts

  useEffect(() => {
    if (!enabled) return
    const parts = combo.toLowerCase().split('+')
    const key = parts[parts.length - 1]
    const needMod = parts.includes('mod')
    const needShift = parts.includes('shift')
    const needAlt = parts.includes('alt')
    const symbolKey = key.length === 1 && !/^[a-z0-9]$/.test(key)

    function onKeyDown(e: KeyboardEvent) {
      if (!allowInInputs && isEditableTarget()) {
        if (!(allowInCellEditors && isCellEditor(document.activeElement))) return
      }
      if (needMod !== (e.metaKey || e.ctrlKey)) return
      if (!symbolKey && needShift !== e.shiftKey) return
      if (needAlt !== e.altKey) return
      if (e.key.toLowerCase() !== key) return
      e.preventDefault()
      handlerRef.current(e)
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [combo, allowInInputs, allowInCellEditors, enabled])
}
