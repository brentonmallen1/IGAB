/**
 * What the budget bar offers: status buttons for the statuses someone pinned,
 * and a "More filters" dropdown holding the other statuses and the saved
 * filters. Every rule about them lives here so the two controls cannot come
 * to disagree about a count, about which one is on, or about what a status
 * matches.
 *
 * **Why some statuses are buttons.** They are fixed things you reach for by
 * eye; a dropdown makes you open it to find out whether anything is
 * overspent. **Why not all of them.** There are six, and four of them ask
 * for nothing: a row of six was mostly noise beside the two that matter. So
 * the ones that earn the space are pinned (Manage Filters; overspent and
 * underfunded to start) and the rest sit in the menu with their counts. A
 * status is in exactly one of the two places, never both — two readings of
 * one number on screen are free to disagree.
 *
 * The bar wraps, and the grid offsets its sticky column header by this bar's
 * *measured height*, so the footprint must not move with the budget's state:
 *
 * - **Every pinned status renders always.** A zero count is `disabled`,
 *   never removed. The old row dropped a status whose count hit zero, so the
 *   row got narrower as things got better and the grid slid up the page.
 * - **The count sits in a fixed slot**, clamped at `99+`, so a digit appearing
 *   never reflows the row.
 * - **Everything unbounded is in the dropdown**, where a long list costs no
 *   width at all.
 *
 * The two controls remain ONE choice: `setActiveFilter` clears
 * `activeQuickFilter` and `setActiveQuickFilter` clears `activeFilterId`, so
 * at most one of them is ever on.
 */
import type { SelectChipGroup } from '../common/SelectChip/SelectChip'
import {
  ALL_QUICK_FILTERS,
  QUICK_FILTER_LABELS,
  QUICK_FILTER_VARIANTS,
  type QuickFilter,
} from '../../stores/uiStore'
import type { CategoryBalance } from '../../types'

export interface SavedFilter {
  id: string
  name: string
}

export type FilterChoice =
  | { kind: 'all' }
  | { kind: 'saved'; id: string }
  /** A status that is not pinned to the bar, chosen from the menu. */
  | { kind: 'status'; filter: QuickFilter }

/**
 * Does this category belong under a status? The one answer: the bar's counts
 * and the grid's rows both ask here. They used to be two switch statements in
 * two files, so a count could promise rows the grid then did not draw.
 *
 * Funding statuses read the served `target_status` — the server's
 * TargetService, the same function Fill Underfunded asks — never a
 * recomputation.
 */
export function quickFilterMatches(
  filter: QuickFilter,
  balance: Pick<CategoryBalance, 'available' | 'target_status'> | undefined
): boolean {
  switch (filter) {
    case 'overspent':
      return (balance?.available ?? 0) < 0
    case 'money-available':
      return (balance?.available ?? 0) > 0
    case 'underfunded':
      return balance?.target_status === 'underfunded'
    case 'pending':
      return balance?.target_status === 'pending'
    case 'overfunded':
      return balance?.target_status === 'overfunded'
    case 'spent-past-target':
      return balance?.target_status === 'spent_past_target'
  }
}

/** How many categories each status holds — `quickFilterMatches`, counted. */
export function quickFilterCounts(
  balances: readonly Pick<CategoryBalance, 'available' | 'target_status'>[]
): Record<QuickFilter, number> {
  const counts = {} as Record<QuickFilter, number>
  for (const filter of ALL_QUICK_FILTERS) {
    counts[filter] = balances.filter((b) => quickFilterMatches(filter, b)).length
  }
  return counts
}

export interface FilterMenu {
  /** The `<select>` value — `''` when nothing narrows the grid. */
  value: string
  groups: SelectChipGroup[]
}

/** One status, as a bar button or a menu line. `disabled` rather than absent
 *  at zero — see the note at the top about why the row's footprint must not
 *  move. */
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
 * Every status, always all of them, in the user's arranged order. The caller
 * splits them between the bar and the menu with `splitStatuses`.
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

/** The statuses split between the two controls: `bar` for the pinned ones,
 *  `menu` for the rest. Each status lands in exactly one. */
export function splitStatuses(
  statuses: readonly StatusButton[],
  pinned: readonly QuickFilter[]
): { bar: StatusButton[]; menu: StatusButton[] } {
  return {
    bar: statuses.filter((s) => pinned.includes(s.filter)),
    menu: statuses.filter((s) => !pinned.includes(s.filter)),
  }
}

export function choiceValue(choice: FilterChoice): string {
  if (choice.kind === 'all') return ''
  return choice.kind === 'saved' ? `saved:${choice.id}` : `status:${choice.filter}`
}

/** Ids are UUIDs, so they never carry the separator; split on the first one
 *  all the same. A status this build does not know reads as no choice. */
export function parseChoice(value: string): FilterChoice {
  const at = value.indexOf(':')
  if (at === -1) return { kind: 'all' }
  const rest = value.slice(at + 1)
  if (value.slice(0, at) === 'status') {
    const filter = ALL_QUICK_FILTERS.find((f) => f === rest)
    return filter ? { kind: 'status', filter } : { kind: 'all' }
  }
  return { kind: 'saved', id: rest }
}

interface MenuInput {
  saved: readonly SavedFilter[]
  activeFilterId: string | null
  /** The statuses that are not buttons on the bar (`splitStatuses().menu`).
   *  Empty where every status is drawn elsewhere, as on the phone's sheet. */
  statuses?: readonly StatusButton[]
}

/**
 * The dropdown: the statuses that are not pinned to the bar, each with its
 * count, then the saved filters.
 *
 * Only the unpinned ones. Offering a status in both places would put its
 * count on screen twice — two readings of the same number, free to disagree
 * the moment one of them is computed from a different list.
 */
export function filterMenu({ saved, activeFilterId, statuses = [] }: MenuInput): FilterMenu {
  // A persisted id can point at a filter this budget does not have — another
  // budget's, or one deleted in another tab. The bar self-heals it, but until
  // that runs the chip must not read blank: the grid is not narrowed by a
  // filter that does not exist, so `All categories` is the true answer.
  const activeSaved = saved.find((f) => f.id === activeFilterId)

  const activeStatus = statuses.find((s) => s.active)

  return {
    value: activeSaved
      ? choiceValue({ kind: 'saved', id: activeSaved.id })
      : activeStatus
        ? choiceValue({ kind: 'status', filter: activeStatus.filter })
        : '',
    groups: [
      {
        label: 'Status',
        options: statuses.map((s) => ({
          value: choiceValue({ kind: 'status', filter: s.filter }),
          label: `${s.label} (${s.countLabel})`,
        })),
      },
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
