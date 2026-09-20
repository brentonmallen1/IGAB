import { ChevronDown, ChevronRight, CheckCircle, CircleDot } from 'lucide-react'
import type { ReactNode } from 'react'

/**
 * The account header's balance region: the fold control and the figures.
 *
 * Presentational and prop-driven on purpose — `formatMoney` arrives as a
 * prop rather than from `useFormatters`, so this renders without a format
 * context, a store or a router. The page around it is a dozen hooks deep and
 * had no test of any kind, which is how the working balance came to be
 * rendered twice, at the same size, three lines apart, for a month.
 *
 * Two rules it exists to hold:
 *
 *  1. The working balance is stated ONCE. Which spelling you get is the fold —
 *     folded it is the headline beside the account name, open it is the `=`
 *     term of the equation. Branches of one conditional, not two rules that
 *     have to be kept in step.
 *
 *  2. The control does not move. It is the last thing on the header's top row
 *     in BOTH states: after the balance when folded, after the pills when
 *     open. It used to lead the figures, which put it on row one folded and
 *     row two open — a control that changes rows when you use it reads as a
 *     glitch, however correct it is.
 *
 * Returns a fragment, so the three parts are direct children of the header's
 * flex row and the equation can take a full line of its own while the control
 * stays up top.
 */
export interface AccountBalancesProps {
  balance: number
  clearedBalance: number
  unclearedBalance: number
  collapsed: boolean
  onToggle: () => void
  formatMoney: (amount: number) => string
}

/** The id `aria-controls` points at. Exported so the test names it once. */
export const DETAIL_ID = 'account-header-detail'

const tone = (amount: number) => (amount < 0 ? 'negative' : 'positive')

export function AccountBalances({
  balance,
  clearedBalance,
  unclearedBalance,
  collapsed,
  onToggle,
  formatMoney,
}: AccountBalancesProps) {
  /* One figure, one spelling. This markup was written out four times. */
  const figure = (value: number, label: ReactNode, colour?: string, working?: boolean) => (
    <div
      className={`account-page__balance-item${working ? ' account-page__balance-item--working' : ''}`}
    >
      <span className={`account-page__balance-value ${colour ?? ''}`}>{formatMoney(value)}</span>
      <span className="account-page__balance-label">{label}</span>
    </div>
  )

  return (
    <>
      {collapsed && (
        <div className="account-page__balance-headline">
          <span className={`account-page__balance-value ${tone(balance)}`}>
            {formatMoney(balance)}
          </span>
          <span className="account-page__balance-label">Working balance</span>
        </div>
      )}
      <button
        type="button"
        className="account-page__header-toggle"
        onClick={onToggle}
        aria-expanded={!collapsed}
        aria-controls={DETAIL_ID}
        aria-label={collapsed ? 'Show account details' : 'Hide account details'}
        title={collapsed ? 'Show account details' : 'Hide account details'}
      >
        {collapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
      </button>
      {/* Mounted in both states so `aria-controls` always resolves — hidden by
          class, never unmounted. Open, it takes a full line of its own, which
          is what keeps the control above it on the top row. */}
      <div
        id={DETAIL_ID}
        className={`account-page__balances ${collapsed ? 'account-page__balances--collapsed' : ''}`}
      >
        {figure(
          clearedBalance,
          <>
            <CheckCircle size={10} />
            Cleared
          </>,
          tone(clearedBalance)
        )}
        <span className="account-page__balance-op">+</span>
        {figure(
          unclearedBalance,
          <>
            <CircleDot size={10} />
            Uncleared
          </>
        )}
        <span className="account-page__balance-op">=</span>
        {figure(balance, 'Working balance', tone(balance), true)}
      </div>
    </>
  )
}
