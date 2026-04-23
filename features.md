# IGAB: I've Got A Budget

## Build a Product Requirements Document (PRD) for a Self-Hosted YNAB-like Budgeting System

You are an expert product manager, systems architect, and full-stack engineer.

Your task is to generate a **complete, implementation-ready PRD** for a **self-hosted budgeting application** with feature parity to YNAB (minus native mobile apps), using:

* **Backend:** Python (FastAPI preferred)
* **Database:** PostgreSQL
* **Frontend:** React (TypeScript)
* **Deployment target:** Self-hosted (Docker-first)
* **Client:** Web + PWA (offline-capable)


NOTEs / thoughts:
- This is a YNAB alternative with the intent of being a budget envelope system
- I plan to be using simpleFIN for auto ingesting of financial transactions
  - https://beta-bridge.simplefin.org/info/developers
- I will also be migrating from ynab4 using this guide: https://actualbudget.org/docs/api/ 
- I'd like to be able to control color palettes. there should be a light and dark mode, and I'd also like to integrate the standard kind of coding color palette options like gruvbox, capuchin, rose pine, and nord



# 0. Implementation and Architecture Notes
- The overall intent is to self host this 
- The name of the application is IGAB which stands for I've Got A Budget
- python 3.13
- uv for the env and dependency management for the backend
- justfile for commands
- env file to manage env variables like ports, admin credentials, db connection and credentials
- Unified docker compose for both the frontend and backend
- use common components and existing libraries where applicable, don't reinvent things unless it really makes sense
  - use a charting library like recharts for the frontend
- frontend should be built so that their's a css per component so that the styling is compartmentalized to make it easier to edit, etc. no global styling


---

# 1. Product Overview

Define:

* Product purpose
* Target user (single user, household, small group)
* Core philosophy:

  * Zero-based budgeting
  * Cash-based system (no future income allocation)
  * Category envelope model
* Explicit non-goals:

  * No investment tracking
  * No bill pay
  * No predictive forecasting

---

# 2. Core System Invariants (CRITICAL)

The system must ALWAYS enforce:

* Σ(category balances) == total budgeted funds
* Account balances == sum(transactions)
* Transfers do not affect net worth
* No allocation of future income
* Category balance rollovers are lossless across periods

Define:

* How invariants are enforced (service layer, DB constraints, or both)
* Failure modes and recovery strategies

---

# 3. Functional Requirements

## 3.1 Budgeting Engine

* Zero-based allocation system
* Monthly budget periods (extensible)
* Carryover balances
* Overspending handling:

  * configurable: allow negative vs enforce correction
* Fund movement between categories
* Auto-assign rules:

  * fill targets
  * proportional
  * equal distribution

---

## 3.2 Data Model (PostgreSQL)

Design full schema including:

### Core Tables

* users
* budgets
* accounts
* transactions
* categories
* category_groups
* assignments
* payees
* scheduled_transactions
* goals
* import_batches
* reconciliation_snapshots

### Requirements

* Proper indexing strategy
* Foreign key constraints
* Soft delete vs hard delete policy
* Auditability (timestamps, optional event log)

---

## 3.3 Accounts System

* Account types:

  * checking
  * savings
  * credit card
  * loan
  * tracking (off-budget)
* Transfer logic:

  * dual-entry
  * no category impact
* Credit card handling:

  * liability tracking
  * payment category auto-funding

---

## 3.4 Transaction System

* Manual entry
* Import (CSV initially; extensible)
* Deduplication strategy
* Payee normalization
* Split transactions
* Categorization memory
* Search and filtering

---

## 3.5 Categories & Budget Structure

* Category groups
* Ordering persistence
* Category notes
* Balance calculation:

  * prior + assigned − activity
* Hidden/archive support

---

## 3.6 Targets / Goals

Support:

* Needed-for-spending
* Savings balance
* Target by date
* Monthly funding

Include:

* Contribution calculation logic
* Status evaluation (underfunded/funded/overfunded)

---

## 3.7 Scheduled Transactions

* Recurrence rules:

  * daily/weekly/monthly/yearly
* Auto-create vs reminder mode
* Upcoming transaction projection

---

## 3.8 Reconciliation

* Statement matching workflow
* Locking reconciled transactions
* Adjustment handling
* History tracking

---

## 3.9 Loan / Debt Modeling

* Amortization schedule
* Interest calculation
* Payment splitting
* Extra payment simulation

---

## 3.10 Reporting & Analytics

* Spending by category
* Income vs expenses
* Net worth
* Time-series queries
* Export (CSV/JSON)

---

## 3.11 System Metrics

* Age of money (cashflow lag)
* Burn rate
* Baseline expense metric

---

# 4. API Design (FastAPI)

Define:

* REST or GraphQL (prefer REST unless justified)
* Endpoint structure for all entities
* Pagination, filtering, sorting
* Idempotency (especially for imports)
* Webhooks (optional)

---

# 5. Frontend (React + TypeScript)

Define:

## Core Views

* Budget view (category table)
* Account register
* Transaction editor
* Reports dashboard

## UX Requirements

* Keyboard-first workflows
* Fast category assignment
* Inline editing
* Optimistic updates

## State Management

* React Query / Zustand / Redux (justify choice)

---

# 6. PWA Requirements

* Installable app manifest
* Offline-first capability:

  * IndexedDB cache
  * Sync queue
* Conflict resolution strategy
* Background sync

---

# 7. Architecture

## Backend

* FastAPI structure:

  * routers
  * services
  * repositories
* Domain layer enforcing invariants

## Database

* PostgreSQL
* Migration strategy (Alembic)

## Deployment

* Docker Compose:

  * api
  * db
  * frontend
* Optional:

  * reverse proxy (nginx)
  * auth service

---

# 8. Security

* Authentication:

  * JWT or session-based
* Authorization:

  * per-budget access
* Optional:

  * 2FA (TOTP)
* Secrets handling

---

# 9. Performance Considerations

* Transaction-heavy workloads
* Indexing strategy
* Aggregation queries (materialized views optional)
* Caching strategy

---

# 10. Edge Cases & Hard Problems

Explicitly address:

* Credit card payment category logic
* Import deduplication collisions
* Partial period target calculations
* Reconciliation drift
* Concurrent edits (multi-user)
* Floating point vs decimal precision (must use DECIMAL)

---

# 11. Milestones / Phased Build

Define:

### Phase 1 (MVP)

* Transactions
* Categories
* Accounts
* Basic budgeting

### Phase 2

* Targets
* Scheduled transactions
* Reports

### Phase 3

* Reconciliation
* Loans
* PWA offline

---

# 12. Deliverables

The PRD output should include:

* System architecture diagram (textual)
* Database schema (SQL)
* API spec (endpoint list)
* Key algorithms (pseudo-code)
* Tradeoffs and alternatives

---

# Constraints

* Must prioritize correctness over convenience
* Must preserve financial invariants at all times
* Avoid unnecessary complexity unless justified
* Design for extensibility but not abstraction overkill

---

# Tone / Style

* Be precise and implementation-oriented
* Avoid vague product language
* Prefer explicit schemas, contracts, and logic
* Include pseudo-code where appropriate
