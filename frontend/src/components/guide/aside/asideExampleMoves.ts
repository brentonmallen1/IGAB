/**
 * One month in a General Savings envelope, the same three moves counted both
 * ways. The moves differ only in the category kind — which is the whole
 * lesson — and every figure is answered by `POST guide/money-moves/month`.
 * Names are the shared invented vocabulary; nothing here is anybody's budget.
 */
import type { CategoryKind, MonthMoveRequest } from '../../../api/moneyRules'
import type { SavingsMode } from '../../../types'
import { builtinShape } from '../money/explorerMove'

const checking = builtinShape('checking')
/** Cascade Point HYSA: off budget, counting as savings. */
const hysa = { ...builtinShape('savings', false), counts_as_savings: true }

export const MODE_KIND: Record<SavingsMode, CategoryKind> = {
  sent_out: 'savings_sent',
  kept_here: 'savings_kept',
}

/** A move, and for each mode a short line on why it counts the way it does.
 * The line is prose; the amount it counts as is served. */
export interface ExampleMove {
  move: MonthMoveRequest
  why: Record<SavingsMode, string>
}

function month(kind: CategoryKind): ExampleMove[] {
  return [
    {
      move: {
        label: 'Assigned to General Savings',
        kind: 'assign',
        category: kind,
        amount: 500,
      },
      why: {
        sent_out: 'Assigning only gives the money a job; it has not left.',
        kept_here: 'What the envelope holds is savings.',
      },
    },
    {
      move: {
        label: 'Car repair, paid from it',
        kind: 'transaction',
        account: checking,
        direction: 'out',
        category: kind,
        amount: 120,
      },
      why: {
        sent_out: 'Money leaving a sent-out envelope counts as saved, wherever it goes.',
        kept_here: 'Spending from it is spending, and lowers what it holds.',
      },
    },
    {
      move: {
        label: 'Moved to Cascade Point HYSA',
        kind: 'transfer',
        account: checking,
        to_account: hysa,
        category: kind,
        amount: 300,
      },
      why: {
        sent_out: 'Sent out to a savings account.',
        kept_here: 'Saved already: it moved from one kind of savings to another.',
      },
    },
  ]
}

export const GENERAL_SAVINGS_MONTH: Record<SavingsMode, ExampleMove[]> = {
  sent_out: month(MODE_KIND.sent_out),
  kept_here: month(MODE_KIND.kept_here),
}

/** The requests alone, as the month endpoint takes them. Built once per mode
 * so the query key is stable across renders. */
export const GENERAL_SAVINGS_REQUESTS: Record<SavingsMode, MonthMoveRequest[]> = {
  sent_out: GENERAL_SAVINGS_MONTH.sent_out.map((m) => m.move),
  kept_here: GENERAL_SAVINGS_MONTH.kept_here.map((m) => m.move),
}
