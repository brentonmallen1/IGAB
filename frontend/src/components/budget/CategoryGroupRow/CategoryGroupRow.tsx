import { useCallback, useMemo, useRef, useState } from 'react'
import { Archive, ChevronDown, ChevronRight, Pencil, Plus, Trash2 } from 'lucide-react'
import { useUIStore } from '../../../stores/uiStore'
import {
  useArchiveCategoryGroup,
  useCreateCategory,
  useReorderCategories,
  useUpdateCategoryGroup,
} from '../../../api/categories'
import { CategoryRow } from '../CategoryRow/CategoryRow'
import { useDeleteCategoryFlow } from '../DeleteCategoryModal/useDeleteCategoryFlow'
import { useFormatters } from '../../../hooks/useFormatters'
import { useDragReorder, type DragReorder } from '../../../hooks/useDragReorder'
import { useCategoryDrag } from '../CategoryDrag/CategoryDragContext'
import { DragHandle } from '../../common/DragHandle/DragHandle'
import { moveItem } from '../../../utils/listOrder'
import { sumBalances } from '../budgetTotals'
import type { Category, CategoryBalance, CategoryGroup } from '../../../types'
import '../budgetGrid.css'
import './CategoryGroupRow.css'

interface Props {
  group: CategoryGroup
  categories: Category[]
  balanceMap: Map<string, CategoryBalance>
  budgetId: string
  month: string
  /** Rendering a view's group, not the budget's own. Rename, hide, delete and
   *  add-category all act on the default arrangement, which a view must never
   *  edit — so they are suppressed rather than silently doing the wrong thing. */
  readOnlyGroup?: boolean
  /** This group's position in the list being reordered. */
  index: number
  /** Present only where reordering groups is meaningful: the budget's own
   *  arrangement, unfiltered, showing every group. Absent under a filter, a
   *  search or a view, where a drop would reorder against a list the user
   *  cannot see. */
  reorder?: DragReorder
  /** Whether the categories inside may be reordered — the same rule as the
   *  groups, minus "showing every group". */
  canReorderCategories?: boolean
}

export function CategoryGroupRow({
  group,
  categories,
  balanceMap,
  budgetId,
  month,
  readOnlyGroup = false,
  index,
  reorder,
  canReorderCategories = false,
}: Props) {
  const { formatMoney } = useFormatters()
  const collapsedGroups = useUIStore((s) => s.collapsedGroups)
  const toggleGroup = useUIStore((s) => s.toggleGroupExpanded)
  const selectedCategoryIds = useUIStore((s) => s.selectedCategoryIds)
  const selectGroupCategories = useUIStore((s) => s.selectGroupCategories)
  const budgetRowMode = useUIStore((s) => s.budgetRowMode)
  const anySelected = selectedCategoryIds.size > 0
  const categoryIds = useMemo(() => categories.map((c) => c.id), [categories])
  const allGroupSelected =
    categoryIds.length > 0 && categoryIds.every((id) => selectedCategoryIds.has(id))
  const someGroupSelected = categoryIds.some((id) => selectedCategoryIds.has(id))
  const isExpanded = !collapsedGroups.has(group.id)
  const canEditGroup = !group.is_system && !readOnlyGroup
  // A group the app keeps by key (the Wishlist) can be hidden but not renamed
  // or deleted — the server refuses both; offering them would only surface an error.
  const canRenameOrDelete = canEditGroup && !group.system_key

  const [isRenaming, setIsRenaming] = useState(false)
  const [renameValue, setRenameValue] = useState('')
  const [isAddingCategory, setIsAddingCategory] = useState(false)
  const [newCatName, setNewCatName] = useState('')

  const renameRef = useRef<HTMLInputElement>(null)
  const addCatRef = useRef<HTMLInputElement>(null)

  const updateGroup = useUpdateCategoryGroup(budgetId)
  const archiveGroup = useArchiveCategoryGroup(budgetId)
  const { requestDelete, modal: deleteModal } = useDeleteCategoryFlow(budgetId)
  const createCategory = useCreateCategory(budgetId)
  const { mutate: reorderCategories } = useReorderCategories(budgetId)
  const moveCategory = useCallback(
    (from: number, to: number) =>
      reorderCategories({ groupId: group.id, categoryIds: [...moveItem(categoryIds, from, to)] }),
    [reorderCategories, group.id, categoryIds]
  )
  const categoryDrag = useDragReorder(categories.length, moveCategory)
  const categoriesReorderable = canReorderCategories && categories.length > 1

  // A category dragged out of another group. `wouldMoveTo` is false inside
  // its own group, where the index-based reorder above is the right handler,
  // and false when a GROUP is the thing being dragged.
  const crossGroupDrag = useCategoryDrag()
  const [categoryOver, setCategoryOver] = useState(false)
  const acceptsCategory = crossGroupDrag != null && crossGroupDrag.wouldMoveTo(group.id)
  const isCategoryDropTarget = acceptsCategory && categoryOver

  // `sumBalances`, not a reduce of its own. This summed three times inline
  // with `?? 0`, which differs from the shared rule on exactly one row type:
  // an income row serves null assigned/available, and counting its activity
  // puts income received into a group's spending total. The grid does not
  // draw system groups today (`renderableGroups`), so the two agreed by
  // accident — the kind of agreement that ends the day someone files income
  // outside the Income group.
  const {
    assigned: groupAssigned,
    activity: groupActivity,
    available: groupAvailable,
  } = useMemo(
    () =>
      sumBalances(
        categories
          .map((cat) => balanceMap.get(cat.id))
          .filter((b): b is CategoryBalance => b !== undefined)
      ),
    [categories, balanceMap]
  )

  function startRename() {
    setRenameValue(group.name)
    setIsRenaming(true)
    setTimeout(() => renameRef.current?.select(), 0)
  }

  function commitRename() {
    const name = renameValue.trim()
    if (name && name !== group.name) updateGroup.mutate({ id: group.id, name })
    setIsRenaming(false)
  }

  function handleRenameKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault()
      commitRename()
    }
    if (e.key === 'Escape') setIsRenaming(false)
  }

  function handleArchive() {
    // The archive endpoint, not a PATCH of the flag. Archiving a group takes
    // every envelope under it off the budget (`IN_ARCHIVED_GROUP`), so the
    // plain column write this used to do could strand a whole group's money
    // in one click. The endpoint refuses and names the envelope that stopped
    // it; the mutation surfaces that sentence.
    archiveGroup.mutate({ id: group.id, month })
  }

  function handleDelete() {
    // The modal is the confirmation now. Deleting a group cascades over its
    // categories and returns their money to Ready to Assign, which is more
    // than a two-pixel tick should be able to set off.
    requestDelete({ kind: 'group', id: group.id, name: group.name })
  }

  function startAddCategory() {
    setNewCatName('')
    setIsAddingCategory(true)
    if (!isExpanded) toggleGroup(group.id)
    setTimeout(() => addCatRef.current?.focus(), 50)
  }

  function commitAddCategory() {
    const name = newCatName.trim()
    if (name) createCategory.mutate({ category_group_id: group.id, name })
    setIsAddingCategory(false)
    setNewCatName('')
  }

  function handleAddCatKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault()
      commitAddCategory()
    }
    if (e.key === 'Escape') {
      setIsAddingCategory(false)
      setNewCatName('')
    }
  }

  return (
    <div
      className={`category-group-row ${budgetRowMode === 'dense' ? 'category-group-row--dense' : ''}`}
    >
      <div
        className={
          'category-group-row__header budget-grid drag-handle-host' +
          (reorder?.dragIndex === index ? ' drag-handle-host--dragging' : '') +
          (reorder && reorder.overIndex === index && reorder.dragIndex !== index
            ? ' drag-handle-host--drag-over'
            : '') +
          // A category hovering over this heading lands in this group. Its
          // own class, not the reorder one: that draws a line above the row,
          // which means "insert here" — the wrong promise for a heading.
          (isCategoryDropTarget ? ' category-group-row__header--accepts' : '')
        }
        // Only the handle starts a drag (see DragHandle); the header is where
        // a dragged group lands.
        onDragOver={(e) => {
          // A dragged category may land on a heading even when the groups
          // themselves are not reorderable — they are separate gestures.
          if (acceptsCategory) {
            e.preventDefault()
            setCategoryOver(true)
            return
          }
          if (reorder) {
            e.preventDefault()
            reorder.over(index)
          }
        }}
        onDragLeave={acceptsCategory ? () => setCategoryOver(false) : undefined}
        onDrop={(e) => {
          if (acceptsCategory) {
            e.preventDefault()
            setCategoryOver(false)
            crossGroupDrag.moveTo(group.id)
            reorder?.end()
            return
          }
          if (reorder) {
            e.preventDefault()
            reorder.drop(index)
          }
        }}
      >
        {reorder && (
          <DragHandle
            label={group.name}
            onDragStart={() => reorder.start(index)}
            onDragEnd={reorder.end}
            onMoveUp={index > 0 ? () => reorder.moveBy(index, -1) : undefined}
            onMoveDown={() => reorder.moveBy(index, 1)}
          />
        )}
        <button
          className="category-group-row__toggle budget-grid__rail"
          onClick={() => toggleGroup(group.id)}
          aria-expanded={isExpanded}
          aria-label={isExpanded ? 'Collapse group' : 'Expand group'}
        >
          {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>

        <div
          className={`category-group-row__checkbox budget-grid__gutter ${anySelected ? 'category-group-row__checkbox--visible' : ''}`}
        >
          <input
            type="checkbox"
            checked={allGroupSelected}
            ref={(el) => {
              if (el) el.indeterminate = someGroupSelected && !allGroupSelected
            }}
            onChange={() => selectGroupCategories(categoryIds)}
            onClick={(e) => e.stopPropagation()}
            aria-label={`Select all in ${group.name}`}
          />
        </div>

        {/* Name and actions share ONE grid cell. They were siblings, so the
            buttons took the ASSIGNED column and pushed all three totals a
            column right — see budgetGrid.css. `CategoryRow` has always nested
            its actions inside its name cell; this is that shape. */}
        <div className="category-group-row__title budget-grid__name">
          {isRenaming ? (
            <input
              ref={renameRef}
              className="category-group-row__rename-input"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onBlur={commitRename}
              onKeyDown={handleRenameKey}
            />
          ) : (
            <span
              className="category-group-row__name"
              onDoubleClick={canRenameOrDelete ? startRename : undefined}
            >
              {group.name}
            </span>
          )}

          {!isRenaming && (
            <div className="category-group-row__actions">
              {canRenameOrDelete && (
                <button
                  className="category-group-row__action-btn"
                  onClick={startRename}
                  aria-label={`Rename group ${group.name}`}
                  title="Rename"
                >
                  <Pencil size={12} />
                </button>
              )}
              {canEditGroup && (
                <button
                  className="category-group-row__action-btn"
                  onClick={handleArchive}
                  aria-label={`Archive group ${group.name}`}
                  title="Archive group"
                >
                  <Archive size={12} />
                </button>
              )}
              {canRenameOrDelete && (
                <button
                  className="category-group-row__action-btn category-group-row__action-btn--danger"
                  onClick={handleDelete}
                  aria-label={`Delete group ${group.name}`}
                  title="Delete group"
                >
                  <Trash2 size={12} />
                </button>
              )}
              {!readOnlyGroup && (
                <button
                  className="category-group-row__action-btn"
                  onClick={startAddCategory}
                  aria-label={`Add category to ${group.name}`}
                  title="Add category"
                >
                  <Plus size={12} />
                </button>
              )}
            </div>
          )}
        </div>

        <span className="category-group-row__assigned budget-grid__assigned tabular">
          {formatMoney(groupAssigned)}
        </span>
        <span className="category-group-row__activity budget-grid__activity tabular">
          {formatMoney(groupActivity)}
        </span>
        <span
          className={`category-group-row__available budget-grid__available tabular ${groupAvailable < 0 ? 'negative' : groupAvailable > 0 ? 'positive' : 'zero'}`}
        >
          {formatMoney(groupAvailable)}
        </span>

        {/* Collapsed groups on mobile hide the assigned/activity columns —
            this sub-line keeps the totals visible (desktop: display none) */}
        {!isExpanded && (
          <span className="category-group-row__mobile-summary tabular">
            Assigned {formatMoney(groupAssigned)} · Activity {formatMoney(groupActivity)}
          </span>
        )}
      </div>

      {isExpanded && (
        <div className="category-group-row__categories">
          {categories.map((cat, position) => (
            <CategoryRow
              key={cat.id}
              category={cat}
              balance={balanceMap.get(cat.id)}
              budgetId={budgetId}
              month={month}
              orderedIds={categoryIds}
              index={position}
              reorder={categoriesReorderable ? categoryDrag : undefined}
            />
          ))}
          {isAddingCategory && (
            <div className="category-group-row__add-cat-row budget-grid">
              <div className="budget-grid__rail" />
              <input
                ref={addCatRef}
                className="category-group-row__add-cat-input budget-grid__name--wide"
                value={newCatName}
                onChange={(e) => setNewCatName(e.target.value)}
                onBlur={commitAddCategory}
                onKeyDown={handleAddCatKey}
                placeholder="Category name…"
              />
            </div>
          )}
          {!isAddingCategory && !readOnlyGroup && (
            <button className="category-group-row__add-cat-btn" onClick={startAddCategory}>
              <Plus size={11} /> Add Category
            </button>
          )}
        </div>
      )}
      {deleteModal}
    </div>
  )
}
