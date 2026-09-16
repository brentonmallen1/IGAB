# Sample Budget

Generate a realistic sample budget before entering your own data (also
available from the budget selector's "Try a Sample Budget"):

```sh
# Make sure the database is running
just dev-db

# Quick demo: 7 accounts, about a year of history
just sample-budget your@email.com "Demo Budget"

# Full household: 18 accounts, 2½ years, thousands of transactions
just sample-budget your@email.com "Big Demo" full
```

The quick demo is a complete budget — categories with targets, seven accounts,
a year of history, scheduled transactions, reconciliations. The full household
adds a mortgage, retirement and HSA accounts, more sinking funds, a
deferred-interest loan, and authentically messy bank-feed payees. Both tiers also
carry the card situations from `card_scenarios.py`, each on its own card.

Every way of setting money aside is on both tiers:

- **Emergency Fund** is tagged *Emergency fund* (counts while it's in the budget) and moves $100 a
  month to **Harborstone Reserve**, an off-budget savings account marked Counts
  toward emergency fund. The fund is the envelope plus the account; the move
  nets to zero in the savings rate.
- **General Savings** is tagged *Savings*, counting while it's in the budget, and takes the month's
  leftovers. It moves $200 a month to **Cascade Point HYSA**, which counts as
  savings but is not part of the fund.
- **Investing** (and Health Savings on the full tier) is *Savings*, counting when it leaves the budget:
  what leaves for the brokerage, the Roth or the HSA counts as saved.
- **Vacation** is a *Long-term expense* sinking fund: its flights and hotel are
  spending when they are paid.
