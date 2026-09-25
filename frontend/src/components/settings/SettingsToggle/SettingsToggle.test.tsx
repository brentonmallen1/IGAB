/**
 * The row is the control. Fourteen settings rows put a bare checkbox after
 * their words with no <label>: tapping the words did nothing, and a screen
 * reader heard an unnamed checkbox.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SettingsToggle } from './SettingsToggle'

describe('SettingsToggle', () => {
  it('is a named switch', () => {
    render(<SettingsToggle label="Check for updates" checked={false} onChange={() => {}} />)
    expect(screen.getByRole('switch', { name: /Check for updates/ })).not.toBeChecked()
  })

  it('toggles from a tap on its words, not only on the switch', async () => {
    const onChange = vi.fn()
    render(
      <SettingsToggle
        label="Auto-open last budget"
        desc="Skip the budget selector when opening the app"
        checked={false}
        onChange={onChange}
      />
    )
    await userEvent.click(screen.getByText('Skip the budget selector when opening the app'))
    expect(onChange).toHaveBeenCalledWith(true)
  })

  it('does nothing while disabled', async () => {
    const onChange = vi.fn()
    render(<SettingsToggle label="Wishlist" checked disabled onChange={onChange} />)
    await userEvent.click(screen.getByText('Wishlist'))
    expect(onChange).not.toHaveBeenCalled()
  })
})
