# IGAB — I've Got A Budget

**Self-hosted envelope budgeting for your household. Your money, your rules, your hardware.**

IGAB is a YNAB-style zero-based budgeting app you run yourself. Give every
dollar a job, sync transactions straight from your bank, reconcile against
statements, and understand where your money actually goes — without a
subscription, and without your financial history living on someone else's
servers.

Built for a small household (1–2 people) that budgets daily or weekly and
wants a tool that is **steady, clear, and trustworthy** — not a fintech
product trying to impress you.

![Python 3.13](https://img.shields.io/badge/python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688)
![React 19](https://img.shields.io/badge/React-19-61dafb)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791)
![Docker Compose](https://img.shields.io/badge/deploy-Docker%20Compose-2496ED)

---

## Why IGAB?

- **Zero-based envelope budgeting** — the proven YNAB method: assign every
  dollar to a category, spend from envelopes, roll with the punches when you
  overspend.
- **Truly yours** — single-household, self-hosted, PostgreSQL-backed. No
  subscription fees, no data mining, no sunset announcements.
- **Bank sync without the middleman drama** — connects to your accounts via
  [SimpleFIN](https://www.simplefin.org/), with smart transaction
  deduplication and a review queue for anything ambiguous.
- **A real escape hatch from YNAB** — import your full YNAB export (accounts,
  categories, transactions, budget history) and run both in parallel until
  you trust the numbers.
- **Financial correctness taken seriously** — a built-in data integrity
  suite verifies money conservation and transfer/split invariants against
  your live budget, and the money-math core is covered by 500+ backend tests.

## Features

### Budgeting
- Monthly budget grid with category groups, targets, and available balances
- Move money between categories in place — cover overspending in two clicks
- Auto-assign and quick-budget helpers for funding categories
- Custom saved budget views (filter and arrange the grid the way you think)

### Accounts & Transactions
- On-budget and tracking accounts: checking, savings, credit cards, loans
- Full transaction editor: splits, transfers, memos, flags, file attachments
- Bulk actions — categorize, approve, or clean up many transactions at once
- Payee management with merge tooling and fuzzy duplicate detection
- Scheduled/recurring transactions
- Statement reconciliation with adjustment handling

### Bank Sync & Import
- **SimpleFIN sync** — link multiple banks; encrypted token storage,
  similarity-scored deduplication (payee, date, amount), and a review queue
  for uncertain matches
- **YNAB import** — full-budget import from a YNAB export ZIP with a preview
  and account-type mapping step
- **CSV import** — per-account bank CSV import with configurable parsing
  (including EU decimal formats) and hash-based dedup

### Reports
Fourteen reports across six groups, all with date-range and
category/payee/account filtering:

| Group | Reports |
| --- | --- |
| Overview | Spending, income, net change, ready-to-assign dashboard |
| Financial State | Net worth, account composition, burn rate |
| Cash Flow | Sankey money-flow diagram, income vs. expense, cash-flow variance |
| Budget | Budget vs. actual, variance, volatility |
| Spending | Pareto breakdown, treemap, seasonality heatmap, payee analysis |
| Insights | Day-of-week patterns, event timeline |

### Mobile & PWA
- **Installable app** — add IGAB to your phone's home screen (manifest +
  service worker); the app shell is precached for instant launches, new
  versions arrive via an in-app update prompt, and an explicit banner appears
  if the server is unreachable (data is always live — never stale from cache)
- **Phone-first UI** — bottom tab navigation, bottom-sheet interactions,
  card layouts for the budget and transaction lists, long-press multi-select
- **Quick-add** — the center ＋ opens amount-first entry built for the
  checkout line: payee memory prefills the category, the account sticks
  between entries, "save & add another" chains purchases
- **Receipt camera** — snap a photo (or pick from the library) while adding a
  transaction; images are converted server-side to WebP with thumbnails, HEIC
  from iPhones included
- **Nearby payees** *(opt-in, per device)* — with location enabled, quick-add
  suggests payees you've used near where you're standing; coordinates stay on
  your server and never touch budget math

### Comfort & Polish
- **9 built-in themes** — dark, light, Gruvbox (dark/light), Catppuccin
  (Mocha/Latte), Rosé Pine (+ Moon), and Nord — implemented with CSS custom
  properties throughout
- Information-dense, keyboard-friendly UI designed to stay calm: color is
  reserved for state that matters (overspent, funded, needs attention)
- Optional **local AI assist** via [Ollama](https://ollama.com/) for payee
  normalization and category suggestions — runs on your hardware like
  everything else, and entirely optional

### Operations Built In
- Automated **daily database backups** with retention pruning (production
  profile), plus one-command manual backup and restore
- **Data integrity checker** in Settings (and via API) that audits your
  budget's invariants and points at the offending transactions
- Single-command Docker Compose deployment with an nginx production profile

## Quick Start

Requirements: Docker with Compose, and [`just`](https://github.com/casey/just).

```sh
git clone <this-repo> igab && cd igab
just init          # copies .env.example → .env
$EDITOR .env       # set DB credentials, SECRET_KEY, admin login, ports
just dev           # start the full stack (db, api, frontend) with live reload
just migrate       # run database migrations
```

Then open the frontend (the port you set in `.env`) and log in with the
`ADMIN_EMAIL` / `ADMIN_PASSWORD` you configured — the admin user is created
automatically on first run.

For a production-style deployment, use the compose production profile
(`just prod`): nginx serves the built frontend with proper caching, proxies
`/api` to the backend, and the daily `db-backup` service runs alongside.

### Install on your phone (PWA)

IGAB is an installable web app: add it to your home screen and it opens
full-screen with its own icon, no browser chrome. Install requires the app to
be served over **HTTPS** (service workers and geolocation need a secure
context; `localhost` is exempt for testing). Two good ways to get there:

**Option A — Tailscale (no ports exposed, automatic certs):**

```sh
just prod                                            # nginx on ${NGINX_PORT:-8080}
tailscale serve --bg https:443 http://localhost:8080 # fronts it with HTTPS on your tailnet
```

Open `https://<machine>.<tailnet>.ts.net` on your phone (with Tailscale
installed) and use *Add to Home Screen* (iOS Safari share menu) or *Install
app* (Android Chrome menu).

**Option B — HTTPS reverse proxy:** point your existing proxy
(Caddy/Traefik/Nginx Proxy Manager/SWAG) at `http://<host>:${NGINX_PORT}`
with a real certificate, then install from that domain.

The app is network-required by design — it caches its own shell for instant
launches, but your data always comes live from the server. When the server is
unreachable you get an explicit banner, not stale numbers. New versions show
an in-app "Update" prompt.

### Configuration

All configuration lives in `.env` (see `.env.example` for the full list):

| Area | Keys |
| --- | --- |
| Database | `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT`, `DATABASE_URL` |
| Auth | `SECRET_KEY`, token lifetimes, `ADMIN_EMAIL`, `ADMIN_PASSWORD` |
| Ports | `API_PORT`, `FRONTEND_PORT`, `NGINX_PORT` |
| Bank sync | `SIMPLEFIN_ENCRYPTION_KEY` (Fernet key for access tokens) |
| AI (optional) | `OLLAMA_HOST`, `OLLAMA_MODEL` |
| Email (optional) | `SMTP_*` |

## Migrating from YNAB

The recommended cutover procedure — deliberate on purpose, because it's your
money:

1. Fresh database → import your YNAB export → link SimpleFIN and sync twice
   (the second sync must report `imported: 0`).
2. Run the integrity check — must be all green.
3. Parallel-run one full statement cycle per account (~2–4 weeks): budget in
   YNAB as usual, let IGAB sync daily, reconcile each statement in **both**.
4. Switch when every account has reconciled cleanly against the bank twice in
   a row in IGAB and a backup restore has been exercised once. Archive the
   final YNAB export.

## Operations

### Backups

Financial data needs a backup story before it needs anything else.

- `just backup` — writes `backups/igab-<timestamp>.dump` (pg_dump custom
  format) from the running `db` container.
- `just restore <file>` — **drops and replaces** the current database from a
  dump. Exercise this once before trusting it; a backup you've never restored
  is a hope, not a backup.
- In the production compose profile, the `db-backup` service dumps daily into
  `${BACKUP_DIR:-./backups}` and prunes files older than
  `${BACKUP_KEEP_DAYS:-30}`. Point `BACKUP_DIR` at a disk that is not the
  database's disk.

### Data integrity

Settings → Data Integrity runs the live invariant suite against your budget
(also `GET /api/v1/budgets/{id}/integrity`): money conservation between
account balances and category activity, split and transfer integrity,
orphaned review matches, stale bank authorizations. Run it after imports and
before reconciling if anything ever looks off — drift shows up here first,
with the offending transaction ids.

### Fresh install / reset

```sh
docker compose down -v      # or: drop the database
docker compose up -d db
just migrate                # single squashed migration (0001)
```

## Architecture

| Layer | Technology |
| --- | --- |
| Backend | Python 3.13, FastAPI (fully async), SQLAlchemy + asyncpg, Alembic |
| Frontend | React 19, TypeScript, Vite, Zustand, React Query, recharts |
| Database | PostgreSQL 16 |
| Deployment | Docker Compose (nginx + daily backups in the production profile) |

## Roadmap

- Report drill-downs (chart element → filtered transaction list) and
  per-report export
- Deeper mobile polish (chart touch interactions, per-page refinements)
- Advanced loan accounts (amortization, interest, extra-payment simulation)
- Command palette, bill reminders, subscription tracking
- YNAB-compatible export — an exit strategy from IGAB itself, because a tool
  you can leave is a tool you can trust

## Contributing & Development

Development setup, conventions, quality gates, and testing requirements are
documented in [CONTRIBUTING.md](CONTRIBUTING.md). Run `just` to see every
available command.
