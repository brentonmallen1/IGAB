import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BottomSheet } from './BottomSheet'
import { scrollLockDepth } from '../../../utils/scrollLock'

describe('BottomSheet dismissal affordances', () => {
  beforeEach(() => {
    // jsdom has no matchMedia; reduced-motion false keeps the exit path live.
    window.matchMedia ??= (() => ({ matches: false })) as unknown as typeof window.matchMedia
  })

  it('renders a close button on a full-height sheet', () => {
    // The backdrop of a full-height sheet is a sliver under the notch and an
    // installed PWA has no back gesture, so this is the only guaranteed exit.
    render(
      <BottomSheet open onClose={() => {}} title="Add Transaction" height="full">
        body
      </BottomSheet>
    )
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument()
  })

  it('uses its own label for the close button when given one', () => {
    render(
      <BottomSheet open onClose={() => {}} title="Add" height="full" closeLabel="Cancel">
        body
      </BottomSheet>
    )
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
  })

  it('offers a drag handle instead of a close button on a short sheet', () => {
    const { container } = render(
      <BottomSheet open onClose={() => {}} title="Move money" height="auto">
        body
      </BottomSheet>
    )
    expect(screen.queryByRole('button', { name: 'Close' })).not.toBeInTheDocument()
    expect(container.ownerDocument.querySelector('.bottom-sheet__handle')).not.toBeNull()
  })

  it('closes on the close button', () => {
    const onClose = vi.fn()
    render(
      <BottomSheet open onClose={onClose} title="Add" height="full">
        body
      </BottomSheet>
    )
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('honours a canClose veto on every dismissal path', () => {
    const onClose = vi.fn()
    const canClose = vi.fn(() => false)
    render(
      <BottomSheet open onClose={onClose} canClose={canClose} title="Add" height="full">
        body
      </BottomSheet>
    )

    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    fireEvent.keyDown(document, { key: 'Escape' })
    const backdrop = document.querySelector('.bottom-sheet-backdrop')!
    fireEvent.click(backdrop)

    expect(canClose).toHaveBeenCalledTimes(3)
    expect(onClose).not.toHaveBeenCalled()
  })

  it('closes when the veto allows it', () => {
    const onClose = vi.fn()
    render(
      <BottomSheet open onClose={onClose} canClose={() => true} title="Add" height="full">
        body
      </BottomSheet>
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('routes Escape to the topmost sheet only', () => {
    const outer = vi.fn()
    const inner = vi.fn()
    render(
      <>
        <BottomSheet open onClose={outer} title="Outer" height="full">
          outer
        </BottomSheet>
        <BottomSheet open onClose={inner} title="Inner" height="auto">
          inner
        </BottomSheet>
      </>
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(inner).toHaveBeenCalledOnce()
    expect(outer).not.toHaveBeenCalled()
  })

  it('renders nothing and holds no scroll lock while closed', () => {
    const before = scrollLockDepth()
    const { container } = render(
      <BottomSheet open={false} onClose={() => {}} title="Add" height="full">
        body
      </BottomSheet>
    )
    expect(container).toBeEmptyDOMElement()
    expect(document.querySelector('.bottom-sheet')).toBeNull()
    expect(scrollLockDepth()).toBe(before)
  })

  it('releases the scroll lock when it unmounts', () => {
    const before = scrollLockDepth()
    const { unmount } = render(
      <BottomSheet open onClose={() => {}} title="Add" height="full">
        body
      </BottomSheet>
    )
    expect(scrollLockDepth()).toBe(before + 1)
    unmount()
    expect(scrollLockDepth()).toBe(before)
  })
})
