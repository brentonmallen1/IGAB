import { useRef } from 'react'
import { useWishlistDisciplineReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'

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

  const decided = data.cooled_then_bought + data.cooled_then_dropped + data.bought_early
  const empty = decided === 0 && data.still_open === 0 && data.unplaced === 0

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Wishlist</h2>
        <ReportInfoButton title="Wishlist">
          <p>
            What the cooling-off period did. <strong>Resisted</strong> is money you wanted, waited
            on, and then decided against — the number this report exists for.
          </p>
          <p>
            <strong>Bought early</strong> counts wishes bought before their waiting period was up.
            It is here because the point is an honest picture of the habit, not a score.
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
              { metric: 'cooled_then_dropped', value: data.cooled_then_dropped },
              { metric: 'cooled_then_bought', value: data.cooled_then_bought },
              { metric: 'bought_early', value: data.bought_early },
              { metric: 'still_open', value: data.still_open },
              { metric: 'resisted_total', value: data.resisted_total },
              { metric: 'bought_total', value: data.bought_total },
            ]}
            captureRef={captureRef}
          />
        </div>
      </div>

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
              label="Resisted"
              value={formatMoney(data.resisted_total)}
              sub={`${data.cooled_then_dropped} talked yourself out of`}
            />
            <MetricCard
              label="Bought"
              value={formatMoney(data.bought_total)}
              sub={`${data.cooled_then_bought} after waiting`}
            />
            <MetricCard
              label="Waiting"
              value={formatMoney(data.open_total)}
              sub={`${data.still_open} still open`}
            />
            <MetricCard
              label="Typical wait"
              // None, not zero: an average of no purchases is not "same day".
              value={data.avg_days_to_buy === null ? '—' : `${data.avg_days_to_buy}d`}
              sub={data.avg_days_to_buy === null ? 'nothing bought yet' : 'from wish to purchase'}
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
              <tr>
                <td>Waited, then decided against</td>
                <td style={{ textAlign: 'right' }}>{data.cooled_then_dropped}</td>
              </tr>
              <tr>
                <td>Waited, then bought</td>
                <td style={{ textAlign: 'right' }}>{data.cooled_then_bought}</td>
              </tr>
              <tr>
                <td>Bought before the wait was up</td>
                <td style={{ textAlign: 'right' }}>{data.bought_early}</td>
              </tr>
              <tr>
                <td>Still waiting</td>
                <td style={{ textAlign: 'right' }}>{data.still_open}</td>
              </tr>
              {data.unplaced > 0 && (
                <tr>
                  {/* Shown rather than folded into a bucket they might not
                      belong in — these are wishes with no waiting period, or
                      ones that ended before the app recorded when. */}
                  <td>Ended, but not against a waiting period</td>
                  <td style={{ textAlign: 'right' }}>{data.unplaced}</td>
                </tr>
              )}
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
