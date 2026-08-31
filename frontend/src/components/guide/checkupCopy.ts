import { findStage, TOOL_IDS, type StageId, type ToolId } from '../../content/roadmap'
import { GLOSSARY_IDS, type GlossaryId } from '../../content/glossary'
import type { CheckupFinding, CheckupMetric, FindingKind } from '../../api/guide'

/**
 * What each checkup figure means and what it helps you decide.
 *
 * Content, not logic — the server serves the numbers and the client explains
 * them, the way the roadmap's prose lives here and its facts do not. Every
 * step, calculator and glossary term named below is checked against the
 * content it points at, so a renamed stage cannot strand an explanation.
 */
export interface CheckupExplainer {
  /** What the figure is, in one or two sentences. */
  what: string
  /** Why the roadmap cares. */
  why: string
  /** The decisions it informs — shown beside the figure, not hidden. */
  decide: string[]
  /** The roadmap step to go to. A fired finding's own step takes precedence. */
  stage?: StageId
  tool?: ToolId
  glossary?: GlossaryId[]
}

export const METRIC_KEYS = [
  'emergency_fund',
  'essential_expenses',
  'high_interest_debt',
  'moderate_interest_debt',
  'retirement_contributions',
  'chronic_overspend',
  'categories_funded',
  'data_gaps',
] as const
export type MetricKey = (typeof METRIC_KEYS)[number]

export const CHECKUP_COPY: Record<MetricKey, CheckupExplainer> = {
  emergency_fund: {
    what: 'How many months of essential spending your emergency fund would cover: the money set aside for genuine surprises, divided by what a lean month costs you. Until there is an essentials figure it is shown as money against the starter amount instead — $1,000 or one month of essentials, whichever is larger.',
    why: 'The roadmap builds it in two passes — a small starter cushion before anything else, then three to six months once expensive debt is cleared. It is what keeps one bad month from becoming new debt.',
    decide: [
      'Whether to keep paying extra on debt, or pause and rebuild the cushion first',
      'How much to set aside each month and when it will be enough — the sizer works it through',
      'What counts: tag what you could not do without as Essential, and point the roadmap at the right envelope if it guessed wrong',
    ],
    stage: 'full-emergency-fund',
    tool: 'emergency-fund',
    glossary: ['emergency-fund', 'essential-expenses'],
  },
  essential_expenses: {
    what: 'What a lean month costs: your spending on the things you could not do without, averaged over the last 90 days. It is the yardstick the emergency fund is measured against — three months of this is the target.',
    why: 'An emergency fund sized against everything you spend is bigger than it needs to be; one sized against essentials is what would actually carry you through a bad month. Until something is tagged Essential this falls back to all your spending, which overstates a lean month.',
    decide: [
      'Tag what you could not do without — rent, groceries, utilities, minimum payments — as Essential, and this narrows to those',
      'Point the roadmap at specific categories if the tag is not the right shape',
      'How big the emergency fund should be — the sizer works it through against this figure',
    ],
    stage: 'foundation',
    tool: 'emergency-fund',
    glossary: ['essential-expenses'],
  },
  high_interest_debt: {
    what: 'What you owe on debts at 10% APR or higher — cards, store financing, personal loans. Only debts with a rate on record are counted; any without one are named under Data gaps.',
    why: 'Above about 10%, paying the debt down beats almost anything else you could do with the money, so the roadmap clears it before growing the emergency fund or saving for retirement beyond an employer match.',
    decide: [
      'Which debt to attack first and with how much — the payoff planner compares avalanche and snowball on these debts',
      'Whether extra money belongs here rather than in savings',
      'Whether a debt is missing its rate — add it on the liability and it is counted',
    ],
    stage: 'high-interest-debt',
    tool: 'payoff-plan',
    glossary: ['apr', 'high-interest-debt', 'avalanche', 'snowball'],
  },
  moderate_interest_debt: {
    what: 'Debts between about 4% and 10% APR — a car loan, a student loan. A mortgage is left out, as the roadmap leaves it out.',
    why: 'In this band, paying down and investing instead are both defensible. The roadmap puts it after the full emergency fund and the employer match, and before saving more for retirement.',
    decide: [
      'Whether to pay these down or put the extra into savings at a rate you can actually get — the pay-down-or-save calculator answers with the break-even rate',
      'The order to clear them in',
    ],
    stage: 'moderate-interest-debt',
    tool: 'pay-vs-save',
    glossary: ['apr', 'amortization'],
  },
  retirement_contributions: {
    what: 'Money moved into your retirement accounts over the last year, as a share of your income. Only what IGAB can see: a workplace plan taken from your pay never appears unless you declare it on the roadmap.',
    why: 'The roadmap works up to 15% of income for retirement, after the employer match and once expensive debt is gone.',
    decide: [
      'Whether contributions have room to grow, and by how much',
      'Which accounts count as retirement — tell the roadmap if it guessed wrong or cannot see them',
      'Whether the employer match is fully taken first',
    ],
    stage: 'retirement-fifteen',
    glossary: ['savings-rate', '401k', 'ira', 'employer-match'],
  },
  chronic_overspend: {
    what: 'Categories that went over budget in at least three of the last six months.',
    why: 'Chronic overspending means the budget does not match how you live: money keeps getting pulled from everything else you funded to cover it, and the plan stops being trustworthy.',
    decide: [
      'Whether the assignment is too low for real life, or the spending needs reining in',
      'Which categories to raise, and what to lower to pay for it',
      'Whether a category should be split or merged',
    ],
    stage: 'foundation',
    glossary: ['zero-based-budgeting', 'to-be-assigned'],
  },
  categories_funded: {
    what: 'Of the categories that carry a target, how many are funded this month — the same pill the budget page shows.',
    why: 'Targets are the plan; this count is how much of it is actually in place this month.',
    decide: [
      'Whether to run Fill Underfunded, and whether there is enough to cover it',
      'Which targets are stale — a goal you no longer hold is one to change, not to keep failing',
    ],
    glossary: ['target', 'sinking-fund'],
  },
  data_gaps: {
    what: 'Things the checkup could not count: debts with no interest rate on record, and figures you told the roadmap about more than a year ago.',
    why: 'A gap is a nudge, not a silence. An unrecorded rate would otherwise let a 26% card drop out of the roadmap’s most important step; a year-old figure may no longer be true.',
    decide: [
      'Add the missing rate on the liability',
      'Confirm or update a self-reported amount on the roadmap step that uses it',
    ],
    glossary: ['apr'],
  },
}

/** Explainer for a served metric, or nothing for a key this build does not know. */
export function explainerFor(key: string): CheckupExplainer | undefined {
  return (CHECKUP_COPY as Record<string, CheckupExplainer>)[key]
}

export type MetricStatus = 'danger' | 'warn' | 'good' | 'neutral' | 'unknown'

export type FindingTone = 'warn' | 'danger'

/** How loudly a finding speaks. Presentational — the server ranks findings,
 *  the client colours them. Amber is the checkup's voice; red is kept for the
 *  one case that is not "worth a look" but "nothing there yet". */
export const FINDING_TONE: Record<Exclude<FindingKind, 'stale_external'>, FindingTone> = {
  high_interest_debt: 'warn',
  ef_not_started: 'danger',
  ef_below_starter: 'warn',
  chronic_overspend: 'warn',
  ef_below_full: 'warn',
  moderate_debt: 'warn',
  retirement_below_target: 'warn',
  unknown_rates: 'warn',
}

export function findingTone(kind: FindingKind): FindingTone {
  return kind === 'stale_external' ? 'warn' : FINDING_TONE[kind]
}

/** The one-word verdict beside the figure. Derived from what is served — a
 *  fired finding wins; otherwise the figure against its target. */
export function metricStatus(
  m: CheckupMetric,
  finding?: CheckupFinding
): { status: MetricStatus; text: string } {
  if (finding) {
    return findingTone(finding.kind) === 'danger'
      ? { status: 'danger', text: 'not started' }
      : { status: 'warn', text: 'worth a look' }
  }
  if (m.value === null) return { status: 'unknown', text: 'not known' }
  const value = Number(m.value)
  const target = m.target === null ? null : Number(m.target)
  if (m.key === 'categories_funded') {
    if (target === null || target === 0) return { status: 'neutral', text: 'no targets set' }
    const short = target - value
    return short <= 0
      ? { status: 'good', text: 'all funded' }
      : { status: 'neutral', text: `${short} underfunded` }
  }
  if (target === 0)
    return value <= 0 ? { status: 'good', text: 'none' } : { status: 'neutral', text: '' }
  if (target !== null)
    return value >= target
      ? { status: 'good', text: 'on target' }
      : { status: 'neutral', text: 'below target' }
  return { status: 'neutral', text: '' }
}

/** 0–1 toward the target where a bar means something; null where it does not
 *  (a debt against zero, a count of overspent categories). */
export function metricProgress(m: CheckupMetric): number | null {
  if (m.value === null || m.target === null) return null
  const target = Number(m.target)
  if (!(target > 0)) return null
  return Math.min(1, Math.max(0, Number(m.value) / target))
}

interface Fmt {
  formatMoney: (n: number) => string
}

export function formatMetricValue(m: CheckupMetric, fmt: Fmt): string {
  if (m.value === null) return '—'
  const n = Number(m.value)
  if (Number.isNaN(n)) return '—'
  switch (m.unit) {
    case 'money':
      return fmt.formatMoney(n)
    case 'months':
      return `${n.toFixed(1)} mo`
    case 'percent':
      return `${n.toFixed(1)}%`
    case 'count':
      return String(Math.round(n))
  }
}

export function formatMetricTarget(
  m: CheckupMetric,
  fmt: Fmt,
  thresholds: { emergency_fund_months?: number; emergency_fund_months_high?: number }
): string | null {
  if (m.target === null) return null
  const t = Number(m.target)
  if (m.key === 'categories_funded') return `of ${Math.round(t)} with targets`
  switch (m.unit) {
    case 'months': {
      const low = thresholds.emergency_fund_months ?? t
      const high = thresholds.emergency_fund_months_high
      return high ? `target ${low}–${high} months` : `target ${low} months`
    }
    case 'percent':
      return `target ${t}%`
    case 'money':
      return t === 0
        ? 'target: none'
        : `target ${fmt.formatMoney(t)}${m.key === 'emergency_fund' ? ' to start' : ''}`
    case 'count':
      return t === 0 ? 'target: none' : `target ${Math.round(t)}`
  }
}

const NUMBER_WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six']

/** The money behind a months figure — "$1,240 of $9,720 — three months of
 *  essentials" — because 0.4 months means nothing until you can see what a
 *  month is worth. Null for a row served without one. */
export function formatMoneyLine(
  m: CheckupMetric,
  fmt: Fmt,
  thresholds: { emergency_fund_months?: number }
): string | null {
  if (m.money_value === null || m.money_target === null) return null
  const value = Number(m.money_value)
  const target = Number(m.money_target)
  if (Number.isNaN(value) || Number.isNaN(target)) return null
  const months = thresholds.emergency_fund_months ?? Number(m.target)
  const word = NUMBER_WORDS[months] ?? String(months)
  return `${fmt.formatMoney(value)} of ${fmt.formatMoney(target)} — ${word} ${months === 1 ? 'month' : 'months'} of essentials`
}

/** Guards the content: run in checkupCopy.test.ts. */
export function checkCopyIntegrity(): string[] {
  const problems: string[] = []
  for (const key of METRIC_KEYS) {
    const c = CHECKUP_COPY[key]
    if (!c.what || !c.why || c.decide.length === 0) problems.push(`${key}: incomplete`)
    if (c.stage && !findStage(c.stage)) problems.push(`${key}: stage ${c.stage}`)
    if (c.tool && !(TOOL_IDS as readonly string[]).includes(c.tool))
      problems.push(`${key}: tool ${c.tool}`)
    for (const g of c.glossary ?? []) {
      if (!(GLOSSARY_IDS as readonly string[]).includes(g)) problems.push(`${key}: glossary ${g}`)
    }
  }
  return problems
}
