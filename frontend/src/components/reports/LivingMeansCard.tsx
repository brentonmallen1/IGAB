import { useState } from 'react'
import type { DashboardMetrics } from '../../types'
import { useFormatters } from '../../hooks/useFormatters'
import { Dialog } from '../common/Dialog/Dialog'
import { Surface } from '../common/Surface'
import { MetricCard } from './MetricCard'
import { shareOfTotal } from './drillDownTotals'
import { AT_MEANS_BAND_PCT, meansReading, netPhrase, type MeansReading } from './livingMeans'
import { spendingDelta } from './overviewMetrics'
import './LivingMeansCard.css'

/**
 * The Overview's above/at/below-your-means card, and the dialog it opens.
 *
 * Both read `meansReading` — the verdict, the band and the net live there and
 * nowhere else. This file only lays the served figures out.
 */
export function LivingMeansCard({ data }: { data: DashboardMetrics }) {
  const { formatMoney } = useFormatters()
  const [open, setOpen] = useState(false)
  const reading = meansReading(data.income_this_month, data.outflows_this_month)

  return (
    <div className="living-means">
      <MetricCard
        label="Your Means"
        value={
          <button
            type="button"
            className={`living-means__open living-means__open--${reading.standing}`}
            aria-haspopup="dialog"
            aria-label={`${reading.label}. Show what is contributing`}
            onClick={() => setOpen(true)}
          >
            {reading.short}
          </button>
        }
        sub={
          reading.standing === 'unknown'
            ? 'No income recorded'
            : netPhrase(reading.net, formatMoney)
        }
      />
      {open && <LivingMeansDialog data={data} reading={reading} onClose={() => setOpen(false)} />}
    </div>
  )
}

function LivingMeansDialog({
  data,
  reading,
  onClose,
}: {
  data: DashboardMetrics
  reading: MeansReading
  onClose: () => void
}) {
  const { formatMoney } = useFormatters()
  const spending = data.expenses_this_month
  const prior = data.expenses_prev_month

  return (
    <Dialog title={reading.label} onClose={onClose} historyKey="overview-living-means">
      <p className="dialog__body">{reading.note}</p>

      <Surface as="dl" variant="sunken" className="living-means__figures">
        <Figure label="Income" value={formatMoney(data.income_this_month)} />
        <Figure label="Spending" value={formatMoney(spending)} />
        <Figure label="Debt payments" value={formatMoney(data.debt_payments_this_month)} />
        <Figure label="Outflows" value={formatMoney(data.outflows_this_month)} strong />
        <Figure
          label={reading.net < 0 ? 'Short' : 'Left over'}
          value={formatMoney(Math.abs(reading.net))}
          strong
        />
      </Surface>

      <section className="living-means__section" aria-label="How the verdict is read">
        <h4 className="living-means__heading">How this is read</h4>
        <p className="dialog__body">
          Outflows are spending plus debt payments. Money moved into savings is not an outflow — it
          is part of what was left over.
        </p>
        {reading.band ? (
          <ul className="living-means__bands">
            <li>
              <strong>Below your means</strong>: outflows under {formatMoney(reading.band.low)}.
            </li>
            <li>
              <strong>At your means</strong>: {formatMoney(reading.band.low)} to{' '}
              {formatMoney(reading.band.high)}, within {AT_MEANS_BAND_PCT}% of income either side.
            </li>
            <li>
              <strong>Above your means</strong>: outflows over {formatMoney(reading.band.high)}.
            </li>
          </ul>
        ) : (
          <p className="dialog__body dialog__body--muted">
            With no income to measure against, there is no band to read outflows by.
          </p>
        )}
      </section>

      <section className="living-means__section" aria-label="Biggest spending">
        <h4 className="living-means__heading">Biggest spending</h4>
        {data.top_categories.length > 0 ? (
          <ol className="living-means__top">
            {data.top_categories.map((c) => {
              const share = shareOfTotal(c.total, spending)
              return (
                <li key={c.id} className="living-means__top-item">
                  <span className="living-means__top-name">
                    {c.name}
                    <span className="living-means__top-group">{c.group_name}</span>
                  </span>
                  <span className="living-means__top-amount">
                    {formatMoney(c.total)}
                    {share !== null && (
                      <span className="living-means__top-share">
                        {share.toFixed(0)}% of spending
                      </span>
                    )}
                  </span>
                </li>
              )
            })}
          </ol>
        ) : (
          <p className="dialog__body dialog__body--muted">No spending in this period.</p>
        )}
      </section>

      <section className="living-means__section" aria-label="Spending against the prior period">
        <h4 className="living-means__heading">Against the prior period</h4>
        <p className="dialog__body">
          {prior > 0 ? (
            <>
              Spending was {formatMoney(spending)} against {formatMoney(prior)} in the period of the
              same length just before — {formatDelta(spendingDelta(spending, prior))}.
            </>
          ) : (
            <>No spending in the period of the same length just before, so nothing to compare.</>
          )}
        </p>
      </section>
    </Dialog>
  )
}

function Figure({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className={`living-means__figure${strong ? ' living-means__figure--strong' : ''}`}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

/** The change in words at the precision the Spent card prints it. */
function formatDelta(pct: number): string {
  const magnitude = Math.abs(pct).toFixed(1)
  if (magnitude === '0.0') return 'unchanged'
  return `${pct > 0 ? 'up' : 'down'} ${magnitude}%`
}
