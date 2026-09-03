import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ImportPanel } from './ImportPanel'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { useTargetsByBudget } from '../../../api/targets'

vi.mock('../../../api/categories', () => ({
  useCategories: vi.fn(),
  useCategoryGroups: vi.fn(),
}))
vi.mock('../../../api/targets', () => ({ useTargetsByBudget: vi.fn() }))

function group(id: string, name: string, sort_order: number) {
  return { id, name, sort_order, budget_id: 'b1', is_archived: false, is_system: false }
}
function category(id: string, name: string, groupId: string, sort_order: number) {
  return {
    id,
    name,
    category_group_id: groupId,
    sort_order,
    budget_id: 'b1',
    is_archived: false,
    linked_account_id: null,
    linked_liability_id: null,
  }
}

const GROUPS = [group('g1', 'Monthly Bills', 0), group('g2', 'True Expenses', 1)]
const CATEGORIES = [
  category('c-rent', 'Rent', 'g1', 0),
  category('c-power', 'Electric', 'g1', 1),
  category('c-car', 'Car Maintenance', 'g2', 0),
]

beforeEach(async () => {
  // An overlay balances its history entry with a deferred history.back() on
  // unmount. Left pending, it lands mid-way through the next test and pops an
  // entry that test's dialog is relying on — which closed every other dialog
  // here. Drain the timer and the popstate it queues, then clear the state so
  // the next push definitely happens.
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')

  vi.mocked(useCategoryGroups).mockReturnValue({ data: GROUPS, isLoading: false } as never)
  vi.mocked(useCategories).mockReturnValue({ data: CATEGORIES, isLoading: false } as never)
  // Rent carries a $1,200/mo funding target; the others have none. Only a
  // monthly_funding target seeds an amount — see seedCentsFromTarget.
  vi.mocked(useTargetsByBudget).mockReturnValue({
    data: [{ category_id: 'c-rent', target_type: 'monthly_funding', target_amount: 1200 }],
    isLoading: false,
  } as never)
})

function setup(linked: string[] = []) {
  const onImport = vi.fn()
  const utils = render(
    <ImportPanel budgetId="b1" linkedIds={new Set(linked)} paycheckCount={2} onImport={onImport} />
  )
  return { ...utils, onImport }
}

async function open() {
  await userEvent.click(screen.getByRole('button', { name: /pull in budget categories/i }))
}

describe('ImportPanel', () => {
  it('opens a dialog rather than growing the page', async () => {
    setup()
    expect(screen.queryByRole('dialog')).toBeNull()
    await open()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('renders the budget’s own group headers — the structure the flat grid discarded', async () => {
    setup()
    await open()
    expect(screen.getByText('Monthly Bills')).toBeInTheDocument()
    expect(screen.getByText('True Expenses')).toBeInTheDocument()
  })

  it('a group header takes the whole group, and the confirm counts what is picked', async () => {
    const { onImport } = setup()
    await open()
    await userEvent.click(screen.getByText('Monthly Bills'))
    expect(screen.getByRole('button', { name: /add 2 categories/i })).toBeEnabled()
    await userEvent.click(screen.getByRole('button', { name: /add 2 categories/i }))
    expect(onImport).toHaveBeenCalledTimes(1)
    const [items, destination] = onImport.mock.calls[0]
    expect(items.map((i: { name: string }) => i.name)).toEqual(['Rent', 'Electric'])
    expect(destination).toBe(0)
  })

  it('seeds an amount from a category’s monthly target and leaves the rest blank', async () => {
    const { onImport } = setup()
    await open()
    await userEvent.click(screen.getByText('Monthly Bills'))
    await userEvent.click(screen.getByRole('button', { name: /add 2 categories/i }))
    const items = onImport.mock.calls[0][0] as { name: string; amount: string }[]
    expect(items.find((i) => i.name === 'Rent')!.amount).toBe('1200')
    expect(items.find((i) => i.name === 'Electric')!.amount).toBe('')
  })

  it('search narrows the list', async () => {
    setup()
    await open()
    await userEvent.type(screen.getByPlaceholderText('Search categories…'), 'car')
    expect(screen.getByText('Car Maintenance')).toBeInTheDocument()
    expect(screen.queryByText('Rent')).toBeNull()
  })

  it('the destination chooses which paycheck the rows land under', async () => {
    const { onImport } = setup()
    await open()
    await userEvent.click(screen.getByText('Car Maintenance'))
    await userEvent.selectOptions(screen.getByLabelText('Which paycheck the rows go under'), '1')
    await userEvent.click(screen.getByRole('button', { name: /add 1 category/i }))
    expect(onImport.mock.calls[0][1]).toBe(1)
  })

  it('categories already in the plan are not offered again', async () => {
    setup(['c-rent'])
    await open()
    expect(screen.queryByText('Rent')).toBeNull()
    expect(screen.getByText('Electric')).toBeInTheDocument()
  })

  it('says so when the budget has nothing left to offer', async () => {
    setup(['c-rent', 'c-power', 'c-car'])
    await open()
    expect(screen.getByText(/already in this plan/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^add/i })).toBeNull()
  })

  it('cannot confirm an empty pick', async () => {
    setup()
    await open()
    expect(screen.getByRole('button', { name: /add categories/i })).toBeDisabled()
  })

  it('forgets the pick when cancelled, so reopening does not re-add it', async () => {
    const { onImport } = setup()
    await open()
    await userEvent.click(screen.getByText('Rent'))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onImport).not.toHaveBeenCalled()
    await open()
    expect(screen.getByRole('button', { name: /add categories/i })).toBeDisabled()
  })
})
