/**
 * Replacing a budget is the most destructive thing in Settings, and the only
 * thing standing in front of it is typing the budget's name. These pin that
 * gate across the move from a hand-rolled overlay to common/Dialog.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { SnapshotInspection } from '../../../api/budgetSnapshots'

const hooks = vi.hoisted(() => ({
  restore: vi.fn(),
  files: [] as { name: string; size_bytes: number; modified_at: string }[],
}))

vi.mock('../../../api/budgetSnapshots', () => ({
  useBudgetSnapshots: () => ({ data: hooks.files, isLoading: false }),
  useCreateBudgetSnapshot: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteBudgetSnapshot: () => ({ mutate: vi.fn() }),
  useImportSnapshot: () => ({ mutate: vi.fn(), isPending: false }),
  useRestoreSnapshot: () => ({ mutateAsync: hooks.restore, isPending: false }),
  downloadBudgetExport: vi.fn(),
  downloadKeptSnapshot: vi.fn(),
  downloadSnapshotNow: vi.fn(),
  inspectSnapshot: vi.fn(async () => INSPECTION),
  tooLargeMessage: () => null,
}))

import { BudgetSnapshotsPanel } from './BudgetSnapshotsPanel'

const INSPECTION: SnapshotInspection = {
  format: 'igab-budget-snapshot',
  format_version: 1,
  alembic_revision: 'a1b2c3d4e5f6',
  app_version: '2026.08.30',
  exported_at: '2026-08-30T10:00:00Z',
  budget_name: 'Household',
  source_budget_id: 'b1',
  row_counts: { transactions: 120, categories: 30 },
  attachments_omitted: 0,
  ok: true,
  refusals: [],
  warnings: [],
}

beforeEach(async () => {
  // Overlays balance their history entry with a deferred history.back(); drain
  // it so a stale pop cannot close the next test's dialog.
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
  hooks.restore.mockReset()
  hooks.restore.mockResolvedValue({ attachments_dropped: 0 })
  hooks.files = []
})

async function openRestoreDialog() {
  render(<BudgetSnapshotsPanel budgetId="b1" budgetName="Household" />)
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  await userEvent.upload(input, new File(['x'], 'household.igab.zip', { type: 'application/zip' }))
  await userEvent.click(await screen.findByRole('button', { name: /Replace/ }))
}

const replaceBtn = () => screen.getByRole('button', { name: 'Replace this budget' })

describe('restoring a budget from a file', () => {
  it('refuses until the budget name is typed exactly', async () => {
    await openRestoreDialog()
    expect(replaceBtn()).toBeDisabled()

    await userEvent.type(screen.getByLabelText('Budget name'), 'Househol')
    expect(replaceBtn()).toBeDisabled()

    await userEvent.type(screen.getByLabelText('Budget name'), 'd')
    expect(replaceBtn()).toBeEnabled()
  })

  it('is case-sensitive — a near miss is still a miss', async () => {
    await openRestoreDialog()
    await userEvent.type(screen.getByLabelText('Budget name'), 'household')
    expect(replaceBtn()).toBeDisabled()
  })

  it('passes the typed name and the pre-snapshot choice through', async () => {
    await openRestoreDialog()
    await userEvent.type(screen.getByLabelText('Budget name'), 'Household')
    await userEvent.click(replaceBtn())
    expect(hooks.restore).toHaveBeenCalledWith(
      expect.objectContaining({ confirmName: 'Household', preSnapshot: true })
    )
  })

  it('offers to snapshot the current state first, ticked by default', async () => {
    await openRestoreDialog()
    const box = screen.getByRole('checkbox')
    expect(box).toBeChecked()
    await userEvent.click(box)
    await userEvent.type(screen.getByLabelText('Budget name'), 'Household')
    await userEvent.click(replaceBtn())
    expect(hooks.restore).toHaveBeenCalledWith(expect.objectContaining({ preSnapshot: false }))
  })

  it('cancelling runs nothing', async () => {
    await openRestoreDialog()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(hooks.restore).not.toHaveBeenCalled()
    expect(screen.queryByLabelText('Budget name')).toBeNull()
  })
})

describe('the snapshots panel layout', () => {
  it('groups its actions rather than stacking four look-alike rows', async () => {
    render(<BudgetSnapshotsPanel budgetId="b1" budgetName="Household" />)
    const titles = [...document.querySelectorAll('.settings-subsection__title')].map(
      (n) => n.textContent
    )
    expect(titles).toEqual(['Download a copy', 'Snapshots on the server', 'Restore from a file'])
  })

  it('gives every action a visible button — bare .settings-btn paints nothing', async () => {
    render(<BudgetSnapshotsPanel budgetId="b1" budgetName="Household" />)
    const bare = [...document.querySelectorAll('button.settings-btn')].filter(
      (b) => !/settings-btn--/.test(b.className)
    )
    expect(bare).toEqual([])
  })

  it('reports a kept snapshot’s size through the one formatter', () => {
    hooks.files = [
      {
        name: 'household-2026-08-30.igab.zip',
        size_bytes: 3 * 1024 ** 3,
        modified_at: '2026-08-30T10:00:00Z',
      },
    ]
    render(<BudgetSnapshotsPanel budgetId="b1" budgetName="Household" />)
    // The panel's own copy stopped at MB and would have said "3072.0 MB".
    expect(screen.getByText('3.00 GB')).toBeInTheDocument()
  })
})
