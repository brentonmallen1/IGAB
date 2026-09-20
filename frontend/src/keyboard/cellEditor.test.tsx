/**
 * The reported bug, by name: assign money to an envelope, press ⌘Z, nothing
 * happens.
 *
 * Nothing was wrong with the recording — the change row was there, live, at
 * the head of the log. Committing an assignment with Enter opens the NEXT
 * row's amount box, so focus was inside an `<input>` when the user reached
 * for ⌘Z, and the global-shortcut guard refuses to fire while an input has
 * focus. The keystroke went to the browser's text-undo for a box the user
 * had never typed in.
 *
 * So: a cell editor lets undo/redo through (and nothing else — typing in an
 * amount box must not still trip the month-nav keys), and the undo closes it
 * first so its stale draft cannot be committed back over the undone figure.
 */
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { CELL_EDITOR_PROPS, cancelCellEdit, isCellEditor } from './cellEditor'
import { useShortcut } from '../hooks/useShortcut'

function Harness({
  undo,
  monthNext,
  cell = true,
}: {
  undo: () => void
  monthNext: () => void
  cell?: boolean
}) {
  useShortcut('mod+z', undo, { allowInCellEditors: true })
  useShortcut(']', monthNext)
  return <input aria-label="Assigned" {...(cell ? CELL_EDITOR_PROPS : {})} />
}

describe('cell editors and the global undo', () => {
  it('lets ⌘Z through while the amount box has focus', async () => {
    const undo = vi.fn()
    render(<Harness undo={undo} monthNext={vi.fn()} />)
    await userEvent.click(screen.getByLabelText('Assigned'))

    await userEvent.keyboard('{Meta>}z{/Meta}')

    expect(undo).toHaveBeenCalledOnce()
  })

  it('still swallows ⌘Z in an ordinary text field', async () => {
    const undo = vi.fn()
    render(<Harness undo={undo} monthNext={vi.fn()} cell={false} />)
    await userEvent.click(screen.getByLabelText('Assigned'))

    await userEvent.keyboard('{Meta>}z{/Meta}')

    expect(undo).not.toHaveBeenCalled()
  })

  it('does not widen the hole: ordinary shortcuts stay blocked in a cell', async () => {
    const monthNext = vi.fn()
    render(<Harness undo={vi.fn()} monthNext={monthNext} />)
    await userEvent.click(screen.getByLabelText('Assigned'))

    await userEvent.keyboard(']')

    expect(monthNext).not.toHaveBeenCalled()
  })
})

/** A cell editor of the shape all three real ones share: Escape cancels,
 *  blur commits. Undo must take the first door, never the second. */
function EditableCell({ onCommit }: { onCommit: (value: string) => void }) {
  const [editing, setEditing] = useState(true)
  const [value, setValue] = useState('42')
  if (!editing) return <button>42</button>
  return (
    <input
      autoFocus
      aria-label="Assigned"
      {...CELL_EDITOR_PROPS}
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Escape') setEditing(false)
      }}
      onBlur={() => onCommit(value)}
    />
  )
}

describe('cancelCellEdit', () => {
  it('closes the open box without committing its draft', () => {
    const onCommit = vi.fn()
    render(<EditableCell onCommit={onCommit} />)

    let closed = false
    act(() => {
      closed = cancelCellEdit()
    })

    expect(closed).toBe(true)

    expect(screen.getByRole('button')).toBeInTheDocument()
    expect(onCommit).not.toHaveBeenCalled()
  })

  it('reports nothing to close when focus is elsewhere', () => {
    render(<input aria-label="Memo" />)
    screen.getByLabelText('Memo').focus()

    expect(cancelCellEdit()).toBe(false)
    expect(isCellEditor(document.activeElement)).toBe(false)
  })
})
