/**
 * Where it went: the ranked lines, their running share, and the 80% line.
 * Pure, so the concentration math is a unit test and not something to click
 * through a table to check.
 *
 * One report now does what Breakdown, Pareto and Treemap did three times over
 * from one endpoint. Each had its own spelling of the same steps: the group
 * key (`parent_id ?? '__none__'`, three copies), the group totals (summed
 * twice, once against the served total and once against its own sum), and
 * the share of what is on screen. The group totals and key come from
 * `treemapGroups`, which the treemap view draws from too, so the table and the
 * tiles cannot disagree about a group.
 */
import type { GroupBy } from '../../../stores/reportStore'
import type { SpendingGroupItem } from '../../../types'
import { toCents } from '../../../utils/money'
import { shareOfTotal } from '../drillDownTotals'
import { categoryKey } from '../drillScope'
import { groupKeyOf, treemapGroups, type TreemapGroup } from './treemapTiles'

export interface RankedLine {
  id: string
  name: string
  total: number
  /** The group a category line sits in — the table's Group column. Null on a
   *  group line and in payee mode. */
  groupName: string | null
  /** The category ids a line opens (`categoryTarget`): its own, a group's
   *  members, or `[null]` for the Uncategorized line. Empty in payee mode,
   *  whose lines open by payee. */
  members: (string | null)[]
}

type Item = Pick<SpendingGroupItem, 'id' | 'name' | 'parent_id' | 'parent_name' | 'total'>

interface PayeeItemLike {
  payee_id: string
  payee_name: string
  total: string | number
}

/** The payee analysis response, whole: the ranked rows travel with the
 *  served figures that span every payee, so a caller cannot pass one without
 *  the other. */
interface PayeeReportLike {
  payees: PayeeItemLike[]
  total: string | number
  payee_count: number
  payees_to_80pct: number | null
}

export interface RankedLines {
  /** Largest first. A line that took back more than it spent sorts last,
   *  signed. */
  lines: RankedLine[]
  /** What the shares are of. */
  total: number
  /** How many lines exist in the window — larger than `lines.length` only in
   *  payee mode, where the server ranks the top 25 and the old Pareto stated
   *  that cap as a period-wide fact. */
  universeCount: number
  /** Served in payee mode, where the client holds only the top 25 and so
   *  cannot find the 80% line itself. Undefined means "count it here". */
  servedTo80?: number | null
}

const byTotal = (a: { total: number }, b: { total: number }) => b.total - a.total

function categoryLine(item: Item): RankedLine {
  return {
    id: categoryKey(item.id),
    name: item.name,
    total: Number(item.total),
    groupName: item.parent_name,
    members: [item.id],
  }
}

function groupLine(group: TreemapGroup): RankedLine {
  return {
    id: group.key,
    name: group.name,
    total: group.total,
    groupName: null,
    members: group.children.map((c) => c.categoryId),
  }
}

/**
 * The lines a mode ranks.
 *
 * Category and group mode state shares of the served total, which is the sum
 * of every line (backend `spending_grouped`). Pareto's group mode summed its
 * own and the Breakdown and Treemap read the served figure — the same number
 * until a cent of rounding, and then two.
 *
 * Payee mode takes the whole response or nothing. An absent response (still
 * loading) is no payees at all, never a total summed from the ranked 25.
 */
export function rankedLines(
  groupBy: GroupBy,
  items: readonly Item[],
  servedTotal: string | number | undefined,
  payeeReport: PayeeReportLike | undefined
): RankedLines {
  if (groupBy === 'payee') {
    if (payeeReport === undefined) {
      return { lines: [], total: 0, universeCount: 0, servedTo80: null }
    }
    const lines = payeeReport.payees
      .map((p) => ({
        id: p.payee_id,
        name: p.payee_name,
        total: Number(p.total),
        groupName: null,
        members: [],
      }))
      .sort(byTotal)
    return {
      lines,
      total: Number(payeeReport.total),
      universeCount: payeeReport.payee_count,
      servedTo80: payeeReport.payees_to_80pct,
    }
  }
  const total = Number(servedTotal ?? 0)
  const lines =
    groupBy === 'group'
      ? [...treemapGroups(items).values()].map(groupLine).sort(byTotal)
      : items.map(categoryLine).sort(byTotal)
  return { lines, total, universeCount: lines.length }
}

/** One group's categories, ranked against the group's own total — what the
 *  table and the treemap show once a group is opened. Null for a key the
 *  data no longer holds (a view switched under an open group). */
export function groupCategoryLines(
  items: readonly Item[],
  key: string
): (RankedLines & { name: string }) | null {
  const group = treemapGroups(items).get(key)
  if (!group) return null
  const lines = items
    .filter((i) => groupKeyOf(i) === key)
    .map(categoryLine)
    .sort(byTotal)
  return { name: group.name, lines, total: group.total, universeCount: lines.length }
}

/** Running share of `total` at each line, in order (0–100), or null where
 *  there is no positive total to be a share of (`shareOfTotal`).
 *
 *  Net of refunds, a line can be negative, so the positive lines above it can
 *  run past 100% and the negative ones bring it back: it always ends at 100.
 *
 *  Summed in cents. A running sum of dollar floats lands a hair under a line
 *  it reaches exactly — 79.99999… — and the 80% line moved down a row. */
export function cumulativeShares(
  lines: readonly { total: number }[],
  total: number
): (number | null)[] {
  const whole = toCents(total)
  let running = 0
  return lines.map((line) => {
    running += toCents(line.total)
    return shareOfTotal(running, whole)
  })
}

/** The 0-based index of the line whose running share reaches 80%, or -1.
 *
 *  `shares` must span every line, not a slice of them — the old chart passed
 *  its twenty drawn bars, so a budget whose 80% line sat at item 32 got no
 *  answer at all, for exactly the diffuse spending the figure exists to name.
 *  Payee mode is served the count instead, because its shares top out at the
 *  ranked 25's. `shared/pareto_cases.json` holds this and the server's
 *  `domain/concentration.py` to one answer. */
export function indexTo80(shares: readonly (number | null)[], servedTo80?: number | null): number {
  if (servedTo80 !== undefined) return servedTo80 === null ? -1 : servedTo80 - 1
  return shares.findIndex((share) => share !== null && share >= 80)
}

export interface RankedRow {
  line: RankedLine
  /** Share of the total, or null with no positive total. */
  share: number | null
  cumulative: number | null
  /** This is the line whose running share reaches 80%. */
  crosses80: boolean
}

export interface RankedTable {
  rows: RankedRow[]
  /** How many lines make 80% — past the listed rows in payee mode — or null
   *  where there is no 80% line (nothing spent, or refunds beat spending). */
  to80: number | null
}

export function rankedTable({ lines, total, servedTo80 }: RankedLines): RankedTable {
  const shares = cumulativeShares(lines, total)
  const idx = indexTo80(shares, servedTo80)
  return {
    rows: lines.map((line, i) => ({
      line,
      share: shareOfTotal(line.total, total),
      cumulative: shares[i],
      crosses80: i === idx,
    })),
    to80: idx >= 0 ? idx + 1 : null,
  }
}

const NOUNS: Record<GroupBy, [string, string]> = {
  category: ['category', 'categories'],
  group: ['group', 'groups'],
  payee: ['payee', 'payees'],
}

/** The table's one-line reading: "12 of 56 categories make 80% of spending".
 *
 *  No verdict. Pareto once added "concentrated — easier to optimize" or
 *  "spread thin — consider consolidating" at a 30% threshold: advice from a
 *  number that describes a budget's shape, not a problem with it. `within`
 *  names an opened group. */
export function concentrationSentence(
  to80: number | null,
  universeCount: number,
  groupBy: GroupBy,
  within?: string
): string | null {
  if (to80 === null || universeCount === 0) return null
  const [one, many] = NOUNS[groupBy]
  const noun = universeCount === 1 ? one : many
  const verb = to80 === 1 ? 'makes' : 'make'
  const of = within ? `the spending in ${within}` : 'spending'
  return `${to80} of ${universeCount} ${noun} ${verb} 80% of ${of}`
}

/** A percentage cut to tenths toward zero. The epsilon keeps a figure that is
 *  exactly on a tenth — 0.57 × 100 is 56.99999… — on it. */
function tenths(pct: number): string {
  const nudged = pct + (pct >= 0 ? 1e-7 : -1e-7)
  return `${(Math.trunc(nudged * 10) / 10).toFixed(1)}%`
}

/**
 * The Share and Running share columns, printed by one rule: tenths, cut
 * rather than rounded.
 *
 * Cut, because the running share is the column the 80% mark reads, and a row
 * rounded up to it contradicts the mark: 79.96% printed "80.0%" on the row
 * above the line that says 80% is reached, and 99.96% printed "100.0%" with
 * lines still to come. The same rule on both columns, because the first row's
 * share IS its running share: rounding one and cutting the other printed
 * "24%" beside "23%" on the same row.
 *
 * A positive share too small to reach a tenth reads "<0.1%" — a run of "0.0%"
 * reads as lines that spent nothing — and there is a dash where there is no
 * positive total to be a share of.
 */
export function shareLabel(share: number | null): string {
  if (share === null) return '—'
  if (share > 0 && share < 0.1) return '<0.1%'
  return tenths(share)
}

export function runningLabel(share: number | null): string {
  return share === null ? '—' : tenths(share)
}

/** The table's rows for export, as they read on screen. */
export function exportRows(table: RankedTable) {
  return table.rows.map(({ line, share, cumulative }) => ({
    name: line.name,
    group: line.groupName ?? '',
    spent: line.total,
    share_pct: share,
    cumulative_pct: cumulative,
  }))
}
