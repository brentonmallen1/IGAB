# IGAB — I've Got A Budget

Self-hosted YNAB-style envelope budgeting. Single household, zero-based
budgeting, SimpleFIN bank sync. See `CLAUDE.md` for the development guide and
`justfile` for all commands.

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

```
docker compose down -v      # or: drop the database
docker compose up -d db
just migrate                # single squashed migration (0001)
```

### Cutover from YNAB (recommended procedure)

1. Fresh database → import your YNAB export → link SimpleFIN and sync twice
   (the second sync must report `imported: 0`).
2. Run the integrity check — must be all green.
3. Parallel-run one full statement cycle per account (~2–4 weeks): budget in
   YNAB as usual, let IGAB sync daily, reconcile each statement in **both**.
4. Switch when every account has reconciled cleanly against the bank twice in
   a row in IGAB and a backup restore has been exercised once. Archive the
   final YNAB export.
