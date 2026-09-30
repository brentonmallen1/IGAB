/**
 * The desktop scan is the phone's hand-off: queue the receipt and close.
 * It used to require an account (a greyed-out Scan with nothing saying why)
 * and then sit polling the job until the model finished.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({ submit: vi.fn(), success: vi.fn(), error: vi.fn() }))

vi.mock('../../../api/aiJobs', () => ({
  useSubmitReceipt: () => ({ mutateAsync: h.submit, isPending: false }),
}))
vi.mock('react-hot-toast', () => ({ default: { success: h.success, error: h.error } }))

import { ReceiptScanTab } from './ReceiptScanTab'

const receipt = new File(['x'], 'receipt.jpg', { type: 'image/jpeg' })

function renderTab(accountId: string, aiEnabled = true) {
  const onQueued = vi.fn()
  const { container } = render(
    <MemoryRouter>
      <ReceiptScanTab
        budgetId="b1"
        accountId={accountId}
        aiEnabled={aiEnabled}
        onQueued={onQueued}
        onClose={vi.fn()}
      />
    </MemoryRouter>
  )
  const input = container.querySelector('input[type="file"]')
  if (input) fireEvent.change(input, { target: { files: [receipt] } })
  return onQueued
}

const scan = () => screen.getByRole('button', { name: /Scan receipt/ })

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => 'blob:preview')
  URL.revokeObjectURL = vi.fn()
  h.submit.mockReset()
  h.submit.mockResolvedValue({ id: 'job-1' })
  h.success.mockClear()
  h.error.mockClear()
})

describe('ReceiptScanTab', () => {
  it('queues into the chosen account and hands back at once', async () => {
    const onQueued = renderTab('acc-1')
    fireEvent.click(scan())
    await waitFor(() => expect(onQueued).toHaveBeenCalled())
    expect(h.submit).toHaveBeenCalledWith({ file: receipt, accountId: 'acc-1' })
    expect(h.success).toHaveBeenCalledWith(
      expect.stringMatching(/show up in your transactions to review/),
      expect.anything()
    )
  })

  it('scans with no account, and says where it will wait', async () => {
    const onQueued = renderTab('')
    expect(scan()).not.toBeDisabled()
    expect(screen.getByText(/waits in AI Activity until you pick one/)).toBeTruthy()
    fireEvent.click(scan())
    await waitFor(() => expect(onQueued).toHaveBeenCalled())
    expect(h.submit).toHaveBeenCalledWith({ file: receipt, accountId: null })
  })

  it('keeps the photo when queuing fails', async () => {
    h.submit.mockRejectedValue(new Error('offline'))
    const onQueued = renderTab('acc-1')
    fireEvent.click(scan())
    await waitFor(() => expect(h.error).toHaveBeenCalled())
    expect(onQueued).not.toHaveBeenCalled()
    expect(scan()).toBeTruthy()
  })

  it('points at Settings when AI is not set up', () => {
    renderTab('acc-1', false)
    expect(screen.getByText(/Configure AI/)).toBeTruthy()
  })
})
