import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ScheduledRow, ScheduledTableHead } from './ScheduledRow'
import { rulesWithContext, stripComments } from '../../../test-utils/cssRules'
import type { ScheduledTransaction } from '../../../types'

vi.mock('../../../hooks/useFormatters', () => ({
  useFormatters: () => ({ formatMoney: (n: number) => `$${n.toFixed(2)}` }),
}))

const base: ScheduledTransaction = {
  id: 's1',
  budget_id: 'b1',
  account_id: 'a1',
  amount: -42.5,
  payee_id: 'p1',
  category_id: 'c1',
  memo: 'water',
  frequency: 'monthly',
  start_date: '2026-01-05',
  end_date: null,
  auto_create: true,
  days_before_reminder: 3,
  next_occurrence_date: '2026-09-10',
  last_created_date: null,
  second_day_of_month: null,
  transfer_account_id: null,
  import_id: null,
  created_at: '',
  updated_at: '',
}

const names = { payee: 'City Water', category: 'Utilities', account: 'Harborstone Checking' }

function renderRow(layout: 'register' | 'table', over: Partial<ScheduledTransaction> = {}) {
  const onEdit = vi.fn()
  const onEnter = vi.fn()
  const onSkip = vi.fn()
  render(
    <ScheduledRow
      scheduled={{ ...base, ...over }}
      names={names}
      layout={layout}
      todayISO="2026-09-08"
      onEdit={onEdit}
      onEnter={onEnter}
      onSkip={onSkip}
    />
  )
  return { onEdit, onEnter, onSkip }
}

describe('ScheduledRow', () => {
  it('renders every cell in both layouts — the stylesheet decides visibility', () => {
    // One DOM: the register and the page cannot drift if they draw the same tree.
    for (const layout of ['register', 'table'] as const) {
      const { unmount } = render(
        <ScheduledRow
          scheduled={base}
          names={names}
          layout={layout}
          todayISO="2026-09-08"
          onEdit={() => {}}
          onEnter={() => {}}
          onSkip={() => {}}
        />
      )
      const row = screen.getByTestId('scheduled-row')
      expect(row.className).toContain(`scheduled-row--${layout}`)
      for (const cell of [
        'account',
        'payee',
        'category',
        'memo',
        'amount',
        'freq',
        'date',
        'auto',
        'actions',
      ]) {
        expect(row.querySelector(`.scheduled-row__${cell}`), cell).not.toBeNull()
      }
      unmount()
    }
  })

  it('signs the amount by direction and says which way', () => {
    renderRow('table')
    const amount = document.querySelector('.scheduled-row__amount')!
    expect(amount.className).toContain('negative')
    expect(amount.textContent).toBe('$42.50 out')
  })

  it('shows the due badge, overdue as a warning', () => {
    // A schedule the nightly job enters itself is never overdue — it only
    // ever reads due-soon — so this one is entered by hand.
    renderRow('register', { next_occurrence_date: '2026-09-06', auto_create: false })
    expect(document.querySelector('.scheduled-row__due--overdue')).not.toBeNull()
  })

  it('edits on the row, and enters or skips without editing', () => {
    const { onEdit, onEnter, onSkip } = renderRow('table')
    fireEvent.click(screen.getByRole('button', { name: 'Enter' }))
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }))
    expect(onEnter).toHaveBeenCalledOnce()
    expect(onSkip).toHaveBeenCalledOnce()
    expect(onEdit).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('scheduled-row'))
    expect(onEdit).toHaveBeenCalledOnce()
  })

  it('waits on both buttons while one is in flight', () => {
    render(
      <ScheduledRow
        scheduled={base}
        names={names}
        layout="table"
        todayISO="2026-09-08"
        onEdit={() => {}}
        onEnter={() => {}}
        onSkip={() => {}}
        busy
      />
    )
    expect(screen.getByRole('button', { name: 'Enter' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Skip' })).toBeDisabled()
  })

  it('draws the page head from the same module', () => {
    render(<ScheduledTableHead />)
    expect(document.querySelector('.scheduled-row__head')?.textContent).toContain('Frequency')
  })
})

/**
 * The differences between the two old copies, kept on purpose and pinned by
 * name (the one-implementation rule's step 5): each of these is a way the
 * register and the page legitimately differ, and the phone card they share.
 */
describe('ScheduledRow stylesheet', () => {
  const css = stripComments(readFileSync(resolve(__dirname, 'ScheduledRow.css'), 'utf8'))
  const rules = rulesWithContext(css)
  const desktop = (sel: string) =>
    rules.find(
      (r) =>
        r.selector
          .split(',')
          .map((s) => s.trim())
          .includes(sel) && !r.atRules.length
    )?.body ?? ''
  const phone = (sel: string) =>
    rules.find(
      (r) =>
        r.selector
          .split(',')
          .map((s) => s.trim())
          .includes(sel) && r.atRules.some((a) => a.includes('max-width: 768px'))
    )?.body ?? ''

  it('register: hides account and auto on desktop (the register knows its account)', () => {
    expect(desktop('.scheduled-row--register .scheduled-row__account')).toMatch(/display:\s*none/)
  })

  it('table: hides category and memo on desktop (the page never showed them)', () => {
    expect(desktop('.scheduled-row--table .scheduled-row__category')).toMatch(/display:\s*none/)
  })

  it('register rows are muted and italic — provisional among real rows', () => {
    const r = desktop('.scheduled-row--register')
    expect(r).toMatch(/font-style:\s*italic/)
    expect(r).toMatch(/color:\s*var\(--text-muted\)/)
  })

  it('the page head shares the table template', () => {
    const head = rules.find(
      (r) =>
        r.selector.includes('.scheduled-row__head') && r.selector.includes('.scheduled-row--table')
    )
    expect(head?.body).toMatch(/grid-template-columns:\s*1\.2fr 1\.2fr 1fr 1fr 1fr 60px auto/)
  })

  it('has one phone card, shared by both layouts', () => {
    const card = phone('.scheduled-row')
    expect(card).toMatch(
      /grid-template-areas:\s*"payee amount"\s*"sub freq"\s*"date auto"\s*"actions actions"/
    )
    expect(phone('.scheduled-row__head')).toMatch(/display:\s*none/)
    expect(phone('.scheduled-row__btn')).toMatch(/min-height:\s*var\(--tap-min\)/)
  })

  it('the phone card second line is the envelope in the register and the account on the page', () => {
    expect(phone('.scheduled-row--register .scheduled-row__category')).toMatch(/display:\s*block/)
    expect(phone('.scheduled-row--register .scheduled-row__account')).toMatch(/display:\s*none/)
  })
})
