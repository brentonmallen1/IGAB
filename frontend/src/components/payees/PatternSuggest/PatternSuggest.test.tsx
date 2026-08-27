import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PatternCandidates, PatternMatchPreview } from './PatternSuggest'
import { patternCandidates } from './patternCandidates'

const NAMES = ['ACH DEPOSIT PAYROLL 88', 'ACH DEPOSIT PAYROLL 99']
const OTHERS = [
  { name: 'ACH WITHDRAWAL 12', mapping_samples: [] },
  { name: 'Rent', mapping_samples: ['ACH DEPOSIT RENT REFUND'] },
]

describe('patternCandidates', () => {
  it('keeps the served order and appends the structural suggestion once', () => {
    expect(patternCandidates(['^A', '^B'], '^C')).toEqual([
      { pattern: '^A', source: 'ai' },
      { pattern: '^B', source: 'ai' },
      { pattern: '^C', source: 'structural' },
    ])
    expect(patternCandidates(['^A'], '^A')).toEqual([{ pattern: '^A', source: 'ai' }])
    expect(patternCandidates([], null)).toEqual([])
  })
})

describe('PatternCandidates', () => {
  it('says how many names each candidate claims, and which other payees it would take', () => {
    render(
      <PatternCandidates
        candidates={[
          { pattern: '^ACH DEPOSIT PAYROLL ', source: 'ai' },
          { pattern: '^ACH', source: 'ai' },
          { pattern: '([bad', source: 'structural' },
        ]}
        value=""
        names={NAMES}
        others={OTHERS}
        onPick={() => {}}
      />
    )
    expect(screen.getByText('matches 2 of 2 · no other payees')).toBeInTheDocument()
    expect(screen.getByText('matches 2 of 2 · also 2 other payees')).toBeInTheDocument()
    expect(screen.getByText('not a valid regular expression')).toBeInTheDocument()
  })

  it('marks the chip that equals the input, and picks on click', async () => {
    const onPick = vi.fn()
    render(
      <PatternCandidates
        candidates={[
          { pattern: '^ACH', source: 'structural' },
          { pattern: 'PAYROLL', source: 'ai' },
        ]}
        value="^ACH"
        names={NAMES}
        others={[]}
        onPick={onPick}
      />
    )
    const pressed = screen.getByRole('button', { pressed: true })
    expect(pressed.textContent).toContain('^ACH')
    await userEvent.click(screen.getByRole('button', { pressed: false }))
    expect(onPick).toHaveBeenCalledWith('PAYROLL')
  })

  it('renders nothing with no candidates', () => {
    const { container } = render(
      <PatternCandidates candidates={[]} value="" names={NAMES} others={[]} onPick={() => {}} />
    )
    expect(container.firstChild).toBeNull()
  })
})

describe('PatternMatchPreview', () => {
  it('highlights the captured part and marks the misses', () => {
    const { container } = render(<PatternMatchPreview pattern="PAYROLL 88" names={NAMES} />)
    expect(container.querySelector('mark')?.textContent).toBe('PAYROLL 88')
    expect(container.querySelectorAll('.pattern-preview__row--match')).toHaveLength(1)
    expect(screen.getByText('no match')).toBeInTheDocument()
  })

  it('renders nothing for an empty or invalid pattern', () => {
    expect(render(<PatternMatchPreview pattern="" names={NAMES} />).container.firstChild).toBeNull()
    expect(render(<PatternMatchPreview pattern="([bad" names={NAMES} />).container.firstChild).toBeNull()
  })
})
