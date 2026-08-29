import { Redo2, Undo2 } from 'lucide-react'
import { useUndoRedo } from '../../../hooks/useUndoRedo'
import { SHORTCUTS, formatCombo } from '../../../keyboard/shortcuts'

/**
 * Undo and redo, visible.
 *
 * ⌘Z has worked since the change log landed, but a keyboard shortcut nobody
 * is told about is a feature only its author has. These call the same
 * `useUndoRedo` the keys do.
 *
 * Deliberately always enabled rather than greyed out when there is nothing to
 * undo: knowing that would mean polling the change log to colour a button,
 * and the empty case already answers honestly with "Nothing to undo".
 */
export function UndoRedoButtons() {
  const { undo, redo, enabled } = useUndoRedo()
  if (!enabled) return null

  return (
    <div className="header__undo-group">
      <button
        className="header__icon-btn"
        onClick={undo}
        aria-label="Undo last change"
        aria-keyshortcuts={SHORTCUTS.undo.combo.replace('mod', 'Meta')}
        title={`Undo last change (${formatCombo(SHORTCUTS.undo.combo)})`}
      >
        <Undo2 size={16} />
      </button>
      <button
        className="header__icon-btn"
        onClick={redo}
        aria-label="Redo"
        aria-keyshortcuts={SHORTCUTS.redo.combo.replace('mod', 'Meta')}
        title={`Redo (${formatCombo(SHORTCUTS.redo.combo)})`}
      >
        <Redo2 size={16} />
      </button>
    </div>
  )
}
