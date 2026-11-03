import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Tooltip } from './Tooltip'
import { TOOLTIP_DELAY_MS, TOOLTIP_WARM_WINDOW_MS, resetTooltipWarmth } from './tooltipDelay'

describe('Tooltip delay', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    resetTooltipWarmth()
  })
  afterEach(() => vi.useRealTimers())

  function host(label = 'glyph', content = 'What this glyph means') {
    render(
      <Tooltip content={content}>
        <span>{label}</span>
      </Tooltip>
    )
    return screen.getByText(label).parentElement!
  }

  it('waits the one shared delay, then shows', () => {
    const el = host()
    fireEvent.mouseEnter(el)
    act(() => vi.advanceTimersByTime(TOOLTIP_DELAY_MS - 1))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    act(() => vi.advanceTimersByTime(1))
    expect(screen.getByRole('tooltip')).toHaveTextContent('What this glyph means')
  })

  it('never shows for a pointer that just passes through', () => {
    const el = host()
    fireEvent.mouseEnter(el)
    act(() => vi.advanceTimersByTime(TOOLTIP_DELAY_MS / 2))
    fireEvent.mouseLeave(el)
    act(() => vi.advanceTimersByTime(TOOLTIP_DELAY_MS * 2))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('shows on keyboard focus too', () => {
    const el = host()
    fireEvent.focus(el)
    act(() => vi.advanceTimersByTime(TOOLTIP_DELAY_MS))
    expect(screen.getByRole('tooltip')).toBeInTheDocument()
    fireEvent.blur(el)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('opens the next tooltip at once when moving straight from one to another', () => {
    const first = host('first', 'First')
    const second = host('second', 'Second')
    fireEvent.mouseEnter(first)
    act(() => vi.advanceTimersByTime(TOOLTIP_DELAY_MS))
    expect(screen.getByRole('tooltip')).toHaveTextContent('First')
    fireEvent.mouseLeave(first)

    fireEvent.mouseEnter(second)
    act(() => vi.advanceTimersByTime(0))
    expect(screen.getByRole('tooltip')).toHaveTextContent('Second')
  })

  it('goes cold again after the warm window passes', () => {
    const first = host('first', 'First')
    const second = host('second', 'Second')
    fireEvent.mouseEnter(first)
    act(() => vi.advanceTimersByTime(TOOLTIP_DELAY_MS))
    fireEvent.mouseLeave(first)
    act(() => vi.advanceTimersByTime(TOOLTIP_WARM_WINDOW_MS + 1))

    fireEvent.mouseEnter(second)
    act(() => vi.advanceTimersByTime(TOOLTIP_DELAY_MS - 1))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    act(() => vi.advanceTimersByTime(1))
    expect(screen.getByRole('tooltip')).toHaveTextContent('Second')
  })

  it('closes on a press and stays closed while the pointer stays put', () => {
    // The approve glyph: clicking it opened the menu under a tooltip that
    // kept covering it, and the click's own focus would have reopened it.
    const el = host()
    fireEvent.mouseEnter(el)
    act(() => vi.advanceTimersByTime(TOOLTIP_DELAY_MS))
    expect(screen.getByRole('tooltip')).toBeInTheDocument()
    fireEvent.pointerDown(el)
    fireEvent.focus(el)
    act(() => vi.advanceTimersByTime(TOOLTIP_DELAY_MS * 2))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()

    fireEvent.mouseLeave(el)
    act(() => vi.advanceTimersByTime(TOOLTIP_WARM_WINDOW_MS + 1))
    fireEvent.mouseEnter(el)
    act(() => vi.advanceTimersByTime(TOOLTIP_DELAY_MS))
    expect(screen.getByRole('tooltip')).toBeInTheDocument()
  })

  it('never shows for a tap', () => {
    // A phone tap: pointerdown, then an emulated mouseenter and a focus, and
    // no mouseleave until the next tap lands elsewhere. The tooltip used to
    // open and hang over the editor the tap navigated to.
    const el = host()
    fireEvent.pointerDown(el)
    fireEvent.mouseEnter(el)
    fireEvent.focus(el)
    act(() => vi.advanceTimersByTime(TOOLTIP_DELAY_MS * 2))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('shows on keyboard focus after an earlier press has blurred away', () => {
    const el = host()
    fireEvent.pointerDown(el)
    fireEvent.focus(el)
    fireEvent.blur(el)
    fireEvent.focus(el)
    act(() => vi.advanceTimersByTime(TOOLTIP_DELAY_MS))
    expect(screen.getByRole('tooltip')).toBeInTheDocument()
  })
})
