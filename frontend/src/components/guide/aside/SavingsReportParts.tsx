import { Link } from 'react-router-dom'
import { savingsModeShort } from '../../../utils/savingsModes'
import { systemTagName } from '../../settings/TagsPanel/systemTagHelp'

const SAVINGS = systemTagName('savings')
const FUND = systemTagName('emergency_fund')

const PARTS: { title: string; lede: string; lines: string[] }[] = [
  {
    title: 'Saved',
    lede: 'Money that is savings now.',
    lines: [
      `${SAVINGS} and ${FUND} envelopes set to ${savingsModeShort('kept_here')}`,
      'Off-budget accounts that count as savings',
    ],
  },
  {
    title: 'On the way to savings',
    lede: 'Waiting to be sent.',
    lines: [
      `What ${SAVINGS} envelopes set to ${savingsModeShort('sent_out')} still hold`,
      'Counted as saved once it leaves, so not added to Saved',
    ],
  },
  {
    title: 'Sinking funds',
    lede: 'Spoken for.',
    lines: [
      `Envelopes tagged ${systemTagName('long_term_expense')}`,
      'Progress toward each one’s target',
    ],
  },
]

/** The Savings report's three totals, and why they are never added together. */
export function SavingsReportParts() {
  return (
    <div className="guide-article__prose">
      <div className="guide-article__cards">
        {PARTS.map((part) => (
          <section
            key={part.title}
            className="surface surface--raised guide-article__card guide-article__prose"
          >
            <h4 className="guide-article__prose-title">{part.title}</h4>
            <p>{part.lede}</p>
            <ul>
              {part.lines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </section>
        ))}
      </div>
      <p>
        The three are never added together. On-budget accounts are never added to any of them: their
        money is already in your envelopes, so adding both would count it twice.
      </p>
      <p className="guide-article__links">
        <Link to="/reports?tab=savings" className="guide-article__link">
          Open the Savings report
        </Link>
      </p>
    </div>
  )
}
