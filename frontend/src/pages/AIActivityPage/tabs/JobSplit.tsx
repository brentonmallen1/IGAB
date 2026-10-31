import { useMemo } from 'react'
import { Split } from 'lucide-react'
import type { AIJob } from '../../../api/aiJobs'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { useFormatters } from '../../../hooks/useFormatters'
import type { Transaction } from '../../../types'
import { buildCategoryLabels } from '../../../utils/categoryLabels'
import { jobSplitView } from './jobSplitView'

/**
 * The split under a scan's card: each line's envelope and amount, so a split
 * the scan filed can be checked without opening the row — and a split the
 * model read but the row did not take is visible beside its one category.
 */
export function JobSplit({
  job,
  budgetId,
  lines,
}: {
  job: AIJob
  budgetId: string
  lines: readonly Transaction[] | undefined
}) {
  // Archived included, so a line filed in an envelope archived since is
  // still named — as JobCategory names the unsplit row.
  const { data: categories = [] } = useCategories(budgetId, true)
  const { data: groups = [] } = useCategoryGroups(budgetId, true)
  const labels = useMemo(() => buildCategoryLabels(categories, groups), [categories, groups])
  const { formatMoney } = useFormatters()

  const view = jobSplitView(job, lines, labels)
  if (!view) return null

  return (
    <div className={`ai-activity__split ai-activity__split--${view.kind}`}>
      <span className="ai-activity__split-head">
        <Split size={11} aria-hidden />
        {view.kind === 'filed'
          ? `Split ${view.lines.length} ways`
          : 'AI suggested a split, not applied'}
      </span>
      <ul className="ai-activity__split-lines">
        {view.lines.map((line, i) => (
          <li key={i} className="ai-activity__split-line">
            <span className="ai-activity__split-name">{line.label}</span>
            <span className="ai-activity__split-amount tabular">{formatMoney(line.amount)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
