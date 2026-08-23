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
  /** 'import' adds the choices that only exist while mapping an export —
   * what leaving an account out actually costs. Stated explicitly rather
   * than inferred from `types` being absent, so the two stay independent. */
  context?: 'import'
}

/** What each account type means and implies — mounted wherever a type is
 * chosen (add/edit account, YNAB import mapping). */
export function AccountTypeInfoModal({ onClose, types, context }: Props) {
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
            {context === 'import' ? 'Account types & import choices' : 'Account types'}
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
                Pick Mortgage, Auto Loan, Student Loan, Credit Card or Loan and the payoff
                tracking comes with the account — no second record to create. Fill in the APR
                and minimum payment on the account page for projections, an amortization
                schedule and interest math. Until then you still get a working ledger.
              </p>
            </div>
          </div>

          {context === 'import' && (
            <div className="type-info__concepts">
              <div className="type-info__section-title">Leaving an account out</div>
              <div className="type-info__concept">
                <div className="type-info__concept-title">Its history goes with it</div>
                <p>
                  The account and every transaction in it are never created. Your other
                  accounts' balances stay correct, but net worth over time has a hole
                  where that account should have been.
                </p>
                <p>
                  It also breaks transfers. A transfer from an account you keep to one
                  you leave out has nothing to pair with, so it arrives unlinked and
                  reads as real income or spending in your reports. That is what the
                  "transfers couldn't be matched" warning after an import is telling
                  you — and leaving accounts out is what causes it.
                </p>
                <p>
                  YNAB exports include accounts you closed years ago. Those are worth
                  importing anyway: they carry the history that makes past months add
                  up.
                </p>
              </div>
            </div>
          )}

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
