# Sample Budget

Generate a realistic sample budget before entering your own data (also
available from the budget selector's "Try a Sample Budget"):

```sh
# Make sure the database is running
just dev-db

# Quick demo: 5 accounts, about a year of history
just sample-budget your@email.com "Demo Budget"

# Full household: 16 accounts, 2½ years, thousands of transactions
just sample-budget your@email.com "Big Demo" full
```

The quick demo is a complete budget — categories with targets, five accounts,
a year of history, scheduled transactions, reconciliations. The full household
adds a mortgage, retirement and HSA accounts, sinking funds, a deferred-interest
loan, and authentically messy bank-feed payees.
