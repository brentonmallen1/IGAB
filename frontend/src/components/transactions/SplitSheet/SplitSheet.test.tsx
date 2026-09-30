/**
 * The phone's split editor. Quick add and the transaction editor both open
 * it (PhoneSplit), so what a line can do is decided here once.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { SplitDraft } from '../../../stores/transactionEditStore'

vi.mock('../../../hooks/useFormatters', () => ({
  useFormatters: () => ({ formatMoney: (n: number) => `$${n.toFixed(2)}` }),
}))
vi.mock('../../../hooks/useHistoryDismissable', () => ({ useHistoryDismissable: () => {} }))

import { SplitSheet } from './SplitSheet'

const OPTIONS = [
  { id: 'g', label: 'Groceries', hint: '$412.10' },
  { id: 'h', label: 'Household', hint: '$96.40' },
  { id: 'k', label: 'Kids', hint: '$120.00' },
]

const draft = (tempId: string, amount: string, categoryId: string | null): SplitDraft => ({
  tempId,
  amount,
  categoryId,
  memo: '',
})

function Harness({
  initial,
  totalCents = 21437,
  onUnsplit,
}: {
  initial: SplitDraft[]
  totalCents?: number
  onUnsplit?: () => void
}) {
  const [legs, setLegs] = useState(initial)
  return (
    <>
      <SplitSheet
        open
        onClose={() => {}}
        totalCents={totalCents}
        legs={legs}
        onChange={setLegs}
        categoryOptions={OPTIONS}
        canCategorize
        onUnsplit={onUnsplit}
      />
      <div data-testid="legs">{JSON.stringify(legs)}</div>
    </>
  )
}

const legs = () => JSON.parse(screen.getByTestId('legs').textContent!) as SplitDraft[]

/** An option in the open picker — by class: dismissed sheets linger in jsdom. */
function option(name: string) {
  return screen
    .getAllByText(name)
    .find((el) => el.className.includes('selection-sheet__option-label'))!
    .closest('button')!
}

describe('SplitSheet', () => {
  const started = [draft('a', '142.18', 'g'), draft('b', '38.40', 'h')]

  it('keeps the total and what is left in sight', () => {
    render(<Harness initial={started} />)
    expect(screen.getByRole('status').textContent).toBe('$33.79 left')
    expect(screen.getByText('Split $214.37')).toBeTruthy()
  })

  it('gives every line a memo', () => {
    render(<Harness initial={started} />)
    fireEvent.change(screen.getByLabelText('Split 2 memo'), { target: { value: 'Paper towels' } })
    expect(legs()[1].memo).toBe('Paper towels')
  })

  it('offers the lines already in the split first when covering the rest, saying what each becomes', () => {
    render(<Harness initial={started} />)
    fireEvent.click(screen.getByRole('button', { name: 'Cover the remaining $33.79…' }))
    expect(screen.getByText('Add to a line in this split')).toBeTruthy()
    expect(option('Groceries').textContent).toContain('$142.18 → $175.97')
    fireEvent.click(option('Groceries'))
    expect(legs().map((l) => l.amount)).toEqual(['175.97', '38.40'])
    expect(screen.getByRole('status').textContent).toBe('Fully split')
  })

  it('puts it on a new line for an envelope not yet in the split', () => {
    render(<Harness initial={started} />)
    fireEvent.click(screen.getByRole('button', { name: /Cover the remaining/ }))
    fireEvent.click(option('Kids'))
    expect(legs()).toHaveLength(3)
    expect(legs()[2]).toMatchObject({ categoryId: 'k', amount: '33.79' })
  })

  it('does not offer to cover what is already covered', () => {
    render(<Harness initial={[draft('a', '200', 'g'), draft('b', '14.37', 'h')]} />)
    expect(screen.queryByRole('button', { name: /Cover the remaining/ })).toBeNull()
  })

  it('offers to stop splitting only where the host can undo the split', () => {
    const onUnsplit = vi.fn()
    const { unmount } = render(<Harness initial={started} onUnsplit={onUnsplit} />)
    fireEvent.click(screen.getByRole('button', { name: /Don't split/ }))
    expect(onUnsplit).toHaveBeenCalled()
    unmount()
    // A saved split: un-splitting it is not an edit the sheet makes.
    render(<Harness initial={started} />)
    expect(screen.queryByRole('button', { name: /Don't split/ })).toBeNull()
  })
})
