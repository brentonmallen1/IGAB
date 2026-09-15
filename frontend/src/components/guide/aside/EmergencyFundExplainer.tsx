import { Link } from 'react-router-dom'
import { sectionHref } from '../../../pages/SettingsPage/settingsSections'
import { guideToolHref } from '../../../utils/guideLinks'
import { savingsModeShort } from '../../../utils/savingsModes'
import { EmergencyFundCountingView } from '../../emergencyFund/EmergencyFundCounting'
import { systemTagName } from '../../settings/TagsPanel/systemTagHelp'
import { EXAMPLE_FUND } from './exampleFund'
import './EmergencyFundExplainer.css'

const FUND_TAG = systemTagName('emergency_fund')
const TAGS_HREF = sectionHref({ id: 'tags', page: 'settings' })

/** Your emergency fund: chosen, not guessed. */
export function EmergencyFundExplainer() {
  return (
    <div className="ef-explainer">
      <div className="guide-article__cards">
        <section className="surface surface--raised guide-article__card guide-article__prose">
          <h4 className="guide-article__prose-title">What counts</h4>
          <ul>
            <li>
              The Available balance of envelopes tagged <strong>{FUND_TAG}</strong>
            </li>
            <li>
              Plus off-budget accounts marked <strong>Counts toward emergency fund</strong>
            </li>
            <li>Plus an amount you say you keep elsewhere, like cash at another bank</li>
          </ul>
          <p>
            Measured in months of essentials: a starter cushion first, then three to six months.
            Nothing is guessed from names or account types.
          </p>
        </section>

        <section className="surface surface--raised guide-article__card guide-article__prose">
          <h4 className="guide-article__prose-title">Every screen says what it counted</h4>
          <div className="ef-explainer__example">
            <span className="ef-explainer__example-label">Example</span>
            <EmergencyFundCountingView fund={EXAMPLE_FUND} />
          </div>
          <p>
            The Guide, the Emergency Fund and Essentials reports and the emergency fund sizer all
            show this line, with a Change button.
          </p>
        </section>
      </div>

      <section className="surface surface--raised guide-article__card guide-article__prose">
        <h4 className="guide-article__prose-title">Three places to choose</h4>
        <ul>
          <li>
            <strong>On the category.</strong> Open it on the <Link to="/budget">Budget</Link> page
            and add the {FUND_TAG} tag, like any tag.
          </li>
          <li>
            <strong>On the tag.</strong> <Link to={TAGS_HREF}>Settings → Tags</Link> → {FUND_TAG}{' '}
            opens one checklist of envelopes, off-budget accounts and an amount kept elsewhere.
          </li>
          <li>
            <strong>Where it is shown.</strong> The Change button opens the same checklist from the
            Guide, the <Link to="/reports?tab=emergency-fund">Emergency Fund</Link> and{' '}
            <Link to="/reports?tab=essentials">Essentials</Link> reports, and the{' '}
            <Link to={guideToolHref('emergency-fund')}>sizer</Link>.
          </li>
        </ul>
      </section>

      <div className="guide-article__cards">
        <section className="surface surface--raised guide-article__card guide-article__prose">
          <h4 className="guide-article__prose-title">An account that holds several things</h4>
          <p>
            Keep it on budget. Its envelopes say what each dollar is for, so only the {FUND_TAG}{' '}
            envelope counts toward the fund. An on-budget account cannot be marked.
          </p>
        </section>
        <section className="surface surface--raised guide-article__card guide-article__prose">
          <h4 className="guide-article__prose-title">An account that is all emergency money</h4>
          <p>
            Off budget, it has no envelopes, so mark the whole account. It must also count as
            savings; the checklist turns that on for you and says so.
          </p>
        </section>
      </div>

      <p className="guide-article__lede">
        {FUND_TAG} envelopes have the same {savingsModeShort('sent_out')} /{' '}
        {savingsModeShort('kept_here')} setting as {systemTagName('savings')}, and start as{' '}
        {savingsModeShort('kept_here')}. The setting changes your savings rate, never the emergency
        fund total, which always reads the envelope’s balance.
      </p>
    </div>
  )
}
