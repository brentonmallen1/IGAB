import { AlertTriangle, ChevronDown, Info, SlidersHorizontal } from 'lucide-react'
import { type AccountNotice, noticesLabel, noticesTone } from './accountNotices'
import './AccountPhoneHeader.css'

interface Props {
  balance: number
  formatMoney: (amount: number) => string
  notices: readonly AccountNotice[]
  /** Reconcile, or the payment on a card or a loan. */
  primary: { label: string; onClick: () => void; disabled?: boolean }
  onOpenTools: () => void
  onOpenNotices: () => void
}

/**
 * The account header on a phone: one row.
 *
 * The desktop header carries the pills, the balance equation, the pending
 * and bank lines and five buttons, and on a phone it stacked to four rows
 * with the review and duplicates banners under it — 420px of a 744px screen
 * before the first transaction, pinned, because only the register scrolls.
 * Folding it was a chevron few people found, and folded it was still three
 * rows. Here it is the working balance, one pill for whatever is waiting, the
 * account's main action, and Tools — the budget header's shape (TbaHero), so
 * the two pages work alike. Everything else is one tap away in a sheet.
 */
export function AccountPhoneHeader({
  balance,
  formatMoney,
  notices,
  primary,
  onOpenTools,
  onOpenNotices,
}: Props) {
  const tone = noticesTone(notices)
  const formatted = formatMoney(balance)
  return (
    <section className="account-phone-header" aria-label="Account">
      {/* The balance opens Tools, where the equation behind it lives: the
          figure is what you would tap to ask "made of what?". */}
      <button
        type="button"
        className="account-phone-header__balance"
        onClick={onOpenTools}
        aria-haspopup="dialog"
        aria-label={`Working balance ${formatted}. Show balances and tools`}
      >
        <span
          className={`account-phone-header__balance-value tabular ${balance < 0 ? 'negative' : 'positive'}`}
        >
          {formatted}
        </span>
        <ChevronDown size={16} aria-hidden="true" />
      </button>
      {tone && (
        <button
          type="button"
          className={`account-phone-header__notice account-phone-header__notice--${tone}`}
          onClick={onOpenNotices}
          aria-haspopup="dialog"
          aria-label={noticesLabel(notices)}
        >
          {tone === 'warning' ? (
            <AlertTriangle size={14} aria-hidden="true" />
          ) : (
            <Info size={14} aria-hidden="true" />
          )}
          <span className="tabular">{notices.length}</span>
        </button>
      )}
      <button
        type="button"
        className="account-phone-header__primary"
        onClick={primary.onClick}
        disabled={primary.disabled}
      >
        {primary.label}
      </button>
      <button
        type="button"
        className="account-phone-header__tools"
        onClick={onOpenTools}
        aria-haspopup="dialog"
        aria-label="Account tools"
      >
        <SlidersHorizontal size={18} aria-hidden="true" />
      </button>
    </section>
  )
}
