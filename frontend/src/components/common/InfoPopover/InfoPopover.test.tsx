/**
 * The panel is portalled to <body>, which is what lets it escape the app
 * shell's `overflow: hidden` instead of being clipped at the main column's
 * edge — where it read as sliding under the sidebar.
 *
 * Portalling costs two things that only a test will keep honest: the trigger's
 * wrapper no longer contains the panel, so the outside-click handler has to
 * check both nodes or every click inside the explanation closes it; and the
 * panel is positioned from the trigger's rect rather than by CSS, so which way
 * it opens is now JavaScript that can regress silently.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { InfoPopover, InfoSection } from './InfoPopover'

const TRIGGER_LEFT = 120

function mockTriggerRect(left = TRIGGER_LEFT) {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    left,
    right: left + 22,
    top: 40,
    bottom: 62,
    width: 22,
    height: 22,
    x: left,
    y: 40,
    toJSON: () => ({}),
  } as DOMRect)
}

function open(width?: number) {
  render(
    <InfoPopover title="Searching transactions" label="How to search" width={width}>
      <p>Type words to search payees and memos.</p>
    </InfoPopover>
  )
  fireEvent.click(screen.getByRole('button', { name: 'How to search' }))
  return screen.getByRole('dialog', { name: 'Searching transactions' })
}

afterEach(() => vi.restoreAllMocks())

describe('InfoPopover', () => {
  it('renders the panel outside the trigger, at the document body', () => {
    mockTriggerRect()
    const panel = open()
    expect(panel.closest('.info-pop')).toBeNull()
    expect(panel.parentElement).toBe(document.body)
  })

  it('opens rightward from the trigger, not leftward across the page', () => {
    mockTriggerRect()
    const panel = open()
    // Left edge tracks the trigger's left edge. Anchoring the panel's RIGHT
    // edge here instead is what put it over the sidebar.
    expect(panel.style.left).toBe(`${TRIGGER_LEFT}px`)
    expect(panel.style.right).toBe('')
  })

  it('clamps a wide panel back on screen near the right edge', () => {
    mockTriggerRect(window.innerWidth - 60)
    const panel = open(380)
    const left = Number.parseInt(panel.style.left, 10)
    expect(left + 380).toBeLessThanOrEqual(window.innerWidth)
    expect(left).toBeGreaterThanOrEqual(0)
  })

  it('stays open when the click lands inside the portalled panel', () => {
    mockTriggerRect()
    const panel = open()
    fireEvent.mouseDown(screen.getByText('Type words to search payees and memos.'))
    expect(panel).toBeInTheDocument()
  })

  it('closes on a click outside it', () => {
    mockTriggerRect()
    open()
    fireEvent.mouseDown(document.body)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('closes on Escape without letting the surface behind it see the key', () => {
    mockTriggerRect()
    open()
    const outer = vi.fn()
    document.addEventListener('keydown', outer)
    fireEvent.keyDown(document, { key: 'Escape' })
    document.removeEventListener('keydown', outer)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(outer).not.toHaveBeenCalled()
  })
})

/**
 * Separation has to survive as structure, not just as CSS. A section that
 * renders its title as a plain <span> looks identical and is invisible to a
 * screen reader, and prose that drifts back out of its section loses the gap
 * that made the panel readable.
 */
describe('InfoSection', () => {
  function openWithSections() {
    render(
      <InfoPopover title="Searching transactions" label="How to search">
        <p>Lede paragraph.</p>
        <InfoSection title="Filters">
          <p>A keyword and a colon.</p>
        </InfoSection>
        <InfoSection title="Dates">
          <p>Any span you mean.</p>
        </InfoSection>
      </InfoPopover>
    )
    fireEvent.click(screen.getByRole('button', { name: 'How to search' }))
  }

  it('exposes each topic as a heading, not just styled text', () => {
    mockTriggerRect()
    openWithSections()
    expect(screen.getAllByRole('heading').map((h) => h.textContent)).toEqual(['Filters', 'Dates'])
  })

  it('keeps a section title with the content it introduces', () => {
    mockTriggerRect()
    openWithSections()
    const section = screen.getByRole('heading', { name: 'Filters' }).parentElement
    expect(section).toHaveClass('info-pop__section')
    expect(section).toHaveTextContent('A keyword and a colon.')
    // The lede belongs to the body, not to the first section.
    expect(section).not.toHaveTextContent('Lede paragraph.')
  })
})
