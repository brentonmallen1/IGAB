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
 * The rule it exists to hold: the working balance is stated ONCE. Which
 * spelling you get is the fold — folded it is the headline beside the account
 * name, open it is the `=` term of the equation. They are branches of one
 * conditional rather than two rules that have to be kept in step.
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
    <div className={`account-page__balance${collapsed ? '' : ' account-page__balance--open'}`}>
      {/* The triangle sits in the same place in both states, immediately
          before the figures. Folded it wraps the headline too, so the target
          is a balance rather than a 14px glyph. */}
      <button
        type="button"
        className="account-page__header-toggle"
        onClick={onToggle}
        aria-expanded={!collapsed}
        aria-controls={DETAIL_ID}
        title={collapsed ? 'Show account details' : 'Hide account details'}
      >
        {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
        {collapsed && (
          <>
            <span className={`account-page__balance-value ${tone(balance)}`}>
              {formatMoney(balance)}
            </span>
            <span className="account-page__balance-label">Working balance</span>
          </>
        )}
      </button>
      {/* Mounted in both states so `aria-controls` always resolves — hidden by
          class, never unmounted. */}
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
    </div>
  )
}
