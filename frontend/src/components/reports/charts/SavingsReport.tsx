import { useMemo, useRef } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useSavingsReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { ReportRangeSelect } from './rangeSelect'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { chartColor } from './chartColors'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ChartTooltip } from './ChartTooltip'
import { OnTheWaySection, SavedSection, SinkingFundsSection } from './SavingsSections'
import { GuideTabLink } from '../../guide/GuideTabLink'
import './SavingsReport.css'
import { useReportMonths } from '../../../stores/reportStore'
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'

interface Props {
  budgetId: string
}

export function SavingsReport({ budgetId }: Props) {
  const { formatMoney, formatDate, formatMonth, formatMonthShort } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const months = useReportMonths()
  const { data, isLoading, isError, error, refetch } = useSavingsReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  // One served series: Saved at each month's end. The envelopes count at
  // their floored Available there, which is the server's rule, so the chart
  // draws the total rather than stacking rows that would not add up to it.
  const chartData = useMemo(
    () =>
      (data?.months ?? []).map((m, i) => ({
        month: formatMonthShort(m),
        Saved: data?.saved.monthly_totals[i] ?? 0,
      })),
    [data, formatMonthShort]
  )

  if (isLoading) {
    return <div className="report-loading">Loading...</div>
  }
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Savings</h2>
        <ReportInfoButton title="Savings">
          <p>The report has three parts, each with its own total. They are never added together.</p>
          <p>
            <strong>Saved</strong> is Savings and Emergency fund envelopes set to{' '}
            <strong>kept here</strong>, plus off-budget accounts marked{' '}
            <strong>Counts as savings</strong>. Moving money from such an envelope to such an
            account leaves Saved unchanged.
          </p>
          <p>
            <strong>On the way to savings</strong> is what Savings envelopes set to{' '}
            <strong>sent out</strong> still hold. That money counts as saved when it leaves the
            envelope, so it is shown here and not added to Saved.
          </p>
          <p>
            <strong>Sinking funds</strong> are envelopes tagged <strong>Long-term expense</strong>:
            money spoken for by a planned bill. They are never savings.
          </p>
          <p>
            On-budget accounts are never added: their money is already in your envelopes, which say
            what each dollar is for.
          </p>
          <p>
            Envelope balances are the Available the Budget page shows; an overspent envelope counts
            as nothing toward its section. On a budget imported from YNAB, months before the import
            are worked back from YNAB&apos;s own balance.
          </p>
          <p>
            <strong>What pulled from savings</strong> lists money moved <em>out</em> of Savings and
            Emergency fund envelopes in the window — to another category or back to Ready to Assign
            — as the audit trail records it.
          </p>
          <p>
            <GuideTabLink tab="aside" anchor="savings-report">
              How the three parts count
            </GuideTabLink>
          </p>
          <ReportScopeNote report="savings" />
        </ReportInfoButton>
        <div className="flex-row">
          <ReportRangeSelect />
        </div>
        <div style={{ marginLeft: 'auto' }}>
          <ReportExportButton
            reportId="savings"
            getRows={() =>
              data
                ? [
                    ...data.saved.envelopes.map((e) => ({
                      section: 'Saved',
                      name: e.category_name,
                      group: e.group_name,
                      balance: e.current_balance,
                    })),
                    ...data.saved.accounts.map((a) => ({
                      section: 'Saved',
                      name: a.name,
                      group: '',
                      balance: a.current_balance,
                    })),
                    ...data.on_the_way.envelopes.map((e) => ({
                      section: 'On the way to savings',
                      name: e.category_name,
                      group: e.group_name,
                      balance: e.current_balance,
                    })),
                    ...data.sinking_funds.envelopes.map((e) => ({
                      section: 'Sinking funds',
                      name: e.category_name,
                      group: e.group_name,
                      balance: e.current_balance,
                    })),
                  ]
                : []
            }
            captureRef={captureRef}
          />
        </div>
      </div>

      {data && (
        <div ref={captureRef} className="report-capture">
          <MetricRow>
            <MetricCard label="Saved" value={formatMoney(data.saved.total)} />
            <MetricCard
              label="On the way to savings"
              value={formatMoney(data.on_the_way.total)}
              sub="not in Saved"
            />
            <MetricCard
              label="Sinking funds"
              value={formatMoney(data.sinking_funds.total)}
              sub="spoken for"
            />
          </MetricRow>

          {data.saved.total !== 0 && (
            <div className="report-chart" style={{ height: 240 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                  <XAxis
                    dataKey="month"
                    tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                    axisLine={{ stroke: 'var(--border-color)' }}
                    tickLine={false}
                  />
                  <YAxis
                    {...moneyAxis}
                    tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    content={({ active, payload, label }) => (
                      <ChartTooltip
                        active={active}
                        payload={payload?.map((p) => ({
                          name: String(p.name ?? ''),
                          value: Number(p.value),
                          color: p.color,
                          fill: p.fill,
                        }))}
                        label={String(label ?? '')}
                        formatter={formatMoney}
                      />
                    )}
                  />
                  <Area
                    type="monotone"
                    dataKey="Saved"
                    fill={chartColor(0)}
                    stroke={chartColor(0)}
                    fillOpacity={0.4}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}

          {data.unrecovered.length > 0 && (
            <p className="reports-note" role="note">
              {data.unrecovered
                .map((u) => `${u.category_name} starts in ${formatMonth(u.starts_from)}`)
                .join('; ')}
              . Before then, the imported history doesn&apos;t reproduce YNAB&apos;s balance, so
              there is no figure to draw.
            </p>
          )}

          <SavedSection saved={data.saved} />
          <OnTheWaySection section={data.on_the_way} />
          <SinkingFundsSection section={data.sinking_funds} />

          {data.drains.moves.length > 0 && (
            <section className="report-drains">
              <h3 className="report-drains__title">What pulled from savings</h3>
              <p className="report-drains__total">
                {formatMoney(data.drains.total)} moved out of Savings and Emergency fund envelopes
                in this window.
              </p>
              <ul className="report-drains__list">
                {data.drains.moves.map((m) => (
                  <li key={m.move_id} className="report-drains__row">
                    <span className="report-drains__date">{formatDate(m.date.slice(0, 10))}</span>
                    <span className="report-drains__amount tabular">{formatMoney(m.amount)}</span>
                    <span>
                      {m.from_name} → {m.to_name}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </div>
  )
}
