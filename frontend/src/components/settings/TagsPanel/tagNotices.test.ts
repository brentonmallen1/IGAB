import { describe, expect, it } from 'vitest'
import { noticeText } from './tagNotices'

describe('noticeText', () => {
  it('says what the emergency fund adoption tagged and marked', () => {
    expect(
      noticeText('emergency_fund_chosen', {
        tagged_categories: ['House Cushion', 'Rainy Day Savings'],
        flagged_accounts: ['Cascade Point HYSA'],
        dropped_accounts: [],
      })
    ).toBe(
      'Your emergency fund is now chosen, not guessed. 2 envelopes were tagged Emergency fund and 1 account marked.'
    )
  })

  it('says why each dropped account stopped counting', () => {
    const text = noticeText('emergency_fund_chosen', {
      tagged_categories: ['House Cushion'],
      flagged_accounts: [],
      dropped_accounts: [
        { name: 'Harborstone Checking', reason: 'on_budget' },
        { name: 'Second Car', reason: 'not_savings' },
      ],
    })
    expect(text).toContain('1 envelope was tagged Emergency fund and 0 accounts marked.')
    expect(text).toContain(
      'Harborstone Checking used to count, but envelopes already say what an on-budget account’s money is for — tag the envelopes that hold it.'
    )
    expect(text).toContain('Second Car used to count; mark it only once it counts as savings.')
  })

  it('reads a malformed payload as nothing rather than throwing', () => {
    expect(noticeText('emergency_fund_chosen', { dropped_accounts: 'nope' })).toBe(
      'Your emergency fund is now chosen, not guessed. 0 envelopes were tagged Emergency fund and 0 accounts marked.'
    )
  })

  it('says nothing is counted until the household chooses', () => {
    expect(noticeText('emergency_fund_not_guessed', {})).toBe(
      'Your emergency fund used to be guessed from names. Nothing is counted until you choose: tag envelopes Emergency fund, or mark an off-budget savings account.'
    )
  })

  it('keeps the payee-tag notices', () => {
    expect(noticeText('payee_tags_retired', { payee_tags_removed: 1 })).toContain(
      '1 payee tag was removed'
    )
  })

  it('falls back to the key for a notice with no copy', () => {
    expect(noticeText('something_new', {})).toBe('something_new')
  })
})
