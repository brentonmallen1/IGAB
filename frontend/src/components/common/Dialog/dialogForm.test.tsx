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
import { AddAccountModal } from '../../accounts/AddAccountModal'
import { AssetSettingsModal } from '../../assets/AssetSettingsModal'
import { LiabilitySettingsModal } from '../../liabilities/LiabilitySettingsModal'
import { useAppStore } from '../../../stores/appStore'
import { stripComments, topLevelRules } from '../../../test-utils/cssRules'

vi.mock('../../../api/accounts', () => ({
  useCreateAccount: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAccounts: () => ({ data: [] }),
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
