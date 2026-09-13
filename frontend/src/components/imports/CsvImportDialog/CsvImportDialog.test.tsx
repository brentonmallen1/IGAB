/**
 * Import is enabled before a file is chosen, like every dialog's primary, and
 * says what it needs on press instead of sitting greyed out.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CsvImportDialog } from './CsvImportDialog'

const { importCsv } = vi.hoisted(() => ({ importCsv: vi.fn() }))
vi.mock('../../../api/imports', () => ({ previewCsv: vi.fn(), importCsv }))

describe('CsvImportDialog', () => {
  it('asks for a file when Import is pressed without one', async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <CsvImportDialog budgetId="b1" accountId="a1" accountName="Checking" onClose={vi.fn()} />
      </QueryClientProvider>
    )
    await userEvent.click(screen.getByRole('button', { name: 'Import' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Choose a CSV file to import')
    expect(importCsv).not.toHaveBeenCalled()
  })
})
