/**
 * What each migration notice on the Tags panel says.
 *
 * The notices are written by migrations (and by a restore that replays one) as
 * Guide-state rows, `GET /tags/notices`; this module is only their copy. Pure,
 * so every key's sentence is a one-line test.
 *
 * Falls back to the key rather than rendering nothing: a notice with no copy
 * is a bug worth seeing.
 */

type Payload = Record<string, unknown>

function count(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`
}

function names(payload: Payload, field: string): string[] {
  const value = payload[field]
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
}

interface DroppedAccount {
  name: string
  reason: string
}

function dropped(payload: Payload): DroppedAccount[] {
  const value = payload.dropped_accounts
  if (!Array.isArray(value)) return []
  return value.filter(
    (v): v is DroppedAccount =>
      typeof v === 'object' &&
      v !== null &&
      typeof v.name === 'string' &&
      typeof v.reason === 'string'
  )
}

/** Why an account the old Guide counted no longer does — migration
 *  e52d44b73edb's `reason`. */
function droppedSentence({ name, reason }: DroppedAccount): string {
  if (reason === 'on_budget') {
    return (
      `${name} used to count, but envelopes already say what an on-budget account’s ` +
      `money is for — tag the envelopes that hold it.`
    )
  }
  return `${name} used to count; mark it only once it counts as savings.`
}

export function noticeText(key: string, payload: Payload): string {
  const removed = Number(payload.payee_tags_removed ?? 0)
  const tags = `${removed} payee tag${removed === 1 ? ' was' : 's were'} removed`
  if (key === 'subscription_tag_moved') {
    return (
      `Subscription is now a category tag. ${tags} — tag the categories your ` +
      `subscriptions are filed to (Streaming, Software…) and the report follows them.`
    )
  }
  if (key === 'payee_tags_retired') {
    return (
      `Tags now apply to categories only. ${tags} — nothing read them, so no ` +
      `figure changes. Tag the categories those payees are filed to and every ` +
      `report that uses tags follows.`
    )
  }
  if (key === 'emergency_fund_chosen') {
    const envelopes = names(payload, 'tagged_categories').length
    const accounts = names(payload, 'flagged_accounts').length
    return [
      `Your emergency fund is now chosen, not guessed. ` +
        `${count(envelopes, 'envelope was', 'envelopes were')} tagged Emergency fund and ` +
        `${count(accounts, 'account', 'accounts')} marked.`,
      ...dropped(payload).map(droppedSentence),
    ].join(' ')
  }
  if (key === 'emergency_fund_not_guessed') {
    return (
      `Your emergency fund used to be guessed from names. Nothing is counted until ` +
      `you choose: tag envelopes Emergency fund, or mark an off-budget savings account.`
    )
  }
  return key
}
