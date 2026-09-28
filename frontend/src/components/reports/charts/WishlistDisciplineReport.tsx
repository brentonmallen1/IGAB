import { useRef } from 'react'
import { useWishlistDisciplineReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import {
  afterTheWait,
  averageWaitSub,
  waitedOutShare,
  wishCount,
  wishes,
  wishlistOutcomes,
} from './wishlistOutcomes'
import { ReportHeader } from '../ReportHeader'

interface Props {
  budgetId: string
}

/**
 * What the cooling-off period actually did.
 *
 * The headline is money that was wanted, waited on, and then not spent —
 * which is the whole point of a wishlist with a waiting period, and the one
 * thing nothing in the app used to say out loud. All time on purpose: a habit
 * measured over twelve months forgets the wish you talked yourself out of two
 * years ago.
 */
export function WishlistDisciplineReport({ budgetId }: Props) {
  const { formatMoney } = useFormatters()
  const { data, isLoading, isError, error, refetch } = useWishlistDisciplineReport(budgetId)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading...</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />
  if (!data) return null

  const outcomes = wishlistOutcomes(data)
  const empty = wishCount(data) === 0

  return (
    <div className="report-section surface">
      <ReportHeader>
        <h2 className="report-section__title">Wishlist</h2>
        <ReportInfoButton title="Wishlist">
          <p>
            What the cooling-off period did. <strong>Waited it out</strong> is the share of the
            wishes you have decided — bought or let go — that you decided only after their waiting
            period was up. That is the part the wait can take credit for.
          </p>
          <p>
            <strong>Resisted</strong> is every wish you decided against, and <strong>Bought</strong>{' '}
            every one you bought; each says how many of them came after the wait. Letting a wish go
            on day three is still money not spent, but the wait played no part in it. Wishes bought
            before the wait was up are here too: the point is an honest picture of the habit, not a
            score.
          </p>
          <p>
            <strong>Waiting</strong> is what is still open. A wish whose waiting period is over is{' '}
            <em>ready to decide</em>: the wait has done its part.
          </p>
          <p>
            <strong>Average wait</strong> is the mean time from adding a wish to buying it, beside
            the waiting period new wishes get.
          </p>
          <p>
            Every wish counts, however long ago — a habit measured over the last year forgets what
            you talked yourself out of before that.
          </p>
        </ReportInfoButton>
        <div style={{ marginLeft: 'auto' }}>
          <ReportExportButton
            reportId="wishlist"
            getRows={() => [
              ...outcomes.map((o) => ({ metric: o.key, value: o.count })),
              { metric: 'waited_out_share', value: data.waited_out_share },
              { metric: 'resisted_count', value: data.resisted_count },
              { metric: 'resisted_total', value: data.resisted_total },
              { metric: 'bought_total', value: data.bought_total },
            ]}
            captureRef={captureRef}
          />
        </div>
      </ReportHeader>

      {empty ? (
        <div className="reports-empty">
          <p>Nothing on the wishlist yet.</p>
          <p style={{ fontSize: 'var(--font-size-xs)', marginTop: 8 }}>
            Add something you want and give it a waiting period. What you decide at the end of it is
            what this report is made of.
          </p>
        </div>
      ) : (
        <div ref={captureRef} className="report-capture">
          <MetricRow>
            <MetricCard
              label="Waited it out"
              value={waitedOutShare(data.waited_out_share)}
              sub={
                data.decided_count === 0
                  ? 'nothing decided yet'
                  : `${data.waited_out_count} of ${wishes(data.decided_count)} decided`
              }
            />
            <MetricCard
              label="Resisted"
              value={formatMoney(data.resisted_total)}
              // resisted_count sums the same wishes as the figure above it —
              // early drops included, which is why the sub-line says how many
              // came after the wait rather than crediting the wait with all.
              sub={afterTheWait(data.resisted_count, data.cooled_then_dropped)}
            />
            <MetricCard
              label="Bought"
              value={formatMoney(data.bought_total)}
              sub={afterTheWait(data.bought_count, data.cooled_then_bought)}
            />
            <MetricCard
              label="Waiting"
              value={formatMoney(data.open_total)}
              sub={`${wishes(data.still_open)} · ${data.ready_to_decide} ready to decide`}
            />
            <MetricCard
              // A mean, so "Average" — "Typical" is a median everywhere else.
              label="Average wait"
              // None, not zero: an average of no purchases is not "same day".
              value={data.avg_days_to_buy === null ? '—' : `${data.avg_days_to_buy}d`}
              sub={averageWaitSub(data.avg_days_to_buy, data.cooling_days)}
            />
          </MetricRow>

          <table className="report-table">
            <caption className="sr-only">What happened to each wish</caption>
            <thead>
              <tr>
                <th scope="col" style={{ textAlign: 'left' }}>
                  Outcome
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Wishes
                </th>
              </tr>
            </thead>
            <tbody>
              {outcomes.map((o) => (
                <tr key={o.key}>
                  <td>{o.label}</td>
                  <td style={{ textAlign: 'right' }}>{o.count}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {data.avg_wish_cost !== null && (
            <p className="reports-note">
              The average wish costs {formatMoney(data.avg_wish_cost)}.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
