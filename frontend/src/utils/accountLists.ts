/**
 * Which accounts a surface should show, and the distinction that decides it.
 *
 * Two questions, and they have different answers:
 *
 * - **Which accounts may I choose?** The open ones. Offering a closed account
 *   in a picker invites someone to file a new row into a register they have
 *   put away.
 * - **Which accounts must I be able to name?** All of them. A row already
 *   exists on the account it exists on, and a register or a report window
 *   reaches back past a closing.
 *
 * Conflating the two is what emptied the account column in the all-accounts
 * register: it fetched open accounts, built its id→name map from them, and
 * drew "—" for every row on a closed account — including transfer legs naming
 * a closed counterpart. A YNAB import that closed its dormant accounts on the
 * way in produced a register full of blanks, reported as "when I look in the
 * transaction log, there is no account for that".
 *
 * `openAccounts` was also written inline six times before it lived here, which
 * is the usual reason a rule ends up in this directory.
 */

/** The narrow shape each helper needs. Taking this rather than `Account`
 *  lets a caller pass a projection, and lets a test state a case in one line. */
export interface ClosableAccount {
  is_closed: boolean
}

export interface NamedAccount {
  id: string
  name: string
}

/**
 * The accounts a picker may offer.
 *
 * Order is preserved, so anything keyed on position — the register's palette
 * slot per account — keeps the colours it had when this list was the whole
 * fetch.
 */
export function openAccounts<T extends ClosableAccount>(accounts: readonly T[]): T[] {
  return accounts.filter((a) => !a.is_closed)
}

/** The accounts a surface has put away. The complement of `openAccounts`, so
 *  the two cannot drift into overlapping or leaving a row out. */
export function closedAccounts<T extends ClosableAccount>(accounts: readonly T[]): T[] {
  return accounts.filter((a) => a.is_closed)
}

/**
 * id → name, for naming rows that already exist.
 *
 * Pass the UNFILTERED list. A name map built from open accounts alone is the
 * defect above; there is no case where a row should go unnamed because its
 * account is closed.
 */
export function accountNameMap(accounts: readonly NamedAccount[]): Map<string, string> {
  return new Map(accounts.map((a) => [a.id, a.name]))
}
