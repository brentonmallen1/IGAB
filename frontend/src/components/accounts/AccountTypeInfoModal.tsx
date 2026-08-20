import { X } from 'lucide-react'
import { BUILTIN_ACCOUNT_TYPES } from '../../constants/accountTypes'
import { useFocusTrap } from '../../hooks/useFocusTrap'
import './AccountTypeInfoModal.css'

interface TypeRow {
  key: string
  label: string
  classification: 'asset' | 'liability'
  default_on_budget: boolean
  description?: string | null
  is_system?: boolean
}

interface Props {
  onClose: () => void
  /** Registry rows when a budget exists (custom types included); the
   * built-ins cover the pre-budget contexts like the YNAB import mapping. */
  types?: TypeRow[]
}

/** What each account type means and implies — mounted wherever a type is
 * chosen (add/edit account, YNAB import mapping). */
export function AccountTypeInfoModal({ onClose, types }: Props) {
  const trapRef = useFocusTrap<HTMLDivElement>(onClose)
  const rows = types && types.length > 0 ? types : BUILTIN_ACCOUNT_TYPES

  return (
    <div
      className="type-info-overlay"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={trapRef}
        tabIndex={-1}
        className="type-info"
        role="dialog"
        aria-modal="true"
        aria-labelledby="type-info-title"
      >
        <div className="type-info__header">
          <span id="type-info-title" className="type-info__title">
            Account types
          </span>
          <button className="type-info__close" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        <div className="type-info__body">
          <div className="type-info__concepts">
            <div className="type-info__concept">
              <div className="type-info__concept-title">On budget = envelopes</div>
              <p>
                An on-budget account's balance funds To Be Assigned, and spending from it
                needs a category. Your day-to-day money belongs here.
              </p>
            </div>
            <div className="type-info__concept">
              <div className="type-info__concept-title">Off budget = net worth only</div>
              <p>
                Off-budget (tracking) accounts count toward net worth but stay out of your
                envelopes. Moving money to one is spending as far as the budget is concerned —
                give that transfer a category. Spending and income reports count on-budget
                accounts by default; each report's info panel says exactly what it includes.
              </p>
            </div>
            <div className="type-info__concept">
              <div className="type-info__concept-title">Loans &amp; payoff tracking</div>
              <p>
                A loan account holds the ledger. Add a Liability record (APR, minimum payment)
                and link it to the account for payoff projections and interest math.
              </p>
            </div>
          </div>

          <div className="type-info__list">
            {rows.map((t) => (
              <div key={t.key} className="type-info__row">
                <div className="type-info__row-head">
                  <span className="type-info__label">{t.label}</span>
                  <span
                    className={`type-info__chip type-info__chip--${t.classification}`}
                  >
                    {t.classification}
                  </span>
                  <span className="type-info__chip">
                    {t.default_on_budget ? 'on budget' : 'off budget'}
                  </span>
                </div>
                <p className="type-info__desc">
                  {t.description || `Custom type — counts as ${t.classification === 'liability' ? 'a liability' : 'an asset'} in net worth.`}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
