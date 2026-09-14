/**
 * The Overview's Means trend card and its dialog. The trend's arithmetic is
 * `livingMeans.test.ts`; these pin what a reader sees and can reach.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { useAppStore } from '../../stores/appStore'
import { PRIVACY_MASK } from '../../utils/money'
import type { MeansMonth } from '../../types'
import { MeansTrendCard } from './MeansTrendCard'

const m = (month: string, income: number, outflows: number): MeansMonth => ({
  month,
  income,
  outflows,
})

/** Six months, invented and round. The three before: 15,000 in, 14,100 out —
 *  6% kept. The last three: 15,000 in, 13,350 out — 11% kept. One of them,
 *  a yearly insurance bill, ran over on its own. */
const SIX = [
  m('2026-01-01', 5000, 4700),
  m('2026-02-01', 5000, 4700),
  m('2026-03-01', 5000, 4700),
  m('2026-04-01', 5000, 4180),
  m('2026-05-01', 5000, 5200),
  m('2026-06-01', 5000, 3970),
]

function card(): { value: string; sub: string } {
  const el = document.querySelector('.metric-card')
  return {
    value: el?.querySelector('.metric-card__value')?.textContent ?? '',
    sub: el?.querySelector('.metric-card__sub')?.textContent ?? '',
  }
}

beforeEach(async () => {
  // A dialog opened in more than one test leaves a deferred history.back()
  // that closes the next test's dialog; drain it first.
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
})

afterEach(() => {
  useAppStore.setState({ privacyMode: false })
})

describe('MeansTrendCard', () => {
  it('reads the pooled three months, the direction and the count', () => {
    render(<MeansTrendCard months={SIX} />)

    expect(card()).toEqual({ value: 'Keeping 11%', sub: '3-month average · up from 6%' })
    expect(screen.getByText('Keeping 11%')).toHaveClass('means-standing--below')
    // January to April and June are below; May is at (4% over).
    expect(
      screen.getByRole('img', { name: '5 of the last 6 months below your means' })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Means trend Keeping 11%. Show the months' })
    ).toBeInTheDocument()
  })

  it('reads a short stretch, with a signed prior', () => {
    render(
      <MeansTrendCard
        months={[
          m('2026-01-01', 5000, 5500),
          m('2026-02-01', 5000, 5500),
          m('2026-03-01', 5000, 5500),
          m('2026-04-01', 5000, 5200),
          m('2026-05-01', 5000, 5200),
          m('2026-06-01', 5000, 5200),
        ]}
      />
    )
    expect(card()).toEqual({ value: 'Short 4%', sub: '3-month average · up from −10%' })
    expect(screen.getByText('Short 4%')).toHaveClass('means-standing--at')
  })

  it('has only the average when there is nothing before it', () => {
    render(<MeansTrendCard months={SIX.slice(3)} />)
    expect(card().sub).toBe('3-month average')
  })

  it('needs a month with income before it reads anything', () => {
    render(<MeansTrendCard months={[m('2026-05-01', 0, 400), m('2026-06-01', 0, 0)]} />)
    expect(card()).toEqual({ value: '—', sub: 'Needs a month with income' })
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  it('opens the months from the keyboard, as a table beside the chart', async () => {
    render(<MeansTrendCard months={[...SIX.slice(0, 5), m('2026-06-01', 0, 250)]} />)
    await userEvent.tab()
    expect(screen.getByRole('button', { name: /^Means trend/ })).toHaveFocus()
    await userEvent.keyboard('{Enter}')

    const dialog = await screen.findByRole('dialog', { name: 'Means trend' })
    const rows = [...dialog.querySelectorAll('.report-detail__row')].map((li) => li.textContent)
    expect(rows).toHaveLength(6)
    expect(rows[3]).toBe('April 2026$5,000.00 in · $4,180.00 out$820.00 left over17% under income')
    expect(rows[4]).toBe('May 2026$5,000.00 in · $5,200.00 out$200.00 short4% over income')
    expect(rows[5]).toBe('June 2026$0.00 in · $250.00 out$250.00 shortNo income')
    expect(within(dialog).getByText(/Money moved into savings is not an outflow/)).toBeVisible()
    expect(dialog).toHaveTextContent('within 5% of income either side')
    expect(dialog).toHaveTextContent('4 of the last 6 months below your means.')
  })

  it('masks every amount in privacy mode, and keeps the percentages', async () => {
    useAppStore.setState({ privacyMode: true })
    render(<MeansTrendCard months={SIX} />)
    expect(card().value).toBe('Keeping 11%')

    await userEvent.click(screen.getByRole('button', { name: /^Means trend/ }))
    const dialog = await screen.findByRole('dialog', { name: 'Means trend' })
    expect(dialog.textContent).not.toMatch(/\$\d/)
    expect(dialog.textContent).toContain(PRIVACY_MASK)
    expect(dialog).toHaveTextContent('17% under income')
  })
})
