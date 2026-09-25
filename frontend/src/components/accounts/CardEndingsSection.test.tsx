import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

const create = vi.hoisted(() => vi.fn())
const update = vi.hoisted(() => vi.fn())
const remove = vi.hoisted(() => vi.fn())

vi.mock('../../api/cardEndings', () => ({
  useCardEndings: () => ({
    data: [
      { id: 'e1', account_id: 'sapphire', last4: '4417', label: "Jane's card" },
      { id: 'e2', account_id: 'sapphire', last4: '9021', label: 'Apple Pay' },
      { id: 'e3', account_id: 'harborstone', last4: '5520', label: null },
    ],
  }),
  useCreateCardEnding: () => ({ mutate: create, isPending: false }),
  useUpdateCardEnding: () => ({ mutate: update, isPending: false }),
  useDeleteCardEnding: () => ({ mutate: remove, isPending: false }),
}))

import { CardEndingsSection } from './CardEndingsSection'

beforeEach(() => {
  create.mockClear()
  update.mockClear()
  remove.mockClear()
})

const renderSection = () => render(<CardEndingsSection budgetId="b1" accountId="sapphire" />)

describe('CardEndingsSection', () => {
  it("lists every card on this account, and no other account's", () => {
    renderSection()
    expect(screen.getByText('•••• 4417')).toBeTruthy()
    expect(screen.getByText('Apple Pay')).toBeTruthy()
    expect(screen.queryByText('•••• 5520')).toBeNull()
  })

  it('adds one, keeping only digits', () => {
    renderSection()
    fireEvent.click(screen.getByRole('button', { name: 'Add a card ending' }))
    fireEvent.change(screen.getByLabelText('Last four digits'), { target: { value: '33-08x9' } })
    expect((screen.getByLabelText('Last four digits') as HTMLInputElement).value).toBe('3308')
    fireEvent.change(screen.getByLabelText('Label'), { target: { value: '  Replacement ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(create.mock.calls[0][0]).toEqual({
      account_id: 'sapphire',
      last4: '3308',
      label: 'Replacement',
    })
  })

  it('refuses fewer than four digits without calling the server', () => {
    renderSection()
    fireEvent.click(screen.getByRole('button', { name: 'Add a card ending' }))
    fireEvent.change(screen.getByLabelText('Last four digits'), { target: { value: '441' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(screen.getByText('Enter the last four digits.')).toBeTruthy()
    expect(create).not.toHaveBeenCalled()
  })

  it('Enter saves the ending and does not submit the settings form around it', () => {
    const submit = vi.fn((e: Event) => e.preventDefault())
    render(
      <form onSubmit={(e) => submit(e.nativeEvent)}>
        <CardEndingsSection budgetId="b1" accountId="sapphire" />
      </form>
    )
    fireEvent.click(screen.getByRole('button', { name: 'Add a card ending' }))
    const input = screen.getByLabelText('Last four digits')
    fireEvent.change(input, { target: { value: '3308' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(create).toHaveBeenCalledTimes(1)
    expect(submit).not.toHaveBeenCalled()
  })

  it('edits and removes a row', () => {
    renderSection()
    fireEvent.click(screen.getByRole('button', { name: 'Edit card ending 9021' }))
    fireEvent.change(screen.getByLabelText('Label'), { target: { value: 'Google Pay' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(update.mock.calls[0][0]).toEqual({ id: 'e2', last4: '9021', label: 'Google Pay' })

    fireEvent.click(screen.getByRole('button', { name: 'Remove card ending 4417' }))
    expect(remove.mock.calls[0][0]).toBe('e1')
  })
})
