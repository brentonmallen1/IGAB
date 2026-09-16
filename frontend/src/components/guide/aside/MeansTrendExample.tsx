import { Link } from 'react-router-dom'
import { useFormatters } from '../../../hooks/useFormatters'
import { MeansTrendChart } from '../../reports/MeansTrendChart'
import { MetricCard } from '../../reports/MetricCard'
import {
  AT_MEANS_BAND_PCT,
  MEANS_TREND_POOL_MONTHS,
  meansTrend,
  meansTrendCountPhrase,
  meansTrendSub,
  meansTrendValue,
  type MeansStanding,
} from '../../reports/livingMeans'
import '../../reports/MeansStanding.css'
import { MEANS_EXAMPLE_MONTHS } from './meansExampleMonths'
import './MeansTrendExample.css'

const LEGEND: { standing: MeansStanding; label: string }[] = [
  { standing: 'below', label: `Below your means: kept more than ${AT_MEANS_BAND_PCT}%` },
  { standing: 'at', label: `At: within ${AT_MEANS_BAND_PCT}% either way` },
  { standing: 'above', label: `Above: spent more than ${AT_MEANS_BAND_PCT}% over income` },
]

const EXAMPLE_TREND = meansTrend(MEANS_EXAMPLE_MONTHS)

/** The Overview's Means trend, drawn by its own chart over invented months. */
export function MeansTrendExample() {
  const { formatMonthShort } = useFormatters()
  const trend = EXAMPLE_TREND
  const value = meansTrendValue(trend.recent)

  return (
    <div className="means-example">
      <p className="guide-article__lede">
        Your Means compares income with what living cost — spending plus debt payments — and gives a
        verdict. The Means trend card on the Overview shows it over the last twelve months, so you
        can see whether you are moving away from paycheck to paycheck.
      </p>

      <div className="surface surface--raised guide-article__card means-example__card">
        <span className="means-example__tag">Example</span>
        <div className="means-example__metric">
          <MetricCard
            label="Means trend"
            value={
              <span className={`means-standing-text means-standing--${trend.recent.standing}`}>
                {value}
              </span>
            }
            sub={`${meansTrendSub(trend)} · ${meansTrendCountPhrase(trend)}`}
          />
        </div>
        <MeansTrendChart
          trend={trend}
          formatMonth={formatMonthShort}
          label={meansTrendCountPhrase(trend)}
        />
        <ul className="means-example__legend" aria-label="Bar colours">
          {LEGEND.map((item) => (
            <li key={item.standing} className={`means-standing--${item.standing}`}>
              <span className="means-example__swatch" aria-hidden />
              {item.label}
            </li>
          ))}
        </ul>
      </div>

      <div className="guide-article__prose">
        <ul>
          <li>
            The headline is a {MEANS_TREND_POOL_MONTHS}-month average — the months’ income added up
            against their outflows added up — so a three-paycheck month or a yearly bill doesn’t
            whip it around.
          </li>
          <li>
            It uses the same ±{AT_MEANS_BAND_PCT}% band as Your Means, so the two cards never
            disagree.
          </li>
          <li>Money moved to savings is not an outflow; it is part of what you kept.</li>
          <li>Click the card for each month’s income, outflows and what was left over.</li>
        </ul>
      </div>
      <p className="guide-article__links">
        <Link to="/reports?tab=overview" className="guide-article__link">
          Open the Overview
        </Link>
      </p>
    </div>
  )
}
