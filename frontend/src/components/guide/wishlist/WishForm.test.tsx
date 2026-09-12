/**
 * The funding radio's third state means "no category of its own", and what
 * that implies depends on the project: with a funded project the wish follows
 * that envelope, without one it waits. The server serves inherited funding as
 * mode 'existing', and seeding the form from that blocked every save of a
 * project-funded wish behind "Pick the category that funds it" — for a
 * category the form deliberately doesn't show. These pin the seeding.
 *
 * Fixtures carry money as the server sends it — a JSON number. They said
 * '900' while the server said 900, and that gap hid a Save that did nothing.
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
    cost: 900,
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
    added_on: '2026-08-01',
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
      total_cost: 0,
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
        maxCoolingDays={365}
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
      cost: 1200,
      url: 'https://new.example/kayak',
      notes: 'the tandem',
      project_id: 'Cabin',
      cooling_until: '2026-10-01',
      funding: { mode: 'none', category_id: null },
    })
  })

  it('offers an envelope of its own to a wish that has none', async () => {
    // The whole funding choice used to be a one-time decision: editing hid
    // the "own" radio, and the server refused the mode anyway.
    renderForm(wish({ mode: 'none' }), [])
    const own = screen.getByRole('radio', { name: /An envelope of its own/ })
    await userEvent.click(own)
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({ funding: { mode: 'own', category_id: null } })
    )
  })

  it('lets a wish that owns an envelope point somewhere else', async () => {
    // It showed a sentence and no controls at all, so this was unreachable.
    renderForm(
      wish({ mode: 'own', owns_envelope: true, category_id: 'c-own', category_name: 'Canoe' }),
      []
    )
    await userEvent.click(screen.getByRole('radio', { name: /Not yet/ }))
    expect(screen.getByText(/Canoe stays on the Budget page/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({ funding: { mode: 'none', category_id: null } })
    )
  })

  it('sends no want_by for an envelope that already exists', async () => {
    // The date sets the new envelope's goal. For one the budget page already
    // owns, claiming to set it would be a lie.
    renderForm(
      wish({ mode: 'own', owns_envelope: true, category_id: 'c-own', category_name: 'Canoe' }),
      []
    )
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({ funding: { mode: 'own', category_id: null } })
    )
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

describe('WishForm with a server-shaped wish', () => {
  it('saves after changing only the cool-off date', async () => {
    // Regression: the server sends cost as a JSON number, the type said
    // string, and the Cost input was seeded with the number. Save called
    // `.trim()` on it and threw outside the try — no request, no message.
    // Fixtures spelled cost '900', so nothing noticed.
    const w = wish({ mode: 'none' }, { cost: 900, cooling_until: '2026-08-31', cooling: true })
    renderForm(w, [])

    fireEvent.change(screen.getByLabelText(/Cooling off until/), {
      target: { value: '2026-10-01' },
    })
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(update).toHaveBeenCalledWith({
      id: 'w1',
      name: 'Canoe',
      cost: 900,
      url: null,
      notes: null,
      project_id: null,
      cooling_until: '2026-10-01',
      funding: { mode: 'none', category_id: null },
    })
  })

  it('keeps a cents cost exact through an untouched save', async () => {
    renderForm(wish({ mode: 'none' }, { cost: 1234.56 }), [])
    expect(screen.getByLabelText('Cost')).toHaveValue('1234.56')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(update).toHaveBeenCalledWith(expect.objectContaining({ cost: 1234.56 }))
  })

  it('says so when the cost does not parse, and sends nothing', async () => {
    renderForm(wish({ mode: 'none' }, { cost: 900 }), [])
    await userEvent.clear(screen.getByLabelText('Cost'))
    await userEvent.type(screen.getByLabelText('Cost'), 'lots')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(screen.getByText('That cost did not parse')).toBeInTheDocument()
    expect(update).not.toHaveBeenCalled()
  })

  it('surfaces a failure from inside the submit rather than doing nothing', async () => {
    update.mockRejectedValueOnce(new Error('boom'))
    renderForm(wish({ mode: 'none' }, { cost: 900 }), [])
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Could not save')).toBeInTheDocument()
  })
})

describe('WishForm cooling-off in days', () => {
  const added = { added_on: '2026-08-01', created_at: '2026-08-01T00:00:00Z' }
  const daysField = () => screen.getByLabelText(/days after added/)
  const dateField = () => screen.getByLabelText(/Cooling off until/)

  it('shows the stored date as days after the wish was added', () => {
    renderForm(wish({ mode: 'none' }, { ...added, cooling_until: '2026-08-15', cooling: true }), [])
    expect(daysField()).toHaveValue('14')
    expect(dateField()).toHaveValue('2026-08-15')
  })

  it('moves the date as days are typed, and sends the days for the server to resolve', async () => {
    renderForm(wish({ mode: 'none' }, { ...added, cooling_until: '2026-08-15', cooling: true }), [])
    await userEvent.clear(daysField())
    await userEvent.type(daysField(), '30')
    expect(dateField()).toHaveValue('2026-08-31')

    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    const body = update.mock.calls[0][0]
    expect(body.cooling_days).toBe(30)
    // Never both: the server refuses a request that carries the two.
    expect(body).not.toHaveProperty('cooling_until')
  })

  it('moves the days as a date is picked, and sends the date', async () => {
    renderForm(wish({ mode: 'none' }, { ...added, cooling_until: '2026-08-15', cooling: true }), [])
    fireEvent.change(dateField(), { target: { value: '2026-09-10' } })
    expect(daysField()).toHaveValue('40')

    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    const body = update.mock.calls[0][0]
    expect(body.cooling_until).toBe('2026-09-10')
    expect(body).not.toHaveProperty('cooling_days')
  })

  it('zero days ends the cooling-off on the day the wish was added', async () => {
    renderForm(wish({ mode: 'none' }, { ...added, cooling_until: '2026-08-15', cooling: true }), [])
    await userEvent.clear(daysField())
    await userEvent.type(daysField(), '0')
    expect(dateField()).toHaveValue('2026-08-01')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(update.mock.calls[0][0].cooling_days).toBe(0)
  })

  it('takes days that are already behind us — that is just a wish done cooling', async () => {
    // Added 2026-08-01; ten days is long past by the time anyone edits it.
    renderForm(wish({ mode: 'none' }, added), [])
    await userEvent.type(daysField(), '10')
    expect(dateField()).toHaveValue('2026-08-11')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(update.mock.calls[0][0].cooling_days).toBe(10)
    expect(screen.queryByText(/Cooling-off days must/)).not.toBeInTheDocument()
  })

  it('refuses days past the served limit with a message, and sends nothing', async () => {
    renderForm(wish({ mode: 'none' }, added), [])
    await userEvent.type(daysField(), '366')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(
      screen.getByText('Cooling-off days must be a whole number from 0 to 365')
    ).toBeInTheDocument()
    expect(update).not.toHaveBeenCalled()
  })

  it('clearing the days clears the date and ends the cooling-off', async () => {
    renderForm(wish({ mode: 'none' }, { ...added, cooling_until: '2026-08-15', cooling: true }), [])
    await userEvent.clear(daysField())
    expect(dateField()).toHaveValue('')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(update).toHaveBeenCalledWith(expect.objectContaining({ cooling_until: null }))
  })

  it('does not validate the days when only the date or another field was edited', async () => {
    // The days field used to be validated on every edit even while hidden. A
    // date picked before the day added reads as negative days — shown as
    // what it is, and no reason to block saving a new name.
    renderForm(wish({ mode: 'none' }, { ...added, cooling_until: '2026-07-20' }), [])
    expect(daysField()).toHaveValue('-12')
    await userEvent.clear(screen.getByLabelText('What'))
    await userEvent.type(screen.getByLabelText('What'), 'Kayak')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Kayak', cooling_until: '2026-07-20' })
    )
  })

  it('create keeps its days field, sends the browser date as the day added', async () => {
    renderForm(null, [])
    await userEvent.type(screen.getByLabelText('What'), 'Tent')
    await userEvent.type(screen.getByLabelText('Cost'), '250')
    const days = screen.getByLabelText('Cooling-off, days')
    expect(days).toHaveValue('30')
    await userEvent.clear(days)
    await userEvent.type(days, '14')
    await userEvent.click(screen.getByRole('button', { name: 'Add to the list' }))
    expect(create).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Tent',
        cost: 250,
        cooling_days: 14,
        client_today: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      })
    )
  })

  it('create refuses the same bad days the edit does', async () => {
    renderForm(null, [])
    await userEvent.type(screen.getByLabelText('What'), 'Tent')
    await userEvent.type(screen.getByLabelText('Cost'), '250')
    const days = screen.getByLabelText('Cooling-off, days')
    await userEvent.clear(days)
    await userEvent.type(days, '1.5')
    await userEvent.click(screen.getByRole('button', { name: 'Add to the list' }))
    expect(screen.getByText(/whole number from 0 to 365/)).toBeInTheDocument()
    expect(create).not.toHaveBeenCalled()
  })
})
