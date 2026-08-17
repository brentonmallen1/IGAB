# Running IGAB on Unraid

Three supported paths — pick the one that fits:

- **[Path A — All-in-One (AIO)](#path-a--all-in-one-aio)**: single container with embedded
  PostgreSQL, API, web UI, and backups. Simplest setup — one container, one appdata folder.
- **[Path B — Docker Compose Manager](#path-b--docker-compose-manager)**: drive the repo's
  `docker-compose.yml` production profile from Unraid's Compose plugin. Identical to the
  reference deployment, updates by `git pull`.
- **[Path C — Community Applications templates](#path-c--ca-templates-with-published-images)**:
  individual containers from published GHCR images using the templates in
  [`unraid/`](../unraid/). More idiomatic Unraid (per-container pages, WebUI button,
  update notifications from Docker tab), no repo checkout on the server.

Paths B and C end up with the same four containers:

| Container | Image | Role |
| --- | --- | --- |
| `igab-db` | `postgres:16-alpine` (official) | database |
| `igab-api` | `ghcr.io/brentonmallen1/igab-api` | FastAPI backend, runs migrations on start |
| `igab-web` | `ghcr.io/brentonmallen1/igab-web` | nginx: serves the UI, proxies `/api` to the API |
| `igab-backup` | `ghcr.io/brentonmallen1/igab-backup` | periodic pg_dump + attachment archives, retention pruning, optional age encryption |

Only `igab-web` needs a host port. The browser talks to nginx; nginx proxies `/api`
same-origin to the backend — so **no CORS configuration is needed** and `VITE_API_URL`
does not exist in production images (the frontend is built with a relative `/api/v1`).

---

## Path A — All-in-One (AIO)

The simplest option: everything runs in a single container.

| Container | Image | Role |
| --- | --- | --- |
| `igab` | `ghcr.io/brentonmallen1/igab-aio` | PostgreSQL + API + nginx + backups |

### 1. Install from Community Applications

Search for "IGAB" in CA and install the **igab-aio** template, or add it manually from
[`unraid/igab-aio.xml`](../unraid/igab-aio.xml).

### 2. Configure

| Setting | Value |
| --- | --- |
| **Secret Key** | Generate with `openssl rand -hex 32` |
| **Admin Email** | Your login email |
| **Admin Password** | Initial password (change in-app after first login) |
| **Web Port** | `8080` (or any free port) |
| **Data** | `/mnt/user/appdata/igab` — all data lives here |

Optional settings (under "Show more"):
- **Ollama Host**: URL of your Ollama server for AI features
- **Backup settings**: interval, retention, encryption key

### 3. Start

Click Apply. Open `http://<unraid-ip>:8080` and log in.

### Storage

AIO uses a single `/data` mount containing:
```
/mnt/user/appdata/igab/
├── postgres/      # database
├── attachments/   # receipts/documents
└── backups/       # backup archives
```

For extra safety, you can split backups to a separate share by mounting
`/data/backups` separately in the template's advanced settings — but for most
users the single-folder approach is fine.

---

## Storage layout (Paths B & C)

Recommended shares:

```
/mnt/user/appdata/igab/postgres      # database data (cache/pool is fine)
/mnt/user/appdata/igab/attachments   # receipts/documents
/mnt/user/backups/igab               # backup archives — array, NOT the appdata pool
```

Put backups on a different disk/share than the database. If the cache drive holding
appdata dies, backups that lived next to the database die with it.

## Path B — Docker Compose Manager

1. Install the **Docker Compose Manager** plugin from Community Applications.
2. Get the repo onto the server, e.g. `/mnt/user/appdata/igab-src`:

   ```sh
   git clone https://github.com/brentonmallen1/IGAB.git /mnt/user/appdata/igab-src
   ```

3. Create the env file: copy `.env.example` → `.env` in the repo root and set at minimum:

   ```sh
   SECRET_KEY=...            # openssl rand -hex 32
   ADMIN_EMAIL=you@example.com
   ADMIN_PASSWORD=...        # app refuses to start on empty/default
   DB_PASSWORD=...
   NGINX_PORT=8480           # host port for the web UI
   COMPOSE_PROFILES=production
   # point data at Unraid shares (defaults are relative ./data, ./backups):
   DB_DATA_DIR=/mnt/user/appdata/igab/postgres
   ATTACHMENTS_DIR=/mnt/user/appdata/igab/attachments
   BACKUP_DIR=/mnt/user/backups/igab
   ```

   `COMPOSE_PROFILES=production` selects nginx + the backup agent (and skips the
   dev-only Vite container). Leave `CORS_ORIGINS` and `VITE_API_URL` unset.

4. In the plugin, **Add New Stack**, point it at the repo directory (it picks up
   `docker-compose.yml` and `.env`), then **Compose Up**.
5. Open `http://<unraid-ip>:8480` and log in with the admin credentials.

Updating: `git pull` in the repo directory, then **Compose Up** again (the plugin
rebuilds changed images).

## Path C — CA templates with published images

The templates live in [`unraid/`](../unraid/) — see that folder's README for how to add
them to Unraid (template repo URL or manual XML drop-in).

### 1. Create the Docker network

Container-name DNS (the templates' defaults like `igab-db`, `igab-api:8000`) only works
on a **custom** Docker network. In an Unraid terminal:

```sh
docker network create igab
```

It then appears in each template's Network dropdown.

### 2. PostgreSQL (`igab-db`)

Use any official PostgreSQL 16 container (the CA "postgres" template works fine):

- **Name**: `igab-db` (the other templates' defaults assume this name)
- **Network**: `igab`
- **POSTGRES_USER** / **POSTGRES_DB**: `igab`
- **POSTGRES_PASSWORD**: pick one — you'll repeat it in `igab-api` and `igab-backup`
- **Data path**: `/var/lib/postgresql/data` → `/mnt/user/appdata/igab/postgres`
- No host port needed.

### 3. API (`igab-api` template)

- **DATABASE_URL**: change only the password in
  `postgresql+asyncpg://igab:changeme@igab-db:5432/igab`
- **SECRET_KEY**: `openssl rand -hex 32`
- **ADMIN_EMAIL** / **ADMIN_PASSWORD**: first-run login credentials
- Paths default to `/mnt/user/appdata/igab/attachments` and `/mnt/user/backups/igab`.

The API runs Alembic migrations automatically on start. If it starts before postgres is
ready it exits and Docker restarts it — in the Docker tab, order autostart as
`igab-db` → `igab-api` → `igab-web`/`igab-backup` (add a few seconds' wait) and it
settles on its own.

### 4. Web UI (`igab-web` template)

- **Web Port**: default `8480` → open `http://<unraid-ip>:8480` (WebUI button works too)
- **API_UPSTREAM**: leave at `igab-api:8000` unless you renamed the API container.

### 5. Backup agent (`igab-backup` template)

- **PGPASSWORD**: same as the postgres container
- **Backups path**: must match the API container's Backups path (the app lists backups
  and triggers/restores through that shared folder)
- **Attachments path**: the API's attachments folder, mounted read-only

Schedule, retention, and encryption are configured in the app under
**Settings → Backups** and picked up by the agent within seconds; the template's
`BACKUP_*` variables are only fallbacks for when the database is unreachable.

## After install (any path)

- **Log in** with `ADMIN_EMAIL` / `ADMIN_PASSWORD`, then change the password in-app.
- **Backups**: verify in Settings → Backups that the agent shows as running, trigger a
  manual backup, and — once — practice a restore. Optionally set an
  [age](https://age-encryption.org) public key there to encrypt backups at rest (keep
  the private key off the server); details in the README's
  [Backups](../README.md#backups) section.
- **HTTPS / phone install**: the PWA install and camera-based receipt capture need a
  secure context. Front `http://<unraid-ip>:8480` with your existing reverse proxy
  (SWAG, Nginx Proxy Manager, Traefik) or Tailscale — see
  [Install on Your Phone](../README.md#install-on-your-phone-pwa).
- **Update notifications**: Unraid's Docker tab flags new image versions (Paths A & C).
  The app also has its own opt-in check (Settings → Updates) that is **off by default** —
  nothing contacts GitHub unless you enable it.
- **Updating safely**: back up before pulling a new image — the two-minute routine
  (backup → pull → recreate → verify), rollback steps, and release-specific notes are
  in [docs/upgrading.md](upgrading.md).
- **Auth hardening**: IGAB ships single-user password auth and deliberately no
  TOTP/2FA — if you expose it beyond your LAN/tailnet, put it behind your own auth
  layer (Authelia, Authentik, Tailscale) like the rest of your self-hosted stack.
