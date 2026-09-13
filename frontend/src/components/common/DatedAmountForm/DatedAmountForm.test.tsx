/**
 * The dated-figure form used to return silently on an amount it could not
 * read: Save did nothing and said nothing. It says so now, beside the button.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DatedAmountForm } from './DatedAmountForm'

beforeEach(async () => {
  // Every test opens a Dialog; drain the deferred history.back() of the last.
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
})

function renderForm() {
  const onSubmit = vi.fn()
  render(
    <DatedAmountForm
      title="Update balance"
      amountLabel="Balance owed"
      pending={false}
      onSubmit={onSubmit}
      onClose={vi.fn()}
    />
  )
  return { onSubmit }
}

describe('DatedAmountForm', () => {
  it('says an empty amount needs filling in, and submits nothing', async () => {
    const { onSubmit } = renderForm()
    const save = screen.getByRole('button', { name: 'Save' })
    expect(save).toBeEnabled()
    await userEvent.click(save)
    expect(screen.getByRole('alert')).toHaveTextContent('Enter an amount of zero or more')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('submits zero — a paid-off balance is a figure, not a blank', async () => {
    const { onSubmit } = renderForm()
    await userEvent.type(screen.getByLabelText('Balance owed'), '0')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSubmit).toHaveBeenCalledWith(0, null)
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('passes the date along when one is given', async () => {
    const { onSubmit } = renderForm()
    await userEvent.type(screen.getByLabelText('Balance owed'), '2690.25')
    await userEvent.type(screen.getByLabelText(/As of/), '2026-08-01')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSubmit).toHaveBeenCalledWith(2690.25, '2026-08-01')
  })
})
