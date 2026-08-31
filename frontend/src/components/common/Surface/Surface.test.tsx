import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Surface } from './Surface'

type IOCallback = (entries: Array<{ isIntersecting: boolean }>) => void

/** Minimal IntersectionObserver double: records the callback so a test can
 *  drive the sentinel in and out of view. */
function installObserver() {
  const instances: Array<{ cb: IOCallback; observed: Element[] }> = []
  class FakeObserver {
    observed: Element[] = []
    constructor(cb: IOCallback) {
      instances.push({ cb, observed: this.observed })
    }
    observe(el: Element) {
      this.observed.push(el)
    }
    disconnect() {}
  }
  vi.stubGlobal('IntersectionObserver', FakeObserver)
  return instances
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Surface', () => {
  it('is raised by default', () => {
    render(<Surface data-testid="s">body</Surface>)
    const el = screen.getByTestId('s')
    expect(el.tagName).toBe('DIV')
    expect(el.className).toBe('surface surface--raised')
  })

  it.each(['raised', 'sunken', 'chrome'] as const)('maps variant %s to one class', (variant) => {
    render(<Surface variant={variant} data-testid="s" />)
    expect(screen.getByTestId('s')).toHaveClass('surface', `surface--${variant}`)
  })

  it('renders the requested element and keeps caller classes', () => {
    render(<Surface as="section" className="settings-section" dashed data-testid="s" />)
    const el = screen.getByTestId('s')
    expect(el.tagName).toBe('SECTION')
    expect(el).toHaveClass('surface', 'surface--raised', 'surface--dashed', 'settings-section')
  })

  it('renders a header only when given a title or header', () => {
    const { rerender } = render(<Surface data-testid="s">body</Surface>)
    expect(screen.getByTestId('s').querySelector('.surface__header')).toBeNull()

    rerender(
      <Surface data-testid="s" title="Backups" actions={<button>Run</button>}>
        body
      </Surface>
    )
    const header = screen.getByTestId('s').querySelector('.surface__header')
    expect(header).not.toBeNull()
    expect(header!.querySelector('.surface__title')).toHaveClass('section-label')
    expect(header!.querySelector('.surface__actions button')).toHaveTextContent('Run')

    rerender(
      <Surface data-testid="s" header={<h2>Paydown</h2>}>
        body
      </Surface>
    )
    expect(screen.getByTestId('s').querySelector('.surface__header h2')).toHaveTextContent(
      'Paydown'
    )
    expect(screen.getByTestId('s').querySelector('.surface__title')).toBeNull()
  })

  it('does not become sticky without the flag', () => {
    render(<Surface variant="chrome" data-testid="s" />)
    expect(screen.getByTestId('s')).not.toHaveClass('surface--sticky')
  })

  it('gains the stuck class only while its sentinel is scrolled out', () => {
    const observers = installObserver()
    render(
      <div>
        <Surface variant="chrome" sticky data-testid="s">
          toolbar
        </Surface>
      </div>
    )
    const el = screen.getByTestId('s')
    expect(el).toHaveClass('surface--sticky')
    expect(el).not.toHaveClass('surface--stuck')

    // the sentinel is inserted in flow immediately before the bar
    const sentinel = el.previousElementSibling
    expect(sentinel).toHaveClass('surface__sentinel')
    expect(observers).toHaveLength(1)
    expect(observers[0].observed).toEqual([sentinel])

    act(() => observers[0].cb([{ isIntersecting: false }]))
    expect(el).toHaveClass('surface--stuck')

    act(() => observers[0].cb([{ isIntersecting: true }]))
    expect(el).not.toHaveClass('surface--stuck')
  })

  it('is never stuck where IntersectionObserver is unavailable', () => {
    vi.stubGlobal('IntersectionObserver', undefined)
    render(<Surface variant="chrome" sticky data-testid="s" />)
    expect(screen.getByTestId('s')).toHaveClass('surface--sticky')
    expect(screen.getByTestId('s')).not.toHaveClass('surface--stuck')
  })
})
