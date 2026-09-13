import { SYSTEM_TAG_HELP } from '../../settings/TagsPanel/systemTagHelp'
import './TwoFacts.css'

const tagName = (key: string) => SYSTEM_TAG_HELP.find((t) => t.key === key)?.name ?? key

/** The two things every rule below reads. */
export function TwoFacts() {
  return (
    <div className="money-facts">
      <section className="money-facts__fact surface surface--raised">
        <h3 className="money-facts__title">1. What kind of account the money is in</h3>
        <p>
          <strong>On budget or off.</strong> On-budget accounts fund your categories. Off-budget
          accounts are tracked for net worth and never spent from the budget.
        </p>
        <p>
          <strong>Asset or liability.</strong> A liability is owed: a card on budget, a loan off it.
        </p>
        <p>
          <strong>Counts as savings.</strong> Only for an off-budget asset. On for a brokerage, off
          for a car or a house, and you can change it on the account.
        </p>
      </section>
      <section className="money-facts__fact surface surface--raised">
        <h3 className="money-facts__title">2. What the category is tagged</h3>
        <p>
          Most categories are just categories. Tag one <strong>{tagName('savings')}</strong> or{' '}
          <strong>{tagName('debt_principal')}</strong> and its outflows count that way, wherever the
          money went.
        </p>
        <p>
          A category in your income group means the money is income, ready to assign. No category on
          an inflow means the same.
        </p>
      </section>
    </div>
  )
}
