import { useRef } from 'react'
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
import { useAccountCompositionReport } from '../../../api/reports'
import { useAccountTypes } from '../../../api/accountTypes'
import { accountTypeLabel } from '../../../constants/accountTypes'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import { ReportErrorState } from '../ReportErrorState'
import { ChartTooltip } from './ChartTooltip'
import { CHART_COLORS, COLOR_NET, chartColor } from './chartColors'
import { MIXED_SIGN_STACK } from './mixedSignStack'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportRangeSelect } from './rangeSelect'
import { useReportMonths } from '../../../stores/reportStore'
import { arrivalMarks } from '../../../utils/trackingStart'
import { arrivalLines } from './arrivalLines'
import { TrackingStartNote } from './TrackingStartNote'
import { bandLabel, compositionBands, plotted } from './compositionView'
import { ReportHeader } from '../ReportHeader'

interface Props {
  budgetId: string
}

export function AccountCompositionReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(340)
  const { formatMoney, formatMonthShort } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const months = useReportMonths()
  const { data, isLoading, isError, error, refetch } = useAccountCompositionReport(budgetId, months)
  const { data: typeRows } = useAccountTypes(budgetId)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const points = data?.points ?? []
  const bands = data ? compositionBands(data, CHART_COLORS.length) : []
  const labelFor = (key: string) => bandLabel(key, (k) => accountTypeLabel(k, typeRows))
  const marks = arrivalMarks(points, formatMoney)
  const chartData = points.map((p, i) => ({
    date: formatMonthShort(p.date),
    Net: Number(p.net_worth),
    ...Object.fromEntries(bands.map((b) => [labelFor(b.key), plotted(b, i)])),
  }))

  return (
    <div className="report-section surface">
      <ReportHeader>
        <h2 className="report-section__title">Account Composition</h2>
        <ReportInfoButton title="Account Composition">
          <p>
            Shows how your net worth is made up across <strong>account types</strong> — checking,
            savings, investments, loans, and any custom types — over time, across all accounts. Two
            more bands hold what no account does: <strong>stated values</strong> (a home, a vehicle)
            and <strong>debts tracked by hand</strong>.
          </p>
          <p>
            Balances keep their sign: assets stack above zero, debts below. The <strong>Net</strong>{' '}
            line is the sum of every band — the same figure the Net Worth report draws. A type keeps
            its colour on every range.
          </p>
          <p>
            A numbered line marks a month something began being counted — an account linked with its
            balance, a value or debt first entered — listed under the chart.
          </p>
          <ReportScopeNote report="account-composition" />
        </ReportInfoButton>
        <div className="flex-row ms-auto">
          <ReportRangeSelect />
          <ReportExportButton
            reportId="account-composition"
            getRows={() =>
              points.map((p, i) => ({
                date: p.date,
                net_worth: Number(p.net_worth),
                ...Object.fromEntries(bands.map((b) => [b.key, b.values[i]])),
                started_tracking: p.entered,
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </ReportHeader>
      <p className="report-section__subtitle">Assets stack above zero, debts below.</p>

      <div ref={captureRef} className="report-capture">
        {chartData.length === 0 ? (
          <div className="reports-empty">No account data available.</div>
        ) : (
          <ResponsiveContainer width="100%" height={chartHeight}>
            {/* Debt balances are negative: without the sign offset the debt
                band walked the stack back down and rendered inside the asset
                band. By sign rather than by classification, because an
                overdrawn checking account genuinely belongs below the line. */}
            <ComposedChart
              data={chartData}
              {...MIXED_SIGN_STACK}
              margin={{ top: 16, right: 16, left: 0, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
              <YAxis
                tickFormatter={moneyAxis.tickFormatter}
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                width={moneyAxis.width}
              />
              {/* showTotal would sum the stack AND the net line — the Net row
                  already is the total, served rather than re-derived. */}
              <Tooltip
                content={<ChartTooltip showTotal={false} formatter={formatMoney} />}
                offset={16}
                isAnimationActive={false}
              />
              <Legend />
              <ReferenceLine y={0} stroke="var(--border-color)" strokeWidth={2} />
              {arrivalLines(marks, (i) => chartData[i].date)}
              {bands.map((b) => (
                // Filled, not stroked: a band crossing the axis stacks its
                // zero on the positive side, and a stroke traced that as a
                // line through the other bands (`plotted` says more).
                <Area
                  key={b.key}
                  type="linear"
                  dataKey={labelFor(b.key)}
                  stroke="none"
                  fill={chartColor(b.colorSlot)}
                  fillOpacity={0.45}
                  stackId="1"
                />
              ))}
              <Line type="linear" dataKey="Net" stroke={COLOR_NET} strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        )}
        <TrackingStartNote
          marks={marks}
          formatMoney={formatMoney}
          formatMonthShort={formatMonthShort}
        />
      </div>
    </div>
  )
}
