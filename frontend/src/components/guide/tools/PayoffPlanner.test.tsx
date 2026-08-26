import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PayoffPlanner } from './PayoffPlanner'
import { useAppStore } from '../../../stores/appStore'
import { useLiabilities, type Liability } from '../../../api/liabilities'
import { usePayoffPlan } from '../../../api/guide'

vi.mock('../../../api/liabilities', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/liabilities')>()),
  useLiabilities: vi.fn(),
}))
vi.mock('../../../api/guide', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/guide')>()),
  usePayoffPlan: vi.fn(),
}))

function liability(over: Partial<Liability>): Liability {
  return {
    id: 'l1',
    name: 'Visa',
    current_balance: 3410,
    interest_rate: 22.9,
    minimum_payment: 85,
    ...over,
  } as unknown as Liability
}

function renderPlanner() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PayoffPlanner />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  useAppStore.setState({ currentBudgetId: 'b1' })
  vi.mocked(usePayoffPlan).mockReturnValue({ data: undefined, isFetching: false } as never)
})

describe('PayoffPlanner', () => {
  it('seeds rows from liabilities that have terms and names the ones left out', () => {
    vi.mocked(useLiabilities).mockReturnValue({
      data: [liability({}), liability({ id: 'l2', name: 'Unknown card', interest_rate: null })],
    } as never)
    renderPlanner()
    expect(screen.getByDisplayValue('Visa')).toBeInTheDocument()
    expect(screen.getByDisplayValue('22.9')).toBeInTheDocument()
    expect(screen.getByText(/Left out/)).toHaveTextContent('Unknown card')
  })

  it('offers an empty row when there is nothing to seed', () => {
    vi.mocked(useLiabilities).mockReturnValue({ data: [] } as never)
    renderPlanner()
    expect(screen.getAllByLabelText('Debt name')).toHaveLength(1)
  })

  it('adds a debt by hand', async () => {
    vi.mocked(useLiabilities).mockReturnValue({ data: [liability({})] } as never)
    renderPlanner()
    await userEvent.click(screen.getByRole('button', { name: /add a debt/i }))
    expect(screen.getAllByLabelText('Debt name')).toHaveLength(2)
  })

  it('asks the server only once every figure parses', async () => {
    vi.mocked(useLiabilities).mockReturnValue({ data: [liability({})] } as never)
    renderPlanner()
    await userEvent.clear(screen.getByLabelText('Minimum payment'))
    expect(screen.getByText(/did not parse/)).toBeInTheDocument()
  })
})
