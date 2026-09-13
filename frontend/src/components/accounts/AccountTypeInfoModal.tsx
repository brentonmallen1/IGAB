import { useMoneyRules, type MoneyShape, type MoveExplanation } from '../../api/moneyRules'
import { BUILTIN_ACCOUNT_TYPES } from '../../constants/accountTypes'
import { useFormatters } from '../../hooks/useFormatters'
import { budgetEffectLines, shapeFor } from '../../utils/moneyMoves'
import { Dialog } from '../common/Dialog/Dialog'
import { GuideTabLink } from '../guide/GuideTabLink'
import './AccountTypeInfoModal.css'

interface TypeRow {
  key: string
  label: string
  classification: 'asset' | 'liability'
  default_on_budget: boolean
  default_counts_as_savings: boolean
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
  /** The budget whose Guide serves the "Money in / Money out" lines. Absent
   * before a budget exists (the import mapping), where the lines are left out. */
  budgetId?: string | null
}

/** The on-budget legs' classes, joined — what the budget's reports see. */
function countedAs(e: MoveExplanation): string {
  const labels = [...new Set(e.legs.filter((l) => l.on_budget).map((l) => l.class_label))]
  return labels.join(' and ')
}

function MoneyLines({ shape }: { shape: MoneyShape }) {
  const { formatMoney } = useFormatters()
  return (
    <dl className="type-info__money">
      {(
        [
          ['Money in', shape.money_in],
          ['Money out', shape.money_out],
        ] as const
      ).map(([title, example]) => (
        <div key={title} className="type-info__money-line">
          <dt>{title}</dt>
          <dd>
            {example.description}: counts as {countedAs(example.explanation)}.{' '}
            {budgetEffectLines(example.explanation.budget_terms, formatMoney).join('. ')}.
          </dd>
        </div>
      ))}
    </dl>
  )
}

function TypeMoneyLines({
  shapes,
  classification,
  onBudget,
  countsAsSavings,
}: {
  shapes: MoneyShape[]
  classification: 'asset' | 'liability'
  onBudget: boolean
  countsAsSavings: boolean
}) {
  const shape = shapeFor(shapes, {
    classification,
    on_budget: onBudget,
    counts_as_savings: countsAsSavings,
  })
  return shape ? <MoneyLines shape={shape} /> : null
}

/** What each account type means and implies — mounted wherever a type is
 * chosen (add/edit account, YNAB import mapping). */
export function AccountTypeInfoModal({ onClose, types, context, budgetId }: Props) {
  const rows = types && types.length > 0 ? types : BUILTIN_ACCOUNT_TYPES
  const { data: money } = useMoneyRules(context === 'import' ? null : (budgetId ?? null))

  return (
    <Dialog
      title={context === 'import' ? 'Account types & import choices' : 'Account types'}
      onClose={onClose}
      historyKey="account-types"
      className="type-info"
    >
      <div className="type-info__body">
        <div className="type-info__concepts">
          <div className="type-info__concept">
            <div className="type-info__concept-title">On budget = envelopes</div>
            <p>
              An on-budget account's balance funds To Be Assigned, and spending from it needs a
              category. Your day-to-day money belongs here.
            </p>
          </div>
          <div className="type-info__concept">
            <div className="type-info__concept-title">Off budget = net worth only</div>
            <p>
              Off-budget (tracking) accounts count toward net worth but stay out of your envelopes.
              Moving money to one is spending as far as the budget is concerned — give that transfer
              a category. In reports, money into a tracked asset that counts as savings is saving;
              into one that does not, like a car, it is spending, and money out of it is income.
              Spending and income reports count on-budget accounts by default; each report's info
              panel says exactly what it includes.
            </p>
          </div>
          <div className="type-info__concept">
            <div className="type-info__concept-title">Loans &amp; payoff tracking</div>
            <p>
              Pick Mortgage, Auto Loan, Student Loan, Credit Card or Loan and the payoff tracking
              comes with the account — no second record to create. Fill in the APR and minimum
              payment on the account page for projections, an amortization schedule and interest
              math. Until then you still get a working ledger.
            </p>
          </div>
        </div>

        {money && (
          <p className="type-info__see-how">
            <GuideTabLink tab="money" />
          </p>
        )}

        {context === 'import' && (
          <div className="type-info__concepts">
            <div className="type-info__section-title">Import, close, or leave out</div>
            <div className="type-info__concept">
              <div className="type-info__concept-title">
                Imported &amp; closed — the safe choice for a dormant account
              </div>
              <p>
                Everything imports. Every transaction counts toward net worth, reports and history,
                and transfers to it still pair up. The account is only hidden from the account
                pickers and report filters, and you can reopen it whenever you like.
              </p>
              <p>
                This is what you want for an account that went quiet years ago — you get the tidy
                list without paying for it in lost history.
              </p>
            </div>
            <div className="type-info__concept">
              <div className="type-info__concept-title">Left out — its history goes too</div>
              <p>
                The account and every transaction in it are never created. Your other accounts'
                balances stay correct, but net worth over time has a hole where that account should
                have been.
              </p>
              <p>
                It also breaks transfers. A transfer from an account you keep to one you leave out
                has nothing to pair with, so it arrives unlinked and reads as real income or
                spending in your reports. That is what the "transfers couldn't be matched" warning
                after an import is telling you — and leaving accounts out is what causes it.
              </p>
              <p>
                YNAB exports include accounts you closed years ago. Those are worth importing
                anyway: they carry the history that makes past months add up.
              </p>
            </div>
          </div>
        )}

        <div className="type-info__list">
          {rows.map((t) => (
            <div key={t.key} className="type-info__row">
              <div className="type-info__row-head">
                <span className="type-info__label">{t.label}</span>
                <span className={`type-info__chip type-info__chip--${t.classification}`}>
                  {t.classification}
                </span>
                <span className="type-info__chip">
                  {t.default_on_budget ? 'on budget' : 'off budget'}
                </span>
              </div>
              <p className="type-info__desc">
                {t.description ||
                  `Custom type — counts as ${t.classification === 'liability' ? 'a liability' : 'an asset'} in net worth.`}
              </p>
              {money && (
                <TypeMoneyLines
                  shapes={money.shapes}
                  classification={t.classification}
                  onBudget={t.default_on_budget}
                  countsAsSavings={t.default_counts_as_savings}
                />
              )}
            </div>
          ))}
        </div>
      </div>
    </Dialog>
  )
}
