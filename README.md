<p align="center">
  <img src="docs/images/envelope-logo.svg" alt="IGAB Logo" width="120" height="120" />
</p>

<h1 align="center">IGAB — I've Got A Budget</h1>

<p align="center">
  <strong>Self-hosted envelope budgeting for your household.<br/>Your money, your rules, your hardware.</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#screenshots">Screenshots</a> •
  <a href="#getting-started">Getting Started</a> •
  <a href="#operations">Operations</a> •
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.13-blue" alt="Python 3.13" />
  <img src="https://img.shields.io/badge/FastAPI-async-009688" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-19-61dafb" alt="React 19" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-336791" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/deploy-Docker%20Compose-2496ED" alt="Docker Compose" />
</p>

---

## Why IGAB?

IGAB is a **zero-based envelope budgeting app** you run yourself. Give every
dollar a job, sync transactions straight from your bank, reconcile against
statements, and understand where your money actually goes — without a
subscription, and without your financial history living on someone else's
servers.

Built for a small household (1–2 people) that budgets daily or weekly and
wants a tool that is **steady, clear, and trustworthy** — not a fintech
product trying to impress you.

### Privacy First

Your financial data is deeply personal. IGAB keeps it that way:

- **Runs entirely on your hardware** — your server, your database, your backups
- **No analytics, no tracking, no telemetry** — zero data leaves your network
- **No subscription fees** — no incentive to monetize your spending patterns
- **Bank sync through SimpleFIN** — you control the connection, encrypted tokens stored locally
- **Optional AI features use local Ollama** — even the AI runs on your machine

### Reports That Actually Help

Twenty reports across six groups give you the visibility you need to plan and understand your finances:

| Group | Reports |
| --- | --- |
| Overview | Spending, income, net change, ready-to-assign dashboard |
| Financial State | Net worth, account composition, liabilities, savings tracker |
| Cash Flow | Income vs. expense, burn rate, Sankey money-flow diagram, cash projection |
| Budget | Budget vs. actual, cumulative variance, volatility |
| Spending | Pareto breakdown, treemap, seasonality heatmap, subscriptions |
| Insights | Anomaly detection, payee analysis, day-of-week patterns (with payday effect), event timeline |

Reports use date-range and category/payee/account filtering where applicable. Monthly reports (net worth, burn rate, etc.) have their own time horizon selectors.

---

## Screenshots

<!-- Screenshots coming soon — budget grid, reports, mobile views -->

*Screenshots of the budget grid, reports, and mobile interface coming soon.*

---

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
- **YNAB import** — switching from YNAB? Import your full export (accounts,
  categories, transactions, budget history) and run both in parallel until
  you trust the numbers
- **CSV import** — per-account bank CSV import with configurable parsing
  (including EU decimal formats) and hash-based dedup

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

---

## Getting Started

### Requirements

- Docker with Compose
- [`just`](https://github.com/casey/just) — command runner

### Quick Start

```sh
git clone <this-repo> igab && cd igab
just init          # copies .env.example → .env
$EDITOR .env       # set DB credentials, SECRET_KEY, admin login, ports
just dev           # start the full stack (db, api, frontend) with live reload
just migrate       # run database migrations
```

Open the frontend (the port you set in `.env`) and log in with the
`ADMIN_EMAIL` / `ADMIN_PASSWORD` you configured — the admin user is created
automatically on first run.

### Explore with a Sample Budget

Want to see how IGAB works before entering your own data? Generate a realistic
sample budget with a year of transactions, categories, and scheduled items:

```sh
# Make sure the database is running
just dev-db

# Generate a sample budget for your admin user
just sample-budget your@email.com "Demo Budget"
```

This creates a complete budget with:
- Realistic category groups and categories with targets
- Multiple accounts (checking, savings, credit cards)
- A year of transaction history with varied payees
- Scheduled recurring transactions
- Sample reconciliations

Perfect for exploring reports, testing the mobile interface, or just getting
a feel for the workflow before importing your real data.

### Production Deployment

IGAB offers two deployment modes:

#### All-in-One (Recommended for Home Servers)

The simplest way to run IGAB — everything in a single container:

```sh
docker run -d \
  --name igab \
  -p 8080:8080 \
  -e SECRET_KEY=$(openssl rand -hex 32) \
  -e ADMIN_PASSWORD=your-password \
  -v ./data:/data \
  ghcr.io/brentonmallen1/igab-aio:latest
```

Or with Docker Compose:

```sh
cp .env.example .env
$EDITOR .env                           # set SECRET_KEY, ADMIN_PASSWORD
docker compose -f docker-compose.aio.yml up -d
```

The AIO image includes PostgreSQL, the API, nginx, and automatic backups. All
data lives in `/data` (database, attachments, backups) — just mount one volume.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `SECRET_KEY` | ✓ | — | JWT signing key (generate with `openssl rand -hex 32`) |
| `ADMIN_PASSWORD` | ✓ | — | Initial admin password |
| `ADMIN_EMAIL` | | `admin@example.com` | Admin login email |
| `WEB_PORT` | | `8080` | Web UI port |
| `TZ` | | `UTC` | Timezone |
| `OLLAMA_HOST` | | — | Ollama server URL for AI features |
| `OLLAMA_MODEL` | | `llama3.2` | Default LLM model |
| `BACKUP_INTERVAL_HOURS` | | `24` | Hours between backups |
| `BACKUP_KEEP_DAYS` | | `30` | Prune backups older than this |
| `BACKUP_AGE_RECIPIENT` | | — | age public key for encrypted backups |
| `SIMPLEFIN_ENCRYPTION_KEY` | | — | Fernet key for bank sync |

#### Multi-Container (Advanced)

For more control, use the multi-container production profile:

```sh
just prod
```

This runs separate containers for PostgreSQL, the API, nginx, and backups.
Useful when you want to use an external database, scale components independently,
or integrate with existing infrastructure.

Tagged releases publish multi-arch (amd64/arm64) images to GHCR —
`ghcr.io/brentonmallen1/igab-api`, `igab-web`, `igab-backup`, and `igab-aio`.

**Unraid:** see [docs/unraid.md](docs/unraid.md) for two supported paths —
the Docker Compose Manager plugin driving this repo's production profile, or
the Community Applications templates in [`unraid/`](unraid/) using the
published images. The `igab-aio` template is the easiest — one container, one
appdata folder.

### Install on Your Phone (PWA)

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

---

## Operations

### Backups

Financial data needs a backup story before it needs anything else.

- **In-app (Settings → Backups):** see the backup service status and every
  existing backup, change the schedule/retention/encryption settings (applied
  by the agent within seconds, no restart), trigger a backup now, and restore
  from a database dump. Restoring asks for confirmation, offers to back up the
  current data first (kept as a `igab-prerestore-*.dump`), then the app goes
  briefly into maintenance mode and restarts itself onto the restored
  database.
- `just backup` — writes `backups/igab-<timestamp>.dump` (pg_dump custom
  format) from the running `db` container.
- `just restore <file>` — **drops and replaces** the current database from a
  dump. Exercise this once before trusting it; a backup you've never restored
  is a hope, not a backup.
- In the production compose profile, the `db-backup` service
  (`scripts/db-backup.sh`) runs every `backup_interval_hours` (default 24)
  and writes two kinds of files into `${BACKUP_DIR:-./backups}`:
  - `igab-<timestamp>.dump` — the database (pg_dump custom format)
  - `igab-attachments-<timestamp>.tar.gz` — receipts/attachments, only when
    their contents changed since the last archive
- Settings precedence: values set in the app (stored in the database) win;
  the `BACKUP_*` env vars are the fallback and the boot-time defaults. If the
  database is unreachable the agent falls back to env values, so backups keep
  running even when the app can't.
- Retention: files older than `backup_keep_days` (default 30) are pruned,
  but the newest `backup_keep_min` (default 7) of each kind are always kept —
  a silent stretch of failed backups can't delete your last good ones. Writes
  are atomic (temp file + rename), a failed dump skips pruning entirely, and
  a failed cycle retries after 15 minutes instead of waiting a full interval.
- **Encryption (optional):** set the encryption key in Settings → Backups (or
  `BACKUP_AGE_RECIPIENT`) to an [age](https://age-encryption.org) public key
  and both file kinds are written as `.age`-encrypted. Generate a keypair with
  `age-keygen` and keep the private key somewhere that isn't this server.
  Because the server deliberately has no private key, encrypted backups (and
  attachment archives) can't be restored from the app — restore with
  `BACKUP_AGE_KEY_FILE=<identity file> just restore <file>.dump.age`;
  attachments:
  `age -d -i <identity file> <file>.tar.gz.age | tar -xz -C data/attachments`.
- Point `BACKUP_DIR` at a disk that is not the database's disk. There is no
  database/field-level encryption at rest by design — the server needs
  plaintext to run queries; use host disk encryption (e.g. LUKS) if stolen
  disks are in your threat model.

### Update Notifications

Settings → Updates has an opt-in check against this repo's GitHub releases —
**off by default**, and nothing is sent anywhere until you enable it. When a
newer tagged release exists, a small dot appears next to Settings in the
sidebar and the Settings page links to the release notes. Dev builds
(`APP_VERSION=dev`, i.e. anything not built from a version tag) never nag.

### Data Integrity

Settings → Data Integrity runs the live invariant suite against your budget
(also `GET /api/v1/budgets/{id}/integrity`): money conservation between
account balances and category activity, split and transfer integrity,
orphaned review matches, stale bank authorizations. Run it after imports and
before reconciling if anything ever looks off — drift shows up here first,
with the offending transaction ids.

### Fresh Install / Reset

```sh
docker compose down -v      # or: drop the database
docker compose up -d db
just migrate                # single squashed migration (0001)
```

---

## Architecture

| Layer | Technology |
| --- | --- |
| Backend | Python 3.13, FastAPI (fully async), SQLAlchemy + asyncpg, Alembic |
| Frontend | React 19, TypeScript, Vite, Zustand, React Query, recharts |
| Database | PostgreSQL 16 |
| Deployment | Docker Compose (nginx + daily backups in the production profile) |

---

## Roadmap

- Deeper mobile polish (chart touch interactions, per-page refinements)
- Advanced loan accounts (amortization, interest, extra-payment simulation)
- Command palette, bill reminders
- YNAB-compatible export — an exit strategy from IGAB itself, because a tool
  you can leave is a tool you can trust

---

## Contributing

Development setup, conventions, quality gates, and testing requirements are
documented in [CONTRIBUTING.md](CONTRIBUTING.md). Run `just` to see every
available command.

---

## License

AGPL-3.0 — see [LICENSE](LICENSE).
