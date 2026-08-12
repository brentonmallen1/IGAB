"""Opt-in update check for self-hosted installs.

Compares the running version (APP_VERSION env, stamped into release images
by the GHCR workflow; "dev" for local builds) against the latest GitHub
release. Never contacts GitHub unless update_check_enabled is switched on
in Settings — it ships off by default. Results are cached in-process so UI
polling doesn't hammer the GitHub API.
"""

import os
import re
import time

import httpx

RELEASES_URL = "https://api.github.com/repos/brentonmallen1/IGAB/releases/latest"
CACHE_TTL_S = 6 * 60 * 60

# {"at": float, "latest": str | None, "url": str | None}
_cache: dict = {}


def current_version() -> str:
    return os.getenv("APP_VERSION", "dev")


def parse_version(version: str) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def is_newer(latest: str | None, current: str) -> bool:
    """True only when both versions parse and latest is strictly newer —
    a dev build or an unparseable tag never produces an update nag."""
    if latest is None:
        return False
    latest_v = parse_version(latest)
    current_v = parse_version(current)
    if latest_v is None or current_v is None:
        return False
    return latest_v > current_v


async def fetch_latest_release() -> tuple[str | None, str | None]:
    """(tag_name, html_url) of the latest release, cached; (None, None) on
    any failure — an unreachable GitHub must never break the app."""
    now = time.monotonic()
    if _cache and now - _cache["at"] < CACHE_TTL_S:
        return _cache["latest"], _cache["url"]
    latest: str | None = None
    url: str | None = None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(RELEASES_URL, headers={"Accept": "application/vnd.github+json"})
            if resp.status_code == 200:
                data = resp.json()
                latest = data.get("tag_name") or None
                url = data.get("html_url") or None
    except httpx.HTTPError:
        pass
    # Failures are cached too: a down GitHub retries next TTL, not every poll
    _cache.update({"at": now, "latest": latest, "url": url})
    return latest, url
