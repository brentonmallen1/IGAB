<p align="center">
  <img src="docs/images/igab-icon.svg" alt="IGAB Logo" width="120" height="120" />
</p>

<h1 align="center">IGAB — I've Got A Budget</h1>

<p align="center">
  <strong>Self-hosted envelope budgeting for your household.<br/>Your money, your data, your hardware.</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#screenshots">Screenshots</a> •
  <a href="#getting-started">Getting Started</a> •
  <a href="docs/deployment.md">Deployment</a> •
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.14-blue" alt="Python 3.14" />
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

It also tries to answer the question a ledger can't: **what should I do
next?** A guided roadmap reads your real numbers, shows where you stand, and
explains itself — with a checkup, calculators, and a wishlist that all work
from the same numbers.

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

Thirty reports in six groups, all reading the same ledger:

| Group | Reports |
| --- | --- |
| Overview | To-be-assigned, net worth, burn rate, savings rate, and top spending on one dashboard |
| Financial State | Net worth, account composition, liabilities, savings, savings rate, essentials, emergency fund coverage |
| Cash Flow | Income vs. expenses, income by source, burn rate, Sankey money-flow diagram, cash projection |
| Budget | Budget vs. actual, category history, cumulative variance, volatility |
| Spending | Spending trends, breakdown, cost of living, wishlist discipline, Pareto, treemap, seasonality heatmap, subscriptions |
| Insights | Plan vs. reality, anomaly detection, payee analysis, day-of-week patterns (with payday effect), event timeline |

Filter by date range, category, payee, or account. Star the reports you read
every week, click any figure to drill down to the transactions behind it, and
export a report as CSV, JSON, or PNG.

---

## Screenshots

<p align="center">
  <img src="screenshots/budget.png" alt="Monthly budget grid with category groups, targets, and available balances" width="900" />
</p>

<p align="center"><em>The budget grid — every dollar assigned a job.</em></p>

<p align="center">
  <img src="screenshots/accounts.png" alt="Checking account register with cleared, uncleared, and working balances" width="900" />
</p>

<p align="center"><em>The account register — cleared, uncleared, and working balances, with upcoming scheduled transactions.</em></p>

<p align="center">
  <a href="screenshots/"><strong>See more screenshots →</strong></a>
</p>

---

## Features

### Budgeting
- Monthly budget grid with category groups, targets, and available balances,
  in three densities
- Move money between categories in place — cover overspending in two clicks
- Auto-assign and quick-budget helpers for funding categories
- Custom saved budget views (filter and arrange the grid the way you think)
- Tags on categories and payees — mark what is *Essential* and the cost-of-living
  and emergency-fund reports read it
- Per-budget currency, date, and time formats

### Guidance & Tools
- **A roadmap that reads your budget** — the r/personalfinance flowchart,
  re-authored as data: walk it one step at a time, read it end to end, or
  explore the map. It marks where you actually are
- **Every inference is explained, correctable, and optional** — IGAB shows
  how it decided; point it at the right category or account, tell it about
  money it can't see, or switch personalization off entirely
- **A checkup with no score** — each figure against the target the roadmap
  states, plus a health report you run when you want it. The only ambient
  signal is a small amber dot on the step concerned
- **Calculators you can check by hand** — payoff planner (avalanche vs.
  snowball), pay down vs. save, compare two loans, balance transfer, emergency
  fund sizer
- **Category planner** — draft a category structure, then apply it to the
  real budget with a preview that cannot disagree with what happens
- **Credit score tracker** — scores you looked up yourself, by date and bureau
- **A wishlist inside the budget** — a want gets an envelope, a cooling-off
  period, and a place in line; the numbers say when, and IGAB shows what
  pulled money out of it
- **A plain-language glossary** — what each term means, and where it lives in
  the app
- **It never pushes** — no notifications, digests, or badges. Educational
  only: no advice, no market projections, no single health score

### Accounts & Transactions
- **On-budget and tracking accounts** — checking, savings, cash, credit cards,
  loans, investments — plus custom account types
- **Full transaction editor** — splits, transfers, memos, flags, file attachments
- **Bulk actions** — categorize, approve, or clean up many transactions at once
- **Payee management** —  merge tooling and fuzzy duplicate detection
- **Scheduled/recurring transactions**
- **Statement reconciliation** with adjustment handling
- **Loans and liabilities** — amortization schedules, promotional-financing
  periods, an extra-payment simulator, and a payoff estimate based on what
  you actually pay, not the minimum
- **Assets** — property, vehicles, and anything else with a stated, dated
  worth, so net worth counts what you own and not just what is in the bank

### Bank Sync & Import
- **SimpleFIN sync** — link multiple banks, with encrypted tokens, scored
  deduplication, and a review queue for uncertain matches
- **Four clearing states, one meaning each** — pending, uncleared, cleared,
  reconciled. A hold that posts clears in place; a changed amount goes to
  review instead of being applied silently
- **YNAB import** — bring over your full export (accounts, categories,
  transactions, budget history) and start where YNAB left off: every envelope
  and card reserve opens at YNAB's own figures at the export's last complete
  month. Every import checks Ready to Assign against the export and says
  where the two differ (see [docs/ynab-import.md](docs/ynab-import.md))
- **CSV import** — per-account bank CSV import with configurable parsing
  (including EU decimal formats), hash-based dedup, and a mapping step that
  remembers each account's choices

### AI Assist *(optional)*

Everything here runs against your own [Ollama](https://ollama.com/) server —
nothing leaves your network — and switches off cleanly when AI is disabled or
unreachable.

- **Ask the budget** — a chat panel beside the page, with tabs for separate
  conversations. It answers from read-only queries over your own ledger,
  shows every tool call it made, and flags any figure it cannot trace back
  to the budget
- **Receipt → transaction** — photograph a receipt (or pick an image or PDF)
  and a local vision model drafts the transaction, files the image as its
  attachment, and turns itemized lines into splits
- **Yours to approve** — scans land unapproved in a review queue and run in
  the background; a failed scan still leaves a transaction with the receipt
  attached
- **Type it or say it** — "coffee at Starbucks 5.50 yesterday" becomes a
  drafted transaction, by keyboard or by microphone
- **Payee normalization and category suggestions** on ordinary manual entry
- **AI Activity page** — every job with its model, prompt, and raw response,
  so you can see why it guessed what it did

Configured in System → AI. Receipt scanning needs a **vision-capable** model;
the text features work with any general model.

### Mobile & PWA
- **Installable app** — add IGAB to your home screen; the shell is precached
  for instant launches, data is always live, and new versions arrive via an
  in-app prompt
- **Phone-first UI** — bottom tab navigation, bottom sheets, card layouts,
  long-press multi-select
- **Quick-add** — amount-first entry built for the checkout line: payee memory
  prefills the category, "save & add another" chains purchases, and a receipt
  splits without leaving the sheet
- **Receipt camera** — snap a photo while adding a transaction (HEIC included);
  hand it to the scanner and the transaction fills itself in
- **Nearby payees** *(opt-in, per device)* — quick-add suggests payees you've
  used near where you're standing; coordinates stay on your server

### Comfort & Polish
- **20 themes, each in light and dark** — 40 variants in all: Default, Gruvbox,
  Catppuccin, Rosé Pine (+ Moon), Nord (+ Aurora), Synthwave, Cozy, Vapor,
  Kodachrome, Phosphor, Blueprint, Desert, Bauhaus, Paper, E-Ink, 90's, 80's,
  and 80's Pop
- **Contrast is tested, not assumed** — an automated suite holds every palette to
  WCAG AA across all its surfaces, and the UI honors `prefers-contrast`
- **⌘K command palette** — navigation, budget actions, theme switching, and live
  search from one prompt
- Information-dense, keyboard-friendly, and calm — color is reserved for state
  that matters

### Household & History
- **Multiple budgets** — keep a household budget and a side project apart,
  and try a generated sample budget before entering your own data
- **Share a budget** — invite another person as owner or member; owners manage
  membership, members do everything day-to-day
- **Activity log with undo and redo** — every change is recorded and
  reversible, one at a time, as a batch, or "revert to here"; a bad CSV
  import is one undo, not an evening of cleanup
- **Budget snapshots** — download a single budget as an exact file, keep a
  set on the server, and clone, import, or restore from one
- **YNAB-format export** — a readable zip in YNAB's own shape, so you can
  open it in a spreadsheet, hand it to another tool, or import it back. A
  tool you can leave is a tool you can trust

### Operations Built In
- Automated **daily database backups** with retention pruning (production
  profile), plus one-command manual backup and restore
- **Data integrity checker** in Settings (and via API) that audits your
  budget's invariants and points at the offending transactions
- Opt-in **update check** against GitHub releases — off by default
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

Try a generated budget before entering your own data — from the budget
selector's "Try a Sample Budget", or `just sample-budget your@email.com
"Demo Budget"`. See [docs/sample-budget.md](docs/sample-budget.md).

### Production Deployment

The simplest way to run IGAB is the all-in-one image — PostgreSQL, the API,
nginx, and automatic backups in one container, with all data under one
volume:

```sh
docker run -d \
  --name igab \
  -p 8080:8080 \
  -e SECRET_KEY=$(openssl rand -hex 32) \
  -e ADMIN_PASSWORD=your-password \
  -v ./data:/data \
  ghcr.io/brentonmallen1/igab-aio:latest
```

**Unraid:** a container template for the same image ships in
[`unraid/`](unraid/) — add this repo under *Docker → Template Repositories*
and **igab-aio** appears in the Add Container dropdown. One container, one
appdata folder. [docs/unraid.md](docs/unraid.md) walks through the install
and the compose-based alternative.

[docs/deployment.md](docs/deployment.md) has the rest: the compose and
multi-container profiles, HTTPS for installing the app on your phone, every
configuration variable, backups and restore, [updating](docs/upgrading.md),
and a fresh reset.

---

## Architecture

| Layer | Technology |
| --- | --- |
| Backend | Python 3.14, FastAPI (fully async), SQLAlchemy + asyncpg, Alembic |
| Frontend | React 19, TypeScript, Vite, Zustand, React Query, recharts |
| Database | PostgreSQL 16 |
| Deployment | Docker Compose (nginx + daily backups in the production profile) |

---

## Roadmap

- Deeper mobile polish (chart touch interactions, per-page refinements)
- Bill reminders

---

## Contributing

Development setup, conventions, quality gates, and testing requirements are
documented in [CONTRIBUTING.md](CONTRIBUTING.md). Run `just` to see every
available command.

---

## License

AGPL-3.0 — see [LICENSE](LICENSE).
