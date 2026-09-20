import type { Transaction } from '../../types'

/**
 * Whether the register may offer Merge on two selected rows.
 *
 * This is a second implementation of a server rule
 * (`backend/.../domain/merging.py`), and it has to be: the button is drawn
 * before any request is made, and the client holds every field the answer
 * needs. Irreducible duplication, per CLAUDE.md — so the two sides are
 * pinned by `shared/merge_cases.json`, which both suites run, rather than by
 * a comment asking the next reader to keep them in step.
 *
 * The comment was what existed before, and the copies had already drifted:
 * this side knew about accounts, reconciled pairs, splits and transfer legs
 * but not about bank identity, so the register offered Merge on two
 * SimpleFIN rows carrying different bank ids. The server refused every save
 * and the modal swallowed the refusal — a duplicate of a reconciled row
 * could not be merged and nothing said why.
 *
 * Two clauses here are deliberately stricter than the server; see
 * `_deliberate_divergence` in the fixture. Offerability is not survivorship:
 * which row survives stays the server's decision.
 */
export function mayOfferMerge(a: Transaction, b: Transaction): boolean {
  if (a.id === b.id) return false
  // A merge moves one row's money into another; across accounts that is a
  // transfer, not a duplicate.
  if (a.account_id !== b.account_id) return false
  // The statement vouched for both, so neither may be the one that goes.
  if (a.cleared === 'reconciled' && b.cleared === 'reconciled') return false
  // Stricter than the server, on purpose: it would keep the split or the
  // leg and merge the plain row away, but the preview shows two plain rows
  // becoming one and cannot show what happens to a split's lines or a
  // transfer's partner.
  if (a.is_split || b.is_split) return false
  if (a.transfer_id || b.transfer_id) return false
  if (a.parent_transaction_id || b.parent_transaction_id) return false
  // Two bank records with two different ids are two real transactions the
  // bank reported separately — the server has always refused to collapse
  // them, and this is the clause that was missing.
  if (a.sync_id && b.sync_id && a.sync_id !== b.sync_id) return false
  return true
}
