import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { AmortizationResponse, AmortizationMonth } from '../../api/liabilities'
import { useFormatters } from '../../hooks/useFormatters'
import { ChartTooltip } from '../reports/charts/ChartTooltip'
import { COLOR_NEGATIVE, COLOR_POSITIVE, CHART_COLORS } from '../reports/charts/chartColors'

interface Props {
  amortization: AmortizationResponse
  mode: 'now' | 'beginning'
  isMobile?: boolean
}

interface ChartPoint {
  month: string
  Balance?: number
  Projected?: number
  'With extra'?: number
  'Principal paid'?: number
  'Interest paid'?: number
}

/**
 * Balance line over stacked cumulative principal/interest areas — the
 * shrinking interest share is the story. "Beginning" prepends the actual
 * historical balance (solid) before the projected curve (dashed), joined
 * at a "Today" reference line so fact and forecast are never ambiguous.
 */
export function PaydownChart({ amortization, mode, isMobile = false }: Props) {
  const { formatMoney } = useFormatters()
  const points: ChartPoint[] = []
  const todayMonth = new Date().toISOString().slice(0, 7)

  if (mode === 'beginning') {
    for (const p of amortization.history) {
      points.push({ month: p.date.slice(0, 7), Balance: Number(p.balance) })
    }
  }

  // Join the solid and dashed curves at today
  points.push({
    month: todayMonth,
    ...(mode === 'beginning' ? { Balance: Number(amortization.current_balance) } : {}),
    Projected: Number(amortization.current_balance),
    'Principal paid': 0,
    'Interest paid': 0,
  })

  let cumPrincipal = 0
  let cumInterest = 0
  const extraByMonth = new Map(
    (amortization.extra_schedule ?? []).map((m: AmortizationMonth) => [
      m.date.slice(0, 7),
      Number(m.balance),
    ])
  )
  for (const m of amortization.baseline_schedule) {
    cumPrincipal += Number(m.principal_paid)
    cumInterest += Number(m.interest_paid)
    const month = m.date.slice(0, 7)
    points.push({
      month,
      Projected: Number(m.balance),
      'Principal paid': cumPrincipal,
      'Interest paid': cumInterest,
      ...(extraByMonth.has(month) ? { 'With extra': extraByMonth.get(month) } : {}),
    })
  }
  // The accelerated curve may extend past... no — it always ends sooner; but
  // if the baseline never pays off while the extra one does, include its tail.
  for (const m of amortization.extra_schedule ?? []) {
    const month = m.date.slice(0, 7)
    if (!points.some((p) => p.month === month)) {
      points.push({ month, 'With extra': Number(m.balance) })
    }
  }

  const liveMonth = amortization.live_payoff_date?.slice(0, 7)
  const showLiveLine = liveMonth !== undefined && points.some((p) => p.month === liveMonth)

  return (
    <ResponsiveContainer width="100%" height={isMobile ? 240 : 320}>
      <ComposedChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
        <XAxis dataKey="month" tick={{ fontSize: 11 }} minTickGap={40} />
        <YAxis tickFormatter={(v) => formatMoney(v)} tick={{ fontSize: 11 }} width={85} />
        <Tooltip content={<ChartTooltip showTotal={false} />} offset={16} isAnimationActive={false} />
        <Legend />
        <Area
          type="monotone"
          dataKey="Principal paid"
          stackId="paid"
          stroke="none"
          fill={CHART_COLORS[0]}
          fillOpacity={0.18}
        />
        <Area
          type="monotone"
          dataKey="Interest paid"
          stackId="paid"
          stroke="none"
          fill={COLOR_NEGATIVE}
          fillOpacity={0.22}
        />
        {mode === 'beginning' && (
          <Line
            type="monotone"
            dataKey="Balance"
            stroke={CHART_COLORS[0]}
            strokeWidth={2}
            dot={false}
          />
        )}
        <Line
          type="monotone"
          dataKey="Projected"
          stroke={CHART_COLORS[0]}
          strokeWidth={2}
          strokeDasharray="5 4"
          dot={false}
        />
        {amortization.extra_schedule && (
          <Line
            type="monotone"
            dataKey="With extra"
            stroke={COLOR_POSITIVE}
            strokeWidth={2}
            strokeDasharray="5 4"
            dot={false}
          />
        )}
        {mode === 'beginning' && (
          <ReferenceLine
            x={todayMonth}
            stroke="var(--text-muted)"
            strokeDasharray="3 3"
            label={{ value: 'Today', fontSize: 11, fill: 'var(--text-muted)', position: 'top' }}
          />
        )}
        {showLiveLine && (
          <ReferenceLine
            x={liveMonth}
            stroke={COLOR_POSITIVE}
            strokeDasharray="3 3"
            label={{
              value: 'Live payoff',
              fontSize: 11,
              fill: COLOR_POSITIVE,
              position: 'top',
            }}
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  )
}
