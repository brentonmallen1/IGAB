import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { AsideAnchor } from '../../../utils/guideLinks'
import { guideTabHref } from '../../../utils/guideLinks'
import { CatchOuts } from '../CatchOuts'
import { ASIDE_CATCH_OUTS } from './asideCatchOuts'
import { EmergencyFundExplainer } from './EmergencyFundExplainer'
import { MeansTrendExample } from './MeansTrendExample'
import { SavingsModesExample } from './SavingsModesExample'
import { SavingsReportParts } from './SavingsReportParts'
import { SpreadExample } from './SpreadExample'
import { WhichTag } from './WhichTag'
import '../GuideArticle.css'

function Section({
  anchor,
  title,
  lede,
  children,
}: {
  anchor: AsideAnchor
  title: string
  lede?: ReactNode
  children: ReactNode
}) {
  return (
    <section id={anchor} className="guide-article__section" aria-labelledby={`${anchor}-title`}>
      <h3 className="guide-article__heading" id={`${anchor}-title`}>
        {title}
      </h3>
      {lede && <p className="guide-article__lede">{lede}</p>}
      {children}
    </section>
  )
}

/**
 * Setting money aside: savings, the emergency fund, sinking funds, and the
 * figures that read them.
 *
 * Examples only — nothing here reads the budget. Every example figure is
 * served by, or computed with, the functions the reports run: the month by
 * `guide/money-moves/month`, the spread by `guide/examples/spread`, the Means
 * trend by `meansTrend()` and its own chart, the Counting line by the real
 * component. The prose around them is the only thing written here.
 */
export function AsidePanel() {
  return (
    <section className="guide-article">
      <header className="guide-roadmap__header">
        <div>
          <h2 className="guide-roadmap__title">Setting money aside</h2>
          <p className="guide-roadmap__lede">
            Savings, an emergency fund and sinking funds all set money aside, and each counts
            differently. Every amount on this page is an invented example; the reports show your
            own. For how every transaction is counted, see{' '}
            <Link to={guideTabHref('money')}>How money counts</Link>.
          </p>
        </div>
      </header>

      <Section
        anchor="savings-modes"
        title="Two ways a Savings category counts"
        lede="The question is when money counts as saved: when you set it aside, or when it leaves the budget. Each Savings category picks one. Sent out suits money on its way to a savings vehicle you may not track; kept here suits money that stays in the budget, like a cushion or a down payment."
      >
        <SavingsModesExample />
      </Section>

      <Section anchor="which-tag" title="Which tag do I use?">
        <WhichTag />
      </Section>

      <Section anchor="emergency-fund" title="Your emergency fund: chosen, not guessed">
        <EmergencyFundExplainer />
      </Section>

      <Section anchor="sinking-funds" title="Sinking funds, spread across the year">
        <SpreadExample />
      </Section>

      <Section anchor="means-trend" title="Am I spending everything that comes in?">
        <MeansTrendExample />
      </Section>

      <Section anchor="savings-report" title="The Savings report, in three parts">
        <SavingsReportParts />
      </Section>

      <div className="guide-article__section">
        <h3 className="guide-article__heading">Things that catch people out</h3>
        <CatchOuts items={ASIDE_CATCH_OUTS} />
      </div>
    </section>
  )
}
