import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CategoryDragProvider, useCategoryDrag } from './CategoryDragContext'
import { CategoryRow } from '../CategoryRow/CategoryRow'
import { useDragReorder } from '../../../hooks/useDragReorder'
import { makeCategory } from '../../../test-utils/factories'
import type { Category } from '../../../types'

/**
 * Dragging a category into another group used to do nothing at all — no
 * error, no request, no movement. Reordering is index-based with one
 * `useDragReorder` per group, so a row dragged out of Bills and dropped in
 * Fun called *Fun's* `drop(index)`, whose `dragIndex` was still null because
 * the drag had begun in Bills' instance. `useDragReorder` then correctly did
 * nothing: a drop target is an integer, and no integer can say "this category,
 * from over there".
 *
 * That silence is why this test mounts the real rows and fires real drag
 * events rather than testing the context's api directly. The defect was never
 * in the arithmetic; it was in what the wiring could express.
 */

const updateCategory = vi.fn()
const reorderWithinGroup = vi.fn()

vi.mock('../../../api/categories', () => ({
  useUpdateCategory: () => ({ mutate: updateCategory, mutateAsync: vi.fn() }),
}))
vi.mock('../../../api/budgets', () => ({
  useBudgets: () => ({ data: [] }),
  useSetAssignment: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../../../api/targets', () => ({ useTarget: () => ({ data: null }) }))

/**
 * Real CategoryRows sharing one index-based reorder, exactly as
 * CategoryGroupRow wires them. The heading is a stand-in — mounting the real
 * one would drag in the rename, add-category and delete flows for no extra
 * coverage — and it calls the same two context functions the real header
 * does, `wouldMoveTo` then `moveTo`, which is where the rule lives.
 */
function Group({ id, categories }: { id: string; categories: Category[] }) {
  const reorder = useDragReorder(categories.length, (from, to) => reorderWithinGroup(id, from, to))
  const crossGroup = useCategoryDrag()
  const accepts = crossGroup != null && crossGroup.wouldMoveTo(id)
  return (
    <div data-testid={`group-${id}`}>
      <div
        data-testid={`heading-${id}`}
        data-accepts={accepts || undefined}
        onDragOver={(e) => accepts && e.preventDefault()}
        onDrop={() => accepts && crossGroup.moveTo(id)}
      >
        {id}
      </div>
      {categories.map((cat, index) => (
        <CategoryRow
          key={cat.id}
          category={cat}
          balance={undefined}
          budgetId="b1"
          month="2026-08-01"
          index={index}
          reorder={reorder}
        />
      ))}
    </div>
  )
}

const bills = [
  makeCategory({ id: 'rent', name: 'Rent', category_group_id: 'bills' }),
  makeCategory({ id: 'power', name: 'Power', category_group_id: 'bills' }),
]
const fun = [makeCategory({ id: 'dining', name: 'Dining', category_group_id: 'fun' })]

function mount() {
  render(
    <CategoryDragProvider budgetId="b1">
      <Group id="bills" categories={bills} />
      <Group id="fun" categories={fun} />
    </CategoryDragProvider>
  )
}

/** The row element that owns the drop, found from its handle. */
function rowFor(name: string) {
  const handle = screen.getByLabelText(`Reorder ${name}. Use the arrow keys to move it.`)
  const row = handle.closest('.category-row')
  if (!row) throw new Error(`no row for ${name}`)
  return { handle, row }
}

function dragOnto(from: string, to: string) {
  const source = rowFor(from)
  const target = rowFor(to)
  fireEvent.dragStart(source.handle)
  fireEvent.dragOver(target.row)
  fireEvent.drop(target.row)
}

beforeEach(() => {
  updateCategory.mockClear()
  reorderWithinGroup.mockClear()
})

describe('dragging a category between groups', () => {
  it('moves it, in one request', () => {
    mount()
    dragOnto('Rent', 'Dining')

    expect(updateCategory).toHaveBeenCalledTimes(1)
    expect(updateCategory).toHaveBeenCalledWith({ id: 'rent', category_group_id: 'fun' })
  })

  it('sends no sort_order, so the move is one undoable step', () => {
    // Landing it at the dropped-on index would need a second request to
    // renumber the target group, and ⌘Z would then undo half a move.
    // Categories sort by (sort_order, name), so sharing a neighbour's
    // sort_order is not a position — it is a tie broken alphabetically.
    mount()
    dragOnto('Rent', 'Dining')

    expect(updateCategory.mock.calls[0][0]).not.toHaveProperty('sort_order')
  })

  it('leaves a drop inside the same group to the group, as a reorder', () => {
    mount()
    dragOnto('Rent', 'Power')

    expect(updateCategory).not.toHaveBeenCalled()
    expect(reorderWithinGroup).toHaveBeenCalledWith('bills', 0, 1)
  })

  it('does nothing when a row is dropped on itself', () => {
    mount()
    const { handle, row } = rowFor('Rent')
    fireEvent.dragStart(handle)
    fireEvent.drop(row)

    expect(updateCategory).not.toHaveBeenCalled()
    expect(reorderWithinGroup).not.toHaveBeenCalled()
  })

  it('accepts a drop on another group heading', () => {
    // The obvious gesture for "put this in that group", and the one that
    // works when the target group is collapsed or empty — there is no row to
    // aim at then.
    mount()
    fireEvent.dragStart(rowFor('Rent').handle)
    fireEvent.drop(screen.getByTestId('heading-fun'))

    expect(updateCategory).toHaveBeenCalledWith({ id: 'rent', category_group_id: 'fun' })
  })

  it('lights only the headings that would take the category', () => {
    mount()
    fireEvent.dragStart(rowFor('Rent').handle)

    expect(screen.getByTestId('heading-fun').dataset.accepts).toBe('true')
    // Not its own group: a drop back there is a reorder, and the group's
    // index-based drag already owns it.
    expect(screen.getByTestId('heading-bills').dataset.accepts).toBeUndefined()
  })

  it('forgets the drag once it ends, so the next drop is not a stale move', () => {
    mount()
    const source = rowFor('Rent')
    fireEvent.dragStart(source.handle)
    fireEvent.dragEnd(source.handle)
    fireEvent.drop(rowFor('Dining').row)

    expect(updateCategory).not.toHaveBeenCalled()
  })
})
