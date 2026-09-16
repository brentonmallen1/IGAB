import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const settings = vi.hoisted(() => ({
  data: undefined as { spread_sinking_funds: boolean } | undefined,
  mutate: vi.fn(),
  isPending: false,
}))

vi.mock('../../../api/reports', () => ({
  useReportSettings: () => ({ data: settings.data }),
  useSetReportSettings: () => ({ mutate: settings.mutate, isPending: settings.isPending }),
}))

import { SpreadSinkingFundsToggle } from './SpreadSinkingFundsToggle'

const toggle = () => screen.getByRole('checkbox', { name: 'Spread yearly bills over 12 months' })

beforeEach(() => {
  settings.data = { spread_sinking_funds: true }
  settings.mutate.mockReset()
  settings.isPending = false
})

describe('SpreadSinkingFundsToggle', () => {
  it('shows the stored setting, with the hint as its description', () => {
    settings.data = { spread_sinking_funds: false }
    render(<SpreadSinkingFundsToggle budgetId="b1" />)
    expect(toggle()).not.toBeChecked()
    expect(toggle()).toHaveAccessibleDescription(/Long-term expense categories count as a twelfth/)
  })

  it('writes the flipped setting on click', async () => {
    render(<SpreadSinkingFundsToggle budgetId="b1" />)
    expect(toggle()).toBeChecked()
    await userEvent.click(toggle())
    expect(settings.mutate).toHaveBeenCalledWith(
      { spread_sinking_funds: false },
      expect.objectContaining({ onError: expect.any(Function) })
    )
  })

  it('toggles from the keyboard', async () => {
    settings.data = { spread_sinking_funds: false }
    render(<SpreadSinkingFundsToggle budgetId="b1" />)
    await userEvent.tab()
    expect(toggle()).toHaveFocus()
    await userEvent.keyboard(' ')
    expect(settings.mutate).toHaveBeenCalledWith({ spread_sinking_funds: true }, expect.anything())
  })

  it('cannot be flipped before the setting has loaded or while it saves', () => {
    settings.data = undefined
    const { rerender } = render(<SpreadSinkingFundsToggle budgetId="b1" />)
    expect(toggle()).toBeDisabled()
    settings.data = { spread_sinking_funds: true }
    settings.isPending = true
    rerender(<SpreadSinkingFundsToggle budgetId="b1" />)
    expect(toggle()).toBeDisabled()
  })
})
