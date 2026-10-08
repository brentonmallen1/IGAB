import { memo } from 'react'
import { useFormatters } from '../../../hooks/useFormatters'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import { categoryCellAction, categoryCellLabel } from '../categoryCell'
import type { Transaction } from '../../../types'
import './SplitLineRows.css'

interface Props {
  /** The split the lines belong to. A click on a line opens THIS row's split,
   *  by the same rule its own category cell uses (categoryCell.ts). */
  parent: Transaction
  /** From `useSplitLinesFor` — undefined while the batch is loading. */
  lines: Transaction[] | undefined
  categoryMap: ReadonlyMap<string, string>
  accountOnBudget: boolean
  onStartSplit: (txn: Transaction) => void
  onEdit: (txn: Transaction) => void
}

/** What a line's category cell reads. A line is never a split itself. */
function lineCategory(
  line: Transaction,
  categoryMap: ReadonlyMap<string, string>,
  accountOnBudget: boolean
): string {
  const label = categoryCellLabel(line, categoryMap, accountOnBudget)
  switch (label.kind) {
    case 'category':
      return label.name
    case 'needs-category':
      return 'Needs Category'
    case 'transfer':
      return 'Transfer'
    default:
      return '—'
  }
}

/**
 * A split's lines, read-only, under its row in the register — the "show split
 * lines" view. Each line sits in the register's own grid, so its category,
 * memo and money land under the headers that caption them, in both the
 * one-account and all-accounts layouts.
 *
 * Lines come from the server (`useSplitLinesFor`), never from the loaded
 * page: the register lists parent rows only.
 */
export const SplitLineRows = memo(function SplitLineRows({
  parent,
  lines,
  categoryMap,
  accountOnBudget,
  onStartSplit,
  onEdit,
}: Props) {
  const { formatMoney } = useFormatters()
  const isMobile = useIsMobile()
  if (!lines || lines.length === 0) return null

  const action = categoryCellAction(parent, { isMobile, accountOnBudget })
  const open =
    action === 'split'
      ? () => onStartSplit(parent)
      : action === 'edit'
        ? () => onEdit(parent)
        : null

  return (
    <div className="split-lines" role="group" aria-label="Split lines">
      {lines.map((line) => {
        const category = lineCategory(line, categoryMap, accountOnBudget)
        const cells = (
          <>
            <span className="split-line__category">{category}</span>
            <span className="split-line__memo">{line.memo ?? ''}</span>
            <span
              className={`split-line__amount tabular ${line.amount < 0 ? 'split-line__amount--out' : 'split-line__amount--in'}`}
            >
              {formatMoney(Math.abs(line.amount))}
            </span>
          </>
        )
        return open ? (
          <button
            key={line.id}
            type="button"
            className="split-line split-line--interactive"
            onClick={open}
            title="Open this split"
          >
            {cells}
          </button>
        ) : (
          <div key={line.id} className="split-line">
            {cells}
          </div>
        )
      })}
    </div>
  )
})
