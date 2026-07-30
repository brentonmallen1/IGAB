import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
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
import { ReportErrorState } from '../ReportErrorState'
import { ChartTooltip } from './ChartTooltip'
import { chartColor } from './chartColors'
import { MetricCard } from '../MetricCard'
import { ReportInfoButton } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import './LiabilitiesReport.css'

interface Props {
  budgetId: string
}

const TYPE_LABELS: Record<string, string> = {
  mortgage: 'Mortgage',
  auto: 'Auto',
  student: 'Student',
  personal: 'Personal',
  credit_card: 'Credit card',
  medical: 'Medical',
  other: 'Other',
}

type SortKey = 'balance' | 'rate' | 'baseline' | 'live' | 'interest'

export function LiabilitiesReport({ budgetId }: Props) {
  const navigate = useNavigate()
  const { formatMoney, formatMonth } = useFormatters()
  const [typeFilter, setTypeFilter] = useState<string | null>(null)
  const [modeFilter, setModeFilter] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('balance')
  const [sortDesc, setSortDesc] = useState(true)
  const captureRef = useRef<HTMLDivElement>(null)

  const { data, isLoading, isError, refetch } = useLiabilitiesReport(
    budgetId,
    typeFilter ?? undefined,
    modeFilter ?? undefined
  )
  // Unfiltered call drives the filter pills so options don't vanish
  const { data: allData } = useLiabilitiesReport(budgetId)

  const items = useMemo(() => {
    const rows = [...(data?.items ?? [])]
    const value = (row: (typeof rows)[number]) => {
      switch (sortKey) {
        case 'balance':
          return Number(row.current_balance)
        case 'rate':
          return Number(row.interest_rate)
        case 'baseline':
          return row.baseline_payoff_date ?? '9999'
        case 'live':
          return row.live_payoff_date ?? '9999'
        case 'interest':
          return Number(row.total_interest_remaining)
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
  if (isError) return <ReportErrorState onRetry={() => refetch()} />

  const presentTypes = [...new Set((allData?.items ?? []).map((i) => i.liability_type))]
  const chartPoints = (data?.balance_over_time ?? []).map((p) => {
    const point: Record<string, number | string> = { date: p.date.slice(0, 7) }
    for (const item of data?.items ?? []) {
      point[item.name] = Number(p.per_liability[item.liability_id] ?? 0)
    }
    return point
  })

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDesc((d) => !d)
    else {
      setSortKey(key)
      setSortDesc(true)
    }
  }

  return (
    <div className="report-section">
      <div className="report-section__header">
        <h2 className="report-section__title">Liabilities</h2>
        <ReportInfoButton title="Liabilities">
          <p>
            A consolidated rollup of every tracked liability —{' '}
            <strong>how's all my debt doing</strong> in one place.
          </p>
          <p>
            Click a row for the full deep-dive: amortization schedule, paydown chart, payoff pill,
            and what-if extra payments.
          </p>
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
                {TYPE_LABELS[t] ?? t}
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
          <ReportExportButton
            reportId="liabilities"
            getRows={() =>
              (data?.items ?? []).map((i) => ({
                name: i.name,
                type: i.liability_type,
                mode: i.mode,
                balance: Number(i.current_balance),
                interest_rate: Number(i.interest_rate),
                baseline_payoff: i.baseline_payoff_date ?? '',
                live_payoff: i.live_payoff_date ?? '',
                interest_remaining: Number(i.total_interest_remaining),
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>

      <div ref={captureRef} className="report-capture">
        {(data?.items.length ?? 0) === 0 ? (
          <div className="reports-empty">
            No liabilities tracked yet — add one from the Liabilities section in the sidebar.
          </div>
        ) : (
          <>
            <div className="report-metrics">
              <MetricCard
                label="Total Liabilities"
                value={formatMoney(Number(data!.total_balance))}
                accent
              />
              <MetricCard
                label="Interest Remaining"
                value={formatMoney(Number(data!.total_interest_remaining))}
                sub="At minimum payments"
              />
              <MetricCard label="Liabilities" value={String(data!.items.length)} />
            </div>

            {chartPoints.length > 1 && (
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={chartPoints} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} minTickGap={40} />
                  <YAxis tickFormatter={(v) => formatMoney(v)} tick={{ fontSize: 11, fill: 'var(--text-muted)' }} width={85} />
                  <Tooltip
                    content={<ChartTooltip showTotal />}
                    offset={16}
                    isAnimationActive={false}
                  />
                  <Legend />
                  {data!.items.map((item, idx) => (
                    <Area
                      key={item.liability_id}
                      type="monotone"
                      dataKey={item.name}
                      stackId="liability"
                      stroke={chartColor(idx)}
                      fill={chartColor(idx)}
                      fillOpacity={0.35}
                    />
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            )}

            <div className="liabilities-report__table-wrap">
              <table className="liabilities-report__table">
                <thead>
                  <tr>
                    <th>Liability</th>
                    <th className="num sortable" onClick={() => toggleSort('balance')}>
                      Balance{sortKey === 'balance' ? (sortDesc ? ' ↓' : ' ↑') : ''}
                    </th>
                    <th className="num sortable" onClick={() => toggleSort('rate')}>
                      Rate{sortKey === 'rate' ? (sortDesc ? ' ↓' : ' ↑') : ''}
                    </th>
                    <th className="sortable" onClick={() => toggleSort('baseline')}>
                      Contractual{sortKey === 'baseline' ? (sortDesc ? ' ↓' : ' ↑') : ''}
                    </th>
                    <th className="sortable" onClick={() => toggleSort('live')}>
                      Live payoff{sortKey === 'live' ? (sortDesc ? ' ↓' : ' ↑') : ''}
                    </th>
                    <th className="num sortable" onClick={() => toggleSort('interest')}>
                      Interest left{sortKey === 'interest' ? (sortDesc ? ' ↓' : ' ↑') : ''}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr
                      key={item.liability_id}
                      onClick={() => navigate(`/liabilities/${item.liability_id}`)}
                      title="Open liability details"
                    >
                      <td>
                        <span className="liabilities-report__name">{item.name}</span>
                        <span className="liabilities-report__type">
                          {TYPE_LABELS[item.liability_type] ?? item.liability_type} ·{' '}
                          {item.mode === 'managed' ? 'from account' : 'manual'}
                        </span>
                      </td>
                      <td className="num">{formatMoney(Number(item.current_balance))}</td>
                      <td className="num">{Number(item.interest_rate)}%</td>
                      <td>
                        {item.baseline_payoff_date
                          ? formatMonth(item.baseline_payoff_date)
                          : '—'}
                      </td>
                      <td>
                        {item.never_pays_off ? (
                          <span className="liabilities-report__warning">
                            <AlertTriangle size={12} /> Won't pay off
                          </span>
                        ) : item.live_payoff_date ? (
                          formatMonth(item.live_payoff_date)
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="num">{formatMoney(Number(item.total_interest_remaining))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
