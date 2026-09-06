import { describe, it, expect } from 'vitest'
import type { Liability } from '../../../api/liabilities'
import {
  addableLiabilities,
  blankRow,
  rowFromLiability,
  rowsToRequest,
  seedRows,
  type PlannerRow,
} from './payoffRows'

function liability(over: Partial<Liability>): Liability {
  return {
    id: 'l1',
    name: 'Visa',
    current_balance: 3410,
    interest_rate: 22.9,
    minimum_payment: 85,
    ...over,
  } as unknown as Liability
}

function row(over: Partial<PlannerRow>): PlannerRow {
  return {
    key: 'r',
    name: 'Visa',
    balance: '3410',
    rate: '22.9',
    minimum: '85',
    fromLiability: false,
    include: true,
    ...over,
  }
}

describe('seedRows', () => {
  it('offers liabilities with a rate and a minimum, as strings', () => {
    const { rows, excluded } = seedRows([liability({})])
    expect(rows).toEqual([
      {
        key: 'l1',
        name: 'Visa',
        balance: '3410',
        rate: '22.9',
        minimum: '85',
        fromLiability: true,
        include: true,
      },
    ])
    expect(excluded).toEqual([])
  })

  it('names a liability with no rate on record instead of assuming one', () => {
    const { rows, excluded } = seedRows([
      liability({}),
      liability({ id: 'l2', name: 'Unknown card', interest_rate: null }),
      liability({ id: 'l3', name: 'No minimum', minimum_payment: null }),
    ])
    expect(rows.map((r) => r.name)).toEqual(['Visa'])
    expect(excluded).toEqual(['Unknown card', 'No minimum'])
  })

  it('leaves out a paid-off liability quietly', () => {
    const { rows, excluded } = seedRows([liability({ current_balance: 0 })])
    expect(rows).toEqual([])
    expect(excluded).toEqual([])
  })
})

describe('rowsToRequest', () => {
  it('parses what a person typed', () => {
    const { body, errors } = rowsToRequest([row({ balance: '1,234.56', rate: '22.9' })], '100')
    expect(errors).toEqual({})
    expect(body).toEqual({
      debts: [
        { key: 'r', name: 'Visa', balance: '1234.56', annual_rate: '22.9', minimum_payment: '85' },
      ],
      extra: '100',
    })
  })

  it('a blank minimum blocks the request rather than booking zero', () => {
    const { body, errors } = rowsToRequest([row({ minimum: '' })], '0')
    expect(body).toBeNull()
    expect(errors).toEqual({ r: ['minimum'] })
  })

  it('an unparseable extra blocks the request', () => {
    const { body, extraError } = rowsToRequest([row({})], 'a lot')
    expect(body).toBeNull()
    expect(extraError).toBe(true)
  })

  it('no extra means none, not an error', () => {
    const { body, extraError } = rowsToRequest([row({})], '')
    expect(extraError).toBe(false)
    expect(body?.extra).toBe('0')
  })

  it('an untouched blank row is not a debt', () => {
    const { body, errors } = rowsToRequest([row({}), blankRow()], '')
    expect(errors).toEqual({})
    expect(body?.debts).toHaveLength(1)
  })

  it('nothing to plan is no request', () => {
    expect(rowsToRequest([blankRow()], '').body).toBeNull()
  })

  it('a rate over 100 or a negative balance is an error', () => {
    const { errors } = rowsToRequest([row({ rate: '120', balance: '-5' })], '')
    expect(errors.r).toEqual(['balance', 'rate'])
  })
})

describe('include', () => {
  it('leaves an unticked row out of the plan without erroring on it', () => {
    // The point of the tick: keep the figures on screen, out of the maths.
    // Removing the row was the only way to do this, and it took them with it.
    const { body, errors } = rowsToRequest(
      [row({ key: 'a' }), row({ key: 'b', name: 'Car', include: false })],
      ''
    )
    expect(body?.debts.map((d) => d.key)).toEqual(['a'])
    expect(errors).toEqual({})
  })

  it('does not let a half-typed excluded row block the plan', () => {
    const { body } = rowsToRequest(
      [row({ key: 'a' }), row({ key: 'b', rate: 'not a number', include: false })],
      ''
    )
    expect(body?.debts.map((d) => d.key)).toEqual(['a'])
  })

  it('has nothing to plan when every row is unticked', () => {
    expect(rowsToRequest([row({ include: false })], '').body).toBeNull()
  })
})

describe('rowFromLiability', () => {
  it('fills in what is known and leaves the rest to type', () => {
    // A mortgage with no APR on record is still worth adding by name.
    expect(rowFromLiability(liability({ interest_rate: null, minimum_payment: null }))).toEqual({
      key: 'l1',
      name: 'Visa',
      balance: '3410',
      rate: '',
      minimum: '',
      fromLiability: true,
      include: true,
    })
  })
})

describe('addableLiabilities', () => {
  it('offers the ones the seed left out', () => {
    const kept = liability({ id: 'l1' })
    const missing = liability({ id: 'l2', name: 'Mortgage', interest_rate: null })
    expect(addableLiabilities([kept, missing], [row({ key: 'l1' })]).map((l) => l.id)).toEqual([
      'l2',
    ])
  })

  it('offers one back after it was removed from the table', () => {
    expect(addableLiabilities([liability({ id: 'l1' })], []).map((l) => l.id)).toEqual(['l1'])
  })

  it('never offers one already in the table', () => {
    expect(addableLiabilities([liability({ id: 'l1' })], [row({ key: 'l1' })])).toEqual([])
  })
})
