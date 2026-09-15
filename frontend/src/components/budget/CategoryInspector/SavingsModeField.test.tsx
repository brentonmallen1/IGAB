/**
 * "Counts as saved when money is: sent out / kept here" — on savings
 * categories only, checked from the served role, saved through the category
 * update so the change log can undo it.
 */
import { render as rtlRender, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeCategory } from '../../../test-utils/factories'
import type { Category } from '../../../types'

const update = vi.hoisted(() => ({
  mutate: vi.fn(),
  isPending: false,
  isError: false,
  error: null as unknown,
}))

vi.mock('../../../api/categories', () => ({
  useUpdateCategory: () => update,
}))

import { SavingsModeField } from './SavingsModeField'

/** Rendered inside a router: the surface links into the Guide. */
const render = (ui: ReactElement) => rtlRender(ui, { wrapper: MemoryRouter })

function show(over: Partial<Category> = {}, tagKeys: string[] = ['savings']) {
  return render(
    <SavingsModeField
      category={makeCategory({ id: 'cat-1', savings_role: 'sent_out', ...over })}
      budgetId="b1"
      tagKeys={tagKeys}
    />
  )
}

const sentOut = () => screen.getByRole('radio', { name: /sent out of this envelope/ })
const keptHere = () => screen.getByRole('radio', { name: /kept in this envelope/ })

beforeEach(() => {
  update.mutate.mockReset()
  update.isPending = false
  update.isError = false
  update.error = null
})

describe('SavingsModeField', () => {
  it('renders nothing for a category that is not a savings category', () => {
    const { container } = show({ savings_role: 'none' }, [])
    expect(container).toBeEmptyDOMElement()
  })

  it('asks the question as a group, checked from the served role', () => {
    show({ savings_role: 'kept_here' })
    expect(
      screen.getByRole('group', { name: 'Counts as saved when money is:' })
    ).toBeInTheDocument()
    expect(keptHere()).toBeChecked()
    expect(sentOut()).not.toBeChecked()
  })

  it('says what each choice does', () => {
    show()
    expect(sentOut()).toHaveAccessibleDescription(
      'Spending or transfers from here count as saved; assigning doesn’t.'
    )
    expect(keptHere()).toHaveAccessibleDescription(
      'What this envelope holds is saved; spending from it lowers your savings.'
    )
  })

  it('keeps its ids stable per category', () => {
    show()
    expect(sentOut()).toHaveAttribute('id', 'savings-mode-cat-1-sent_out')
    expect(keptHere()).toHaveAttribute('id', 'savings-mode-cat-1-kept_here')
  })

  it('marks the served role as the default when nothing is stored, with no reset', () => {
    show({ savings_mode: null, savings_role: 'kept_here' })
    expect(keptHere()).toHaveAccessibleName('kept in this envelope (default)')
    expect(sentOut()).toHaveAccessibleName('sent out of this envelope')
    expect(screen.queryByRole('button', { name: 'Use default' })).not.toBeInTheDocument()
  })

  it('drops the marker and offers "Use default" once a mode is chosen', async () => {
    show({ savings_mode: 'kept_here', savings_role: 'kept_here' })
    expect(keptHere()).toHaveAccessibleName('kept in this envelope')

    await userEvent.click(screen.getByRole('button', { name: 'Use default' }))
    expect(update.mutate).toHaveBeenCalledWith({ id: 'cat-1', savings_mode: null })
  })

  it('selecting a mode sends savings_mode through the category update', async () => {
    show()
    await userEvent.click(keptHere())
    expect(update.mutate).toHaveBeenCalledWith({ id: 'cat-1', savings_mode: 'kept_here' })
  })

  it('moves between the choices with the keyboard', async () => {
    show()
    sentOut().focus()
    await userEvent.keyboard('{ArrowDown}')
    expect(update.mutate).toHaveBeenCalledWith({ id: 'cat-1', savings_mode: 'kept_here' })
  })

  it.each([['savings'], ['emergency_fund']])(
    'says a %s and Long-term expense category counts as savings',
    (key) => {
      show({}, [key, 'long_term_expense'])
      expect(
        screen.getByText(
          'Also tagged Long-term expense: it counts as savings, not as a sinking fund.'
        )
      ).toBeInTheDocument()
    }
  )

  it('says nothing about sinking funds otherwise', () => {
    show()
    expect(screen.queryByText(/sinking fund/)).not.toBeInTheDocument()
  })

  it('is disabled while saving and says when a save failed', () => {
    update.isPending = true
    update.isError = true
    update.error = new Error('nope')
    show()
    expect(sentOut()).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent('Could not save how this category counts')
  })

  it('links to how the two modes count', () => {
    show()
    expect(screen.getByRole('link', { name: /How this counts/ })).toHaveAttribute(
      'href',
      '/guide?tab=aside#savings-modes'
    )
  })
})
