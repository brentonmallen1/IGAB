import { useFormatters } from '../../../hooks/useFormatters'
import { addMonths } from '../../../utils/dates'
import { EnvelopeListDialog } from '../EnvelopeListDialog/EnvelopeListDialog'
import type { OverspentLastMonth } from '../budgetTotals'

interface Props {
  /** The month being viewed; the overspending was the month before it. */
  month: string
  lastMonth: OverspentLastMonth
  onClose: () => void
}

/**
 * What the 1st took out of Ready to Assign, envelope by envelope.
 *
 * The header only carries the total, as a pill: the list sat there as a
 * sentence once and wrapped into two ragged lines beside the number. Every
 * figure is served (`overspent_last_month`); this names and lists them.
 */
export function LastMonthModal({ month, lastMonth, onClose }: Props) {
  const { formatMonth } = useFormatters()
  const previous = formatMonth(addMonths(month, -1))
  return (
    <EnvelopeListDialog
      title={`Overspent in ${previous}`}
      historyKey="overspent-last-month"
      tone="negative"
      lede={
        <>
          These ended {previous} below zero, so this month&rsquo;s Ready to Assign covered them on
          the 1st. Nothing to do now.
        </>
      }
      rows={lastMonth.sources.map((s) => ({ key: s.name, name: s.name, amount: -s.amount }))}
      total={-lastMonth.total}
      onClose={onClose}
    />
  )
}
