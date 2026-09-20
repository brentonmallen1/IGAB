/**
 * The account header stated its working balance twice.
 *
 * Once inside the fold control and once as the `=` term of the equation —
 * same value, same 22px/700, three lines apart, differing only in the casing
 * of the label. It survived because this page had no component test of any
 * kind: a dozen hooks deep, nothing mounted it, and nothing could see that
 * two render sites had converged on one number.
 *
 * So the figure region is its own prop-driven component now, and these hold
 * the rule that replaced the duplication: the working balance appears exactly
 * ONCE, and which spelling you get is the fold.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { AccountBalances, DETAIL_ID } from './AccountBalances'

const money = (n: number) =>
  `${n < 0 ? '-' : ''}$${Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2 })}`

function draw(collapsed: boolean, onToggle = vi.fn()) {
  const { container } = render(
    <AccountBalances
      balance={8243.24}
      clearedBalance={8253.9}
      unclearedBalance={-10.66}
      collapsed={collapsed}
      onToggle={onToggle}
      formatMoney={money}
    />
  )
  return container
}

/** Every rendering of the working balance that a person can actually see. */
const visibleWorking = (container: HTMLElement) => {
  const detail = container.querySelector(`#${DETAIL_ID}`)!
  const hidden = detail.classList.contains('account-page__balances--collapsed')
  return [...container.querySelectorAll('.account-page__balance-value')].filter(
    (el) => el.textContent === '$8,243.24' && !(hidden && detail.contains(el))
  )
}

describe('the working balance is stated once', () => {
  it('folded: once, as the headline', () => {
    const c = draw(true)
    expect(visibleWorking(c)).toHaveLength(1)
    // The parts are hidden when folded. Asserted as the class, not with
    // toBeVisible: jsdom loads no stylesheet, so a class-driven display:none
    // is invisible to it — see themes/overlayBounds.test.ts for the same
    // reason applied to geometry.
    expect(c.querySelector(`#${DETAIL_ID}`)).toHaveClass('account-page__balances--collapsed')
  })

  it('open: once, as the result of the equation', () => {
    const c = draw(false)
    expect(visibleWorking(c)).toHaveLength(1)
    const detail = c.querySelector(`#${DETAIL_ID}`) as HTMLElement
    expect(within(detail).getByText('Cleared')).toBeInTheDocument()
    expect(within(detail).getByText('Uncleared')).toBeInTheDocument()
    // and it is the `=` term, not a second headline above it
    expect(c.querySelector('.account-page__balance-item--working')).toBeTruthy()
  })

  it.each([true, false])('never both (collapsed=%s)', (collapsed) => {
    // The regression this file exists for. If the headline ever renders
    // alongside the equation again, this is the line that fails.
    expect(visibleWorking(draw(collapsed))).toHaveLength(1)
  })
})

describe('the fold control', () => {
  it.each([true, false])('is a triangle in the same place (collapsed=%s)', (collapsed) => {
    const region = draw(collapsed).querySelector('.account-page__balance')!
    expect(region.firstElementChild).toHaveClass('account-page__header-toggle')
  })

  it.each([true, false])(
    'says what it controls, and that target is mounted either way (collapsed=%s)',
    (collapsed) => {
      // aria-controls pointing at an unmounted node is a broken relationship,
      // which is why the detail block is hidden by class rather than removed.
      const c = draw(collapsed)
      const btn = within(c).getByRole('button')
      expect(btn).toHaveAttribute('aria-expanded', String(!collapsed))
      expect(btn).toHaveAttribute('aria-controls', DETAIL_ID)
      expect(c.querySelector(`#${DETAIL_ID}`)).toBeTruthy()
    }
  )

  it('carries the balance when folded, so the target is not a 14px glyph', () => {
    draw(true)
    expect(screen.getByRole('button')).toHaveTextContent('$8,243.24')
  })

  it('toggles', () => {
    const onToggle = vi.fn()
    draw(true, onToggle)
    fireEvent.click(screen.getByRole('button'))
    expect(onToggle).toHaveBeenCalledOnce()
  })
})
