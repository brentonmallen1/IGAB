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

Settings → **MCP** → **New key**. Name it after where it will
live ("Claude on the laptop"), tick the budgets it may read, and copy the key
when it is shown.

**It is shown once.** The server stores only a hash, the same way it does for
a password. If you lose it, revoke that key and make another.

## Connect a client

Settings → **MCP** → **How to connect** has a client picker that prints
the right instructions with your own host and, once you have made a key, the
key itself filled in.

### Claude Code

```
claude mcp add --transport http igab https://<your-igab>/api/v1/mcp/ \
  --header "Authorization: Bearer igab_..."
```

### Claude Desktop, or anything else that keeps a config file

Most desktop clients that speak MCP over HTTP — Claude Desktop among them —
take an entry shaped like this in their config:

```json
{
  "mcpServers": {
    "igab": {
      "url": "https://<your-igab>/api/v1/mcp/",
      "headers": { "Authorization": "Bearer igab_..." }
    }
  }
}
```

Not every client's config file uses this exact shape, so check yours if the
above doesn't work — but it's the common one.

### Ollama, ChatGPT, or anything else

Neither of those speaks MCP by itself — Ollama is a model runtime, and
ChatGPT's own connectors are a different protocol. What actually connects is
whatever MCP client sits in front of them: a local-model chat app, an
MCP-aware IDE, a bridge. Whatever it is, its setup form wants these four
things:

```
Transport   Streamable HTTP (one POST per call)
URL         https://<your-igab>/api/v1/mcp/
Header      Authorization: Bearer igab_...
Auth        Static bearer token — no OAuth, no login flow
```

That is the whole contract. A client that can set a header can use it,
regardless of what wrote its UI or which model answers on the other end.

**Mind the trailing slash.** `/api/v1/mcp` answers `307 Temporary Redirect`
to `/api/v1/mcp/`, and only the slashed form answers directly. Clients that
follow redirects never notice; one that does not will fail with nothing in
its error pointing at the cause. Use the slashed URL everywhere.

## Check it works

Before blaming a client's setup screen, prove the endpoint and the key:

```
curl -X POST https://<your-igab>/api/v1/mcp/ \
  -H "Authorization: Bearer igab_..." \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

It answers with the tool list. No `initialize` handshake is needed first —
the server is stateless, so one POST is a complete exchange.

A `401` means the key is wrong, revoked, or missing. A `307` means the
trailing slash is missing. Anything else is the endpoint not being reachable
at all, which is a networking answer, not an MCP one.

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

Settings → **MCP** → **Revoke**. It stops working immediately.
Revoked keys stay in the list so a key you find in a config file later is
still identifiable.

## A note on exposure

The endpoint is only as reachable as your IGAB install. If IGAB is behind
Tailscale or a VPN, so is this. If you publish IGAB to the internet, this is
published too — and then the key is the only thing between a stranger and a
read of your budget. Treat it like a password.
