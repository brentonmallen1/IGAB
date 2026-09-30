import type { SelectionSheetOption } from '../../common/SelectionSheet/SelectionSheet'
import type { SplitDraft } from '../../../stores/transactionEditStore'
import { SplitSheet } from './SplitSheet'
import { SplitSummaryRow } from './SplitSummaryRow'

/**
 * A split in a phone form: the one summary row, and the full-screen sheet it
 * opens. Quick add and the editor both mount this, so the two cannot wire
 * the row and the sheet together two ways. `open` is the host's so it can
 * open the sheet the moment a split begins.
 */
export function PhoneSplit({
  open,
  onOpenChange,
  totalCents,
  legs,
  onChange,
  categoryOptions,
  canCategorize,
  onUnsplit,
  loading = false,
  framed = false,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  totalCents: number
  legs: SplitDraft[]
  onChange: (legs: SplitDraft[]) => void
  categoryOptions: SelectionSheetOption[]
  canCategorize: boolean
  onUnsplit?: () => void
  /** A saved split's lines are still on their way: nothing to summarise. */
  loading?: boolean
  framed?: boolean
}) {
  const nameOf = (id: string) => categoryOptions.find((o) => o.id === id)?.label ?? ''
  return (
    <>
      {loading ? (
        <div className="split-summary split-summary--loading" role="status">
          Loading lines…
        </div>
      ) : (
        <SplitSummaryRow
          framed={framed}
          totalCents={totalCents}
          legs={legs}
          nameOf={nameOf}
          onOpen={() => onOpenChange(true)}
        />
      )}
      <SplitSheet
        open={open && !loading}
        onClose={() => onOpenChange(false)}
        totalCents={totalCents}
        legs={legs}
        onChange={onChange}
        categoryOptions={categoryOptions}
        canCategorize={canCategorize}
        onUnsplit={onUnsplit}
      />
    </>
  )
}
