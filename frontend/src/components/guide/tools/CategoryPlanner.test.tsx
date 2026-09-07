import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CategoryPlanner } from './CategoryPlanner'
import { useAppStore } from '../../../stores/appStore'
import { useGuideStore } from '../../../stores/guideStore'
import { useCategoryPlan, useCategoryPlans, type CategoryPlan } from '../../../api/categoryPlans'

vi.mock('../../../api/categoryPlans', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/categoryPlans')>()),
  useCategoryPlans: vi.fn(),
  useCategoryPlan: vi.fn(),
}))

function plan(): CategoryPlan {
  return {
    id: 'plan1',
    name: 'Plan 1',
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    payload: {
      schema_version: 1,
      monthly_income_cents: 520000,
      cadence: 'biweekly',
      paycheck_count_override: null,
      paychecks: [
        {
          id: 'p1',
          label: null,
          income_override_cents: null,
          items: [{ id: 'i1', category_id: null, name: 'Rent', due_day: 1, amount_cents: 145000 }],
        },
        { id: 'p2', label: null, income_override_cents: null, items: [] },
      ],
    },
  }
}

function renderPlanner() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <CategoryPlanner />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  useAppStore.setState({ currentBudgetId: 'b1' })
  useGuideStore.setState({ activePlanId: 'plan1' })
  vi.mocked(useCategoryPlans).mockReturnValue({
    data: [{ id: 'plan1', name: 'Plan 1' }],
    isSuccess: true,
  } as never)
  vi.mocked(useCategoryPlan).mockReturnValue({ data: plan() } as never)
})

const columns = () => document.querySelectorAll('.planner__column')

describe('CategoryPlanner', () => {
  it('renders the plan and its totals from the one math module', () => {
    renderPlanner()
    expect(screen.getByDisplayValue('Rent')).toBeInTheDocument()
    // 5,200 take-home − 1,450 planned = 3,750 left to plan.
    expect(screen.getByText('Left to plan')).toBeInTheDocument()
    expect(screen.getByText('$3,750.00')).toBeInTheDocument()
  })

  it('adding a row updates the planned total once an amount is typed', async () => {
    renderPlanner()
    const second = within(columns()[1] as HTMLElement)
    await userEvent.click(second.getByRole('button', { name: /add a category/i }))
    await userEvent.type(second.getByLabelText('Amount'), '550')
    // Monthly planned: 1,450 + 550 = 2,000.
    expect(screen.getByText('$2,000.00')).toBeInTheDocument()
  })

  it('the move control relocates a row to another paycheck', async () => {
    renderPlanner()
    await userEvent.selectOptions(screen.getByLabelText('Move to another paycheck'), '1')
    const second = within(columns()[1] as HTMLElement)
    expect(second.getByDisplayValue('Rent')).toBeInTheDocument()
  })

  it('a paycheck can be named, and its name is what the move controls offer', async () => {
    renderPlanner()
    const first = within(columns()[0] as HTMLElement)
    await userEvent.type(first.getByLabelText('Name for paycheck 1'), 'Northwind, 1st')
    // The row's own move picker names the columns the headers do.
    expect(
      within(columns()[1] as HTMLElement).queryByLabelText('Name for paycheck 2')
    ).toHaveAttribute('placeholder', 'Paycheck 2')
    await userEvent.click(first.getByLabelText(/select rent/i))
    await userEvent.click(screen.getByRole('button', { name: /move to paycheck/i }))
    expect(screen.getByRole('menuitem', { name: 'Northwind, 1st' })).toBeInTheDocument()
  })

  it('selecting rows moves them together', async () => {
    renderPlanner()
    const first = within(columns()[0] as HTMLElement)
    await userEvent.click(first.getByLabelText(/select rent/i))
    expect(screen.getByText('1 row selected')).toBeInTheDocument()
    // The shared floating selection bar, as on the register and the budget
    // grid, with the destinations in a menu rather than a native select.
    await userEvent.click(screen.getByRole('button', { name: /move to paycheck/i }))
    await userEvent.click(screen.getByRole('menuitem', { name: 'Paycheck 2' }))
    expect(within(columns()[1] as HTMLElement).getByDisplayValue('Rent')).toBeInTheDocument()
    // The selection clears with the move — a stale tick on a moved row is a
    // second move nobody asked for.
    expect(screen.queryByText(/row selected/)).not.toBeInTheDocument()
  })

  it('each column counts its categories', () => {
    renderPlanner()
    const first = within(columns()[0] as HTMLElement)
    expect(first.getByText('1')).toBeInTheDocument()
  })

  it('with no plans yet, offers to start one', () => {
    vi.mocked(useCategoryPlans).mockReturnValue({ data: [], isSuccess: true } as never)
    vi.mocked(useCategoryPlan).mockReturnValue({ data: undefined } as never)
    renderPlanner()
    expect(screen.getByRole('button', { name: /start a plan/i })).toBeInTheDocument()
  })
})
