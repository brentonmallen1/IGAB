# Unraid Community Applications templates

CA container templates for deploying IGAB from the published GHCR images:

- [`igab-api.xml`](igab-api.xml) — FastAPI backend (`ghcr.io/brentonmallen1/igab-api`)
- [`igab-web.xml`](igab-web.xml) — nginx web UI + `/api` proxy (`ghcr.io/brentonmallen1/igab-web`)
- [`igab-backup.xml`](igab-backup.xml) — backup agent (`ghcr.io/brentonmallen1/igab-backup`)

Pair them with any official **PostgreSQL 16** container named `igab-db`. Full
walkthrough (network setup, postgres pairing, install order, storage layout):
[docs/unraid.md](../docs/unraid.md).

## Using the templates

**Option 1 — template repository (recommended).** In Unraid: *Docker tab → Template
Repositories* (bottom of page) → add:

```
https://github.com/brentonmallen1/IGAB
```

Unraid scans the repo for template XMLs; the three IGAB templates then show up under
*Add Container → Template* dropdown (user templates section).

**Option 2 — manual drop-in.** Copy the three XML files to
`/boot/config/plugins/dockerMan/templates-user/` on the Unraid box; they appear in the
same dropdown.

## Install order

1. `docker network create igab` (terminal, once)
2. postgres 16 container named `igab-db` on that network
3. `igab-api`
4. `igab-web` (this one has the WebUI, default port 8480)
5. `igab-backup`

## Publishing note

Templates intentionally live in the app repo (referenced by their raw GitHub URLs in
`<TemplateURL>`). If they're ever split into a dedicated `unraid-templates` repo or
submitted to Community Applications proper, update the `<TemplateURL>` values to match
the new home.
