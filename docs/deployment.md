# Deployment and Operations

How to run IGAB for real: production images, HTTPS for the phone app,
configuration, backups, updating, and resetting. Development setup is in
[CONTRIBUTING.md](../CONTRIBUTING.md); the README covers the quick start.

## Production Deployment

IGAB offers two deployment modes:

### All-in-One (Recommended for Home Servers)

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
| `OLLAMA_MODEL` | | `llama3.2` | Seed LLM model; System → AI overrides it, and sets the vision model for receipts |
| `BACKUP_INTERVAL_HOURS` | | `24` | Hours between backups |
| `BACKUP_KEEP_DAYS` | | `30` | Prune backups older than this |
| `BACKUP_AGE_RECIPIENT` | | — | age public key for encrypted backups |
| `SIMPLEFIN_ENCRYPTION_KEY` | | — | Fernet key for bank sync — see [Bank sync key](#bank-sync-key). Not a hex string; `openssl rand -hex 32` will not work |

### Multi-Container (Advanced)

For more control, use the multi-container production profile:

```sh
just prod
```

Separate containers for PostgreSQL, the API, nginx, and backups — for an
external database or existing infrastructure.

Tagged releases publish multi-arch (amd64/arm64) images to GHCR —
`ghcr.io/brentonmallen1/igab-api`, `igab-web`, `igab-backup`, and `igab-aio`.

**Unraid:** see [unraid.md](unraid.md) for two supported paths —
the Docker Compose Manager plugin driving this repo's production profile, or
the Community Applications templates in [`unraid/`](../unraid/) using the
published images. The `igab-aio` template is the easiest — one container, one
appdata folder.

## Install on Your Phone (PWA)

Installing requires **HTTPS** (service workers and geolocation need a secure
context; `localhost` is exempt). Two good ways to get there:

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

The app caches its own shell, but your data always comes live from the server
— when it's unreachable you get a banner, not stale numbers.

## Configuration

All configuration lives in `.env` (see `.env.example` for the full list):

| Area | Keys |
| --- | --- |
| Database | `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT`, `DATABASE_URL` |
| Auth | `SECRET_KEY`, token lifetimes, `ADMIN_EMAIL`, `ADMIN_PASSWORD` |
| Ports | `API_PORT`, `FRONTEND_PORT`, `NGINX_PORT` |
| Bank sync | `SIMPLEFIN_ENCRYPTION_KEY` (Fernet key for access tokens — see [Bank sync key](#bank-sync-key)) |
| AI (optional) | `OLLAMA_HOST`, `OLLAMA_MODEL` |
| Email (optional) | `SMTP_*` |

### Bank sync key

SimpleFIN access URLs are stored encrypted, so bank sync needs
`SIMPLEFIN_ENCRYPTION_KEY` before you can connect. Generate one with:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Two things to know:

- **It is not the `SECRET_KEY` recipe.** A Fernet key is 32 url-safe base64
  bytes; a hex string from `openssl rand -hex 32` is rejected.
- **Keep it.** Connections are encrypted with this key and cannot be read with
  any other. If it is lost or changed, every SimpleFIN connection has to be
  removed and set up again.

On Unraid the field is on the container's edit page with **Advanced View**
turned on. System → SimpleFIN reports what is wrong when the key is missing
or malformed, and refuses to spend your (single-use) setup token until it is
fixed.

---

## Operations

### Backups

Financial data needs a backup story before it needs anything else.

- **In-app (System → Server Backups):** service status, every existing backup,
  schedule/retention/encryption settings (applied live, no restart), back up
  now, and restore from a dump. Restore offers to back up the current data
  first (`igab-prerestore-*.dump`), then restarts the app onto the restored
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
- Settings precedence: values set in the app win; the `BACKUP_*` env vars are
  the fallback and boot-time defaults, so backups keep running even when the
  app can't reach the database.
- Retention: files older than `backup_keep_days` (default 30) are pruned, but
  the newest `backup_keep_min` (default 7) of each kind are always kept, so a
  stretch of failed backups can't delete your last good ones. Writes are
  atomic, a failed dump skips pruning, and a failed cycle retries after 15
  minutes.
- **Encryption (optional):** set the key in System → Server Backups (or
  `BACKUP_AGE_RECIPIENT`) to an [age](https://age-encryption.org) public key
  and both file kinds are written `.age`-encrypted. Keep the private key
  somewhere that isn't this server — which means encrypted backups can't be
  restored from the app. Restore with
  `BACKUP_AGE_KEY_FILE=<identity file> just restore <file>.dump.age`;
  attachments:
  `age -d -i <identity file> <file>.tar.gz.age | tar -xz -C data/attachments`.
- Point `BACKUP_DIR` at a disk that is not the database's disk. There is no
  encryption at rest by design — the server needs plaintext to run queries;
  use host disk encryption (e.g. LUKS) if stolen disks are in your threat
  model.

### Updating

Updates never touch the data volume, but back up first anyway — it takes two
minutes and it's your money's history. The routine:

```sh
# 1. Back up (System → Server Backups → "Back up now", or just backup)
# 2. Pull and restart
docker compose -f docker-compose.aio.yml pull
docker compose -f docker-compose.aio.yml up -d
# 3. Verify: health endpoint, log in, spot-check balances
```

Database migrations run automatically on startup. See
[upgrading.md](upgrading.md) for the full runbook: pre-update
checks, what lives where, multi-container/Unraid steps, rollback, and
one-time notes for specific releases.

### Update Notifications

System → Updates has an opt-in check against this repo's GitHub releases —
**off by default**, nothing is sent until you enable it. A newer release shows
as a small dot next to Settings, with a link to the notes. Dev builds never
nag.

### Data Integrity

Settings → Data Integrity runs the invariant suite against your budget (also
`GET /api/v1/budgets/{id}/integrity`): money conservation, split and transfer
integrity, orphaned review matches, stale bank authorizations. Run it after
imports or whenever something looks off — drift shows up here first, with the
offending transaction ids.

### Fresh Install / Reset

```sh
docker compose down -v      # or: drop the database
docker compose up -d db
just migrate                # single squashed migration (0001)
```
