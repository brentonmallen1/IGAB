import { AlertTriangle, Info, SlidersHorizontal } from 'lucide-react'
import { amountTone } from '../../utils/figureTone'
import { type AccountNotice, noticesLabel, noticesTone } from './accountNotices'
import './AccountPhoneHeader.css'

interface Props {
  balance: number
  clearedBalance: number
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
 * rows. Here it is the working balance (with the cleared balance as a small
 * line under it), one pill for whatever is waiting, the account's main
 * action, and Tools — the budget header's shape (TbaHero), so the two pages
 * work alike. Everything else is one tap away in a sheet.
 */
export function AccountPhoneHeader({
  balance,
  clearedBalance,
  formatMoney,
  notices,
  primary,
  onOpenTools,
  onOpenNotices,
}: Props) {
  const tone = noticesTone(notices)
  return (
    <section className="account-phone-header" aria-label="Account">
      {/* Figures, not a control. They once carried a chevron that opened
          Tools, and the chevron read as "expand the header" — a fold this
          row no longer has. Tools is the one way in. Cleared sits under
          Working as a smaller line, so the pair costs height, not width, and
          the row still fits a 390px phone. */}
      <div className="account-phone-header__figures">
        <span
          className={`account-phone-header__balance tabular ${amountTone(balance)}`}
          title="Working balance"
        >
          {formatMoney(balance)}
        </span>
        <span className="account-phone-header__cleared" title="Cleared balance">
          <span className="account-phone-header__cleared-label">Cleared</span>{' '}
          <span className={`tabular ${amountTone(clearedBalance)}`}>
            {formatMoney(clearedBalance)}
          </span>
        </span>
      </div>
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
