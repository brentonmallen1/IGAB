import { useState } from 'react'
import type { MeansMonth } from '../../types'
import { useFormatters } from '../../hooks/useFormatters'
import { Dialog } from '../common/Dialog/Dialog'
import { MetricCard } from './MetricCard'
import { MeansTrendChart } from './MeansTrendChart'
import {
  AT_MEANS_BAND_PCT,
  MEANS_TREND_CLAMP_PCT,
  MEANS_TREND_POOL_MONTHS,
  marginPhrase,
  meansTrend,
  meansTrendCountPhrase,
  meansTrendSub,
  meansTrendValue,
  netPhrase,
  type MeansTrend,
} from './livingMeans'
import {
  DetailFigure,
  DetailFigures,
  DetailList,
  DetailRow,
  DetailRows,
  DetailSection,
} from './ReportDetail'
import './MeansStanding.css'

/**
 * The Overview's Means trend card — the last twelve complete months read by
 * the Your Means rule — and the dialog it opens.
 *
 * Everything shown is `meansTrend()` over the served `means_months`; the
 * chart is the presentational `MeansTrendChart`. This file lays them out.
 */
export function MeansTrendCard({ months }: { months: MeansMonth[] }) {
  const { formatMonthShort } = useFormatters()
  const [open, setOpen] = useState(false)
  const trend = meansTrend(months)
  const value = meansTrendValue(trend.recent)

  return (
    <>
      <MetricCard
        label="Means trend"
        value={
          <span className={`means-standing-text means-standing--${trend.recent.standing}`}>
            {value}
          </span>
        }
        details={{ label: `Means trend ${value}. Show the months`, onOpen: () => setOpen(true) }}
        sub={
          <>
            {meansTrendSub(trend)}
            {trend.monthsWithIncome > 0 && (
              <MeansTrendChart
                trend={trend}
                formatMonth={formatMonthShort}
                variant="strip"
                label={meansTrendCountPhrase(trend)}
              />
            )}
          </>
        }
      />
      {open && <MeansTrendDialog trend={trend} onClose={() => setOpen(false)} />}
    </>
  )
}

function MeansTrendDialog({ trend, onClose }: { trend: MeansTrend; onClose: () => void }) {
  const { formatMoney, formatMonth, formatMonthShort } = useFormatters()
  const n = trend.bars.length

  return (
    <Dialog title="Means trend" onClose={onClose} historyKey="overview-means-trend" width="lg">
      <p className="dialog__body">
        {trend.monthsWithIncome > 0
          ? `${meansTrendCountPhrase(trend)}.`
          : 'No month in this stretch had income, so there is nothing to read outflows against.'}
      </p>

      <DetailFigures>
        <DetailFigure
          label={`Last ${MEANS_TREND_POOL_MONTHS} months`}
          value={meansTrendValue(trend.recent)}
          strong
        />
        {trend.prior && (
          <DetailFigure
            label={`${MEANS_TREND_POOL_MONTHS} months before`}
            value={meansTrendValue(trend.prior)}
          />
        )}
      </DetailFigures>

      {trend.monthsWithIncome > 0 && (
        <MeansTrendChart trend={trend} formatMonth={formatMonthShort} />
      )}

      <DetailSection title="Month by month">
        {n > 0 ? (
          <DetailRows>
            {trend.bars.map((bar) => (
              <DetailRow
                key={bar.month}
                name={formatMonth(bar.month)}
                nameNote={`${formatMoney(bar.income)} in · ${formatMoney(bar.outflows)} out`}
                amount={netPhrase(bar.reading.net, formatMoney)}
                amountNote={bar.reading.margin ? marginPhrase(bar.reading.margin) : 'No income'}
              />
            ))}
          </DetailRows>
        ) : (
          <p className="dialog__body dialog__body--muted">No complete months recorded yet.</p>
        )}
      </DetailSection>

      <DetailSection title="How this is read">
        <DetailList>
          <li>
            The headline pools the last {MEANS_TREND_POOL_MONTHS} complete months: their income
            added up against their outflows added up, not an average of three percentages.
          </li>
          <li>
            Bars above zero kept part of what came in; bars below zero ran short. The shaded band is
            the Your Means band — within {AT_MEANS_BAND_PCT}% of income either side reads as at your
            means. Bars stop at {MEANS_TREND_CLAMP_PCT}%; the table states the real figure.
          </li>
          <li>
            A large yearly bill can dip one month below the line; the{' '}
            {`${MEANS_TREND_POOL_MONTHS}-month`} figure softens it with the months around it.
          </li>
          <li>
            Outflows are spending plus debt payments. Money moved into savings is not an outflow —
            it is part of what was kept.
          </li>
        </DetailList>
      </DetailSection>
    </Dialog>
  )
}
