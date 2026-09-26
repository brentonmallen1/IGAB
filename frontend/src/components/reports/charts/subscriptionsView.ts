/**
 * Presentation for the Subscriptions report: words for the served facts, the
 * chart's series, and the drill a service opens. Every figure is the
 * server's (`domain/subscriptions.py`) — nothing here decides what a service
 * costs, which cadence it has or whether it has stopped.
 */
import type {
  SubscriptionCategory,
  SubscriptionService,
  SubscriptionsReport,
  SubscriptionsSummary,
} from '../../../types'
import type { DrillDownContext } from '../../../stores/reportStore'
import type { TrendRow } from './spendingTrends'

/** "monthly", "yearly", "every 91 days" — and "monthly?" when one charge was
 *  all there was to go on and the server assumed it. */
export function cadenceLabel(
  s: Pick<SubscriptionService, 'cadence' | 'interval_days' | 'cadence_assumed'>
): string {
  if (s.cadence_assumed) return 'monthly?'
  if (s.cadence === 'monthly') return 'monthly'
  if (s.cadence === 'yearly') return 'yearly'
  return `every ${s.interval_days} days`
}

/** The note beside a service whose Annual is not simply its year's charges. */
export function basisNote(basis: SubscriptionService['basis']): string | null {
  switch (basis) {
    case 'new':
      return 'new · projected'
    case 'price_change':
      return 'new price · projected'
    case 'stopped':
      return 'stopped'
    default:
      return null
  }
}

/** The Active card: "2 of 8", then what it counts. It read "Active 2" — a
 *  count of categories under a label that read as services, with stopped
 *  ones counted. */
export function activeCard(summary: SubscriptionsSummary): { value: string; sub: string } {
  const sub = ['tagged categories charged']
  if (summary.new_this_month > 0) sub.push(`${summary.new_this_month} new this month`)
  return {
    value: `${summary.charged_categories} of ${summary.tagged_categories}`,
    sub: sub.join(' · '),
  }
}

/** Under Annual: whose year it is, and how much of it is projected. */
export function annualSub(summary: SubscriptionsSummary): string {
  const parts = ['last 12 complete months']
  if (summary.projected_services > 0) parts.push(`${summary.projected_services} projected`)
  if (summary.stopped_services > 0) parts.push(`${summary.stopped_services} stopped, left out`)
  return parts.join(' · ')
}

/** Categories as the rows `stackTrends` stacks — ten by name, the rest in
 *  an Other band that makes each bar the month's served total. */
export function subscriptionTrendRows(subscriptions: readonly SubscriptionCategory[]): TrendRow[] {
  return [...subscriptions]
    .sort((a, b) => b.total - a.total)
    .map((s) => ({
      key: s.category_id,
      name: s.category_name,
      group_name: s.group_name,
      monthly: s.monthly_amounts,
      total: s.total,
    }))
}

/**
 * The transactions behind one service: its payee inside its category, refunds
 * included (they are netted into its figures), from the earlier of the chart's
 * first month and the year's start through its last charge — every row either
 * figure on its line was read from.
 *
 * None for a payee-less service: the drill filters by payee id and has no way
 * to say "no payee", and a category-wide list would claim other services' rows.
 */
export function serviceDrill(
  category: Pick<SubscriptionCategory, 'category_id' | 'category_name'>,
  service: Pick<SubscriptionService, 'payee_id' | 'payee_name' | 'last_charge_date'>,
  report: Pick<SubscriptionsReport, 'months' | 'year_start' | 'year_end'>
): DrillDownContext | null {
  if (!service.payee_id) return null
  const chartStart = report.months[0]
  const startDate = chartStart && chartStart < report.year_start ? chartStart : report.year_start
  const endDate =
    service.last_charge_date > report.year_end ? service.last_charge_date : report.year_end
  return {
    kind: 'payee',
    label: `${service.payee_name} · ${category.category_name}`,
    scope: 'leaf',
    categoryIds: [category.category_id],
    payeeIds: [service.payee_id],
    startDate,
    endDate,
  }
}
