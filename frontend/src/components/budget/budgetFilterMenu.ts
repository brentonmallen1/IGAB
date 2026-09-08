/**
 * What the budget bar's one filter control offers, and which entry it reads.
 *
 * The bar drew a button per choice: `All`, up to five quick filters, and one
 * per saved filter — unbounded. It wraps, and the grid offsets its sticky
 * column header by this bar's *measured height*, so every filter someone saved
 * pushed the register further down the page. Bounding the chips helped and did
 * not fix it: the row still changed width as counts appeared and disappeared,
 * and on a phone it was several rows deep before anyone saved anything.
 *
 * The buttons were never independent to begin with. `setActiveFilter` clears
 * `activeQuickFilter` and `setActiveQuickFilter` clears `activeFilterId`, so
 * at most one of the eight was ever on — a single-valued choice wearing eight
 * controls. One `<select>` says the same thing in a fixed amount of space,
 * which is the property the bar needs.
 *
 * **A count of zero hides a quick filter, except the chosen one.** The old bar
 * dropped a chip at zero even while it was the active filter, leaving the grid
 * narrowed with nothing on screen saying so. Here the chosen entry is always
 * present, so the chip can always name what it is doing.
 */
import type { SelectChipGroup } from '../common/SelectChip/SelectChip'
import { QUICK_FILTER_LABELS, type QuickFilter } from '../../stores/uiStore'

export interface SavedFilter {
  id: string
  name: string
}

export type FilterChoice =
  { kind: 'all' } | { kind: 'quick'; filter: QuickFilter } | { kind: 'saved'; id: string }

export interface FilterMenu {
  /** The `<select>` value — `''` when nothing narrows the grid. */
  value: string
  groups: SelectChipGroup[]
  /** Overspent categories the chip is not already naming. Zero means draw no
   *  marker. The count is the one thing the collapsed row would otherwise
   *  stop saying out loud, and it is the one worth interrupting someone for. */
  attention: number
}

export function choiceValue(choice: FilterChoice): string {
  if (choice.kind === 'all') return ''
  return choice.kind === 'quick' ? `quick:${choice.filter}` : `saved:${choice.id}`
}

/** Ids are UUIDs and quick-filter keys are dash-separated, so neither carries
 *  the separator; split on the first one all the same. */
export function parseChoice(value: string): FilterChoice {
  const at = value.indexOf(':')
  if (at === -1) return { kind: 'all' }
  const rest = value.slice(at + 1)
  return value.slice(0, at) === 'quick'
    ? { kind: 'quick', filter: rest as QuickFilter }
    : { kind: 'saved', id: rest }
}

interface MenuInput {
  quickFilterOrder: readonly QuickFilter[]
  counts: Record<QuickFilter, number>
  saved: readonly SavedFilter[]
  activeQuickFilter: QuickFilter | null
  activeFilterId: string | null
}

export function filterMenu({
  quickFilterOrder,
  counts,
  saved,
  activeQuickFilter,
  activeFilterId,
}: MenuInput): FilterMenu {
  const quick = quickFilterOrder
    .filter((f) => counts[f] > 0 || f === activeQuickFilter)
    .map((f) => ({
      value: choiceValue({ kind: 'quick', filter: f }),
      label: `${QUICK_FILTER_LABELS[f]} (${counts[f]})`,
    }))

  // A persisted id can point at a filter this budget does not have — another
  // budget's, or one deleted in another tab. The bar self-heals it, but until
  // that runs the chip must not read blank: the grid is not narrowed by a
  // filter that does not exist, so `All categories` is the true answer.
  const activeSaved = saved.find((f) => f.id === activeFilterId)

  const value = activeQuickFilter
    ? choiceValue({ kind: 'quick', filter: activeQuickFilter })
    : activeSaved
      ? choiceValue({ kind: 'saved', id: activeSaved.id })
      : ''

  return {
    value,
    groups: [
      { label: 'By status', options: quick },
      {
        label: 'Saved filters',
        options: saved.map((f) => ({
          value: choiceValue({ kind: 'saved', id: f.id }),
          label: f.name,
        })),
      },
    ],
    attention: activeQuickFilter === 'overspent' ? 0 : counts.overspent,
  }
}
