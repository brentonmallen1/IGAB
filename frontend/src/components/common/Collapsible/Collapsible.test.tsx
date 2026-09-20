/**
 * A collapsed section's header is the only evidence its rows exist, and the
 * register folds `pending` by default — so a synced card payment sat behind a
 * muted 11px uppercase label that read as a divider, and went unseen for two
 * days while the person hunted the account for it.
 *
 * These pin the state that fixes it: closed *and* non-empty is loud, and every
 * other combination stays chrome.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { Collapsible } from './Collapsible'

const HIDING = 'collapsible__header--hiding'

function header(props: Partial<Parameters<typeof Collapsible>[0]> = {}) {
  render(
    <Collapsible title="Pending" isOpen={false} count={1} onToggle={vi.fn()} {...props}>
      <div>a row</div>
    </Collapsible>
  )
  return screen.getByRole('button')
}

describe('Collapsible', () => {
  it('shouts when it is closed over rows you cannot see', () => {
    expect(header().className).toContain(HIDING)
  })

  it('stays chrome once opened — the rows speak for themselves', () => {
    expect(header({ isOpen: true }).className).not.toContain(HIDING)
  })

  it('stays chrome when closed over nothing', () => {
    // Guards the off-by-one that would band an empty section: `count > 0`,
    // not `count !== undefined`.
    expect(header({ count: 0 }).className).not.toContain(HIDING)
  })

  it('stays chrome when the section keeps no count', () => {
    // No count means nothing to promise is behind it, so there is nothing to
    // shout about — and no chip to carry the accent.
    expect(header({ count: undefined }).className).not.toContain(HIDING)
  })

  it('keeps the count visible either way — it is what says how much is hidden', () => {
    expect(header().textContent).toContain('1')
  })
})
