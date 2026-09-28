/**
 * Plan vs Spent's column header row, drawn twice: once as the table's own
 * header, for assistive tech and collapsed to no height, and once as the
 * visible strip that pins under the report header while the page scrolls.
 *
 * Twice because the table cannot pin its own header to the page: it scrolls
 * sideways, and a box that scrolls sideways is its own scroll container in
 * both directions — a row pinned inside it pins to the box, not the page.
 * Giving the box a height of its own so the row could pin there made two
 * vertical scrollers, and on a phone a drag that began on the table scrolled
 * the table and stranded the page. One component, so the two rows cannot
 * name or order their columns differently; one set of column widths
 * (PlanVsSpentReport.css), so they cannot drift apart.
 */
interface Props {
  months: string[]
  monthName: (month: string) => string
  isRunning: (month: string) => boolean
  /** The table's own header: every label for assistive tech, nothing drawn. */
  collapsed?: boolean
}

export function PlanVsSpentHeadRow({ months, monthName, isRunning, collapsed = false }: Props) {
  const label = (text: string) => (collapsed ? <span className="sr-only">{text}</span> : text)
  return (
    <tr>
      <th scope="col" className="plan-spent__name">
        {label('Category')}
      </th>
      {months.map((m) => (
        <th
          scope="col"
          key={m}
          className={`plan-spent__month-header${isRunning(m) ? ' plan-spent__month-header--running' : ''}`}
        >
          {label(monthName(m))}
        </th>
      ))}
      <th scope="col" className="plan-spent__tot plan-spent__tot--months">
        {label('Over')}
      </th>
      <th scope="col" className="plan-spent__tot plan-spent__tot--funded">
        {label('Funded')}
      </th>
      <th scope="col" className="plan-spent__tot plan-spent__tot--spent">
        {label('Spent')}
      </th>
      <th scope="col" className="plan-spent__tot plan-spent__tot--overspent">
        {label('Overspent')}
      </th>
    </tr>
  )
}
