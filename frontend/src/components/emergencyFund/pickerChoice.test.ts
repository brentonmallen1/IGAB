import { describe, expect, it } from 'vitest'
import { FUND_MEMBERSHIP, FUND_PICKER } from '../../test-utils/emergencyFundFixtures'
import { initialDraft, toggleChecked } from '../tags/membershipList'
import {
  AMOUNT_ERROR,
  buildChoice,
  externalDraft,
  memberAccounts,
  parseExternal,
  turnsOnSavings,
} from './pickerChoice'

describe('parseExternal', () => {
  const declared = (amount: string, note = '') => ({ declared: true, amount, note })

  it('reads a typed amount the way every money input does, as a canonical string', () => {
    expect(parseExternal(declared('1,250.5'))).toEqual({
      value: { declared: true, amount: '1250.50', note: null },
    })
  })

  it('blank is "I have this covered" — null, never zero', () => {
    expect(parseExternal(declared('  ', ' credit union '))).toEqual({
      value: { declared: true, amount: null, note: 'credit union' },
    })
  })

  it('an unreadable or negative amount is an error, not a zero', () => {
    expect(parseExternal(declared('most of it'))).toEqual({ error: AMOUNT_ERROR })
    expect(parseExternal(declared('-5'))).toEqual({ error: AMOUNT_ERROR })
  })

  it('undeclared sends nothing, whatever was typed', () => {
    expect(parseExternal({ declared: false, amount: 'junk', note: 'x' })).toEqual({
      value: { declared: false, amount: null, note: null },
    })
  })
})

describe('seeding and building', () => {
  it('seeds from what is served', () => {
    expect(externalDraft(FUND_PICKER.fund.external)).toEqual({
      declared: true,
      amount: '1000',
      note: 'credit union',
    })
    expect(memberAccounts(FUND_PICKER.account_candidates)).toEqual(new Set(['reserve']))
  })

  it('names the checked accounts that will also count as savings', () => {
    const candidates = FUND_PICKER.account_candidates
    expect(turnsOnSavings(candidates, new Set(['reserve']))).toEqual(new Set())
    expect(turnsOnSavings(candidates, new Set(['reserve', 'hysa']))).toEqual(new Set(['hysa']))
  })

  it('builds one choice, or refuses on a bad amount', () => {
    const envelopes = toggleChecked(initialDraft(FUND_MEMBERSHIP.categories), 'fund')
    const input = {
      rows: FUND_MEMBERSHIP.categories,
      envelopes,
      accounts: new Set(['reserve', 'hysa']),
      external: { declared: false, amount: '', note: '' },
    }
    expect(buildChoice(input)).toEqual({
      choice: {
        add_categories: [],
        remove_categories: ['fund'],
        savings_modes: {},
        account_ids: ['hysa', 'reserve'],
        external: { declared: false, amount: null, note: null },
      },
    })
    expect(
      buildChoice({ ...input, external: { declared: true, amount: 'lots', note: '' } })
    ).toEqual({ error: AMOUNT_ERROR })
  })
})
