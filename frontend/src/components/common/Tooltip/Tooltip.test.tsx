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
})
