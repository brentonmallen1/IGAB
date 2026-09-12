/**
 * An envelope's Available while adding a transaction on the phone.
 *
 * Three places show it — the category picker, the chosen category's row, and
 * the toast after Save — and every figure has to be the server's. The toast's
 * "after" is the refetched month, never the old balance plus the amount: a
 * card envelope, a future-dated row or a rollover would make that sum wrong
 * with nothing on screen to say so.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { isValidElement, type ReactElement } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ROOT } from '../../../api/queryKeys'
import { makeCategoryBalance } from '../../../test-utils/factories'
import { COUNT_UP_MS } from '../../../utils/countUp'
import type { BudgetMonth, CategoryBalance } from '../../../types'

const h = vi.hoisted(() => ({
  qc: null as unknown as import('@tanstack/react-query').QueryClient,
  /** What GET /{budget}/months/{month} answers, by month. */
  months: {} as Record<string, unknown>,
  /** Swapped in by the create mutation: the server's months after the save. */
  monthsAfterSave: {} as Record<string, unknown>,
  failAfterSave: false,
  saved: false,
  privacyMode: false,
  reducedMotion: false,
  onBudget: true,
  get: vi.fn(),
  notify: vi.fn(),
}))

vi.mock('../../../api/client', () => ({
  apiClient: { get: h.get, post: vi.fn() },
  apiErrorMessage: (_e: unknown, fallback: string) => fallback,
}))
vi.mock('../../../api/transactions', () => ({
  useCreateTransaction: () => ({
    // What useCreateTransaction's onSuccess does for real: the server has the
    // row, and every budget month is invalidated before mutateAsync resolves.
    mutateAsync: async () => {
      h.saved = true
      await h.qc.invalidateQueries({ queryKey: [ROOT.budgetMonth] })
      return { id: 'txn-new', account_id: 'acc-1' }
    },
    isPending: false,
  }),
}))
vi.mock('../../../api/attachments', () => ({
  ATTACHMENT_ACCEPT: '',
  isAttachableFile: () => true,
  uploadFilesToTransaction: vi.fn(() => Promise.resolve({ failed: [] })),
}))
vi.mock('../../../api/ai', () => ({ useAIStatus: () => ({ data: { enabled: false } }) }))
vi.mock('../../../api/aiJobs', () => ({
  useSubmitReceipt: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../../../api/payees', () => ({
  usePayees: () => ({
    data: [
      {
        id: 'p1',
        name: 'Corner Market',
        transfer_account_id: null,
        last_used: null,
        default_category_id: 'c1',
      },
    ],
  }),
  useNearbyPayees: () => ({ data: [] }),
  useCreatePayee: () => ({ mutateAsync: vi.fn() }),
}))
const category = (id: string, name: string, group = 'g1') => ({
  id,
  category_group_id: group,
  name,
  is_archived: false,
  linked_account_id: null,
  linked_liability_id: null,
  is_assignable: group !== 'g-income',
  is_categorizable: true,
})
vi.mock('../../../api/categories', () => ({
  useCategories: () => ({
    data: [
      category('c1', 'Groceries'),
      category('c2', 'Household'),
      category('c3', 'Paycheck', 'g-income'),
    ],
  }),
  useCategoryGroups: () => ({
    data: [
      { id: 'g1', name: 'Everyday' },
      { id: 'g-income', name: 'Income' },
    ],
  }),
}))
vi.mock('../../../api/accounts', () => ({
  useAccounts: () => ({
    data: [{ id: 'acc-1', name: 'Checking', on_budget: h.onBudget, is_closed: false }],
  }),
}))
vi.mock('../../../stores/appStore', () => ({
  useAppStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      currentBudgetId: 'budget-1',
      lastQuickAddAccountId: null,
      setLastQuickAddAccountId: vi.fn(),
      locationEnabled: false,
      privacyMode: h.privacyMode,
    }),
}))
vi.mock('../../../stores/uiStore', () => ({
  useUIStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ quickAddOpen: true, closeQuickAdd: vi.fn() }),
}))
vi.mock('../../../utils/motion', () => ({ prefersReducedMotion: () => h.reducedMotion }))
vi.mock('../../../hooks/useCurrentPosition', () => ({ useCurrentPosition: () => null }))
vi.mock('../../../hooks/useMediaQuery', () => ({
  useIsTouch: () => true,
  useIsMobile: () => true,
}))
vi.mock('../../ai/NLQuickEntry', () => ({ NLQuickEntry: () => null }))
vi.mock('../../../utils/haptics', () => ({ hapticTick: vi.fn() }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))
vi.mock('../../../utils/toastUndo', () => ({ useUndoToast: () => h.notify }))

import { QuickAddSheet } from './QuickAddSheet'
import { today } from '../../../utils/dates'

const THIS_MONTH = `${today().slice(0, 7)}-01`

function month(balances: CategoryBalance[]): BudgetMonth {
  return { category_balances: balances, cards: [] } as unknown as BudgetMonth
}

/** Groceries $240, Household overdrawn to −$12.50, Paycheck an income row. */
const BEFORE = [
  makeCategoryBalance({ category_id: 'c1', available: 240 }),
  makeCategoryBalance({ category_id: 'c2', available: -12.5 }),
  makeCategoryBalance({ category_id: 'c3', assigned: null, available: null }),
]

beforeEach(() => {
  h.qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  h.months = { [THIS_MONTH]: month(BEFORE) }
  h.monthsAfterSave = {}
  h.failAfterSave = false
  h.saved = false
  h.privacyMode = false
  h.reducedMotion = false
  h.onBudget = true
  h.notify.mockReset()
  h.get.mockReset()
  h.get.mockImplementation(async (url: string) => {
    const m = url.match(/^\/budget-1\/months\/(.+)$/)
    if (!m) throw new Error(`unexpected GET ${url}`)
    if (h.saved && h.failAfterSave) throw new Error('offline')
    const served = (h.saved ? h.monthsAfterSave : h.months)[m[1]]
    if (!served) throw new Error(`no month ${m[1]}`)
    return { data: served }
  })
})

function renderSheet() {
  return render(
    <QueryClientProvider client={h.qc}>
      <QuickAddSheet />
    </QueryClientProvider>
  )
}

/** The option row inside the open selection sheet (see the split test for why
 *  the class, not bare text: dismissed sheets linger in jsdom). */
function optionRow(name: string): HTMLElement {
  const label = screen
    .getAllByText(name)
    .find((el) => el.className.includes('selection-sheet__option-label'))
  return label!.closest('button')!
}

async function monthLoaded() {
  await waitFor(() =>
    expect(h.qc.getQueryData([ROOT.budgetMonth, 'budget-1', THIS_MONTH])).toBeTruthy()
  )
}

function chooseCategory(name: string) {
  fireEvent.click(screen.getByLabelText('Category'))
  fireEvent.click(optionRow(name))
}

async function saveOutflow(amount: string) {
  fireEvent.change(screen.getByLabelText('Amount'), { target: { value: amount } })
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(h.notify).toHaveBeenCalled())
  return h.notify.mock.calls[0] as [string | ReactElement, unknown]
}

/** Render what the toast would show, as the Toaster would. */
function renderToast(message: string | ReactElement) {
  expect(isValidElement(message)).toBe(true)
  return render(message as ReactElement).container
}

describe('the category picker', () => {
  it("shows each category's Available as a hint", async () => {
    renderSheet()
    await monthLoaded()
    fireEvent.click(screen.getByLabelText('Category'))
    const hint = (name: string) =>
      optionRow(name).querySelector('.selection-sheet__option-hint')?.textContent
    await waitFor(() => expect(hint('Groceries')).toBe('$240.00'))
    expect(hint('Household')).toBe('-$12.50')
  })

  it('shows no hint for an income category, whose Available is null', async () => {
    renderSheet()
    await monthLoaded()
    fireEvent.click(screen.getByLabelText('Category'))
    await waitFor(() => expect(optionRow('Groceries').textContent).toContain('$240.00'))
    expect(optionRow('Paycheck').querySelector('.selection-sheet__option-hint')).toBeNull()
  })

  it("asks for the month the transaction is dated in, not today's", async () => {
    h.months['2026-01-01'] = month([makeCategoryBalance({ category_id: 'c1', available: 75 })])
    renderSheet()
    fireEvent.change(screen.getByLabelText('Date'), { target: { value: '2026-01-31' } })
    await waitFor(() => expect(h.get).toHaveBeenCalledWith('/budget-1/months/2026-01-01'))
    fireEvent.click(screen.getByLabelText('Category'))
    await waitFor(() =>
      expect(
        optionRow('Groceries').querySelector('.selection-sheet__option-hint')?.textContent
      ).toBe('$75.00')
    )
  })

  it('shows hints for every split leg', async () => {
    renderSheet()
    await monthLoaded()
    fireEvent.click(screen.getByTitle('Split this across categories'))
    fireEvent.click(screen.getByLabelText('Split 2 category'))
    await waitFor(() => expect(optionRow('Household').textContent).toContain('-$12.50'))
    fireEvent.click(optionRow('Household'))
    expect(screen.getByLabelText('Split 2 category').textContent).toContain('Available -$12.50')
  })
})

describe('the category row', () => {
  it('shows Available once payee memory has chosen the category', async () => {
    renderSheet()
    await monthLoaded()
    fireEvent.click(screen.getByText('Choose payee'))
    fireEvent.click(optionRow('Corner Market'))
    const row = screen.getByLabelText('Category')
    expect(row.textContent).toContain('Groceries')
    expect(row.textContent).toContain('Available $240.00')
  })

  it('shows nothing before a category is chosen', async () => {
    renderSheet()
    await monthLoaded()
    expect(screen.getByLabelText('Category').textContent).not.toContain('Available')
  })

  it('shows no Available line for an income category', async () => {
    renderSheet()
    await monthLoaded()
    chooseCategory('Paycheck')
    const row = screen.getByLabelText('Category')
    expect(row.textContent).toContain('Paycheck')
    expect(row.textContent).not.toContain('Available')
  })

  it('fetches no month and offers no category on a tracking account', async () => {
    h.onBudget = false
    renderSheet()
    expect(screen.queryByLabelText('Category')).toBeNull()
    expect(h.get).not.toHaveBeenCalled()
  })
})

describe('the toast after Save', () => {
  it("counts from the loaded figure to the server's new one", async () => {
    // The server's answer is deliberately not 240 − 42: a pending rollover
    // moved it too. The toast must say what the server says.
    h.monthsAfterSave = {
      [THIS_MONTH]: month([makeCategoryBalance({ category_id: 'c1', available: 190 })]),
    }
    renderSheet()
    await monthLoaded()
    chooseCategory('Groceries')
    const [message, target] = await saveOutflow('42')
    expect(target).toBe('latest')
    const toast = renderToast(message)
    expect(toast.textContent).toContain('Added −$42.00')
    expect(toast.textContent).toContain('Groceries')
    expect(toast.textContent).toContain('$240.00')
    // Announced once, as the final figure, while the digits count.
    expect(toast.querySelector('.count-up-money .sr-only')?.textContent).toBe('$190.00')
    await waitFor(
      () =>
        expect(toast.querySelector('.count-up-money [aria-hidden="true"]')?.textContent).toBe(
          '$190.00'
        ),
      { timeout: COUNT_UP_MS * 4 }
    )
    expect(toast.textContent).not.toContain('$198.00')
  })

  it('colours the result as the grid does when the save overspends', async () => {
    h.monthsAfterSave = {
      [THIS_MONTH]: month([makeCategoryBalance({ category_id: 'c1', available: -2 })]),
    }
    h.reducedMotion = true
    renderSheet()
    await monthLoaded()
    chooseCategory('Groceries')
    const toast = renderToast((await saveOutflow('242'))[0])
    expect(toast.querySelector('.available-change-toast__after--negative')).not.toBeNull()
  })

  it('stays calm when the red rode on a card', async () => {
    h.monthsAfterSave = {
      [THIS_MONTH]: month([
        makeCategoryBalance({ category_id: 'c1', available: -2, credit_overspent: 2 }),
      ]),
    }
    h.reducedMotion = true
    renderSheet()
    await monthLoaded()
    chooseCategory('Groceries')
    const toast = renderToast((await saveOutflow('242'))[0])
    expect(toast.querySelector('.available-change-toast__after--negative')).toBeNull()
    expect(toast.querySelector('.available-change-toast__after--negative-on-card')).not.toBeNull()
  })

  it('shows the final figure immediately under reduced motion', async () => {
    h.monthsAfterSave = {
      [THIS_MONTH]: month([makeCategoryBalance({ category_id: 'c1', available: 198 })]),
    }
    h.reducedMotion = true
    renderSheet()
    await monthLoaded()
    chooseCategory('Groceries')
    const toast = renderToast((await saveOutflow('42'))[0])
    expect(toast.querySelector('.count-up-money [aria-hidden="true"]')?.textContent).toBe('$198.00')
  })

  it('shows masked figures without animating them in privacy mode', async () => {
    h.privacyMode = true
    h.monthsAfterSave = {
      [THIS_MONTH]: month([makeCategoryBalance({ category_id: 'c1', available: 198 })]),
    }
    renderSheet()
    await monthLoaded()
    chooseCategory('Groceries')
    const raf = vi.spyOn(window, 'requestAnimationFrame')
    const toast = renderToast((await saveOutflow('42'))[0])
    expect(toast.textContent).not.toMatch(/\d/)
    expect(toast.textContent).toContain('$••••')
    expect(raf).not.toHaveBeenCalled()
    raf.mockRestore()
  })

  it('falls back to the plain sentence when the refetch fails', async () => {
    h.failAfterSave = true
    renderSheet()
    await monthLoaded()
    chooseCategory('Groceries')
    const [message] = await saveOutflow('42')
    expect(message).toBe('Added −$42.00 · Groceries')
  })

  it('falls back when the month never loaded, rather than inventing a before', async () => {
    h.months = {}
    h.monthsAfterSave = {
      [THIS_MONTH]: month([makeCategoryBalance({ category_id: 'c1', available: 198 })]),
    }
    renderSheet()
    await waitFor(() => expect(h.get).toHaveBeenCalled())
    chooseCategory('Groceries')
    const [message] = await saveOutflow('42')
    expect(message).toBe('Added −$42.00 · Groceries')
  })

  it('falls back when the server no longer lists the category', async () => {
    h.monthsAfterSave = { [THIS_MONTH]: month([]) }
    renderSheet()
    await monthLoaded()
    chooseCategory('Groceries')
    const [message] = await saveOutflow('42')
    expect(message).toBe('Added −$42.00 · Groceries')
  })

  it('keeps the plain sentence for an income category', async () => {
    h.monthsAfterSave = { [THIS_MONTH]: month(BEFORE) }
    renderSheet()
    await monthLoaded()
    chooseCategory('Paycheck')
    fireEvent.click(screen.getByRole('radio', { name: 'Received' }))
    const [message] = await saveOutflow('900')
    expect(message).toBe('Added $900.00 · Paycheck')
  })

  it('keeps the plain sentence for a split', async () => {
    h.monthsAfterSave = { [THIS_MONTH]: month(BEFORE) }
    renderSheet()
    await monthLoaded()
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '10' } })
    fireEvent.click(screen.getByTitle('Split this across categories'))
    fireEvent.click(screen.getByLabelText('Split 1 category'))
    fireEvent.click(optionRow('Groceries'))
    fireEvent.click(screen.getByLabelText('Split 2 category'))
    fireEvent.click(optionRow('Household'))
    fireEvent.change(screen.getByLabelText('Split 1 amount'), { target: { value: '6' } })
    fireEvent.change(screen.getByLabelText('Split 2 amount'), { target: { value: '4' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(h.notify).toHaveBeenCalled())
    expect(h.notify.mock.calls[0][0]).toBe('Added −$10.00 · split 2 ways')
  })
})
