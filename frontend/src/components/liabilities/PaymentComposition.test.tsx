/**
 * The escrow editor's rules, and the total that makes them checkable.
 *
 * The point of the total is that a mortgage statement has one too. Without it
 * there is no way to tell a correct split from a plausible one.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { PaymentComponentInput } from '../../api/liabilities'
import { PaymentComposition } from './PaymentComposition'
import { declaredTotal, invalidComponentIndexes, usableComponents } from './compositionRows'

const money = (n: number) => `$${n.toFixed(2)}`

const row = (over: Partial<PaymentComponentInput> = {}): PaymentComponentInput => ({
  kind: 'tax',
  label: '',
  amount: '410.00',
  ...over,
})

describe('which rows count', () => {
  it('drops a row with no amount, which is someone who changed their mind', () => {
    expect(usableComponents([row(), row({ amount: '' })])).toHaveLength(1)
  })

  it('flags an amount that does not parse rather than booking it as zero', () => {
    // The repo's rule: unparseable input surfaces an error, never a silent 0.
    expect(invalidComponentIndexes([row(), row({ amount: 'lots' })])).toEqual([1])
    expect(invalidComponentIndexes([row({ amount: '-5' })])).toEqual([0])
  })

  it('does not flag a row left blank', () => {
    expect(invalidComponentIndexes([row({ amount: '' })])).toEqual([])
  })
})

describe('the declared bill', () => {
  it('is P&I plus the parts', () => {
    expect(declaredTotal('1896.20', [row({ amount: '410.00' }), row({ amount: '95.00' })])).toBe(
      2401.2
    )
  })

  it('is the payment alone when nothing rides beside it', () => {
    expect(declaredTotal('1896.20', [])).toBe(1896.2)
  })

  it('refuses a total while a part is unreadable', () => {
    // A total missing one of its terms reads as a complete one.
    expect(declaredTotal('1896.20', [row({ amount: 'lots' })])).toBeNull()
  })

  it('refuses a total with no P&I to add to', () => {
    expect(declaredTotal('', [row()])).toBeNull()
  })
})

describe('the editor', () => {
  it('starts empty and says so, since most debts have no escrow', () => {
    render(
      <PaymentComposition
        rows={[]}
        onChange={vi.fn()}
        principalAndInterest="1896.20"
        formatMoney={money}
      />
    )
    expect(screen.getByText(/Leave this empty unless your servicer bills more/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Amount per month')).not.toBeInTheDocument()
  })

  it('shows the bill to hold against a statement', () => {
    render(
      <PaymentComposition
        rows={[row({ amount: '547.80' })]}
        onChange={vi.fn()}
        principalAndInterest="1896.20"
        formatMoney={money}
      />
    )
    expect(screen.getByText('$2444.00')).toBeInTheDocument()
  })

  it('shows no total while a figure is unreadable', () => {
    render(
      <PaymentComposition
        rows={[row({ amount: 'lots' })]}
        onChange={vi.fn()}
        principalAndInterest="1896.20"
        formatMoney={money}
      />
    )
    expect(screen.queryByText(/Your full bill/)).not.toBeInTheDocument()
  })

  it('adds a row on request', async () => {
    const onChange = vi.fn()
    render(
      <PaymentComposition
        rows={[]}
        onChange={onChange}
        principalAndInterest="1896.20"
        formatMoney={money}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: /Add part of the payment/ }))
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ amount: '' })])
  })

  it('removes the row you asked to remove', async () => {
    const onChange = vi.fn()
    render(
      <PaymentComposition
        rows={[row({ label: 'Tax' }), row({ label: 'Insurance', kind: 'insurance' })]}
        onChange={onChange}
        principalAndInterest="1896.20"
        formatMoney={money}
      />
    )
    const removes = screen.getAllByRole('button', { name: /Remove this part/ })
    await userEvent.click(removes[0])
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ label: 'Insurance' })])
  })
})
