import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { act, render, screen, fireEvent } from '@testing-library/react'
import { useState } from 'react'
import { useHistoryDismissable } from './useHistoryDismissable'

const sheetKey = () => (window.history.state as { igabSheet?: string } | null)?.igabSheet

/** history.back() is deferred a tick and popstate is queued after it. */
const settle = () => act(() => new Promise((resolve) => setTimeout(resolve, 30)))

function Sheet({ name, open, onClose }: { name: string; open: boolean; onClose: () => void }) {
  useHistoryDismissable(open, onClose, name)
  return open ? <div role="dialog" aria-label={name} /> : null
}

/** Two sheets whose open flags live together, so one click can hand off between them. */
function Handoff({ initial }: { initial: 'first' | 'none' }) {
  const [first, setFirst] = useState(initial === 'first')
  const [second, setSecond] = useState(false)
  return (
    <>
      <button onClick={() => setFirst(true)}>open first</button>
      <button onClick={() => setFirst(false)}>close first</button>
      <button
        onClick={() => {
          setFirst(false)
          setSecond(true)
        }}
      >
        hand off
      </button>
      <button onClick={() => setSecond(false)}>close second</button>
      <Sheet name="first" open={first} onClose={() => setFirst(false)} />
      <Sheet name="second" open={second} onClose={() => setSecond(false)} />
    </>
  )
}

describe('useHistoryDismissable', () => {
  beforeEach(async () => {
    // A pending back() from a previous test would land in this one — drain it.
    await settle()
    window.history.replaceState(null, '', '/')
  })
  afterEach(async () => {
    await settle()
    window.history.replaceState(null, '', '/')
  })

  it('pushes an entry on open and consumes it on a UI close', async () => {
    const base = window.history.length
    render(<Handoff initial="none" />)
    fireEvent.click(screen.getByRole('button', { name: 'open first' }))
    expect(sheetKey()).toBe('first')
    expect(window.history.length).toBe(base + 1)

    fireEvent.click(screen.getByRole('button', { name: 'close first' }))
    await settle()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(sheetKey()).toBeUndefined()
  })

  it('closes the sheet whose entry a back gesture pops', async () => {
    render(<Handoff initial="first" />)
    expect(sheetKey()).toBe('first')
    await act(async () => {
      window.history.back()
    })
    await settle()
    expect(screen.queryByRole('dialog', { name: 'first' })).toBeNull()
  })

  it('keeps the second sheet open when one sheet closes and another opens in the same act', async () => {
    // The More sheet's "Ask about your budget" closed More and opened the
    // assistant in one click. More's cleanup scheduled history.back() for its
    // entry; the assistant pushed its own on top; the deferred back() then
    // popped the assistant's entry, and its popstate handler — seeing More's
    // state, not its own — closed it again. The chat flashed and vanished.
    render(<Handoff initial="first" />)
    const withFirst = window.history.length

    fireEvent.click(screen.getByRole('button', { name: 'hand off' }))
    await settle()

    expect(screen.queryByRole('dialog', { name: 'first' })).toBeNull()
    expect(screen.getByRole('dialog', { name: 'second' })).toBeInTheDocument()
    expect(sheetKey()).toBe('second')
    // The handoff reuses the closing sheet's entry: the stack neither grows
    // nor loses the entry a back gesture needs.
    expect(window.history.length).toBe(withFirst)

    // And the second sheet is still dismissable by the back gesture.
    await act(async () => {
      window.history.back()
    })
    await settle()
    expect(screen.queryByRole('dialog', { name: 'second' })).toBeNull()
  })

  it('a UI close after a handoff consumes the handed-off entry', async () => {
    render(<Handoff initial="first" />)
    fireEvent.click(screen.getByRole('button', { name: 'hand off' }))
    await settle()
    fireEvent.click(screen.getByRole('button', { name: 'close second' }))
    await settle()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(sheetKey()).toBeUndefined()
  })
})
