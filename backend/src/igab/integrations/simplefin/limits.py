"""How often SimpleFIN may be asked, per connection per day.

Its own module because two layers need the number and neither should own it:
the service enforces it, and the API schema validates a sync schedule against
it — a connection cannot be scheduled to sync more often than it is allowed
to. Importing the service into a schema module to reach a constant would drag
the whole sync engine into request parsing.
"""

GLOBAL_DAILY_LIMIT = 12
ACCOUNT_DAILY_LIMIT = 12
