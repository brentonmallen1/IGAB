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
import { fireEvent, render, screen } from '@testing-library/react'
import { AddAccountModal } from '../../accounts/AddAccountModal'
import { AssetSettingsModal } from '../../assets/AssetSettingsModal'
import { LiabilitySettingsModal } from '../../liabilities/LiabilitySettingsModal'
import { CardPaymentModal } from '../../accounts/CardPaymentModal'
import { CloneBudgetModal } from '../../budgets/CloneBudgetModal'
import { TargetEditor } from '../../budget/TargetEditor'
import { BudgetFilterModal } from '../../budget/BudgetFilterModal/BudgetFilterModal'
import { BudgetViewModal } from '../../budget/BudgetViewModal/BudgetViewModal'
import { useAppStore } from '../../../stores/appStore'
import { stripComments, topLevelRules } from '../../../test-utils/cssRules'

vi.mock('../../../api/accounts', () => ({
  useCreateAccount: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAccounts: () => ({
    data: [
      {
        id: 'chk',
        name: 'Harborstone Checking',
        on_budget: true,
        classification: 'asset',
        balance: 900,
      },
      {
        id: 'card',
        name: 'Sapphire Visa',
        on_budget: true,
        classification: 'liability',
        balance: -240,
      },
    ],
  }),
}))
vi.mock('../../../api/budgets', () => ({ useBudgetMonth: () => ({ data: undefined }) }))
vi.mock('../../../api/transactions', () => ({
  useCreateTransaction: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../../../api/budgetSnapshots', () => ({
  useCloneBudget: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../../../utils/toastUndo', () => ({ useUndoToast: () => vi.fn() }))
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
  useLiabilities: () => ({ data: [] }),
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

/**
 * The dialogs converted after the add-asset three. They have no one field in
 * common to look up by name, so the contract is structural: every text control
 * is inside a dialog-form, every footer button is a dialog-btn, and a primary
 * submit is enabled while nothing is pending — it answers an empty form with a
 * sentence, not a greyed-out button.
 */
const CONVERTED = {
  'the card payment form': () => (
    <CardPaymentModal budgetId="b1" accountId="card" onClose={vi.fn()} />
  ),
  'the copy-budget form': () => (
    <CloneBudgetModal budgetId="b1" budgetName="Household" onClose={vi.fn()} />
  ),
  ...FORMS,
}

describe.each(Object.entries(CONVERTED))('%s, structurally', (_, form) => {
  it('puts every text control inside a dialog-form', () => {
    render(form())
    const controls = document.querySelectorAll(
      'input:not([type="checkbox"], [type="radio"], [type="hidden"]), select, textarea'
    )
    expect(controls.length).toBeGreaterThan(0)
    for (const c of controls) expect(c.closest('.dialog-form')).not.toBeNull()
  })

  it('draws every footer button as a shared button, the submit enabled', () => {
    render(form())
    const buttons = document.querySelectorAll('.dialog-actions button')
    expect(buttons.length).toBeGreaterThan(0)
    for (const b of buttons) expect(b).toHaveClass('dialog-btn')
    const submit = document.querySelector('.dialog-actions button[type="submit"]')
    expect(submit).toHaveClass('dialog-btn--primary')
    expect(submit).toBeEnabled()
  })

  it('nests no form inside another', () => {
    render(form())
    expect(document.querySelectorAll('form form')).toHaveLength(0)
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

  it('aligns a multi-line choice to its first line (sweep A)', () => {
    const multi = rules.find(([sel]) => sel === '.dialog-form__field--multiline')
    expect(multi?.[1]).toMatch(/align-items:\s*flex-start/)
  })

  it('focuses a field on the input focus-ring token', () => {
    const focus = rules.find(([sel]) => sel.endsWith('textarea ):focus'))
    expect(focus?.[1]).toMatch(/border-color:\s*var\(--input-focus-ring\)/)
  })
})

/* ─── sweep B: the budget page's dialogs ─────────────────────────────────── */

// The target editor, the filter editor and the view editor each hand-rolled
// their labels, inputs and three different footers — the view editor's name
// field had no label at all, and two of the three disabled Save (or relied on
// a browser `required` bubble) instead of saying what was missing.
vi.mock('../../../api/targets', () => ({
  useUpsertTarget: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteTarget: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../../../api/categories', () => ({
  useCategoryGroups: () => ({ data: [] }),
  useCategories: () => ({ data: [] }),
}))
vi.mock('../../../api/tags', () => ({
  useTags: () => ({ data: [] }),
  useCreateTag: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
const createFilter = vi.hoisted(() => vi.fn())
vi.mock('../../../api/budgetFilters', () => ({
  useBudgetFilters: () => ({ data: [] }),
  useCreateBudgetFilter: () => ({ mutateAsync: createFilter, isPending: false }),
  useUpdateBudgetFilter: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteBudgetFilter: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
const createView = vi.hoisted(() => vi.fn())
vi.mock('../../../api/budgetViews', () => ({
  useBudgetViews: () => ({ data: [] }),
  useCreateBudgetView: () => ({ mutateAsync: createView, isPending: false }),
  useUpdateBudgetView: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteBudgetView: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

const BUDGET_FORMS = {
  'the target editor': {
    render: () => (
      <TargetEditor categoryId="c1" categoryName="Groceries" existing={null} onClose={vi.fn()} />
    ),
    field: 'Amount',
    missing: /Enter an amount/,
    mutate: null,
  },
  'the filter editor': {
    render: () => <BudgetFilterModal budgetId="b1" filterId={null} onClose={vi.fn()} />,
    field: 'Filter name',
    missing: /Give this filter a name/,
    mutate: createFilter,
  },
  'the view editor': {
    render: () => <BudgetViewModal budgetId="b1" viewId={null} onClose={vi.fn()} />,
    field: 'View name',
    missing: /Give this view a name/,
    mutate: createView,
  },
}

describe.each(Object.entries(BUDGET_FORMS))('%s', (_, form) => {
  it('is a dialog-form whose first field is the shared, labelled field', () => {
    render(form.render())
    const field = screen.getByLabelText(form.field)
    expect(field.closest('form')).toHaveClass('dialog-form')
    expect(field.closest('label')).toHaveClass('dialog-form__field')
  })

  it('keeps its actions in the footer, in the shared buttons', () => {
    render(form.render())
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveClass(
      'dialog-btn',
      'dialog-btn--secondary'
    )
    const submit = document.querySelector('button[type="submit"]')!
    expect(submit).toHaveClass('dialog-btn', 'dialog-btn--primary')
    expect(submit.closest('form')).toBeNull()
    expect(submit.getAttribute('form')).toBe(document.querySelector('form.dialog-form')!.id)
  })

  it('leaves Save enabled when empty and says what is missing on submit', async () => {
    render(form.render())
    const submit = document.querySelector<HTMLButtonElement>('button[type="submit"]')!
    expect(submit).toBeEnabled()
    fireEvent.submit(document.querySelector('form.dialog-form')!)
    const error = await screen.findByText(form.missing)
    expect(error).toHaveClass('dialog-form__error')
    if (form.mutate) expect(form.mutate).not.toHaveBeenCalled()
  })
})
