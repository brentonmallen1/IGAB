/**
 * The checklist's rows as a person meets them: a row counted through another
 * tag is ticked, locked and says why.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { MembershipCategory } from '../../api/tags'
import { makeMembershipRow as row } from '../../test-utils/factories'
import { CategoryMembershipList } from './CategoryMembershipList'
import { initialDraft } from './membershipList'

function show(rows: MembershipCategory[], savingsTag = false) {
  const onChange = vi.fn()
  render(
    <CategoryMembershipList
      rows={rows}
      draft={initialDraft(rows)}
      onChange={onChange}
      savingsTag={savingsTag}
      label="Categories tagged Cost of living"
      fillsSheet
    />
  )
  return onChange
}

describe('CategoryMembershipList', () => {
  it('draws an implied row ticked, disabled and labelled with the tag it counts through', () => {
    const onChange = show([
      row({ id: 'rent', name: 'Rent', group_name: 'Bills', implied_by: 'Essential' }),
      row({ id: 'gym', name: 'Gym', group_name: 'Bills' }),
    ])

    const rent = screen.getByRole('checkbox', { name: /Rent/ })
    expect(rent).toBeChecked()
    expect(rent).toBeDisabled()
    expect(rent).toHaveAccessibleName('Rent, Bills, counted through Essential')
    fireEvent.click(rent)
    expect(onChange).not.toHaveBeenCalled()

    const gym = screen.getByRole('checkbox', { name: /Gym/ })
    expect(gym).not.toBeChecked()
    expect(gym).toBeEnabled()
    expect(screen.getAllByText(/counted through/)).toHaveLength(1)
  })

  it('locks a row that carries the tag and is implied too', () => {
    show([row({ id: 'water', name: 'Water', member: true, implied_by: 'Essential' })])
    const water = screen.getByRole('checkbox', { name: /Water.*counted through Essential/ })
    expect(water).toBeChecked()
    expect(water).toBeDisabled()
  })

  it('offers no savings mode on an implied row of a savings tag', () => {
    show(
      [
        row({
          id: 'fund',
          name: 'Emergency Fund',
          savings_role: 'kept_here',
          implied_by: 'Emergency fund',
        }),
        row({ id: 'general', name: 'General Savings', member: true, savings_role: 'sent_out' }),
      ],
      true
    )
    expect(
      screen.getByRole('checkbox', { name: /Emergency Fund.*counted through Emergency fund/ })
    ).toBeDisabled()
    expect(
      screen.queryByRole('combobox', { name: 'Emergency Fund counts as saved' })
    ).not.toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'General Savings counts as saved' })).toBeEnabled()
  })

  it('fills the sheet only when the caller says it is the whole body', () => {
    const { container, rerender } = render(
      <CategoryMembershipList
        rows={[]}
        draft={initialDraft([])}
        onChange={vi.fn()}
        savingsTag={false}
        label="Envelopes"
        fillsSheet={false}
      />
    )
    expect(container.firstElementChild).not.toHaveClass('membership-list--fill')
    rerender(
      <CategoryMembershipList
        rows={[]}
        draft={initialDraft([])}
        onChange={vi.fn()}
        savingsTag={false}
        label="Envelopes"
        fillsSheet
      />
    )
    expect(container.firstElementChild).toHaveClass('membership-list--fill')
  })
})
