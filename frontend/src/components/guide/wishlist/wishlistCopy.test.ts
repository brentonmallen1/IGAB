import { describe, it, expect } from 'vitest'
import { impactLabel, reachLabel, stillWantedLine } from './wishlistCopy'
import type { Wish } from '../../../api/wishlist'

const fmt = { formatMoney: (n: number) => `$${n}`, formatDate: (s: string) => s }

function wish(over: Partial<Wish>): Wish {
  return {
    id: 'w',
    project_id: null,
    name: 'W',
    url: null,
    notes: null,
    cost: '100',
    priority: 0,
    status: 'open',
    funding: {
      mode: 'existing',
      category_id: 'c',
      category_name: 'Bike Fund',
      inherited: false,
      owns_envelope: false,
      target_date: null,
    },
    cooling_until: null,
    cooling: false,
    last_affirmed_at: null,
    review_due: false,
    done_at: null,
    created_at: '2026-08-01',
    reach: null,
    ...over,
  }
}

describe('impactLabel', () => {
  it('speaks in weeks under a month and half-months above', () => {
    expect(impactLabel('0.25')).toBe('about 1 week further away')
    expect(impactLabel('0.6')).toBe('about 3 weeks further away')
    expect(impactLabel('1')).toBe('about 1 month further away')
    expect(impactLabel('1.4')).toBe('about 1½ months further away')
    expect(impactLabel('2.1')).toBe('about 2 months further away')
  })

  it('says nothing when there is no pace', () => {
    expect(impactLabel(null)).toBeNull()
    expect(impactLabel('0')).toBeNull()
  })
})

describe('reachLabel', () => {
  it('names each state', () => {
    expect(
      reachLabel(
        wish({ reach: { state: 'now', months: 0, date: null, ahead_cost: '0', progress: '1' } }),
        fmt
      )
    ).toBe('you can afford this now')
    expect(
      reachLabel(
        wish({
          reach: {
            state: 'months',
            months: 8,
            date: '2027-04-26',
            ahead_cost: '0',
            progress: '0.3',
          },
        }),
        fmt
      )
    ).toBe('about 8 months (2027-04-26)')
    expect(
      reachLabel(
        wish({
          reach: { state: 'no_rate', months: null, date: null, ahead_cost: '0', progress: '0' },
        }),
        fmt
      )
    ).toMatch(/nothing assigned/)
    expect(
      reachLabel(
        wish({
          funding: {
            mode: 'none',
            category_id: null,
            category_name: null,
            inherited: false,
            owns_envelope: false,
            target_date: null,
          },
          reach: { state: 'unlinked', months: null, date: null, ahead_cost: '0', progress: '0' },
        }),
        fmt
      )
    ).toMatch(/not linked/)
  })
})

describe('stillWantedLine', () => {
  it('reads the served window and counts', () => {
    expect(stillWantedLine({ count: 2, of: 5, months: 3 })).toBe(
      'Added over 3 months ago and still wanted: 2 of 5'
    )
    expect(stillWantedLine({ count: 0, of: 0, months: 3 })).toBeNull()
  })
})
