import { GripVertical } from 'lucide-react'
import './DragHandle.css'

interface Props {
  /** What the handle moves — for the accessible name. */
  label: string
  onDragStart: () => void
  onDragEnd: () => void
  onMoveUp?: () => void
  onMoveDown?: () => void
}

/**
 * The grip that starts a drag, and the keyboard path to the same outcome —
 * the order of a budget is not a pointer-only decision.
 *
 * Only the handle is draggable: making a whole row draggable turns every
 * attempt to select its name into a drag. Its host row carries
 * `drag-handle-host` and handles the drop; the handle sits in the host's left
 * padding rather than taking a grid column, so offering reordering never
 * shifts the money columns.
 */
export function DragHandle({ label, onDragStart, onDragEnd, onMoveUp, onMoveDown }: Props) {
  return (
    <span
      className="drag-handle"
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      tabIndex={0}
      role="button"
      aria-label={`Reorder ${label}. Use the arrow keys to move it.`}
      onKeyDown={(e) => {
        if (e.key === 'ArrowUp' && onMoveUp) {
          e.preventDefault()
          onMoveUp()
        }
        if (e.key === 'ArrowDown' && onMoveDown) {
          e.preventDefault()
          onMoveDown()
        }
      }}
      title="Drag to reorder, or use the arrow keys"
    >
      <GripVertical size={12} />
    </span>
  )
}
