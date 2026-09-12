/**
 * The Overview's means card and its dialog. The verdict's arithmetic is
 * `livingMeans.test.ts`; these pin what a reader sees and can reach.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { useAppStore } from '../../stores/appStore'
import { PRIVACY_MASK } from '../../utils/money'
import type { DashboardMetrics } from '../../types'
import { LivingMeansCard } from './LivingMeansCard'

/** 5,000 in; 3,000 spent and 1,000 to the mortgage; 2,000 saved, which is
 *  not an outflow. Band 4,750 to 5,250. */
function metrics(overrides: Partial<DashboardMetrics> = {}): DashboardMetrics {
  return {
    net_worth: 0,
    net_worth_prev: 0,
    burn_rate_30: 0,
    burn_rate_90: 0,
    essentials_monthly: null,
    essentials_tagged: false,
    savings_rate: 0.4,
    days_until_zero: null,
    income_this_month: 5000,
    expenses_this_month: 3000,
    expenses_prev_month: 2500,
    debt_payments_this_month: 1000,
    outflows_this_month: 4000,
    top_categories: [
      { id: 'c1', name: 'Groceries', group_name: 'Everyday', total: 1200 },
      { id: 'c2', name: 'Dining', group_name: 'Everyday', total: 600 },
      { id: 'c3', name: 'Fuel', group_name: 'Transport', total: 300 },
    ],
    ...overrides,
  }
}

function value(): { text: string; sub: string } {
  const card = document.querySelector('.living-means .metric-card')
  return {
    text: card?.querySelector('.metric-card__value')?.textContent ?? '',
    sub: card?.querySelector('.metric-card__sub')?.textContent ?? '',
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

describe('LivingMeansCard', () => {
  it.each([
    ['below', 4000, 'Below', '$1,000.00 left over', 'Living below your means'],
    ['at', 5200, 'At', '$200.00 short', 'Living at your means'],
    ['above', 6000, 'Above', '$1,000.00 short', 'Living above your means'],
  ])('reads %s your means', (standing, outflows, short, sub, label) => {
    render(<LivingMeansCard data={metrics({ outflows_this_month: outflows })} />)

    const button = screen.getByRole('button', { name: new RegExp(`^${label}`) })
    expect(button).toHaveClass(`living-means__open--${standing}`)
    expect(value()).toEqual({ text: short, sub })
  })

  it('says there is no income rather than giving a verdict', () => {
    render(<LivingMeansCard data={metrics({ income_this_month: 0 })} />)

    expect(screen.getByRole('button', { name: /^No income this period/ })).toHaveClass(
      'living-means__open--unknown'
    )
    expect(value()).toEqual({ text: '—', sub: 'No income recorded' })
    expect(document.body).not.toHaveTextContent(/(above|at|below) your means/i)
  })

  it('opens the dialog with the figures, the band and the prior period', async () => {
    render(<LivingMeansCard data={metrics()} />)
    await userEvent.click(screen.getByRole('button', { name: /Living below your means/ }))

    const dialog = await screen.findByRole('dialog', { name: 'Living below your means' })
    const figures = Object.fromEntries(
      [...dialog.querySelectorAll('.living-means__figure')].map((row) => [
        row.querySelector('dt')?.textContent,
        row.querySelector('dd')?.textContent,
      ])
    )
    expect(figures).toEqual({
      Income: '$5,000.00',
      Spending: '$3,000.00',
      'Debt payments': '$1,000.00',
      Outflows: '$4,000.00',
      'Left over': '$1,000.00',
    })
    expect(within(dialog).getByText(/savings is not an outflow/i)).toBeInTheDocument()
    expect(dialog).toHaveTextContent('At your means: $4,750.00 to $5,250.00, within 5% of income')
    expect(dialog).toHaveTextContent('Below your means: outflows under $4,750.00.')
    expect(dialog).toHaveTextContent('Above your means: outflows over $5,250.00.')

    const top = [...dialog.querySelectorAll('.living-means__top-item')].map((li) => li.textContent)
    expect(top).toEqual([
      'GroceriesEveryday$1,200.0040% of spending',
      'DiningEveryday$600.0020% of spending',
      'FuelTransport$300.0010% of spending',
    ])
    expect(dialog).toHaveTextContent(
      'Spending was $3,000.00 against $2,500.00 in the period of the same length just before — up 20.0%.'
    )
  })

  it('names a shortfall as short in the dialog', async () => {
    render(<LivingMeansCard data={metrics({ outflows_this_month: 6000 })} />)
    await userEvent.click(screen.getByRole('button', { name: /Living above your means/ }))

    const dialog = await screen.findByRole('dialog', { name: 'Living above your means' })
    const short = [...dialog.querySelectorAll('.living-means__figure')].find(
      (row) => row.querySelector('dt')?.textContent === 'Short'
    )
    expect(short?.querySelector('dd')?.textContent).toBe('$1,000.00')
  })

  it('opens from the keyboard', async () => {
    render(<LivingMeansCard data={metrics()} />)
    await userEvent.tab()
    expect(screen.getByRole('button', { name: /Living below your means/ })).toHaveFocus()
    await userEvent.keyboard('{Enter}')
    expect(await screen.findByRole('dialog', { name: 'Living below your means' })).toBeVisible()
  })

  it('has no band and nothing to compare when there is nothing to compare', async () => {
    render(
      <LivingMeansCard
        data={metrics({ income_this_month: 0, expenses_prev_month: 0, top_categories: [] })}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: /No income this period/ }))

    const dialog = await screen.findByRole('dialog', { name: 'No income this period' })
    expect(dialog).toHaveTextContent('there is no band to read outflows by')
    expect(dialog).toHaveTextContent('No spending in this period.')
    expect(dialog).toHaveTextContent('so nothing to compare')
    expect(dialog).not.toHaveTextContent('% of spending')
  })

  it('masks every amount in privacy mode, on the card and in the dialog', async () => {
    useAppStore.setState({ privacyMode: true })
    render(<LivingMeansCard data={metrics()} />)

    expect(value().sub).toBe(`$${PRIVACY_MASK} left over`)
    await userEvent.click(screen.getByRole('button', { name: /Living below your means/ }))
    const dialog = await screen.findByRole('dialog', { name: 'Living below your means' })
    expect(dialog.textContent).not.toMatch(/\$\d/)
    expect(dialog.textContent).toContain(PRIVACY_MASK)
  })
})
