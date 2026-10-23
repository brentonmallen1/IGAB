import type { IncomeSplitReport } from '../../types'
import { BUCKET_LABEL, RULE, barGeometry, shares, tooUnfiled } from '../../utils/incomeSplit'
import './IncomeSplitBar.css'

/**
 * The split as one bar: needs, wants (its committed part darker), savings &
 * debt, uncategorized and left over, with the rule's 50 and 80 as ticks and
 * the 50/30/20 split as a faint strip underneath.
 *
 * One bar, two callers — the Income Split report and the Guide's roadmap
 * node — so the Guide never draws a second reading of the same money.
 * `compact` drops the in-bar labels and the tick numbers for a smaller frame.
 */
export function IncomeSplitBar({
  data,
  compact = false,
}: {
  data: IncomeSplitReport
  compact?: boolean
}) {
  const bar = barGeometry(data)
  const pct = shares(data)
  if (!bar || !pct) return null
  return (
    <div
      className={`income-split-bar income-split-palette ${compact ? 'income-split-bar--compact' : ''} ${tooUnfiled(data) ? 'is-unfiled' : ''}`}
    >
      {!compact && (
        <div className="income-split-bar__ticks" aria-hidden="true">
          {bar.ticks.map((t, i) => (
            <span key={t} style={{ left: `${t}%` }}>
              {i === 0 ? RULE.needs : RULE.needs + RULE.wants}%
            </span>
          ))}
        </div>
      )}
      <div
        className="income-split-bar__bar"
        role="img"
        aria-label={`Needs ${pct.needs}%, wants ${pct.wants}%, savings and debt ${pct.savings}%, uncategorized ${pct.uncategorized}%, left over ${pct.left}% of take-home`}
      >
        {bar.segments.map((s) => (
          <span
            key={s.key}
            className={`income-split-bar__seg income-split-bar__seg--${s.key}`}
            style={{ width: `${s.width}%` }}
          >
            {!compact && s.width >= 14 && s.key !== 'committed' && s.key !== 'left' && (
              <span className="income-split-bar__label">
                {BUCKET_LABEL[s.key]} {pct[s.key]}%
              </span>
            )}
          </span>
        ))}
        {bar.ticks.map((t) => (
          <span
            key={t}
            className="income-split-bar__tick"
            style={{ left: `${t}%` }}
            aria-hidden="true"
          />
        ))}
        {bar.over > 0 && (
          <span
            className="income-split-bar__income-line"
            style={{ left: `${bar.incomeAt}%` }}
            aria-hidden="true"
          />
        )}
      </div>
      <div className="income-split-bar__rule" aria-hidden="true">
        <span style={{ width: `${(RULE.needs * bar.incomeAt) / 100}%` }} />
        <span style={{ width: `${(RULE.wants * bar.incomeAt) / 100}%` }} />
        <span style={{ width: `${(RULE.savings * bar.incomeAt) / 100}%` }} />
      </div>
    </div>
  )
}
