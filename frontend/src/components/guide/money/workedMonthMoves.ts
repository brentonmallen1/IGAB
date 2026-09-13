/**
 * The worked month: one invented household's month, every figure answered by
 * `POST guide/money-moves/month`. Names are the shared invented vocabulary and
 * the amounts are round enough to check on paper; nothing here is anybody's
 * budget.
 */
import type { MonthMoveRequest } from '../../../api/moneyRules'
import { builtinShape } from './explorerMove'

const checking = builtinShape('checking')

export const WORKED_MONTH: MonthMoveRequest[] = [
  {
    label: 'Paycheck from Northwind Payserv',
    kind: 'transaction',
    account: checking,
    direction: 'in',
    category: 'income',
    amount: 6000,
  },
  {
    label: 'Harborstone mortgage payment',
    kind: 'transfer',
    account: checking,
    to_account: builtinShape('mortgage'),
    category: 'none',
    amount: 1800,
  },
  {
    label: 'Checking to the brokerage',
    kind: 'transfer',
    account: checking,
    to_account: builtinShape('investment'),
    category: 'none',
    amount: 500,
  },
  {
    label: 'Flight, from a Savings-tagged Vacation category',
    kind: 'transaction',
    account: checking,
    direction: 'out',
    category: 'savings',
    amount: 250,
  },
  {
    label: 'Checking to Cascade Point HYSA, on budget',
    kind: 'transfer',
    account: checking,
    to_account: builtinShape('savings', true),
    category: 'none',
    amount: 400,
  },
  {
    label: 'Sapphire Visa payment',
    kind: 'transfer',
    account: checking,
    to_account: builtinShape('credit_card'),
    category: 'none',
    amount: 900,
  },
  {
    label: 'Everyday spending',
    kind: 'transaction',
    account: checking,
    direction: 'out',
    category: 'ordinary',
    amount: 2300,
  },
  {
    label: 'Dividend inside the brokerage',
    kind: 'transaction',
    account: builtinShape('investment'),
    direction: 'in',
    category: 'none',
    amount: 35,
  },
  {
    label: 'Sold the car into checking',
    kind: 'transfer',
    account: builtinShape('other_asset'),
    to_account: checking,
    category: 'none',
    amount: 4500,
  },
]
