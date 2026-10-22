import { useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, Info } from 'lucide-react'
import { useIncomeSplitReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { sectionHref } from '../../../pages/SettingsPage/settingsSections'
import { useReportStore } from '../../../stores/reportStore'
import { today } from '../../../utils/dates'
import {
  BUCKET_LABEL,
  RULE,
  barGeometry,
  gapPhrase,
  lineDetail,
  perMonthDivisor,
  reasonChip,
  ruleFor,
  shares,
  sum,
  tooUnfiled,
  type BucketKey,
} from '../../../utils/incomeSplit'
import type { IncomeSplitLine, IncomeSplitReport as Report } from '../../../types'
import { systemTagName } from '../../settings/TagsPanel/systemTagHelp'
import { ReportErrorState } from '../ReportErrorState'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportHeader } from '../ReportHeader'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { periodHeading } from '../overviewMetrics'
import './IncomeSplitReport.css'

interface Props {
  budgetId: string
}

const TAGS_HREF = sectionHref({ id: 'tags', page: 'settings' })
/** The register, narrowed to what still needs a category. */
const UNFILED_HREF = `/transactions?q=${encodeURIComponent('is: uncategorized')}`

const GROUPS: BucketKey[] = ['needs', 'wants', 'savings', 'uncategorized', 'left']

/**
 * Where take-home pay went over the range, beside the 50/30/20 rule of thumb:
 * one bar with the rule's 50 and 80 as ticks, a legend, and a breakdown that
 * names every category and why it is where it is.
 *
 * Replaces Cost of Living and Discretionary: Cost of Living is Needs plus the
 * committed part of Wants, Discretionary the chosen part. The server sorts the
 * rows (`domain.activity_class` — ESSENTIAL_ROW, COMMITTED_ROW,
 * DISCRETIONARY_ROW, NON_ESSENTIAL_DEBT_OUTFLOW) and serves money; the rule
 * and the shares are `utils/incomeSplit`.
 */
export function IncomeSplitReport({ budgetId }: Props) {
  const { formatMoney, formatMonthShort, formatDayMonth } = useFormatters()
  const { filters } = useReportStore()
  const { data, isLoading, isError, error, refetch } = useIncomeSplitReport(
    budgetId,
    filters.startDate,
    filters.endDate
  )
  const captureRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState<Set<BucketKey>>(new Set())

  if (isLoading) return <div className="report-loading">Loading...</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />
  if (!data) return null

  const essential = systemTagName('essential')
  const costOfLiving = systemTagName('cost_of_living')
  const period = periodHeading(
    data.start_date,
    data.end_date,
    today(),
    formatMonthShort,
    formatDayMonth
  )
  const divisor = perMonthDivisor(data)
  const per = (n: number) => formatMoney(n / divisor)
  const perLabel = divisor > 1 ? 'per month' : 'in this range'

  const allOpen = open.size === GROUPS.length
  const toggle = (key: BucketKey) =>
    setOpen((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  return (
    <div className="report-section surface">
      <ReportHeader>
        <h2 className="report-section__title">Income Split</h2>
        <ReportInfoButton title="Income Split">
          <p>
            Where take-home pay went, beside the <strong>50/30/20 rule</strong>: about half to
            needs, up to a third to wants, and a fifth to saving and paying down debt. It is a
            yardstick, not a target — where you live decides a lot of the needs figure.
          </p>
          <p>
            <strong>Needs</strong> are categories tagged <strong>{essential}</strong>, debt payments
            in them included. <strong>Wants</strong> are all other spending: committed (tagged{' '}
            <strong>{costOfLiving}</strong>) and chosen (tagged neither).{' '}
            <strong>Savings &amp; debt</strong> is what the Savings Rate counts as saved, plus debt
            payments outside {essential}.
          </p>
          <p>Replaces the Cost of Living and Discretionary reports.</p>
          <ReportScopeNote report="income-split" />
        </ReportInfoButton>
        <div className="ms-auto">
          <ReportExportButton
            reportId="income-split"
            getRows={() => exportRows(data)}
            captureRef={captureRef}
            window={{ start: data.start_date, end: data.end_date }}
          />
        </div>
      </ReportHeader>

      <p className="income-split__lede">
        Where take-home pay went, measured against the 50/30/20 rule: about half to needs, under a
        third to wants, a fifth to saving and paying down debt. Replaces Cost of Living and
        Discretionary — Cost of Living is Needs plus the committed part of Wants; Discretionary is
        the chosen part.
      </p>

      {!data.tagged ? (
        <div className="income-split__empty">
          <p>
            Needs come from the <strong>{essential}</strong> tag, and nothing carries it yet. Tag
            the categories you couldn’t go without — housing, groceries, insurance, the minimum on
            each debt — and the split appears.
          </p>
          <p>
            <Link to={TAGS_HREF}>Choose {essential} categories in Settings → Tags</Link>
          </p>
        </div>
      ) : (
        <div ref={captureRef} className="report-capture income-split">
          <SplitSummary data={data} period={period} per={per} perLabel={perLabel} />
          <section
            className="income-split__breakdown surface surface--raised"
            aria-label="Breakdown"
          >
            <div className="income-split__breakdown-head">
              <div>
                <h3 className="income-split__h3">Breakdown</h3>
                <p className="income-split__muted">
                  Every category counted, and the tag that put it there. Change a category’s tags to
                  move it.
                </p>
              </div>
              <button
                type="button"
                className="income-split__btn"
                onClick={() => setOpen(allOpen ? new Set() : new Set(GROUPS))}
              >
                {allOpen ? 'Collapse all' : 'Expand all'}
              </button>
            </div>
            {GROUPS.map((key) => (
              <BreakdownGroup
                key={key}
                bucket={key}
                data={data}
                open={open.has(key)}
                onToggle={() => toggle(key)}
                per={per}
                money={formatMoney}
              />
            ))}
          </section>
          <SplitNotes essential={essential} costOfLiving={costOfLiving} spreadOn={data.spread_on} />
        </div>
      )}
    </div>
  )
}

function SplitSummary({
  data,
  period,
  per,
  perLabel,
}: {
  data: Report
  period: string
  per: (n: number) => string
  perLabel: string
}) {
  const bar = barGeometry(data)
  const pct = shares(data)
  const unfiled = tooUnfiled(data)
  const amounts = {
    needs: data.needs.total,
    wants: data.wants.total,
    savings: data.savings_debt.total,
    uncategorized: data.uncategorized.total,
    left: data.left_over,
  }

  return (
    <section className="income-split__summary surface surface--raised" aria-label="The split">
      <div className="income-split__period">
        <span>
          {period} · {perLabel}
          {data.clamped && ' · from the start of your history'}
        </span>
        <span>
          Take-home <strong>{per(data.income)}</strong>
        </span>
      </div>
      {data.running && (
        <p className="income-split__muted">
          This range runs to today: income is in and spending is still arriving, so Left over reads
          high until the month is done.
        </p>
      )}

      {!bar || !pct ? (
        <p className="income-split__muted">
          No income in this range, so there is nothing to take a share of. The breakdown below still
          lists where money went.
        </p>
      ) : (
        <>
          <div className={`income-split__bar-wrap ${unfiled ? 'is-unfiled' : ''}`}>
            <div className="income-split__ticks" aria-hidden="true">
              {bar.ticks.map((t, i) => (
                <span key={t} style={{ left: `${t}%` }}>
                  {i === 0 ? RULE.needs : RULE.needs + RULE.wants}%
                </span>
              ))}
            </div>
            <div
              className="income-split__bar"
              role="img"
              aria-label={`Needs ${pct.needs}%, wants ${pct.wants}%, savings and debt ${pct.savings}%, uncategorized ${pct.uncategorized}%, left over ${pct.left}% of take-home`}
            >
              {bar.segments.map((s) => (
                <span
                  key={s.key}
                  className={`income-split__seg income-split__seg--${s.key}`}
                  style={{ width: `${s.width}%` }}
                >
                  {s.width >= 14 && s.key !== 'committed' && s.key !== 'left' && (
                    <span className="income-split__seg-label">
                      {BUCKET_LABEL[s.key]} {pct[s.key]}%
                    </span>
                  )}
                </span>
              ))}
              {bar.ticks.map((t) => (
                <span
                  key={t}
                  className="income-split__tick"
                  style={{ left: `${t}%` }}
                  aria-hidden="true"
                />
              ))}
              {bar.over > 0 && (
                <span
                  className="income-split__income-line"
                  style={{ left: `${bar.incomeAt}%` }}
                  aria-hidden="true"
                />
              )}
            </div>
            <div className="income-split__rule" aria-hidden="true">
              <span style={{ width: `${(RULE.needs * bar.incomeAt) / 100}%` }} />
              <span style={{ width: `${(RULE.wants * bar.incomeAt) / 100}%` }} />
              <span style={{ width: `${(RULE.savings * bar.incomeAt) / 100}%` }} />
            </div>
          </div>
          {bar.over > 0 && (
            <p className="income-split__over">
              Outflows ran past take-home by <strong>{per(bar.over)}</strong> {perLabel} — drawn
              from balances.
            </p>
          )}
          {unfiled && (
            <p className="income-split__over">
              {pct.uncategorized}% of take-home went out unfiled. The split leans on categories, so
              it can move a lot once these are filed — the gaps are not stated until then.{' '}
              <Link to={UNFILED_HREF}>Review them</Link>
            </p>
          )}
        </>
      )}

      <ul className="income-split__legend">
        {GROUPS.map((key) => {
          const rule = ruleFor(key)
          return (
            <li key={key} className="income-split__legend-cell">
              <span className="income-split__legend-name">
                <span className={`income-split__swatch income-split__swatch--${key}`} />
                {BUCKET_LABEL[key]}
              </span>
              <span className="income-split__legend-amount tabular">{per(amounts[key])}</span>
              {pct && <span className="income-split__muted">{pct[key]}% of take-home</span>}
              <span className="income-split__muted">
                {rule !== null && pct && !unfiled
                  ? `Rule ${rule}% · ${gapPhrase(pct[key], rule)}`
                  : key === 'uncategorized'
                    ? `${data.uncategorized.count} row${data.uncategorized.count === 1 ? '' : 's'} not filed`
                    : key === 'left'
                      ? 'In envelopes or Ready to Assign'
                      : rule !== null
                        ? `Rule ${rule}%`
                        : ''}
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function BreakdownGroup({
  bucket,
  data,
  open,
  onToggle,
  per,
  money,
}: {
  bucket: BucketKey
  data: Report
  open: boolean
  onToggle: () => void
  per: (n: number) => string
  money: (n: number) => string
}) {
  const pct = shares(data)
  const head = groupHead(bucket, data)
  const rule = ruleFor(bucket)
  return (
    <div className={`income-split__group income-split__group--${bucket}`}>
      <button
        type="button"
        className="income-split__group-head"
        aria-expanded={open}
        onClick={onToggle}
      >
        <ChevronRight size={16} className="income-split__chevron" aria-hidden="true" />
        <span className={`income-split__swatch income-split__swatch--${bucket}`} />
        <span className="income-split__group-name">
          <strong>{BUCKET_LABEL[bucket]}</strong>
          <span className="income-split__muted">{head.desc}</span>
        </span>
        <span className="income-split__group-figures">
          <strong className="tabular">{per(head.total)}</strong>
          {pct && <span className="tabular">{pct[bucket]}%</span>}
          {rule !== null && <span className="income-split__muted">Rule {rule}%</span>}
        </span>
      </button>
      {open && (
        <div className="income-split__group-body">
          {head.parts.map((part) => (
            <div key={part.label ?? 'lines'}>
              {part.label && (
                <div className="income-split__subhead">
                  <span
                    className={`income-split__swatch income-split__swatch--${part.tone ?? bucket}`}
                  />
                  <span>{part.label}</span>
                  <span className="tabular">{per(sum(part.lines))}</span>
                </div>
              )}
              {part.lines.map((line) => (
                <Line
                  key={`${line.reason}-${line.category_id}-${line.name}`}
                  line={line}
                  per={per}
                  money={money}
                />
              ))}
            </div>
          ))}
          {head.foot && (
            <p className="income-split__foot">
              <Info size={14} aria-hidden="true" />
              <span>{head.foot}</span>
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function Line({
  line,
  per,
  money,
}: {
  line: IncomeSplitLine
  per: (n: number) => string
  money: (n: number) => string
}) {
  const detail = lineDetail(line, money)
  return (
    <div className="income-split__line">
      <span className="income-split__line-name">
        <span>{line.name}</span>
        {detail && <span className="income-split__muted income-split__line-detail">{detail}</span>}
      </span>
      <span className="income-split__muted income-split__line-group">{line.group_name ?? ''}</span>
      <span className="income-split__chip">{reasonChip(line)}</span>
      <span className="income-split__line-amount tabular">{per(line.total)}</span>
    </div>
  )
}

interface GroupHead {
  total: number
  desc: string
  parts: { label?: string; tone?: string; lines: IncomeSplitLine[] }[]
  foot?: ReactNode
}

function groupHead(bucket: BucketKey, data: Report): GroupHead {
  switch (bucket) {
    case 'needs': {
      const moved = data.needs.total - data.strict.needs
      return {
        total: data.needs.total,
        desc: 'Tagged Essential',
        parts: [{ lines: data.needs.lines }],
        foot:
          moved > 0 ? (
            <>
              Read strictly, the rule counts only a debt’s minimum as a need. Moving what was paid
              above the minimums gives Needs {Math.round((data.strict.needs / data.income) * 100)}%
              · Savings &amp; debt {Math.round((data.strict.savings_debt / data.income) * 100)}%.
            </>
          ) : undefined,
      }
    }
    case 'wants':
      return {
        total: data.wants.total,
        desc: 'Everything else you spent',
        parts: [
          {
            label: 'Committed, not essential — tagged Cost of living',
            tone: 'committed',
            lines: data.wants.committed,
          },
          { label: 'Chosen — tagged neither', tone: 'wants', lines: data.wants.chosen },
        ],
      }
    case 'savings':
      return {
        total: data.savings_debt.total,
        desc: 'Set aside, or paid down beyond needs',
        parts: [
          { label: 'Saved', tone: 'savings', lines: data.savings_debt.saved },
          { label: 'Debt paid outside Essential', tone: 'savings', lines: data.savings_debt.debt },
        ],
      }
    case 'uncategorized':
      return {
        total: data.uncategorized.total,
        desc: 'Spent, not filed — counted nowhere else',
        parts: [],
        foot: (
          <>
            Filing these moves them into Needs or Wants. <Link to={UNFILED_HREF}>Review them</Link>
          </>
        ),
      }
    case 'left':
      return {
        total: data.left_over,
        desc: 'Came in, not yet spent or saved',
        parts: [],
        foot: 'Stayed in ordinary envelopes or Ready to Assign. Money held in a Savings envelope is counted under Savings & debt, not here.',
      }
  }
}

function SplitNotes({
  essential,
  costOfLiving,
  spreadOn,
}: {
  essential: string
  costOfLiving: string
  spreadOn: boolean
}) {
  return (
    <section className="income-split__notes">
      <div>
        <h3 className="income-split__note-head">The 50/30/20 rule</h3>
        <p>
          A rule of thumb for splitting take-home pay: 50% to needs, 30% to wants, 20% to saving and
          paying down debt. It’s a yardstick, not a target to hit exactly — housing alone can put
          needs past 50% where you live. The ticks on the bar mark where 50% and 80% fall.{' '}
          <Link to="/guide?tab=roadmap">More in the Guide</Link>
        </p>
      </div>
      <div>
        <h3 className="income-split__note-head">Counts</h3>
        <p>
          Needs: spending and debt payments in categories tagged {essential}
          {spreadOn ? ', yearly Long-term expense bills spread over 12 months' : ''}. Wants: all
          other spending — {costOfLiving} first, then untagged. Savings &amp; debt: what the Savings
          Rate report counts as saved, plus debt payments outside {essential}. Left over: take-home
          not yet spent or saved.
        </p>
      </div>
      <div>
        <h3 className="income-split__note-head">Leaves out</h3>
        <p>
          Saving that never reaches the budget — a 401(k) deferral, a paycheck split straight to
          savings — so the rule is measured against take-home, not gross. Transfers between budget
          accounts, and money arriving from a loan.
        </p>
      </div>
    </section>
  )
}

function exportRows(data: Report) {
  const rows: Record<string, string | number>[] = []
  const add = (bucket: string, lines: IncomeSplitLine[]) =>
    lines.forEach((l) =>
      rows.push({
        bucket,
        line: l.name,
        group: l.group_name ?? '',
        counted_because: reasonChip(l),
        total: l.total,
      })
    )
  add('Needs', data.needs.lines)
  add('Wants · committed', data.wants.committed)
  add('Wants · chosen', data.wants.chosen)
  add('Savings & debt · saved', data.savings_debt.saved)
  add('Savings & debt · debt', data.savings_debt.debt)
  rows.push({
    bucket: 'Uncategorized',
    line: '',
    group: '',
    counted_because: '',
    total: data.uncategorized.total,
  })
  rows.push({
    bucket: 'Left over',
    line: '',
    group: '',
    counted_because: '',
    total: data.left_over,
  })
  return rows
}
