import { useState } from 'react'
import { Info } from 'lucide-react'
import { Dialog } from '../common/Dialog/Dialog'
import {
  REPORT_TABS,
  TAB_GROUPS,
  useReportStore,
  type ReportTab,
  type TabGroup,
} from '../../stores/reportStore'
import { REPORT_CATALOG, REPORT_SECTIONS, type ReportCatalogEntry } from './reportCatalog'
import { SCOPE_COPY } from './reportScope'
import './ReportsOverviewDialog.css'

/** The table's columns, named once: the header row reads them on a wide
 *  screen, and each cell's stacked label reads them on a phone. */
const COLUMNS = {
  report: 'Report',
  counts: 'Counts',
  leavesOut: 'Leaves out',
  accounts: 'Accounts',
} as const

interface Row extends ReportCatalogEntry {
  key: string
  label: string
  tab: ReportTab
  /** A report drawn inside another tab — indented under it. */
  nested: boolean
}

function groupRows(group: TabGroup): Row[] {
  return REPORT_TABS.filter((t) => t.group === group).flatMap((t) => [
    { key: t.id, label: t.label, tab: t.id, nested: false, ...REPORT_CATALOG[t.id] },
    ...Object.entries(REPORT_SECTIONS)
      .filter(([, s]) => s.tab === t.id)
      .map(([id, s]) => ({ key: id, nested: true, ...s })),
  ])
}

/**
 * What every report counts, in one table — opened from the ⓘ beside the star
 * in the Reports nav, desktop and phone. Mounted only while open.
 */
export function ReportsOverviewDialog({ onClose }: { onClose: () => void }) {
  const setActiveTab = useReportStore((s) => s.setActiveTab)
  const setNavFavorites = useReportStore((s) => s.setNavFavorites)

  function open(tab: ReportTab) {
    setActiveTab(tab)
    // The report's own group row always holds it; the starred row may not.
    setNavFavorites(false)
    onClose()
  }

  return (
    <Dialog title="About these reports" onClose={onClose} historyKey="reports-overview" width="lg">
      <p className="dialog__body">
        What each report counts, what it leaves out, and which accounts it reads. Pick a report to
        open it.
      </p>
      {TAB_GROUPS.map((group) => (
        <section
          key={group.id}
          className="reports-overview__group"
          aria-labelledby={`reports-overview-${group.id}`}
        >
          <h4 id={`reports-overview-${group.id}`} className="reports-overview__heading">
            {group.label}
          </h4>
          <div className="reports-overview__scroll">
            <table className="reports-overview__table">
              <thead>
                <tr>
                  {Object.values(COLUMNS).map((c) => (
                    <th key={c} scope="col">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {groupRows(group.id).map((row) => (
                  <tr
                    key={row.key}
                    className={row.nested ? 'reports-overview__row--nested' : undefined}
                  >
                    <td data-label={COLUMNS.report}>
                      <button
                        type="button"
                        className="reports-overview__report"
                        onClick={() => open(row.tab)}
                      >
                        {row.label}
                      </button>
                      <span className="reports-overview__summary">{row.summary}</span>
                    </td>
                    <td data-label={COLUMNS.counts}>{row.counts}</td>
                    <td data-label={COLUMNS.leavesOut}>{row.leavesOut}</td>
                    <td data-label={COLUMNS.accounts}>
                      <span className="reports-overview__accounts">{SCOPE_COPY[row.scope]}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </Dialog>
  )
}

/** The ⓘ that opens the overview. One component for both chromes, which
 *  differ only in how the button is sized. */
export function ReportsOverviewButton({
  className,
  iconSize,
}: {
  className: string
  iconSize: number
}) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        type="button"
        className={className}
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        title="About these reports"
        aria-label="About these reports"
      >
        <Info size={iconSize} />
      </button>
      {open && <ReportsOverviewDialog onClose={() => setOpen(false)} />}
    </>
  )
}
