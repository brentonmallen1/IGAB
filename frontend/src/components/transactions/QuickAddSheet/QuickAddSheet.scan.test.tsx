/**
 * Scan receipt with no account chosen.
 *
 * v2026.09.21 stopped pre-selecting the account, and Scan sat disabled until
 * one was picked — greyed out, with nothing on screen saying why, so on a
 * phone it read as "scanning is broken". Scan now asks: it opens the account
 * picker, choosing one goes straight on to the camera, and a dismissed picker
 * leaves the Account row marked with what Scan is waiting for.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  submit: vi.fn(),
}))

vi.mock('../../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
  apiErrorMessage: (_e: unknown, fallback: string) => fallback,
}))
vi.mock('../../../api/transactions', () => ({
  useCreateTransaction: () => ({ mutateAsync: vi.fn(), isPending: false }),
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
