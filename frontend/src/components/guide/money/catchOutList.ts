/**
 * The things that catch people out, each with the move that shows it. The
 * prose is ours; what the move counts as is served when "Try it" loads it.
 */
import { SYSTEM_TAG_HELP } from '../../settings/TagsPanel/systemTagHelp'
import { preset, type ExplorerState } from './explorerMove'

const tagName = (key: string) => SYSTEM_TAG_HELP.find((t) => t.key === key)?.name ?? key

export interface CatchOut {
  id: string
  title: string
  detail: string
  /** Loads the explorer with the move this describes, so the claim can be
   * checked against the served answer rather than taken on trust. */
  tryIt: ExplorerState
}

export const CATCH_OUTS: CatchOut[] = [
  {
    id: 'on-budget-hysa',
    title: 'Moving money to an on-budget savings account is not saving',
    detail:
      'Both accounts are in the budget, so the money never left it. Take the account off budget, or tag the category it leaves from, if you want it counted.',
    tryIt: preset('transfer', 'checking', 'savings'),
  },
  {
    id: 'brokerage-withdrawal',
    title: 'Taking money out of a brokerage lowers what you saved',
    detail:
      'Money back from an account that counts as savings is saving in reverse, so a month with a big withdrawal can show a negative savings rate.',
    tryIt: preset('transfer', 'investment', 'checking'),
  },
  {
    id: 'mortgage-payment',
    title: 'The whole mortgage payment counts as debt principal',
    detail:
      'IGAB sees one transfer to the loan, not its split into interest and escrow, so the full payment lands in the savings rate with debt and in cost of living.',
    tryIt: preset('transfer', 'checking', 'mortgage'),
  },
  {
    id: 'uncategorized-inflow',
    title: 'Money arriving with no category is income',
    detail:
      'A refund or a reimbursement left uncategorized raises income and Ready to Assign. File it to the category it paid back and it nets against that spending instead.',
    tryIt: preset('transaction', 'checking', 'checking', { direction: 'in' }),
  },
  {
    id: 'card-payment',
    title: 'A credit card payment never counts',
    detail:
      'The spending counted when you used the card. Paying the card only moves money you already set aside.',
    tryIt: preset('transfer', 'checking', 'credit_card'),
  },
  {
    id: 'take-home',
    title: 'Income is take-home pay',
    detail:
      'Only what reaches your accounts is counted, so tax and anything your employer deducts before paying you never appear, and the savings rate is a share of take-home.',
    tryIt: preset('transaction', 'checking', 'checking', { direction: 'in', category: 'income' }),
  },
  {
    id: 'savings-tag',
    title: `The ${tagName('savings')} tag counts every outflow as saving`,
    detail: `Spend a vacation fund tagged ${tagName('savings')} on a flight and the flight counts as saved. For money set aside toward a bill, use ${tagName('long_term_expense')}: the bill then counts as spending when it is paid.`,
    tryIt: preset('transaction', 'checking', 'checking', { category: 'savings' }),
  },
  {
    id: 'car-sale',
    title: 'Selling something that is not savings is income',
    detail:
      'Selling a car into checking raises income and Ready to Assign, and buying one is spending. The account’s Counts as savings switch decides: turn it on and the same sale reads as savings drawn back out.',
    tryIt: preset('transfer', 'other_asset', 'checking'),
  },
]
