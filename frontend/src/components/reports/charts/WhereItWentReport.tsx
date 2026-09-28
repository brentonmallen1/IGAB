import { useMemo, useRef, useState } from 'react'
import { ChevronRight } from 'lucide-react'
import {
  resolveWhereItWentView,
  useReportScope,
  useReportStore,
  type GroupBy,
  type WhereItWentView,
} from '../../../stores/reportStore'
import { usePayeeAnalysisReport, useSpendingGroupedReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportErrorState } from '../ReportErrorState'
import { ReportInfoButton, ReportScopeNote, SpendingClassNote } from '../ReportInfoButton'
import { ReportNotes, IncludeSavingsToggle, emptySpendingMessage } from '../ReportNotes'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { drillDownFooter } from '../drillDownTotals'
import { categoryTarget } from '../drillScope'
import { PAYEE_RANKED } from './reportControls'
import { WhereItWentTreemap } from './WhereItWentTreemap'
import {
  concentrationSentence,
  exportRows,
  groupCategoryLines,
  rankedLines,
  rankedTable,
  runningLabel,
  shareLabel,
  type RankedLine,
} from './whereItWent'
import './WhereItWentReport.css'

interface Props {
  budgetId: string
}

const VIEWS: { value: WhereItWentView; label: string }[] = [
  { value: 'table', label: 'Table' },
  { value: 'treemap', label: 'Treemap' },
]

const LINE_HEADINGS: Record<GroupBy, string> = {
  group: 'Group',
  category: 'Category',
  payee: 'Payee',
}

/**
 * Where the period's spending went, ranked.
 *
 * Breakdown, Pareto and Treemap read one endpoint and showed the same rows
 * three ways: a donut that stopped saying anything past eight slices, bars
 * under a running-share line whose only facts of its own were "N of M make
 * 80%" and a payee mode, and tiles sized by amount. This is the table all
 * three were drawing, with the running share as a column and the 80% line
 * marked in it; the treemap is a view of the same rows.
 */
export function WhereItWentReport({ budgetId }: Props) {
  const { formatMoney } = useFormatters()
  const { filters, setDrillDown, whereItWentView, setWhereItWentView } = useReportStore()
  const groupBy = filters.groupBy
  const view = resolveWhereItWentView(whereItWentView, groupBy)
  const captureRef = useRef<HTMLDivElement>(null)
  const [includeSavings, setIncludeSavings] = useState(false)
  const [openGroup, setOpenGroup] = useState<string | null>(null)

  // Close an opened group when the mode or the view changes (state adjusted
  // during render, per react-hooks/set-state-in-effect). A view replaces the
  // whole group keyspace, so a group held across the switch named a key that
  // no longer exists.
  const scopeKey = `${groupBy}|${filters.viewId ?? ''}`
  const [prevScopeKey, setPrevScopeKey] = useState(scopeKey)
  if (prevScopeKey !== scopeKey) {
    setPrevScopeKey(scopeKey)
    setOpenGroup(null)
  }

  const reportScope = useReportScope()
  const acctIds = filters.accountIds.length > 0 ? filters.accountIds : undefined
  const payeeIds = filters.payeeIds.length > 0 ? filters.payeeIds : undefined
  // Both queries always run — hooks are unconditional. Payee Analysis takes
  // no savings toggle, and the filter bar dims what each mode ignores.
  const spendingQ = useSpendingGroupedReport(
    budgetId,
    filters.startDate,
    filters.endDate,
    reportScope,
    acctIds,
    includeSavings && groupBy !== 'payee',
    filters.viewId
  )
  const payeeQ = usePayeeAnalysisReport(
    budgetId,
    filters.startDate,
    filters.endDate,
    PAYEE_RANKED,
    payeeIds,
    acctIds
  )

  const items = useMemo(() => spendingQ.data?.groups ?? [], [spendingQ.data])
  const opened = useMemo(
    () => (groupBy === 'group' && openGroup ? groupCategoryLines(items, openGroup) : null),
    [groupBy, openGroup, items]
  )
  const ranked = useMemo(
    () => opened ?? rankedLines(groupBy, items, spendingQ.data?.total, payeeQ.data),
    [opened, groupBy, items, spendingQ.data, payeeQ.data]
  )
  const table = useMemo(() => rankedTable(ranked), [ranked])

  const activeQ = groupBy === 'payee' ? payeeQ : spendingQ
  if (activeQ.isLoading) return <div className="report-loading">Loading…</div>
  if (activeQ.isError)
    return <ReportErrorState error={activeQ.error} onRetry={() => activeQ.refetch()} />

  // What the rows are: an opened group lists its categories.
  const lineMode: GroupBy = opened ? 'category' : groupBy
  const window = { startDate: filters.startDate, endDate: filters.endDate }
  const sentence = concentrationSentence(table.to80, ranked.universeCount, lineMode, opened?.name)
  // Payee mode lists the ranked 25 of every payee; the footer says so rather
  // than heading 25 rows' sum "Total".
  const footer = drillDownFooter(
    ranked.lines.map((l) => ({ amount: l.total })),
    groupBy === 'payee'
      ? { total: ranked.total, count: ranked.universeCount, label: 'payees' }
      : undefined,
    formatMoney
  )
  const showGroupColumn = lineMode === 'category' && !opened

  /** What a row opens: a group's categories, or the transactions behind the
   *  line — every row of the classes the report counted, whichever way it
   *  went, since spending is net of refunds and an outflow list totals more
   *  than the line. Payee lines carry no category scope: their report takes
   *  none, and the filter bar dims it there. */
  function openLine(line: RankedLine) {
    if (lineMode === 'group') {
      setOpenGroup(line.id)
      return
    }
    if (lineMode === 'payee') {
      if (!payeeQ.data) return
      setDrillDown({
        kind: 'payee',
        label: line.name,
        scope: 'leaf',
        payeeIds: [line.id],
        activityClasses: payeeQ.data.counted_classes,
        ...window,
      })
      return
    }
    if (!spendingQ.data) return
    setDrillDown({
      kind: 'category',
      label: line.name,
      scope: 'leaf',
      ...categoryTarget(line.members),
      activityClasses: spendingQ.data.counted_classes,
      ...window,
    })
  }

  /** Every transaction of the opened group — what its line in the group
   *  table added up. */
  function openGroupTransactions() {
    if (!opened || !spendingQ.data) return
    setDrillDown({
      kind: 'category-group',
      label: opened.name,
      scope: 'leaf',
      ...categoryTarget(opened.lines.flatMap((l) => l.members)),
      activityClasses: spendingQ.data.counted_classes,
      ...window,
    })
  }

  const lastRow = table.rows.length - 1

  return (
    <div className="report-section surface">
      <div className="report-section__header wiw__header">
        <h2 className="report-section__title">Where it went</h2>
        <ReportInfoButton title="Where it went">
          <p>
            The period&apos;s spending, largest first, by group, category or payee — switch with{' '}
            <strong>Group by</strong> in the toolbar. <strong>Share</strong> is each line&apos;s
            part of the total; <strong>Running share</strong> adds the lines above it, and the line
            marks where it reaches 80%: how few lines make most of the spending.
          </p>
          <p>
            A line whose refunds outweighed its spending is listed last, signed, and brings the
            running share back to 100%. Payee mode lists the 25 largest payees and counts the 80%
            over every payee; it ignores the category, tag, saved-filter and view pickers, which
            dim.
          </p>
          <p>
            Open a group to see its categories; open a category or payee to see the transactions
            behind it. The treemap draws the same lines as areas.
          </p>
          <ReportScopeNote report="where-it-went" />
          <SpendingClassNote />
        </ReportInfoButton>
        <div className="wiw__views" role="group" aria-label="Show as">
          {VIEWS.map((v) => {
            // Payee mode has only the ranked 25, which would fill the area
            // and read as all of the spending (`resolveWhereItWentView`).
            const unavailable = v.value === 'treemap' && groupBy === 'payee'
            return (
              <button
                key={v.value}
                type="button"
                className={`report-btn ${view === v.value ? 'report-btn--active' : ''}`}
                aria-pressed={view === v.value}
                disabled={unavailable}
                title={unavailable ? 'Payee mode lists the 25 largest payees, not all of them' : ''}
                onClick={() => setWhereItWentView(v.value)}
              >
                {v.label}
              </button>
            )
          })}
        </div>
        {groupBy !== 'payee' && (
          <IncludeSavingsToggle checked={includeSavings} onChange={setIncludeSavings} />
        )}
        <div className="ms-auto">
          <ReportExportButton
            reportId="where-it-went"
            getRows={() => exportRows(table)}
            captureRef={captureRef}
            window={{ start: filters.startDate, end: filters.endDate }}
          />
        </div>
      </div>

      {/* Payee mode reads Payee Analysis, which no view filters. */}
      {groupBy !== 'payee' && (
        <ReportNotes report={spendingQ.data} toggleAvailable={!includeSavings} />
      )}

      {opened && (
        <nav className="wiw__crumbs" aria-label="Opened group">
          <button type="button" className="wiw__crumb" onClick={() => setOpenGroup(null)}>
            All groups
          </button>
          <ChevronRight size={14} className="wiw__crumb-sep" aria-hidden />
          <span className="wiw__crumb wiw__crumb--here">{opened.name}</span>
          <button
            type="button"
            className="report-btn wiw__crumb-list"
            onClick={openGroupTransactions}
          >
            List its transactions
          </button>
        </nav>
      )}

      {ranked.lines.length === 0 ? (
        <div className="reports-empty">
          {emptySpendingMessage(groupBy === 'payee' ? 0 : spendingQ.data?.view_hidden_categories)}
        </div>
      ) : (
        <div ref={captureRef} className="report-capture">
          <MetricRow>
            <MetricCard label={opened ? opened.name : 'Spent'} value={formatMoney(ranked.total)} />
          </MetricRow>
          {sentence ? (
            <p className="wiw__reading">{sentence}.</p>
          ) : (
            ranked.total <= 0 && (
              <p className="wiw__reading">
                Refunds took back as much as was spent, so there are no shares to state.
              </p>
            )
          )}

          {view === 'treemap' && lineMode !== 'payee' ? (
            <WhereItWentTreemap
              items={items}
              total={ranked.total}
              mode={groupBy === 'category' ? 'category' : 'group'}
              openGroup={opened ? openGroup : null}
              onOpenGroup={setOpenGroup}
              onOpenCategory={(tile) => {
                const line = ranked.lines.find((l) => l.id === tile.id)
                if (line) openLine(line)
              }}
            />
          ) : (
            <table className="report-table wiw__table">
              <caption className="sr-only">
                Where the spending went, by {LINE_HEADINGS[lineMode].toLowerCase()}
              </caption>
              <thead>
                <tr>
                  <th scope="col" className="wiw__name">
                    {LINE_HEADINGS[lineMode]}
                  </th>
                  {showGroupColumn && (
                    <th scope="col" className="wiw__name wiw__group">
                      Group
                    </th>
                  )}
                  <th scope="col" className="wiw__num">
                    Spent
                  </th>
                  <th scope="col" className="wiw__num">
                    Share
                  </th>
                  <th scope="col" className="wiw__num">
                    Running share
                  </th>
                </tr>
              </thead>
              <tbody>
                {table.rows.map(({ line, share, cumulative, crosses80 }, i) => (
                  <WhereRow
                    key={line.id}
                    line={line}
                    opens={lineMode === 'group' ? 'group' : 'transactions'}
                    showGroup={showGroupColumn}
                    spent={formatMoney(line.total)}
                    share={shareLabel(share)}
                    cumulative={runningLabel(cumulative)}
                    marked={crosses80 && i < lastRow}
                    onOpen={() => openLine(line)}
                  />
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td>{footer.totalLabel}</td>
                  {showGroupColumn && <td className="wiw__group" />}
                  <td className="wiw__num tabular">{formatMoney(footer.shown)}</td>
                  <td className="wiw__num tabular">
                    {footer.share === null ? '' : shareLabel(footer.share)}
                  </td>
                  <td />
                </tr>
                {footer.wider !== null && (
                  <tr className="wiw__of">
                    <td>{footer.widerLabel}</td>
                    {showGroupColumn && <td className="wiw__group" />}
                    <td className="wiw__num tabular">{formatMoney(footer.wider)}</td>
                    <td />
                    <td />
                  </tr>
                )}
              </tfoot>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

/** One ranked line, and — under the line whose running share reaches 80% —
 *  the mark that says so. */
function WhereRow({
  line,
  opens,
  showGroup,
  spent,
  share,
  cumulative,
  marked,
  onOpen,
}: {
  line: RankedLine
  opens: 'group' | 'transactions'
  showGroup: boolean
  spent: string
  share: string
  cumulative: string
  marked: boolean
  onOpen: () => void
}) {
  return (
    <>
      <tr className={marked ? 'wiw__row--crosses' : undefined}>
        <td className="wiw__name">
          {/* A button, not a clickable row, so every line opens from the
              keyboard too. */}
          <button
            type="button"
            className="report-table__drill"
            onClick={onOpen}
            aria-label={
              opens === 'group'
                ? `Open ${line.name}'s categories`
                : `Show the transactions behind ${line.name}`
            }
          >
            {line.name}
          </button>
        </td>
        {showGroup && <td className="wiw__name wiw__group">{line.groupName ?? ''}</td>}
        <td className="wiw__num tabular">{spent}</td>
        <td className="wiw__num tabular wiw__muted">{share}</td>
        <td className="wiw__num tabular">{cumulative}</td>
      </tr>
      {marked && (
        // Cell for cell with the rows, not one spanning cell: the phone hides
        // the Group column, and a span counted with it drew a phantom column.
        <tr className="wiw__mark" aria-hidden>
          <td>80% of spending is above this line</td>
          {showGroup && <td className="wiw__group" />}
          <td />
          <td />
          <td />
        </tr>
      )}
    </>
  )
}
