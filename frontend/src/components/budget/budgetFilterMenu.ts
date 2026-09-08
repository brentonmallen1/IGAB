/**
 * What the budget bar offers: five status buttons, and a dropdown of saved
 * filters. Both rules live here so the two controls cannot come to disagree
 * about a count or about which one is on.
 *
 * **Why the statuses are buttons again.** They are five fixed things you reach
 * for by eye; a dropdown makes you open it to find out whether anything is
 * overspent. The reason they were collapsed into it was real, and is not about
 * being buttons: the bar wraps, the grid offsets its sticky column header by
 * this bar's *measured height*, and the old row's footprint moved with the
 * budget's state — it dropped a status whose count hit zero, so the row got
 * narrower as things got better and the register slid up and down the page.
 * Saved filters made it worse by being unbounded.
 *
 * So the footprint is now static, and that is the property to preserve:
 *
 * - **All five render always.** A zero count is `disabled`, never removed.
 *   This is the rule the old row got wrong.
 * - **The count sits in a fixed slot**, clamped at `99+`, so a digit appearing
 *   never reflows the row.
 * - **Saved filters stay in the dropdown**, where an unbounded list costs no
 *   width at all.
 *
 * The bar's width and height are then the same on an empty budget and a
 * hundred-category one, which is what the grid below it needs.
 *
 * The two controls remain ONE choice: `setActiveFilter` clears
 * `activeQuickFilter` and `setActiveQuickFilter` clears `activeFilterId`, so
 * at most one of them is ever on.
 */
import type { SelectChipGroup } from '../common/SelectChip/SelectChip'
import {
  QUICK_FILTER_LABELS,
  QUICK_FILTER_VARIANTS,
  type QuickFilter,
} from '../../stores/uiStore'

export interface SavedFilter {
  id: string
  name: string
}

//: Statuses are buttons and no longer reach this control, so there is no
//: `quick` arm here any more — a value shape nothing can emit is a second way
//: to say the same thing, waiting to disagree with the first.
export type FilterChoice = { kind: 'all' } | { kind: 'saved'; id: string }

export interface FilterMenu {
  /** The `<select>` value — `''` when nothing narrows the grid. */
  value: string
  groups: SelectChipGroup[]
}

/** One status button. `disabled` rather than absent at zero — see the note at
 *  the top about why the row's footprint must not move. */
export interface StatusButton {
  filter: QuickFilter
  label: string
  count: number
  /** What the count slot shows. Clamped, so three digits cannot widen it. */
  countLabel: string
  /** Tone class suffix, from the one map the Manage Filters badges also read. */
  variant: string
  active: boolean
  disabled: boolean
}

/** Above this the slot would grow a character. A budget with a hundred
 *  overspent categories is not asking for the exact figure. */
const COUNT_CEILING = 99

/**
 * The five status buttons, always all five, in the user's arranged order.
 *
 * A status with nothing in it is disabled rather than dropped — and the active
 * one is never disabled, so a filter that empties its own list still says what
 * it is doing rather than leaving a narrowed grid with no visible reason.
 */
export function statusButtons({
  quickFilterOrder,
  counts,
  activeQuickFilter,
}: {
  quickFilterOrder: readonly QuickFilter[]
  counts: Record<QuickFilter, number>
  activeQuickFilter: QuickFilter | null
}): StatusButton[] {
  return quickFilterOrder.map((filter) => {
    const count = counts[filter] ?? 0
    const active = activeQuickFilter === filter
    return {
      filter,
      label: QUICK_FILTER_LABELS[filter],
      count,
      countLabel: count > COUNT_CEILING ? `${COUNT_CEILING}+` : String(count),
      variant: QUICK_FILTER_VARIANTS[filter],
      active,
      disabled: count === 0 && !active,
    }
  })
}

export function choiceValue(choice: FilterChoice): string {
  return choice.kind === 'all' ? '' : `saved:${choice.id}`
}

/** Ids are UUIDs, so they never carry the separator; split on the first one
 *  all the same. */
export function parseChoice(value: string): FilterChoice {
  const at = value.indexOf(':')
  return at === -1 ? { kind: 'all' } : { kind: 'saved', id: value.slice(at + 1) }
}

interface MenuInput {
  saved: readonly SavedFilter[]
  activeFilterId: string | null
}

/**
 * The dropdown: saved filters, and nothing else.
 *
 * Statuses left it for the button row. Offering them in both places would put
 * the overspent count on screen twice — two readings of the same number, free
 * to disagree the moment one of them is computed from a different list.
 */
export function filterMenu({ saved, activeFilterId }: MenuInput): FilterMenu {
  // A persisted id can point at a filter this budget does not have — another
  // budget's, or one deleted in another tab. The bar self-heals it, but until
  // that runs the chip must not read blank: the grid is not narrowed by a
  // filter that does not exist, so `All categories` is the true answer.
  const activeSaved = saved.find((f) => f.id === activeFilterId)

  return {
    value: activeSaved ? choiceValue({ kind: 'saved', id: activeSaved.id }) : '',
    groups: [
      {
        label: 'Saved filters',
        options: saved.map((f) => ({
          value: choiceValue({ kind: 'saved', id: f.id }),
          label: f.name,
        })),
      },
    ],
  }
}
