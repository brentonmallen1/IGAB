"""Whether a transaction may move to a different account.

A row's account is the field three other systems believe they own:

- **the bank feed**, which reported the row in one account and looks for it
  there again (`find_by_sync_id` is account-scoped);
- **reconciliation**, which vouched for a balance in one account — so
  `account_id` is in `RECONCILED_LOCKED_FIELDS` beside amount and date;
- **the transfer pair**, whose legs carry payees naming each other's
  accounts, so moving one leg renames the other's payee.

Only the second was written down before a move was possible at all. This
module is the other two, plus the structural rules — as facts in, message
out, so every branch is a one-line test with no database.

What it does NOT decide, because one implementation each:

- whether the resulting row may keep its category — `leg_may_carry_category`
  in `domain.transfers` answers that, and the service asks it about the
  account the edit *ends* on rather than the one it started on;
- whether a reconciled row may move — `domain.reconciliation` already locks
  `account_id`, and the service's generic locked-field check runs first.
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class MoveRequest:
    """A proposed move, as facts rather than ORM rows.

    `counterpart_account_id` is the far leg's account when this row is a
    linked transfer leg, and None otherwise.
    """

    target_account_id: uuid.UUID
    target_is_closed: bool
    is_split_child: bool
    is_bank_synced: bool
    counterpart_account_id: uuid.UUID | None = None
    retargeting_transfer: bool = False


def refusal_for_move(request: MoveRequest) -> str | None:
    """Why this move must not happen, or None when it may.

    One sentence, addressed to the person who asked for it: every one of
    these is reachable from the editor's account picker, and "400 Bad
    Request" is not an answer about their money.
    """
    if request.is_split_child:
        return (
            "Move the split's parent transaction instead — a split's lines "
            "always live in the same account as the row they belong to"
        )
    if request.is_bank_synced:
        return (
            "This transaction came from a bank feed, which decides which account "
            "it lives in. Moving it would leave the feed free to add it back to "
            "the original account, and you would have it twice. Delete it here "
            "and enter it by hand in the right account instead"
        )
    if request.target_is_closed:
        return "That account is closed — reopen it first if this transaction belongs there"
    if request.retargeting_transfer:
        return (
            "Change the account this transaction is in and the account it "
            "transfers to in separate edits"
        )
    if request.counterpart_account_id is not None and (
        request.counterpart_account_id == request.target_account_id
    ):
        return (
            "This is a transfer to that account, so both sides would end up in it. "
            "Break the transfer first, or send it somewhere else"
        )
    return None
