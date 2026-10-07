"""How often SimpleFIN may be asked, per connection per day.

What the bridge says: "You are expected to make 24 requests or fewer per
day", and "Requests for all accounts `GET /accounts` have a quota. Requests
for individual accounts have their own quota `GET /accounts?account=...`".
Read one way that is 24 in all; read the other, it is two separate quotas.
IGAB splits its budget 12 + 12 — all-accounts requests on the global bucket,
`account=` requests on the account bucket — so it stays under whichever
reading holds. Which bucket a request draws on is decided by whether it
names one account (`SimpleFINService.sync`), so the request and the counter
cannot disagree.

More requests do not mean fresher data: the bridge refreshes from the bank
about once a day and answers every request in between from that refresh.

Its own module because two layers need the numbers and neither should own
them: the service enforces them and serves them to the client, and the API
schema validates a sync schedule against the global one — a connection
cannot be scheduled to sync more often than it is allowed to. Importing the
service into a schema module to reach a constant would drag the whole sync
engine into request parsing.
"""

GLOBAL_DAILY_LIMIT = 12
ACCOUNT_DAILY_LIMIT = 12
