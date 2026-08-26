import { fireEvent, render } from '@testing-library/react'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import { Combobox } from './Combobox'

const OPTIONS = Array.from({ length: 30 }, (_, i) => ({ id: `o${i}`, label: `Option ${i}` }))
const ROW = 20
const VIEW = 40 // two rows visible

/** jsdom has no layout; give the list a real geometry so the follow-scroll
 *  arithmetic in Combobox has something to act on. */
beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, 'offsetTop', {
    configurable: true,
    get() {
      const idx = (this as HTMLElement).dataset.optionIndex
      return idx == null ? 0 : Number(idx) * ROW
    },
  })
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, get: () => ROW })
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, get: () => VIEW })
})
afterAll(() => {
  for (const k of ['offsetTop', 'offsetHeight', 'clientHeight']) {
    delete (HTMLElement.prototype as unknown as Record<string, unknown>)[k]
  }
})

function setup() {
  const onChange = vi.fn()
  const utils = render(<Combobox value={null} options={OPTIONS} onChange={onChange} autoFocus />)
  const input = utils.container.querySelector('input')!
  const list = document.querySelector<HTMLElement>('.combobox__list')!
  const option = (i: number) => document.querySelector<HTMLElement>(`[data-option-index="${i}"]`)!
  return { ...utils, input, list, option }
}

describe('Combobox highlight scrolling', () => {
  it('follows the highlight for keyboard navigation', () => {
    const { input, list } = setup()
    expect(list.scrollTop).toBe(0)
    for (let i = 0; i < 3; i++) fireEvent.keyDown(input, { key: 'ArrowDown' })
    // highlight 3 sits at 60–80px; the 40px viewport must scroll to show it
    expect(list.scrollTop).toBe(3 * ROW + ROW - VIEW)
  })

  it('never scrolls for a pointer hover — hovering an edge option must not creep the list', () => {
    const { list, option } = setup()
    // an option below the fold, exactly what a pointer at the bottom edge touches
    fireEvent.mouseEnter(option(5))
    expect(list.scrollTop).toBe(0)
    expect(option(5).className).toContain('combobox__option--highlighted')
  })

  it('does not scroll on hover even after keyboard navigation has scrolled it', () => {
    const { input, list, option } = setup()
    for (let i = 0; i < 6; i++) fireEvent.keyDown(input, { key: 'ArrowDown' })
    const scrolled = list.scrollTop
    expect(scrolled).toBeGreaterThan(0)
    fireEvent.mouseEnter(option(1)) // above the fold now
    expect(list.scrollTop).toBe(scrolled)
    fireEvent.keyDown(input, { key: 'ArrowUp' })
    expect(list.scrollTop).not.toBe(scrolled)
  })
})
