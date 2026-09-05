/**
 * Summaries and diffs for change-log rows — pure, so every branch tests
 * without mounting the page.
 *
 * A snapshot stores bare ids; the server sends a `names` map beside each
 * page (id → display name, deleted entities included) and everything here
 * resolves through it. The map is the single authority on what resolves:
 * any string value it knows becomes a name, so this module never keeps its
 * own list of which fields are references.
 */
import type { Change } from '../../api/changes'
import { parseApiDecimal } from '../../utils/money'

export type Names = Record<string, string>

/** One row of the expanded diff panel. `before`/`after` are display-ready;
 *  null means "no value on that side" (a create has no befores). */
export interface DiffRow {
  label: string
  before: string | null
  after: string | null
}

const MONEY_FIELDS = new Set([
  'amount',
  'entered_amount',
  'bank_amount',
  'assigned',
  'target_amount',
  'balance',
  'value',
  'manual_balance',
  'manual_value',
  'statement_balance',
  'cleared_balance',
  'adjustment_amount',
  'cost',
  'minimum_payment',
  'minimum_payment_floor',
  'planned_extra_payment',
  'original_principal',
])

function money(value: unknown): string {
  const n = parseApiDecimal(String(value))
  return `${n < 0 ? '-' : ''}$${Math.abs(n).toFixed(2)}`
}

function signedMoney(value: unknown): string {
  const n = parseApiDecimal(String(value))
  return `${n < 0 ? '-' : '+'}$${Math.abs(n).toFixed(2)}`
}

export function truncate(text: string, max = 24): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

/** Display form of one snapshot value. Ids the names map knows become
 *  names; unknown ids shorten to a stub rather than a full UUID. */
export function formatFieldValue(field: string, value: unknown, names: Names): string {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value)) {
    if (value.length === 0) return '—'
    return value.map((v) => names[String(v)] ?? truncate(String(v), 9)).join(', ')
  }
  if (typeof value === 'object') return '(document)'
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  const text = String(value)
  const named = names[text]
  if (named) return named
  if (MONEY_FIELDS.has(field)) return money(text)
  if (field === 'interest_rate' || field === 'minimum_payment_percent') return `${text}%`
  if (/^[0-9a-f]{8}-[0-9a-f-]{27,}$/i.test(text)) return `#${text.slice(0, 4)}`
  return text
}

/** "category_id" → "category", "_tag_ids" → "tags", "is_priority" → "pinned"…
 *  mostly mechanical; the few special cases are spellings a person expects. */
export function fieldLabel(field: string): string {
  if (field === '_tag_ids') return 'tags'
  if (field === 'memo') return 'memo'
  return field
    .replace(/^_/, '')
    .replace(/_ids?$/, '')
    .replaceAll('_', ' ')
}

/** Which reference fields say what a row was ABOUT, per entity — the
 *  " · Payee · Account" (or " · Category") tail on the summary line. */
const CONTEXT_FIELDS: Record<string, string[]> = {
  transaction: ['payee_id', 'account_id'],
  scheduled_transaction: ['payee_id', 'account_id'],
  assignment: ['category_id'],
  category_target: ['category_id'],
  liability_snapshot: ['liability_id'],
  asset_value: ['asset_id'],
}

/** Read from after falling back to before, so deletes keep their context. */
function contextSuffix(change: Change, names: Names): string {
  const fields = CONTEXT_FIELDS[change.entity_type]
  if (!fields) return ''
  const snap = { ...(change.before ?? {}), ...(change.after ?? {}) }
  const parts = fields
    .map((field) => names[String(snap[field] ?? '')])
    .filter((name): name is string => Boolean(name))
    .map((name) => truncate(name))
  return parts.length ? ` · ${parts.join(' · ')}` : ''
}

type Snap = Record<string, unknown>

function datedFigure(figure: unknown, snap: Snap): string {
  // Dated balance/value points: the figure and the day it was stated for.
  return figure ? `${money(figure)} on ${snap.date as string}` : ''
}

/** Per-entity figure lines; anything not listed (or listed but empty) falls
 *  through to the name/label fallback in `summarizeSnapshot`. */
const FIGURE_SUMMARY: Record<string, (snap: Snap) => string> = {
  transaction: (s) => (s.amount != null ? signedMoney(s.amount) : ''),
  scheduled_transaction: (s) => (s.amount != null ? signedMoney(s.amount) : ''),
  assignment: (s) => (s.assigned ? `Assigned ${money(s.assigned)}` : ''),
  category_target: (s) => (s.target_amount ? `Goal ${money(s.target_amount)}` : ''),
  liability_snapshot: (s) => datedFigure(s.balance, s),
  asset_value: (s) => datedFigure(s.value, s),
  reconciliation: (s) => (s.statement_balance ? `Statement ${money(s.statement_balance)}` : ''),
}

/** One summarizer for both sides — a create reads `after`, a delete reads
 *  `before`, and the text for a given entity must be the same either way. */
function summarizeSnapshot(change: Change, snap: Snap | null): string {
  if (!snap) return ''
  const figure = FIGURE_SUMMARY[change.entity_type]?.(snap)
  if (figure) return figure
  // Everything else that carries a name (or an account type's label) is
  // summarized by it.
  return ((snap.name ?? snap.label) as string) ?? ''
}

function changedFields(change: Change): string[] {
  const before = change.before ?? {}
  const after = change.after ?? {}
  return Object.keys({ ...before, ...after }).filter((key) => {
    if (key.startsWith('_') && key !== '_tag_ids') return false
    return String(before[key]) !== String(after[key])
  })
}

function summarizeUpdate(change: Change, names: Names): string {
  const after = change.after ?? {}
  const changed = changedFields(change)
  if (changed.length === 0) return ''
  if (changed.length === 1) {
    const field = changed[0]
    if (field === 'approved') return 'Marked approved'
    if (field === 'cleared') return `Cleared: ${after.cleared}`
    if (field === 'amount') return `Amount → ${signedMoney(after.amount)}`
    if (field === 'name') return `Renamed to "${after.name}"`
    if (field === 'assigned') return `Assigned → ${money(after.assigned)}`
    if (field === '_tag_ids') return `Tags → ${formatFieldValue('_tag_ids', after._tag_ids, names)}`
    return `Changed ${fieldLabel(field)}`
  }
  return `Changed ${changed.length} fields`
}

/** The card's one-line summary: the figure or name, then who/where context
 *  (payee · account, or the category) resolved through the names map. */
export function summarizeChange(change: Change, names: Names): string {
  let core = ''
  if (change.action === 'create' || change.action === 'import') {
    core = summarizeSnapshot(change, change.after)
  } else if (change.action === 'delete') {
    core = summarizeSnapshot(change, change.before)
  } else if (change.action === 'update' || change.action === 'approve') {
    core = summarizeUpdate(change, names)
  } else if (change.action === 'merge') {
    core = 'Merged into another'
  }
  // Archive rows carry id-keyed payloads (one archive touches many rows), so
  // the field-diff summarizer would print raw ids; the action label says it.
  if (change.action === 'archive' || change.action === 'unarchive') return ''
  if (!core) return ''
  return `${core}${contextSuffix(change, names)}`
}

/**
 * The expanded panel's rows: what it was before, what it is after.
 *
 * Updates show only the fields that moved; creates and deletes show the
 * whole snapshot on their one side. Reorders and archives return nothing —
 * their payloads are id-keyed bookkeeping, and the action label already
 * says everything a person could read from them.
 */
export function diffRows(change: Change, names: Names): DiffRow[] {
  if (change.action === 'reorder' || change.action === 'archive' || change.action === 'unarchive') {
    return []
  }
  const before = change.before ?? {}
  const after = change.after ?? {}

  if (change.action === 'update' || change.action === 'approve' || change.action === 'merge') {
    return changedFields(change).map((field) => ({
      label: fieldLabel(field),
      before: formatFieldValue(field, before[field], names),
      after: formatFieldValue(field, after[field], names),
    }))
  }

  // create/import read after; delete reads before — one side only.
  const side = change.action === 'delete' ? before : after
  const isDelete = change.action === 'delete'
  return Object.keys(side)
    .filter((key) => !key.startsWith('_') || key === '_tag_ids')
    .filter((key) => side[key] !== null && side[key] !== undefined && side[key] !== '')
    .map((field) => ({
      label: fieldLabel(field),
      before: isDelete ? formatFieldValue(field, side[field], names) : null,
      after: isDelete ? null : formatFieldValue(field, side[field], names),
    }))
}
