# Connecting an assistant (MCP)

IGAB exposes a **read-only** MCP endpoint so an assistant can answer questions
about a budget — what a category has left, what a month came to, where the
money went — without you pasting a screenshot.

It is deliberately narrow:

- **Read-only.** There is no tool that writes. Nothing an assistant does here
  can change a transaction, an assignment or an account.
- **Scoped to the budgets you name.** A key reaches those and nothing else,
  even if you have others.
- **Its own credential.** Not your session. Your sign-in token lasts 30
  minutes and the refresh token behind it can do everything you can do; a key
  is separate, revocable on its own, and never signs you out.
- **Vendor-agnostic.** It is a standard MCP server over HTTP with a bearer
  token, so anything that speaks MCP works — Claude Code, Claude Desktop, or
  an MCP client in front of a local model.

## Make a key

Settings → **Assistant Access** → **New key**. Name it after where it will
live ("Claude on the laptop"), tick the budgets it may read, and copy the key
when it is shown.

**It is shown once.** The server stores only a hash, the same way it does for
a password. If you lose it, revoke that key and make another.

## Connect Claude Code

```
claude mcp add --transport http igab https://<your-igab>/api/v1/mcp \
  --header "Authorization: Bearer igab_..."
```

## Connect anything else

Point the client at:

```
URL:     https://<your-igab>/api/v1/mcp
Header:  Authorization: Bearer igab_...
```

That is the whole contract. A client that can set a header can use it.

## What it can answer

The tools are the ones the app's own assistant already has, so an answer here
agrees with the app by construction — it is the same code, not a second
implementation that could drift.

Budget month summaries, category balances and history, account balances,
transaction search, spending by category, budget vs actual, income vs
expense, savings rate, payee analysis, large transactions, and the Guide's
financial-health checkup.

If a key covers more than one budget, the tools take a `budget` argument and
a `list_budgets` tool says which are available. With a single-budget key the
assistant never has to ask.

## Revoking

Settings → **Assistant Access** → **Revoke**. It stops working immediately.
Revoked keys stay in the list so a key you find in a config file later is
still identifiable.

## A note on exposure

The endpoint is only as reachable as your IGAB install. If IGAB is behind
Tailscale or a VPN, so is this. If you publish IGAB to the internet, this is
published too — and then the key is the only thing between a stranger and a
read of your budget. Treat it like a password.
