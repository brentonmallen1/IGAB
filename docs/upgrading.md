# Upgrading IGAB Safely

Updating to a new image never touches your data volume — but financial data
deserves a belt-and-suspenders routine. This is it. The short version: **back
up, pull, restart, verify.** The whole thing takes about two minutes.

## What lives where

Everything that matters survives a container update or recreation as long as
the data volume stays mounted.

### All-in-One (AIO)

One volume: `./data:/data` (or your `DATA_DIR`).

| Path | Contents | Survives update? |
| --- | --- | --- |
| `/data/postgres` | The database itself | ✅ on the volume |
| `/data/attachments` | Receipt images / attachments | ✅ on the volume |
| `/data/backups` | Backup dumps and archives | ✅ on the volume |
| everything else | App code, OS — comes from the image | ♻️ replaced by updates (by design) |

> **Known issue in releases before the backup-path fix:** the backup agent
> wrote its dumps to `/backups` *inside* the container instead of
> `/data/backups`, so scheduled backups did **not** survive container
> recreation (and the in-app backup panel showed the service as offline).
> Your database and attachments were always safe on the volume — only the
> backup archives were affected. See
> [One-time notes for specific releases](#one-time-notes-for-specific-releases).

### Multi-Container

| Location | Contents |
| --- | --- |
| `postgres_data` named volume (or your override) | The database |
| `./data/attachments` bind mount | Receipt images / attachments |
| `${BACKUP_DIR:-./backups}` bind mount | Backup dumps and archives |

## Before you update

1. **Confirm the data volume is mounted** (AIO):

   ```sh
   docker inspect igab --format '{{ range .Mounts }}{{ .Source }} -> {{ .Destination }}{{ "\n" }}{{ end }}'
   ```

   You should see your data directory mapped to `/data`. If you don't, stop —
   figure out where your data is before updating anything.

2. **Take a manual backup that lands on the host.** Preferred: Settings →
   Backups → *Back up now*, then confirm a fresh `igab-<timestamp>.dump`
   appeared in your backups directory on the host.

   If the backup service shows **offline** (all AIO releases before the
   backup-path fix), run the dump directly — it writes to the mounted volume,
   bypassing the broken path:

   ```sh
   # Database dump onto the host volume
   docker exec igab sh -c 'PATH=/usr/lib/postgresql/16/bin:$PATH \
     PGPASSWORD=igab pg_dump -h localhost -U igab -Fc igab \
     > /data/backups/manual-$(date +%Y%m%d-%H%M%S).dump'

   # Attachments archive onto the host volume
   docker exec igab sh -c 'tar czf \
     /data/backups/manual-attachments-$(date +%Y%m%d-%H%M%S).tar.gz \
     -C /data attachments'
   ```

   Then confirm both files exist in `./data/backups/` **on the host**, not
   just inside the container:

   ```sh
   ls -lh ./data/backups/
   ```

   Multi-container: `just backup` (writes `backups/igab-<timestamp>.dump`
   from the running `db` container).

3. **Optional but wise:** copy that backup somewhere that isn't this machine.

## Updating

Database migrations run automatically when the new container starts — there
is no separate migration step.

**AIO with Docker Compose:**

```sh
docker compose -f docker-compose.aio.yml pull
docker compose -f docker-compose.aio.yml up -d
```

**AIO with `docker run`:** pull `ghcr.io/brentonmallen1/igab-aio:latest`
(or a version tag), remove the old container, and re-run your original
`docker run` command — same volume mount, same env vars.

**Multi-container:**

```sh
docker compose --profile production pull
docker compose --profile production up -d
```

**Unraid:** use the template's update action as usual; it pulls the new image
and recreates the container with the same appdata mapping.

Pinning a version tag (e.g. `igab-aio:2026.08.1`) instead of `latest` makes
updates deliberate and rollbacks trivial.

## After updating

1. Wait for the container to report healthy, then check
   `http://<host>:<port>/api/v1/health`.
2. Log in and spot-check a couple of account balances and the current month's
   budget.
3. Skim the container logs for migration errors:

   ```sh
   docker logs igab --since 10m | grep -iE 'alembic|error' || echo "clean"
   ```

4. Settings → Data Integrity → run the check. Drift shows up here first.

## Rolling back

If something is wrong, run the previous image version again — the data volume
is untouched by the update itself:

```sh
docker compose -f docker-compose.aio.yml pull igab  # or edit the tag
# pin the previous tag in docker-compose.aio.yml / your run command, then:
docker compose -f docker-compose.aio.yml up -d
```

Only restore from a dump if a migration actually corrupted data (rare — and
this is why the pre-update backup exists). Restore via Settings → Backups, or
manually:

```sh
docker exec igab sh -c 'PATH=/usr/lib/postgresql/16/bin:$PATH \
  PGPASSWORD=igab pg_restore --clean --if-exists --no-owner \
  -h localhost -U igab -d igab /data/backups/<your-backup>.dump'
```

Multi-container: `just restore <file>`.

**Note:** rolling back to an *older* image after a *newer* one has migrated
the database can fail if the migration changed the schema. Restore the
pre-update dump in that case.

## One-time notes for specific releases

### Upgrading to the release where hidden categories became archived

The flag behind "hidden" categories and groups is renamed to `is_archived`,
and a `archived_at` column is added beside it. Nothing is reclassified: every
category and group that was hidden is now archived, which is what the flag
already meant — it blocked assigning and blocked filing, it just also drew the
row greyed out in the grid.

No manual steps are required. Two things to expect afterwards:

1. **"Show hidden" is gone.** Archived envelopes are no longer drawn in the
   budget grid at all; **See archived** in the budget header opens them, with
   their transaction count, the date they were archived, and anything still
   left in one.
2. **Rows archived before this release have no date.** The column cannot be
   backfilled honestly — `updated_at` moves on any edit — so those read
   "Archived before dates were kept" rather than showing an invented date.

**Rolling back to an older image** needs the migration's downgrade, which the
older image will not run for you: restore the pre-update dump, per *Rolling
back* above. The downgrade also does not restore one thing on purpose — the
Credit Card Payments group was previously kept hidden only to keep card
envelopes out of the pickers, and that is now decided on the group's own
merits, so the migration un-hides it and leaves it visible either way.

### Upgrading to the release with the backup-path fix

This release fixes the AIO backup agent writing to ephemeral container
storage (`/backups`) instead of the data volume (`/data/backups`), which also
made the backup service show as **offline** in Settings → Backups.

No manual steps are required beyond the normal routine above. After updating,
verify the fix took:

1. Settings → Backups shows the service **online** within ~30 seconds.
2. *Back up now* completes and the new `igab-<timestamp>.dump` appears in
   `./data/backups/` on the host.
3. Any backups the old agent wrote inside the container are gone — they were
   never persisted (that's the bug). Your pre-update manual backup covers the
   gap until the first scheduled backup lands.
