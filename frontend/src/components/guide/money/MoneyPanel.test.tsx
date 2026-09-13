/**
 * The money tab renders what the server serves and decides nothing itself.
 * Every served string below is invented, so a passing assertion proves the
 * component drew the response rather than copy of its own.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { useAppStore } from '../../../stores/appStore'
import {
  useExplainMove,
  useMoneyMonth,
  useMoneyRules,
  type MoneyMoveRequest,
} from '../../../api/moneyRules'
import { useAccountTypes } from '../../../api/accountTypes'
import { SERVED_RULES, ZERO_FIGURES, explanation } from '../../../test-utils/moneyRulesFixtures'
import { MoneyPanel } from './MoneyPanel'
import { WORKED_MONTH } from './workedMonthMoves'

vi.mock('../../../api/moneyRules', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/moneyRules')>()),
  useMoneyRules: vi.fn(),
  useExplainMove: vi.fn(),
  useMoneyMonth: vi.fn(),
}))

vi.mock('../../../api/accountTypes', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/accountTypes')>()),
  useAccountTypes: vi.fn(),
}))

type Explained = ReturnType<typeof useExplainMove>

function serveExplain(data: ReturnType<typeof explanation>, extra: Partial<Explained> = {}) {
  vi.mocked(useExplainMove).mockReturnValue({
    data,
    isFetching: false,
    isError: false,
    isPlaceholderData: false,
    ...extra,
  } as unknown as Explained)
}

function renderPanel() {
  return render(
    <MemoryRouter>
      <MoneyPanel />
    </MemoryRouter>
  )
}

beforeEach(() => {
  useAppStore.setState({ currentBudgetId: 'b1' })
  vi.mocked(useAccountTypes).mockReturnValue({ data: undefined } as ReturnType<
    typeof useAccountTypes
  >)
  vi.mocked(useMoneyRules).mockReturnValue({
    data: {
      rules: SERVED_RULES,
      report_families: [{ key: 'income', label: 'Served Income family', classes: ['income'] }],
      shapes: [],
      planned_spend_tag_keys: ['savings'],
    },
    isError: false,
  } as unknown as ReturnType<typeof useMoneyRules>)
  serveExplain(explanation())
  vi.mocked(useMoneyMonth).mockReturnValue({
    data: {
      rows: WORKED_MONTH.map((m) => ({ label: m.label, explanation: explanation() })),
      class_totals: {},
      figures: {
        ...ZERO_FIGURES,
        income: 10500,
        spending: 2300,
        savings: 750,
        debt_principal: 1800,
        savings_rate: 0.0714,
        savings_rate_with_debt: 0.2429,
      },
    },
    isError: false,
  } as unknown as ReturnType<typeof useMoneyMonth>)
})

describe('the rule ladder', () => {
  it('lists the served rules in order, the default last', () => {
    renderPanel()
    const ladder = screen.getByRole('list', { name: 'Rules, first match wins' })
    const items = within(ladder).getAllByRole('listitem')
    expect(items.map((li) => li.textContent)).toEqual([
      expect.stringContaining('Served tag reason'),
      expect.stringContaining('Served transfer reason'),
      expect.stringContaining('Otherwise: Served default reason'),
    ])
    expect(within(items[0]).getByText('Served Savings')).toBeInTheDocument()
    expect(within(items[0]).getByText('tag: Savings')).toBeInTheDocument()
  })
})

describe('the explorer', () => {
  it('renders the served answer for each leg and the move', () => {
    renderPanel()
    expect(screen.getByText('Because served income reason.')).toBeInTheDocument()
    expect(screen.getByText('Counted in: Served Income family')).toBeInTheDocument()
    expect(screen.getByText('Off budget, so no report counts this side')).toBeInTheDocument()
    expect(screen.getByText(/Ready to Assign goes up by/)).toBeInTheDocument()
    expect(screen.getByText(/Unchanged — the money only moved/)).toBeInTheDocument()
    expect(screen.getByText('Served assumption.')).toBeInTheDocument()
  })

  it('disables the category, and says why, when the server says no leg may carry one', () => {
    serveExplain(explanation({ category_role: null }))
    renderPanel()
    const select = screen.getByRole('combobox', { name: 'Category' })
    expect(select).toBeDisabled()
    expect(select).toHaveAccessibleDescription(/Neither side can hold a category/)
  })

  it('does not read that from an answer about the previous controls', () => {
    serveExplain(explanation({ category_role: null }), { isPlaceholderData: true })
    renderPanel()
    expect(screen.getByRole('combobox', { name: 'Category' })).toBeEnabled()
  })

  it('asks again with the new controls when a type changes', async () => {
    renderPanel()
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: 'To account type' }),
      'Other Asset'
    )
    const last = vi.mocked(useExplainMove).mock.lastCall?.[1] as MoneyMoveRequest
    expect(last.to_account).toEqual({
      classification: 'asset',
      on_budget: false,
      counts_as_savings: false,
    })
  })

  it('loads a catch-out into the explorer', async () => {
    renderPanel()
    await userEvent.click(
      screen.getByRole('button', { name: /Try it in the explorer: Selling something/ })
    )
    const last = vi.mocked(useExplainMove).mock.lastCall?.[1] as MoneyMoveRequest
    expect(last.account.counts_as_savings).toBe(false)
    expect(last.to_account?.on_budget).toBe(true)
  })
})

describe('the tag table', () => {
  it('says a tag changes the class only where a served rule reads it', () => {
    renderPanel()
    const table = screen.getByRole('table', { name: 'What each tag does' })
    const savings = within(table).getByRole('rowheader', { name: 'Savings' }).closest('tr')!
    const essential = within(table).getByRole('rowheader', { name: 'Essential' }).closest('tr')!
    expect(within(savings).getByText('Served Savings')).toBeInTheDocument()
    expect(within(essential).getByText('No')).toBeInTheDocument()
  })
})

describe('the worked month', () => {
  it('asks for the fixed month and shows the served totals and both rates', () => {
    renderPanel()
    expect(vi.mocked(useMoneyMonth)).toHaveBeenCalledWith('b1', WORKED_MONTH)
    expect(screen.getByText('Sold the car into checking')).toBeInTheDocument()
    expect(screen.getByText('7.1%')).toBeInTheDocument()
    expect(screen.getByText('24.3%')).toBeInTheDocument()
  })
})
