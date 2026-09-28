import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAccountTypes } from '../../../api/accountTypes'
import { liabilityTypeLabel } from '../../../utils/liabilityTypeLabel'
import { AlertTriangle } from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useLiabilitiesReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import { ReportErrorState } from '../ReportErrorState'
import { ChartTooltip } from './ChartTooltip'
import { chartColor } from './chartColors'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { LogScaleToggle, logAxisProps } from './logScale'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import {
  AT_MINIMUM,
  AT_MINIMUM_MEANS,
  AT_YOUR_PACE,
  AT_YOUR_PACE_MEANS,
  NEVER_AT_THIS_PAYMENT,
  PACE_MISSING,
  TERMS_DISAGREE,
  carryingSub,
  closedDebtNote,
  drawnLiabilities,
  interestRemainingSub,
  paceCell,
  totalLiabilitiesSub,
} from './liabilitiesView'
import { ReportRangeSelect } from './rangeSelect'
import { useReportMonths } from '../../../stores/reportStore'
import { formatRate } from '../../../utils/rate'
import { arrivalMarks } from '../../../utils/trackingStart'
import { arrivalLines } from './arrivalLines'
import { TrackingStartNote } from './TrackingStartNote'
import './LiabilitiesReport.css'
import { ReportHeader } from '../ReportHeader'

interface Props {
  budgetId: string
}

type SortKey = 'balance' | 'rate' | 'baseline' | 'live' | 'interest'

export function LiabilitiesReport({ budgetId }: Props) {
  const navigate = useNavigate()
  const { formatMoney, formatMoneyOrDash, formatMonth, formatMonthShort } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const [typeFilter, setTypeFilter] = useState<string | null>(null)
  const [modeFilter, setModeFilter] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('balance')
  const [sortDesc, setSortDesc] = useState(true)
  const [logScale, setLogScale] = useState(false)
  const captureRef = useRef<HTMLDivElement>(null)
  const months = useReportMonths()

  const { data, isLoading, isError, error, refetch } = useLiabilitiesReport(
    budgetId,
    typeFilter ?? undefined,
    modeFilter ?? undefined,
    months
  )
  // Unfiltered call drives the filter pills so options don't vanish
  const { data: allData } = useLiabilitiesReport(budgetId, undefined, undefined, months)
  // Labels come from the registry, so a custom liability type reads as itself
  const { data: accountTypes } = useAccountTypes(budgetId)

  const items = useMemo(() => {
    const rows = [...(data?.items ?? [])]
    const value = (row: (typeof rows)[number]) => {
      switch (sortKey) {
        case 'balance':
          return row.current_balance
        // Unknown sorts to one end rather than mixing in with real zeros —
        // a 0% promo card and a card with no APR entered are different things.
        case 'rate':
          return row.interest_rate === null ? -Infinity : row.interest_rate
        case 'baseline':
          return row.baseline_payoff_date ?? '9999'
        case 'live':
          return row.live_payoff_date ?? '9999'
        // A debt the minimum never retires has no bill because it is
        // unbounded, not because it is small: it sorts above every figure.
        case 'interest':
          if (row.baseline_never_pays_off) return Infinity
          return row.total_interest_remaining === null ? -Infinity : row.total_interest_remaining
      }
    }
    rows.sort((a, b) => {
      const av = value(a)
      const bv = value(b)
      const cmp = av < bv ? -1 : av > bv ? 1 : 0
      return sortDesc ? -cmp : cmp
    })
    return rows
  }, [data, sortKey, sortDesc])

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const presentTypes = [...new Set((allData?.items ?? []).map((i) => i.liability_type))]
  const closedCount = data?.closed_with_balance_count ?? 0
  const closedOwed = formatMoney(data?.closed_with_balance_total ?? 0)
  const series = data?.balance_over_time ?? []
  // A debt absent from a month (before its first point) is null there — a
  // gap, where it read 0 and its arrival drew as a cliff. One zero across the
  // whole window is not drawn at all.
  const drawn = drawnLiabilities(data?.items ?? [], series)
  const chartPoints = series.map((p) => {
    const point: Record<string, number | string | null> = { date: formatMonthShort(p.date) }
    for (const item of drawn) {
      point[item.name] = p.per_liability[item.liability_id] ?? null
    }
    return point
  })
  const marks = arrivalMarks(series, formatMoney)

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDesc((d) => !d)
    else {
      setSortKey(key)
      setSortDesc(true)
    }
  }

  function sortableProps(key: SortKey) {
    return {
      tabIndex: 0,
      'aria-sort': (sortKey === key ? (sortDesc ? 'descending' : 'ascending') : undefined) as
        'ascending' | 'descending' | undefined,
      onClick: () => toggleSort(key),
      onKeyDown: (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          toggleSort(key)
        }
      },
    }
  }

  return (
    <div className="report-section surface">
      <ReportHeader>
        <h2 className="report-section__title">Liabilities</h2>
        <ReportInfoButton title="Liabilities">
          <p>
            A consolidated rollup of every tracked liability —{' '}
            <strong>how's all my debt doing</strong> in one place.
          </p>
          <p>
            <strong>{AT_MINIMUM}</strong>: {AT_MINIMUM_MEANS}. <strong>{AT_YOUR_PACE}</strong>:{' '}
            {AT_YOUR_PACE_MEANS}. Where a cell has no date it says why — no APR and minimum on file,
            payments that arrive as plain deposits rather than transfers, or fewer than two months
            with a payment. <strong>Interest left</strong> is at the minimum.
          </p>
          <p>
            <em>{TERMS_DISAGREE}</em> marks a loan whose payment does not match what its own
            principal, rate and term imply — usually taxes and insurance folded into it, which makes
            every projection run faster than the loan does.
          </p>
          <p>
            The chart follows the report range. A debt appears the month its balance was first
            known, and a numbered line marks that month — a debt added, not borrowed then.
          </p>
          <p>
            Click a row for the full deep-dive: amortization schedule, paydown chart, payoff pill,
            and what-if extra payments.
          </p>
          <ReportScopeNote report="liabilities" />
        </ReportInfoButton>
        <div className="flex-row ms-auto" style={{ flexWrap: 'wrap' }}>
          {presentTypes.length > 1 &&
            presentTypes.map((t) => (
              <button
                key={t}
                type="button"
                className={`report-btn ${typeFilter === t ? 'report-btn--active' : ''}`}
                onClick={() => setTypeFilter(typeFilter === t ? null : t)}
              >
                {liabilityTypeLabel(t, accountTypes)}
              </button>
            ))}
          {(['managed', 'unmanaged'] as const).map((m) => (
            <button
              key={m}
              type="button"
              className={`report-btn ${modeFilter === m ? 'report-btn--active' : ''}`}
              onClick={() => setModeFilter(modeFilter === m ? null : m)}
            >
              {m === 'managed' ? 'From accounts' : 'Manual'}
            </button>
          ))}
          <ReportRangeSelect />
          <LogScaleToggle enabled={logScale} onToggle={() => setLogScale((v) => !v)} />
          <ReportExportButton
            reportId="liabilities"
            getRows={() =>
              (data?.items ?? []).map((i) => ({
                name: i.name,
                type: i.liability_type,
                mode: i.mode,
                balance: i.current_balance,
                interest_rate: i.interest_rate === null ? '' : i.interest_rate,
                at_minimum: i.baseline_payoff_date ?? '',
                at_your_pace: i.live_payoff_date ?? '',
                interest_remaining:
                  i.total_interest_remaining === null ? '' : i.total_interest_remaining,
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </ReportHeader>

      <div ref={captureRef} className="report-capture">
        {(data?.items.length ?? 0) === 0 ? (
          <div className="reports-empty">
            {closedDebtNote(closedCount, closedOwed, true) ??
              'No liabilities tracked yet — add one from the Liabilities section in the sidebar.'}
          </div>
        ) : (
          <>
            <MetricRow>
              {/* Every debt, on-budget credit cards included. The sidebar's
                  Liabilities section deliberately sums something narrower —
                  what that section lists, with cards counted under their own
                  account type — so the two figures differ on purpose. */}
              <MetricCard
                label="Total Liabilities"
                value={formatMoney(data!.total_balance)}
                sub={totalLiabilitiesSub(closedCount)}
              />
              {/* Rows without terms, or that the minimum never pays off,
                  contribute no interest, so say the total is partial rather
                  than let it read as the whole figure. */}
              <MetricCard
                label="Interest Remaining"
                value={formatMoney(data!.total_interest_remaining)}
                sub={interestRemainingSub(
                  data!.liabilities_missing_terms,
                  formatMoney(data!.missing_terms_balance),
                  data!.liabilities_never_paying_off
                )}
              />
              <MetricCard
                label="Liabilities"
                value={String(data!.items.length)}
                sub={carryingSub(data!.carrying_balance_count, data!.items.length)}
              />
            </MetricRow>
            {closedCount > 0 && (
              <p className="report-note">{closedDebtNote(closedCount, closedOwed, false)}</p>
            )}

            {chartPoints.length > 1 && drawn.length > 0 && (
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={chartPoints} margin={{ top: 16, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                    minTickGap={40}
                  />
                  <YAxis
                    tickFormatter={moneyAxis.tickFormatter}
                    tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                    width={moneyAxis.width}
                    {...logAxisProps(logScale)}
                  />
                  <Tooltip
                    content={<ChartTooltip showTotal formatter={formatMoney} />}
                    offset={16}
                    isAnimationActive={false}
                  />
                  <Legend />
                  {arrivalLines(marks, (i) => String(chartPoints[i].date))}
                  {drawn.map((item, idx) => (
                    <Area
                      key={item.liability_id}
                      type="linear"
                      dataKey={item.name}
                      // Stacked areas lie on a log axis — log mode overlays
                      // each liability as its own line instead
                      stackId={logScale ? undefined : 'liability'}
                      stroke={chartColor(idx)}
                      strokeWidth={logScale ? 2 : 1}
                      fill={chartColor(idx)}
                      fillOpacity={logScale ? 0 : 0.35}
                    />
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            )}
            <TrackingStartNote
              marks={marks}
              formatMoney={formatMoney}
              formatMonthShort={formatMonthShort}
            />

            <div className="liabilities-report__table-wrap">
              <table className="liabilities-report__table">
                <caption className="sr-only">Liabilities summary</caption>
                <thead>
                  <tr>
                    <th scope="col">Liability</th>
                    <th scope="col" className="num sortable" {...sortableProps('balance')}>
                      Balance{sortKey === 'balance' ? (sortDesc ? ' ↓' : ' ↑') : ''}
                    </th>
                    <th scope="col" className="num sortable" {...sortableProps('rate')}>
                      Rate{sortKey === 'rate' ? (sortDesc ? ' ↓' : ' ↑') : ''}
                    </th>
                    <th
                      scope="col"
                      className="sortable"
                      title={AT_MINIMUM_MEANS}
                      {...sortableProps('baseline')}
                    >
                      {AT_MINIMUM}
                      {sortKey === 'baseline' ? (sortDesc ? ' ↓' : ' ↑') : ''}
                    </th>
                    <th
                      scope="col"
                      className="sortable"
                      title={AT_YOUR_PACE_MEANS}
                      {...sortableProps('live')}
                    >
                      {AT_YOUR_PACE}
                      {sortKey === 'live' ? (sortDesc ? ' ↓' : ' ↑') : ''}
                    </th>
                    <th scope="col" className="num sortable" {...sortableProps('interest')}>
                      Interest left{sortKey === 'interest' ? (sortDesc ? ' ↓' : ' ↑') : ''}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => {
                    const pace = paceCell(item, formatMonth)
                    return (
                      <tr
                        key={item.liability_id}
                        tabIndex={0}
                        onClick={() => navigate(`/liabilities/${item.liability_id}`)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') navigate(`/liabilities/${item.liability_id}`)
                        }}
                        title="Open liability details"
                      >
                        <td>
                          <span className="liabilities-report__name">{item.name}</span>
                          <span className="liabilities-report__type">
                            {liabilityTypeLabel(item.liability_type, accountTypes)} ·{' '}
                            {item.mode === 'managed' ? 'from account' : 'manual'}
                          </span>
                          {item.terms_disagree && (
                            <span className="liabilities-report__warning">
                              <AlertTriangle size={12} aria-hidden /> {TERMS_DISAGREE}
                            </span>
                          )}
                        </td>
                        <td className="num">{formatMoney(item.current_balance)}</td>
                        <td className="num">
                          {item.interest_rate === null ? (
                            <span className="liabilities-report__why">Not set</span>
                          ) : (
                            formatRate(item.interest_rate)
                          )}
                        </td>
                        <td>
                          {item.baseline_never_pays_off ? (
                            NEVER_AT_THIS_PAYMENT
                          ) : item.baseline_payoff_date ? (
                            formatMonth(item.baseline_payoff_date)
                          ) : (
                            <span
                              className="liabilities-report__why"
                              title={PACE_MISSING.no_terms.why}
                            >
                              {PACE_MISSING.no_terms.label}
                            </span>
                          )}
                        </td>
                        <td>
                          {pace.warning ? (
                            <span className="liabilities-report__warning">
                              <AlertTriangle size={12} aria-hidden /> {pace.text}
                            </span>
                          ) : pace.why ? (
                            <span className="liabilities-report__why" title={pace.why}>
                              {pace.text}
                            </span>
                          ) : (
                            pace.text
                          )}
                        </td>
                        <td className="num">
                          {item.baseline_never_pays_off ? (
                            NEVER_AT_THIS_PAYMENT
                          ) : item.total_interest_remaining === null ? (
                            <span
                              className="liabilities-report__why"
                              title={PACE_MISSING.no_terms.why}
                            >
                              {PACE_MISSING.no_terms.label}
                            </span>
                          ) : (
                            formatMoneyOrDash(item.total_interest_remaining)
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p className="report-note">
              <strong>{AT_MINIMUM}</strong>: {AT_MINIMUM_MEANS}. <strong>{AT_YOUR_PACE}</strong>:{' '}
              {AT_YOUR_PACE_MEANS}.
            </p>
          </>
        )}
      </div>
    </div>
  )
}
