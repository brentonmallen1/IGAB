import { useMemo, useState } from 'react'
import { Plus, X } from 'lucide-react'
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useAppStore } from '../../../stores/appStore'
import { useLiabilities } from '../../../api/liabilities'
import {
  usePayoffPlan,
  type CascadeOut,
  type PayoffPlanRequest,
  type PayoffPlanResponse,
} from '../../../api/guide'
import { useFormatters } from '../../../hooks/useFormatters'
import { useDebouncedValue } from '../../../hooks/useDebouncedValue'
import { CHART_COLORS, TOOLTIP_STYLE } from '../../reports/charts/chartColors'
import { blankRow, rowsToRequest, seedRows, type PlannerRow, type RowField } from './payoffRows'

/**
 * Avalanche against snowball over the household's real debts.
 *
 * Rows come from the liabilities that have a rate and a minimum on record;
 * the rest are named as left out. Every figure is editable and none of it
 * is written back — these are scenario inputs. Both strategies are measured
 * against "minimums only, nothing rolled", and both the money and the
 * psychological payoff are reported: the source chart says to weigh both.
 */
export function PayoffPlanner() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: liabilities } = useLiabilities(budgetId)
  // Rows are the seed until the first edit, so liabilities arriving late
  // still fill the table and no effect has to copy state into state.
  const seed = useMemo(() => seedRows(liabilities ?? []), [liabilities])
  const [empty] = useState(() => [blankRow()])
  const [edited, setEdited] = useState<PlannerRow[] | null>(null)
  const [extra, setExtra] = useState('')
  const { formatMoney, formatDate } = useFormatters()

  const current = edited ?? (seed.rows.length ? seed.rows : empty)
  const excluded = seed.excluded
  const validation = useMemo(() => rowsToRequest(current, extra), [current, extra])
  // Debounce on the serialised body so identity churn does not refetch.
  const settledKey = useDebouncedValue(JSON.stringify(validation.body))
  const settledBody = useMemo(
    () => (settledKey === 'null' ? null : (JSON.parse(settledKey) as PayoffPlanRequest)),
    [settledKey]
  )
  const { data, isFetching } = usePayoffPlan(budgetId, settledBody)

  function update(key: string, field: RowField, value: string) {
    setEdited(current.map((row) => (row.key === key ? { ...row, [field]: value } : row)))
  }
  function remove(key: string) {
    setEdited(current.filter((row) => row.key !== key))
  }
  function add() {
    setEdited([...current, blankRow()])
  }

  return (
    <div className="tool">
      <div className="tool__inputs">
        <table className="tool__table">
          <thead>
            <tr>
              <th>Debt</th>
              <th>Balance</th>
              <th>APR %</th>
              <th>Minimum / mo</th>
              <th aria-label="Remove" />
            </tr>
          </thead>
          <tbody>
            {current.map((row) => {
              const bad = validation.errors[row.key] ?? []
              return (
                <tr key={row.key}>
                  <td>
                    <input
                      aria-label="Debt name"
                      value={row.name}
                      onChange={(e) => update(row.key, 'name', e.target.value)}
                      className={bad.includes('name') ? 'is-invalid' : ''}
                      placeholder="Card, loan…"
                    />
                  </td>
                  <td>
                    <input
                      aria-label="Balance"
                      inputMode="decimal"
                      value={row.balance}
                      onChange={(e) => update(row.key, 'balance', e.target.value)}
                      className={bad.includes('balance') ? 'is-invalid' : ''}
                    />
                  </td>
                  <td>
                    <input
                      aria-label="APR"
                      inputMode="decimal"
                      value={row.rate}
                      onChange={(e) => update(row.key, 'rate', e.target.value)}
                      className={bad.includes('rate') ? 'is-invalid' : ''}
                    />
                  </td>
                  <td>
                    <input
                      aria-label="Minimum payment"
                      inputMode="decimal"
                      value={row.minimum}
                      onChange={(e) => update(row.key, 'minimum', e.target.value)}
                      className={bad.includes('minimum') ? 'is-invalid' : ''}
                    />
                  </td>
                  <td>
                    <button
                      type="button"
                      className="tool__icon-button"
                      onClick={() => remove(row.key)}
                      aria-label={`Remove ${row.name || 'this debt'}`}
                    >
                      <X size={13} />
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <div className="tool__row-actions">
          <button type="button" className="guide-link-button tool__add" onClick={add}>
            <Plus size={12} aria-hidden /> Add a debt
          </button>
          {excluded.length > 0 && (
            <p className="tool__nudge">
              Left out — no rate or minimum on record for {excluded.join(', ')}. Add the terms on
              the liability and it will be here.
            </p>
          )}
        </div>
        <label className="tool__field tool__field--inline">
          <span>Extra per month</span>
          <input
            inputMode="decimal"
            value={extra}
            onChange={(e) => setExtra(e.target.value)}
            className={validation.extraError ? 'is-invalid' : ''}
            placeholder="0"
          />
        </label>
        {(Object.keys(validation.errors).length > 0 || validation.extraError) && (
          <p className="tool__error">Some figures did not parse — nothing is assumed to be zero.</p>
        )}
      </div>

      {data && (
        <div className={`tool__results ${isFetching ? 'tool__results--stale' : ''}`}>
          <Comparison plan={data} formatMoney={formatMoney} />
          <div className="tool__cards">
            <StrategyCard
              title="Avalanche"
              hint="Highest rate first — the least interest."
              result={data.avalanche}
              baseline={data.minimums_only}
              formatMoney={formatMoney}
              formatDate={formatDate}
            />
            <StrategyCard
              title="Snowball"
              hint="Smallest balance first — the earliest win."
              result={data.snowball}
              baseline={data.minimums_only}
              formatMoney={formatMoney}
              formatDate={formatDate}
            />
          </div>
          <BalanceChart plan={data} formatMoney={formatMoney} />
        </div>
      )}
    </div>
  )
}

function Comparison({
  plan,
  formatMoney,
}: {
  plan: PayoffPlanResponse
  formatMoney: (n: number) => string
}) {
  const { avalanche, snowball } = plan
  if (avalanche.never_pays_off || snowball.never_pays_off) {
    return (
      <p className="tool__summary">
        At these payments not every debt clears — the minimums do not cover the interest somewhere.
        Add something extra and the picture changes.
      </p>
    )
  }
  const saves = Number(snowball.total_interest) - Number(avalanche.total_interest)
  const firstAv = Math.min(...avalanche.debts.map((d) => d.months))
  const firstSn = Math.min(...snowball.debts.map((d) => d.months))
  const sooner = firstAv - firstSn
  return (
    <p className="tool__summary">
      {saves > 0.005 ? (
        <>
          Avalanche saves <strong>{formatMoney(saves)}</strong> in interest over snowball.{' '}
        </>
      ) : (
        <>The two strategies cost the same in interest here. </>
      )}
      {sooner > 0 ? (
        <>
          Snowball clears its first debt{' '}
          <strong>
            {sooner} {sooner === 1 ? 'month' : 'months'}
          </strong>{' '}
          sooner — pick the one you will actually stick to.
        </>
      ) : (
        <>Both clear a first debt at the same time.</>
      )}
    </p>
  )
}

function StrategyCard({
  title,
  hint,
  result,
  baseline,
  formatMoney,
  formatDate,
}: {
  title: string
  hint: string
  result: CascadeOut
  baseline: CascadeOut
  formatMoney: (n: number) => string
  formatDate: (s: string) => string
}) {
  const saved = Number(baseline.total_interest) - Number(result.total_interest)
  const sooner = baseline.months.length - result.months.length
  return (
    <div className="tool__card">
      <h3 className="tool__card-title">{title}</h3>
      <p className="tool__card-hint">{hint}</p>
      <dl className="tool__facts">
        <dt>Debt-free</dt>
        <dd>{result.debt_free_date ? formatDate(result.debt_free_date) : 'never at this pace'}</dd>
        <dt>Total interest</dt>
        <dd className="tabular">{formatMoney(Number(result.total_interest))}</dd>
        {!baseline.never_pays_off && !result.never_pays_off && (
          <>
            <dt>vs minimums only</dt>
            <dd>
              {formatMoney(saved)} less interest
              {sooner > 0 && `, ${sooner} ${sooner === 1 ? 'month' : 'months'} sooner`}
            </dd>
          </>
        )}
      </dl>
      <ol className="tool__order">
        {result.debts.map((d) => (
          <li key={d.key}>
            <span>{d.name}</span>
            <span className="tool__order-when">
              {d.payoff_date ? formatDate(d.payoff_date) : 'not cleared'}
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}

function BalanceChart({
  plan,
  formatMoney,
}: {
  plan: PayoffPlanResponse
  formatMoney: (n: number) => string
}) {
  const series: {
    key: keyof PayoffPlanResponse & ('avalanche' | 'snowball' | 'minimums_only')
    label: string
  }[] = [
    { key: 'avalanche', label: 'Avalanche' },
    { key: 'snowball', label: 'Snowball' },
    { key: 'minimums_only', label: 'Minimums only' },
  ]
  const length = Math.max(...series.map((s) => plan[s.key].months.length))
  if (length === 0) return null
  const points = Array.from({ length }, (_, i) => {
    const point: Record<string, string | number | undefined> = {
      month:
        plan.avalanche.months[i]?.date ??
        plan.snowball.months[i]?.date ??
        plan.minimums_only.months[i]?.date,
    }
    for (const s of series) {
      const m = plan[s.key].months[i]
      point[s.label] = m ? Number(m.balance) : plan[s.key].never_pays_off ? undefined : 0
    }
    return point
  })
  return (
    <div className="tool__chart" aria-label="Remaining balance by strategy">
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <XAxis
            dataKey="month"
            tickFormatter={(d: string) => d.slice(0, 7)}
            tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
            minTickGap={24}
          />
          <YAxis
            tickFormatter={(v: number) => formatMoney(v)}
            tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
            width={72}
          />
          <Tooltip
            {...TOOLTIP_STYLE}
            formatter={(v) => formatMoney(Number(v))}
            labelFormatter={(d) => String(d).slice(0, 7)}
          />
          {series.map((s, i) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.label}
              stroke={CHART_COLORS[i]}
              dot={false}
              strokeWidth={s.key === 'minimums_only' ? 1 : 2}
              strokeDasharray={s.key === 'minimums_only' ? '4 3' : undefined}
              connectNulls={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
