import { useCallback, useMemo, useState } from 'react'

export interface DragReorderApi {
  /** A drag began on the row at `index`. */
  start: (index: number) => void
  /** The pointer is over the row at `index`. */
  over: (index: number) => void
  /** Dropped on the row at `index`: commits the move and clears the drag. */
  drop: (index: number) => void
  /** The drag ended, with or without a drop. */
  end: () => void
  /** The keyboard and button equivalent: move the row at `index` one step. */
  moveBy: (index: number, delta: -1 | 1) => void
}

export interface DragReorder extends DragReorderApi {
  dragIndex: number | null
  overIndex: number | null
}

/**
 * Drag-and-drop (and arrow-key) reordering of an indexed list — the one
 * implementation the budget grid's groups and categories, the view editor and
 * the filter manager share. It owns only the transient drag state; `onMove`
 * is where the caller persists the result. The returned object only changes
 * while a drag is in progress or when `onMove` does, so a memoised row that
 * receives it does not re-render for nothing.
 */
export function useDragReorder(
  count: number,
  onMove: (from: number, to: number) => void
): DragReorder {
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [overIndex, setOverIndex] = useState<number | null>(null)

  const start = useCallback((index: number) => setDragIndex(index), [])
  const over = useCallback((index: number) => setOverIndex(index), [])
  const end = useCallback(() => {
    setDragIndex(null)
    setOverIndex(null)
  }, [])
  const drop = useCallback(
    (index: number) => {
      if (dragIndex !== null && dragIndex !== index) onMove(dragIndex, index)
      setDragIndex(null)
      setOverIndex(null)
    },
    [dragIndex, onMove]
  )
  const moveBy = useCallback(
    (index: number, delta: -1 | 1) => {
      const to = index + delta
      if (to < 0 || to >= count) return
      onMove(index, to)
    },
    [count, onMove]
  )

  return useMemo(
    () => ({ dragIndex, overIndex, start, over, drop, end, moveBy }),
    [dragIndex, overIndex, start, over, drop, end, moveBy]
  )
}
