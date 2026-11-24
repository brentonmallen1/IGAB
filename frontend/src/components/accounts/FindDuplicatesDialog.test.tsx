/**
 * The scan asks what to look through before it looks. Unasked, it compared
 * every row in the account with every other — any age, reconciled or not.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { FindDuplicatesDialog } from './FindDuplicatesDialog'
import { DEFAULT_DUPLICATE_SCAN_SCOPE } from './duplicateScan'

beforeEach(async () => {
  // Dialog pushes a history entry; let the last test's unwind first.
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
})

function renderDialog(over: Partial<Parameters<typeof FindDuplicatesDialog>[0]> = {}) {
  const onScan = vi.fn()
  render(
    <FindDuplicatesDialog
      accountName="Harborstone Checking"
      initial={DEFAULT_DUPLICATE_SCAN_SCOPE}
      onScan={onScan}
      onClose={vi.fn()}
      isPending={false}
      {...over}
    />
  )
  return onScan
}

describe('FindDuplicatesDialog', () => {
  it('opens on the narrow reading: 90 days, nothing reconciled', () => {
    const onScan = renderDialog()
    expect((screen.getByLabelText('How far back') as HTMLSelectElement).value).toBe('90')
    expect(
      (screen.getByLabelText('Include reconciled transactions') as HTMLInputElement).checked
    ).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: 'Find' }))
    expect(onScan).toHaveBeenCalledWith({ lookbackDays: 90, includeReconciled: false })
  })

  it('sends what was chosen, all time included', () => {
    const onScan = renderDialog()
    fireEvent.change(screen.getByLabelText('How far back'), { target: { value: 'all' } })
    fireEvent.click(screen.getByLabelText('Include reconciled transactions'))
    fireEvent.click(screen.getByRole('button', { name: 'Find' }))
    expect(onScan).toHaveBeenCalledWith({ lookbackDays: null, includeReconciled: true })
  })

  it('opens on the scope used last time', () => {
    renderDialog({ initial: { lookbackDays: 365, includeReconciled: true } })
    expect((screen.getByLabelText('How far back') as HTMLSelectElement).value).toBe('365')
    expect(
      (screen.getByLabelText('Include reconciled transactions') as HTMLInputElement).checked
    ).toBe(true)
  })

  it('says what including reconciled rows does and does not do', () => {
    renderDialog()
    expect(screen.getByText(/Reconciled transactions are left out/)).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Include reconciled transactions'))
    expect(screen.getByText(/two reconciled ones cannot be merged/)).toBeInTheDocument()
  })

  it('cannot be sent twice while it is looking', () => {
    renderDialog({ isPending: true })
    expect(screen.getByRole('button', { name: 'Looking…' })).toBeDisabled()
  })
})
