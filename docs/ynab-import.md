# Importing from YNAB

Export your budget from YNAB (Budget → Export budget), then import the zip
from the budget selector. The preview reads the file and shows every account
with a suggested type; nothing is written until you confirm.

## Your budget starts where YNAB left off

The import **anchors**: every category's Available and every card's payment
reserve open at YNAB's own figures at the export's last complete month (the
*anchor*). Ready to Assign then matches YNAB at the handoff by construction.

- **All history still imports.** The register, account balances, and every
  report cover your full YNAB history.
- **Envelope math starts at the anchor.** Months before it live in the
  register and reports; the budget page's month navigation stops at the
  anchor with a note. IGAB and YNAB apply some rules differently month to
  month — most visibly around credit cards — and re-deriving years of history
  under different rules produces figures that argue with the ones you trust.
  The anchor sidesteps the argument: YNAB's displayed position is adopted as
  the opening statement, and IGAB's rules apply from there forward.
- **Card reserves carry over.** A card's Ready to pay opens at the CCP
  Available YNAB shipped, and debt with nothing set aside behind it shows as
  Uncovered. The card's month-by-month view labels the seam.
- **A register-only export imports unanchored** (there is no plan to read a
  position from); envelope history is then re-derived from transactions.

## After the import

The review dialog compares the imported budget against the export's own
figures and explains any difference. Two habits make the handoff smooth:

- **Keep YNAB around until you're confident.** Run both for a pay cycle or
  two; the parity check in the import review is the scorecard. A fresh
  export can always be re-imported as a new budget.
- **Old imports don't change.** A budget imported before anchoring existed
  keeps its full re-derived history. To adopt the anchor, re-import a fresh
  export as a new budget.
