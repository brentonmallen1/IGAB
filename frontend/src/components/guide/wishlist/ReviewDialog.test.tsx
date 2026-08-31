import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReviewDialog } from './ReviewDialog'
import { useAffirmWish, useUpdateWish, type Wish } from '../../../api/wishlist'

vi.mock('../../../api/wishlist', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/wishlist')>()),
  useAffirmWish: vi.fn(),
  useUpdateWish: vi.fn(),
}))

const affirm = vi.fn()
const update = vi.fn()

function wish(name: string): Wish {
  return {
    id: name,
    project_id: null,
    name,
    url: null,
    notes: null,
    cost: '100',
    priority: 0,
    status: 'open',
    funding: {
      mode: 'none',
      category_id: null,
      category_name: null,
      inherited: false,
      owns_envelope: false,
      target_date: null,
    },
    cooling_until: null,
    cooling: false,
    last_affirmed_at: null,
    review_due: true,
    done_at: null,
    created_at: '2026-01-01T00:00:00Z',
    reach: null,
  }
}

function renderDialog(due: Wish[]) {
  const qc = new QueryClient()
  return render(
    <QueryClientProvider client={qc}>
      <ReviewDialog budgetId="b1" due={due} reviewDays={90} onClose={() => {}} />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  affirm.mockReset()
  update.mockReset()
  // Resolve straight away so the dialog steps on.
  affirm.mockImplementation((_id, opts) => opts?.onSuccess?.())
  update.mockImplementation((_vars, opts) => opts?.onSuccess?.())
  vi.mocked(useAffirmWish).mockReturnValue({ mutate: affirm, isPending: false } as never)
  vi.mocked(useUpdateWish).mockReturnValue({ mutate: update, isPending: false } as never)
})

describe('ReviewDialog', () => {
  it('affirms, drops, and finishes with the closing line', async () => {
    renderDialog([wish('Bike'), wish('Lamp')])
    expect(screen.getByText('1 of 2')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Still want it' }))
    expect(affirm).toHaveBeenCalledWith('Bike', expect.anything())
    expect(screen.getByText('2 of 2')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Drop it' }))
    expect(update).toHaveBeenCalledWith({ id: 'Lamp', status: 'dropped' }, expect.anything())
    expect(screen.getByText(/Next review in 90 days/)).toBeInTheDocument()
  })

  it('done marks the wish done', async () => {
    renderDialog([wish('Bike')])
    await userEvent.click(screen.getByRole('button', { name: /Done/ }))
    expect(update).toHaveBeenCalledWith({ id: 'Bike', status: 'done' }, expect.anything())
  })
})
