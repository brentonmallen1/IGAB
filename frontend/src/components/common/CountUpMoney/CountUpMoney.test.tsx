import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { COUNT_UP_MS } from '../../../utils/countUp'

const state = vi.hoisted(() => ({ privacyMode: false, reducedMotion: false }))

vi.mock('../../../stores/appStore', () => ({
  useAppStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ privacyMode: state.privacyMode }),
}))
vi.mock('../../../utils/motion', () => ({ prefersReducedMotion: () => state.reducedMotion }))

import { CountUpMoney } from './CountUpMoney'

/** A hand-cranked clock: frames run only when the test says so. */
let now = 0
let queued: FrameRequestCallback[] = []
function advance(ms: number) {
  now += ms
  const run = queued
  queued = []
  act(() => run.forEach((cb) => cb(now)))
}

const shown = (el: HTMLElement) => el.querySelector('[aria-hidden="true"]')!.textContent
const announced = (el: HTMLElement) => el.querySelector('.sr-only')!.textContent

beforeEach(() => {
  state.privacyMode = false
  state.reducedMotion = false
  now = 0
  queued = []
  vi.spyOn(performance, 'now').mockImplementation(() => now)
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => {
    queued.push(cb)
    return queued.length
  })
  vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {})
})

afterEach(() => vi.restoreAllMocks())

describe('CountUpMoney', () => {
  it('counts from the old figure to the new one', () => {
    const { container } = render(<CountUpMoney from={240} to={198} />)
    expect(shown(container)).toBe('$240.00')
    advance(COUNT_UP_MS / 2)
    const mid = shown(container)
    expect(mid).not.toBe('$240.00')
    expect(mid).not.toBe('$198.00')
    advance(COUNT_UP_MS / 2)
    expect(shown(container)).toBe('$198.00')
    // Finished: no frame is left asking for more.
    expect(queued).toHaveLength(0)
  })

  it('announces only the final figure', () => {
    const { container } = render(<CountUpMoney from={240} to={198} />)
    expect(announced(container)).toBe('$198.00')
  })

  it('shows the final figure immediately under reduced motion', () => {
    state.reducedMotion = true
    const { container } = render(<CountUpMoney from={240} to={198} />)
    expect(shown(container)).toBe('$198.00')
    expect(window.requestAnimationFrame).not.toHaveBeenCalled()
  })

  it('never animates masked digits in privacy mode', () => {
    state.privacyMode = true
    const { container } = render(<CountUpMoney from={240} to={-22} />)
    expect(shown(container)).toBe('$••••')
    expect(announced(container)).toBe('$••••')
    expect(window.requestAnimationFrame).not.toHaveBeenCalled()
  })

  it('restarts from the new start when handed new figures', () => {
    const { container, rerender } = render(<CountUpMoney from={240} to={198} />)
    advance(COUNT_UP_MS)
    expect(shown(container)).toBe('$198.00')
    rerender(<CountUpMoney from={198} to={150} />)
    // Not a flash of $150.00 from the previous count's finished clock.
    expect(shown(container)).toBe('$198.00')
    advance(COUNT_UP_MS)
    expect(shown(container)).toBe('$150.00')
  })
})
