/**
 * Import is enabled before a file is chosen, like every dialog's primary, and
 * says what it needs on press instead of sitting greyed out.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CsvImportDialog } from './CsvImportDialog'
import type { CsvPreview } from '../../../api/imports'

const { importCsv, previewCsv } = vi.hoisted(() => ({ importCsv: vi.fn(), previewCsv: vi.fn() }))
vi.mock('../../../api/imports', () => ({ previewCsv, importCsv }))

function renderDialog() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <CsvImportDialog budgetId="b1" accountId="a1" accountName="Checking" onClose={vi.fn()} />
    </QueryClientProvider>
  )
}

/** Every line of this file is a row already here; two of them uncleared. */
const ALL_MATCHED: CsvPreview = {
  headers: ['Date', 'Description', 'Amount'],
  mapping: { date: 'Date', payee: 'Description', amount: 'Amount' },
  date_format: '%Y-%m-%d',
  total_rows: 3,
  new_rows: 0,
  duplicate_rows: 0,
  matched_rows: 3,
  confirmed_rows: 2,
  review_rows: 0,
  skipped: [],
  sample: [
    {
      line: 2,
      date: '2026-01-03',
      amount: -84.12,
      payee: "TRADER JOE'S #552 SEATTLE WA",
      memo: null,
      category: null,
      outcome: 'matched',
      confirms: true,
    },
  ],
}

describe('CsvImportDialog', () => {
  beforeEach(() => {
    importCsv.mockReset()
    previewCsv.mockReset()
  })

  it('asks for a file when Import is pressed without one', async () => {
    renderDialog()
    await userEvent.click(screen.getByRole('button', { name: 'Import' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Choose a CSV file to import')
    expect(importCsv).not.toHaveBeenCalled()
  })

  it('imports a file whose every line is already here when it would clear some', async () => {
    // The early return used to read `new_rows === 0` as "nothing to do", so a
    // bank file that matched every row could never mark any of them cleared.
    previewCsv.mockResolvedValue(ALL_MATCHED)
    importCsv.mockResolvedValue({
      imported: 0,
      skipped: 0,
      errors: [],
      matched: 3,
      confirmed: 2,
      review: 0,
      batch_id: 'batch-1',
    })
    renderDialog()
    // The dialog renders in a portal, outside the render container.
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await userEvent.upload(input, new File(['x'], 'export.csv', { type: 'text/csv' }))

    expect(await screen.findByText('will clear')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Clear 2 transactions' }))
    expect(importCsv).toHaveBeenCalledOnce()
  })
})
