import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import { useUpdateCategory } from '../../../api/categories'

/** What is in flight, while a category is being dragged. */
export interface CategoryDragState {
  categoryId: string
  /** The group it started in — a drop back into this one is a reorder, not a
   *  move, and stays with the group's own `useDragReorder`. */
  fromGroupId: string
}

interface CategoryDragApi {
  dragging: CategoryDragState | null
  begin: (drag: CategoryDragState) => void
  end: () => void
  /**
   * Whether dropping on `groupId` right now would move the dragged category
   * there. False during a group drag, and false inside the category's own
   * group, where the group's index-based reorder is the right handler.
   */
  wouldMoveTo: (groupId: string) => boolean
  /** Move the dragged category into `groupId`, and clear the drag. */
  moveTo: (groupId: string) => void
}

const CategoryDragCtx = createContext<CategoryDragApi | null>(null)

/**
 * Which category is being dragged, across the whole grid.
 *
 * Reordering inside a group is index-based (`useDragReorder`), and that is
 * right for a list: a drop target is an integer. But there is one such
 * instance *per group*, each closing over its own `group.id`, so a row
 * dragged from group A and dropped in group B called B's `drop(index)` with
 * B's `dragIndex` still null — and `useDragReorder` correctly did nothing.
 * The move was not blocked; it was unrepresentable, which is why it failed
 * silently rather than erroring.
 *
 * This carries the one fact the index cannot: *which* category is moving, and
 * where it came from. `dataTransfer` would be the browser-native place to put
 * it, but its contents are unreadable during `dragover` — precisely when the
 * drop indicator has to decide whether this group is a target.
 *
 * A cross-group drop appends to the end of the target group, which is what
 * the server does when a PATCH names a new group without a position
 * (`api/v1/categories.py`). Landing it at the dropped-on index would take a
 * second request to renumber the target group, and then ⌘Z would undo half a
 * move — categories sort by `(sort_order, name)`, so sharing a neighbour's
 * sort_order is not a position, it is a tie broken alphabetically.
 */
export function CategoryDragProvider({
  budgetId,
  children,
}: {
  budgetId: string
  children: React.ReactNode
}) {
  const [dragging, setDragging] = useState<CategoryDragState | null>(null)
  const updateCategory = useUpdateCategory(budgetId)

  const begin = useCallback((drag: CategoryDragState) => setDragging(drag), [])
  const end = useCallback(() => setDragging(null), [])

  const wouldMoveTo = useCallback(
    (groupId: string) => dragging !== null && dragging.fromGroupId !== groupId,
    [dragging]
  )

  const moveTo = useCallback(
    (groupId: string) => {
      if (dragging && dragging.fromGroupId !== groupId) {
        // No sort_order: the server puts it last in the new group. One
        // request, one change-log record, one undo.
        updateCategory.mutate({ id: dragging.categoryId, category_group_id: groupId })
      }
      setDragging(null)
    },
    [dragging, updateCategory]
  )

  const value = useMemo(
    () => ({ dragging, begin, end, wouldMoveTo, moveTo }),
    [dragging, begin, end, wouldMoveTo, moveTo]
  )
  return <CategoryDragCtx.Provider value={value}>{children}</CategoryDragCtx.Provider>
}

/**
 * Null outside the budget grid's own arrangement — the view editor and the
 * filter manager reorder lists that have no groups to move between, and they
 * share `useDragReorder` without this.
 */
export function useCategoryDrag(): CategoryDragApi | null {
  return useContext(CategoryDragCtx)
}
