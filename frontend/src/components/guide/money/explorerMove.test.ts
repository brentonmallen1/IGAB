import { describe, expect, it } from 'vitest'
import { BUILTIN_ACCOUNT_TYPES } from '../../../constants/accountTypes'
import {
  DEFAULT_EXPLORER,
  EXPLORER_AMOUNT,
  explorerRequest,
  preset,
  sideForType,
} from './explorerMove'
import { WORKED_MONTH } from './workedMonthMoves'

const types = BUILTIN_ACCOUNT_TYPES

describe('explorerRequest', () => {
  it('asks about a transfer with both shapes and no direction', () => {
    const body = explorerRequest(preset('transfer', 'other_asset', 'checking'), types)
    expect(body).toEqual({
      kind: 'transfer',
      account: { classification: 'asset', on_budget: false, counts_as_savings: false },
      to_account: { classification: 'asset', on_budget: true, counts_as_savings: true },
      category: 'none',
      amount: EXPLORER_AMOUNT,
    })
  })

  it('asks about a transaction with a direction and no to-account', () => {
    const body = explorerRequest(
      { ...DEFAULT_EXPLORER, kind: 'transaction', direction: 'in', category: 'income' },
      types
    )
    expect(body).toMatchObject({ kind: 'transaction', direction: 'in', category: 'income' })
    expect(body).not.toHaveProperty('to_account')
  })

  it('carries the reader’s flips over the type defaults', () => {
    const state = preset('transfer', 'checking', 'other_asset')
    const body = explorerRequest(
      { ...state, to: { ...state.to, countsAsSavings: true, onBudget: true } },
      types
    )
    expect(body?.to_account).toEqual({
      classification: 'asset',
      on_budget: true,
      counts_as_savings: true,
    })
  })

  it('asks nothing while a chosen type is unknown', () => {
    const state = { ...DEFAULT_EXPLORER, from: { ...DEFAULT_EXPLORER.from, typeKey: 'gone' } }
    expect(explorerRequest(state, types)).toBeNull()
  })
})

describe('sides', () => {
  it('start from the type’s own defaults, as the account forms do', () => {
    const car = types.find((t) => t.key === 'other_asset')!
    expect(sideForType(car)).toEqual({
      typeKey: 'other_asset',
      onBudget: false,
      countsAsSavings: false,
    })
  })

  it('a preset can put a type on budget, the on-budget HYSA case', () => {
    expect(preset('transfer', 'checking', 'investment', { toOnBudget: true }).to.onBudget).toBe(
      true
    )
  })
})

describe('the worked month', () => {
  it('uses only invented names from the shared vocabulary', () => {
    const labels = WORKED_MONTH.map((m) => m.label).join(' ')
    for (const name of [
      'Northwind Payserv',
      'Harborstone',
      'Cascade Point HYSA',
      'Sapphire Visa',
    ]) {
      expect(labels).toContain(name)
    }
  })

  it('sells the car from a tracked asset that does not count as savings', () => {
    const sale = WORKED_MONTH.find((m) => m.label.includes('car'))!
    expect(sale.account).toEqual({
      classification: 'asset',
      on_budget: false,
      counts_as_savings: false,
    })
  })
})
