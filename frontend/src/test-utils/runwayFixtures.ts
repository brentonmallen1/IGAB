import type {
  IfIncomeStopped,
  OverviewRunway,
  RunwayFigure,
  RunwayMoney,
  RunwaySpending,
  StoppedIncomeOption,
} from '../types'

/**
 * Runway fixtures, shaped the way the server serves them (`domain/runway.py`).
 * The household is invented: 20,000 against Essentials of 1,000 a month is
 * twenty months, 500 owed on the cards already taken out.
 */
export function runwayFigure(overrides: Partial<RunwayFigure> = {}): RunwayFigure {
  return {
    spending: 'essentials',
    money: 'with_fund',
    monthly_spending: 1000,
    money_total: 20000,
    card_debt: 500,
    months: 20,
    runs_out_on: '2028-05-27',
    ...overrides,
  }
}

export function overviewRunway(overrides: Partial<OverviewRunway> = {}): OverviewRunway {
  return {
    ...runwayFigure(),
    fund_chosen: true,
    essentials_known: true,
    window_start: '2026-06-01',
    window_end: '2026-08-31',
    ...overrides,
  }
}

const SPENDING: RunwaySpending[] = ['all', 'cost_of_living', 'essentials']
const MONEY: RunwayMoney[] = ['checking', 'with_fund', 'with_savings']
const MONTHLY: Record<RunwaySpending, number> = {
  all: 2000,
  cost_of_living: 1250,
  essentials: 1000,
}
const HELD: Record<RunwayMoney, number> = {
  checking: 5000,
  with_fund: 10000,
  with_savings: 12500,
  fund: 6500,
}

/**
 * Every choice the projection offers, from 2026-09-26 over a 90-day horizon.
 * `noFund` serves "+ Emergency fund" as unanswered; `untagged` serves the
 * Cost of living and Essentials tiers as unknown.
 */
export function ifIncomeStopped(
  opts: { noFund?: boolean; untagged?: boolean } = {}
): IfIncomeStopped {
  const options: StoppedIncomeOption[] = SPENDING.flatMap((spending) =>
    MONEY.map((money) => {
      const monthly = opts.untagged && spending !== 'all' ? null : MONTHLY[spending]
      const held = opts.noFund && money === 'with_fund' ? null : HELD[money]
      const months =
        monthly === null || held === null ? null : Math.round((held / monthly) * 10) / 10
      return {
        ...runwayFigure({ spending, money, monthly_spending: monthly, money_total: held, months }),
        runs_out_on: months === null ? null : '2027-01-01',
        line:
          held === null
            ? []
            : [
                { date: '2026-09-26', balance: held },
                { date: '2026-12-25', balance: held - 3000 },
              ],
      }
    })
  )
  return {
    options,
    default_spending: opts.untagged ? 'all' : 'essentials',
    default_money: opts.noFund ? 'checking' : 'with_fund',
    fund_chosen: !opts.noFund,
    essentials_known: !opts.untagged,
    window_start: '2026-06-01',
    window_end: '2026-08-31',
  }
}
