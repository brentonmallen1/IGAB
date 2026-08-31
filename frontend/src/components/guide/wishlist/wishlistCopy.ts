import type { Wish, WishlistProject } from '../../../api/wishlist'

/** The words. Pure, so the phrasing that carries meaning is pinned. */

interface Fmt {
  formatMoney: (n: number) => string
  formatDate: (s: string) => string
}

export function reachLabel(w: Wish, fmt: Fmt): string {
  if (w.funding.mode === 'none' || !w.reach || w.reach.state === 'unlinked') {
    return 'not linked to an envelope yet — pick where this gets funded'
  }
  switch (w.reach.state) {
    case 'now':
      return 'you can afford this now'
    case 'months': {
      const n = w.reach.months ?? 0
      const when = w.reach.date ? ` (${fmt.formatDate(w.reach.date)})` : ''
      return `about ${n} ${n === 1 ? 'month' : 'months'}${when}`
    }
    case 'no_rate':
      return 'nothing assigned to this envelope lately — no date to give'
  }
}

export function fundingLabel(w: Wish): string {
  if (w.funding.mode === 'none' || !w.funding.category_name) return 'no envelope yet'
  return w.funding.inherited
    ? `from ${w.funding.category_name} (project)`
    : `from ${w.funding.category_name}`
}

export function coolingLabel(w: Wish, fmt: Fmt): string | null {
  if (!w.cooling || !w.cooling_until) return null
  return `cooling off until ${fmt.formatDate(w.cooling_until)}`
}

/** "about 2 weeks further away" / "about 1½ months further away". */
export function impactLabel(months: string | null): string | null {
  if (months === null) return null
  const m = Number(months)
  if (Number.isNaN(m) || m <= 0) return null
  if (m < 0.75) {
    const weeks = Math.max(1, Math.round(m * 4.33))
    return `about ${weeks} ${weeks === 1 ? 'week' : 'weeks'} further away`
  }
  const half = Math.round(m * 2) / 2
  const text = half % 1 === 0 ? `${half}` : `${Math.floor(half)}½`
  return `about ${text} ${half === 1 ? 'month' : 'months'} further away`
}

export function stillWantedLine(still: {
  count: number
  of: number
  months: number
}): string | null {
  if (still.of === 0) return null
  return `Added over ${still.months} months ago and still wanted: ${still.count} of ${still.of}`
}

export function projectLine(p: WishlistProject, fmt: Fmt): string {
  const s = p.summary
  if (s.state === 'empty') return 'nothing on it yet'
  if (s.complete) return 'complete'
  const parts = [
    `${s.affordable_now} of ${s.open_count} affordable now`,
    fmt.formatMoney(Number(s.total_cost)),
  ]
  if (s.funded_by)
    parts.push(s.state === 'now' ? 'all affordable now' : `all by ${fmt.formatDate(s.funded_by)}`)
  else if (s.state === 'unlinked') parts.push('no envelope yet')
  return parts.join(' · ')
}

/**
 * The note on spending for fun. It began as the source flowchart's aside on
 * entertainment expenses and lived on the roadmap; it belongs here, where
 * wants are actually kept, and speaks about them rather than about the roadmap.
 */
export const FUN_NOTE = {
  title: 'A note on spending for fun',
  paragraphs: [
    'Discretionary spending is not a moral failing, and a wishlist is not an argument for having no fun. Money you plan to enjoy is doing its job as much as money you save.',
    'The one honest caveat: while high-interest debt is outstanding — and arguably while moderate-interest debt is too — money spent on wants is money borrowed at that rate. That is the whole tradeoff, and it is yours to make.',
    'This list exists to make the tradeoff visible, not to win it. A want that sits through its cooling-off period, with an envelope filling for it, and is still wanted was never an impulse.',
  ],
}
