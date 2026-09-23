import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReviewDialog } from './ReviewDialog'
import { useAffirmWish, type Wish } from '../../../api/wishlist'

vi.mock('../../../api/wishlist', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/wishlist')>()),
  useAffirmWish: vi.fn(),
}))

const affirm = vi.fn()
const onEnd = vi.fn()

function wish(name: string): Wish {
  return {
    id: name,
    project_id: null,
    name,
    url: null,
    notes: null,
    cost: 100,
    priority: 0,
    is_priority: false,
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
    dropped_at: null,
    settlement: null,
    added_on: '2026-01-01',
    created_at: '2026-01-01T00:00:00Z',
    reach: null,
  }
}

function renderDialog(due: Wish[]) {
  const qc = new QueryClient()
  return render(
    <QueryClientProvider client={qc}>
      <ReviewDialog budgetId="b1" due={due} reviewDays={90} onEnd={onEnd} onClose={() => {}} />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  affirm.mockReset()
  onEnd.mockReset()
  onEnd.mockResolvedValue(undefined)
  // Resolve straight away so the dialog steps on.
  affirm.mockImplementation((_id, opts) => opts?.onSuccess?.())
  vi.mocked(useAffirmWish).mockReturnValue({ mutate: affirm, isPending: false } as never)
})

describe('ReviewDialog', () => {
  it('affirms, drops, and finishes with the closing line', async () => {
    renderDialog([wish('Bike'), wish('Lamp')])
    expect(screen.getByText('1 of 2')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Still want it' }))
    expect(affirm).toHaveBeenCalledWith('Bike', expect.anything())
    expect(screen.getByText('2 of 2')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Drop it' }))
    // The panel's ending, not a second one here: a wish that leaves an
    // envelope standing must raise the same question wherever it was ended.
    expect(onEnd).toHaveBeenCalledWith(expect.objectContaining({ id: 'Lamp' }), 'dropped')
    expect(screen.getByText(/Next review in 90 days/)).toBeInTheDocument()
  })

  it('done marks the wish done', async () => {
    renderDialog([wish('Bike')])
    await userEvent.click(screen.getByRole('button', { name: /Done/ }))
    expect(onEnd).toHaveBeenCalledWith(expect.objectContaining({ id: 'Bike' }), 'done')
  })
})
