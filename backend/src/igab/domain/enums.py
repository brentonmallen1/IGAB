from enum import StrEnum
from typing import Literal

# Account types are no longer a static enum: each budget carries an
# account_types registry row per type (built-ins seeded from
# igab.domain.account_types, plus user-defined custom types).


class ClearedStatus(StrEnum):
    PENDING = "pending"
    UNCLEARED = "uncleared"
    CLEARED = "cleared"
    RECONCILED = "reconciled"


class UserClearedStatus(StrEnum):
    """Cleared values a user may set directly. `pending` belongs to bank sync;
    `reconciled` is granted only by the reconciliation flow (and removed only
    via the explicit unreconcile action)."""

    UNCLEARED = "uncleared"
    CLEARED = "cleared"


class TargetType(StrEnum):
    """Three shapes of goal. `needed_for_spending` used to be a fourth: undated
    it was arithmetically `monthly_funding`, dated it was `savings_balance`
    with a date, and the editor's copy could not say how it differed. The
    migration mapped every row to the type it already was
    (domain/targets.py `normalize_legacy_target`)."""

    #: Assign this much every month.
    MONTHLY_FUNDING = "monthly_funding"
    #: Assign this much every week — this month's duty is the amount times
    #: the number of that weekday in the month (4 or 5), so `weekday` is
    #: required. It used to be treated as a flat monthly figure.
    WEEKLY_FUNDING = "weekly_funding"
    #: Keep this much available; an optional `target_date` paces the ask.
    SAVINGS_BALANCE = "savings_balance"


#: The answers the budget row's pill can show. A Literal rather than a
#: StrEnum because it is a computed verdict that crosses the API to the client,
#: not a stored column — TargetService produces it and the response schema
#: declares it, and this is what stops the two drifting apart.
#:
#: "pending" is "underfunded, but its funding day has not come" — the budget's
#: `funding_day` or the target's own `check_after_day`. Fill Underfunded still
#: fills a pending target; only the nag is held back.
TargetStatus = Literal["funded", "underfunded", "overfunded", "pending"]


class ScheduleFrequency(StrEnum):
    #: A single dated occurrence — what a future-dated YNAB row becomes at
    #: import, and what "remind me about this one bill" means. Completes
    #: (soft-deletes) once entered or skipped; see domain/schedule.py.
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    TWICE_MONTHLY = "twice_monthly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class ImportSource(StrEnum):
    SIMPLEFIN = "simplefin"
    CSV = "csv"
    YNAB = "ynab"
    MANUAL = "manual"


class OverspendingHandling(StrEnum):
    ALLOW = "allow"
    WARN = "warn"


class AccountClassification(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"


class SkipReason(StrEnum):
    """Why one bank feed row produced no change.

    A single `skipped` counter used to stand for all six of these, and that
    is how an account went nine days importing nothing while reporting
    success: 500-odd rows belonging to no linked account read exactly like
    500-odd rows that were already filed. "Skipped" is only ever actionable
    when it says which of these it means.
    """

    #: The row belongs to a bank account no synced budget account claims.
    #: Ordinary for accounts the user never linked — and the signature of a
    #: re-issued account id when it is the *only* thing an account produces.
    FOREIGN_ACCOUNT = "foreign_account"
    #: The feed's account id matched a target set entry but no account object.
    ACCOUNT_NOT_FOUND = "account_not_found"
    #: The bank changed a user-entered row's amount, and there is no matching
    #: service configured to ask about it.
    NO_MATCHER = "no_matcher"
    #: The review copy collided with an existing row's bank id.
    REVIEW_IMPORT_DUPLICATE = "review_import_duplicate"
    #: Known id, nothing changed. The benign one: a re-sync of a filed row.
    ALREADY_POSTED = "already_posted"
    #: Writing the row hit the account's unique bank-id index.
    DUPLICATE_SYNC_ID = "duplicate_sync_id"
