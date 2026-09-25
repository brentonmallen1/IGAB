/**
 * Scan and Save with no account chosen.
 *
 * v2026.09.21 stopped pre-selecting the account, and Scan and Save sat
 * disabled until one was picked — greyed out, with nothing on screen saying
 * why, so on a phone it read as "scanning is broken". Both now ask: they open
 * the account picker, choosing one carries on with what was tapped, and a
 * dismissed picker leaves the Account row marked with what is waiting on it.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  submit: vi.fn(),
  create: vi.fn(),
}))

vi.mock('../../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
  apiErrorMessage: (_e: unknown, fallback: string) => fallback,
}))
vi.mock('../../../api/transactions', () => ({
  useCreateTransaction: () => ({ mutateAsync: h.create, isPending: false }),
}))
vi.mock('../../../api/attachments', () => ({
  ATTACHMENT_ACCEPT: '',
  isAttachableFile: () => true,
  isTooLargeToAttach: () => false,
  MAX_ATTACHMENT_LABEL: '10 MB',
  uploadFilesToTransaction: vi.fn(() => Promise.resolve({ failed: [] })),
}))
vi.mock('../../../api/ai', () => ({
  useAIStatus: () => ({ data: { enabled: true, available: false } }),
}))
vi.mock('../../../api/aiJobs', () => ({
  useSubmitReceipt: () => ({ mutateAsync: h.submit, isPending: false }),
}))
vi.mock('../../../api/payees', () => ({
  usePayees: () => ({ data: [] }),
  useNearbyPayees: () => ({ data: [] }),
  useCreatePayee: () => ({ mutateAsync: vi.fn() }),
}))
vi.mock('../../../api/categories', () => ({
  useCategories: () => ({ data: [] }),
  useCategoryGroups: () => ({ data: [] }),
}))
vi.mock('../../../api/accounts', () => ({
  useAccounts: () => ({
    data: [{ id: 'acc-1', name: 'Checking', on_budget: true, is_closed: false }],
  }),
}))
vi.mock('./useCategoryAvailable', () => ({
  useCategoryAvailable: () => ({
    balances: new Map(),
    hintFor: () => undefined,
    readServerBalance: async () => null,
  }),
}))
vi.mock('../../../stores/appStore', () => ({
  useAppStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      currentBudgetId: 'budget-1',
      recentAccountIds: [],
      noteAccountUsed: vi.fn(),
      locationEnabled: false,
      privacyMode: false,
    }),
}))
vi.mock('../../../stores/uiStore', () => ({
  useUIStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ quickAddOpen: true, closeQuickAdd: vi.fn() }),
}))
vi.mock('../../../hooks/useCurrentPosition', () => ({ useCurrentPosition: () => null }))
vi.mock('../../../hooks/useMediaQuery', () => ({
  useIsTouch: () => true,
  useIsMobile: () => true,
}))
vi.mock('../../ai/NLQuickEntry', () => ({ NLQuickEntry: () => null }))
vi.mock('../../../utils/haptics', () => ({ hapticTick: vi.fn() }))
vi.mock('react-hot-toast', () => ({
  default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}))
vi.mock('../../../utils/toastUndo', () => ({ useUndoToast: () => vi.fn() }))

import { QuickAddSheet } from './QuickAddSheet'

/** Which file inputs were opened, in order. */
let opened: HTMLInputElement[] = []

beforeEach(() => {
  h.submit.mockReset()
  h.submit.mockResolvedValue({})
  h.create.mockReset()
  h.create.mockResolvedValue({ id: 'txn-new', account_id: 'acc-1' })
  opened = []
  vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(function (
    this: HTMLInputElement
  ) {
    opened.push(this)
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

function renderSheet() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <QuickAddSheet />
    </QueryClientProvider>
  )
}

const scanButton = () => screen.getByRole('button', { name: /Scan receipt/ })
const accountRow = () =>
  screen
    .getAllByText('Account')
    .find((el) => el.className.includes('quick-add__row-label'))!
    .closest('button')!
const scanInput = () => screen.getByLabelText<HTMLInputElement>('Receipts to scan')

/** The option row inside the open selection sheet — by class, not bare text,
 *  because dismissed sheets linger in jsdom. */
function optionRow(name: string): HTMLElement {
  const label = screen
    .getAllByText(name)
    .find((el) => el.className.includes('selection-sheet__option-label'))
  return label!.closest('button')!
}

describe('Scan receipt before an account is chosen', () => {
  it('is tappable, not disabled, with no account', () => {
    renderSheet()
    expect(scanButton()).not.toBeDisabled()
  })

  it('asks for the account, then goes straight on to the camera', async () => {
    renderSheet()
    fireEvent.click(scanButton())

    // The picker opened instead of the camera.
    expect(opened).toEqual([])
    fireEvent.click(optionRow('Checking'))

    expect(opened).toEqual([scanInput()])
    expect(accountRow()).not.toHaveClass('quick-add__row--asked')

    const receipt = new File(['x'], 'receipt.jpg', { type: 'image/jpeg' })
    fireEvent.change(scanInput(), { target: { files: [receipt] } })
    await waitFor(() =>
      expect(h.submit).toHaveBeenCalledWith({ file: receipt, accountId: 'acc-1' })
    )
  })

  it('marks the Account row when the picker is dismissed unanswered', () => {
    renderSheet()
    fireEvent.click(scanButton())
    // Not while the picker covers it — the pulse would play out of sight.
    expect(accountRow()).not.toHaveClass('quick-add__row--asked')

    fireEvent.keyDown(document, { key: 'Escape' })

    expect(accountRow()).toHaveClass('quick-add__row--asked')
    expect(screen.getByText('Choose account to scan')).toBeInTheDocument()
    expect(opened).toEqual([])
  })

  it('does not open the camera when the account is chosen from its own row later', () => {
    renderSheet()
    fireEvent.click(scanButton())
    fireEvent.keyDown(document, { key: 'Escape' })

    fireEvent.click(accountRow())
    fireEvent.click(optionRow('Checking'))

    // The Scan tap was abandoned with the first picker; picking now is just
    // picking. The mark clears once the question is answered.
    expect(opened).toEqual([])
    expect(accountRow()).not.toHaveClass('quick-add__row--asked')
  })

  it('opens the camera directly once an account is chosen', () => {
    renderSheet()
    fireEvent.click(accountRow())
    fireEvent.click(optionRow('Checking'))

    fireEvent.click(scanButton())

    expect(opened).toEqual([scanInput()])
    expect(accountRow()).not.toHaveClass('quick-add__row--asked')
  })
})

describe('Save before an account is chosen', () => {
  const saveButton = () => screen.getByRole('button', { name: 'Save' })
  const saveAnotherButton = () => screen.getByRole('button', { name: 'Save & add another' })
  const typeAmount = (value: string) =>
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value } })

  it('stays disabled while the amount is missing — asking is only for the account', () => {
    renderSheet()
    expect(saveButton()).toBeDisabled()
    expect(saveAnotherButton()).toBeDisabled()
  })

  it('asks for the account, then saves to it', async () => {
    renderSheet()
    typeAmount('12.50')
    expect(saveButton()).not.toBeDisabled()

    fireEvent.click(saveButton())
    expect(h.create).not.toHaveBeenCalled()
    fireEvent.click(optionRow('Checking'))

    await waitFor(() => expect(h.create).toHaveBeenCalledTimes(1))
    expect(h.create.mock.calls[0][0]).toMatchObject({ account_id: 'acc-1', amount: -12.5 })
  })

  it('carries Save & add another through the same question', async () => {
    renderSheet()
    typeAmount('4.00')
    fireEvent.click(saveAnotherButton())
    fireEvent.click(optionRow('Checking'))

    await waitFor(() => expect(h.create).toHaveBeenCalledTimes(1))
    expect(h.create.mock.calls[0][0]).toMatchObject({ account_id: 'acc-1', amount: -4 })
  })

  it('says what is waiting when the picker is dismissed, and saves nothing', () => {
    renderSheet()
    typeAmount('12.50')
    fireEvent.click(saveButton())
    fireEvent.keyDown(document, { key: 'Escape' })

    expect(accountRow()).toHaveClass('quick-add__row--asked')
    expect(screen.getByText('Choose account to save')).toBeInTheDocument()
    expect(h.create).not.toHaveBeenCalled()
  })

  it('does not save when the account is chosen from its own row later', () => {
    renderSheet()
    typeAmount('12.50')
    fireEvent.click(saveButton())
    fireEvent.keyDown(document, { key: 'Escape' })

    fireEvent.click(accountRow())
    fireEvent.click(optionRow('Checking'))

    expect(h.create).not.toHaveBeenCalled()
    expect(accountRow()).not.toHaveClass('quick-add__row--asked')
  })
})

describe('Scan receipt, deciding the account later', () => {
  const DECIDE_LATER = 'Decide later — it waits in AI Activity'

  it('scans with no account, straight on to the camera', async () => {
    renderSheet()
    fireEvent.click(scanButton())
    fireEvent.click(optionRow(DECIDE_LATER))

    expect(opened).toEqual([scanInput()])
    const receipt = new File(['x'], 'receipt.jpg', { type: 'image/jpeg' })
    fireEvent.change(scanInput(), { target: { files: [receipt] } })
    await waitFor(() => expect(h.submit).toHaveBeenCalledWith({ file: receipt, accountId: null }))
  })

  const offered = () =>
    screen
      .queryAllByText(DECIDE_LATER)
      .filter((el) => el.className.includes('selection-sheet__option-label'))

  it('is not offered when the account row is opened on its own', () => {
    renderSheet()
    fireEvent.click(accountRow())
    expect(offered()).toEqual([])
  })

  it('is not offered when Save is the one asking — a saved row needs its account', () => {
    renderSheet()
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '12.50' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(offered()).toEqual([])
  })
})
