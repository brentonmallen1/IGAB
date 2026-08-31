/**
 * The server sends every money field as a JSON **string**; `types/index.ts`
 * calls them `number`. `tsc` cannot see the difference, so the damage is
 * silent rather than loud, and it reached the screen: `uncovered !== 0` is
 * true for `"0.00"`, so a settled card drew `$0.00` where the code says `—`.
 *
 * Every fixture here is a string, exactly as FastAPI serializes a `Decimal`.
 * The card-row suites use numeric literals — that is precisely why they did
 * not catch it, and why this file exists beside them.
 */
import { describe, expect, it, vi } from 'vitest'

const apiGet = vi.hoisted(() => vi.fn())
vi.mock('./client', () => ({
  apiClient: { get: apiGet },
  apiErrorMessage: (_e: unknown, fallback: string) => fallback,
}))

import { fetchBudgetMonth } from './budgets'

/** A settled card, as the wire actually carries it. */
const WIRE_CARD = {
  account_id: 'a1',
  name: 'Sapphire Visa',
  category_id: 'c1',
  balance: '-1500.00',
  set_aside: '7400.00',
  uncovered: '0.00',
  is_closed: false,
  overspent_this_month: '0',
  reserve_discrepancy: '0',
  assigned: '5900.00',
  reserved: '0',
  released: '0',
  residual: '9.00',
  payments: '0',
  riding: '0',
  over_reserved: '5900.00',
  short_reserved: '10.00',
  card_credit: '0',
  charged_this_month: '412.00',
  paid_this_month: '640.00',
  debt_change_this_month: '228.00',
  rode_by_month: [{ month: '2026-07-01', amount: '60.00' }],
}

async function load(card: Record<string, unknown> = WIRE_CARD) {
  apiGet.mockResolvedValue({ data: { month: '2026-08-01', cards: [card] } })
  return (await fetchBudgetMonth('b1', '2026-08-01')).cards[0]
}

describe('budget month decimals', () => {
  it('parses every money field to a number', async () => {
    const card = await load()
    for (const [key, value] of Object.entries(card)) {
      if (key === 'rode_by_month') continue
      if (typeof value === 'string' && /^-?\d+(\.\d+)?$/.test(value)) {
        throw new Error(`${key} is still the string ${value}`)
      }
    }
    expect(card.balance).toBe(-1500)
    expect(card.over_reserved).toBe(5900)
  })

  it('makes a settled card compare equal to zero', async () => {
    // The bug on screen: `uncovered !== 0 ? formatMoney(...) : '—'` drew
    // $0.00 on every settled card, because "0.00" is not 0.
    const card = await load()
    expect(card.uncovered).toBe(0)
    expect(card.uncovered !== 0).toBe(false)
  })

  it('parses the amounts inside rode_by_month', async () => {
    const card = await load()
    expect(card.rode_by_month[0].amount).toBe(60)
  })

  it('leaves arithmetic and ordering comparisons sound', async () => {
    // "9.00" + "10.00" concatenates, and "9.00" >= "10.00" is true
    // lexicographically — two of the ways this reached the row's copy.
    const card = await load()
    expect(card.residual + card.short_reserved).toBe(19)
    expect(card.residual >= card.short_reserved).toBe(false)
  })

  it('survives a response with no cards', async () => {
    apiGet.mockResolvedValue({ data: { month: '2026-08-01' } })
    await expect(fetchBudgetMonth('b1', '2026-08-01')).resolves.toBeTruthy()
  })

  it('leaves a card with no ride months with an empty list', async () => {
    const { rode_by_month: _drop, ...rest } = WIRE_CARD
    const card = await load(rest)
    expect(card.rode_by_month).toEqual([])
  })
})
