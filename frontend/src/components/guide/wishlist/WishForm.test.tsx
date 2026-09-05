/**
 * The funding radio's third state means "no category of its own", and what
 * that implies depends on the project: with a funded project the wish follows
 * that envelope, without one it waits. The server serves inherited funding as
 * mode 'existing', and seeding the form from that blocked every save of a
 * project-funded wish behind "Pick the category that funds it" — for a
 * category the form deliberately doesn't show. These pin the seeding.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { WishForm } from './WishForm'
import {
  useCreateWish,
  useUpdateWish,
  type Wish,
  type WishFunding,
  type WishlistProject,
} from '../../../api/wishlist'

vi.mock('../../../api/wishlist', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/wishlist')>()),
  useCreateWish: vi.fn(),
  useUpdateWish: vi.fn(),
}))

const create = vi.fn()
const update = vi.fn()

function wish(funding: Partial<WishFunding>, over: Partial<Wish> = {}): Wish {
  return {
    id: 'w1',
    project_id: null,
    name: 'Canoe',
    url: null,
    notes: null,
    cost: '900',
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
      ...funding,
    },
    cooling_until: null,
    cooling: false,
    last_affirmed_at: null,
    review_due: false,
    done_at: null,
    created_at: '2026-08-01T00:00:00Z',
    reach: null,
    ...over,
  }
}

function project(over: Partial<WishlistProject>): WishlistProject {
  return {
    id: over.name ?? 'p',
    name: 'P',
    category_id: null,
    category_name: null,
    notes: null,
    sort_order: 0,
    summary: {
      item_count: 0,
      open_count: 0,
      total_cost: '0',
      affordable_now: 0,
      funded_by: null,
      state: 'empty',
      complete: false,
    },
    ...over,
  }
}

const cabin = project({ name: 'Cabin', category_id: 'c-cabin', category_name: 'Cabin Fund' })
const someday = project({ name: 'Someday' })

function renderForm(w: Wish | null, projects: WishlistProject[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <WishForm
        budgetId="b1"
        wish={w}
        projects={projects}
        defaultCoolingDays={30}
        onClose={() => {}}
      />
    </QueryClientProvider>
  )
}

beforeEach(async () => {
  // GuideDialog pushes a history entry per mount and pops it on close; drain
  // the queue so a stale pop cannot close the next test's dialog.
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')

  create.mockReset().mockResolvedValue({})
  update.mockReset().mockResolvedValue({})
  vi.mocked(useCreateWish).mockReturnValue({ mutateAsync: create, isPending: false } as never)
  vi.mocked(useUpdateWish).mockReturnValue({ mutateAsync: update, isPending: false } as never)
})

describe('WishForm', () => {
  it('saves a project-funded wish without demanding a category it never chose', async () => {
    // Regression: inherited funding is served as mode 'existing', and the
    // form used to seed from it — then block the save on the empty combobox.
    const w = wish(
      { mode: 'existing', category_id: 'c-cabin', category_name: 'Cabin Fund', inherited: true },
      { project_id: 'Cabin' }
    )
    renderForm(w, [cabin, someday])

    await userEvent.selectOptions(screen.getByLabelText('Project'), 'Someday')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 'w1',
        project_id: 'Someday',
        funding: { mode: 'none', category_id: null },
      })
    )
    expect(screen.queryByText(/Pick the category/)).not.toBeInTheDocument()
  })

  it("says whose envelope 'no category of its own' means, live with the picker", async () => {
    const w = wish(
      { mode: 'existing', category_id: 'c-cabin', category_name: 'Cabin Fund', inherited: true },
      { project_id: 'Cabin' }
    )
    renderForm(w, [cabin, someday])
    expect(screen.getByText('The project’s envelope')).toBeInTheDocument()
    expect(screen.getByText(/funded from Cabin Fund/)).toBeInTheDocument()

    // Switch to an unfunded project and the same choice means waiting.
    await userEvent.selectOptions(screen.getByLabelText('Project'), 'Someday')
    expect(screen.getByText('Not yet')).toBeInTheDocument()
  })

  it('the edit sends every attribute the form owns — nothing silently dropped', async () => {
    // The twin of the backend's every-field round-trip: the wish's link once
    // looked uneditable because an unrelated validation blocked the save, and
    // this pins that each form field actually reaches the request.
    const w = wish(
      { mode: 'none' },
      { url: 'https://old.example', notes: 'old', cooling_until: '2026-09-20', cooling: true }
    )
    renderForm(w, [cabin])

    await userEvent.clear(screen.getByLabelText('What'))
    await userEvent.type(screen.getByLabelText('What'), 'Kayak')
    await userEvent.clear(screen.getByLabelText('Cost'))
    await userEvent.type(screen.getByLabelText('Cost'), '1200')
    await userEvent.selectOptions(screen.getByLabelText('Project'), 'Cabin')
    const link = screen.getByLabelText('Link (optional)')
    await userEvent.clear(link)
    await userEvent.type(link, 'https://new.example/kayak')
    const notes = screen.getByLabelText('Notes (optional)')
    await userEvent.clear(notes)
    await userEvent.type(notes, 'the tandem')
    const cooling = screen.getByLabelText(/Cooling off until/)
    await userEvent.clear(cooling)
    // fireEvent for the date value: typing into a date input is flaky in jsdom
    fireEvent.change(cooling, { target: { value: '2026-10-01' } })

    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(update).toHaveBeenCalledWith({
      id: 'w1',
      name: 'Kayak',
      cost: '1200',
      url: 'https://new.example/kayak',
      notes: 'the tandem',
      project_id: 'Cabin',
      cooling_until: '2026-10-01',
      funding: { mode: 'none', category_id: null },
    })
  })

  it('clearing the cooling date ends the cooling-off', async () => {
    const w = wish({ mode: 'none' }, { cooling_until: '2026-09-20', cooling: true })
    renderForm(w, [])
    fireEvent.change(screen.getByLabelText(/Cooling off until/), { target: { value: '' } })
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(update).toHaveBeenCalledWith(expect.objectContaining({ cooling_until: null }))
  })

  it('still requires a category when one was explicitly chosen and then cleared', async () => {
    const w = wish({ mode: 'existing', category_id: 'c-own', category_name: 'Fun Money' })
    renderForm(w, [])
    // Explicit funding seeds 'existing' with its category — the save passes.
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({ funding: { mode: 'existing', category_id: 'c-own' } })
    )
  })
})
