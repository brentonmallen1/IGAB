/**
 * The two dialogs the add-asset flow opens are one form.
 *
 * "Track its balance" opens the New Account form and "Track its value" the
 * valued-asset form, one after the other from the same chooser. Each had its
 * own stylesheet — uppercase labels not tied to their inputs in one, the
 * actions inside the scroll region with a borderless Cancel in the other —
 * so the user saw two unrelated dialogs for one question. Both now draw from
 * DialogForm.css; this holds them to it, so neither can grow a private field
 * or button style again without failing here.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AddAccountModal } from '../../accounts/AddAccountModal'
import { AssetSettingsModal } from '../../assets/AssetSettingsModal'
import { LiabilitySettingsModal } from '../../liabilities/LiabilitySettingsModal'
import { useAppStore } from '../../../stores/appStore'
import { ScheduledTransactionEditor } from '../../scheduled/ScheduledTransactionEditor'
import { DatedAmountForm } from '../DatedAmountForm/DatedAmountForm'
import { MergePreviewModal } from '../../transactions/MergePreviewModal/MergePreviewModal'
import { PayeeMergeModal } from '../../payees/PayeeMergeModal/PayeeMergeModal'
import { CsvImportDialog } from '../../imports/CsvImportDialog/CsvImportDialog'
import type { PayeeWithCount } from '../../../api/payees'
import type { Transaction } from '../../../types'
import { stripComments, topLevelRules } from '../../../test-utils/cssRules'

vi.mock('../../../api/accounts', () => ({
  useCreateAccount: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAccounts: () => ({ data: [] }),
}))
vi.mock('../../../api/categories', () => ({
  useCategories: () => ({ data: [] }),
  useCategoryGroups: () => ({ data: [] }),
}))
vi.mock('../../../api/scheduledTransactions', () => ({
  useCreateScheduledTransaction: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateScheduledTransaction: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteScheduledTransaction: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../../../api/ai', () => ({
  useAIStatus: () => ({ data: { available: false } }),
  useSuggestRegex: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../../../api/accountTypes', () => ({ useAccountTypes: () => ({ data: undefined }) }))
vi.mock('../../../api/assets', () => ({
  useCreateAsset: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateAsset: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteAsset: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../../../api/liabilities', () => ({
  useCreateLiability: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateLiability: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteLiability: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

beforeEach(async () => {
  // Every test opens a Dialog; drain the deferred history.back() of the last.
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
  useAppStore.setState({ currentBudgetId: 'b1' })
})

const FORMS = {
  'the New Account form': () => <AddAccountModal onClose={vi.fn()} initialTypeKey="investment" />,
  'the valued-asset form': () => (
    <AssetSettingsModal budgetId="b1" asset={null} onClose={vi.fn()} />
  ),
  'the liability form': () => (
    <LiabilitySettingsModal budgetId="b1" liability={null} onClose={vi.fn()} />
  ),
}

describe.each(Object.entries(FORMS))('%s', (_, form) => {
  it('is a dialog-form whose fields are the shared field', () => {
    render(form())
    const name = screen.getByLabelText('Name')
    expect(name.closest('form')).toHaveClass('dialog-form')
    expect(name.closest('label')).toHaveClass('dialog-form__field')
  })

  it('keeps its actions in the footer, in the shared buttons', () => {
    render(form())
    const cancel = screen.getByRole('button', { name: 'Cancel' })
    expect(cancel).toHaveClass('dialog-btn', 'dialog-btn--secondary')
    const submit = document.querySelector('button[type="submit"]')!
    expect(submit).toHaveClass('dialog-btn', 'dialog-btn--primary')
    // Outside the form, joined to it by id: the footer is pinned, the form scrolls.
    expect(submit.closest('form')).toBeNull()
    expect(submit.getAttribute('form')).toBe(document.querySelector('form.dialog-form')!.id)
  })
})

// ─── Sweep C: the scheduled, dated-figure, merge and import dialogs ─────────

/** Forms whose fields are the shared field, keyed by a label they carry. */
const SWEEP_C_FORMS = {
  'the scheduled-transaction editor': {
    label: 'Memo',
    submit: 'Create',
    render: () => <ScheduledTransactionEditor budgetId="b1" existing={null} onClose={vi.fn()} />,
  },
  'the dated-figure form': {
    label: 'Balance owed',
    submit: 'Save',
    render: () => (
      <DatedAmountForm
        title="Update balance"
        amountLabel="Balance owed"
        pending={false}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />
    ),
  },
}

describe.each(Object.entries(SWEEP_C_FORMS))('%s', (_, form) => {
  it('is a dialog-form whose fields are the shared field', () => {
    render(form.render())
    const field = screen.getByLabelText(form.label)
    expect(field.closest('form')).toHaveClass('dialog-form')
    expect(field.closest('label')).toHaveClass('dialog-form__field')
  })

  it('submits from the footer with an enabled shared primary', () => {
    render(form.render())
    const submit = screen.getByRole('button', { name: form.submit })
    expect(submit).toHaveClass('dialog-btn', 'dialog-btn--primary')
    expect(submit).toBeEnabled()
    expect(submit.closest('form')).toBeNull()
    expect(submit.getAttribute('form')).toBe(document.querySelector('form.dialog-form')!.id)
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveClass('dialog-btn--secondary')
  })
})

const txn = (id: string, created: string) =>
  ({
    id,
    date: '2026-08-01',
    amount: -42,
    payee_id: null,
    category_id: null,
    memo: null,
    import_id: null,
    import_description: null,
    sync_id: null,
    cleared: 'uncleared',
    created_at: created,
  }) as unknown as Transaction

const mergePayees = [
  { id: 'p1', name: 'Harborstone', transaction_count: 3, mapping_samples: [] },
  { id: 'p2', name: 'HARBORSTONE 01', transaction_count: 1, mapping_samples: [] },
] as unknown as PayeeWithCount[]

/** Dialogs with no form of their own whose actions are still the shared footer. */
const SWEEP_C_FOOTERS = {
  'the transaction merge preview': {
    primary: 'Merge',
    render: () => (
      <MergePreviewModal
        transactions={[txn('t1', '2026-08-01T00:00:00Z'), txn('t2', '2026-08-02T00:00:00Z')]}
        payeeMap={new Map()}
        categoryMap={new Map()}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        isPending={false}
      />
    ),
  },
  'the payee merge': {
    primary: 'Merge 2 payees',
    render: () => (
      <PayeeMergeModal
        payees={mergePayees}
        allPayees={mergePayees}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        isPending={false}
      />
    ),
  },
  'the CSV import': {
    primary: 'Import',
    render: () => (
      <QueryClientProvider client={new QueryClient()}>
        <CsvImportDialog budgetId="b1" accountId="a1" accountName="Checking" onClose={vi.fn()} />
      </QueryClientProvider>
    ),
  },
}

describe.each(Object.entries(SWEEP_C_FOOTERS))('%s', (_, dialog) => {
  it('ends its footer with Cancel and an enabled shared primary', () => {
    render(dialog.render())
    const cancel = screen.getByRole('button', { name: 'Cancel' })
    const primary = screen.getByRole('button', { name: dialog.primary })
    expect(cancel).toHaveClass('dialog-btn', 'dialog-btn--secondary')
    expect(primary).toHaveClass('dialog-btn', 'dialog-btn--primary')
    expect(primary).toBeEnabled()
    const end = primary.closest('.dialog-actions__end')
    expect(end).not.toBeNull()
    expect(end).toContainElement(cancel)
    expect(end!.closest('.dialog-actions')).not.toBeNull()
  })
})

describe('DialogForm.css', () => {
  const css = stripComments(readFileSync(resolve(__dirname, 'DialogForm.css'), 'utf8'))
  // Selectors with whitespace collapsed: prettier breaks a long :where() over lines.
  const rules = topLevelRules(css).map(([sel, body]) => [sel.replace(/\s+/g, ' ').trim(), body])

  it('styles text controls and leaves checkboxes their native box', () => {
    const control = rules.find(([sel]) => sel.endsWith('select, textarea )'))
    expect(control?.[0]).toMatch(/:not\(\[type="checkbox"\], \[type="radio"\]/)
    expect(control?.[1]).toMatch(/border:\s*1px solid var\(--input-border\)/)
  })

  it('focuses a field on the input focus-ring token', () => {
    const focus = rules.find(([sel]) => sel.endsWith('textarea ):focus'))
    expect(focus?.[1]).toMatch(/border-color:\s*var\(--input-focus-ring\)/)
  })
})
