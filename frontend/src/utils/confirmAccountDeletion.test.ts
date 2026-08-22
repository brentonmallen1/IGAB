/**
 * Every liability-classified account carries a companion now, so "does this
 * account have a liability?" stopped being a useful question — asking it would
 * put a three-way dialog in front of every credit-card deletion, most of them
 * over an empty row nobody filled in. These pin the test that replaced it, and
 * that the safe branch is what a dismissal produces.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Liability } from '../api/liabilities'
import type { Account } from '../types'
import { confirmAccountDeletion } from './confirmAccountDeletion'

const confirmAsync = vi.fn()
const chooseAsync = vi.fn()
vi.mock('../stores/confirmStore', () => ({
  confirmAsync: (...args: unknown[]) => confirmAsync(...args),
  chooseAsync: (...args: unknown[]) => chooseAsync(...args),
}))

const account = { id: 'acct-1', name: 'Car Loan' } as Account

function companion(overrides: Partial<Liability> = {}): Liability {
  return {
    id: 'l1',
    linked_account_id: 'acct-1',
    terms_complete: true,
    ...overrides,
  } as Liability
}

beforeEach(() => {
  confirmAsync.mockReset()
  chooseAsync.mockReset()
})

describe('confirmAccountDeletion', () => {
  it('asks a plain yes/no when there is no companion', async () => {
    confirmAsync.mockResolvedValue(true)

    const result = await confirmAccountDeletion(account, [])

    expect(chooseAsync).not.toHaveBeenCalled()
    expect(result).toEqual({ proceed: true, liability: 'keep' })
  })

  it('asks a plain yes/no when the companion has no terms', async () => {
    // An untouched companion has nothing to lose, so it goes quietly with its
    // account — exactly as it arrived.
    confirmAsync.mockResolvedValue(true)

    await confirmAccountDeletion(account, [companion({ terms_complete: false })])

    expect(chooseAsync).not.toHaveBeenCalled()
  })

  it('asks what to do with a debt someone filled in', async () => {
    chooseAsync.mockResolvedValue('keep')

    const result = await confirmAccountDeletion(account, [companion()])

    expect(confirmAsync).not.toHaveBeenCalled()
    const request = chooseAsync.mock.calls[0][0]
    expect(request.options.map((o: { id: string }) => o.id)).toEqual(['keep', 'delete'])
    // Keeping the debt is listed first and is not the destructive one.
    expect(request.options[0].destructive).toBeUndefined()
    expect(request.options[1].destructive).toBe(true)
    expect(result).toEqual({ proceed: true, liability: 'keep' })
  })

  it('passes the explicit delete through', async () => {
    chooseAsync.mockResolvedValue('delete')

    expect(await confirmAccountDeletion(account, [companion()])).toEqual({
      proceed: true,
      liability: 'delete',
    })
  })

  it('treats a dismissal as cancel, not as either outcome', async () => {
    chooseAsync.mockResolvedValue(null)

    expect(await confirmAccountDeletion(account, [companion()])).toEqual({
      proceed: false,
      liability: 'keep',
    })
  })

  it('cancels the plain path too', async () => {
    confirmAsync.mockResolvedValue(false)

    expect(await confirmAccountDeletion(account, [])).toEqual({
      proceed: false,
      liability: 'keep',
    })
  })

  it('ignores a companion belonging to another account', async () => {
    confirmAsync.mockResolvedValue(true)

    await confirmAccountDeletion(account, [companion({ linked_account_id: 'other' })])

    expect(chooseAsync).not.toHaveBeenCalled()
  })
})
