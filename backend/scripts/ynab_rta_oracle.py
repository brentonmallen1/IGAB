"""What YNAB's own numbers say Ready to Assign should be, from an export zip.

    just ynab-oracle "~/Downloads/YNAB Export.zip" [--month 2026-08] \\
        [--skip "Old Account"]... [--credit-card "Visa"]... [--categories]

No database, no `.env`: this reads the zip the way the importer does and
applies `igab.integrations.ynab.oracle` to it. Run it on a fresh export next
to the figure YNAB shows on screen; if the two agree, the oracle is right and
any gap after importing is IGAB's to explain — the parity line in the import
summary then names it.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from igab.domain.dates import month_start
from igab.integrations.ynab.oracle import export_consistency, ynab_rta
from igab.integrations.ynab.parser import YNABParser


def _money(value) -> str:
    return f"{value:,.2f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("zip", type=Path)
    ap.add_argument("--month", help="YYYY-MM; defaults to the plan's final month")
    ap.add_argument("--skip", action="append", default=[], help="account left out of the import")
    ap.add_argument(
        "--credit-card", action="append", default=[], help="account that is a credit card"
    )
    ap.add_argument(
        "--tracking", action="append", default=[], help="account that is off budget (tracking)"
    )
    ap.add_argument("--categories", action="store_true", help="print YNAB's Available per category")
    args = ap.parse_args(argv)

    parser = YNABParser()
    budget = parser.parse_zip(args.zip)
    if args.month:
        year, month = (int(x) for x in args.month.split("-"))
        month_date = date(year, month, 1)
    elif budget.plan_rows:
        month_date = max(r.month for r in budget.plan_rows)
    else:
        month_date = month_start(date.today())

    kept = {t.account_name for t in budget.transactions} - set(args.skip)
    report = ynab_rta(
        budget,
        month_date,
        accounts=kept,
        credit_card_accounts=set(args.credit_card),
        tracking_accounts=set(args.tracking),
    )

    print(f"Month                         {month_date:%b %Y}")
    print(f"Inflow to Ready to Assign     {_money(report.inflow)}")
    print(f"Assigned (all months)         {_money(report.assigned)}")
    print(f"  of which card-payment reserves {_money(report.credit_card_payment_assigned)}")
    print(f"Cash overspending written off {_money(report.cash_overspending_written_off)}")
    print(f"YNAB Ready to Assign          {_money(report.rta)}")
    print()
    print(f"Credit-card balances          {_money(report.card_balances)}")
    print(f"Card-payment reserves (avail) {_money(report.ccp_available)}")
    print(f"Uncovered card debt, reset    {_money(report.uncovered_card_debt)}")
    print(f"Uncategorized rows, on budget {_money(report.uncategorized_net)}")
    print(f"Expected IGAB Ready to Assign {_money(report.expected_igab)}")
    print()
    consistency = export_consistency(budget)
    if consistency.self_consistent:
        print("Export agrees with itself.")
    else:
        # Said first among the closing lines, because everything above is
        # read out of a file that contradicts itself.
        print("EXPORT DOES NOT AGREE WITH ITSELF — figures above describe the file:")
    print(
        f"  plan rows breaking YNAB's own running balance  "
        f"{consistency.carryover_rows_violating:,} of {consistency.carryover_rows_checked:,} "
        f"({consistency.carryover_violation_rate:.1%})"
    )
    print(
        f"  Activity cells disagreeing with the register   "
        f"{consistency.activity_cells_disagreeing:,} of {consistency.activity_cells_checked:,} "
        f"({consistency.activity_disagreement_rate:.1%})"
    )
    print()
    print(f"Accounts in scope: {len(kept)}; parse errors: {len(budget.errors)}")
    for message in budget.errors[:5]:
        print(f"  {message}")
    if args.categories:
        print()
        for (group, category), available in sorted(report.available.items()):
            print(f"  {group} / {category}: {_money(available)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
