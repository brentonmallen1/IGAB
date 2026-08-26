import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Tooltip } from './Tooltip'
import { TOOLTIP_DELAY_MS } from './tooltipDelay'

describe('Tooltip delay', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  function host() {
    render(
      <Tooltip content="What this glyph means">
        <span>glyph</span>
      </Tooltip>
    )
    return screen.getByText('glyph').parentElement!
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
})
