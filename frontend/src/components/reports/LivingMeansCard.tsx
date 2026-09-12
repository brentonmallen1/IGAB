import { useState } from 'react'
import type { DashboardMetrics } from '../../types'
import { useFormatters } from '../../hooks/useFormatters'
import { Dialog } from '../common/Dialog/Dialog'
import { MetricCard } from './MetricCard'
import { sharePhrase } from './drillDownTotals'
import { AT_MEANS_BAND_PCT, meansReading, netPhrase, type MeansReading } from './livingMeans'
import { spendingDelta } from './overviewMetrics'
import { DetailFigure, DetailFigures, DetailRow, DetailRows, DetailSection } from './ReportDetail'
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
    <>
      <MetricCard
        label="Your Means"
        value={
          <span className={`living-means__verdict living-means__verdict--${reading.standing}`}>
            {reading.short}
          </span>
        }
        details={{
          label: `${reading.label}. Show what is contributing`,
          onOpen: () => setOpen(true),
        }}
        sub={
          reading.standing === 'unknown'
            ? 'No income recorded'
            : netPhrase(reading.net, formatMoney)
        }
      />
      {open && <LivingMeansDialog data={data} reading={reading} onClose={() => setOpen(false)} />}
    </>
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

      <DetailFigures>
        <DetailFigure label="Income" value={formatMoney(data.income_this_month)} />
        <DetailFigure label="Spending" value={formatMoney(spending)} />
        <DetailFigure label="Debt payments" value={formatMoney(data.debt_payments_this_month)} />
        <DetailFigure label="Outflows" value={formatMoney(data.outflows_this_month)} strong />
        <DetailFigure
          label={reading.net < 0 ? 'Short' : 'Left over'}
          value={formatMoney(Math.abs(reading.net))}
          strong
        />
      </DetailFigures>

      <DetailSection title="How this is read">
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
      </DetailSection>

      <DetailSection title="Biggest spending">
        {data.top_categories.length > 0 ? (
          <DetailRows>
            {data.top_categories.map((c) => (
              <DetailRow
                key={c.id}
                name={c.name}
                nameNote={c.group_name}
                amount={formatMoney(c.total)}
                amountNote={sharePhrase(c.total, spending, 'of spending')}
              />
            ))}
          </DetailRows>
        ) : (
          <p className="dialog__body dialog__body--muted">No spending in this period.</p>
        )}
      </DetailSection>

      <DetailSection title="Against the prior period">
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
      </DetailSection>
    </Dialog>
  )
}

/** The change in words at the precision the Spent card prints it. */
function formatDelta(pct: number): string {
  const magnitude = Math.abs(pct).toFixed(1)
  if (magnitude === '0.0') return 'unchanged'
  return `${pct > 0 ? 'up' : 'down'} ${magnitude}%`
}
